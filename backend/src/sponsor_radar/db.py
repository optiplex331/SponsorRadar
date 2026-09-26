from __future__ import annotations

import os
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

MIGRATIONS_DIR = Path(__file__).with_name("migrations")
DEFAULT_URL = "postgresql://radar:radar@127.0.0.1:5433/radar"
MIGRATE_LOCK = 0x5350_5241  # pg_advisory_lock key shared by every `migrate` caller


def connect(url: str | None = None) -> psycopg.Connection:
    return psycopg.connect(url or os.environ.get("DATABASE_URL", DEFAULT_URL), row_factory=dict_row)


def migrate(conn: psycopg.Connection) -> list[str]:
    """Apply pending forward-only migrations in filename order.

    Holds a session advisory lock so the web initContainer and the collector never apply the same file twice.
    """
    conn.execute("SELECT pg_advisory_lock(%s)", (MIGRATE_LOCK,))
    try:
        return _apply_pending(conn)
    finally:
        conn.rollback()
        conn.execute("SELECT pg_advisory_unlock(%s)", (MIGRATE_LOCK,))
        conn.commit()


def _apply_pending(conn: psycopg.Connection) -> list[str]:
    conn.execute("CREATE TABLE IF NOT EXISTS schema_migrations (name text PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now())")
    applied = {row["name"] for row in conn.execute("SELECT name FROM schema_migrations")}
    newly_applied = []
    for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
        if path.name in applied:
            continue
        with conn.transaction():
            conn.execute(path.read_text())
            conn.execute("INSERT INTO schema_migrations (name) VALUES (%s)", (path.name,))
        newly_applied.append(path.name)
    conn.commit()
    return newly_applied
