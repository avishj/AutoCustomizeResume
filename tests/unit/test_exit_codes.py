# SPDX-FileCopyrightText: 2026 Avish Jha <avish.j@pm.me>
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Unit tests for exit codes."""

import pytest

from autocustomizeresume.exit_codes import ExitCode


pytestmark = pytest.mark.unit


def test_ok_is_zero():
    assert ExitCode.OK == 0


def test_error_is_one():
    assert ExitCode.ERROR == 1


def test_codes_are_int():
    for code in ExitCode:
        assert isinstance(code, int)
