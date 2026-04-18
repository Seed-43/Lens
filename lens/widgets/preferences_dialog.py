# preferences_dialog.py
#
# Copyright 2021-2025 Andrey Maksimov
# Copyright 2026-present Seed-43
#
# MIT License - see LICENSE file for details

from gi.repository import Adw, Gtk

from lens.config import RESOURCE_PREFIX
from lens.widgets.preferences_general_page import PreferencesGeneralPage
from lens.widgets.preferences_languages_page import PreferencesLanguagesPage


@Gtk.Template(resource_path=f'{RESOURCE_PREFIX}/ui/preferences_dialog.ui')
class PreferencesDialog(Adw.PreferencesDialog):
    __gtype_name__ = 'PreferencesDialog'

    general_page: PreferencesGeneralPage = Gtk.Template.Child()
    languages_page: PreferencesLanguagesPage = Gtk.Template.Child()

    def __init__(self):
        super().__init__()
