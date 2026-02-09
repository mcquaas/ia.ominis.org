"""Add sources_json to message_feedback

Revision ID: 005
Revises: 004
Create Date: 2026-02-08
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("message_feedback", sa.Column("sources_json", JSONB, nullable=True))


def downgrade() -> None:
    op.drop_column("message_feedback", "sources_json")
