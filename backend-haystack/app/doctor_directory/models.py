"""Structured doctor profiles and scrape run audit rows."""

import enum
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Enum, Float, ForeignKey, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB

from app.database import Base


class DoctorScrapeStatus(str, enum.Enum):
    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"


class DoctorDirectoryScrapeRun(Base):
    __tablename__ = "doctor_directory_scrape_runs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    source_site = Column(String(64), nullable=False, index=True)
    status = Column(
        Enum(DoctorScrapeStatus, name="doctorscrapestatus", native_enum=True, values_callable=lambda cls: [e.value for e in cls]),
        nullable=False,
        default=DoctorScrapeStatus.pending,
    )
    started_at = Column(DateTime(timezone=True), nullable=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)
    max_profiles = Column(Integer, nullable=False, default=50)
    profiles_attempted = Column(Integer, nullable=False, default=0)
    profiles_upserted = Column(Integer, nullable=False, default=0)
    profiles_failed = Column(Integer, nullable=False, default=0)
    error_message = Column(Text, nullable=True)
    extra = Column(JSONB, nullable=True)

    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class DoctorDirectoryProfile(Base):
    __tablename__ = "doctor_directory_profiles"
    __table_args__ = (UniqueConstraint("dedupe_key", name="uq_doctor_profile_dedupe_key"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    dedupe_key = Column(String(64), nullable=False, unique=True, index=True)
    """Stable hash of normalized name + specialty + locality + region (cross-source identity)."""

    source_site = Column(String(64), nullable=False, index=True)
    """merged | single source — see source_appearances for each site."""

    profile_slug = Column(String(512), nullable=False, index=True)
    """Equals dedupe_key for canonical rows (legacy slugs kept only inside source_appearances)."""

    profile_url = Column(Text, nullable=False)

    display_name = Column(String(512), nullable=False)
    specialty_label = Column(String(255), nullable=True, index=True)
    specialties_json = Column(JSONB, nullable=True)
    description = Column(Text, nullable=True)
    image_url = Column(Text, nullable=True)

    street_address = Column(Text, nullable=True)
    locality = Column(String(255), nullable=True, index=True)
    region = Column(String(255), nullable=True, index=True)
    postal_code = Column(String(32), nullable=True)
    country_code = Column(String(8), nullable=True)

    services_json = Column(JSONB, nullable=True)
    phones_json = Column(JSONB, nullable=True)
    external_reviews_json = Column(JSONB, nullable=True)

    rating_value = Column(Float, nullable=True)
    rating_count = Column(Integer, nullable=True)
    rating_best = Column(Float, nullable=True)
    rating_worst = Column(Float, nullable=True)

    raw_json_ld = Column(JSONB, nullable=True)

    source_appearances = Column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    """Per-source profile URLs and scrape timestamps: [{source_site, profile_slug, profile_url, last_scraped_at, scrape_run_id, ...}]."""

    last_scraped_at = Column(DateTime(timezone=True), nullable=False)
    scrape_run_id = Column(Integer, ForeignKey("doctor_directory_scrape_runs.id"), nullable=True, index=True)

    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
