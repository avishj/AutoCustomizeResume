"""Tests for the model registry."""

from __future__ import annotations

import pytest

from autocustomizeresume.model_registry import _DEFAULTS, get_model_params

pytestmark = pytest.mark.unit


class TestGetModelParams:
    def test_unknown_model_returns_defaults(self):
        result = get_model_params("some/unknown-model")
        assert result == _DEFAULTS
        assert result is not _DEFAULTS

    def test_returns_copy_not_reference(self):
        a = get_model_params("qwen/qwen3.5-397b-a17b")
        b = get_model_params("qwen/qwen3.5-397b-a17b")
        a["temperature"] = 999
        assert b["temperature"] != 999
