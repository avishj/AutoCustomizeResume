# SPDX-FileCopyrightText: 2026 Avish Jha <avish.j@pm.me>
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Unit tests for application configuration."""

import pytest

from autocustomizeresume.config import Settings


pytestmark = pytest.mark.unit


def test_defaults(monkeypatch):
    monkeypatch.delenv("AUTOCUSTOMIZERESUME_VERBOSE", raising=False)
    s = Settings(_env_file=None)
    assert s.verbose is False


def test_env_prefix(monkeypatch):
    monkeypatch.setenv("AUTOCUSTOMIZERESUME_VERBOSE", "1")
    s = Settings(_env_file=None)
    assert s.verbose is True


def test_env_without_prefix_ignored(monkeypatch):
    monkeypatch.delenv("AUTOCUSTOMIZERESUME_VERBOSE", raising=False)
    monkeypatch.setenv("VERBOSE", "true")
    s = Settings(_env_file=None)
    assert s.verbose is False
