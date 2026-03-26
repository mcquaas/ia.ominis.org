"""Canonical doctor profiles: dedupe_key + source_appearances (cross-source merge).

Revision ID: 021_doctor_dedupe
Revises: 020_doctor_directory
Create Date: 2026-03-25
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections import defaultdict

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "021_doctor_dedupe"
down_revision = "020_doctor_directory"
branch_labels = None
depends_on = None


def _norm(s: str | None) -> str:
    if not s:
        return ""
    t = unicodedata.normalize("NFKD", str(s))
    t = "".join(c for c in t if not unicodedata.combining(c))
    t = t.lower().strip()
    t = re.sub(r"^(dr\.?|dra\.?|doctora?\.?)\s+", "", t, flags=re.I)
    t = re.sub(r"\s+", " ", t)
    return t


def _dedupe_key(name: str, spec: str | None, loc: str | None, reg: str | None) -> str:
    raw = "|".join([_norm(name), _norm(spec), _norm(loc), _norm(reg)])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def upgrade() -> None:
    bind = op.get_bind()
    tbl = bind.execute(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM information_schema.tables "
            "WHERE table_schema='public' AND table_name='doctor_directory_profiles')"
        )
    ).scalar()
    if not tbl:
        return
    has_col = bind.execute(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM information_schema.columns "
            "WHERE table_schema='public' AND table_name='doctor_directory_profiles' AND column_name='dedupe_key')"
        )
    ).scalar()
    if has_col:
        return

    op.add_column("doctor_directory_profiles", sa.Column("dedupe_key", sa.String(length=64), nullable=True))
    op.add_column(
        "doctor_directory_profiles",
        sa.Column("source_appearances", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )

    rows = bind.execute(
        sa.text(
            "SELECT id, source_site, profile_slug, profile_url, display_name, specialty_label, locality, region, "
            "last_scraped_at, scrape_run_id FROM doctor_directory_profiles ORDER BY id"
        )
    ).mappings().all()

    for r in rows:
        dk = _dedupe_key(
            r["display_name"] or "",
            r.get("specialty_label"),
            r.get("locality"),
            r.get("region"),
        )
        app = {
            "source_site": r["source_site"],
            "profile_slug": r["profile_slug"],
            "profile_url": (r["profile_url"] or "").rstrip("/") + "/",
            "last_scraped_at": r["last_scraped_at"].isoformat() if r["last_scraped_at"] else None,
            "scrape_run_id": r["scrape_run_id"],
            "rating_value": None,
            "rating_count": None,
        }
        bind.execute(
            sa.text(
                "UPDATE doctor_directory_profiles SET dedupe_key = :dk, "
                "source_appearances = CAST(:apps AS jsonb) WHERE id = :id"
            ),
            {"dk": dk, "apps": json.dumps([app]), "id": r["id"]},
        )

    by_dk: dict[str, list[int]] = defaultdict(list)
    id_rows = bind.execute(sa.text("SELECT id, dedupe_key FROM doctor_directory_profiles")).fetchall()
    for rid, dk in id_rows:
        if dk:
            by_dk[dk].append(rid)

    for dk, ids in by_dk.items():
        if len(ids) <= 1:
            continue
        keeper = min(ids)
        others = [i for i in ids if i != keeper]
        apps_out: list[dict] = []
        seen: set[tuple[str, str]] = set()
        for rid in sorted(ids):
            raw_apps = bind.execute(
                sa.text("SELECT source_appearances FROM doctor_directory_profiles WHERE id = :id"),
                {"id": rid},
            ).scalar()
            if raw_apps is None:
                lst = []
            elif isinstance(raw_apps, list):
                lst = raw_apps
            elif isinstance(raw_apps, str):
                lst = json.loads(raw_apps)
            else:
                lst = []
            for a in lst:
                k = (a.get("source_site") or "", a.get("profile_slug") or "")
                if k not in seen and k[0]:
                    seen.add(k)
                    apps_out.append(a)
        apps_out.sort(key=lambda x: (x.get("source_site") or "", x.get("profile_slug") or ""))
        sites = {a.get("source_site") for a in apps_out if a.get("source_site")}
        src_site = "merged" if len(sites) > 1 else (next(iter(sites)) if sites else "unknown")
        primary_url = apps_out[0].get("profile_url") if apps_out else ""
        bind.execute(
            sa.text(
                "UPDATE doctor_directory_profiles SET source_appearances = CAST(:apps AS jsonb), "
                "source_site = :ss, profile_slug = :dk, profile_url = COALESCE(NULLIF(:pu, ''), profile_url) "
                "WHERE id = :id"
            ),
            {"apps": json.dumps(apps_out), "ss": src_site, "dk": dk, "pu": primary_url or "", "id": keeper},
        )
        for oid in others:
            bind.execute(sa.text("DELETE FROM doctor_directory_profiles WHERE id = :id"), {"id": oid})

    op.alter_column("doctor_directory_profiles", "dedupe_key", nullable=False)
    op.alter_column(
        "doctor_directory_profiles",
        "source_appearances",
        nullable=False,
        server_default=sa.text("'[]'::jsonb"),
    )

    op.execute(sa.text("ALTER TABLE doctor_directory_profiles DROP CONSTRAINT IF EXISTS uq_doctor_profile_source_slug"))
    has_dedupe_uq = bind.execute(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM pg_constraint c "
            "JOIN pg_class t ON c.conrelid = t.oid "
            "WHERE t.relname = 'doctor_directory_profiles' AND c.conname = 'uq_doctor_profile_dedupe_key')"
        )
    ).scalar()
    if not has_dedupe_uq:
        op.create_unique_constraint("uq_doctor_profile_dedupe_key", "doctor_directory_profiles", ["dedupe_key"])


def downgrade() -> None:
    op.execute(sa.text("ALTER TABLE doctor_directory_profiles DROP CONSTRAINT IF EXISTS uq_doctor_profile_dedupe_key"))
    op.create_unique_constraint(
        "uq_doctor_profile_source_slug",
        "doctor_directory_profiles",
        ["source_site", "profile_slug"],
    )
    op.drop_column("doctor_directory_profiles", "source_appearances")
    op.drop_column("doctor_directory_profiles", "dedupe_key")
