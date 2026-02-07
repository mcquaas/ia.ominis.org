"""Initial schema: users, api_keys, rag_sources, query_logs, system_stats

Revision ID: 001
Revises: None
Create Date: 2026-02-06
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Users
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("username", sa.String(100), nullable=False),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("full_name", sa.String(255), nullable=True),
        sa.Column(
            "role",
            sa.Enum("researcher", "admin", "superadmin", name="roleenum"),
            nullable=False,
            server_default="researcher",
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("institution", sa.String(255), nullable=True),
        sa.Column("bio", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
        sa.UniqueConstraint("username"),
    )
    op.create_index("ix_users_email", "users", ["email"])
    op.create_index("ix_users_username", "users", ["username"])

    # API Keys
    op.create_table(
        "api_keys",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("key_hash", sa.String(255), nullable=False),
        sa.Column("key_prefix", sa.String(20), nullable=False),
        sa.Column(
            "status",
            sa.Enum("active", "revoked", "expired", name="apikeystatus"),
            nullable=False,
            server_default="active",
        ),
        sa.Column("permissions", sa.Text(), nullable=True),
        sa.Column("ip_whitelist", sa.Text(), nullable=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("request_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("key_hash"),
    )
    op.create_index("ix_api_keys_key_prefix", "api_keys", ["key_prefix"])

    # RAG Sources
    op.create_table(
        "rag_sources",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(255), nullable=False),
        sa.Column("source_type", sa.String(50), nullable=False, server_default="webpage"),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column(
            "status",
            sa.Enum("active", "inactive", "indexing", "error", name="sourcestatus"),
            nullable=False,
            server_default="active",
        ),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("category", sa.String(100), nullable=True),
        sa.Column("language", sa.String(10), nullable=True, server_default="es"),
        sa.Column("chunks_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_indexed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("indexing_error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug"),
    )
    op.create_index("ix_rag_sources_slug", "rag_sources", ["slug"])

    # Query Logs
    op.create_table(
        "query_logs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("answer", sa.Text(), nullable=True),
        sa.Column("sources_used", sa.Text(), nullable=True),
        sa.Column("model_used", sa.String(100), nullable=True),
        sa.Column("response_time_ms", sa.Integer(), nullable=True),
        sa.Column("tokens_used", sa.Integer(), nullable=True),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("api_key_id", sa.Integer(), nullable=True),
        sa.Column("rag_search", sa.Boolean(), server_default="true"),
        sa.Column("web_search", sa.Boolean(), server_default="false"),
        sa.Column("pubmed_search", sa.Boolean(), server_default="false"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    # System Stats (singleton)
    op.create_table(
        "system_stats",
        sa.Column("id", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("model_version", sa.String(50), nullable=True, server_default="ominis-2.0"),
        sa.Column("model_status", sa.String(20), nullable=True, server_default="active"),
        sa.Column("total_queries", sa.Integer(), server_default="0"),
        sa.Column("total_users", sa.Integer(), server_default="0"),
        sa.Column("total_sources", sa.Integer(), server_default="0"),
        sa.Column("total_chunks", sa.Integer(), server_default="0"),
        sa.Column("cpu_server_status", sa.String(20), nullable=True, server_default="unknown"),
        sa.Column("gpu_server_status", sa.String(20), nullable=True, server_default="unknown"),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    # Insert default system stats row
    op.execute(
        "INSERT INTO system_stats (id) VALUES (1) ON CONFLICT DO NOTHING"
    )


def downgrade() -> None:
    op.drop_table("system_stats")
    op.drop_table("query_logs")
    op.drop_table("rag_sources")
    op.drop_table("api_keys")
    op.drop_table("users")
    op.execute("DROP TYPE IF EXISTS roleenum")
    op.execute("DROP TYPE IF EXISTS apikeystatus")
    op.execute("DROP TYPE IF EXISTS sourcestatus")
