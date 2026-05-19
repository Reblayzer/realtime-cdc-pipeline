"""
Workload simulator for the CDC pipeline.

Continuously generates realistic INSERT / UPDATE / DELETE traffic against the
Postgres source DB. Every write becomes a CDC event downstream — that's the
whole point of this script.

Operation mix (configurable via env):
    - 50%  insert a new order for an existing customer
    - 25%  advance an existing order's status (pending -> paid -> shipped -> delivered)
    - 10%  add an item to an existing pending/paid order
    - 10%  insert a new customer (with one starter order)
    -  5%  cancel + delete a pending order (UPDATE then DELETE, both captured)

Tuning knobs (all via environment variables, all optional):
    POSTGRES_HOST       host name of the DB (default: postgres)
    POSTGRES_PORT       port (default: 5432)
    POSTGRES_DB         database (default: shop)
    POSTGRES_USER       user (default: cdc_user)
    POSTGRES_PASSWORD   password (default: cdc_pass)
    OPS_PER_SECOND      target ops/sec, float, default 2.0
    JITTER              0..1, fractional sleep jitter, default 0.3
    LOG_EVERY           print a summary every N ops, default 20
"""

from __future__ import annotations

import json
import logging
import os
import random
import signal
import sys
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Iterable

import psycopg
from faker import Faker

# ── logging ────────────────────────────────────────────────────────────────
# JSON-ish single-line logs so they are grep-able from `docker compose logs`.
logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format='{"ts":"%(asctime)s","level":"%(levelname)s","component":"data-gen","msg":%(message)s}',
)
log = logging.getLogger(__name__)


# ── config ─────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class Config:
    host: str = os.environ.get("POSTGRES_HOST", "postgres")
    port: int = int(os.environ.get("POSTGRES_PORT", "5432"))
    db: str = os.environ.get("POSTGRES_DB", "shop")
    user: str = os.environ.get("POSTGRES_USER", "cdc_user")
    password: str = os.environ.get("POSTGRES_PASSWORD", "cdc_pass")
    ops_per_second: float = float(os.environ.get("OPS_PER_SECOND", "2.0"))
    jitter: float = float(os.environ.get("JITTER", "0.3"))
    log_every: int = int(os.environ.get("LOG_EVERY", "20"))


# ── stats counter ──────────────────────────────────────────────────────────
@dataclass
class Stats:
    ops_total: int = 0
    by_kind: dict[str, int] = field(default_factory=dict)

    def bump(self, kind: str) -> None:
        self.ops_total += 1
        self.by_kind[kind] = self.by_kind.get(kind, 0) + 1


# ── reference data ─────────────────────────────────────────────────────────
SKUS = [
    ("SKU-COFFEE-250G", 2495),
    ("SKU-COFFEE-1KG", 8995),
    ("SKU-MUG-CERAMIC", 1299),
    ("SKU-MUG-STEEL", 1799),
    ("SKU-FRENCHPRESS", 12500),
    ("SKU-FILTERS-100", 1166),
    ("SKU-GRINDER-MANUAL", 4499),
    ("SKU-GRINDER-ELEC", 9999),
    ("SKU-DESCALER", 899),
    ("SKU-BEANS-SAMPLER", 3499),
]
COUNTRIES = ["IT", "DE", "FR", "ES", "NL", "BE", "PT", "AT", "IE", "PL"]
STATUS_TRANSITIONS = {
    "pending": ["paid", "cancelled"],
    "paid": ["shipped"],
    "shipped": ["delivered"],
    "delivered": [],   # terminal
    "cancelled": [],   # terminal
}


# ── operations ─────────────────────────────────────────────────────────────
fake = Faker()


def op_insert_customer(conn: psycopg.Connection) -> str:
    """Sign up a new customer, with one starter order."""
    email = fake.unique.email()
    name = fake.name()
    country = random.choice(COUNTRIES)
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO customers (email, full_name, country) VALUES (%s, %s, %s) RETURNING id",
            (email, name, country),
        )
        cid = cur.fetchone()[0]
        sku, price = random.choice(SKUS)
        qty = random.randint(1, 3)
        cur.execute(
            "INSERT INTO orders (customer_id, status, total_cents, currency) "
            "VALUES (%s, 'pending', %s, 'EUR') RETURNING id",
            (cid, price * qty),
        )
        oid = cur.fetchone()[0]
        cur.execute(
            "INSERT INTO order_items (order_id, sku, qty, unit_price_cents) VALUES (%s, %s, %s, %s)",
            (oid, sku, qty, price),
        )
    return "insert_customer"


def op_insert_order(conn: psycopg.Connection) -> str:
    """New order for an existing customer."""
    with conn.cursor() as cur:
        cur.execute("SELECT id FROM customers ORDER BY random() LIMIT 1")
        row = cur.fetchone()
        if not row:
            return op_insert_customer(conn)
        cid = row[0]
        sku, price = random.choice(SKUS)
        qty = random.randint(1, 4)
        cur.execute(
            "INSERT INTO orders (customer_id, status, total_cents, currency) "
            "VALUES (%s, 'pending', %s, 'EUR') RETURNING id",
            (cid, price * qty),
        )
        oid = cur.fetchone()[0]
        cur.execute(
            "INSERT INTO order_items (order_id, sku, qty, unit_price_cents) VALUES (%s, %s, %s, %s)",
            (oid, sku, qty, price),
        )
    return "insert_order"


def op_advance_status(conn: psycopg.Connection) -> str:
    """Move an order along its lifecycle. Each transition is a CDC UPDATE."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, status FROM orders "
            "WHERE status NOT IN ('delivered', 'cancelled') "
            "ORDER BY random() LIMIT 1"
        )
        row = cur.fetchone()
        if not row:
            return op_insert_order(conn)
        oid, status = row
        nexts = STATUS_TRANSITIONS.get(status, [])
        if not nexts:
            return op_insert_order(conn)
        new_status = random.choice(nexts)
        cur.execute("UPDATE orders SET status = %s WHERE id = %s", (new_status, oid))
    return f"advance_status:{status}->{new_status}"


def op_add_item(conn: psycopg.Connection) -> str:
    """Add an item to an in-progress (pending/paid) order. Bumps order total."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id FROM orders WHERE status IN ('pending','paid') "
            "ORDER BY random() LIMIT 1"
        )
        row = cur.fetchone()
        if not row:
            return op_insert_order(conn)
        oid = row[0]
        sku, price = random.choice(SKUS)
        qty = random.randint(1, 2)
        cur.execute(
            "INSERT INTO order_items (order_id, sku, qty, unit_price_cents) VALUES (%s, %s, %s, %s)",
            (oid, sku, qty, price),
        )
        # Keep orders.total_cents consistent — also produces a second CDC event.
        cur.execute(
            "UPDATE orders SET total_cents = total_cents + %s WHERE id = %s",
            (price * qty, oid),
        )
    return "add_item"


def op_cancel_and_delete(conn: psycopg.Connection) -> str:
    """Cancel a pending order, then delete it. Both events flow downstream."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id FROM orders WHERE status = 'pending' ORDER BY random() LIMIT 1"
        )
        row = cur.fetchone()
        if not row:
            return op_insert_order(conn)
        oid = row[0]
        cur.execute("UPDATE orders SET status = 'cancelled' WHERE id = %s", (oid,))
        # ON DELETE CASCADE on order_items.order_id also produces delete events
        # for the items — nice for testing fan-out in the Spark job.
        cur.execute("DELETE FROM orders WHERE id = %s", (oid,))
    return "cancel_and_delete"


OPS: list[tuple[float, callable]] = [
    (0.50, op_insert_order),
    (0.25, op_advance_status),
    (0.10, op_add_item),
    (0.10, op_insert_customer),
    (0.05, op_cancel_and_delete),
]


def pick_op() -> callable:
    r = random.random()
    cum = 0.0
    for weight, fn in OPS:
        cum += weight
        if r <= cum:
            return fn
    return OPS[-1][1]


# ── main loop ──────────────────────────────────────────────────────────────
@contextmanager
def connect(cfg: Config) -> Iterable[psycopg.Connection]:
    conn = psycopg.connect(
        host=cfg.host,
        port=cfg.port,
        dbname=cfg.db,
        user=cfg.user,
        password=cfg.password,
        autocommit=True,   # one CDC event per op, easier to read downstream
    )
    try:
        yield conn
    finally:
        conn.close()


def wait_for_db(cfg: Config, timeout_s: int = 60) -> None:
    """Block until Postgres is ready. Important on cold compose-up."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            with psycopg.connect(
                host=cfg.host, port=cfg.port, dbname=cfg.db,
                user=cfg.user, password=cfg.password,
                connect_timeout=3,
            ) as c:
                c.execute("SELECT 1")
            log.info(json.dumps({"event": "db_ready", "host": cfg.host, "port": cfg.port}))
            return
        except Exception as e:
            log.info(json.dumps({"event": "waiting_for_db", "error": str(e)[:120]}))
            time.sleep(2)
    raise SystemExit("Postgres not reachable within timeout")


def main() -> None:
    cfg = Config()
    log.info(json.dumps({"event": "starting", "config": cfg.__dict__}))

    stop = {"flag": False}

    def _sig(_sig, _frm):  # graceful shutdown so `docker compose down` is clean
        log.info(json.dumps({"event": "shutdown_signal"}))
        stop["flag"] = True

    signal.signal(signal.SIGTERM, _sig)
    signal.signal(signal.SIGINT, _sig)

    wait_for_db(cfg)

    stats = Stats()
    base_sleep = 1.0 / max(cfg.ops_per_second, 0.001)

    with connect(cfg) as conn:
        while not stop["flag"]:
            fn = pick_op()
            try:
                kind = fn(conn)
                stats.bump(kind.split(":")[0])
            except psycopg.Error as e:
                # The most common failure path is a transient DB hiccup — log and continue.
                log.warning(json.dumps({"event": "op_failed", "error": str(e)[:200]}))
                time.sleep(1.0)
                continue

            if stats.ops_total % cfg.log_every == 0:
                log.info(json.dumps({"event": "tick", "stats": stats.by_kind, "total": stats.ops_total}))

            jitter = random.uniform(1 - cfg.jitter, 1 + cfg.jitter)
            time.sleep(base_sleep * jitter)

    log.info(json.dumps({"event": "stopped", "stats": stats.by_kind, "total": stats.ops_total}))


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(0)
