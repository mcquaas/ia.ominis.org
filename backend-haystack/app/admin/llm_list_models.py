"""Fetch model IDs from provider APIs (server-side only)."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.admin.llm_provider_registry import PROVIDERS, STATIC_MODELS

logger = logging.getLogger(__name__)


def list_models_for_provider(
    provider_id: str,
    *,
    api_token: str | None,
    ollama_base_url: str | None,
) -> list[str]:
    """
    Return model id strings. On failure, return STATIC_MODELS fallback (except ollama uses /api/tags).
    """
    pid = (provider_id or "").strip().lower()
    if pid == "claude":
        return STATIC_MODELS.get("claude", [])
    if pid == "ominis":
        base = (ollama_base_url or "http://127.0.0.1:11434").rstrip("/")
        try:
            with httpx.Client(timeout=12.0) as c:
                r = c.get(f"{base}/api/tags")
                if r.status_code == 200:
                    data = r.json()
                    models = data.get("models") or []
                    return [str(m.get("name", "")).strip() for m in models if m.get("name")]
        except Exception as e:
            logger.warning("Ollama list models failed: %s", e)
        return STATIC_MODELS.get("ominis", []) or ["qwen2.5:14b"]

    meta = PROVIDERS.get(pid)
    if not meta or meta.get("protocol") != "openai":
        return STATIC_MODELS.get(pid, [])

    base = (meta.get("openai_base") or "").rstrip("/")
    if not base.endswith("/v1"):
        base = f"{base}/v1"
    token = (api_token or "").strip()
    if not token:
        return STATIC_MODELS.get(pid, [])

    try:
        with httpx.Client(timeout=20.0) as c:
            r = c.get(
                f"{base}/models",
                headers={"Authorization": f"Bearer {token}"},
            )
            if r.status_code != 200:
                logger.warning("list models HTTP %s: %s", r.status_code, r.text[:200])
                return STATIC_MODELS.get(pid, [])
            data = r.json()
            out: list[str] = []
            for item in data.get("data", []) or []:
                mid = item.get("id") or item.get("name")
                if mid:
                    out.append(str(mid))
            return out or STATIC_MODELS.get(pid, [])
    except Exception as e:
        logger.warning("list models error: %s", e)
        return STATIC_MODELS.get(pid, [])


def anthropic_static_models() -> list[str]:
    return STATIC_MODELS.get("claude", [])
