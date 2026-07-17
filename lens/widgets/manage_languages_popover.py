# manage_languages_popover.py
#
# Copyright (C) 2026-present Seed-43
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

from gettext import gettext as _

from gi.repository import Gtk, GLib, GObject
from loguru import logger

from lens.config import RESOURCE_PREFIX
from lens.language_manager import language_manager


@Gtk.Template(resource_path=f"{RESOURCE_PREFIX}/ui/manage_languages_popover.ui")
class ManageLanguagesPopover(Gtk.Popover):
    __gtype_name__ = "ManageLanguagesPopover"

    search_entry: Gtk.SearchEntry = Gtk.Template.Child()
    list_view: Gtk.ListBox = Gtk.Template.Child()
    views: Gtk.Stack = Gtk.Template.Child()

    def __init__(self):
        super().__init__()
        language_manager.connect("downloaded", self._on_languages_changed)
        language_manager.connect("removed", self._on_languages_changed)

    @Gtk.Template.Callback()
    def _on_popover_show(self, _):
        self.search_entry.set_text("")
        self._populate(query=None)

    @Gtk.Template.Callback()
    def _on_popover_closed(self, _):
        self.search_entry.set_text("")

    @Gtk.Template.Callback()
    def _on_search_changed(self, entry: Gtk.SearchEntry):
        self._populate(query=entry.get_text().strip() or None)

    @Gtk.Template.Callback()
    def _on_stop_search(self, _):
        self.popdown()

    def _on_languages_changed(self, _sender, _code):
        self._populate(query=self.search_entry.get_text().strip() or None)

    def _populate(self, query: str | None = None):
        """Rebuild the list, showing all languages filtered by query."""
        # Remove all existing rows
        while row := self.list_view.get_row_at_index(0):
            self.list_view.remove(row)

        downloaded = set(language_manager.get_downloaded_codes())
        all_codes = language_manager.get_available_codes()

        shown = 0
        for code in all_codes:
            title = language_manager.get_language(code)
            if query and query.lower() not in title.lower():
                continue

            row = self._make_row(code, title, code in downloaded)
            self.list_view.append(row)
            shown += 1

        self.views.set_visible_child_name("languages" if shown > 0 else "empty")

    def _make_row(self, code: str, title: str, is_downloaded: bool) -> Gtk.ListBoxRow:
        """Build a single language row with download or delete button."""
        row = Gtk.ListBoxRow()
        row.set_activatable(False)

        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        box.set_margin_top(4)
        box.set_margin_bottom(4)
        box.set_margin_start(12)
        box.set_margin_end(6)

        label = Gtk.Label(label=title, xalign=0, hexpand=True)
        box.append(label)

        if is_downloaded and code != "eng":
            # Delete button
            btn = Gtk.Button(icon_name="user-trash-symbolic", has_frame=False)
            btn.set_tooltip_text(_("Remove language"))
            btn.add_css_class("flat")
            btn.connect("clicked", self._on_remove_clicked, code)
            box.append(btn)
        elif not is_downloaded:
            # Download button
            if code in language_manager.loading_languages:
                spinner = Gtk.Spinner(spinning=True)
                box.append(spinner)
            else:
                btn = Gtk.Button(icon_name="folder-download-symbolic", has_frame=False)
                btn.set_tooltip_text(_("Download language"))
                btn.add_css_class("flat")
                btn.connect("clicked", self._on_download_clicked, code)
                box.append(btn)
        else:
            # English — show a lock icon, can't be removed
            icon = Gtk.Image(icon_name="system-lock-screen-symbolic")
            icon.add_css_class("dim-label")
            box.append(icon)

        row.set_child(box)
        return row

    def _on_download_clicked(self, _btn, code: str):
        logger.debug(f"Downloading language: {code}")
        language_manager.download(code)
        # Rebuild to show spinner
        self._populate(query=self.search_entry.get_text().strip() or None)

    def _on_remove_clicked(self, _btn, code: str):
        logger.debug(f"Removing language: {code}")
        language_manager.remove_language(code)
