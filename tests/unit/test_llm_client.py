# SPDX-FileCopyrightText: 2026 Avish Jha <avish.j@pm.me>
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for the LLM client wrapper."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx
import pytest

from autocustomizeresume.llm_client import LLMClient, LLMError

pytestmark = pytest.mark.unit

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_config() -> MagicMock:
    """Build a minimal mock Config for LLMClient."""
    cfg = MagicMock()
    cfg.llm.base_url = "https://api.example.com/v1"
    cfg.llm.model = "test-model"
    cfg.llm.api_key = "test-key-123"
    cfg.llm.api_key_env = "TEST_API_KEY"
    return cfg


def _mock_response(content: str | None) -> MagicMock:
    """Build a mock ChatCompletion response."""
    msg = MagicMock()
    msg.content = content
    choice = MagicMock()
    choice.message = msg
    resp = MagicMock()
    resp.choices = [choice]
    return resp


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


class TestInit:
    @patch("autocustomizeresume.llm_client.OpenAI")
    def test_reads_config(self, mock_openai_cls: MagicMock):
        cfg = _make_config()
        client = LLMClient(cfg)

        mock_openai_cls.assert_called_once()
        call_kwargs = mock_openai_cls.call_args.kwargs
        assert call_kwargs["base_url"] == "https://api.example.com/v1"
        assert call_kwargs["api_key"] == "test-key-123"
        assert "timeout" in call_kwargs
        assert client._model == "test-model"

    @patch("autocustomizeresume.llm_client.OpenAI")
    def test_custom_timeout(self, mock_openai_cls: MagicMock):
        cfg = _make_config()
        LLMClient(cfg, timeout=60.0)

        mock_openai_cls.assert_called_once()
        call_kwargs = mock_openai_cls.call_args.kwargs
        assert "timeout" in call_kwargs
        assert call_kwargs["timeout"] == httpx.Timeout(60.0)


# ---------------------------------------------------------------------------
# chat() — always returns parsed JSON dict
# ---------------------------------------------------------------------------


class TestChat:
    @patch("autocustomizeresume.llm_client.OpenAI")
    def test_returns_parsed_dict(self, mock_openai_cls: MagicMock):
        mock_client = mock_openai_cls.return_value
        mock_client.chat.completions.create.return_value = _mock_response(
            '{"name": "test", "value": 42}'
        )

        client = LLMClient(_make_config())
        result = client.chat(system="sys", user="usr")

        assert result == {"name": "test", "value": 42}

    @patch("autocustomizeresume.llm_client.OpenAI")
    def test_passes_messages_and_temperature(self, mock_openai_cls: MagicMock):
        mock_client = mock_openai_cls.return_value
        mock_client.chat.completions.create.return_value = _mock_response("{}")

        client = LLMClient(_make_config())
        client.chat(system="be helpful", user="hi", temperature=0.5)

        call_kwargs = mock_client.chat.completions.create.call_args[1]
        assert call_kwargs["model"] == "test-model"
        assert call_kwargs["temperature"] == 0.5
        assert call_kwargs["messages"] == [
            {"role": "system", "content": "be helpful"},
            {"role": "user", "content": "hi"},
        ]

    @patch("autocustomizeresume.llm_client.OpenAI")
    def test_always_uses_json_format(self, mock_openai_cls: MagicMock):
        mock_client = mock_openai_cls.return_value
        mock_client.chat.completions.create.return_value = _mock_response("{}")

        client = LLMClient(_make_config())
        client.chat(system="sys", user="usr")

        call_kwargs = mock_client.chat.completions.create.call_args[1]
        assert call_kwargs["response_format"] == {"type": "json_object"}

    @patch("autocustomizeresume.llm_client.OpenAI")
    def test_invalid_json_raises(self, mock_openai_cls: MagicMock):
        mock_client = mock_openai_cls.return_value
        mock_client.chat.completions.create.return_value = _mock_response(
            "not json at all"
        )

        client = LLMClient(_make_config())
        with pytest.raises(LLMError, match="invalid JSON"):
            client.chat(system="sys", user="usr")

    @patch("autocustomizeresume.llm_client.OpenAI")
    def test_json_array_raises(self, mock_openai_cls: MagicMock):
        mock_client = mock_openai_cls.return_value
        mock_client.chat.completions.create.return_value = _mock_response("[1, 2, 3]")

        client = LLMClient(_make_config())
        with pytest.raises(LLMError, match="Expected a JSON object"):
            client.chat(system="sys", user="usr")

    @patch("autocustomizeresume.llm_client.OpenAI")
    def test_strips_think_blocks(self, mock_openai_cls: MagicMock):
        mock_client = mock_openai_cls.return_value
        mock_client.chat.completions.create.return_value = _mock_response(
            '<think>reasoning</think>{"key": "val"}'
        )

        client = LLMClient(_make_config())
        result = client.chat(system="sys", user="usr")

        assert result == {"key": "val"}

    @patch("autocustomizeresume.llm_client.OpenAI")
    def test_none_content_raises(self, mock_openai_cls: MagicMock):
        mock_client = mock_openai_cls.return_value
        mock_client.chat.completions.create.return_value = _mock_response(None)

        client = LLMClient(_make_config())
        with pytest.raises(LLMError, match="empty response"):
            client.chat(system="sys", user="usr")

    @patch("autocustomizeresume.llm_client.OpenAI")
    def test_empty_choices_raises(self, mock_openai_cls: MagicMock):
        mock_client = mock_openai_cls.return_value
        resp = MagicMock()
        resp.choices = []
        mock_client.chat.completions.create.return_value = resp

        client = LLMClient(_make_config())
        with pytest.raises(LLMError, match="no choices"):
            client.chat(system="sys", user="usr")


# ---------------------------------------------------------------------------
# chat() — error handling
# ---------------------------------------------------------------------------


class TestChatErrors:
    @patch("autocustomizeresume.llm_client.OpenAI")
    def test_auth_error(self, mock_openai_cls: MagicMock):
        from openai import AuthenticationError

        mock_client = mock_openai_cls.return_value
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_resp.headers = {}
        mock_client.chat.completions.create.side_effect = AuthenticationError(
            message="bad key",
            response=mock_resp,
            body=None,
        )

        client = LLMClient(_make_config())
        with pytest.raises(LLMError, match="authentication failed") as exc_info:
            client.chat(system="sys", user="usr")
        assert "TEST_API_KEY" in str(exc_info.value)

    @patch("autocustomizeresume.llm_client.OpenAI")
    def test_timeout_error(self, mock_openai_cls: MagicMock):
        from openai import APITimeoutError

        mock_client = mock_openai_cls.return_value
        mock_client.chat.completions.create.side_effect = APITimeoutError(
            request=MagicMock(),
        )

        client = LLMClient(_make_config())
        with pytest.raises(LLMError, match="timed out"):
            client.chat(system="sys", user="usr")

    @patch("autocustomizeresume.llm_client.OpenAI")
    def test_connection_error(self, mock_openai_cls: MagicMock):
        from openai import APIConnectionError

        mock_client = mock_openai_cls.return_value
        mock_client.chat.completions.create.side_effect = APIConnectionError(
            request=MagicMock(),
        )

        client = LLMClient(_make_config())
        with pytest.raises(LLMError, match="Could not connect"):
            client.chat(system="sys", user="usr")

    @patch("autocustomizeresume.llm_client.OpenAI")
    def test_rate_limit_error(self, mock_openai_cls: MagicMock):
        from openai import RateLimitError

        mock_client = mock_openai_cls.return_value
        mock_resp = MagicMock()
        mock_resp.status_code = 429
        mock_resp.headers = {}
        mock_client.chat.completions.create.side_effect = RateLimitError(
            message="rate limited",
            response=mock_resp,
            body=None,
        )

        client = LLMClient(_make_config())
        with pytest.raises(LLMError, match="rate limit"):
            client.chat(system="sys", user="usr")

    @patch("autocustomizeresume.llm_client.OpenAI")
    def test_generic_error(self, mock_openai_cls: MagicMock):
        mock_client = mock_openai_cls.return_value
        mock_client.chat.completions.create.side_effect = RuntimeError("boom")

        client = LLMClient(_make_config())
        with pytest.raises(LLMError, match="LLM API call failed"):
            client.chat(system="sys", user="usr")
