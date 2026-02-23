"""
LiveAvatar integration — OpenAI-compatible proxy for Pipecat/HeyGen.

- POST /v1/liveavatar/chat/completions: OpenAI proxy for Pipecat + Ominis Med (clinical LLM)
- POST /v1/liveavatar/session: Create HeyGen session (FULL mode) for /live page
"""

import json
import logging
import os
import time
import uuid
from typing import Optional
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, Body, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.config import get_settings

logger = logging.getLogger(__name__)
router = APIRouter(tags=["liveavatar"])


class OpenAIMessage(BaseModel):
    role: str
    content: str


class LiveAvatarSessionRequest(BaseModel):
    """Request body for session creation."""
    mode: Optional[str] = None  # "heygen" = HeyGen FULL only; "pipecat" or None = try Pipecat first


class LiveAvatarChatRequest(BaseModel):
    """OpenAI-compatible chat request for Pipecat."""
    messages: list[OpenAIMessage]
    model: Optional[str] = "ominis-2.0-clinic"  # Ignored; we always use clinic
    stream: bool = True
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None


class OpenAIChatCompletionsRequest(BaseModel):
    """OpenAI /chat/completions request for LibreChat / custom clients."""
    messages: list[dict]  # [{ "role": "user"|"assistant"|"system", "content": "..." }]
    model: Optional[str] = "ominis-2.0"
    stream: bool = True
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    # Ominis RAG and search (optional; when true, query-stream uses our RAG/web/pubmed/openscholar)
    rag_search: bool = True
    web_search: bool = False
    pubmed_search: bool = False
    openscholar_search: bool = False


def _messages_to_question_and_history(messages: list[dict]) -> tuple[str, list[dict]]:
    """Extract question (last user message) and history from OpenAI messages."""
    history: list[dict] = []
    question = ""
    system_prefix = ""
    for msg in messages:
        role = (msg.get("role") or "").strip().lower()
        content = (msg.get("content") or "").strip()
        if not content:
            continue
        if role == "system":
            system_prefix = f"[Contexto: {content[:500]}]\n\n" if content else ""
        elif role == "user":
            if question:
                history.append({"role": "user", "content": question})
            question = content
        elif role == "assistant":
            history.append({"role": "assistant", "content": content})
    if system_prefix and question:
        question = system_prefix + question
    if not question:
        question = "Hola"
    return question, history


def _openai_chunk(content: str, finish_reason: Optional[str] = None) -> str:
    """Format a single chunk in OpenAI SSE format."""
    chunk = {
        "id": f"chatcmpl-{uuid.uuid4().hex[:24]}",
        "object": "chat.completion.chunk",
        "choices": [
            {
                "index": 0,
                "delta": {"content": content} if content else {},
                "finish_reason": finish_reason,
            }
        ],
    }
    return f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"


def _openai_model_to_internal(model: Optional[str]) -> str:
    """Map OpenAI-style or display model names to our internal model_id for query-stream."""
    if not model or not model.strip():
        return "ominis-2.0"
    m = model.strip()
    # Common OpenAI names -> our default
    if m in ("gpt-3.5-turbo", "gpt-4", "gpt-4o"):
        return "ominis-2.0"
    # Pass through known public IDs (backend will resolve)
    return m


async def _stream_from_query(
    base_url: str,
    question: str,
    history: list[dict],
    auth_headers: Optional[dict] = None,
    req_id: str = "",
    model: str = "ominis-2.0-clinic",
    rag_search: bool = False,
    web_search: bool = False,
    pubmed_search: bool = False,
    openscholar_search: bool = False,
) -> str:
    """Stream from /v1/query-stream and yield OpenAI-formatted SSE chunks."""
    internal_model = _openai_model_to_internal(model)
    payload = {
        "question": question,
        "history": [{"role": h["role"], "content": h["content"]} for h in history],
        "model": internal_model,
        "rag_search": rag_search,
        "web_search": web_search,
        "pubmed_search": pubmed_search,
        "openscholar_search": openscholar_search,
    }
    url = f"{base_url.rstrip('/')}/v1/query-stream"
    headers = {"Content-Type": "application/json"}
    if auth_headers:
        headers.update(auth_headers)

    t0 = time.perf_counter()
    first_chunk = True
    chunk_count = 0
    char_count = 0

    async with httpx.AsyncClient(timeout=180.0) as client:
        async with client.stream("POST", url, json=payload, headers=headers) as resp:
            t_first_byte = time.perf_counter()
            logger.info(
                "liveavatar[%s] request_sent resp_status=%s ttfb_backend=%.3fs",
                req_id, resp.status_code, t_first_byte - t0,
            )
            if resp.status_code != 200:
                err = await resp.aread()
                err_msg = err.decode()[:300] if err else str(resp.status_code)
                logger.warning("liveavatar[%s] backend_error status=%s msg=%s", req_id, resp.status_code, err_msg)
                yield _openai_chunk(f"Error {resp.status_code}: {err_msg}")
                yield _openai_chunk("", finish_reason="stop")
                return
            buffer = ""
            sources_from_done: list[dict] = []
            async for chunk in resp.aiter_text():
                buffer += chunk
                while "\n\n" in buffer:
                    line, buffer = buffer.split("\n\n", 1)
                    if line.startswith("data: "):
                        data = line[6:]
                        if data.strip() in ("[DONE]", "[ERROR]"):
                            continue
                        try:
                            evt = json.loads(data)
                            if evt.get("type") == "chunk":
                                text = evt.get("text", "")
                                if text:
                                    if first_chunk:
                                        ttfb = time.perf_counter() - t0
                                        logger.info(
                                            "liveavatar[%s] first_token ttfb=%.3fs text_preview=%s",
                                            req_id, ttfb, repr(text[:60]),
                                        )
                                        first_chunk = False
                                    chunk_count += 1
                                    char_count += len(text)
                                    yield _openai_chunk(text)
                            elif evt.get("type") == "done":
                                sources_from_done = evt.get("sources") or []
                            elif evt.get("type") == "sources":
                                # Optional early sources; keep for done if done has none
                                if not sources_from_done:
                                    sources_from_done = evt.get("sources") or []
                            elif evt.get("type") == "error":
                                logger.warning("liveavatar[%s] chunk_error %s", req_id, evt.get("message", ""))
                                yield _openai_chunk(f"[Error: {evt.get('message', 'Unknown')}]")
                                break
                        except json.JSONDecodeError:
                            pass
            # Append sources as markdown so LibreChat (chat.ominis.org) displays them
            if sources_from_done:
                lines = ["\n\n---\n**Fuentes**\n\n"]
                for i, s in enumerate(sources_from_done):
                    title = (s.get("title") or "Fuente").strip()
                    if title.lower() == "url":
                        try:
                            title = urlparse(s.get("url") or "").netloc or "Enlace"
                        except Exception:
                            title = "Enlace"
                    url = (s.get("url") or "").strip()
                    if url:
                        lines.append(f"[{i + 1}] [{title}]({url})\n")
                if len(lines) > 1:
                    yield _openai_chunk("".join(lines))
            yield _openai_chunk("", finish_reason="stop")
            duration = time.perf_counter() - t0
            logger.info(
                "liveavatar[%s] done duration=%.3fs chunks=%d chars=%d",
                req_id, duration, chunk_count, char_count,
            )


@router.post("/chat/completions")
async def chat_completions(body: OpenAIChatCompletionsRequest, request: Request):
    """
    OpenAI-compatible /chat/completions for LibreChat and other clients.
    Streams from Haystack query-stream; supports model names like ominis-2.0, ominis-2.0-med (Ominis Med).
    Auth: X-API-Key or Authorization header (same as query-stream).
    """
    question, history = _messages_to_question_and_history(body.messages)
    base_url = os.getenv("LIVEAVATAR_QUERY_URL") or str(request.base_url).rstrip("/")
    auth_headers = {}
    if request.headers.get("Authorization"):
        auth_headers["Authorization"] = request.headers["Authorization"]
    if request.headers.get("X-API-Key"):
        auth_headers["X-API-Key"] = request.headers["X-API-Key"]
    req_id = uuid.uuid4().hex[:8]
    model = (body.model or "ominis-2.0").strip()

    async def generate():
        async for chunk in _stream_from_query(
            base_url,
            question,
            history,
            auth_headers,
            req_id,
            model=model,
            rag_search=body.rag_search,
            web_search=body.web_search,
            pubmed_search=body.pubmed_search,
            openscholar_search=body.openscholar_search,
        ):
            yield chunk

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/liveavatar/chat/completions")
async def liveavatar_chat_completions(body: LiveAvatarChatRequest, request: Request):
    """
    OpenAI-compatible streaming endpoint for LiveAvatar + clinical LLM.
    Pipecat's BaseOpenAILLMService can use: base_url + /v1/liveavatar/chat/completions
    Uses BioMistral without RAG for fast TTS (avoids HeyGen websocket timeout).
    """
    question, history = _messages_to_question_and_history([m.model_dump() for m in body.messages])
    base_url = os.getenv("LIVEAVATAR_QUERY_URL") or str(request.base_url).rstrip("/")
    auth_headers = {}
    if request.headers.get("Authorization"):
        auth_headers["Authorization"] = request.headers["Authorization"]
    if request.headers.get("X-API-Key"):
        auth_headers["X-API-Key"] = request.headers["X-API-Key"]
    req_id = uuid.uuid4().hex[:8]
    logger.info(
        "liveavatar[%s] chat request question=%s history_len=%s",
        req_id, question[:80], len(history),
    )

    async def generate():
        async for chunk in _stream_from_query(
            base_url, question, history, auth_headers, req_id, model="ominis-2.0-clinic"
        ):
            yield chunk

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# --- Session endpoint for /live page ---


async def _create_pipecat_session(settings) -> Optional[dict]:
    """Create session via Pipecat Cloud (uses Ominis Med / ominis-2.0-clinic). Returns dict or None."""
    agent = (settings.pipecat_agent_name or "").strip()
    token = (settings.pipecat_api_token or "").strip()
    if not agent or not token:
        return None
    base = (settings.pipecat_api_url or "https://api.pipecat.daily.co/v1/public").rstrip("/")
    url = f"{base}/{agent}/start"
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(
            url,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={
                "createDailyRoom": True,
                "enableDefaultIceServers": True,
                "transport": "daily",
            },
        )
        if resp.status_code != 200:
            logger.warning("Pipecat start failed: %s %s", resp.status_code, resp.text[:200])
            return None
        data = resp.json()
        daily_room = data.get("dailyRoom", "")
        daily_token = data.get("dailyToken", "")
        if not daily_room or not daily_token:
            return None
        # Use our /live/join page to embed Daily with room+token
        from urllib.parse import quote
        base = (settings.live_join_base_url or "https://ia.ominis.org").rstrip("/")
        join_url = f"{base}/live/join?room={quote(daily_room, safe='')}&token={quote(daily_token, safe='')}"
        return {
            "join_url": join_url,
            "daily_room": daily_room,
            "daily_token": daily_token,
            "session_id": data.get("sessionId"),
            "mode": "pipecat",
        }


@router.post("/liveavatar/session")
async def liveavatar_session(body: Optional[LiveAvatarSessionRequest] = Body(None)):
    """
    Create a LiveAvatar session and return join URL for the /live page.
    mode=heygen: use HeyGen FULL (HeyGen LLM) to test basic avatar.
    mode=pipecat or unset: try Pipecat (BioMistral) first, fallback to HeyGen FULL.
    """
    settings = get_settings()
    force_heygen = body and (body.mode or "").strip().lower() == "heygen"

    # Try Pipecat first unless mode=heygen (clinical LLM)
    result = None
    if not force_heygen:
        result = await _create_pipecat_session(settings)
    if result:
        return result

    # Fall back to HeyGen FULL mode
    api_key = (settings.heygen_live_avatar_api_key or "").strip()
    if not api_key:
        raise HTTPException(
            status_code=503,
            detail="LiveAvatar no está configurado. Configure PIPECAT_AGENT_NAME + PIPECAT_API_TOKEN (clínico) o HEYGEN_LIVE_AVATAR_API_KEY (FULL).",
        )
    avatar_id = settings.heygen_live_avatar_avatar_id
    voice_id = settings.heygen_live_avatar_voice_id
    is_sandbox = settings.heygen_live_avatar_sandbox

    # 1. Create session token
    token_payload = {
        "mode": "FULL",
        "avatar_id": avatar_id,
        "avatar_persona": {
            "voice_id": voice_id,
            "language": "es",
            "context": (
                "Eres un asistente de salud de Ominis Health, respaldado por FUNSALUD. "
                "Responde en español de forma clara y breve. No des diagnósticos médicos; "
                "recomienda consultar a un profesional cuando sea apropiado."
            ),
        },
        "is_sandbox": is_sandbox,
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        token_resp = await client.post(
            "https://api.liveavatar.com/v1/sessions/token",
            headers={
                "X-API-KEY": api_key,
                "Content-Type": "application/json",
            },
            json=token_payload,
        )
        if token_resp.status_code != 200:
            err = token_resp.text
            logger.warning("LiveAvatar token failed: %s %s", token_resp.status_code, err[:200])
            raise HTTPException(
                status_code=502,
                detail=f"Error al crear sesión LiveAvatar: {err[:200]}",
            )
        token_data = token_resp.json()
        # Some APIs return { code, data } or { code, message } with 200
        if token_data.get("code") and token_data.get("code") not in (0, 200):
            msg = token_data.get("message") or token_data.get("detail", "")
            logger.warning("LiveAvatar token API error: code=%s %s", token_data.get("code"), msg)
            raise HTTPException(status_code=502, detail=msg or "LiveAvatar rechazó la petición")
        # Support snake_case, camelCase, and nested data
        data = token_data.get("data") or token_data
        session_token = (
            data.get("session_token")
            or data.get("sessionToken")
            or token_data.get("session_token")
            or token_data.get("sessionToken")
        )
        if not session_token:
            err_msg = data.get("message") or data.get("error") or token_data.get("message")
            logger.warning(
                "LiveAvatar token response: keys=%s msg=%s",
                list(token_data.keys()),
                err_msg,
            )
            raise HTTPException(
                status_code=502,
                detail=err_msg or f"LiveAvatar no devolvió session_token. Revisa API key y avatar.",
            )

        # 2. Start session
        start_resp = await client.post(
            "https://api.liveavatar.com/v1/sessions/start",
            headers={
                "Authorization": f"Bearer {session_token}",
                "Content-Type": "application/json",
            },
        )
        if start_resp.status_code != 200:
            err = start_resp.text
            logger.warning("LiveAvatar start failed: %s %s", start_resp.status_code, err[:200])
            raise HTTPException(
                status_code=502,
                detail=f"Error al iniciar sesión LiveAvatar: {err[:200]}",
            )
        start_data = start_resp.json()
        livekit_url = start_data.get("livekit_url") or start_data.get("liveKitUrl", "")
        livekit_token = start_data.get("livekit_client_token") or start_data.get("livekit_token", "")
        if not livekit_url or not livekit_token:
            raise HTTPException(status_code=502, detail="LiveAvatar no devolvió URL de sala")

        join_url = f"https://meet.livekit.io/custom?liveKitUrl={livekit_url}&token={livekit_token}"
        return {
            "session_id": token_data.get("session_id"),
            "session_token": session_token,
            "join_url": join_url,
        }
