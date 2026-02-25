"""Add health_docs and health_chunks for nightly Mexican health datastore.

Revision ID: 015
Revises: 014_research_2_1
Create Date: 2026-02-23

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "015"
down_revision: Union[str, None] = "014_research_2_1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "health_docs",
        sa.Column("doc_id", sa.String(36), primary_key=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("year", sa.Integer(), nullable=True),
        sa.Column("country", sa.String(64), nullable=True),
        sa.Column("institution", sa.String(256), nullable=True),
        sa.Column("document_type", sa.String(64), nullable=True),
        sa.Column("medical_specialty", sa.String(128), nullable=True),
        sa.Column("population", sa.String(128), nullable=True),
        sa.Column("state", sa.String(64), nullable=True),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("source_type", sa.String(64), nullable=False),
        sa.Column("date_ingested", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=True),
        sa.Column("raw_text", sa.Text(), nullable=True),
    )
    op.create_index("ix_health_docs_source_type", "health_docs", ["source_type"])
    op.create_index("ix_health_docs_content_hash", "health_docs", ["content_hash"])
    op.create_index("ix_health_docs_date_ingested", "health_docs", ["date_ingested"])

    op.create_table(
        "health_chunks",
        sa.Column("chunk_id", sa.String(36), primary_key=True),
        sa.Column("doc_id", sa.String(36), sa.ForeignKey("health_docs.doc_id", ondelete="CASCADE"), nullable=False),
        sa.Column("section", sa.String(256), nullable=True),
        sa.Column("chunk_text", sa.Text(), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=True),
        sa.Column("disease", sa.String(256), nullable=True),
        sa.Column("institution", sa.String(256), nullable=True),
        sa.Column("state", sa.String(64), nullable=True),
        sa.Column("year", sa.Integer(), nullable=True),
        sa.Column("document_type", sa.String(64), nullable=True),
        sa.Column("country", sa.String(64), nullable=True),
        sa.Column("evidence_level", sa.String(32), nullable=True),
        sa.Column("classifier_tag", sa.String(32), nullable=True),
    )
    op.create_index("ix_health_chunks_doc_id", "health_chunks", ["doc_id"])


def downgrade() -> None:
    op.drop_table("health_chunks")
    op.drop_table("health_docs")
