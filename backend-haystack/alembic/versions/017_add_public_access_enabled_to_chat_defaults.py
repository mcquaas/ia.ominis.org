"""Add public access toggle to chat_defaults (require registration when disabled).

Revision ID: 017_public_access_enabled
Revises: 016_default_model
Create Date: 2026-03-17
"""

from alembic import op
import sqlalchemy as sa


revision = "017_public_access_enabled"
down_revision = "016_default_model"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "chat_defaults",
        sa.Column("public_access_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    # Ensure existing singleton row starts with closed access (require auth).
    op.execute("UPDATE chat_defaults SET public_access_enabled = false WHERE id = 1")


def downgrade() -> None:
    op.drop_column("chat_defaults", "public_access_enabled")

