"""Tests for the model registry."""

from __future__ import annotations

from autocustomizeresume.model_registry import get_model_params


class TestGetModelParams:
    def test_known_model_returns_profile(self):
        params = get_model_params("qwen/qwen3.5-397b-a17b")
        assert params["temperature"] == 0.6
        assert params["top_p"] == 0.95
        assert params["max_tokens"] == 16384
        assert params["extra_params"]["extra_body"]["top_k"] == 20

    def test_known_model_minimax(self):
        params = get_model_params("minimaxai/minimax-m2.5")
        assert params["temperature"] == 1
        assert params["max_tokens"] == 16384

    def test_unknown_model_returns_defaults(self):
        params = get_model_params("some/unknown-model")
        assert params["temperature"] == 1.0
        assert params["top_p"] == 1.0
        assert params["max_tokens"] == 16384
        assert params["extra_params"] == {}

    def test_returns_copy_not_reference(self):
        a = get_model_params("qwen/qwen3.5-397b-a17b")
        b = get_model_params("qwen/qwen3.5-397b-a17b")
        a["temperature"] = 999
        assert b["temperature"] == 0.6
