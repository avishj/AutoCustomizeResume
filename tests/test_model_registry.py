"""Tests for the model registry."""

from __future__ import annotations

from autocustomizeresume.model_registry import _DEFAULTS, get_model_params


class TestGetModelParams:
    def test_known_model_overrides_defaults(self):
        params = get_model_params("qwen/qwen3.5-397b-a17b")
        # A registered model should differ from defaults in at least one key
        assert any(params[k] != _DEFAULTS[k] for k in _DEFAULTS)
        # And still contain all expected keys
        assert set(_DEFAULTS) <= set(params)

    def test_unknown_model_returns_defaults(self):
        assert get_model_params("some/unknown-model") == _DEFAULTS

    def test_returns_copy_not_reference(self):
        a = get_model_params("qwen/qwen3.5-397b-a17b")
        b = get_model_params("qwen/qwen3.5-397b-a17b")
        a["temperature"] = 999
        assert b["temperature"] != 999
