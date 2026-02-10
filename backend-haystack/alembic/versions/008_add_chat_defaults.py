"""Add chat_defaults table for default toggles (Investigación, Ominis, PubMed, Web)

Revision ID: 008
Revises: 007
Create Date: 2026-02-10

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "008"
down_revision: Union[str, None] = "007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "chat_defaults",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("research_mode", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("rag_search", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("web_search", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("pubmed_search", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
    )
    op.execute("INSERT INTO chat_defaults (id, research_mode, rag_search, web_search, pubmed_search) VALUES (1, false, true, true, true)")


def downgrade() -> None:
    op.drop_table("chat_defaults")
