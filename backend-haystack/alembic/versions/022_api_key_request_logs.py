"""Store last API key request/response samples for dashboard.

Revision ID: 022_api_key_logs
Revises: 021_doctor_dedupe
Create Date: 2026-03-25
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "022_api_key_logs"
down_revision = "021_doctor_dedupe"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "api_key_request_logs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("api_key_id", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("method", sa.String(length=16), nullable=False),
        sa.Column("path", sa.String(length=512), nullable=False),
        sa.Column("status_code", sa.Integer(), nullable=False),
        sa.Column("request_body", sa.Text(), nullable=True),
        sa.Column("response_body", sa.Text(), nullable=True),
        sa.Column("request_truncated", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("response_truncated", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("stream_response", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.ForeignKeyConstraint(["api_key_id"], ["api_keys.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_api_key_request_logs_key_created",
        "api_key_request_logs",
        ["api_key_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_api_key_request_logs_key_created", table_name="api_key_request_logs")
    op.drop_table("api_key_request_logs")
