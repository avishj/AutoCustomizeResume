"""Tests for the file watcher and debounced handler."""

from __future__ import annotations

import threading
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from watchdog.events import DirModifiedEvent, FileModifiedEvent

from autocustomizeresume.watcher import DebouncedHandler


# ---------------------------------------------------------------------------
# DebouncedHandler — debounce & filtering behavior
# ---------------------------------------------------------------------------


class TestDebouncedHandler:
    """Behavior tests for DebouncedHandler."""

    @pytest.fixture()
    def watched_file(self, tmp_path: Path) -> Path:
        f = tmp_path / "jd.txt"
        f.write_text("some job description")
        return f

    @staticmethod
    def _make_event(path: Path, *, is_directory: bool = False) -> DirModifiedEvent | FileModifiedEvent:
        if is_directory:
            return DirModifiedEvent(str(path))
        return FileModifiedEvent(str(path))

    def test_debounce_coalesces_rapid_events(self, watched_file: Path):
        """Multiple rapid events within the debounce window fire callback once."""
        callback = MagicMock()
        handler = DebouncedHandler(watched_file, debounce_seconds=0.15, callback=callback)
        fired = threading.Event()
        callback.side_effect = lambda: fired.set()

        for _ in range(5):
            handler.on_modified(self._make_event(watched_file))
            time.sleep(0.02)

        fired.wait(timeout=1.0)
        time.sleep(0.1)  # extra settle time
        assert callback.call_count == 1

    def test_debounce_resets_on_new_event(self, watched_file: Path):
        """A later event resets the debounce timer, delaying the callback."""
        callback = MagicMock()
        handler = DebouncedHandler(watched_file, debounce_seconds=0.15, callback=callback)

        handler.on_modified(self._make_event(watched_file))
        time.sleep(0.08)
        assert callback.call_count == 0, "should not have fired yet"

        handler.on_modified(self._make_event(watched_file))
        time.sleep(0.08)
        assert callback.call_count == 0, "timer should have reset, still waiting"

        fired = threading.Event()
        callback.side_effect = lambda: fired.set()
        fired.wait(timeout=1.0)
        assert callback.call_count == 1

    def test_ignores_directory_events(self, watched_file: Path):
        """Directory modification events are silently ignored."""
        callback = MagicMock()
        handler = DebouncedHandler(watched_file, debounce_seconds=0.05, callback=callback)

        handler.on_modified(self._make_event(watched_file, is_directory=True))
        time.sleep(0.15)
        callback.assert_not_called()

    def test_ignores_unrelated_file(self, tmp_path: Path, watched_file: Path):
        """Events for a different file in the same directory are ignored."""
        other = tmp_path / "other.txt"
        other.write_text("unrelated")

        callback = MagicMock()
        handler = DebouncedHandler(watched_file, debounce_seconds=0.05, callback=callback)

        handler.on_modified(self._make_event(other))
        time.sleep(0.15)
        callback.assert_not_called()

    def test_ignores_empty_file_save(self, watched_file: Path):
        """An event for a zero-byte file does not trigger the callback."""
        watched_file.write_text("")  # truncate to 0 bytes

        callback = MagicMock()
        handler = DebouncedHandler(watched_file, debounce_seconds=0.05, callback=callback)

        handler.on_modified(self._make_event(watched_file))
        time.sleep(0.15)
        callback.assert_not_called()
