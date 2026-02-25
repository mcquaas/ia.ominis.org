"""Add default_model to chat_defaults (default chat model: ominis-2.0 or ominis-2.0-med)

Revision ID: 016_default_model
Revises: 015_add_health_datastore_tables
Create Date: 2026-02-24

"""
from alembic import op
import sqlalchemy as sa


revision = "016_default_model"
down_revision = "015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "chat_defaults",
        sa.Column("default_model", sa.String(80), nullable=True),
    )
    op.execute("UPDATE chat_defaults SET default_model = 'ominis-2.0' WHERE id = 1")


def downgrade() -> None:
    op.drop_column("chat_defaults", "default_model")
