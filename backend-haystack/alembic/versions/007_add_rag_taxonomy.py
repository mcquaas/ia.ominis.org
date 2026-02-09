"""Add taxonomy and metadata columns to rag_sources for researcher classification

Revision ID: 007
Revises: 006
Create Date: 2026-02-08

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "007"
down_revision: Union[str, None] = "006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "rag_sources",
        sa.Column("taxonomy", JSONB, nullable=True),
    )


def downgrade() -> None:
    op.drop_column("rag_sources", "taxonomy")
