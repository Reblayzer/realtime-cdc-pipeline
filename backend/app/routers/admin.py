"""
Admin endpoints — read-only views of the CDC pipeline's state.

Everything here reads from ClickHouse (the warehouse), *not* from Postgres.
That's the whole point of the pipeline: the source of truth for analytics
lives in the warehouse. The one exception is the lag panel, which needs
both sides to compute the delta.

All endpoints are fast (sub-100ms typical) so the frontend can poll them
every 3 seconds without overloading anything.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Query

from ..db import ch_client, pg_conn
from ..models import (
    DashboardMetrics, HealthMetrics, MinuteBucket, TopSku,
    RecentEvent, DlqRow,
)

log = logging.getLogger("app.admin")
router = APIRouter()


# Email marker used by the storefront router. Anything with our pattern is
# clearly a user-placed order vs. a synthetic data-gen order — the admin UI
# highlights these so the "I just placed that" demo is visually obvious.
STOREFRONT_EMAIL_DOMAINS = ("example.com",)   # data-gen uses fake.email() -> example.com etc.
# In practice, storefront orders come from real-looking email addresses the
# user types in. The simpler heuristic: data-gen orders are 'pending' for
# microseconds before the generator advances them; user orders stay 'pending'.
# We surface both signals to the frontend so it can decide.


@router.get("/health", response_model=HealthMetrics, summary="Pipeline health snapshot")
def health() -> HealthMetrics:
    # Postgres truth
    with pg_conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM orders")
        pg_orders = cur.fetchone()[0]

    # ClickHouse warehouse state
    ch = ch_client()
    ch_orders = ch.execute("SELECT count() FROM analytics.v_orders")[0][0]
    dlq_rows = ch.execute("SELECT count() FROM analytics.cdc_dead_letter")[0][0]
    latency = ch.execute("""
        SELECT
            round(quantile(0.5)(latency_ms)),
            round(quantile(0.95)(latency_ms))
        FROM (
            SELECT toUnixTimestamp64Milli(_ingested_at) - _op_ts_ms AS latency_ms
            FROM analytics.orders
            WHERE _ingested_at >= now() - INTERVAL 1 MINUTE
              AND latency_ms BETWEEN 0 AND 60000
        )
    """)
    p50, p95 = (latency[0] if latency else (None, None))

    lag = pg_orders - ch_orders
    # Health gauge — lenient because we expect ~5-15s of normal lag.
    if lag <= 50 and dlq_rows < 100:
        status = "healthy"
    elif lag <= 500:
        status = "degraded"
    else:
        status = "down"

    return HealthMetrics(
        postgres_orders=pg_orders,
        clickhouse_orders=ch_orders,
        lag_rows=lag,
        dlq_rows=dlq_rows,
        latency_p50_ms=int(p50) if p50 is not None else None,
        latency_p95_ms=int(p95) if p95 is not None else None,
        status=status,
    )


@router.get("/metrics", response_model=DashboardMetrics, summary="Full dashboard payload")
def metrics() -> DashboardMetrics:
    """Single round-trip for the dashboard. Returns the per-minute time series, top SKUs, and health."""
    ch = ch_client()

    # 1. orders/minute over the last 30 minutes
    bucket_rows = ch.execute("""
        SELECT toStartOfMinute(created_at)   AS minute,
               count()                        AS orders,
               sum(total_cents) / 100.0       AS revenue_eur
        FROM analytics.v_orders
        WHERE created_at >= now() - INTERVAL 30 MINUTE
        GROUP BY minute
        ORDER BY minute
    """)
    orders_per_minute = [
        MinuteBucket(minute=r[0], orders=r[1], revenue_eur=float(r[2]))
        for r in bucket_rows
    ]

    # 2. top SKUs by units sold (lifetime)
    sku_rows = ch.execute("""
        SELECT sku,
               sum(qty)                                  AS units,
               sum(qty * unit_price_cents) / 100.0       AS revenue_eur
        FROM analytics.v_order_items
        GROUP BY sku
        ORDER BY units DESC
        LIMIT 10
    """)
    top_skus = [
        TopSku(sku=r[0], units=int(r[1]), revenue_eur=float(r[2]))
        for r in sku_rows
    ]

    return DashboardMetrics(
        orders_per_minute=orders_per_minute,
        top_skus=top_skus,
        health=health(),
    )


@router.get("/recent-events", response_model=list[RecentEvent], summary="Recent CDC events from the orders stream")
def recent_events(limit: int = Query(default=30, ge=1, le=200)) -> list[RecentEvent]:
    ch = ch_client()
    rows = ch.execute("""
        SELECT
            'orders'                                                AS tbl,
            o._op                                                   AS op,
            o.id                                                    AS row_id,
            o._op_ts_ms                                             AS op_ts_ms,
            o._ingested_at                                          AS ingested_at,
            toInt64(toUnixTimestamp64Milli(o._ingested_at) - o._op_ts_ms) AS latency_ms,
            o.status                                                AS status,
            o.total_cents                                           AS total_cents,
            c.email                                                 AS email
        FROM analytics.orders o
        LEFT JOIN analytics.v_customers c ON c.id = o.customer_id
        ORDER BY o._ingested_at DESC
        LIMIT %(lim)s
    """, {"lim": limit})

    out: list[RecentEvent] = []
    for r in rows:
        email = r[8]
        # data-gen uses Faker which produces emails ending in example.com / .net / .org.
        # Real storefront users will type in something different (gmail, yahoo, etc.),
        # so this heuristic is good-enough for highlighting "I just placed that".
        is_storefront = isinstance(email, str) and not email.endswith((
            "@example.com", "@example.net", "@example.org",
        ))
        out.append(RecentEvent(
            table=r[0],
            op=r[1],
            row_id=int(r[2]),
            op_ts_ms=int(r[3]),
            ingested_at=r[4] if isinstance(r[4], datetime) else datetime.now(timezone.utc),
            latency_ms=max(0, int(r[5])) if r[5] is not None else None,
            status=r[6],
            total_cents=int(r[7]) if r[7] is not None else None,
            customer_email=email,
            is_storefront_order=is_storefront,
        ))
    return out


@router.get("/dlq", response_model=list[DlqRow], summary="Dead-letter table contents")
def dlq(limit: int = Query(default=20, ge=1, le=200)) -> list[DlqRow]:
    ch = ch_client()
    rows = ch.execute("""
        SELECT failed_at, kafka_topic, kafka_offset, error_message, raw_value
        FROM analytics.cdc_dead_letter
        ORDER BY failed_at DESC
        LIMIT %(lim)s
    """, {"lim": limit})
    return [
        DlqRow(
            failed_at=r[0] if isinstance(r[0], datetime) else datetime.now(timezone.utc),
            kafka_topic=r[1],
            kafka_offset=int(r[2]),
            error=r[3],
            raw_value=r[4][:500],   # truncate for over-the-wire frugality
        )
        for r in rows
    ]
