# SPDX-FileCopyrightText: 2026 Avish Jha <avish.j@pm.me>
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""File watcher with debounce for jd.txt.

Monitors the JD file for changes and triggers the pipeline
after a configurable debounce period.
"""

from __future__ import annotations

import os
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING

from watchdog.events import DirModifiedEvent, FileModifiedEvent, FileSystemEventHandler
from watchdog.observers import Observer

from autocustomizeresume import status
from autocustomizeresume.namer import handle_output
from autocustomizeresume.pipeline import run_pipeline

if TYPE_CHECKING:
    from collections.abc import Callable

    from autocustomizeresume.config import Config


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
        """Set up the handler with a debounced callback for *watch_path*."""
        super().__init__()
        self._watch_path = str(watch_path.resolve())
        self._debounce = debounce_seconds
        self._callback = callback
        self._timer: threading.Timer | None = None
        self._lock = threading.Lock()

    def on_modified(self, event: DirModifiedEvent | FileModifiedEvent) -> None:
        """Handle a file-modified event, debouncing rapid successive saves."""
        if event.is_directory:
            return
        src_path = os.path.abspath(os.fsdecode(event.src_path))
        if src_path != self._watch_path:
            return
        # Ignore empty-file saves
        try:
            if Path(src_path).stat().st_size == 0:
                return
        except OSError:
            return

        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
            self._timer = threading.Timer(self._debounce, self._callback)
            self._timer.daemon = True
            self._timer.start()


def watch(
    config: Config, *, company: str | None = None, role: str | None = None
) -> None:
    """Start watching the JD file for changes.

    Runs until interrupted with Ctrl+C.  Each detected change
    triggers a full pipeline run; errors are printed but do not
    stop the watcher.

    Parameters
    ----------
    config:
        Application configuration.
    company:
        Optional company name override for every run.
    role:
        Optional role title override for every run.
    """
    jd_path = Path(config.paths.jd_file).resolve()
    _run_lock = threading.Lock()
    _running = False

    def _on_change() -> None:
        nonlocal _running
        with _run_lock:
            if _running:
                status.info("Pipeline already running — skipping trigger.")
                return
            _running = True
        try:
            status.info("Change detected, running pipeline…")
            jd_text = jd_path.read_text(encoding="utf-8").strip()
            if not jd_text:
                status.info("JD file is empty — skipping.")
                return
            result = run_pipeline(jd_text, config, company=company, role=role)
            handle_output(result, config)
            status.success(f"Output → {config.paths.output_dir}/")
        except Exception as exc:
            status.error(f"Pipeline failed: {exc}")
        finally:
            with _run_lock:
                _running = False  # always release, even on early empty-file return

    handler = DebouncedHandler(jd_path, config.watcher.debounce_seconds, _on_change)
    observer = Observer()
    observer.schedule(handler, str(jd_path.parent), recursive=False)
    observer.start()

    status.info(f"Watching {config.paths.jd_file} for changes (Ctrl+C to stop)…")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        observer.stop()
        observer.join()
