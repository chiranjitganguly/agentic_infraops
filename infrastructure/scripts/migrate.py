"""PostgreSQL migration runner.

Applies SQL migration files from infrastructure/db/migrations/ in ascending
filename order. Tracks applied migrations in a `schema_migrations` table so
each file is applied exactly once.

Usage:
    python infrastructure/scripts/migrate.py
    python infrastructure/scripts/migrate.py --dry-run
"""
from __future__ import annotations

import argparse
import asyncio
import os
import re
import sys
from pathlib import Path

import asyncpg


MIGRATIONS_DIR = Path(__file__).parent.parent / "db" / "migrations"
MIGRATION_TABLE = "schema_migrations"


async def ensure_migrations_table(conn: asyncpg.Connection) -> None:
    await conn.execute(f"""
        CREATE TABLE IF NOT EXISTS {MIGRATION_TABLE} (
            filename TEXT PRIMARY KEY,
            applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)


async def applied_migrations(conn: asyncpg.Connection) -> set[str]:
    rows = await conn.fetch(f"SELECT filename FROM {MIGRATION_TABLE}")
    return {row["filename"] for row in rows}


def migration_files() -> list[Path]:
    if not MIGRATIONS_DIR.exists():
        return []
    files = sorted(
        p for p in MIGRATIONS_DIR.iterdir()
        if p.suffix == ".sql" and re.match(r"^\d{3}_", p.name)
    )
    return files


async def run_migrations(dry_run: bool = False) -> None:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        print("ERROR: DATABASE_URL environment variable is not set", file=sys.stderr)
        sys.exit(1)

    conn = await asyncpg.connect(database_url)
    try:
        await ensure_migrations_table(conn)
        applied = await applied_migrations(conn)
        pending = [f for f in migration_files() if f.name not in applied]

        if not pending:
            print("All migrations already applied — nothing to do.")
            return

        for migration_file in pending:
            sql = migration_file.read_text(encoding="utf-8")
            print(f"{'[DRY-RUN] ' if dry_run else ''}Applying {migration_file.name}...")
            if not dry_run:
                async with conn.transaction():
                    await conn.execute(sql)
                    await conn.execute(
                        f"INSERT INTO {MIGRATION_TABLE} (filename) VALUES ($1)",
                        migration_file.name,
                    )
                print(f"  ✓ {migration_file.name} applied.")
            else:
                print(f"  (would apply {len(sql)} bytes of SQL)")

        print(f"\n{'[DRY-RUN] ' if dry_run else ''}Migration complete. {len(pending)} file(s) processed.")
    finally:
        await conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run PostgreSQL migrations")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be applied without executing")
    args = parser.parse_args()
    asyncio.run(run_migrations(dry_run=args.dry_run))


if __name__ == "__main__":
    main()
