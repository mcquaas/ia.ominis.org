"""Doctor directory profiles and scrape run audit (Mexico public listings).

Revision ID: 020_doctor_directory
Revises: 019_vision_llm_site_config
Create Date: 2026-03-25
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "020_doctor_directory"
down_revision = "019_vision_llm_site_config"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    already = bind.execute(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_name = 'doctor_directory_scrape_runs')"
        )
    ).scalar()
    if already:
        return

    # Idempotent: another process may have created the enum already.
    op.execute(
        """
        DO $$ BEGIN
            CREATE TYPE doctorscrapestatus AS ENUM ('pending', 'running', 'completed', 'failed');
        EXCEPTION
            WHEN duplicate_object THEN NULL;
        END $$;
        """
    )
    scrape_status = postgresql.ENUM(
        "pending", "running", "completed", "failed",
        name="doctorscrapestatus",
        create_type=False,
    )

    op.create_table(
        "doctor_directory_scrape_runs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("source_site", sa.String(length=64), nullable=False),
        sa.Column("status", scrape_status, nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("max_profiles", sa.Integer(), nullable=False),
        sa.Column("profiles_attempted", sa.Integer(), nullable=False),
        sa.Column("profiles_upserted", sa.Integer(), nullable=False),
        sa.Column("profiles_failed", sa.Integer(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("extra", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_doctor_directory_scrape_runs_source_site",
        "doctor_directory_scrape_runs",
        ["source_site"],
    )

    op.create_table(
        "doctor_directory_profiles",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("source_site", sa.String(length=64), nullable=False),
        sa.Column("profile_slug", sa.String(length=512), nullable=False),
        sa.Column("profile_url", sa.Text(), nullable=False),
        sa.Column("display_name", sa.String(length=512), nullable=False),
        sa.Column("specialty_label", sa.String(length=255), nullable=True),
        sa.Column("specialties_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("image_url", sa.Text(), nullable=True),
        sa.Column("street_address", sa.Text(), nullable=True),
        sa.Column("locality", sa.String(length=255), nullable=True),
        sa.Column("region", sa.String(length=255), nullable=True),
        sa.Column("postal_code", sa.String(length=32), nullable=True),
        sa.Column("country_code", sa.String(length=8), nullable=True),
        sa.Column("services_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("phones_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("external_reviews_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("rating_value", sa.Float(), nullable=True),
        sa.Column("rating_count", sa.Integer(), nullable=True),
        sa.Column("rating_best", sa.Float(), nullable=True),
        sa.Column("rating_worst", sa.Float(), nullable=True),
        sa.Column("raw_json_ld", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("last_scraped_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("scrape_run_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["scrape_run_id"], ["doctor_directory_scrape_runs.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_site", "profile_slug", name="uq_doctor_profile_source_slug"),
    )
    op.create_index("ix_doctor_directory_profiles_source_site", "doctor_directory_profiles", ["source_site"])
    op.create_index("ix_doctor_directory_profiles_profile_slug", "doctor_directory_profiles", ["profile_slug"])
    op.create_index("ix_doctor_directory_profiles_specialty_label", "doctor_directory_profiles", ["specialty_label"])
    op.create_index("ix_doctor_directory_profiles_locality", "doctor_directory_profiles", ["locality"])
    op.create_index("ix_doctor_directory_profiles_region", "doctor_directory_profiles", ["region"])
    op.create_index("ix_doctor_directory_profiles_scrape_run_id", "doctor_directory_profiles", ["scrape_run_id"])


def downgrade() -> None:
    op.drop_index("ix_doctor_directory_profiles_scrape_run_id", table_name="doctor_directory_profiles")
    op.drop_index("ix_doctor_directory_profiles_region", table_name="doctor_directory_profiles")
    op.drop_index("ix_doctor_directory_profiles_locality", table_name="doctor_directory_profiles")
    op.drop_index("ix_doctor_directory_profiles_specialty_label", table_name="doctor_directory_profiles")
    op.drop_index("ix_doctor_directory_profiles_profile_slug", table_name="doctor_directory_profiles")
    op.drop_index("ix_doctor_directory_profiles_source_site", table_name="doctor_directory_profiles")
    op.drop_table("doctor_directory_profiles")
    op.drop_index("ix_doctor_directory_scrape_runs_source_site", table_name="doctor_directory_scrape_runs")
    op.drop_table("doctor_directory_scrape_runs")
    op.execute("DROP TYPE IF EXISTS doctorscrapestatus")
