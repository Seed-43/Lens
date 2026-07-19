# hotkey_service.py
#
# Copyright (C) 2026-present Seed-43
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

import os
import re
import subprocess
from gettext import gettext as _

from gi.repository import GObject, Gtk
from loguru import logger

LENS_BINDING_PATH = "/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/lens-hotkey/"
MEDIA_SCHEMA      = "org.gnome.settings-daemon.plugins.media-keys"
CUSTOM_SCHEMA     = "org.gnome.settings-daemon.plugins.media-keys.custom-keybinding"

# /.flatpak-info only exists inside a Flatpak sandbox — the standard,
# reliable way to detect it. flatpak-spawn is only meaningful (and
# only present) in that context; a native install (like the Fedora
# RPM) needs gsettings/dconf called directly instead.
_IN_FLATPAK = os.path.exists("/.flatpak-info")

APP_CMD_SILENT = "/usr/bin/flatpak run --user io.github.seed43.lens -- -e" if _IN_FLATPAK else "/usr/bin/lens -e"
APP_CMD_SHOW   = "/usr/bin/flatpak run --user io.github.seed43.lens" if _IN_FLATPAK else "/usr/bin/lens"

DEFAULT_SHORTCUT = "<Primary>g"


def _run(cmd: list) -> str | None:
    """Run a command — via flatpak-spawn on the host if sandboxed,
    directly otherwise (native installs have no flatpak-spawn at all)."""
    try:
        full_cmd = (["flatpak-spawn", "--host"] if _IN_FLATPAK else []) + cmd
        logger.debug(f"Running: {' '.join(full_cmd)}")
        result = subprocess.run(full_cmd, capture_output=True, text=True, timeout=5)
        if result.returncode != 0:
            logger.debug(f"Command failed: {result.stderr.strip()}")
            return None
        return result.stdout.strip()
    except Exception as e:
        logger.debug(f"Command error: {e}")
        return None


def _gset(schema_path: str, key: str, value: str) -> bool:
    """Set a gsettings key with a path."""
    result = _run(["gsettings", "set", f"{CUSTOM_SCHEMA}:{schema_path}", key, value])
    return result is not None


def _gget(schema_path: str, key: str) -> str | None:
    """Get a gsettings key with a path."""
    return _run(["gsettings", "get", f"{CUSTOM_SCHEMA}:{schema_path}", key])


def _media_set(key: str, value: str) -> bool:
    result = _run(["gsettings", "set", MEDIA_SCHEMA, key, value])
    return result is not None


def _media_get(key: str) -> str | None:
    return _run(["gsettings", "get", MEDIA_SCHEMA, key])


class HotkeyService(GObject.GObject):
    """Registers and manages a system-wide GNOME hotkey for Lens."""

    __gtype_name__ = "HotkeyService"

    __gsignals__ = {
        "shortcut-changed": (GObject.SIGNAL_RUN_FIRST, None, (str,)),
    }

    def __init__(self):
        super().__init__()

    def get_current_shortcut(self) -> str | None:
        result = _gget(LENS_BINDING_PATH, "binding")
        if result and result not in ("''", '""', ""):
            return result.strip("'\"")
        return None

    def get_current_mode(self) -> str:
        result = _gget(LENS_BINDING_PATH, "command")
        if result and "-e" in result:
            return "silent"
        return "show"

    def find_conflict(self, shortcut: str) -> str | None:
        """
        Check whether *shortcut* is already claimed by another GNOME
        custom keybinding, and if so, return that binding's name.

        This only checks other custom keybindings — apps and scripts
        that registered a shortcut the same way Lens does. It can't see
        built-in GNOME/window-manager shortcuts (workspace switching,
        window snapping, the default screenshot tool, etc.), those live
        in a different schema entirely and aren't practical to enumerate
        reliably here. A clean result from this check is a good sign,
        not a guarantee the combination is free.
        """
        ok, keyval, mods = Gtk.accelerator_parse(shortcut)
        if not ok:
            return None

        current = _media_get("custom-keybindings") or "@as []"
        for path in re.findall(r"'([^']+)'", current):
            if path == LENS_BINDING_PATH:
                continue
            binding = _run(["gsettings", "get", f"{CUSTOM_SCHEMA}:{path}", "binding"])
            if not binding:
                continue
            other_binding = binding.strip("'\"")
            if not other_binding:
                continue
            other_ok, other_keyval, other_mods = Gtk.accelerator_parse(other_binding)
            if other_ok and other_keyval == keyval and other_mods == mods:
                name = _run(["gsettings", "get", f"{CUSTOM_SCHEMA}:{path}", "name"])
                return (name or "").strip("'\"") or _("another shortcut")
        return None

    def set_shortcut(self, shortcut: str, mode: str = "silent") -> bool:
        try:
            cmd = APP_CMD_SILENT if mode == "silent" else APP_CMD_SHOW

            _gset(LENS_BINDING_PATH, "name", "'Lens Text Extractor'")
            _gset(LENS_BINDING_PATH, "command", f"'{cmd}'")
            _gset(LENS_BINDING_PATH, "binding", f"'{shortcut}'")

            # Register path in media-keys list
            current = _media_get("custom-keybindings") or "@as []"
            if LENS_BINDING_PATH not in current:
                # Parse existing list and append
                cleaned = current.strip()
                if cleaned in ("@as []", "[]", ""):
                    new_val = f"['{LENS_BINDING_PATH}']"
                else:
                    # Remove closing bracket and append
                    new_val = cleaned.rstrip("]").rstrip() + f", '{LENS_BINDING_PATH}']"
                _media_set("custom-keybindings", new_val)

            logger.debug(f"Hotkey registered: {shortcut} -> {cmd}")
            self.emit("shortcut-changed", shortcut)
            return True

        except Exception as e:
            logger.debug(f"Failed to set hotkey: {e}")
            return False

    def clear_shortcut(self) -> bool:
        try:
            # Remove from custom-keybindings list
            current = _media_get("custom-keybindings") or "@as []"
            if LENS_BINDING_PATH in current:
                import re
                new_val = re.sub(rf",?\s*'{re.escape(LENS_BINDING_PATH)}'", "", current)
                new_val = re.sub(rf"'{re.escape(LENS_BINDING_PATH)}',?\s*", "", new_val)
                stripped = new_val.strip("[]").strip().strip(",").strip()
                new_val = "@as []" if not stripped else f"[{stripped}]"
                _media_set("custom-keybindings", new_val)

            # Fully wipe the dconf path so no stale entries remain
            _run(["dconf", "reset", "-f",
                  "/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/lens-hotkey/"])

            logger.debug("Hotkey cleared")
            self.emit("shortcut-changed", "")
            return True

        except Exception as e:
            logger.debug(f"Failed to clear hotkey: {e}")
            return False


hotkey_service = HotkeyService()
