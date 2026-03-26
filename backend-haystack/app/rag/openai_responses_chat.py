"""
OpenAI Responses API (/v1/responses) for models that reject /v1/chat/completions
(e.g. gpt-5.4 on api.openai.com with certain account/routing behavior).

Haystack-compatible .run(messages=..., streaming_callback=..., generation_kwargs=...).
"""

from __future__ import annotations

import json
import logging
from typing import Any, Callable, Optional

import httpx
from haystack.dataclasses import ChatMessage, StreamingChunk

logger = logging.getLogger(__name__)


def _normalize_openai_v1_base(api_base_url: str) -> str:
    b = (api_base_url or "").rstrip("/")
    if not b.endswith("/v1"):
        b = f"{b}/v1"
    return b


def _chat_messages_to_responses_input(messages: list[ChatMessage]) -> list[dict[str, Any]]:
    """Map Haystack ChatMessage list to Responses API input items (role + content)."""
    items: list[dict[str, Any]] = []
    for m in messages:
        role_raw = m.role.value if hasattr(m.role, "value") else str(m.role)
        r = (role_raw or "user").lower()
        if r == "system":
            api_role = "system"
        elif r == "assistant":
            api_role = "assistant"
        else:
            api_role = "user"
        # Haystack >=2.23 removed direct `.content` in favor of `.text`.
        content = getattr(m, "text", None)
        if content is None:
            content = getattr(m, "content", None)
        if isinstance(content, list):
            texts: list[str] = []
            for part in content:
                if isinstance(part, dict):
                    if part.get("type") == "text":
                        texts.append(str(part.get("text", "")))
                    else:
                        texts.append(str(part))
                else:
                    texts.append(str(part))
            content = "\n".join(texts)
        elif content is None:
            content = ""
        else:
            content = str(content)
        items.append({"role": api_role, "content": content})
    return items


def _max_output_from_generation_kwargs(generation_kwargs: dict[str, Any] | None, default: int = 2048) -> int:
    if not generation_kwargs:
        return min(max(default, 1), 128_000)
    for k in ("max_completion_tokens", "max_tokens", "max_output_tokens"):
        v = generation_kwargs.get(k)
        if v is not None:
            try:
                return min(max(int(v), 1), 128_000)
            except (TypeError, ValueError):
                break
    return min(max(default, 1), 128_000)


def _extract_output_text(data: dict[str, Any]) -> str:
    ot = data.get("output_text")
    if isinstance(ot, str) and ot.strip():
        return ot
    chunks: list[str] = []
    for item in data.get("output") or []:
        if not isinstance(item, dict) or item.get("type") != "message":
            continue
        for c in item.get("content") or []:
            if not isinstance(c, dict):
                continue
            if c.get("type") == "output_text" and c.get("text"):
                chunks.append(str(c["text"]))
    return "".join(chunks)


def _is_reasoning_model(model: str) -> bool:
    m = (model or "").strip().lower()
    return m.startswith("gpt-5") or m.startswith(("o1", "o3", "o4"))


class OpenAIResponsesChatGenerator:
    """
    POST /v1/responses with JSON body; returns Haystack-shaped {"replies": [...]}.
    """

    def __init__(
        self,
        model: str,
        api_key: str,
        api_base_url: str,
        timeout: float = 120.0,
        default_generation_kwargs: dict[str, Any] | None = None,
    ):
        self.model = model
        self.api_key = (api_key or "").strip()
        self.api_base_url = _normalize_openai_v1_base(api_base_url)
        self.timeout = float(timeout)
        self._default_generation_kwargs = default_generation_kwargs or {}

    def run(
        self,
        messages: list[ChatMessage],
        streaming_callback: Optional[Callable[[StreamingChunk], None]] = None,
        generation_kwargs: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        merged = {**self._default_generation_kwargs, **(generation_kwargs or {})}
        max_out = _max_output_from_generation_kwargs(merged, 2048)
        payload: dict[str, Any] = {
            "model": self.model,
            "input": _chat_messages_to_responses_input(messages),
            "max_output_tokens": max_out,
        }
        # GPT-5/o-series can spend excessive pre-token latency on hidden reasoning.
        # Keep effort as low as supported by the model unless explicitly overridden.
        if _is_reasoning_model(self.model) and "reasoning" not in merged:
            # gpt-5.4 currently accepts: medium | high | very_high
            payload["reasoning"] = {"effort": "medium"}
        url = f"{self.api_base_url}/responses"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        if streaming_callback is None:
            with httpx.Client(timeout=self.timeout) as client:
                r = client.post(url, json=payload, headers=headers)
                if r.status_code >= 400:
                    raise RuntimeError(f"Error code: {r.status_code} - {r.text[:4000]}")
                data = r.json()
            err = data.get("error")
            if err:
                raise RuntimeError(f"Error code: {r.status_code} - {err!r}")
            text = _extract_output_text(data)
            return {"replies": [ChatMessage.from_assistant(text)]}

        payload["stream"] = True
        assembled: list[str] = []
        with httpx.Client(timeout=self.timeout) as client:
            with client.stream("POST", url, json=payload, headers=headers) as r:
                if r.status_code >= 400:
                    body = r.read().decode("utf-8", errors="replace")
                    raise RuntimeError(f"Error code: {r.status_code} - {body[:4000]}")
                for line in r.iter_lines():
                    if not line:
                        continue
                    if line.startswith("data: "):
                        raw = line[6:].strip()
                        if raw == "[DONE]":
                            break
                        try:
                            ev = json.loads(raw)
                        except json.JSONDecodeError:
                            continue
                        if ev.get("type") == "response.output_text.delta":
                            delta = ev.get("delta") or ""
                            if delta:
                                assembled.append(delta)
                                streaming_callback(
                                    StreamingChunk(content=delta, meta={}, finish_reason=None)
                                )
        text = "".join(assembled)
        return {"replies": [ChatMessage.from_assistant(text)]}
