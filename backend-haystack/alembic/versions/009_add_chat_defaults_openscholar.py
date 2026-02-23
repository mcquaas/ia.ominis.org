"""Add openscholar_search to chat_defaults (Open Scholar / Semantic Scholar source, default off)

Revision ID: 009
Revises: 008
Create Date: 2026-02-10

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "009"
down_revision: Union[str, None] = "008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "chat_defaults",
        sa.Column("openscholar_search", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("chat_defaults", "openscholar_search")
