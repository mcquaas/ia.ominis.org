"""
LLM-based metadata extraction for ingested documents.

Uses the OllamaChatGenerator to analyze document content and extract:
- title: An adequate, professional title
- publisher: The publishing organization
- document_date: Date found on the document
- description: One-sentence summary

Follows Haystack best practices using ChatMessage objects.
"""

import asyncio
import json
import logging
import re

from haystack.dataclasses import ChatMessage

logger = logging.getLogger(__name__)

EXTRACTION_SYSTEM = (
    "Eres un bibliotecario experto en catalogación de documentos. "
    "Analiza el contenido del documento proporcionado y extrae metadatos. "
    "Devuelve SOLO JSON válido sin texto extra."
)

EXTRACTION_USER_TEMPLATE = """Analiza el siguiente fragmento de documento y extrae estos metadatos:

CONTENIDO DEL DOCUMENTO (primeros caracteres):
{content}

URL DE ORIGEN: {url}
NOMBRE DEL ARCHIVO: {filename}

Devuelve un JSON con esta estructura exacta:
{{
    "title": "Título profesional y descriptivo del documento (máximo 200 caracteres)",
    "publisher": "Organización o institución que publica el documento (si no se identifica, pon 'Desconocido')",
    "document_date": "Fecha del documento si aparece (formato libre, ej: 'Marzo 2023', '2019', '09/08/2012'). Si no hay fecha, pon ''",
    "description": "Descripción del documento en UNA oración concisa (máximo 200 caracteres)"
}}

IMPORTANTE:
- El título debe ser descriptivo y profesional, NO el nombre del archivo
- Si el contenido es de una institución gubernamental mexicana, identifícala
- La descripción debe explicar de qué trata el documento
- Responde SOLO con el JSON, sin texto adicional"""


def _extract_json(text: str) -> dict | None:
    """Extract first JSON object from text."""
    try:
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return None
        return json.loads(text[start:end + 1])
    except Exception:
        return None


async def extract_document_metadata(
    content_snippet: str,
    url: str = "",
    filename: str = "",
    generator=None,
) -> dict:
    """
    Use the LLM to extract metadata from a document snippet.

    Args:
        content_snippet: First ~2000 chars of the document content
        url: Original URL of the document
        filename: Original filename
        generator: OllamaChatGenerator instance

    Returns:
        dict with keys: title, publisher, document_date, description
    """
    if not generator:
        logger.warning("No generator provided for metadata extraction")
        return {}

    # Truncate content to avoid overwhelming the LLM
    snippet = content_snippet[:2500] if content_snippet else ""
    if not snippet.strip():
        return {}

    user_msg = EXTRACTION_USER_TEMPLATE.format(
        content=snippet,
        url=url or "(no disponible)",
        filename=filename or "(no disponible)",
    )

    messages = [
        ChatMessage.from_system(EXTRACTION_SYSTEM),
        ChatMessage.from_user(user_msg),
    ]

    try:
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: generator.run(messages=messages),
        )
        replies = result.get("replies", [])
        text = replies[0].text if replies else ""
        parsed = _extract_json(text) or {}
    except Exception as e:
        logger.error(f"Metadata extraction failed: {e}", exc_info=True)
        return {}

    # Validate and clean
    meta = {}
    if parsed.get("title") and isinstance(parsed["title"], str):
        meta["title"] = parsed["title"].strip()[:250]
    if parsed.get("publisher") and isinstance(parsed["publisher"], str):
        pub = parsed["publisher"].strip()
        if pub.lower() not in ("desconocido", "unknown", "n/a", ""):
            meta["publisher"] = pub[:250]
    if parsed.get("document_date") and isinstance(parsed["document_date"], str):
        date_str = parsed["document_date"].strip()
        if date_str:
            meta["document_date"] = date_str[:100]
    if parsed.get("description") and isinstance(parsed["description"], str):
        meta["description"] = parsed["description"].strip()[:500]

    logger.info(f"Extracted metadata: title='{meta.get('title', '')[:50]}', publisher='{meta.get('publisher', '')[:30]}'")
    return meta


def extract_document_metadata_sync(
    content_snippet: str,
    url: str = "",
    filename: str = "",
    generator=None,
) -> dict:
    """Synchronous wrapper for extract_document_metadata."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                return pool.submit(
                    lambda: asyncio.run(
                        extract_document_metadata(content_snippet, url, filename, generator)
                    )
                ).result(timeout=60)
        else:
            return asyncio.run(
                extract_document_metadata(content_snippet, url, filename, generator)
            )
    except Exception as e:
        logger.error(f"Sync metadata extraction failed: {e}")
        return {}
