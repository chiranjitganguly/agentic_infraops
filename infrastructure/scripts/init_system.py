"""InfraOps system initialiser — run once at stack startup.

Idempotent: safe to run on every boot. Skips steps already done.

Steps:
  1. Wait for PostgreSQL to accept connections
  2. Run DB migrations
  3. Wait for PubSub emulator to be reachable
  4. Create PubSub topics and subscriptions (emulator only)
  5. Create default users if not already present
"""
from __future__ import annotations

import asyncio
import base64
import os
import secrets
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import asyncpg
import bcrypt
import httpx

# ─── Configuration ────────────────────────────────────────────────────────────

DATABASE_URL   = os.environ["DATABASE_URL"]
GCP_PROJECT_ID = os.environ.get("GCP_PROJECT_ID", "local-dev")
PUBSUB_HOST    = os.environ.get("PUBSUB_EMULATOR_HOST", "")   # e.g. pubsub-emulator:8085

DEFAULT_USER_ID   = os.environ.get("DEFAULT_USER_ID",   "cg4ai@gmail.com")
DEFAULT_USER_ROLE = os.environ.get("DEFAULT_USER_ROLE", "developer")
DEFAULT_PASSWORD  = os.environ.get("DEFAULT_PASSWORD",  "password")

PLATFORM_USER_ID   = os.environ.get("PLATFORM_USER_ID",   "platformengg@infraops.com")
PLATFORM_USER_ROLE = os.environ.get("PLATFORM_USER_ROLE", "platform_engineer")
PLATFORM_PASSWORD  = os.environ.get("PLATFORM_PASSWORD",  "password")

# In Docker the script is copied to /app/init_system.py with migrations at /app/migrations.
# Locally the script lives at infrastructure/scripts/init_system.py with migrations at
# infrastructure/db/migrations.
_docker_migrations = Path("/app/migrations")
MIGRATIONS_DIR = _docker_migrations if _docker_migrations.exists() else Path(__file__).parent.parent / "db" / "migrations"

TOPICS = [
    f"projects/{GCP_PROJECT_ID}/topics/infraops.provisioning.requests",
    f"projects/{GCP_PROJECT_ID}/topics/infraops.provisioning.status",
    f"projects/{GCP_PROJECT_ID}/topics/infraops.audit.events",
]

SUBSCRIPTIONS = {
    f"projects/{GCP_PROJECT_ID}/topics/infraops.provisioning.requests":
        f"projects/{GCP_PROJECT_ID}/subscriptions/infraops-provisioning-requests-vm-sub",
    f"projects/{GCP_PROJECT_ID}/topics/infraops.provisioning.status":
        f"projects/{GCP_PROJECT_ID}/subscriptions/infraops-provisioning-status-sub",
}

API_KEY_BYTES       = 32
API_KEY_EXPIRY_DAYS = 365

# ─── Helpers ─────────────────────────────────────────────────────────────────

def _log(msg: str) -> None:
    print(f"[infraops-init] {msg}", flush=True)


def _generate_api_key() -> tuple[str, str]:
    raw = secrets.token_bytes(API_KEY_BYTES)
    plaintext = base64.urlsafe_b64encode(raw).decode()
    hashed = bcrypt.hashpw(plaintext.encode(), bcrypt.gensalt(rounds=12)).decode()
    return plaintext, hashed


# ─── Step 1 & 2: PostgreSQL + migrations ─────────────────────────────────────

async def wait_for_postgres(retries: int = 30, delay: float = 2.0) -> asyncpg.Connection:
    for attempt in range(1, retries + 1):
        try:
            conn = await asyncpg.connect(DATABASE_URL)
            _log("PostgreSQL ready.")
            return conn
        except Exception as exc:
            _log(f"Waiting for PostgreSQL ({attempt}/{retries}): {exc}")
            if attempt == retries:
                raise
            await asyncio.sleep(delay)
    raise RuntimeError("PostgreSQL never became ready")


async def run_migrations(conn: asyncpg.Connection) -> None:
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS schema_migrations (
            filename TEXT PRIMARY KEY,
            applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    applied: set[str] = {r["filename"] for r in await conn.fetch("SELECT filename FROM schema_migrations")}

    pending = sorted(
        p for p in MIGRATIONS_DIR.glob("*.sql")
        if p.name not in applied
    )
    if not pending:
        _log("Migrations: all up to date.")
        return

    for f in pending:
        _log(f"Applying migration: {f.name}")
        async with conn.transaction():
            await conn.execute(f.read_text())
            await conn.execute("INSERT INTO schema_migrations (filename) VALUES ($1)", f.name)
        _log(f"  ✓ {f.name}")


# ─── Step 3 & 4: PubSub emulator topics + subscriptions ──────────────────────

def _pubsub_base_url() -> str | None:
    if not PUBSUB_HOST:
        return None
    host = PUBSUB_HOST if PUBSUB_HOST.startswith("http") else f"http://{PUBSUB_HOST}"
    return host


def wait_for_pubsub(retries: int = 30, delay: float = 2.0) -> bool:
    base = _pubsub_base_url()
    if not base:
        _log("PubSub: no emulator configured, skipping topic setup.")
        return False
    for attempt in range(1, retries + 1):
        try:
            r = httpx.get(base, timeout=5)
            if r.status_code < 500:
                _log("PubSub emulator ready.")
                return True
        except Exception as exc:
            _log(f"Waiting for PubSub emulator ({attempt}/{retries}): {exc}")
        if attempt < retries:
            time.sleep(delay)
    _log("WARNING: PubSub emulator not reachable — topics not created.")
    return False


def create_pubsub_resources() -> None:
    base = _pubsub_base_url()
    if not base:
        return

    with httpx.Client(timeout=10) as client:
        for topic in TOPICS:
            url = f"{base}/v1/{topic}"
            r = client.put(url, json={})
            if r.status_code in (200, 409):
                _log(f"PubSub topic ready: {topic.split('/')[-1]}")
            else:
                _log(f"WARNING: topic create returned {r.status_code}: {topic}")

        for topic, sub in SUBSCRIPTIONS.items():
            url = f"{base}/v1/{sub}"
            r = client.put(url, json={"topic": topic, "ackDeadlineSeconds": 60})
            if r.status_code in (200, 409):
                _log(f"PubSub subscription ready: {sub.split('/')[-1]}")
            else:
                _log(f"WARNING: subscription create returned {r.status_code}: {sub}")


# ─── Step 5: Users ───────────────────────────────────────────────────────────

async def ensure_user(
    conn: asyncpg.Connection,
    user_id: str,
    role: str,
    password: str,
) -> str | None:
    """Create user if not present. Returns plaintext API key if newly created, else None."""
    existing = await conn.fetchrow(
        "SELECT user_id FROM user_roles WHERE user_id = $1", user_id
    )
    if existing:
        # Back-fill password_hash if the column was added after user was created.
        has_pw = await conn.fetchval(
            "SELECT password_hash FROM user_roles WHERE user_id = $1", user_id
        )
        if not has_pw:
            pw_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=12)).decode()
            await conn.execute(
                "UPDATE user_roles SET password_hash = $1 WHERE user_id = $2",
                pw_hash, user_id,
            )
            _log(f"Password set for existing user: {user_id}")
        else:
            _log(f"User already exists: {user_id}")
        return None

    plaintext, key_hash = _generate_api_key()
    pw_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=12)).decode()
    now = datetime.now(tz=timezone.utc)
    expires_at = now + timedelta(days=API_KEY_EXPIRY_DAYS)

    await conn.execute(
        """
        INSERT INTO user_roles (
            user_id, role, api_key_hash, api_key_expires_at, password_hash,
            daily_provisioning_count, daily_count_reset_at, created_at, updated_at
        ) VALUES ($1, $2, $3, $4, $5, 0, $6, $6, $6)
        """,
        user_id, role, key_hash, expires_at, pw_hash, now,
    )
    _log(f"Created user: {user_id}  role={role}")
    return plaintext


# ─── Main ─────────────────────────────────────────────────────────────────────

async def main() -> None:
    _log("=== InfraOps system init starting ===")

    # PostgreSQL
    conn = await wait_for_postgres()
    try:
        await run_migrations(conn)
        dev_key = await ensure_user(conn, DEFAULT_USER_ID, DEFAULT_USER_ROLE, DEFAULT_PASSWORD)
        plat_key = await ensure_user(conn, PLATFORM_USER_ID, PLATFORM_USER_ROLE, PLATFORM_PASSWORD)
    finally:
        await conn.close()

    # PubSub
    if wait_for_pubsub():
        create_pubsub_resources()

    # Print API key banner for any newly created users
    new_users = []
    if dev_key:
        new_users.append((DEFAULT_USER_ID, DEFAULT_USER_ROLE, dev_key))
    if plat_key:
        new_users.append((PLATFORM_USER_ID, PLATFORM_USER_ROLE, plat_key))

    if new_users:
        print("\n" + "=" * 60)
        print("  NEW USER API KEYS (store these — shown once)")
        print("=" * 60)
        key_lines = []
        for uid, role, key in new_users:
            print(f"  User : {uid}  role={role}")
            print(f"  Key  : {key}")
            print()
            key_lines.append(f"{uid}:{key}")
        print("=" * 60 + "\n")
        key_path = Path("/tmp/infraops_api_key.txt")
        key_path.write_text("\n".join(key_lines) + "\n")
        _log(f"API keys written to {key_path}")

    _log("=== Init complete ===")


if __name__ == "__main__":
    asyncio.run(main())
