# SPDX-FileCopyrightText: 2026 Avish Jha <avish.j@pm.me>
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""End-to-end tests invoking the CLI as a subprocess."""

import subprocess

import pytest


pytestmark = pytest.mark.e2e


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["autocustomizeresume", *args],
        capture_output=True,
        text=True,
        check=False,
    )


def test_version_flag():
    result = _run("--version")
    assert result.returncode == 0
    assert result.stdout.strip()


def test_help_shows_usage():
    result = _run("--help")
    assert result.returncode == 0
    assert "Usage" in result.stdout or "autocustomizeresume" in result.stdout


def test_invalid_command():
    result = _run("nonexistent")
    assert result.returncode != 0
