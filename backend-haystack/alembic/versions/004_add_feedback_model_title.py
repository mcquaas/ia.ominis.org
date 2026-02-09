"""Add model_name and query_title to message_feedback

Revision ID: 004
Revises: 003
Create Date: 2026-02-06
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("message_feedback", sa.Column("model_name", sa.String(100), nullable=True))
    op.add_column("message_feedback", sa.Column("query_title", sa.String(500), nullable=True))


def downgrade() -> None:
    op.drop_column("message_feedback", "query_title")
    op.drop_column("message_feedback", "model_name")
