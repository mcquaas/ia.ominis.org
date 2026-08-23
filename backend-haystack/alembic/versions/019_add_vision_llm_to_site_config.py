"""Vision LLM settings on site_config (singleton).

Revision ID: 019_vision_llm_site_config
Revises: 018_llm_provider_credentials
Create Date: 2026-03-25
"""

from alembic import op
import sqlalchemy as sa


revision = "019_vision_llm_site_config"
down_revision = "018_llm_provider_credentials"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("site_config", sa.Column("vision_llm_provider", sa.String(length=32), nullable=True))
    op.add_column("site_config", sa.Column("vision_backend_model", sa.String(length=255), nullable=True))
    op.add_column("site_config", sa.Column("vision_ollama_url", sa.String(length=512), nullable=True))
    op.add_column("site_config", sa.Column("vision_openai_base_url", sa.String(length=512), nullable=True))
    op.add_column("site_config", sa.Column("vision_credentials_enc", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("site_config", "vision_credentials_enc")
    op.drop_column("site_config", "vision_openai_base_url")
    op.drop_column("site_config", "vision_ollama_url")
    op.drop_column("site_config", "vision_backend_model")
    op.drop_column("site_config", "vision_llm_provider")
