# ocr_engine_service.py
#
# Copyright (C) 2026-present Seed-43
# GPL-3.0-or-later

import json
import os
import shutil
import subprocess
import sys
import tempfile
from gettext import gettext as _
from io import BytesIO
from typing import Union

from gi.repository import GLib, GObject
from loguru import logger

from lens.config import tessdata_config

_DATA_DIR = os.path.join(
    os.environ.get("XDG_DATA_HOME", os.path.expanduser("~/.local/share")),
    "io.github.seed43.lens",
)
_VENV_DIR = os.path.join(_DATA_DIR, "ocr-venv")
_VENV_PIP = os.path.join(_VENV_DIR, "bin", "pip3")
_VENV_PY = os.path.join(_VENV_DIR, "bin", "python3")
_RUNNER_PATH = os.path.join(_DATA_DIR, "ocr_runner.py")

# How long a single extraction may take.  Generous because EasyOCR,
# EasyOCR and docTR download their models on first run.
_EXTRACT_TIMEOUT = 900

ENGINES = {
    "tesseract": {
        "label": "Tesseract 5",
        "packages": [],
        "pip_name": None,
        "extra_index": None,
    },
    "ocrad": {
        "label": "Ocrad",
        "packages": [],
        "pip_name": None,
        "extra_index": None,
    },
    "easyocr": {
        "label": "EasyOCR",
        "packages": ["easyocr"],
        "pip_name": "easyocr",
        "extra_index": None,
    },
    "doctr": {
        "label": "docTR",
        "packages": ["python-doctr[torch]"],
        "pip_name": "python-doctr",
        "extra_index": None,
    },
}
ENGINE_KEYS = ["tesseract", "ocrad", "easyocr", "doctr"]

# Engines that ship baked into the app itself (built from source in the
# Flatpak, or already present in a distro package) rather than being
# downloaded at runtime. Always reported as installed, never offered a
# Download button.
BUILTIN_ENGINES = {"tesseract", "ocrad"}


# --------------------------------------------------------------------- #
# Runner script executed by the host venv's Python.                      #
#                                                                        #
# Kept as a plain (non f-string) raw literal and written to disk, so     #
# there is no quoting or escaping to go wrong.  It reads argv, prints    #
# a single JSON object on stdout and never raises.                       #
# --------------------------------------------------------------------- #

_RUNNER_SOURCE = r'''
import json
import sys

# Tesseract three-letter codes to EasyOCR codes
EASYOCR_LANGS = {
    "eng": "en", "fra": "fr", "deu": "de", "spa": "es", "ita": "it",
    "por": "pt", "nld": "nl", "jpn": "ja", "kor": "ko", "rus": "ru",
    "ara": "ar", "hin": "hi", "tur": "tr", "ukr": "uk", "ces": "cs",
    "pol": "pl", "swe": "sv", "nor": "no", "dan": "da", "fin": "fi",
    "chi_sim": "ch_sim", "chi_tra": "ch_tra", "vie": "vi", "tha": "th",
    "ind": "id", "ron": "ro", "hun": "hu", "ell": "el", "bul": "bg",
    "hrv": "hr", "slk": "sk", "slv": "sl", "lit": "lt", "lav": "lv",
    "est": "et", "heb": "he", "fas": "fa", "urd": "ur", "ben": "bn",
    "tam": "ta", "tel": "te", "kan": "kn", "mar": "mr", "nep": "ne",
}


def _tess_codes(lang):
    return [c for c in lang.split("+") if c]


def run_easyocr(image_path, lang):
    import easyocr
    codes = []
    for c in _tess_codes(lang):
        mapped = EASYOCR_LANGS.get(c)
        if mapped and mapped not in codes:
            codes.append(mapped)
    if not codes:
        codes = ["en"]
    reader = easyocr.Reader(codes, gpu=False, verbose=False)
    results = reader.readtext(image_path)
    return "\n".join(r[1] for r in results)


def run_doctr(image_path, lang):
    from doctr.io import DocumentFile
    from doctr.models import ocr_predictor
    model = ocr_predictor(pretrained=True)
    result = model(DocumentFile.from_images(image_path))
    lines = []
    for page in result.pages:
        for block in page.blocks:
            for line in block.lines:
                lines.append(" ".join(w.value for w in line.words))
    return "\n".join(lines)


def main():
    if len(sys.argv) != 4:
        print(json.dumps({"error": "usage: ocr_runner.py ENGINE IMAGE LANG"}))
        return
    engine, image_path, lang = sys.argv[1], sys.argv[2], sys.argv[3]
    runners = {
        "easyocr": run_easyocr,
        "doctr": run_doctr,
    }
    fn = runners.get(engine)
    if fn is None:
        print(json.dumps({"error": "unknown engine: %s" % engine}))
        return
    try:
        text = fn(image_path, lang)
        print(json.dumps({"text": (text or "").strip()}))
    except Exception as exc:
        print(json.dumps({"error": str(exc)}))


if __name__ == "__main__":
    main()
'''


class OcrEngineService(GObject.GObject):
    __gtype_name__ = "OcrEngineService"
    __gsignals__ = {
        "download-progress": (GObject.SIGNAL_RUN_FIRST, None, (str,)),
        "download-done":     (GObject.SIGNAL_RUN_FIRST, None, (bool,)),
        "uninstall-done":    (GObject.SIGNAL_RUN_FIRST, None, (bool,)),
        # engine_key, latest_version — a newer release of an installed
        # engine was found on the package index.
        "update-available":  (GObject.SIGNAL_RUN_FIRST, None, (str, str)),
        # Emitted when a non-Tesseract engine failed and Tesseract was
        # used instead.  Carries the label of the engine that failed.
        "engine-fallback":   (GObject.SIGNAL_RUN_FIRST, None, (str,)),
    }

    def __init__(self):
        super().__init__()
        os.makedirs(_DATA_DIR, exist_ok=True)
        # Cache of installation state so the UI can query cheaply.
        self._installed_cache: dict[str, bool] = {}

    # ------------------------------------------------------------------ #
    # Thread-safe signal emission                                          #
    # ------------------------------------------------------------------ #

    def _emit_on_main(self, signal: str, *args) -> None:
        """Emit a GObject signal on the GLib main loop (never repeats)."""
        def _do():
            self.emit(signal, *args)
            return False
        GLib.idle_add(_do)

    # ------------------------------------------------------------------ #
    # Host helpers                                                         #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _run(argv: list, timeout: int = 30) -> subprocess.CompletedProcess:
        """
        Run *argv* inside the Flatpak sandbox — no host access.

        Everything the OCR engines need (venv, pip, network) lives inside
        the app's own writable data directory and the sandbox's shared
        network, so there's no need to reach out to the host at all.
        """
        return subprocess.run(argv, capture_output=True, text=True, timeout=timeout)

    def _ensure_venv(self) -> bool:
        """Create the OCR venv, inside the sandbox, if it doesn't exist."""
        if os.path.exists(_VENV_PIP):
            return True
        try:
            logger.debug(f"Creating venv at {_VENV_DIR}")
            result = self._run(
                [sys.executable, "-m", "venv", _VENV_DIR], timeout=120
            )
            if result.returncode == 0:
                logger.debug("Venv created OK")
                return True
            logger.debug(f"Venv creation failed: {result.stderr[:300]}")
            return False
        except Exception as exc:
            logger.debug(f"Venv error: {exc}")
            return False

    def _write_runner(self) -> None:
        """Write the runner script to the shared data dir."""
        with open(_RUNNER_PATH, "w", encoding="utf-8") as f:
            f.write(_RUNNER_SOURCE)

    # ------------------------------------------------------------------ #
    # Engine detection                                                     #
    # ------------------------------------------------------------------ #

    def is_installed(self, engine_key: str, refresh: bool = False) -> bool:
        """
        Report whether *engine_key* is usable.

        Non-Tesseract engines live in a venv inside the app's own sandboxed
        data directory, so the check is performed with the venv's own
        Python via ``importlib.metadata``
        (fast — no heavy imports).  Results are cached; pass
        ``refresh=True`` after an install or uninstall.

        Note: this runs a short subprocess, so call it from a worker
        thread when updating the UI.
        """
        if engine_key in BUILTIN_ENGINES:
            return True
        if not refresh and engine_key in self._installed_cache:
            return self._installed_cache[engine_key]

        installed = False
        pip_name = ENGINES[engine_key]["pip_name"]
        if os.path.exists(_VENV_PY):
            try:
                result = self._run(
                    [_VENV_PY, "-c",
                     f"import importlib.metadata as m; m.version({pip_name!r})"],
                    timeout=15,
                )
                installed = result.returncode == 0
            except Exception as exc:
                logger.debug(f"is_installed({engine_key}) check failed: {exc}")

        self._installed_cache[engine_key] = installed
        return installed

    def any_extra_installed(self) -> bool:
        return any(
            self.is_installed(k) for k in ENGINE_KEYS if k not in BUILTIN_ENGINES
        )

    # ------------------------------------------------------------------ #
    # Installation                                                         #
    # ------------------------------------------------------------------ #

    def install(self, engine_key: str) -> None:
        from lens.gobject_worker import GObjectWorker
        GObjectWorker.call(
            self._install_worker,
            (engine_key,),
            lambda ok: self.emit("download-done", bool(ok)),
        )

    def _install_worker(self, engine_key: str) -> bool:
        packages = ENGINES[engine_key]["packages"]
        if not packages:
            return True
        try:
            self._emit_on_main("download-progress", _("Preparing environment…"))
            if not self._ensure_venv():
                self._emit_on_main(
                    "download-progress", _("Failed to create environment")
                )
                return False

            self._emit_on_main("download-progress", _("Starting download…"))
            logger.debug(f"Installing {packages} into venv {_VENV_DIR}")

            cmd = [
                _VENV_PIP, "install",
                "--upgrade",
                "--progress-bar", "off",
            ]
            extra_index = ENGINES[engine_key]["extra_index"]
            if extra_index:
                cmd += ["--extra-index-url", extra_index]
            cmd += packages

            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )

            last_msg = ""
            for line in process.stdout:
                line = line.strip()
                if not line:
                    continue
                logger.debug(f"pip: {line}")
                msg = None
                if line.startswith("Collecting"):
                    pkg = line.replace("Collecting", "").strip().split()[0]
                    msg = _("Fetching {}…").format(pkg)
                elif line.startswith("Downloading"):
                    parts = line.split()
                    name = parts[1].split("-")[0] if len(parts) > 1 else ""
                    size = ""
                    if line.endswith(")") and "(" in line:
                        size = line.rsplit("(", 1)[1].rstrip(")")
                    msg = _("Downloading {} {}").format(name, size).strip()
                elif line.startswith("Installing collected"):
                    msg = _("Installing…")
                if msg and msg != last_msg:
                    self._emit_on_main("download-progress", msg)
                    last_msg = msg

            process.wait()
            ok = process.returncode == 0
            if ok:
                self.is_installed(engine_key, refresh=True)
            return ok

        except Exception as exc:
            logger.debug(f"Install error: {exc}")
            return False

    # ------------------------------------------------------------------ #
    # Uninstallation                                                       #
    # ------------------------------------------------------------------ #

    def uninstall(self, engine_key: str) -> None:
        from lens.gobject_worker import GObjectWorker
        GObjectWorker.call(
            self._uninstall_worker,
            (engine_key,),
            lambda ok: self.emit("uninstall-done", bool(ok)),
        )

    def _uninstall_worker(self, engine_key: str) -> bool:
        pip_name = ENGINES[engine_key]["pip_name"]
        if not pip_name or not os.path.exists(_VENV_PIP):
            return True
        try:
            result = self._run(
                [_VENV_PIP, "uninstall", "-y", pip_name], timeout=300
            )
            ok = result.returncode == 0
            self.is_installed(engine_key, refresh=True)

            # If that was the last extra engine, delete the whole venv to
            # reclaim the shared dependencies (torch and friends).
            still_used = any(
                self.is_installed(k, refresh=True)
                for k in ENGINE_KEYS if k not in BUILTIN_ENGINES
            )
            if ok and not still_used:
                logger.debug("No engines left — removing venv entirely")
                shutil.rmtree(_VENV_DIR, ignore_errors=True)
            return ok
        except Exception as exc:
            logger.debug(f"Uninstall error: {exc}")
            return False

    # ------------------------------------------------------------------ #
    # Update checking                                                      #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _parse_version(v: str) -> tuple:
        """Turn '1.2.3rc1' into (1, 2, 3) for a rough but safe comparison."""
        parts = []
        for chunk in v.split("."):
            digits = ""
            for ch in chunk:
                if ch.isdigit():
                    digits += ch
                else:
                    break
            parts.append(int(digits) if digits else 0)
        return tuple(parts)

    def _is_newer(self, latest: str, current: str) -> bool:
        return self._parse_version(latest) > self._parse_version(current)

    def _get_installed_version(self, engine_key: str) -> str | None:
        pip_name = ENGINES[engine_key]["pip_name"]
        if not pip_name or not os.path.exists(_VENV_PY):
            return None
        try:
            result = self._run(
                [_VENV_PY, "-c",
                 f"import importlib.metadata as m; print(m.version({pip_name!r}))"],
                timeout=15,
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception as exc:
            logger.debug(f"get_installed_version({engine_key}) failed: {exc}")
        return None

    def _get_latest_version(self, engine_key: str) -> str | None:
        pip_name = ENGINES[engine_key]["pip_name"]
        if not pip_name or not os.path.exists(_VENV_PIP):
            return None
        cmd = [_VENV_PIP, "index", "versions", pip_name]
        extra_index = ENGINES[engine_key]["extra_index"]
        if extra_index:
            cmd += ["--extra-index-url", extra_index]
        try:
            result = self._run(cmd, timeout=20)
            # "pip index" is experimental but stable enough to parse:
            # first line looks like "easyocr (1.7.2)"
            for line in result.stdout.splitlines():
                line = line.strip()
                if line.startswith(pip_name) and "(" in line and ")" in line:
                    return line.split("(", 1)[1].split(")", 1)[0].strip()
        except Exception as exc:
            logger.debug(f"get_latest_version({engine_key}) failed: {exc}")
        return None

    def check_updates(self) -> None:
        """
        Check every installed engine for a newer release, skipping the
        built-in ones (Tesseract, Ocrad), which are updated by rebuilding
        the app itself, not by a runtime download.

        Runs entirely on a worker thread; emits ``update-available`` on
        the main loop once per engine that has one. Safe to call even
        when offline — failures are logged and simply produce no signal.
        """
        from lens.gobject_worker import GObjectWorker
        GObjectWorker.call(self._check_updates_worker)

    def _check_updates_worker(self) -> None:
        for engine_key in ENGINE_KEYS:
            if engine_key in BUILTIN_ENGINES:
                continue
            if not self.is_installed(engine_key, refresh=True):
                continue
            current = self._get_installed_version(engine_key)
            latest = self._get_latest_version(engine_key)
            if current and latest and self._is_newer(latest, current):
                logger.debug(f"Update available: {engine_key} {current} -> {latest}")
                self._emit_on_main("update-available", engine_key, latest)

    # ------------------------------------------------------------------ #
    # Extraction                                                           #
    # ------------------------------------------------------------------ #

    def extract(
        self, engine_key: str, source: Union[str, BytesIO], lang: str
    ) -> str | None:
        """
        Extract text using *engine_key*.

        Falls back to Tesseract automatically when a non-Tesseract engine
        errors out, emitting ``engine-fallback`` so the UI can mention it.
        Runs on a worker thread — never call from the main loop.
        """
        if engine_key == "tesseract":
            return self._extract_tesseract(source, lang)
        if engine_key == "ocrad":
            text, errored = self._extract_ocrad(source)
            if errored:
                self._emit_on_main("engine-fallback", ENGINES["ocrad"]["label"])
                return self._extract_tesseract(source, lang)
            return text

        text, errored = self._extract_via_venv(engine_key, source, lang)
        if errored:
            label = ENGINES[engine_key]["label"]
            logger.debug(f"{label} failed — falling back to Tesseract")
            self._emit_on_main("engine-fallback", label)
            return self._extract_tesseract(source, lang)
        return text

    def _extract_ocrad(self, source: Union[str, BytesIO]) -> tuple[str | None, bool]:
        """
        Run the bundled ``ocrad`` binary against *source*.

        Ocrad only understands PNM/PGM/PBM/PPM images reliably across
        versions (PNG support depends on how it was built), so the image
        is always converted to grayscale PNM first via Pillow, which
        every build of ocrad accepts. Ocrad has no language packs — it
        recognizes shapes, not scripts — so it works best on clean,
        printed Latin-script text and the *lang* setting doesn't apply.

        Ocrad's own manual recommends characters be at least 20 pixels
        tall for reliable recognition. Screen-captured text is usually
        well under that (often 12-16px), so the image is upscaled 3x
        before recognition — without this, ocrad silently finds nothing
        on most ordinary screenshots.

        Ocrad also assumes normal polarity — dark text on a light
        background, like a scanned page. Light text on a dark
        background (dark-mode UI, terminals, etc.) reads as a solid
        block to it and produces nothing. The image's average
        brightness is checked and inverted automatically when it looks
        like light-on-dark, so both polarities work without the user
        needing to know or care which one they're capturing.

        Returns ``(text, errored)``, matching ``_extract_via_venv``.
        """
        from PIL import Image, ImageOps
        from PIL.ImageStat import Stat

        self._rewind(source)
        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".pgm", delete=False) as f:
                tmp_path = f.name
            img = Image.open(source).convert("L")

            # Light text on a dark background reads darker on average
            # than dark text on a light background — flip it so ocrad
            # always sees dark-on-light, regardless of source polarity.
            if Stat(img).mean[0] < 128:
                img = ImageOps.invert(img)

            img = img.resize(
                (img.width * 3, img.height * 3), Image.Resampling.LANCZOS
            )
            img.save(tmp_path)

            result = self._run(
                ["ocrad", "--format=utf8", tmp_path], timeout=30
            )
            if result.returncode != 0:
                logger.debug(f"ocrad exited {result.returncode}: {result.stderr[:300]}")
                return None, True
            return (result.stdout or "").strip() or None, False
        except Exception as exc:
            logger.debug(f"ocrad extraction failed: {exc}")
            return None, True
        finally:
            if tmp_path:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass

    @staticmethod
    def _rewind(source) -> None:
        if hasattr(source, "seek"):
            try:
                source.seek(0)
            except Exception:
                pass

    def _extract_tesseract(self, source, lang: str) -> str | None:
        import pytesseract
        from PIL import Image
        self._rewind(source)
        text = pytesseract.image_to_string(
            Image.open(source), lang=lang, config=tessdata_config
        )
        return text.strip() or None

    def _extract_via_venv(
        self, engine_key: str, source: Union[str, BytesIO], lang: str
    ) -> tuple[str | None, bool]:
        """
        Run extraction with the venv's Python.

        Returns ``(text, errored)`` — *errored* is True only for genuine
        failures, not for images that simply contain no text.
        """
        tmp_path = None
        if not isinstance(source, str):
            self._rewind(source)
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
                f.write(source.read())
                tmp_path = f.name
            image_path = tmp_path
        else:
            image_path = source

        try:
            self._write_runner()
            result = self._run(
                [_VENV_PY, _RUNNER_PATH, engine_key, image_path, lang],
                timeout=_EXTRACT_TIMEOUT,
            )
            output = result.stdout.strip().splitlines()
            if output:
                # Engines can print noise on stdout — the JSON is last.
                data = json.loads(output[-1])
                if "error" in data:
                    logger.debug(f"Venv extraction error: {data['error']}")
                    return None, True
                return data.get("text") or None, False
            logger.debug(f"Venv stderr: {result.stderr[:300]}")
            return None, True
        except Exception as exc:
            logger.debug(f"Venv extraction failed: {exc}")
            return None, True
        finally:
            if tmp_path:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass


ocr_engine_service = OcrEngineService()
