# language_row.py
#
# Copyright (C) 2026-present Seed-43
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

from gi.repository import GLib, GObject, Gtk
from loguru import logger

from lens.config import RESOURCE_PREFIX
from lens.language_manager import language_manager
from lens.types.language_item import LanguageItem


@Gtk.Template(resource_path=f"{RESOURCE_PREFIX}/ui/language_row.ui")
class LanguageRow(Gtk.Overlay):
    """
    A list row showing a language with install / remove controls
    and a download progress bar.
    """

    __gtype_name__ = "LanguageRow"

    label:        Gtk.Label      = Gtk.Template.Child()
    install_btn:  Gtk.Button     = Gtk.Template.Child()
    remove_btn:   Gtk.Button     = Gtk.Template.Child()
    progress_bar: Gtk.ProgressBar = Gtk.Template.Child()
    revealer:     Gtk.Revealer   = Gtk.Template.Child()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._item: LanguageItem | None = None
        self.progress_bar.set_fraction(0.14)

        language_manager.connect("downloading", self._on_downloading)
        language_manager.connect("downloaded",  self._on_downloaded)

        GLib.idle_add(self._refresh_ui)

    # ------------------------------------------------------------------ #
    # Item property                                                        #
    # ------------------------------------------------------------------ #

    @GObject.Property(type=GObject.TYPE_PYOBJECT)
    def item(self) -> LanguageItem | None:
        return self._item

    @item.setter
    def item(self, value: LanguageItem) -> None:
        self._item = value
        self.label.set_label(value.title)

    # ------------------------------------------------------------------ #
    # Template callbacks                                                   #
    # ------------------------------------------------------------------ #

    @Gtk.Template.Callback()
    def _on_download(self, _btn: Gtk.Button) -> None:
        if not self._item or self._item.code in language_manager.loading_languages:
            return
        language_manager.download(self._item.code)
        self._refresh_ui()

    @Gtk.Template.Callback()
    def _on_remove(self, _btn: Gtk.Button) -> None:
        if not self._item or self._item.code in language_manager.loading_languages:
            return
        if self._item.code in language_manager.get_downloaded_codes():
            language_manager.remove_language(self._item.code)
            self._refresh_ui()

    # ------------------------------------------------------------------ #
    # Signal handlers                                                      #
    # ------------------------------------------------------------------ #

    def _on_downloading(self, _sender, code: str, progress: int) -> None:
        if self._item and self._item.code == code:
            GLib.idle_add(self._update_progress, code, progress)

    def _on_downloaded(self, _sender, code: str) -> None:
        if self._item and self._item.code == code:
            GLib.idle_add(self._refresh_ui)

    # ------------------------------------------------------------------ #
    # Private helpers                                                      #
    # ------------------------------------------------------------------ #

    def _refresh_ui(self) -> None:
        if not self._item:
            return
        code = self._item.code

        # English is always installed and cannot be removed
        if code == "eng":
            self.install_btn.set_visible(False)
            self.remove_btn.set_sensitive(False)
            return

        is_installed  = code in language_manager.get_downloaded_codes()
        is_loading    = code in language_manager.loading_languages

        self.install_btn.set_visible(not is_installed and not is_loading)
        self.install_btn.set_sensitive(not is_loading)
        self.remove_btn.set_visible(is_installed)
        if not is_installed:
            self.revealer.set_reveal_child(False)

    def _update_progress(self, code: str, progress: int) -> None:
        if not self._item or self._item.code != code:
            return
        if not self.revealer.get_reveal_child():
            self.revealer.set_reveal_child(True)
        self.progress_bar.set_fraction(progress / 100)
        logger.debug(f"Downloading {code}: {progress}%")
        if progress >= 100:
            self.revealer.set_reveal_child(False)
