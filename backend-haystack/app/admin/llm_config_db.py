"""
Sync read of llm_model_config for merging into model registry.
Used by config._build_model_registry(); avoids async in config layer.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


def get_llm_config_overrides() -> dict[str, dict[str, Any]]:
    """
    Load all rows from llm_model_config. Returns dict keyed by model_id with override values.
    Only non-null fields are included so we can merge over env defaults.
    """
    try:
        from sqlalchemy import create_engine
        from sqlalchemy.orm import Session
        from app.config import get_settings
        from app.admin.models import LLMModelConfig

        settings = get_settings()
        sync_url = getattr(settings, "database_url_sync", None) or settings.database_url.replace("+asyncpg", "+psycopg2")
        engine = create_engine(sync_url, pool_pre_ping=True)
        out: dict[str, dict[str, Any]] = {}
        with Session(engine) as session:
            rows = session.query(LLMModelConfig).all()
            for row in rows:
                overrides: dict[str, Any] = {}
                if row.display_name is not None:
                    overrides["display_name"] = row.display_name
                if row.version_label is not None:
                    overrides["version_label"] = row.version_label
                if row.description is not None:
                    overrides["description"] = row.description
                if row.backend_model is not None:
                    overrides["backend_model"] = row.backend_model
                if row.backend_url_override is not None:
                    overrides["backend_url_override"] = row.backend_url_override
                if row.system_prompt is not None:
                    overrides["system_prompt"] = row.system_prompt
                if row.temperature is not None:
                    overrides["temperature"] = row.temperature
                if row.num_predict is not None:
                    overrides["num_predict"] = row.num_predict
                if row.extra_params is not None:
                    overrides["extra_params"] = dict(row.extra_params) if row.extra_params else {}
                if row.is_default is not None:
                    overrides["is_default"] = row.is_default
                if getattr(row, "available_for_researcher", None) is not None:
                    overrides["available_for_researcher"] = row.available_for_researcher
                if getattr(row, "llm_provider", None) is not None:
                    overrides["llm_provider"] = row.llm_provider
                out[row.model_id] = overrides
        return out
    except Exception as e:
        logger.warning("Could not load llm_model_config overrides: %s", e)
        return {}
