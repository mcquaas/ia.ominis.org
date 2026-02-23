"""Add tokens_per_second to query_logs for performance stats.

Revision ID: 013
Revises: 012
Create Date: 2026-02-19

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "013"
down_revision: Union[str, None] = "012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "query_logs",
        sa.Column("tokens_per_second", sa.Float(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("query_logs", "tokens_per_second")
