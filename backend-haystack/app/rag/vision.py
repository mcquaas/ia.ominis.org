"""
Vision analysis using Haystack's OllamaChatGenerator with ImageContent,
or optional Qwen2.5-VL (OpenAI-compatible) when QWEN_VL_API_URL is set.
"""

import asyncio
import base64
import logging
import os
from typing import Optional

import httpx
from haystack.dataclasses import ChatMessage, ImageContent

from app.config import get_settings

logger = logging.getLogger(__name__)


async def _analyze_image_qwen_vl(
    image_b64: str,
    question: str,
    mime_type: str,
    *,
    vr=None,
) -> str:
    """Call Qwen2.5-VL or OpenAI-compatible multimodal for image analysis."""
    from app.admin.vision_runtime import VisionRuntimeSettings

    settings = get_settings()
    vk = (getattr(settings, "vast_api_key", None) or os.environ.get("VAST_API_KEY", "") or "").strip()
    v_ep = (getattr(settings, "vast_serverless_qwen_vl_endpoint", None) or "").strip()
    if vr is not None and isinstance(vr, VisionRuntimeSettings):
        v_ep = vr.vast_qwen_endpoint or v_ep
        vk = vr.vast_api_key or vk
    if v_ep and vk:
        from app.vast_serverless.generators import openai_chat_completion_sync

        model = (
            (vr.qwen_vl_model if vr is not None else None)
            or getattr(settings, "qwen_vl_model", "qwen2.5-vl")
            or "qwen2.5-vl"
        )
        timeout = (
            vr.qwen_vl_timeout
            if vr is not None and getattr(vr, "qwen_vl_timeout", None)
            else (getattr(settings, "qwen_vl_timeout", 60) or 60)
        )
        oc = int(getattr(settings, "vast_serverless_qwen_vl_cost", 0) or 0)
        dc = int(getattr(settings, "vast_serverless_default_cost", 500) or 500)
        cost = oc if oc > 0 else dc
        prompt = (
            f"Analiza esta imagen. Pregunta del usuario: {question}. Describe en detalle, transcribe texto si hay. Responde en español."
            if question
            else "Describe esta imagen en detalle. Si hay texto, transcríbelo. Responde en español."
        )
        body = {
            "model": model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{image_b64}"}},
                    ],
                }
            ],
            "max_tokens": 1024,
        }

        def _sync_call() -> dict:
            return openai_chat_completion_sync(
                api_key=vk,
                endpoint_name=v_ep,
                body=body,
                cost=cost,
                request_timeout=float(timeout),
                worker_timeout=max(float(timeout), 300.0),
            )

        loop = asyncio.get_event_loop()
        data = await loop.run_in_executor(None, _sync_call)
        choice = (data.get("choices") or [{}])[0]
        text = (choice.get("message") or {}).get("content", "")
        return (text or "").strip()

    url = (getattr(settings, "qwen_vl_api_url", None) or "").rstrip("/")
    if vr is not None and getattr(vr, "qwen_vl_api_url", None):
        url = (vr.qwen_vl_api_url or "").rstrip("/")
    if not url.endswith("/v1"):
        url = f"{url}/v1" if url else ""
    if not url:
        return ""
    endpoint = f"{url}/chat/completions"
    model = getattr(settings, "qwen_vl_model", "qwen2.5-vl") or "qwen2.5-vl"
    if vr is not None and getattr(vr, "qwen_vl_model", None):
        model = vr.qwen_vl_model or model
    timeout = getattr(settings, "qwen_vl_timeout", 60) or 60
    if vr is not None:
        timeout = vr.qwen_vl_timeout or timeout
    api_key = (getattr(settings, "openai_api_key", None) or os.environ.get("OPENAI_API_KEY", "") or "").strip()
    if vr is not None and getattr(vr, "qwen_api_key", None):
        api_key = (vr.qwen_api_key or "").strip() or api_key
    prompt = (
        f"Analiza esta imagen. Pregunta del usuario: {question}. Describe en detalle, transcribe texto si hay. Responde en español."
        if question
        else "Describe esta imagen en detalle. Si hay texto, transcríbelo. Responde en español."
    )
    body = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{image_b64}"}},
                ],
            }
        ],
        "max_tokens": 1024,
    }
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(endpoint, json=body, headers=headers)
        resp.raise_for_status()
        data = resp.json()
    choice = (data.get("choices") or [{}])[0]
    text = (choice.get("message") or {}).get("content", "")
    return (text or "").strip()


def _guess_mime_type(b64: str) -> str:
    """Guess MIME type from base64 image header bytes."""
    try:
        header = base64.b64decode(b64[:32])
        if header[:8] == b'\x89PNG\r\n\x1a\n':
            return "image/png"
        if header[:2] == b'\xff\xd8':
            return "image/jpeg"
        if header[:4] == b'GIF8':
            return "image/gif"
        if header[:4] == b'RIFF' and header[8:12] == b'WEBP':
            return "image/webp"
    except Exception:
        pass
    return "image/png"  # default fallback


async def _analyze_image_ollama_rest(
    image_b64: str,
    question: str,
    mime_type: str,
    *,
    ollama_url: str,
    model: str,
    api_key: str,
    timeout: float,
) -> str:
    """Ollama /api/chat with optional Bearer auth (proxied deployments)."""
    base = ollama_url.rstrip("/")
    prompt = (
        f"Analiza esta imagen. Pregunta del usuario: {question}. Describe en detalle, transcribe texto si hay. Responde en español."
        if question
        else "Describe esta imagen en detalle. Si hay texto, transcríbelo. Responde en español."
    )
    body = {
        "model": model,
        "messages": [{"role": "user", "content": prompt, "images": [image_b64]}],
        "stream": False,
    }
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    async with httpx.AsyncClient(timeout=timeout) as client:
        r = await client.post(f"{base}/api/chat", json=body, headers=headers)
        r.raise_for_status()
        data = r.json()
    msg = (data.get("message") or {}) if isinstance(data, dict) else {}
    text = msg.get("content") or data.get("response") or ""
    return (text or "").strip()


async def analyze_image(
    image_b64: str,
    question: str = "",
    vision_generator=None,
) -> str:
    """
    Analyze an image using the Haystack OllamaChatGenerator with ImageContent.

    Args:
        image_b64: Base64-encoded image (may include data URI prefix)
        question: The user's question for context
        vision_generator: An OllamaChatGenerator instance configured with a vision model

    Returns:
        A text description/analysis of the image in Spanish.
    """
    from app.admin.vision_runtime import get_vision_runtime_settings, vision_prefers_openai_multimodal

    settings = get_settings()
    vr = get_vision_runtime_settings()

    if vision_prefers_openai_multimodal(vr):
        if image_b64.startswith("data:"):
            parts = image_b64.split(",", 1)
            mime_type = "image/png"
            if len(parts) == 2:
                if "/" in parts[0]:
                    mime_type = parts[0].split(":")[1].split(";")[0]
                image_b64 = parts[1]
        else:
            mime_type = _guess_mime_type(image_b64)
        return await _analyze_image_qwen_vl(image_b64, question, mime_type, vr=vr)

    if vr.use_ollama_vision and vr.ollama_api_key and vr.ollama_url and vr.vision_model:
        if image_b64.startswith("data:"):
            parts = image_b64.split(",", 1)
            mime_type = "image/png"
            if len(parts) == 2:
                if "/" in parts[0]:
                    mime_type = parts[0].split(":")[1].split(";")[0]
                image_b64 = parts[1]
        else:
            mime_type = _guess_mime_type(image_b64)
        return await _analyze_image_ollama_rest(
            image_b64,
            question,
            mime_type,
            ollama_url=vr.ollama_url,
            model=vr.vision_model,
            api_key=vr.ollama_api_key,
            timeout=float(getattr(settings, "ollama_timeout", 90) or 90),
        )

    if vision_generator is None:
        logger.warning("No vision generator available; skipping image analysis.")
        return ""

    # Strip data URI prefix if present (e.g., "data:image/png;base64,...")
    mime_type = "image/png"
    if image_b64.startswith("data:"):
        # Extract MIME type from the data URI
        header_part = image_b64.split(",", 1)
        if len(header_part) == 2:
            mime_info = header_part[0]  # e.g., "data:image/jpeg;base64"
            if "/" in mime_info:
                mime_type = mime_info.split(":")[1].split(";")[0]
            image_b64 = header_part[1]
    else:
        mime_type = _guess_mime_type(image_b64)

    # Build the prompt
    if question:
        prompt_text = (
            f"Analiza esta imagen en el contexto de la siguiente pregunta: "
            f"\"{question}\"\n\n"
            f"Describe lo que ves de forma detallada y relevante. "
            f"Responde en español."
        )
    else:
        prompt_text = (
            "Describe esta imagen de forma detallada. "
            "Si contiene texto, transcríbelo. "
            "Si contiene datos médicos, gráficos o tablas, describe su contenido. "
            "Responde en español."
        )

    try:
        # Build ChatMessage with ImageContent (Haystack 2.23 native multimodal)
        image_content = ImageContent(
            base64_image=image_b64,
            mime_type=mime_type,
            validation=False,  # Skip validation for speed
        )

        user_message = ChatMessage.from_user(
            content_parts=[prompt_text, image_content]
        )

        # Run the vision generator in a thread executor (it's synchronous)
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: vision_generator.run(messages=[user_message]),
        )

        replies = result.get("replies", [])
        if replies:
            description = replies[0].text or ""
            logger.info(f"Vision analysis completed: {len(description)} chars")
            return description.strip()

        logger.warning("Vision generator returned no replies")
        return "(No se pudo analizar la imagen)"

    except Exception as e:
        logger.error(f"Vision analysis error: {e}", exc_info=True)
        return f"(Error al analizar la imagen: {str(e)[:100]})"
