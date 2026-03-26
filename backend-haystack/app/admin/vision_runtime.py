"""
Effective Vision LLM settings: site_config (dashboard) merged with env defaults.
Used by app.rag.vision and app.rag.pipeline (sync reads).
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass

from app.admin.llm_crypto import decrypt_credentials_blob
from app.admin.llm_provider_registry import PROVIDERS

logger = logging.getLogger(__name__)


@dataclass
class VisionRuntimeSettings:
    """Resolved vision routing: Qwen/OpenAI multimodal vs Ollama ImageContent."""

    # Prefer OpenAI-compatible multimodal (vision.py _analyze_image_qwen_vl)
    use_openai_multimodal: bool
    qwen_vl_api_url: str  # base ending in /v1 or empty
    qwen_vl_model: str
    qwen_vl_timeout: float
    qwen_api_key: str
    vast_qwen_endpoint: str
    vast_api_key: str

    # Ollama native (pipeline vision generator + vision.py fallback)
    use_ollama_vision: bool
    vision_model: str
    ollama_url: str
    ollama_api_key: str  # optional Bearer for proxied Ollama
    force_direct_ollama: bool = False  # dashboard OMINIS: never use Vast serverless for vision


def _site_config_row_sync():
    try:
        from sqlalchemy import create_engine
        from sqlalchemy.orm import Session

        from app.admin.models import SiteConfig
        from app.config import get_settings

        settings = get_settings()
        sync_url = getattr(settings, "database_url_sync", None) or settings.database_url.replace("+asyncpg", "+psycopg2")
        engine = create_engine(sync_url, pool_pre_ping=True)
        with Session(engine) as session:
            return session.query(SiteConfig).filter(SiteConfig.id == 1).one_or_none()
    except Exception as e:
        logger.warning("Could not load site_config for vision: %s", e)
        return None


def get_vision_provider_token(credential_key: str) -> str:
    """API token stored for Vision (site_config), by provider credential key."""
    if not credential_key:
        return ""
    row = _site_config_row_sync()
    if not row or not getattr(row, "vision_credentials_enc", None):
        return ""
    creds = decrypt_credentials_blob(row.vision_credentials_enc)
    return (creds.get(credential_key) or "").strip()


def get_vision_runtime_settings() -> VisionRuntimeSettings:
    """Merge env defaults with dashboard vision overrides."""
    from app.config import get_settings

    s = get_settings()
    vk = (getattr(s, "vast_api_key", None) or os.environ.get("VAST_API_KEY", "") or "").strip()
    qwen_http = (getattr(s, "qwen_vl_api_url", "") or "").strip()
    qwen_slv = (getattr(s, "vast_serverless_qwen_vl_endpoint", "") or "").strip()

    row = _site_config_row_sync()
    creds: dict[str, str] = {}
    if row and getattr(row, "vision_credentials_enc", None):
        creds = decrypt_credentials_blob(row.vision_credentials_enc)

    pid = (getattr(row, "vision_llm_provider", None) or "").strip().lower() if row else ""

    # No dashboard override: preserve legacy env-only behavior
    if not pid:
        qwen_on = bool(qwen_http or (qwen_slv and vk))
        vm = (getattr(s, "vision_model", None) or "") or ""
        return VisionRuntimeSettings(
            use_openai_multimodal=qwen_on,
            qwen_vl_api_url=qwen_http,
            qwen_vl_model=(getattr(s, "qwen_vl_model", None) or "qwen2.5-vl") or "qwen2.5-vl",
            qwen_vl_timeout=float(getattr(s, "qwen_vl_timeout", 60) or 60),
            qwen_api_key=(getattr(s, "openai_api_key", None) or os.environ.get("OPENAI_API_KEY", "") or "").strip(),
            vast_qwen_endpoint=qwen_slv,
            vast_api_key=vk,
            use_ollama_vision=bool(vm) and not qwen_on,
            vision_model=vm,
            ollama_url=(getattr(s, "ollama_url", "") or ""),
            ollama_api_key="",
        )

    if pid == "ominis":
        ollama_url = (getattr(row, "vision_ollama_url", None) or "").strip() or (getattr(s, "ollama_url", "") or "")
        model = (getattr(row, "vision_backend_model", None) or "").strip() or (getattr(s, "vision_model", "") or "minicpm-v")
        okey = (creds.get("ominis") or "").strip()
        return VisionRuntimeSettings(
            use_openai_multimodal=False,
            qwen_vl_api_url="",
            qwen_vl_model="",
            qwen_vl_timeout=float(getattr(s, "qwen_vl_timeout", 60) or 60),
            qwen_api_key="",
            vast_qwen_endpoint="",
            vast_api_key="",
            use_ollama_vision=bool(model and ollama_url),
            vision_model=model,
            ollama_url=ollama_url.rstrip("/"),
            ollama_api_key=okey,
            force_direct_ollama=True,
        )

    meta = PROVIDERS.get(pid)
    if not meta or meta.get("protocol") != "openai":
        # Claude: not OpenAI multimodal in this path — fall back to env Qwen if any
        return VisionRuntimeSettings(
            use_openai_multimodal=bool(qwen_http or (qwen_slv and vk)),
            qwen_vl_api_url=qwen_http,
            qwen_vl_model=(getattr(s, "qwen_vl_model", None) or "qwen2.5-vl") or "qwen2.5-vl",
            qwen_vl_timeout=float(getattr(s, "qwen_vl_timeout", 60) or 60),
            qwen_api_key="",
            vast_qwen_endpoint=qwen_slv,
            vast_api_key=vk,
            use_ollama_vision=bool(getattr(s, "vision_model", None) and not (qwen_http or (qwen_slv and vk))),
            vision_model=(getattr(s, "vision_model", "") or ""),
            ollama_url=(getattr(s, "ollama_url", "") or ""),
            ollama_api_key="",
        )

    ck = meta.get("credential_key") or ""
    api_key = (creds.get(ck) or "").strip() if ck else ""
    base = (getattr(row, "vision_openai_base_url", None) or "").strip()
    if not base:
        base = (meta.get("openai_base") or "").strip()
    base = base.rstrip("/")
    if base and not base.endswith("/v1"):
        base = f"{base}/v1"
    model = (getattr(row, "vision_backend_model", None) or "").strip() or (getattr(s, "qwen_vl_model", "") or "qwen2.5-vl")
    return VisionRuntimeSettings(
        use_openai_multimodal=bool(base and model),
        qwen_vl_api_url=base,
        qwen_vl_model=model,
        qwen_vl_timeout=float(getattr(s, "qwen_vl_timeout", 60) or 60),
        qwen_api_key=api_key or (getattr(s, "openai_api_key", None) or os.environ.get("OPENAI_API_KEY", "") or "").strip(),
        vast_qwen_endpoint="",
        vast_api_key="",
        use_ollama_vision=False,
        vision_model="",
        ollama_url="",
        ollama_api_key="",
    )


def vision_prefers_openai_multimodal(vr: VisionRuntimeSettings) -> bool:
    """True when vision should use Qwen/OpenAI multimodal path (not Ollama ImageContent)."""
    if vr.vast_qwen_endpoint and vr.vast_api_key:
        return True
    return bool(vr.qwen_vl_api_url and vr.qwen_vl_model)
