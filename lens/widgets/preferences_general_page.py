# preferences_general_page.py
#
# Copyright 2021-2025 Andrey Maksimov
# Copyright 2026-present Seed-43
#
# MIT License - see LICENSE file for details

from gi.repository import Adw, Gio, Gtk
from loguru import logger

from lens.config import RESOURCE_PREFIX
from lens.language_manager import language_manager
from lens.settings import Settings


@Gtk.Template(resource_path=f'{RESOURCE_PREFIX}/ui/preferences_general.ui')
class PreferencesGeneralPage(Adw.PreferencesPage):
    __gtype_name__ = 'PreferencesGeneralPage'

    extra_language_combo: Adw.ComboRow = Gtk.Template.Child()
    autocopy_switch: Adw.SwitchRow = Gtk.Template.Child()
    autolinks_switch: Adw.SwitchRow = Gtk.Template.Child()

    def __init__(self):
        super().__init__()

        self.settings: Settings = Gtk.Application.get_default().props.settings

        self.settings.bind('autocopy', self.autocopy_switch, 'active', Gio.SettingsBindFlags.DEFAULT)
        self.settings.bind('autolinks', self.autolinks_switch, 'active', Gio.SettingsBindFlags.DEFAULT)

        downloaded_langs = language_manager.get_downloaded_languages()
        self.extra_language_combo.set_model(Gtk.StringList.new(downloaded_langs))
        extra_lang = language_manager.get_language(self.settings.get_string('extra-language'))
        if extra_lang in downloaded_langs:
            self.extra_language_combo.set_selected(downloaded_langs.index(extra_lang))
        self.extra_language_combo.connect('notify::selected-item', self._on_extra_language_changed)

    def do_show(self, *args, **kwargs):
        pass

    def _on_extra_language_changed(self, combo_row: Adw.ComboRow, _param):
        lang_name = combo_row.get_selected_item().get_string()
        lang_code = language_manager.get_language_code(lang_name)
        logger.debug(f'Extra language: {lang_name}:{lang_code}')
        self.settings.set_string('extra-language', lang_code)
