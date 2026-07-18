# history_service.py
#
# Copyright (C) 2026-present Seed-43
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

import json
import os
from datetime import datetime

from gi.repository import GObject
from loguru import logger

HISTORY_FILE = os.path.join(
    os.environ.get('XDG_DATA_HOME', os.path.expanduser('~/.local/share')),
    'io.github.seed43.lens',
    'history.json'
)
MAX_ENTRIES = 100


class HistoryEntry:
    def __init__(self, text: str, timestamp: str = None, entry_id: str = None):
        self.text = text
        self.timestamp = timestamp or datetime.now().isoformat()
        self.id = entry_id or self.timestamp

    def to_dict(self) -> dict:
        return {"id": self.id, "text": self.text, "timestamp": self.timestamp}

    @classmethod
    def from_dict(cls, data: dict) -> 'HistoryEntry':
        return cls(
            text=data["text"],
            timestamp=data["timestamp"],
            entry_id=data.get("id", data["timestamp"])
        )

    def friendly_time(self) -> str:
        try:
            dt = datetime.fromisoformat(self.timestamp)
            now = datetime.now()
            if dt.date() == now.date():
                return f"Today {dt.strftime('%H:%M')}"
            elif (now.date() - dt.date()).days == 1:
                return f"Yesterday {dt.strftime('%H:%M')}"
            else:
                return dt.strftime('%d %b %H:%M')
        except Exception:
            return self.timestamp

    def preview(self, length: int = 30) -> str:
        text = self.text.strip().replace('\n', ' ')
        return text[:length] + '…' if len(text) > length else text


class HistoryService(GObject.GObject):
    """Persists and manages extraction history."""

    __gtype_name__ = "HistoryService"

    __gsignals__ = {
        "changed": (GObject.SIGNAL_RUN_FIRST, None, ()),
    }

    def __init__(self):
        super().__init__()
        self._entries: list[HistoryEntry] = []
        self._load()

    def add(self, text: str) -> HistoryEntry:
        entry = HistoryEntry(text=text)
        self._entries.insert(0, entry)
        if len(self._entries) > MAX_ENTRIES:
            self._entries = self._entries[:MAX_ENTRIES]
        self._save()
        self.emit("changed")
        return entry

    def delete(self, entry_id: str):
        self._entries = [e for e in self._entries if e.id != entry_id]
        self._save()
        self.emit("changed")

    def purge_old(self, days: int):
        """Remove entries older than `days` days."""
        from datetime import timedelta
        cutoff = datetime.now() - timedelta(days=days)
        before = len(self._entries)
        self._entries = [
            e for e in self._entries
            if datetime.fromisoformat(e.timestamp) > cutoff
        ]
        if len(self._entries) < before:
            self._save()
            self.emit("changed")

    def clear(self):
        self._entries = []
        self._save()
        self.emit("changed")

    def entries(self) -> list[HistoryEntry]:
        return self._entries

    def _load(self):
        try:
            if os.path.exists(HISTORY_FILE):
                with open(HISTORY_FILE) as f:
                    data = json.load(f)
                self._entries = [HistoryEntry.from_dict(e) for e in data]
                logger.debug(f"Loaded {len(self._entries)} history entries")
        except Exception as e:
            logger.debug(f"Could not load history: {e}")
            self._entries = []

    def _save(self):
        try:
            os.makedirs(os.path.dirname(HISTORY_FILE), exist_ok=True)
            with open(HISTORY_FILE, 'w') as f:
                json.dump([e.to_dict() for e in self._entries], f, indent=2)
        except Exception as e:
            logger.debug(f"Could not save history: {e}")


history_service = HistoryService()
