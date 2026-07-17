# download_state.py
#
# Copyright (C) 2026-present Seed-43
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.


class DownloadState:
    """
    Tracks the progress of an in-flight language pack download.

    Attributes
    ----------
    total:    Total bytes expected (0 = unknown).
    progress: Bytes received so far.
    """

    __slots__ = ("total", "progress")

    def __init__(self, total: int = 0, progress: int = 0):
        self.total    = total
        self.progress = progress

    @property
    def percent(self) -> int:
        """Download completion as an integer 0–100."""
        if self.total <= 0:
            return 0
        return min(100, int(self.progress * 100 / self.total))

    def __repr__(self) -> str:
        return f"<DownloadState: {self.progress}/{self.total} ({self.percent}%)>"
