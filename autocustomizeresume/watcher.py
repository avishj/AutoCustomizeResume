"""File watcher with debounce for jd.txt.

Monitors the JD file for changes and triggers the pipeline
after a configurable debounce period.
"""

from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import Callable

from watchdog.events import FileModifiedEvent, FileSystemEventHandler


class DebouncedHandler(FileSystemEventHandler):
    """Watchdog handler that debounces rapid file modifications.

    Fires *callback* only after *debounce_seconds* elapse with no
    further modification events on the watched file.  Empty-file
    saves are ignored.

    Parameters
    ----------
    watch_path:
        Absolute path to the file being watched.
    debounce_seconds:
        Seconds to wait after the last event before firing.
    callback:
        Called (with no arguments) when the debounce period elapses.
    """

    def __init__(
        self,
        watch_path: Path,
        debounce_seconds: float,
        callback: Callable[[], None],
    ) -> None:
        super().__init__()
        self._watch_path = str(watch_path.resolve())
        self._debounce = debounce_seconds
        self._callback = callback
        self._timer: threading.Timer | None = None
        self._lock = threading.Lock()

    def on_modified(self, event: FileModifiedEvent) -> None:  # type: ignore[override]
        if event.is_directory:
            return
        if os.path.abspath(event.src_path) != self._watch_path:
            return
        # Ignore empty-file saves
        try:
            if Path(event.src_path).stat().st_size == 0:
                return
        except OSError:
            return

        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
            self._timer = threading.Timer(self._debounce, self._callback)
            self._timer.daemon = True
            self._timer.start()
