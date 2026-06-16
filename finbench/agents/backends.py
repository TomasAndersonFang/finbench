"""LLM backends for the agent loop.

The loop only needs one operation: given the running message history and the tool
schema, return the model's next turn (assistant text plus any tool calls). That
keeps providers swappable.

``OpenAICompatBackend`` targets the OpenAI Chat Completions shape, which is the
de-facto standard: OpenAI, DeepSeek, Groq, Together, Fireworks, OpenRouter, and
local servers (Ollama ``/v1``, vLLM, LM Studio) all speak it. So one backend
covers most models cheaper than a frontier API, including free local ones. Point
it at a provider with ``base_url`` + ``api_key`` + ``model``.

``ScriptedBackend`` returns canned turns for tests, so the loop and the
container plumbing can be exercised with no network or API key.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any, Optional, Protocol


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class AssistantTurn:
    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    raw: Any = None  # provider-native assistant message, for replay


class Backend(Protocol):
    def chat(self, messages: list[dict], tools: list[dict]) -> AssistantTurn: ...

    def assistant_message(self, turn: AssistantTurn) -> dict:
        """Provider-native assistant message to append to history before tool results."""
        ...


class OpenAICompatBackend:
    """Any OpenAI Chat Completions-compatible endpoint."""

    def __init__(
        self,
        model: str,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: int = 4096,
    ):
        from openai import OpenAI

        # Local servers (Ollama/vLLM) accept any non-empty key.
        self.client = OpenAI(base_url=base_url, api_key=api_key or "not-needed")
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens

    def chat(self, messages: list[dict], tools: list[dict]) -> AssistantTurn:
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "tools": tools,
            "max_tokens": self.max_tokens,
        }
        if self.temperature is not None:
            kwargs["temperature"] = self.temperature
        resp = self.client.chat.completions.create(**kwargs)
        msg = resp.choices[0].message
        calls: list[ToolCall] = []
        for tc in msg.tool_calls or []:
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            calls.append(ToolCall(id=tc.id, name=tc.function.name, arguments=args))
        return AssistantTurn(text=msg.content or "", tool_calls=calls, raw=msg)

    def assistant_message(self, turn: AssistantTurn) -> dict:
        # Reconstruct the OpenAI assistant message (model_dump on the raw object
        # would also work, but we rebuild to stay independent of SDK internals).
        out: dict[str, Any] = {"role": "assistant", "content": turn.text or ""}
        if turn.tool_calls:
            out["tool_calls"] = [
                {
                    "id": c.id,
                    "type": "function",
                    "function": {"name": c.name, "arguments": json.dumps(c.arguments)},
                }
                for c in turn.tool_calls
            ]
        return out


@dataclass
class ScriptedBackend:
    """Return queued turns in order; for tests (no network)."""

    turns: list[AssistantTurn]
    _i: int = 0

    def chat(self, messages: list[dict], tools: list[dict]) -> AssistantTurn:
        if self._i >= len(self.turns):
            return AssistantTurn(text="done")
        turn = self.turns[self._i]
        self._i += 1
        return turn

    def assistant_message(self, turn: AssistantTurn) -> dict:
        out: dict[str, Any] = {"role": "assistant", "content": turn.text or ""}
        if turn.tool_calls:
            out["tool_calls"] = [
                {
                    "id": c.id,
                    "type": "function",
                    "function": {"name": c.name, "arguments": json.dumps(c.arguments)},
                }
                for c in turn.tool_calls
            ]
        return out


# Defaults: a HuggingFace-style repo id served by a local vLLM server. vLLM
# exposes an OpenAI-compatible API at /v1 and accepts any api key. Override with
# FINBENCH_MODEL / FINBENCH_BASE_URL for another model or a hosted provider.
DEFAULT_MODEL = "Qwen/Qwen3.6-35B-A3B"
DEFAULT_BASE_URL = "http://localhost:8000/v1"  # vLLM default


def backend_from_env() -> OpenAICompatBackend:
    """Build a backend from FINBENCH_* env vars (all optional).

    FINBENCH_MODEL     model id (default: DEFAULT_MODEL)
    FINBENCH_BASE_URL  endpoint (default: local vLLM at DEFAULT_BASE_URL)
    FINBENCH_API_KEY   provider key (any value for vLLM/local servers)
    """
    return OpenAICompatBackend(
        model=os.environ.get("FINBENCH_MODEL") or DEFAULT_MODEL,
        base_url=os.environ.get("FINBENCH_BASE_URL") or DEFAULT_BASE_URL,
        api_key=os.environ.get("FINBENCH_API_KEY") or "EMPTY",
    )
