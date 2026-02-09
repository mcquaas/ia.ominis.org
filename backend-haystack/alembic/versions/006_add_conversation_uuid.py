"""Add uuid to conversations for shareable URLs

Revision ID: 006
Revises: 005
Create Date: 2026-02-08
"""
import uuid
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "006"
down_revision: Union[str, None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("conversations", sa.Column("uuid", sa.String(36), nullable=True))
    # Backfill existing rows with UUIDs
    conn = op.get_bind()
    result = conn.execute(sa.text("SELECT id FROM conversations WHERE uuid IS NULL"))
    rows = result.fetchall()
    for (cid,) in rows:
        conn.execute(
            sa.text("UPDATE conversations SET uuid = :u WHERE id = :id"),
            {"u": str(uuid.uuid4()), "id": cid},
        )
    op.alter_column("conversations", "uuid", nullable=False)
    op.create_index("ix_conversations_uuid", "conversations", ["uuid"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_conversations_uuid", table_name="conversations")
    op.drop_column("conversations", "uuid")
