# language_manager.py
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
import pathlib
from gettext import gettext as _
from shutil import copyfile
from urllib import request

from gi.repository import GObject
from loguru import logger

from lens.config import tessdata_dir, tessdata_url, tessdata_best_url
from lens.gobject_worker import GObjectWorker
from lens.types.download_state import DownloadState
from lens.types.language_item import LanguageItem


# All Tesseract language codes and their human-readable names.
# Sorted alphabetically by display name at runtime.
_LANGUAGES: dict[str, str] = {
    "afr":      _("Afrikaans"),
    "amh":      _("Amharic"),
    "ara":      _("Arabic"),
    "asm":      _("Assamese"),
    "aze":      _("Azerbaijani"),
    "aze_cyrl": _("Azerbaijani — Cyrillic"),
    "bel":      _("Belarusian"),
    "ben":      _("Bengali"),
    "bod":      _("Tibetan"),
    "bos":      _("Bosnian"),
    "bre":      _("Breton"),
    "bul":      _("Bulgarian"),
    "cat":      _("Catalan"),
    "ceb":      _("Cebuano"),
    "ces":      _("Czech"),
    "chi_sim":  _("Chinese — Simplified"),
    "chi_tra":  _("Chinese — Traditional"),
    "chr":      _("Cherokee"),
    "cos":      _("Corsican"),
    "cym":      _("Welsh"),
    "dan":      _("Danish"),
    "deu":      _("German"),
    "dzo":      _("Dzongkha"),
    "ell":      _("Greek"),
    "eng":      _("English"),
    "enm":      _("English, Middle (1100-1500)"),
    "epo":      _("Esperanto"),
    "equ":      _("Math / equation detection"),
    "est":      _("Estonian"),
    "eus":      _("Basque"),
    "fao":      _("Faroese"),
    "fas":      _("Persian"),
    "fil":      _("Filipino"),
    "fin":      _("Finnish"),
    "fra":      _("French"),
    "frk":      _("German — Fraktur"),
    "frm":      _("French, Middle (ca. 1400–1600)"),
    "fry":      _("Western Frisian"),
    "gla":      _("Scottish Gaelic"),
    "gle":      _("Irish"),
    "glg":      _("Galician"),
    "grc":      _("Greek, Ancient"),
    "guj":      _("Gujarati"),
    "hat":      _("Haitian Creole"),
    "heb":      _("Hebrew"),
    "hin":      _("Hindi"),
    "hrv":      _("Croatian"),
    "hun":      _("Hungarian"),
    "hye":      _("Armenian"),
    "iku":      _("Inuktitut"),
    "ind":      _("Indonesian"),
    "isl":      _("Icelandic"),
    "ita":      _("Italian"),
    "ita_old":  _("Italian — Old"),
    "jav":      _("Javanese"),
    "jpn":      _("Japanese"),
    "jpn_vert": _("Japanese — Vertical"),
    "kan":      _("Kannada"),
    "kat":      _("Georgian"),
    "kat_old":  _("Georgian — Old"),
    "kaz":      _("Kazakh"),
    "khm":      _("Khmer"),
    "kir":      _("Kyrgyz"),
    "kmr":      _("Kurdish — Latin"),
    "kor":      _("Korean"),
    "kor_vert": _("Korean — Vertical"),
    "lao":      _("Lao"),
    "lat":      _("Latin"),
    "lav":      _("Latvian"),
    "lit":      _("Lithuanian"),
    "ltz":      _("Luxembourgish"),
    "mal":      _("Malayalam"),
    "mar":      _("Marathi"),
    "mkd":      _("Macedonian"),
    "mlt":      _("Maltese"),
    "mon":      _("Mongolian"),
    "mri":      _("Māori"),
    "msa":      _("Malay"),
    "mya":      _("Burmese"),
    "nep":      _("Nepali"),
    "nld":      _("Dutch"),
    "nor":      _("Norwegian"),
    "oci":      _("Occitan"),
    "ori":      _("Odia"),
    "osd":      _("Orientation & script detection"),
    "pan":      _("Punjabi"),
    "pol":      _("Polish"),
    "por":      _("Portuguese"),
    "pus":      _("Pashto"),
    "que":      _("Quechua"),
    "ron":      _("Romanian"),
    "rus":      _("Russian"),
    "san":      _("Sanskrit"),
    "sin":      _("Sinhala"),
    "slk":      _("Slovak"),
    "slv":      _("Slovenian"),
    "snd":      _("Sindhi"),
    "spa":      _("Spanish"),
    "spa_old":  _("Spanish — Old"),
    "sqi":      _("Albanian"),
    "srp":      _("Serbian"),
    "srp_latn": _("Serbian — Latin"),
    "sun":      _("Sundanese"),
    "swa":      _("Swahili"),
    "swe":      _("Swedish"),
    "syr":      _("Syriac"),
    "tam":      _("Tamil"),
    "tat":      _("Tatar"),
    "tel":      _("Telugu"),
    "tgk":      _("Tajik"),
    "tha":      _("Thai"),
    "tir":      _("Tigrinya"),
    "ton":      _("Tongan"),
    "tur":      _("Turkish"),
    "uig":      _("Uyghur"),
    "ukr":      _("Ukrainian"),
    "urd":      _("Urdu"),
    "uzb":      _("Uzbek"),
    "uzb_cyrl": _("Uzbek — Cyrillic"),
    "vie":      _("Vietnamese"),
    "yid":      _("Yiddish"),
    "yor":      _("Yoruba"),
}


class LanguageManager(GObject.GObject):
    """
    Manages Tesseract language packs — tracking which are installed,
    downloading new ones, and removing existing ones.

    Signals
    -------
    added(str)        — a download has been queued for *code*
    downloading(str, int) — download progress (code, percent 0-100)
    downloaded(str)   — a language pack finished downloading
    removed(str)      — a language pack was deleted
    """

    __gtype_name__ = "LanguageManager"

    __gsignals__ = {
        "added":       (GObject.SIGNAL_RUN_FIRST, None, (str,)),
        "downloading": (GObject.SIGNAL_RUN_FIRST, None, (str, int)),
        "downloaded":  (GObject.SIGNAL_RUN_FIRST, None, (str,)),
        "removed":     (GObject.SIGNAL_RUN_FIRST, None, (str,)),
    }

    def __init__(self):
        super().__init__()
        self._active_language: LanguageItem = LanguageItem(code="eng", title=_("English"))
        self.loading_languages: dict[str, DownloadState] = {}
        self._downloaded_cache: list[str] = []
        self._cache_dirty = True

    # ------------------------------------------------------------------ #
    # Setup                                                                #
    # ------------------------------------------------------------------ #

    @staticmethod
    def init_tessdata() -> None:
        """
        Ensure the tessdata directory exists and that the bundled English
        model is in place.
        """
        os.makedirs(tessdata_dir, exist_ok=True)
        dest   = os.path.join(tessdata_dir, "eng.traineddata")
        source = pathlib.Path("/app/share/appdata/eng.traineddata")
        if not os.path.exists(dest):
            copyfile(source, dest)

    # ------------------------------------------------------------------ #
    # Active language property                                             #
    # ------------------------------------------------------------------ #

    @GObject.Property(type=GObject.TYPE_PYOBJECT)
    def active_language(self) -> LanguageItem:
        return self._active_language

    @active_language.setter
    def active_language(self, language: LanguageItem) -> None:
        logger.debug(f"Active language set to {language}")
        self._active_language = language
        self.notify("active_language")

    # ------------------------------------------------------------------ #
    # Language catalogue queries                                           #
    # ------------------------------------------------------------------ #

    def get_available_codes(self) -> list[str]:
        """All supported language codes, sorted by display name."""
        return sorted(_LANGUAGES.keys(), key=lambda c: _LANGUAGES.get(c, c))

    def get_language(self, code: str) -> str | None:
        """Human-readable name for *code*, or ``None`` if unknown."""
        return _LANGUAGES.get(code)

    def get_language_code(self, name: str) -> str | None:
        """Reverse lookup — return the code for a display *name*."""
        for code, title in _LANGUAGES.items():
            if title == name:
                return code
        return None

    def get_language_item(self, code: str) -> LanguageItem:
        return LanguageItem(code=code, title=self.get_language(code))

    # ------------------------------------------------------------------ #
    # Downloaded language queries                                          #
    # ------------------------------------------------------------------ #

    def get_downloaded_codes(self, force: bool = False) -> list[str]:
        """Codes of language packs present in tessdata_dir."""
        if self._cache_dirty or force:
            self._downloaded_cache = [
                os.path.splitext(f)[0]
                for f in os.listdir(tessdata_dir)
                if f.endswith(".traineddata")
            ]
            self._cache_dirty = False
            logger.debug(f"Downloaded codes: {self._downloaded_cache}")
        return sorted(self._downloaded_cache, key=lambda c: _LANGUAGES.get(c, c))

    def get_downloaded_languages(self, force: bool = False) -> list[str]:
        """Display names of installed language packs, sorted alphabetically."""
        return sorted(
            _LANGUAGES[c]
            for c in self.get_downloaded_codes(force)
            if c in _LANGUAGES
        )

    # ------------------------------------------------------------------ #
    # Download                                                             #
    # ------------------------------------------------------------------ #

    def download(self, code: str) -> None:
        """Queue a background download of the language pack for *code*."""
        self.emit("added", code)
        self.loading_languages[code] = DownloadState()
        self.emit("downloading", code, 0)
        GObjectWorker.call(self._download_worker, (code,), self._on_download_done)

    def _download_worker(self, code: str) -> str | None:
        """Run in a background thread — download the traineddata file."""
        tessfile = f"{code}.traineddata"
        dest     = os.path.join(tessdata_dir, tessfile)

        def _progress(block, block_size, total):
            if total > 0:
                pct = min(100, int(block * block_size * 100 / total))
                self.emit("downloading", code, pct)

        try:
            request.urlretrieve(tessdata_best_url + tessfile, dest, _progress)
            return code
        except Exception as exc:
            logger.debug(f"{code} not in tessdata_best: {exc}")

        try:
            request.urlretrieve(tessdata_url + tessfile, dest, _progress)
            return code
        except Exception as exc:
            logger.debug(f"{code} not in tessdata either: {exc}")
            return None

    def _on_download_done(self, code: str | None) -> None:
        self._cache_dirty = True
        if code:
            self.loading_languages.pop(code, None)
        self.emit("downloaded", code or "")

    # ------------------------------------------------------------------ #
    # Remove                                                               #
    # ------------------------------------------------------------------ #

    def remove_language(self, code: str) -> None:
        """Delete the installed language pack for *code*."""
        path = os.path.join(tessdata_dir, f"{code}.traineddata")
        try:
            os.remove(path)
            logger.debug(f"Removed language pack: {code}")
        except OSError as exc:
            logger.debug(f"Could not remove {code}: {exc}")
        self._cache_dirty = True
        self.emit("removed", code)


# Module-level singleton.
language_manager = LanguageManager()
