# screenshot_service.py
#
# Copyright (C) 2026-present Seed-43
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.

import os
from gettext import gettext as _
from io import BytesIO
from typing import Union

from PIL import Image
from gi.repository import Gio, GLib, GObject, Xdp
from loguru import logger
try:
    from pyzbar.pyzbar import decode as decode_qr
    QR_AVAILABLE = True
except ImportError:
    # pyzbar isn't available on every distribution packaging Lens (it
    # isn't currently a Fedora package, for instance). QR-code
    # detection just gets skipped rather than the whole app failing
    # to start over one optional feature.
    decode_qr = None
    QR_AVAILABLE = False

from lens.gobject_worker import GObjectWorker
from lens.services.ocr_engine_service import ocr_engine_service


class ScreenshotService(GObject.GObject):
    """
    Captures screenshots via the XDG Desktop Portal and extracts text
    or decodes QR codes from images.

    All heavy work (QR decoding, OCR) runs on a worker thread; signals
    are always delivered on the GLib main loop.

    Signals
    -------
    text-ready(str, bool)
        Emitted when extraction succeeds.  The first argument is the
        extracted text; the second indicates whether the caller requested
        the result be copied to the clipboard.
    error(str)
        Emitted when any step fails, carrying a human-readable message.
    """

    __gtype_name__ = "ScreenshotService"

    __gsignals__ = {
        "text-ready": (GObject.SIGNAL_RUN_FIRST, None, (str, bool)),
        "error":      (GObject.SIGNAL_RUN_LAST,  None, (str,)),
    }

    def __init__(self):
        super().__init__()
        self._portal = Xdp.Portal()

    # ------------------------------------------------------------------
    # Thread-safe signal emission
    # ------------------------------------------------------------------

    def _emit_on_main(self, signal: str, *args) -> None:
        def _do():
            self.emit(signal, *args)
            return False
        GLib.idle_add(_do)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def capture(
        self,
        lang: str,
        copy: bool = False,
        engine: str = "tesseract",
        delete_after: bool = True,
    ) -> None:
        """
        Open the interactive XDG screenshot selector and extract text
        from the region the user selects.

        Parameters
        ----------
        lang:
            Tesseract language code(s), e.g. ``"eng"`` or ``"eng+fra"``.
        copy:
            When *True* the caller wants the result written to the
            clipboard in addition to being emitted via ``text-ready``.
        engine:
            OCR engine key, e.g. ``"tesseract"`` or ``"easyocr"``.
        delete_after:
            When *True* the screenshot file is deleted once processed.
        """
        cancellable = Gio.Cancellable.new()
        self._portal.take_screenshot(
            None,
            Xdp.ScreenshotFlags.INTERACTIVE,
            cancellable,
            self._on_screenshot_taken,
            (lang, copy, engine, delete_after),
        )

    def decode_image(
        self,
        lang: str,
        source: Union[str, BytesIO],
        copy: bool = False,
        remove_source: bool = False,
        engine: str = "tesseract",
    ) -> None:
        """
        Extract text or decode a QR code from an existing image.

        Safe to call from any thread; the work itself happens here, so
        callers should invoke this via :class:`GObjectWorker`.

        Parameters
        ----------
        lang:
            Tesseract language code(s).
        source:
            Either a file-system path (``str``) or an in-memory
            ``BytesIO`` buffer containing image data.
        copy:
            Passed through to the ``text-ready`` signal.
        remove_source:
            When *True* and *source* is a file path, the file is
            deleted after processing.  Ignored for ``BytesIO`` sources.
        engine:
            OCR engine key.
        """
        if not isinstance(source, str):
            remove_source = False

        logger.debug(f"Decoding image — lang={lang}, engine={engine}")

        try:
            text = self._extract(source, lang, engine)
        except Exception as exc:
            logger.debug(f"Extraction error: {exc}")
            self._emit_on_main("error", _("Failed to process image."))
            return
        finally:
            if remove_source and isinstance(source, str):
                self._delete_file(source)

        if text:
            logger.debug("Extraction successful")
            self._emit_on_main("text-ready", text, copy)
        else:
            self._emit_on_main(
                "error", _("No text found. Try grabbing another region.")
            )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _on_screenshot_taken(
        self, _source: GObject.GObject, result: Gio.Task, user_data: tuple
    ) -> None:
        """Portal callback — converts the URI and starts extraction."""
        if result.had_error():
            self.emit("error", _("Could not take a screenshot."))
            return

        lang, copy, engine, delete_after = user_data

        try:
            uri = self._portal.take_screenshot_finish(result)
            path = GLib.Uri.unescape_string(uri.removeprefix("file://"))
            # OCR can be slow — keep it off the main loop.
            GObjectWorker.call(
                self.decode_image,
                (lang, path, copy, delete_after, engine),
            )
        except Exception as exc:
            logger.debug(f"Screenshot finish error: {exc}")
            self.emit("error", _("Could not take a screenshot."))

    def _extract(
        self, source: Union[str, BytesIO], lang: str, engine: str = "tesseract"
    ) -> str | None:
        """Try QR decoding first, then use the selected OCR engine."""
        if hasattr(source, "seek"):
            source.seek(0)
        if QR_AVAILABLE:
            qr_results = decode_qr(Image.open(source))
            if qr_results:
                return qr_results[0].data.decode("utf-8")
            # The QR pass consumed the stream — the engine service
            # rewinds it again before reading.
        return ocr_engine_service.extract(engine, source, lang)

    def _delete_file(self, path: str) -> None:
        """Silently remove a temporary screenshot file."""
        try:
            os.unlink(path)
            logger.debug(f"Deleted temp file: {path}")
        except Exception as exc:
            logger.debug(f"Could not delete {path}: {exc}")
