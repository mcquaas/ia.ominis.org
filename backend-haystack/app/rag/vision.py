"""
Vision analysis using Haystack's OllamaChatGenerator with ImageContent,
or optional Qwen2.5-VL (OpenAI-compatible) when QWEN_VL_API_URL is set.
"""

import asyncio
import base64
import logging
from typing import Optional

import httpx
from haystack.dataclasses import ChatMessage, ImageContent

from app.config import get_settings

logger = logging.getLogger(__name__)


async def _analyze_image_qwen_vl(image_b64: str, question: str, mime_type: str) -> str:
    """Call Qwen2.5-VL (OpenAI-compatible) for image analysis."""
    settings = get_settings()
    url = (getattr(settings, "qwen_vl_api_url", None) or "").rstrip("/")
    if not url.endswith("/v1"):
        url = f"{url}/v1" if url else ""
    if not url:
        return ""
    endpoint = f"{url}/chat/completions"
    model = getattr(settings, "qwen_vl_model", "qwen2.5-vl") or "qwen2.5-vl"
    timeout = getattr(settings, "qwen_vl_timeout", 60) or 60
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
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(endpoint, json=body)
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
    settings = get_settings()
    if (getattr(settings, "qwen_vl_api_url", None) or "").strip():
        # Use Qwen2.5-VL (OpenAI-compatible) when configured
        if image_b64.startswith("data:"):
            parts = image_b64.split(",", 1)
            mime_type = "image/png"
            if len(parts) == 2:
                if "/" in parts[0]:
                    mime_type = parts[0].split(":")[1].split(";")[0]
                image_b64 = parts[1]
        else:
            mime_type = _guess_mime_type(image_b64)
        return await _analyze_image_qwen_vl(image_b64, question, mime_type)

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
