"""
Migration script: Strapi PostgreSQL -> New Haystack backend schema.

Migrates:
- Users (including bcrypt password hashes - compatible between systems)
- API keys (preserves hashes and prefixes)
- RAG source metadata

Usage:
    python scripts/migrate_from_strapi.py \
        --strapi-db "postgresql://user:pass@host:5432/ominis_strapi" \
        --new-db "postgresql://user:pass@host:5432/ominis_haystack"

Or with environment variables:
    STRAPI_DATABASE_URL=... NEW_DATABASE_URL=... python scripts/migrate_from_strapi.py
"""

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone

import psycopg2
from psycopg2.extras import DictCursor

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def get_strapi_users(strapi_conn) -> list[dict]:
    """Fetch users from Strapi's users-permissions plugin."""
    with strapi_conn.cursor(cursor_factory=DictCursor) as cur:
        cur.execute("""
            SELECT 
                u.id,
                u.username,
                u.email,
                u.password,
                u.confirmed,
                u.blocked,
                u.created_at,
                u.updated_at,
                r.name as role_name,
                r.type as role_type
            FROM up_users u
            LEFT JOIN up_roles r ON u.role = r.id
            ORDER BY u.id
        """)
        return [dict(row) for row in cur.fetchall()]


def get_strapi_api_keys(strapi_conn) -> list[dict]:
    """Fetch API keys from Strapi."""
    with strapi_conn.cursor(cursor_factory=DictCursor) as cur:
        try:
            cur.execute("""
                SELECT 
                    id,
                    name,
                    key_hash,
                    key_prefix,
                    status,
                    permissions,
                    ip_whitelist,
                    request_count,
                    last_used_at,
                    expires_at,
                    created_at,
                    owner
                FROM api_keys
                ORDER BY id
            """)
            return [dict(row) for row in cur.fetchall()]
        except psycopg2.errors.UndefinedTable:
            logger.warning("api_keys table not found in Strapi DB. Skipping.")
            strapi_conn.rollback()
            return []


def get_strapi_rag_sources(strapi_conn) -> list[dict]:
    """Fetch RAG source metadata from Strapi."""
    with strapi_conn.cursor(cursor_factory=DictCursor) as cur:
        try:
            cur.execute("""
                SELECT 
                    id, title, slug, source_type, source_url, status,
                    content, category, language, chunks_count,
                    last_indexed_at, indexing_error,
                    created_at, updated_at
                FROM rag_sources
                ORDER BY id
            """)
            return [dict(row) for row in cur.fetchall()]
        except psycopg2.errors.UndefinedTable:
            logger.warning("rag_sources table not found in Strapi DB. Skipping.")
            strapi_conn.rollback()
            return []


def map_role(role_type: str) -> str:
    """Map Strapi role type to new schema role enum."""
    mapping = {
        "researcher": "researcher",
        "admin": "admin",
        "superadmin": "superadmin",
        "authenticated": "researcher",  # Default Strapi role
    }
    return mapping.get(role_type, "researcher")


def migrate_users(strapi_conn, new_conn, users: list[dict]) -> dict[int, int]:
    """
    Migrate users. Returns a mapping of old_id -> new_id.
    Strapi uses bcrypt for passwords, which is compatible with passlib.
    """
    id_map = {}
    with new_conn.cursor() as cur:
        for user in users:
            role = map_role(user.get("role_type", "researcher"))
            is_active = not user.get("blocked", False)

            try:
                cur.execute(
                    """
                    INSERT INTO users (email, username, hashed_password, role, is_active, created_at, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                    """,
                    (
                        user["email"],
                        user["username"],
                        user["password"],  # bcrypt hash, directly compatible
                        role,
                        is_active,
                        user.get("created_at", datetime.now(timezone.utc)),
                        user.get("updated_at", datetime.now(timezone.utc)),
                    ),
                )
                new_id = cur.fetchone()[0]
                id_map[user["id"]] = new_id
                logger.info(f"  Migrated user: {user['email']} (old_id={user['id']} -> new_id={new_id})")
            except psycopg2.errors.UniqueViolation:
                new_conn.rollback()
                logger.warning(f"  Skipped duplicate user: {user['email']}")
            except Exception as e:
                new_conn.rollback()
                logger.error(f"  Failed to migrate user {user['email']}: {e}")

    new_conn.commit()
    return id_map


def migrate_api_keys(new_conn, api_keys: list[dict], user_id_map: dict[int, int]):
    """Migrate API keys with updated user ID references."""
    with new_conn.cursor() as cur:
        for key in api_keys:
            old_user_id = key.get("owner")
            new_user_id = user_id_map.get(old_user_id)

            if not new_user_id:
                logger.warning(f"  Skipped API key '{key['name']}' - owner not migrated")
                continue

            # Handle permissions
            permissions = key.get("permissions")
            if isinstance(permissions, dict):
                permissions = json.dumps(permissions)
            elif permissions is None:
                permissions = json.dumps({"query": True, "queryGpu": True, "sources": False})

            try:
                cur.execute(
                    """
                    INSERT INTO api_keys (name, key_hash, key_prefix, status, permissions,
                                         ip_whitelist, user_id, request_count, last_used_at,
                                         expires_at, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        key["name"],
                        key["key_hash"],
                        key["key_prefix"],
                        key.get("status", "active"),
                        permissions,
                        key.get("ip_whitelist"),
                        new_user_id,
                        key.get("request_count", 0),
                        key.get("last_used_at"),
                        key.get("expires_at"),
                        key.get("created_at", datetime.now(timezone.utc)),
                    ),
                )
                logger.info(f"  Migrated API key: {key['name']} (prefix={key['key_prefix']})")
            except Exception as e:
                new_conn.rollback()
                logger.error(f"  Failed to migrate API key '{key['name']}': {e}")

    new_conn.commit()


def migrate_rag_sources(new_conn, sources: list[dict]):
    """Migrate RAG source metadata."""
    with new_conn.cursor() as cur:
        for source in sources:
            # Map status
            status_map = {
                "indexed": "active",
                "pending": "inactive",
                "processing": "indexing",
                "failed": "error",
                "archived": "inactive",
            }
            status = status_map.get(source.get("status", "active"), "active")

            try:
                cur.execute(
                    """
                    INSERT INTO rag_sources (title, slug, source_type, source_url, status,
                                            content, category, language, chunks_count,
                                            last_indexed_at, indexing_error,
                                            created_at, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        source["title"],
                        source["slug"],
                        source.get("source_type", "webpage"),
                        source.get("source_url"),
                        status,
                        source.get("content"),
                        source.get("category"),
                        source.get("language", "es"),
                        source.get("chunks_count", 0),
                        source.get("last_indexed_at"),
                        source.get("indexing_error"),
                        source.get("created_at", datetime.now(timezone.utc)),
                        source.get("updated_at", datetime.now(timezone.utc)),
                    ),
                )
                logger.info(f"  Migrated RAG source: {source['title']}")
            except psycopg2.errors.UniqueViolation:
                new_conn.rollback()
                logger.warning(f"  Skipped duplicate source: {source['slug']}")
            except Exception as e:
                new_conn.rollback()
                logger.error(f"  Failed to migrate source '{source['title']}': {e}")

    new_conn.commit()


def main():
    parser = argparse.ArgumentParser(description="Migrate data from Strapi to Haystack backend")
    parser.add_argument(
        "--strapi-db",
        default=os.environ.get("STRAPI_DATABASE_URL", ""),
        help="Strapi PostgreSQL connection string",
    )
    parser.add_argument(
        "--new-db",
        default=os.environ.get("NEW_DATABASE_URL", os.environ.get("DATABASE_URL_SYNC", "")),
        help="New backend PostgreSQL connection string",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print what would be migrated without executing")
    args = parser.parse_args()

    if not args.strapi_db or not args.new_db:
        logger.error("Both --strapi-db and --new-db connection strings are required.")
        sys.exit(1)

    logger.info("=" * 60)
    logger.info("Strapi -> Haystack Backend Migration")
    logger.info("=" * 60)

    # Connect
    strapi_conn = psycopg2.connect(args.strapi_db)
    new_conn = psycopg2.connect(args.new_db)

    try:
        # Fetch data
        logger.info("\n1. Fetching users from Strapi...")
        users = get_strapi_users(strapi_conn)
        logger.info(f"   Found {len(users)} users")

        logger.info("\n2. Fetching API keys from Strapi...")
        api_keys = get_strapi_api_keys(strapi_conn)
        logger.info(f"   Found {len(api_keys)} API keys")

        logger.info("\n3. Fetching RAG sources from Strapi...")
        rag_sources = get_strapi_rag_sources(strapi_conn)
        logger.info(f"   Found {len(rag_sources)} RAG sources")

        if args.dry_run:
            logger.info("\n[DRY RUN] Would migrate:")
            logger.info(f"  - {len(users)} users")
            logger.info(f"  - {len(api_keys)} API keys")
            logger.info(f"  - {len(rag_sources)} RAG sources")
            return

        # Migrate
        logger.info("\n4. Migrating users...")
        user_id_map = migrate_users(strapi_conn, new_conn, users)
        logger.info(f"   Migrated {len(user_id_map)} users")

        logger.info("\n5. Migrating API keys...")
        migrate_api_keys(new_conn, api_keys, user_id_map)

        logger.info("\n6. Migrating RAG sources...")
        migrate_rag_sources(new_conn, rag_sources)

        # Insert default system stats
        with new_conn.cursor() as cur:
            cur.execute("INSERT INTO system_stats (id) VALUES (1) ON CONFLICT DO NOTHING")
        new_conn.commit()

        logger.info("\n" + "=" * 60)
        logger.info("Migration complete!")
        logger.info("=" * 60)

    finally:
        strapi_conn.close()
        new_conn.close()


if __name__ == "__main__":
    main()
