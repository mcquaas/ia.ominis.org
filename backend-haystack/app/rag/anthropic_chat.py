"""Minimal Anthropic Messages API chat generator (Haystack-compatible run() shape)."""

from __future__ import annotations

import logging
from typing import Any

from haystack.dataclasses import ChatMessage

logger = logging.getLogger(__name__)


class AnthropicChatGenerator:
    """Claude via Anthropic SDK (not OpenAI-compatible)."""

    def __init__(
        self,
        *,
        model: str,
        api_key: str,
        timeout: float = 120.0,
        generation_kwargs: dict[str, Any] | None = None,
    ):
        self.model = model
        self.api_key = api_key
        self.timeout = timeout
        self.generation_kwargs = generation_kwargs or {}

    def run(
        self,
        messages: list[ChatMessage],
        streaming_callback: Any = None,
        generation_kwargs: dict[str, Any] | None = None,
        **_: Any,
    ) -> dict[str, list[ChatMessage]]:
        import anthropic

        merged = {**self.generation_kwargs, **(generation_kwargs or {})}
        client = anthropic.Anthropic(api_key=self.api_key, timeout=self.timeout)

        from haystack.dataclasses.chat_message import ChatRole

        system_parts: list[str] = []
        api_messages: list[dict[str, Any]] = []
        for m in messages:
            text = (m.text or "").strip()
            role = m.role
            if role == ChatRole.SYSTEM:
                system_parts.append(text)
            elif role == ChatRole.USER:
                api_messages.append({"role": "user", "content": text})
            elif role == ChatRole.ASSISTANT:
                api_messages.append({"role": "assistant", "content": text})

        system = "\n".join(system_parts).strip() or None
        max_tokens = int(merged.get("max_tokens") or merged.get("num_predict") or 2048)
        temperature = float(merged.get("temperature", 0.3))

        resp = client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system,
            messages=api_messages,
        )
        out_text = ""
        for block in resp.content:
            if hasattr(block, "text"):
                out_text += block.text
        reply = ChatMessage.from_assistant(out_text)
        if streaming_callback is not None:
            from haystack.dataclasses.streaming_chunk import StreamingChunk

            streaming_callback(StreamingChunk(content=out_text, meta={}, finish_reason="stop"))
        return {"replies": [reply]}
