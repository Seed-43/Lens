# main.py
#
# Copyright 2021-2025 Andrey Maksimov
# Copyright 2026-present Seed-43
#
# MIT License - see LICENSE file for details

import asyncio
import datetime
import sys
from gettext import gettext as _

from gi.events import GLibEventLoopPolicy
from gi.repository import Adw, Gdk, GdkPixbuf, GLib, GObject, Gio, Gtk, Notify
from loguru import logger

from lens.config import APP_ID, RESOURCE_PREFIX
from lens.language_manager import language_manager
from lens.services.clipboard_service import clipboard_service
from lens.services.screenshot_service import ScreenshotService
from lens.settings import Settings
from lens.window import LensWindow


class LensApplication(Adw.Application):
    __gtype_name__ = 'LensApplication'

    settings: Settings = GObject.Property(type=GObject.TYPE_PYOBJECT)

    def __init__(self, version=None):
        super().__init__(application_id=APP_ID,
                         flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE)
        self.backend = None
        self.version = version

        self.settings = Settings.new()

        self.add_main_option(
            'extract_to_clipboard',
            ord('e'),
            GLib.OptionFlags.NONE,
            GLib.OptionArg.NONE,
            _("Extract directly into the clipboard"),
            None
        )

        language_manager.init_tessdata()
        Notify.init("Lens")

    def do_startup(self, *args, **kwargs):
        Adw.Application.do_startup(self)

        self.backend = ScreenshotService()
        self.backend.connect('decoded', LensApplication.on_decoded)

        action = Gio.SimpleAction.new("show_uri", GLib.VariantType.new('s'))
        action.connect("activate", self.on_show_uri)
        self.add_action(action)

        # Note: get_screenshot and copy_to_clipboard use different shortcuts
        self.create_action('get_screenshot', self.get_screenshot, ['<primary>g'])
        self.create_action('get_screenshot_and_copy', self.get_screenshot_and_copy, ['<primary><shift>g'])
        self.create_action('copy_to_clipboard', self.on_copy_to_clipboard, ['<primary>c'])
        self.create_action('open_image', self.open_image, ['<primary>o'])
        self.create_action('paste_from_clipboard', self.on_paste_from_clipboard, ['<primary>v'])
        self.create_action('listen', self.on_listen, ['<primary>l'])
        self.create_action('listen_cancel', self.on_listen_cancel, ['<primary><ctrl>l'])
        self.create_action('shortcuts', self.on_shortcuts, ['<primary>question'])
        self.create_action('quit', lambda *_: self.quit(), ['<primary>q', '<primary>w'])
        self.create_action('about', self.on_about)
        self.create_action('preferences', self.on_preferences, ['<primary>comma'])
        self.create_action('github_star', self.on_github_star)

        self.settings.connect("changed", self.on_settings_changed)

    def do_activate(self):
        win = self.props.active_window
        if not win:
            win = LensWindow(application=self)
        win.present()

    def do_command_line(self, command_line):
        options = command_line.get_options_dict()
        options = options.end().unpack()

        if "extract_to_clipboard" in options:
            self.backend.capture(self.settings.get_string("active-language"), True)
            return 1

        self.activate()
        return 0

    def on_settings_changed(self, settings, key):
        logger.debug('SETTINGS: {} changed', key)

    def on_preferences(self, _action, _param) -> None:
        self.get_active_window().show_preferences()

    def on_github_star(self, _action, _param) -> None:
        launcher = Gtk.UriLauncher()
        launcher.set_uri('https://github.com/Seed-43/Lens')
        launcher.launch(callback=self._on_github_star)

    def on_about(self, _action, _param):
        about_window = Adw.AboutDialog(
            application_name="Lens",
            application_icon=APP_ID,
            version=self.version,
            copyright=f'© {datetime.date.today().year} Seed-43',
            website="https://github.com/Seed-43/Lens",
            issue_url="https://github.com/Seed-43/Lens/issues/new",
            license_type=Gtk.License.MIT_X11,
            developer_name="Seed-43",
            developers=["Seed-43"],
        )
        about_window.present(self.props.active_window)

    def on_shortcuts(self, _action, _param):
        builder = Gtk.Builder()
        builder.add_from_resource(f"{RESOURCE_PREFIX}/ui/shortcuts.ui")
        builder.get_object("shortcuts").set_transient_for(self.get_active_window())
        builder.get_object("shortcuts").present()

    def on_copy_to_clipboard(self, _action, _param) -> None:
        self.get_active_window().on_copy_to_clipboard(self)

    def on_show_uri(self, _action, param) -> None:
        Gtk.show_uri(None, param.get_string(), Gdk.CURRENT_TIME)

    def get_screenshot(self, _action, _param) -> None:
        self.get_active_window().get_screenshot()

    def get_screenshot_and_copy(self, _action, _param) -> None:
        self.get_active_window().get_screenshot(copy=True)

    def open_image(self, _action, _param) -> None:
        self.get_active_window().open_image()

    def on_paste_from_clipboard(self, _action, _param) -> None:
        self.get_active_window().on_paste_from_clipboard(self)

    @staticmethod
    def on_decoded(_sender, text: str, copy: bool) -> None:
        icon = GdkPixbuf.Pixbuf.new_from_resource_at_scale(
            f"{RESOURCE_PREFIX}/icons/io.github.seed43.lens.svg",
            128, 128, True
        )

        if not text:
            notification = Notify.Notification.new(
                summary='Lens',
                body=_("No text found. Try to grab another region.")
            )
            notification.set_icon_from_pixbuf(icon)
            notification.show()
            return

        if copy:
            clipboard_service.set(text)
            notification = Notify.Notification.new(
                summary='Lens',
                body=_("Text extracted. You can paste it with Ctrl+V")
            )
            notification.set_icon_from_pixbuf(icon)
            notification.show()
        else:
            logger.debug(f'{text}\n')

    def on_listen(self, _sender, _event):
        self.get_active_window().on_listen()

    def on_listen_cancel(self, _sender, _event):
        self.get_active_window().on_listen_cancel()

    def create_action(self, name, callback, shortcuts=None):
        """Add an application action."""
        action = Gio.SimpleAction.new(name, None)
        action.connect("activate", callback)
        self.add_action(action)
        if shortcuts:
            self.set_accels_for_action(f"app.{name}", shortcuts)

    def _on_github_star(self, _, result):
        pass


def main(version):
    asyncio.set_event_loop_policy(GLibEventLoopPolicy())
    app = LensApplication(version)
    return app.run(sys.argv)
