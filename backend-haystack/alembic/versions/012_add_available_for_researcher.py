"""Add available_for_researcher to llm_model_config (SuperAdmin controls which models researchers can use).

Revision ID: 012
Revises: 011
Create Date: 2026-02-19

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "012"
down_revision: Union[str, None] = "011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "llm_model_config",
        sa.Column("available_for_researcher", sa.Boolean(), nullable=True),
    )
    # Default True so existing behaviour is preserved; ominis-2.0 is always allowed for guests
    op.execute("UPDATE llm_model_config SET available_for_researcher = true WHERE available_for_researcher IS NULL")


def downgrade() -> None:
    op.drop_column("llm_model_config", "available_for_researcher")
