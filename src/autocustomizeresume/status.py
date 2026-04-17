# SPDX-FileCopyrightText: 2026 Avish Jha <avish.j@pm.me>
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Terminal status output helpers.

Provides formatted print functions for pipeline progress, info,
success, and error messages displayed during execution.
"""

from __future__ import annotations

import sys
from typing import TextIO


def _write(line: str, *, stream: TextIO = sys.stdout) -> None:
    """Write one status line to the selected stream."""
    stream.write(f"{line}\n")
    stream.flush()


def step(current: int, total: int, msg: str) -> None:
    """Print a pipeline step progress message."""
    _write(f"[{current}/{total}] {msg}")


def info(msg: str) -> None:
    """Print an informational message."""
    _write(f"i  {msg}")


def success(msg: str) -> None:
    """Print a success/completion message."""
    _write(f"[ok] {msg}")


def error(msg: str) -> None:
    """Print an error message to stderr."""
    _write(f"[error] {msg}", stream=sys.stderr)
