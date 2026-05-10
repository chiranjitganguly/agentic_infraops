"""Create a user with an API key in the InfraOps platform.

Inserts a UserRole row into PostgreSQL, generates a cryptographically
random API key, bcrypt-hashes it for storage, and prints the plaintext
key once. The key is never stored in plaintext.

Usage:
    python infrastructure/scripts/create_user.py --user-id user@example.com --role developer
    python infrastructure/scripts/create_user.py --user-id pe@example.com --role platform_engineer
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import os
import secrets
import sys
from datetime import datetime, timedelta, timezone

import asyncpg
import bcrypt


API_KEY_BYTES = 32
API_KEY_EXPIRY_DAYS = 90


def generate_api_key() -> tuple[str, str]:
    """Return (plaintext_key, bcrypt_hash)."""
    raw = secrets.token_bytes(API_KEY_BYTES)
    plaintext = base64.urlsafe_b64encode(raw).decode()
    hashed = bcrypt.hashpw(plaintext.encode(), bcrypt.gensalt(rounds=12)).decode()
    return plaintext, hashed


async def create_user(user_id: str, role: str) -> None:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        print("ERROR: DATABASE_URL environment variable is not set", file=sys.stderr)
        sys.exit(1)

    plaintext_key, key_hash = generate_api_key()
    now = datetime.now(tz=timezone.utc)
    expires_at = now + timedelta(days=API_KEY_EXPIRY_DAYS)

    conn = await asyncpg.connect(database_url)
    try:
        existing = await conn.fetchrow(
            "SELECT user_id FROM user_roles WHERE user_id = $1", user_id
        )
        if existing:
            print(f"ERROR: User '{user_id}' already exists.", file=sys.stderr)
            sys.exit(1)

        await conn.execute(
            """
            INSERT INTO user_roles (
                user_id, role, api_key_hash, api_key_expires_at,
                daily_provisioning_count, daily_count_reset_at, created_at, updated_at
            ) VALUES ($1, $2, $3, $4, 0, $5, $5, $5)
            """,
            user_id,
            role,
            key_hash,
            expires_at,
            now,
        )
    finally:
        await conn.close()

    print(f"\nUser created successfully.")
    print(f"  User ID : {user_id}")
    print(f"  Role    : {role}")
    print(f"  Expires : {expires_at.date()} (in {API_KEY_EXPIRY_DAYS} days)")
    print(f"\nAPI Key (store securely — shown only once):")
    print(f"\n  {plaintext_key}\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Create an InfraOps platform user with an API key")
    parser.add_argument("--user-id", required=True, help="User email address (used as user_id)")
    parser.add_argument(
        "--role",
        required=True,
        choices=["developer", "platform_engineer"],
        help="User role",
    )
    args = parser.parse_args()
    asyncio.run(create_user(args.user_id, args.role))


if __name__ == "__main__":
    main()
