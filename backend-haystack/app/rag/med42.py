"""
Optional Med42 (A100) for clinical translation step in research.
OpenAI-compatible API. When MED42_API_URL is set, use for implications/risks/recommendations.
"""

import os
from typing import Optional, Union

from haystack.components.generators.chat import OpenAIChatGenerator
from haystack.dataclasses import ChatMessage
from haystack.utils import Secret

from app.config import get_settings
from app.vast_serverless.generators import ServerlessOpenAIChatGenerator


def _vast_api_key() -> str:
    s = get_settings()
    return (getattr(s, "vast_api_key", None) or os.environ.get("VAST_API_KEY", "") or "").strip()


def _vast_cost(override: int) -> int:
    s = get_settings()
    if override and override > 0:
        return int(override)
    return int(getattr(s, "vast_serverless_default_cost", 500) or 500)


def _vast_client_timeout() -> float:
    s = get_settings()
    return float(getattr(s, "vast_serverless_client_timeout", 900) or 900)


def get_med42_generator() -> Optional[Union[OpenAIChatGenerator, ServerlessOpenAIChatGenerator]]:
    """Return Med42 OpenAIChatGenerator when MED42_API_URL or Vast Serverless Med42 is set, else None."""
    settings = get_settings()
    vk = _vast_api_key()
    v_ep = (getattr(settings, "vast_serverless_med42_endpoint", "") or "").strip()
    if v_ep and vk:
        oc = int(getattr(settings, "vast_serverless_med42_cost", 0) or 0)
        model = getattr(settings, "med42_model", "med42") or "med42"
        vst = _vast_client_timeout()
        return ServerlessOpenAIChatGenerator(
            endpoint_name=v_ep,
            model=model,
            api_key=vk,
            cost=_vast_cost(oc),
            timeout=vst,
            worker_timeout=vst,
            generation_kwargs={"temperature": 0.3, "max_tokens": 1024},
        )
    url = (getattr(settings, "med42_api_url", None) or "").strip().rstrip("/")
    if not url:
        return None
    if not url.endswith("/v1"):
        url = f"{url}/v1"
    model = getattr(settings, "med42_model", "med42") or "med42"
    timeout = getattr(settings, "med42_timeout", 60) or 60
    return OpenAIChatGenerator(
        model=model,
        api_key=Secret.from_token("dummy"),
        api_base_url=url,
        timeout=timeout,
        generation_kwargs={"temperature": 0.3, "max_tokens": 1024},
    )


def run_clinical_translator_sync(
    generator: Union[OpenAIChatGenerator, ServerlessOpenAIChatGenerator], synthesis: str
) -> str:
    """
    Given a research synthesis, produce clinical implications, risks, and prudent recommendations.
    Returns the appended section text (Spanish).
    """
    prompt = (
        "Eres un experto en traducción de evidencia a práctica clínica. "
        "A partir del siguiente reporte de investigación, escribe una sección breve (8-12 líneas) que incluya:\n"
        "1. Implicaciones clínicas (qué debe considerar el profesional)\n"
        "2. Riesgos o limitaciones a tener en cuenta\n"
        "3. Recomendaciones prudentes (sin sustituir el criterio clínico)\n"
        "Responde solo en español. Sé conservador y evita afirmaciones que vayan más allá de la evidencia.\n\n"
        "REPORTE:\n" + (synthesis[:8000] or "")
    )
    messages = [ChatMessage.from_user(prompt)]
    try:
        result = generator.run(messages=messages)
        replies = result.get("replies", [])
        return (replies[0].text or "").strip() if replies else ""
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning("Med42 clinical translator failed: %s", e)
        return ""
