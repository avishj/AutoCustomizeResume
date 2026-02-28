"""OpenAI-compatible LLM client.

Thin wrapper around the ``openai`` library that reads connection
settings from Config and exposes a simple ``chat()`` method.
Works with any OpenAI-compatible API (NVIDIA NIM, Groq, Together,
Ollama, OpenAI, etc.).
"""

from __future__ import annotations

import json
import logging
from typing import Any

from openai import APIConnectionError, APITimeoutError, AuthenticationError, OpenAI, RateLimitError

from autocustomizeresume.config import Config

logger = logging.getLogger(__name__)


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

    def __init__(self, config: Config) -> None:
        self._model = config.llm.model
        self._client = OpenAI(
            base_url=config.llm.base_url,
            api_key=config.llm.api_key,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def chat(
        self,
        *,
        system: str,
        user: str,
        temperature: float = 0.2,
        json_response: bool = False,
    ) -> str:
        """Send a chat completion request and return the assistant reply.

        Parameters
        ----------
        system:
            The system prompt.
        user:
            The user prompt.
        temperature:
            Sampling temperature (default 0.2 for deterministic-ish output).
        json_response:
            If ``True``, requests ``response_format={"type": "json_object"}``
            so the model is constrained to produce valid JSON.

        Returns
        -------
        str
            The assistant's response text.

        Raises
        ------
        LLMError
            On authentication, connection, timeout, rate-limit, or
            unexpected API failures.
        """
        messages: list[dict[str, str]] = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]

        kwargs: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "temperature": temperature,
        }

        if json_response:
            kwargs["response_format"] = {"type": "json_object"}

        try:
            response = self._client.chat.completions.create(**kwargs)
        except AuthenticationError as exc:
            raise LLMError(
                f"LLM authentication failed — check your API key "
                f"(env var from config llm.api_key_env): {exc}"
            ) from exc
        except APITimeoutError as exc:
            raise LLMError(f"LLM API request timed out: {exc}") from exc
        except APIConnectionError as exc:
            raise LLMError(
                f"Could not connect to LLM API at {self._client.base_url}: {exc}"
            ) from exc
        except RateLimitError as exc:
            raise LLMError(f"LLM API rate limit exceeded: {exc}") from exc
        except Exception as exc:
            raise LLMError(f"LLM API call failed: {exc}") from exc

        if not response.choices:
            raise LLMError("LLM returned no choices (empty choices list)")

        choice = response.choices[0]
        content = choice.message.content

        if content is None:
            raise LLMError("LLM returned an empty response (content is None)")

        return content

    def chat_json(
        self,
        *,
        system: str,
        user: str,
        temperature: float = 0.2,
    ) -> dict[str, Any]:
        """Send a chat request and parse the response as JSON.

        Convenience wrapper around :meth:`chat` that sets
        ``json_response=True`` and parses the result.

        Returns
        -------
        dict
            The parsed JSON object.

        Raises
        ------
        LLMError
            If the LLM call fails or the response is not valid JSON.
        """
        raw = self.chat(
            system=system,
            user=user,
            temperature=temperature,
            json_response=True,
        )

        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise LLMError(
                f"LLM returned invalid JSON: {exc}\nRaw response:\n{raw}"
            ) from exc

        if not isinstance(parsed, dict):
            raise LLMError(
                f"Expected a JSON object (dict), got {type(parsed).__name__}: {raw}"
            )

        return parsed
