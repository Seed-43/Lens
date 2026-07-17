# gobject_worker.py
#
# Copyright (C) 2026-present Seed-43
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.

"""
Lightweight helper for running blocking work on a background thread
and delivering the result back to the GLib main loop.
"""

import threading
import traceback
from typing import Callable

from gi.repository import GLib
from loguru import logger


class GObjectWorker:
    """
    Run a callable in a daemon thread and schedule the result callback
    on the GLib main loop when it finishes.

    Usage
    -----
    GObjectWorker.call(
        my_blocking_function,
        args=(arg1, arg2),
        callback=on_done,       # called on main thread with the return value
        errorback=on_error,     # called on main thread with the exception
    )
    """

    @staticmethod
    def call(
        func: Callable,
        args: tuple = (),
        callback: Callable | None = None,
        errorback: Callable | None = None,
    ) -> None:
        """
        Schedule *func* to run on a background daemon thread.

        Parameters
        ----------
        func:
            The blocking callable to execute off the main thread.
        args:
            Positional arguments forwarded to *func*.
        callback:
            Optional callable invoked on the GLib main loop with the
            return value of *func* as its sole argument.
        errorback:
            Optional callable invoked on the GLib main loop with the
            exception if *func* raises.  Defaults to a logger warning.
        """
        if errorback is None:
            errorback = GObjectWorker._default_errorback

        def _run():
            try:
                result = func(*args)
                if callback:
                    GLib.idle_add(callback, result)
            except Exception as exc:
                exc.traceback = traceback.format_exc()
                GLib.idle_add(errorback, exc)

        thread = threading.Thread(target=_run, daemon=True)
        thread.start()

    @staticmethod
    def _default_errorback(exc: Exception) -> None:
        logger.warning(f"Unhandled error in worker thread:\n{getattr(exc, 'traceback', exc)}")
