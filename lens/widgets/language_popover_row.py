# language_popover_row.py
#
# Copyright (C) 2026-present Seed-43
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

from gi.repository import GObject, Gtk

from lens.config import RESOURCE_PREFIX
from lens.types.language_item import LanguageItem


@Gtk.Template(resource_path=f"{RESOURCE_PREFIX}/ui/language_popover_row.ui")
class LanguagePopoverRow(Gtk.ListBoxRow):
    """A single row in the language selector popover."""

    __gtype_name__ = "LanguagePopoverRow"

    title:     Gtk.Label = Gtk.Template.Child()
    selection: Gtk.Image = Gtk.Template.Child()

    def __init__(self, lang: LanguageItem):
        super().__init__()
        self.lang = lang
        self.title.set_label(lang.title)
        lang.bind_property(
            "selected",
            self.selection,
            "visible",
            GObject.BindingFlags.SYNC_CREATE,
        )
