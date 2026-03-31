# SPDX-FileCopyrightText: 2026 Avish Jha <avish.j@pm.me>
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""CLI integration tests."""

import pytest

from autocustomizeresume import __version__
from autocustomizeresume.exit_codes import ExitCode


pytestmark = pytest.mark.integration


def test_version(invoke):
    result = invoke("--version")
    assert result.exit_code == ExitCode.OK
    assert __version__ in result.output


def test_help(invoke):
    result = invoke("--help")
    assert result.exit_code == ExitCode.OK
    assert "Usage" in result.output
