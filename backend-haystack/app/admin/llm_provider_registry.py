"""
Registry of LLM providers for dashboard mapping. URLs and protocols are server-side only.
"""

from __future__ import annotations

from typing import Any, Literal

ProviderId = Literal["ominis", "openai", "google", "claude", "deepseek"]

# OpenAI-compatible base URLs (without trailing /v1 — normalized in code)
PROVIDERS: dict[str, dict[str, Any]] = {
    "ominis": {
        "label": "OMINIS (Ollama / propio)",
        "protocol": "ollama",
        "credential_key": "ominis",
    },
    "openai": {
        "label": "OpenAI",
        "protocol": "openai",
        "openai_base": "https://api.openai.com/v1",
        "credential_key": "openai",
    },
    "google": {
        "label": "Google (Gemini, API OpenAI-compatible)",
        "protocol": "openai",
        "openai_base": "https://generativelanguage.googleapis.com/v1beta/openai/v1",
        "credential_key": "google",
    },
    "deepseek": {
        "label": "DeepSeek",
        "protocol": "openai",
        "openai_base": "https://api.deepseek.com/v1",
        "credential_key": "deepseek",
    },
    "claude": {
        "label": "Anthropic Claude",
        "protocol": "anthropic",
        "credential_key": "claude",
    },
}

# Fallback models when list API fails or for Claude (no list endpoint in dashboard flow)
STATIC_MODELS: dict[str, list[str]] = {
    "openai": [
        "gpt-5.4",
        "gpt-5.4-mini",
        "gpt-5-mini",
        "gpt-4o-mini",
        "gpt-4o",
        "gpt-4-turbo",
        "gpt-3.5-turbo",
    ],
    "google": ["gemini-2.0-flash", "gemini-1.5-pro", "gemini-1.5-flash"],
    "deepseek": ["deepseek-chat", "deepseek-reasoner"],
    "claude": [
        "claude-sonnet-4-20250514",
        "claude-3-5-sonnet-20241022",
        "claude-3-5-haiku-20241022",
        "claude-3-opus-20240229",
    ],
    "ominis": [],
}


def list_provider_ids() -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for k, v in PROVIDERS.items():
        ck = v.get("credential_key")
        out.append({"id": k, "label": v["label"], "credential_key": ck if ck else ""})
    return out
