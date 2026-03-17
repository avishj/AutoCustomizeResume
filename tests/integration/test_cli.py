"""CLI integration tests."""

import pytest

from autocustomizeresume import __version__


pytestmark = pytest.mark.integration


def test_version(invoke):
    result = invoke("--version")
    assert result.exit_code == 0
    assert __version__ in result.output


def test_help(invoke):
    result = invoke("--help")
    assert result.exit_code == 0
    assert "Usage" in result.output
