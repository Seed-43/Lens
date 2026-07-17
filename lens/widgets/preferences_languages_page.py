# preferences_languages_page.py
#
# Copyright (C) 2026-present Seed-43
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

from gettext import gettext as _

from gi.repository import Adw, Gio, Gtk

from lens.config import RESOURCE_PREFIX
from lens.language_manager import language_manager
from lens.types.language_item import LanguageItem
from lens.widgets.language_row import LanguageRow


@Gtk.Template(resource_path=f"{RESOURCE_PREFIX}/ui/preferences_languages.ui")
class PreferencesLanguagesPage(Adw.PreferencesPage):
    """
    Preferences page for managing installed Tesseract language packs.
    Supports search, download and removal of packs.
    """

    __gtype_name__ = "PreferencesLanguagesPage"

    banner:                Adw.Banner        = Gtk.Template.Child()
    views:                 Gtk.Stack         = Gtk.Template.Child()
    search_bar:            Gtk.SearchBar     = Gtk.Template.Child()
    language_search_entry: Gtk.SearchEntry   = Gtk.Template.Child()
    list_view:             Gtk.ListView      = Gtk.Template.Child()
    model:                 Gtk.FilterListModel = Gtk.Template.Child()
    list_store:            Gio.ListStore     = Gtk.Template.Child()
    revealer:              Gtk.Revealer      = Gtk.Template.Child()

    def __init__(self):
        super().__init__()
        self.settings = Gtk.Application.get_default().props.settings
        self._load_all_languages()

        language_manager.connect("added",      self._on_language_changed)
        language_manager.connect("downloaded", self._on_language_changed)
        language_manager.connect("removed",    self._on_language_changed)

        self.language_search_entry.connect("search-changed", self._on_search_changed)
        self.language_search_entry.connect("stop-search",    self._on_search_stopped)
        self.search_bar.connect("notify::search-mode-enabled", self._on_search_mode_changed)

        self._apply_filter()
        self._check_connection()

    # ------------------------------------------------------------------ #
    # Template callbacks                                                   #
    # ------------------------------------------------------------------ #

    @Gtk.Template.Callback()
    def _on_banner_clicked(self, _) -> None:
        self._check_connection()

    @Gtk.Template.Callback()
    def _on_item_setup(self, _factory: Gtk.SignalListItemFactory, item: Gtk.ListItem) -> None:
        item.set_child(LanguageRow())

    @Gtk.Template.Callback()
    def _on_item_bind(self, _factory: Gtk.SignalListItemFactory, list_item: Gtk.ListItem) -> None:
        row: LanguageRow     = list_item.get_child()
        lang: LanguageItem   = list_item.get_item()
        row.item = lang

    @Gtk.Template.Callback()
    def _on_add_language(self, _sender: Gtk.Widget) -> None:
        if self.search_bar.get_search_mode():
            self._apply_filter()
            self.search_bar.set_search_mode(False)
        else:
            self._show_all()
            self.search_bar.set_search_mode(True)
            self.language_search_entry.grab_focus()

    # ------------------------------------------------------------------ #
    # Search                                                               #
    # ------------------------------------------------------------------ #

    def _on_search_changed(self, entry: Gtk.SearchEntry) -> None:
        self._apply_filter(entry.get_text() or None)

    def _on_search_stopped(self, entry: Gtk.SearchEntry) -> None:
        entry.set_text("")
        self.search_bar.set_search_mode(False)
        self.revealer.set_reveal_child(True)
        self._apply_filter()

    def _on_search_mode_changed(self, _bar, _param) -> None:
        if not self.search_bar.get_search_mode():
            self._apply_filter()

    def _on_language_changed(self, _sender, _code: str | None = None) -> None:
        if not self.search_bar.get_search_mode():
            self._apply_filter()

    # ------------------------------------------------------------------ #
    # Helpers                                                              #
    # ------------------------------------------------------------------ #

    def _load_all_languages(self) -> None:
        self.list_store.remove_all()
        for code in language_manager.get_available_codes():
            self.list_store.append(language_manager.get_language_item(code))

    def _apply_filter(self, query: str | None = None) -> None:
        """Show only installed languages, optionally filtered by *query*."""
        downloaded = set(language_manager.get_downloaded_codes())

        def _filter(item: LanguageItem, q: str | None) -> bool:
            if q:
                return q.lower() in item.title.lower()
            return item.code in downloaded

        self.model.set_filter(Gtk.CustomFilter.new(_filter, query))
        self._toggle_empty(not self.model.get_n_items())

    def _show_all(self) -> None:
        """Remove filter so all languages are visible for browsing."""
        self.model.set_filter(None)

    def _toggle_empty(self, is_empty: bool) -> None:
        name = "empty_state" if is_empty else "languages_state"
        self.views.set_visible_child_name(name)

    def _check_connection(self) -> None:
        monitor = Gio.NetworkMonitor.get_default()
        host    = Gio.NetworkAddress.new("raw.githubusercontent.com", 443)

        if not monitor.can_reach(host):
            self.banner.set_title(_("Models location unreachable. Check your internet connection."))
            self.banner.set_revealed(True)
        elif monitor.get_network_metered():
            self.banner.set_title(_("Metered connection — be careful downloading language packs."))
            self.banner.set_revealed(True)
        else:
            self.banner.set_revealed(False)
