# clipboard_service.py
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

from gettext import gettext as _

from gi.repository import Gdk, Gio, GObject
from loguru import logger


class ClipboardService(GObject.GObject):
    """
    Reads and writes the system clipboard.

    Signals
    -------
    image-ready(Gdk.Texture)
        Emitted when an image has been successfully read from the clipboard.
    error(str)
        Emitted when a clipboard operation fails, carrying a human-readable
        message suitable for display in a toast.
    """

    __gtype_name__ = "ClipboardService"

    __gsignals__ = {
        "image-ready": (GObject.SIGNAL_RUN_FIRST, None, (Gdk.Texture,)),
        "error":       (GObject.SIGNAL_RUN_FIRST, None, (str,)),
    }

    def __init__(self):
        super().__init__()
        self._clipboard = Gdk.Display.get_default().get_clipboard()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set(self, text: str) -> None:
        """Write *text* to the system clipboard."""
        self._clipboard.set(text)
        logger.debug("Clipboard updated")

    def read_image(self) -> None:
        """
        Asynchronously read an image from the clipboard.

        On success, ``image-ready`` is emitted with the texture.
        On failure, ``error`` is emitted with a user-facing message.
        """
        self._clipboard.read_texture_async(
            cancellable=None,
            callback=self._on_texture_ready,
        )

    # ------------------------------------------------------------------
    # Private callbacks
    # ------------------------------------------------------------------

    def _on_texture_ready(
        self, _source: GObject.GObject, result: Gio.AsyncResult
    ) -> None:
        try:
            texture = self._clipboard.read_texture_finish(result)
            if texture is None:
                raise ValueError("clipboard contained no image data")
            self.emit("image-ready", texture)
        except Exception as exc:
            logger.debug(f"Clipboard read failed: {exc}")
            self.emit("error", _("No image found in clipboard"))


# Module-level singleton — import and use directly.
clipboard_service = ClipboardService()
