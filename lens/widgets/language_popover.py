# language_popover.py
#
# Copyright (C) 2026-present Seed-43
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

from gi.repository import Gio, GObject, Gtk
from loguru import logger

from lens.config import RESOURCE_PREFIX
from lens.language_manager import language_manager
from lens.types.language_item import LanguageItem
from lens.widgets.language_popover_row import LanguagePopoverRow


@Gtk.Template(resource_path=f"{RESOURCE_PREFIX}/ui/language_popover.ui")
class LanguagePopover(Gtk.Popover):
    """
    Searchable popover for selecting an installed Tesseract language.

    Signals
    -------
    language-changed(LanguageItem)
        Emitted when the user selects a language.
    """

    __gtype_name__ = "LanguagePopover"

    __gsignals__ = {
        "language-changed": (GObject.SIGNAL_RUN_LAST, None, (LanguageItem,)),
    }

    views:     Gtk.Stack       = Gtk.Template.Child()
    search_box: Gtk.Box        = Gtk.Template.Child()
    entry:     Gtk.SearchEntry = Gtk.Template.Child()
    list_view: Gtk.ListBox     = Gtk.Template.Child()

    def __init__(self, set_active: bool = True):
        super().__init__()
        self._set_active    = set_active
        self._active_code:  str | None = None

        self.settings = Gtk.Application.get_default().props.settings
        self._active_code = self.settings.get_string("active-language")

        self._lang_list   = Gio.ListStore(item_type=LanguageItem)
        self._filter      = Gtk.CustomFilter.new(self._filter_func, None)
        self._filter_list = Gtk.FilterListModel.new(self._lang_list, self._filter)
        self.list_view.bind_model(self._filter_list, LanguagePopoverRow)

        language_manager.connect("downloaded", lambda *_: self._populate())
        language_manager.connect("removed",    lambda *_: self._populate())

    # ------------------------------------------------------------------ #
    # Template callbacks                                                   #
    # ------------------------------------------------------------------ #

    @Gtk.Template.Callback()
    def _on_popover_show(self, _) -> None:
        self._populate()

    @Gtk.Template.Callback()
    def _on_popover_closed(self, _) -> None:
        self.entry.set_text("")

    @Gtk.Template.Callback()
    def _on_search_activate(self, _entry: Gtk.SearchEntry) -> None:
        self._on_language_activate(self.list_view, self.list_view.get_row_at_index(0))

    @Gtk.Template.Callback()
    def _on_language_activate(self, _box: Gtk.ListBox, row) -> None:
        if row is None:
            return
        item: LanguageItem = row.lang
        self._active_code = item.code
        if self._set_active:
            language_manager.active_language = item
        self.emit("language-changed", item)
        self.popdown()

    @Gtk.Template.Callback()
    def _on_search_changed(self, entry: Gtk.SearchEntry) -> None:
        query = entry.get_text().strip() or None
        new_filter = Gtk.CustomFilter.new(self._filter_func, query)
        self._filter_list.set_filter(new_filter)
        self._toggle_empty(not self._filter_list.get_n_items())

    @Gtk.Template.Callback()
    def _on_stop_search(self, _entry: Gtk.SearchEntry) -> None:
        self.popdown()

    @Gtk.Template.Callback()
    def _on_add_clicked(self, _: Gtk.Widget) -> None:
        self.activate_action("app.preferences")
        self.popdown()

    # ------------------------------------------------------------------ #
    # Private helpers                                                      #
    # ------------------------------------------------------------------ #

    def _filter_func(self, item: LanguageItem, query: str | None) -> bool:
        return not query or query.lower() in item.title.lower()

    def _populate(self) -> None:
        self._lang_list.remove_all()
        for lang_name in language_manager.get_downloaded_languages(force=True):
            code = language_manager.get_language_code(lang_name)
            self._lang_list.append(
                LanguageItem(code=code, title=lang_name, selected=(self._active_code == code))
            )
        # Emit initial selection
        codes = language_manager.get_downloaded_codes()
        code  = self._active_code if self._active_code in codes else "eng"
        self.emit("language-changed", language_manager.get_language_item(code))

    def _toggle_empty(self, is_empty: bool) -> None:
        self.views.set_visible_child_name("empty_page" if is_empty else "languages_page")
