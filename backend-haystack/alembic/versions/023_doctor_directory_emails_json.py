"""Add emails_json to doctor_directory_profiles.

Revision ID: 023_doctor_emails
Revises: 022_api_key_logs
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "023_doctor_emails"
down_revision = "022_api_key_logs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "doctor_directory_profiles",
        sa.Column("emails_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("doctor_directory_profiles", "emails_json")
