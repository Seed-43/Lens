# welcome_page.py
#
# Copyright 2021-2025 Andrey Maksimov
# Copyright 2026-present Seed-43
#
# MIT License - see LICENSE file for details

from gi.repository import Adw, Gdk, Gtk

from lens.config import APP_ID, RESOURCE_PREFIX
from lens.language_manager import language_manager
from lens.types.language_item import LanguageItem
from lens.widgets.language_popover import LanguagePopover


@Gtk.Template(resource_path=f"{RESOURCE_PREFIX}/ui/welcome_page.ui")
class WelcomePage(Adw.NavigationPage):
    __gtype_name__ = "WelcomePage"

    spinner: Adw.Spinner = Gtk.Template.Child()
    welcome: Adw.StatusPage = Gtk.Template.Child()
    lang_combo: Gtk.MenuButton = Gtk.Template.Child()
    language_popover: LanguagePopover = Gtk.Template.Child()

    def __init__(self):
        super().__init__()

        logo = Gdk.Texture.new_from_resource(f"{RESOURCE_PREFIX}/icons/{APP_ID}.svg")
        self.welcome.set_paintable(logo)

        self.language_popover.connect('language-changed', self._on_language_changed)

        self.settings = Gtk.Application.get_default().props.settings
        self.lang_combo.set_label(
            language_manager.get_language(self.settings.get_string("active-language"))
        )

    def do_showing(self) -> None:
        pass

    def _on_language_changed(self, _: LanguagePopover, language: LanguageItem):
        self.lang_combo.set_label(language.title)
        self.settings.set_string("active-language", language.code)
        self.settings.sync()
