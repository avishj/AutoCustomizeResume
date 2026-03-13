"""Terminal status output helpers.

Provides formatted print functions for pipeline progress, info,
success, and error messages displayed during execution.
"""

from __future__ import annotations


def step(current: int, total: int, msg: str) -> None:
    """Print a pipeline step progress message."""


def info(msg: str) -> None:
    """Print an informational message."""


def success(msg: str) -> None:
    """Print a success/completion message."""


def error(msg: str) -> None:
    """Print an error message to stderr."""
