# language_item.py
#
# Copyright (C) 2026-present Seed-43
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

from gi.repository import GObject


class LanguageItem(GObject.GObject):
    """
    A single Tesseract language entry.

    Attributes
    ----------
    code:
        ISO 639-3 / Tesseract language code, e.g. ``"eng"``.
    title:
        Human-readable display name, e.g. ``"English"``.
    selected:
        Whether this item is currently the active selection.
    """

    __gtype_name__ = "LanguageItem"

    title:    str  = GObject.Property(type=str)
    code:     str  = GObject.Property(type=str)
    selected: bool = GObject.Property(type=bool, default=False)

    def __init__(self, code: str, title: str, selected: bool = False):
        super().__init__()
        self.code     = code
        self.title    = title
        self.selected = selected

    def __repr__(self) -> str:
        return f"<LanguageItem: {self.title}, {self.code}>"
