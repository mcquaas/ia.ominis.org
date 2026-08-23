"""Alembic environment configuration."""

import os
import sys
from logging.config import fileConfig

# Load .env before any app imports (so DATABASE_URL_SYNC is available)
try:
    from dotenv import load_dotenv
    env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
    load_dotenv(env_path)
except ImportError:
    pass

from sqlalchemy import engine_from_config, pool
from alembic import context

# Add the project root to the path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app.database import Base
from app.auth.models import User  # noqa: F401 - import so metadata registers
from app.api_keys.models import APIKey, APIKeyRequestLog  # noqa: F401
from app.admin.models import RAGSource, QueryLog, SystemStat, ChatDefaults, LLMModelConfig  # noqa: F401
from app.chat.models import Conversation, ChatMessage  # noqa: F401
from app.feedback.models import MessageFeedback  # noqa: F401
from app.doctor_directory.models import DoctorDirectoryProfile, DoctorDirectoryScrapeRun  # noqa: F401

config = context.config

# Override sqlalchemy.url from environment (DATABASE_URL_SYNC or sync equiv of DATABASE_URL)
database_url = os.environ.get("DATABASE_URL_SYNC")
if not database_url:
    async_url = os.environ.get("DATABASE_URL", "")
    if async_url and "asyncpg" in async_url:
        database_url = async_url.replace("postgresql+asyncpg://", "postgresql://").replace("postgresql+asyncpg", "postgresql")
if database_url:
    config.set_main_option("sqlalchemy.url", database_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
