"""
LLM client for PPT Agent.

Wraps DeepSeek (OpenAI-compatible) API with:
- Standard chat completions (text-only)
- Function calling / tool use (for structured edit operations)
- JSON-mode output (for schema extraction, evaluation, etc.)
- Retry with exponential backoff
"""

from __future__ import annotations

import json
import time
from typing import Any, Optional

from openai import OpenAI
from openai.types.chat import (
    ChatCompletion,
    ChatCompletionMessageParam,
    ChatCompletionToolParam,
)

from src.config import LLMConfig, get_config


class LLMClient:
    """Thin wrapper around DeepSeek's OpenAI-compatible chat API.

    All prompts / tool definitions flow through this single client so
    every module uses consistent auth, base URL, and retry logic.

    Usage::

        client = LLMClient()
        reply = client.chat("Hello!")
        tools = client.chat_with_tools(messages, tool_defs)
        obj   = client.json_chat(system_prompt, user_prompt, output_schema)
    """

    def __init__(self, config: Optional[LLMConfig] = None) -> None:
        cfg = config or get_config().llm
        self._model = cfg.model
        self._temperature = cfg.temperature
        self._max_tokens = cfg.max_tokens
        self._timeout = cfg.request_timeout
        self._client = OpenAI(
            api_key=cfg.api_key,
            base_url=cfg.base_url,
            timeout=self._timeout,
        )

    # ── Low-level completion ────────────────────────────────────────────

    def _complete(
        self,
        messages: list[ChatCompletionMessageParam],
        *,
        tools: Optional[list[ChatCompletionToolParam]] = None,
        tool_choice: Optional[str | dict[str, Any]] = None,
        response_format: Optional[dict[str, str]] = None,
        max_retries: int = 3,
    ) -> ChatCompletion:
        """Send a chat completion request with retry logic.

        Args:
            messages: Conversation messages.
            tools: Optional tool definitions for function calling.
            tool_choice: How the model should pick tools ("auto", "required", etc.).
            response_format: Pass ``{"type": "json_object"}`` for JSON mode.
            max_retries: Number of retries on transient errors.

        Returns:
            The raw ChatCompletion object from the API.

        Raises:
            RuntimeError: If all retries are exhausted.
        """
        last_error: Optional[Exception] = None
        for attempt in range(max_retries):
            try:
                kwargs: dict[str, Any] = {
                    "model": self._model,
                    "messages": messages,
                    "temperature": self._temperature,
                    "max_tokens": self._max_tokens,
                }
                if tools:
                    kwargs["tools"] = tools
                    kwargs["tool_choice"] = tool_choice or "auto"
                if response_format:
                    kwargs["response_format"] = response_format

                return self._client.chat.completions.create(**kwargs)

            except Exception as exc:
                last_error = exc
                if attempt < max_retries - 1:
                    wait = 2 ** attempt
                    time.sleep(wait)
                else:
                    raise RuntimeError(
                        f"LLM call failed after {max_retries} attempts: {exc}"
                    ) from last_error

        # Unreachable — satisfy type checker
        raise RuntimeError(f"LLM call failed: {last_error}")

    # ── Public API ──────────────────────────────────────────────────────

    def chat(self, prompt: str, *, system: Optional[str] = None) -> str:
        """Simple text-in, text-out chat.

        Args:
            prompt: The user message.
            system: Optional system-level instruction.

        Returns:
            The model's text reply.
        """
        messages: list[ChatCompletionMessageParam] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        response = self._complete(messages)
        return response.choices[0].message.content or ""

    def chat_with_tools(
        self,
        messages: list[ChatCompletionMessageParam],
        tools: list[ChatCompletionToolParam],
        *,
        tool_choice: Optional[str] = None,
    ) -> ChatCompletion:
        """Chat completion with function-calling / tool-use support.

        Args:
            messages: Full conversation (can include prior assistant tool_calls).
            tools: Tool definitions (OpenAI function-calling format).
            tool_choice: "auto", "required", "none", or a specific tool dict.

        Returns:
            The completion, possibly containing ``tool_calls``.
        """
        return self._complete(messages, tools=tools, tool_choice=tool_choice)

    def json_chat(
        self,
        prompt: str,
        *,
        system: Optional[str] = None,
        output_schema: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Chat with structured JSON output (JSON mode).

        Args:
            prompt: The user message.
            system: Optional system instruction.
            output_schema: Optional JSON schema to describe in the system prompt.
                           (DeepSeek does not support ``response_format.json_schema``
                           the same way as GPT-4; we inject the schema into the prompt).

        Returns:
            Parsed JSON object.
        """
        full_system = system or "You are a helpful assistant. Always output valid JSON."
        if output_schema:
            full_system += (
                "\n\nYou MUST respond with a single JSON object that matches "
                "the following schema:\n" + json.dumps(output_schema, indent=2)
                + "\nDo NOT include markdown code fences or any other text."
            )

        messages: list[ChatCompletionMessageParam] = [
            {"role": "system", "content": full_system},
            {"role": "user", "content": prompt},
        ]
        response = self._complete(messages, response_format={"type": "json_object"})
        raw = response.choices[0].message.content or "{}"
        # Strip possible markdown fences
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[-1]
            if raw.endswith("```"):
                raw = raw[:-3]
        return json.loads(raw)

def get_llm_client() -> LLMClient:
    """Return a shared LLMClient using the global config."""
    return LLMClient()

