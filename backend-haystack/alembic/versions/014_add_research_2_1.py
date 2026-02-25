"""Add research_2_1 to chat_defaults (Research 2.1 deep investigation mode)

Revision ID: 014_research_2_1
Revises: 013_add_query_log_tokens_per_second
Create Date: 2026-02-23

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "014_research_2_1"
down_revision = "013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "chat_defaults",
        sa.Column("research_2_1", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("chat_defaults", "research_2_1")
