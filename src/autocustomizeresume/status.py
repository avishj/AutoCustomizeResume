# SPDX-FileCopyrightText: 2026 Avish Jha <avish.j@pm.me>
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Terminal status output helpers.

Provides formatted print functions for pipeline progress, info,
success, and error messages displayed during execution.
"""

from __future__ import annotations

import sys


def step(current: int, total: int, msg: str) -> None:
    """Print a pipeline step progress message."""
    print(f"[{current}/{total}] {msg}", flush=True)


def info(msg: str) -> None:
    """Print an informational message."""
    print(f"ℹ  {msg}", flush=True)


def success(msg: str) -> None:
    """Print a success/completion message."""
    print(f"✅ {msg}", flush=True)


def error(msg: str) -> None:
    """Print an error message to stderr."""
    print(f"❌ {msg}", file=sys.stderr, flush=True)
