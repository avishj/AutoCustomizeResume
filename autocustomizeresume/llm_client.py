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

import httpx
from openai import (
    APIConnectionError,
    APITimeoutError,
    AuthenticationError,
    OpenAI,
    RateLimitError,
)

from autocustomizeresume.config import Config

logger = logging.getLogger(__name__)


def _extract_json(text: str) -> str:
    """Extract JSON from text that may contain thinking/reasoning content.

    Models that support thinking (e.g., minimax-m2.5, glm5) may output
    thinking in <!-- and --> or similar markers. This strips those and
    finds the last valid JSON object.
    """
    import re

    text = text.strip()

    # Strip thinking content between各种 thinking tags
    # Common patterns:<think>...</think>, ```thinking...```
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    text = re.sub(r"```thinking.*?```", "", text, flags=re.DOTALL)
    text = text.strip()

    # First try: direct parse (no thinking content)
    if text.startswith("{"):
        try:
            json.loads(text)
            return text
        except json.JSONDecodeError:
            pass

    # Find all potential JSON starts (lines starting with {)
    lines = text.split("\n")
    candidates: list[tuple[int, str]] = []

    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("{"):
            candidate = "\n".join(lines[i:])
            candidates.append((i, candidate))

    if not candidates:
        return text

    # Try parsing from the last candidate (most likely to be the actual JSON)
    for _, candidate in reversed(candidates):
        try:
            parsed = json.loads(candidate)
            # Verify it's a dict (our expected response type)
            if isinstance(parsed, dict):
                return candidate
        except json.JSONDecodeError:
            continue

    # Fallback: first { to last }
    first_brace = text.find("{")
    last_brace = text.rfind("}")

    if first_brace == -1 or last_brace == -1 or last_brace < first_brace:
        return text

    return text[first_brace : last_brace + 1]


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

    DEFAULT_TIMEOUT = 120.0  # seconds

    def __init__(
        self,
        config: Config,
        timeout: float | None = None,
    ) -> None:
        self._model = config.llm.model
        self._api_key_env = config.llm.api_key_env
        self._timeout = timeout if timeout is not None else self.DEFAULT_TIMEOUT
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
        temperature: float = 0.2,
        json_response: bool = False,
        stream: bool = False,
        extra_body: dict[str, Any] | None = None,
        **kwargs: Any,
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
        stream:
            If ``True``, stream the response and return concatenated content.
        extra_body:
            Extra body parameters to pass to the API (e.g., for NVIDIA NIM
            chat template kwargs).
        **kwargs:
            Additional parameters to pass to the chat completion API.

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

        request_kwargs: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "temperature": temperature,
        }

        if json_response:
            request_kwargs["response_format"] = {"type": "json_object"}

        if extra_body:
            request_kwargs["extra_body"] = extra_body

        request_kwargs.update(kwargs)

        logger.info(
            "LLM request: model=%s, stream=%s, json_response=%s, extra_body=%s",
            self._model,
            stream,
            json_response,
            extra_body,
        )
        logger.debug("LLM request kwargs: %s", request_kwargs)

        try:
            if stream:
                logger.info("Starting streaming request...")
                response = self._client.chat.completions.create(
                    **request_kwargs, stream=True
                )
                chunks: list[str] = []
                for i, chunk in enumerate(response):
                    logger.debug("Stream chunk %d: %s", i, chunk)
                    if not chunk.choices:
                        continue
                    delta = chunk.choices[0].delta
                    if delta and delta.content:
                        chunks.append(delta.content)
                result = "".join(chunks)
                logger.info("Streaming complete, got %d chars", len(result))
                return result

            logger.info("Starting non-streaming request...")
            response = self._client.chat.completions.create(**request_kwargs)
            logger.info("Non-streaming request complete")
        except AuthenticationError as exc:
            raise LLMError(
                f"LLM authentication failed — check your API key "
                f"(env var '{self._api_key_env}'): {exc}"
            ) from exc
        except APITimeoutError as exc:
            raise LLMError(f"LLM API request timed out: {exc}") from exc
        except APIConnectionError as exc:
            raise LLMError(
                f"Could not connect to LLM API at {self._client.base_url}: {exc}"
            ) from exc
        except RateLimitError as exc:
            raise LLMError(f"LLM API rate limit exceeded: {exc}") from exc
        except httpx.TimeoutException as exc:
            raise LLMError(
                f"LLM API request timed out after {self._timeout}s: {exc}"
            ) from exc
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
        extra_body: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Send a chat request and parse the response as JSON.

        Convenience wrapper around :meth:`chat` that sets
        ``json_response=True`` and parses the result.

        Parameters
        ----------
        system:
            The system prompt.
        user:
            The user message.
        temperature:
            Sampling temperature.
        extra_body:
            Extra body parameters for the API.
        **kwargs:
            Additional parameters to pass to the chat API.

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
            extra_body=extra_body,
            **kwargs,
        )

        json_text = _extract_json(raw)

        try:
            parsed = json.loads(json_text)
        except json.JSONDecodeError as exc:
            raise LLMError(
                f"LLM returned invalid JSON: {exc}\nRaw response:\n{raw}"
            ) from exc

        if not isinstance(parsed, dict):
            raise LLMError(
                f"Expected a JSON object (dict), got {type(parsed).__name__}: {raw}"
            )

        return parsed
