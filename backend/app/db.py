"""
Database connection helpers.

Postgres uses a connection pool because storefront writes are bursty (one
request → multiple INSERTs in a transaction).

ClickHouse uses single-shot connections per request — the native protocol
is cheap to open, and the read workload here is light (a handful of
analytic queries per dashboard refresh).
"""
from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

import psycopg
from clickhouse_driver import Client
from psycopg_pool import ConnectionPool

from .config import settings

# ─── Postgres ────────────────────────────────────────────────────────────────
_pg_pool: ConnectionPool | None = None


def init_pg_pool() -> None:
    global _pg_pool
    conninfo = (
        f"host={settings.postgres_host} port={settings.postgres_port} "
        f"dbname={settings.postgres_db} user={settings.postgres_user} "
        f"password={settings.postgres_password}"
    )
    # min/max sized for a small demo. Bump for real load.
    _pg_pool = ConnectionPool(conninfo, min_size=1, max_size=5, open=True)


def close_pg_pool() -> None:
    if _pg_pool is not None:
        _pg_pool.close()


@contextmanager
def pg_conn() -> Iterator[psycopg.Connection]:
    if _pg_pool is None:
        raise RuntimeError("Postgres pool not initialised")
    with _pg_pool.connection() as conn:
        yield conn


# ─── ClickHouse ──────────────────────────────────────────────────────────────
def ch_client() -> Client:
    """A fresh ClickHouse client per call. Cheap, thread-safe-ish (callers don't share)."""
    return Client(
        host=settings.clickhouse_host,
        port=settings.clickhouse_port,
        database=settings.clickhouse_db,
        user=settings.clickhouse_user,
        password=settings.clickhouse_password,
    )
