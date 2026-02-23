"""Add site_config table for global banner message (superadmin notification).

Revision ID: 011
Revises: 010
Create Date: 2026-02-19

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "011"
down_revision: Union[str, None] = "010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "site_config",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("banner_message", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.execute("INSERT INTO site_config (id, banner_message) VALUES (1, NULL)")


def downgrade() -> None:
    op.drop_table("site_config")
