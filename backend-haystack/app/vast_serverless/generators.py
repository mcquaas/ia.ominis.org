"""
Haystack-compatible generators that call Vast Serverless (vastai SDK: route → worker → inference).
"""

from __future__ import annotations

import logging
from typing import Any

from haystack.dataclasses import ChatMessage

from app.vast_serverless.runner import submit

logger = logging.getLogger(__name__)

_sl_singleton: Any = None
_sl_key: str | None = None


def _get_serverless(api_key: str):
    global _sl_singleton, _sl_key
    if _sl_singleton is None or _sl_key != api_key:
        from vastai import Serverless

        _sl_singleton = None
        _sl_key = api_key
        _sl_singleton = Serverless(api_key=api_key)
    return _sl_singleton


async def _ensure_session(client) -> None:
    await client._get_session()


async def _openai_chat_async(
    *,
    api_key: str,
    endpoint_name: str,
    model: str,
    messages: list[ChatMessage],
    generation_kwargs: dict[str, Any],
    cost: int,
    request_timeout: float | None,
    worker_timeout: float,
) -> dict[str, Any]:
    client = _get_serverless(api_key)
    await _ensure_session(client)
    ep = await client.get_endpoint(name=endpoint_name)
    openai_messages = [m.to_openai_dict_format() for m in messages]
    base = {"model": model, "messages": openai_messages, **generation_kwargs}
    # Haystack/OpenAI: max_tokens vs max_completion_tokens for newer APIs
    sr = ep.request(
        "/v1/chat/completions",
        base,
        cost=cost,
        timeout=request_timeout,
        worker_timeout=worker_timeout,
        retry=True,
    )
    result = await sr
    if not result.get("ok"):
        err = result.get("response") or result.get("text") or result
        raise RuntimeError(f"Vast Serverless chat failed: {err!r}")
    return result


async def _ollama_chat_async(
    *,
    api_key: str,
    endpoint_name: str,
    model: str,
    messages: list[ChatMessage],
    generation_kwargs: dict[str, Any],
    cost: int,
    request_timeout: float | None,
    worker_timeout: float,
) -> dict[str, Any]:
    from haystack_integrations.components.generators.ollama.chat.chat_generator import (
        _convert_chatmessage_to_ollama_format,
    )

    client = _get_serverless(api_key)
    await _ensure_session(client)
    ep = await client.get_endpoint(name=endpoint_name)
    ollama_messages = [_convert_chatmessage_to_ollama_format(m) for m in messages]
    opts: dict[str, Any] = {}
    for k in ("temperature", "top_p", "num_predict", "num_ctx", "num_gpu"):
        if k in generation_kwargs:
            opts[k] = generation_kwargs[k]
    payload: dict[str, Any] = {
        "model": model,
        "messages": ollama_messages,
        "stream": False,
    }
    if opts:
        payload["options"] = opts
    sr = ep.request(
        "/api/chat",
        payload,
        cost=cost,
        timeout=request_timeout,
        worker_timeout=worker_timeout,
        retry=True,
    )
    result = await sr
    if not result.get("ok"):
        err = result.get("response") or result.get("text") or result
        raise RuntimeError(f"Vast Serverless Ollama chat failed: {err!r}")
    return result


def _replies_from_openai_worker_response(data: Any) -> list[ChatMessage]:
    if isinstance(data, dict) and "choices" in data:
        return _replies_from_openai_json(data)
    if isinstance(data, dict) and isinstance(data.get("response"), dict) and "choices" in data["response"]:
        return _replies_from_openai_json(data["response"])
    raise RuntimeError(f"Unexpected OpenAI worker response shape: {type(data)!r}")


def _replies_from_openai_json(data: dict) -> list[ChatMessage]:
    choice = (data.get("choices") or [{}])[0]
    msg = choice.get("message") or {}
    text = msg.get("content") or ""
    meta = {
        "model": data.get("model"),
        "finish_reason": choice.get("finish_reason"),
        "usage": data.get("usage"),
    }
    return [ChatMessage.from_assistant(text=text, meta=meta)]


def _replies_from_ollama_worker_response(data: Any) -> list[ChatMessage]:
    from haystack_integrations.components.generators.ollama.chat.chat_generator import (
        _convert_ollama_meta_to_openai_format,
    )

    if not isinstance(data, dict):
        raise RuntimeError(f"Unexpected Ollama worker response: {type(data)!r}")
    if "message" in data:
        body = data
    elif isinstance(data.get("response"), dict) and "message" in data["response"]:
        body = data["response"]
    else:
        body = data
    msg = (body.get("message") or {})
    text = msg.get("content") or ""
    meta = _convert_ollama_meta_to_openai_format({k: v for k, v in body.items() if k != "message"})
    return [ChatMessage.from_assistant(text=text, meta=meta)]


class ServerlessOpenAIChatGenerator:
    """OpenAI-compatible chat via Vast Serverless (vLLM PyWorker)."""

    def __init__(
        self,
        *,
        endpoint_name: str,
        model: str,
        api_key: str,
        cost: int = 500,
        timeout: float = 120.0,
        worker_timeout: float = 600.0,
        generation_kwargs: dict[str, Any] | None = None,
    ):
        self.endpoint_name = endpoint_name
        self.model = model
        self.api_key = api_key
        self.cost = cost
        self.timeout = timeout
        self.worker_timeout = worker_timeout
        self.generation_kwargs = generation_kwargs or {}

    def run(
        self,
        messages: list[ChatMessage],
        streaming_callback: Any = None,
        generation_kwargs: dict[str, Any] | None = None,
        **_: Any,
    ) -> dict[str, list[ChatMessage]]:
        merged = {**self.generation_kwargs, **(generation_kwargs or {})}
        submit_timeout = max(self.worker_timeout + 180.0, self.timeout + 120.0, 900.0)
        result = submit(
            _openai_chat_async(
                api_key=self.api_key,
                endpoint_name=self.endpoint_name,
                model=self.model,
                messages=messages,
                generation_kwargs=merged,
                cost=self.cost,
                request_timeout=self.timeout,
                worker_timeout=self.worker_timeout,
            ),
            timeout=submit_timeout,
        )
        inner = result.get("response")
        replies = _replies_from_openai_worker_response(inner)
        if streaming_callback is not None:
            from haystack.dataclasses.streaming_chunk import StreamingChunk

            for r in replies:
                txt = r.text or ""
                if txt:
                    streaming_callback(
                        StreamingChunk(content=txt, meta=r.meta or {}, finish_reason="stop")
                    )
        return {"replies": replies}


class ServerlessOllamaChatGenerator:
    """Ollama /api/chat via Vast Serverless."""

    def __init__(
        self,
        *,
        endpoint_name: str,
        model: str,
        api_key: str,
        cost: int = 500,
        timeout: float = 120.0,
        worker_timeout: float = 600.0,
        generation_kwargs: dict[str, Any] | None = None,
    ):
        self.endpoint_name = endpoint_name
        self.model = model
        self.api_key = api_key
        self.cost = cost
        self.timeout = timeout
        self.worker_timeout = worker_timeout
        self.generation_kwargs = generation_kwargs or {}

    def run(
        self,
        messages: list[ChatMessage],
        streaming_callback: Any = None,
        generation_kwargs: dict[str, Any] | None = None,
        **_: Any,
    ) -> dict[str, list[ChatMessage]]:
        merged = {**self.generation_kwargs, **(generation_kwargs or {})}
        submit_timeout = max(self.worker_timeout + 180.0, self.timeout + 120.0, 900.0)
        result = submit(
            _ollama_chat_async(
                api_key=self.api_key,
                endpoint_name=self.endpoint_name,
                model=self.model,
                messages=messages,
                generation_kwargs=merged,
                cost=self.cost,
                request_timeout=self.timeout,
                worker_timeout=self.worker_timeout,
            ),
            timeout=submit_timeout,
        )
        inner = result.get("response")
        replies = _replies_from_ollama_worker_response(inner)
        if streaming_callback is not None:
            from haystack.dataclasses.streaming_chunk import StreamingChunk

            for r in replies:
                txt = r.text or ""
                if txt:
                    streaming_callback(
                        StreamingChunk(content=txt, meta=r.meta or {}, finish_reason="stop")
                    )
        return {"replies": replies}


def openai_chat_completion_sync(
    *,
    api_key: str,
    endpoint_name: str,
    body: dict[str, Any],
    cost: int,
    request_timeout: float | None,
    worker_timeout: float,
) -> dict[str, Any]:
    """Sync API for callers on any thread; runs the vastai SDK on the dedicated loop."""

    async def _once() -> dict[str, Any]:
        client = _get_serverless(api_key)
        await _ensure_session(client)
        ep = await client.get_endpoint(name=endpoint_name)
        sr = ep.request(
            "/v1/chat/completions",
            body,
            cost=cost,
            timeout=request_timeout,
            worker_timeout=worker_timeout,
            retry=True,
        )
        result = await sr
        if not result.get("ok"):
            err = result.get("response") or result.get("text") or result
            raise RuntimeError(f"Vast Serverless request failed: {err!r}")
        inner = result.get("response")
        if isinstance(inner, dict):
            return inner
        raise RuntimeError(f"Unexpected serverless response: {type(inner)!r}")

    rt = float(request_timeout or 900.0)
    return submit(_once(), timeout=max(rt + 120.0, 900.0))
