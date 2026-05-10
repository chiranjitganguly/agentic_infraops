"""asyncpg connection pool factory.

Reads DATABASE_URL from the environment. Provides get_pool() async context
manager and a module-level pool for services that hold it across requests.
"""
from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator

import asyncpg


_pool: asyncpg.Pool | None = None


async def create_pool(
    dsn: str | None = None,
    min_size: int = 2,
    max_size: int = 10,
    command_timeout: float = 30.0,
) -> asyncpg.Pool:
    """Create and return a new connection pool."""
    database_url = dsn or os.environ.get("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL environment variable is not set")

    return await asyncpg.create_pool(
        dsn=database_url,
        min_size=min_size,
        max_size=max_size,
        command_timeout=command_timeout,
        # Ensure asyncpg returns UUIDs as uuid.UUID objects, not strings
        init=_init_connection,
    )


async def _init_connection(conn: asyncpg.Connection) -> None:
    await conn.set_type_codec(
        "uuid",
        encoder=str,
        decoder=lambda val: val,
        schema="pg_catalog",
        format="text",
    )


async def init_pool(
    dsn: str | None = None,
    min_size: int = 2,
    max_size: int = 10,
) -> None:
    """Initialise the module-level pool. Call once at service startup."""
    global _pool
    _pool = await create_pool(dsn=dsn, min_size=min_size, max_size=max_size)


async def close_pool() -> None:
    """Close the module-level pool. Call at service shutdown."""
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


def get_pool() -> asyncpg.Pool:
    """Return the module-level pool. Raises if init_pool() has not been called."""
    if _pool is None:
        raise RuntimeError("Database pool not initialised. Call init_pool() at startup.")
    return _pool


@asynccontextmanager
async def acquire() -> AsyncGenerator[asyncpg.Connection, None]:
    """Acquire a connection from the module-level pool."""
    pool = get_pool()
    async with pool.acquire() as conn:
        yield conn


@asynccontextmanager
async def transaction() -> AsyncGenerator[asyncpg.Connection, None]:
    """Acquire a connection and begin a transaction."""
    async with acquire() as conn:
        async with conn.transaction():
            yield conn
