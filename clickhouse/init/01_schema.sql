-- =============================================================================
-- ClickHouse warehouse schema.
--
-- Why ReplacingMergeTree?
--   CDC produces multiple events for the same row (insert, then 0..N updates,
--   then maybe a delete). The warehouse wants the "latest" version of each row
--   for analytics queries. ReplacingMergeTree dedupes by the ORDER BY key,
--   keeping the row with the highest value of the version column on merge.
--   We use `_op_ts_ms` (the Debezium-supplied event timestamp) as the version.
--
-- A note on timestamp types
--   We use `DateTime64(3)` (without an explicit timezone). The ClickHouse JDBC
--   driver reports `DateTime64(N, 'TZ')` as JDBC type TIMESTAMP_WITH_TIMEZONE,
--   which Spark's JDBC dialect can't handle. The server runs in UTC by default,
--   so dropping the explicit `'UTC'` is purely a JDBC interop fix — semantics
--   are unchanged.
--
-- Why a separate `_is_deleted` column?
--   ClickHouse merges happen asynchronously in the background, and deletes are
--   hard in column stores. Treating delete as "insert a row with is_deleted=1
--   and a newer version" lets us absorb deletes through the same code path as
--   updates. Queries filter with `WHERE _is_deleted = 0`. With `FINAL` or
--   `argMax`, this gives correct results even before background merges run.
--
-- Why PARTITION BY toYYYYMM?
--   ClickHouse merges happen within a partition, so partitioning bounds the
--   work the engine has to do at merge time and makes time-range queries hit
--   far fewer parts. Monthly is the standard granularity for transactional data
--   measured in years; bump to weekly/daily at 10x volume.
--
-- The `_kafka_topic` / `_kafka_offset` columns are kept for lineage and to
-- support replay debugging — handy when an interviewer asks "what would you
-- do if you discover bad data on a specific day?"
-- =============================================================================

CREATE DATABASE IF NOT EXISTS analytics;

CREATE TABLE IF NOT EXISTS analytics.customers
(
    id            Int64,
    email         String,
    full_name     String,
    country       FixedString(2),
    created_at    DateTime64(3),
    updated_at    DateTime64(3),

    -- CDC metadata
    _op           LowCardinality(String),       -- 'c','u','d','r'
    _op_ts_ms     Int64,                        -- Debezium event timestamp (ms)
    _is_deleted   UInt8 DEFAULT 0,
    _kafka_topic  LowCardinality(String),
    _kafka_offset Int64,
    _ingested_at  DateTime64(3) DEFAULT now64(3)
)
ENGINE = ReplacingMergeTree(_op_ts_ms)
PARTITION BY toYYYYMM(created_at)
ORDER BY (id);

CREATE TABLE IF NOT EXISTS analytics.orders
(
    id            Int64,
    customer_id   Int64,
    status        LowCardinality(String),
    total_cents   Int64,
    currency      FixedString(3),
    created_at    DateTime64(3),
    updated_at    DateTime64(3),

    _op           LowCardinality(String),
    _op_ts_ms     Int64,
    _is_deleted   UInt8 DEFAULT 0,
    _kafka_topic  LowCardinality(String),
    _kafka_offset Int64,
    _ingested_at  DateTime64(3) DEFAULT now64(3)
)
ENGINE = ReplacingMergeTree(_op_ts_ms)
PARTITION BY toYYYYMM(created_at)
ORDER BY (id);

CREATE TABLE IF NOT EXISTS analytics.order_items
(
    id                Int64,
    order_id          Int64,
    sku               LowCardinality(String),
    qty               Int32,
    unit_price_cents  Int64,
    created_at        DateTime64(3),
    updated_at        DateTime64(3),

    _op               LowCardinality(String),
    _op_ts_ms         Int64,
    _is_deleted       UInt8 DEFAULT 0,
    _kafka_topic      LowCardinality(String),
    _kafka_offset     Int64,
    _ingested_at      DateTime64(3) DEFAULT now64(3)
)
ENGINE = ReplacingMergeTree(_op_ts_ms)
PARTITION BY toYYYYMM(created_at)
ORDER BY (id);

-- =============================================================================
-- Dead-letter table for malformed Kafka records.
--
-- The Spark job catches parse errors and writes the offending raw payload here
-- instead of crashing the stream. Operators can then inspect, fix, and replay.
-- =============================================================================
CREATE TABLE IF NOT EXISTS analytics.cdc_dead_letter
(
    raw_value     String,
    error_message String,
    kafka_topic   LowCardinality(String),
    kafka_offset  Int64,
    kafka_partition Int32,
    failed_at     DateTime64(3) DEFAULT now64(3)
)
ENGINE = MergeTree
PARTITION BY toYYYYMM(failed_at)
ORDER BY (failed_at, kafka_topic, kafka_offset);

-- =============================================================================
-- "Latest-state" views: hide the CDC plumbing from BI users.
-- Using FINAL forces ClickHouse to merge on read — slower than a raw scan but
-- always correct. For high-traffic dashboards, materialize these into a
-- separate table on a schedule instead.
-- =============================================================================

CREATE OR REPLACE VIEW analytics.v_customers AS
SELECT id, email, full_name, country, created_at, updated_at
FROM analytics.customers FINAL
WHERE _is_deleted = 0;

CREATE OR REPLACE VIEW analytics.v_orders AS
SELECT id, customer_id, status, total_cents, currency, created_at, updated_at
FROM analytics.orders FINAL
WHERE _is_deleted = 0;

CREATE OR REPLACE VIEW analytics.v_order_items AS
SELECT id, order_id, sku, qty, unit_price_cents, created_at, updated_at
FROM analytics.order_items FINAL
WHERE _is_deleted = 0;
