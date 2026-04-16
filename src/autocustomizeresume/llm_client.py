"""OpenAI-compatible LLM client.

Thin wrapper around the ``openai`` library that reads connection
settings from Config and exposes a simple ``chat()`` method.
Works with any OpenAI-compatible API (NVIDIA NIM, Groq, Together,
Ollama, OpenAI, etc.).
"""

from __future__ import annotations

import json
import logging
import re
from typing import TYPE_CHECKING, Any

import httpx
from openai import (
    APIConnectionError,
    APITimeoutError,
    AuthenticationError,
    OpenAI,
    RateLimitError,
)

from autocustomizeresume.model_registry import get_model_params

if TYPE_CHECKING:
    from autocustomizeresume.config import Config

logger = logging.getLogger(__name__)


_THINK_TAG_RE = re.compile(r"<think>.*?</think>", re.DOTALL)


def _strip_think_blocks(text: str) -> str:
    """Strip ``<think>…</think>`` reasoning blocks from model output.

    Reasoning models (e.g., minimax-m2.5, glm5) may prepend a thinking
    block even when ``response_format=json_object`` is set.  The OpenAI
    API spec keeps thinking content in a separate ``reasoning_content``
    field, but not all providers follow that convention—some inline it
    in the main ``content`` field wrapped in ``<think>`` tags.

    This function removes those tags so the remaining text can be parsed
    as JSON.
    """
    return _THINK_TAG_RE.sub("", text).strip()


class LLMError(Exception):
    """Raised when an LLM call fails after all attempts."""


class LLMClient:
    """Reusable client for OpenAI-compatible chat completions.

    Parameters
    ----------
    config:
        The application ``Config`` object.  LLM settings (``base_url``,
        ``model``, ``api_key``) are read from ``config.llm``.
    """

    DEFAULT_TIMEOUT = 600.0  # seconds

    def __init__(
        self,
        config: Config,
        timeout: float | None = None,
    ) -> None:
        self._model = config.llm.model
        self._api_key_env = config.llm.api_key_env
        self._timeout = timeout if timeout is not None else self.DEFAULT_TIMEOUT
        self._profile = get_model_params(self._model)
        self._client = OpenAI(
            base_url=config.llm.base_url,
            api_key=config.llm.api_key,
            timeout=httpx.Timeout(self._timeout),
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def chat(
        self,
        *,
        system: str,
        user: str,
        temperature: float | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Send a chat completion request and return parsed JSON.

        Always requests ``response_format={"type": "json_object"}``,
        strips any ``<think>`` blocks, and parses the response as JSON.
        Sampling parameters are resolved from the model registry profile;
        an explicit *temperature* overrides the profile value.

        Parameters
        ----------
        system:
            The system prompt.
        user:
            The user prompt.
        temperature:
            Sampling temperature override.  When ``None`` (default) the
            value from the model registry profile is used.
        **kwargs:
            Additional parameters to pass to the chat completion API.

        Returns:
        -------
        dict
            The parsed JSON object.

        Raises:
        ------
        LLMError
            On authentication, connection, timeout, rate-limit,
            unexpected API failures, or invalid JSON responses.
        """
        messages: list[dict[str, str]] = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]

        if temperature is None:
            temperature = self._profile["temperature"]

        request_kwargs: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "temperature": temperature,
            "top_p": self._profile["top_p"],
            "max_tokens": self._profile["max_tokens"],
            "response_format": {"type": "json_object"},
            **self._profile.get("extra_params", {}),
            **kwargs,
        }

        logger.info("LLM request: model=%s", self._model)
        logger.debug("LLM request kwargs: %s", request_kwargs)

        try:
            response = self._client.chat.completions.create(**request_kwargs)

            if not response.choices:
                msg = "LLM returned no choices (empty choices list)"
                raise LLMError(msg)

            raw = response.choices[0].message.content
            if raw is None:
                msg = "LLM returned an empty response (content is None)"
                raise LLMError(msg)
        except AuthenticationError as exc:
            msg = (
                f"LLM authentication failed — check your API key "
                f"(env var '{self._api_key_env}'): {exc}"
            )
            raise LLMError(msg) from exc
        except APITimeoutError as exc:
            msg = f"LLM API request timed out: {exc}"
            raise LLMError(msg) from exc
        except APIConnectionError as exc:
            msg = f"Could not connect to LLM API at {self._client.base_url}: {exc}"
            raise LLMError(msg) from exc
        except RateLimitError as exc:
            msg = f"LLM API rate limit exceeded: {exc}"
            raise LLMError(msg) from exc
        except httpx.TimeoutException as exc:
            msg = f"LLM API request timed out after {self._timeout}s: {exc}"
            raise LLMError(msg) from exc
        except LLMError:
            raise
        except Exception as exc:
            msg = f"LLM API call failed: {exc}"
            raise LLMError(msg) from exc

        json_text = _strip_think_blocks(raw)

        try:
            parsed = json.loads(json_text)
        except json.JSONDecodeError as exc:
            msg = f"LLM returned invalid JSON: {exc}\nRaw response:\n{raw}"
            raise LLMError(msg) from exc

        if not isinstance(parsed, dict):
            msg = f"Expected a JSON object (dict), got {type(parsed).__name__}: {raw}"
            raise LLMError(msg)

        return parsed
