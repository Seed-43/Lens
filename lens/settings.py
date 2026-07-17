# settings.py
#
# Copyright (C) 2026-present Seed-43
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

from gi.repository import Gio
from lens.config import APP_ID


class Settings(Gio.Settings):
    """
    Thin subclass of ``Gio.Settings`` bound to the Lens application schema.

    Use ``Settings.new()`` to obtain the singleton instance rather than
    constructing directly.
    """

    __gtype_name__ = "Settings"

    def __init__(self):
        Gio.Settings.__init__(self)

    @classmethod
    def new(cls) -> "Settings":
        """Return a ``Settings`` instance bound to the Lens GSettings schema."""
        settings = Gio.Settings.new(APP_ID)
        settings.__class__ = Settings
        return settings
