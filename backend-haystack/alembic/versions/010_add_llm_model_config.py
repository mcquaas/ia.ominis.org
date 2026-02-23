"""Add llm_model_config table for dashboard-configurable LLM assignments, prompts, and params.

Revision ID: 010
Revises: 009
Create Date: 2026-02-18

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "010"
down_revision: Union[str, None] = "009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "llm_model_config",
        sa.Column("model_id", sa.String(80), primary_key=True),
        sa.Column("display_name", sa.String(255), nullable=True),
        sa.Column("version_label", sa.String(64), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("backend_model", sa.String(255), nullable=True),
        sa.Column("backend_url_override", sa.String(512), nullable=True),
        sa.Column("system_prompt", sa.Text(), nullable=True),
        sa.Column("temperature", sa.Float(), nullable=True),
        sa.Column("num_predict", sa.Integer(), nullable=True),
        sa.Column("extra_params", JSONB, nullable=True),
        sa.Column("is_default", sa.Boolean(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("llm_model_config")
