"""Encrypt/decrypt per-provider API tokens stored in llm_model_config.provider_credentials_enc."""

from __future__ import annotations

import base64
import hashlib
import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

_fernet = None


def _get_fernet():
    global _fernet
    if _fernet is not None:
        return _fernet
    try:
        from cryptography.fernet import Fernet
    except ImportError as e:
        raise RuntimeError("cryptography package required for LLM credential storage") from e

    from app.config import get_settings

    secret = (getattr(get_settings(), "jwt_secret", None) or "change-me").encode("utf-8")
    key = base64.urlsafe_b64encode(hashlib.sha256(secret + b"|ominis-llm-provider-keys-v1").digest())
    _fernet = Fernet(key)
    return _fernet


def encrypt_credentials_blob(data: dict[str, Any]) -> str:
    """JSON dict -> Fernet token string."""
    raw = json.dumps(data, ensure_ascii=False).encode("utf-8")
    return _get_fernet().encrypt(raw).decode("ascii")


def decrypt_credentials_blob(token: str | None) -> dict[str, str]:
    if not token or not str(token).strip():
        return {}
    try:
        raw = _get_fernet().decrypt(token.encode("ascii"))
        d = json.loads(raw.decode("utf-8"))
        if not isinstance(d, dict):
            return {}
        return {str(k): str(v) for k, v in d.items() if isinstance(v, str) and v.strip()}
    except Exception as e:
        logger.warning("Could not decrypt provider credentials: %s", e)
        return {}


def merge_credential_patch(existing_enc: str | None, patch: dict[str, str | None]) -> str | None:
    """
    Merge non-empty string values into decrypted dict; None or empty string in patch = skip (keep old).
    Use explicit empty string to clear a key? User said keep keys when switching - we never delete unless explicit.
    """
    cur = decrypt_credentials_blob(existing_enc)
    for k, v in patch.items():
        if v is None:
            continue
        vs = str(v).strip()
        if vs:
            cur[k] = vs
        elif vs == "" and k in cur:
            del cur[k]
    if not cur:
        return None
    return encrypt_credentials_blob(cur)
