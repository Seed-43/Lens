# main.py
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

import asyncio
import sys
from gettext import gettext as _

from gi.events import GLibEventLoopPolicy
from gi.repository import Adw, Gdk, GLib, GObject, Gio, Gtk
from loguru import logger

from lens.config import APP_ID, RESOURCE_PREFIX
from lens.language_manager import language_manager
from lens.services.clipboard_service import clipboard_service
from lens.settings import Settings
from lens.window import LensWindow


class LensApplication(Adw.Application):
    __gtype_name__ = "LensApplication"

    settings: Settings = GObject.Property(type=GObject.TYPE_PYOBJECT)

    def __init__(self, version=None):
        super().__init__(
            application_id=APP_ID,
            flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE,
        )
        self.version = version
        self.settings = Settings.new()

        # Command-line option: -e / --extract-to-clipboard
        self.add_main_option(
            "extract_to_clipboard",
            ord("e"),
            GLib.OptionFlags.NONE,
            GLib.OptionArg.NONE,
            _("Extract text directly to clipboard without opening the window"),
            None,
        )

        language_manager.init_tessdata()

    # ------------------------------------------------------------------
    # Application lifecycle
    # ------------------------------------------------------------------

    def do_startup(self, *args, **kwargs):
        Adw.Application.do_startup(self)

        # URI launcher action (used by QR-code toasts)
        action = Gio.SimpleAction.new("show_uri", GLib.VariantType.new("s"))
        action.connect("activate", self._on_show_uri)
        self.add_action(action)

        # Keyboard shortcuts
        self._register_actions()
        self.settings.connect("changed", self._on_settings_changed)

    def do_activate(self):
        win = self._get_or_create_window()
        win.present()

    def do_command_line(self, command_line):
        options = command_line.get_options_dict().end().unpack()

        if "extract_to_clipboard" in options:
            # Silent extract — open window if needed but grab immediately
            win = self._get_or_create_window()
            win.get_screenshot(copy=True)
            return 0

        self.activate()
        return 0

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _register_actions(self):
        self._action("get_screenshot",          self._on_get_screenshot,          ["<primary>g"])
        self._action("get_screenshot_and_copy", self._on_get_screenshot_and_copy, ["<primary><shift>g"])
        self._action("copy_to_clipboard",       self._on_copy_to_clipboard,       ["<primary>c"])
        self._action("open_image",              self._on_open_image,              ["<primary>o"])
        self._action("paste_from_clipboard",    self._on_paste_from_clipboard,    ["<primary>v"])
        self._action("shortcuts",               self._on_shortcuts,               ["<primary>question"])
        self._action("clear_text",              self._on_clear_text,              [])
        self._action("quit",                    lambda *_: self.quit(),           ["<primary>q"])

    def _action(self, name: str, callback, accels: list | None = None):
        action = Gio.SimpleAction.new(name, None)
        action.connect("activate", callback)
        self.add_action(action)
        if accels:
            self.set_accels_for_action(f"app.{name}", accels)

    # ------------------------------------------------------------------
    # Action handlers
    # ------------------------------------------------------------------

    def _on_get_screenshot(self, _action, _param) -> None:
        self._get_or_create_window().get_screenshot()

    def _on_get_screenshot_and_copy(self, _action, _param) -> None:
        self._get_or_create_window().get_screenshot(copy=True)

    def _on_copy_to_clipboard(self, _action, _param) -> None:
        self._get_or_create_window().on_copy_to_clipboard(self)

    def _on_open_image(self, _action, _param) -> None:
        self._get_or_create_window().open_image()

    def _on_paste_from_clipboard(self, _action, _param) -> None:
        self._get_or_create_window().on_paste_from_clipboard(self)

    def _on_show_uri(self, _action, param) -> None:
        Gtk.show_uri(None, param.get_string(), Gdk.CURRENT_TIME)

    def _on_clear_text(self, _action, _param) -> None:
        win = self._get_or_create_window()
        win.clear_text()

    def _on_shortcuts(self, _action, _param) -> None:
        builder = Gtk.Builder()
        builder.add_from_resource(f"{RESOURCE_PREFIX}/ui/shortcuts.ui")
        win = builder.get_object("shortcuts")
        win.set_transient_for(self.get_active_window())
        win.present()

    def _on_settings_changed(self, _settings, key: str) -> None:
        logger.debug(f"Setting changed: {key}")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get_or_create_window(self) -> LensWindow:
        """Return the existing LensWindow or create a new one."""
        for win in self.get_windows():
            if isinstance(win, LensWindow):
                return win
        return LensWindow(application=self, version=self.version)


def main(version):
    asyncio.set_event_loop_policy(GLibEventLoopPolicy())
    app = LensApplication(version)
    return app.run(sys.argv)
