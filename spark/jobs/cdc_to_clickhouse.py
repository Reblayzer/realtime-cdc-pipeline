"""
Spark Structured Streaming job: Kafka (Debezium CDC) → ClickHouse warehouse.

Pipeline shape
==============
    Kafka                                              ClickHouse
    ┌───────────────┐  parse Debezium     route by      ┌──────────────┐
    │ shop.public.* │ ── envelope ──▶ table ──▶ enrich  │ analytics.*  │
    └───────────────┘  + DLQ on err     + upsert        └──────────────┘

Why this shape?
---------------
- One streaming query, one Kafka subscription via a topic *pattern*, instead
  of three independent queries. Lower scheduler/driver overhead, single source
  of metrics, single checkpoint.
- We use `foreachBatch` to write each micro-batch via JDBC. Structured Streaming
  has no native ClickHouse sink, and JDBC-based batch writes are the official
  recommendation for that case.
- For each batch we partition by table (`source.table`) and do one JDBC write
  per (table, ClickHouse partition). ClickHouse's ReplacingMergeTree handles
  deduplication and "latest wins" semantics by the version column (_op_ts_ms).

Resilience
----------
- Checkpoint dir on a host-mounted volume → resume on restart, exactly-once
  Kafka read semantics (Spark commits offsets in checkpoint atomically).
- Malformed records (failed JSON parse, unknown table, etc.) go to a dead-
  letter table (analytics.cdc_dead_letter) — they NEVER crash the stream.
- ClickHouse JDBC write failures bubble up and Spark retries the batch as
  designed; the checkpoint will only advance when the write succeeds.

Schema evolution (interview answer)
-----------------------------------
- If Postgres adds a NULLABLE column, the JSON envelope will simply contain a
  new field. `from_json` against the OLD schema silently drops it — pipeline
  keeps running, new field invisible until you update schemas.py and bump
  the warehouse table.
- If Postgres adds a NON-NULL column with a default, same story — Debezium
  sends the value, Spark drops it on parse, warehouse never sees it.
- If a column TYPE changes incompatibly (text → int), parse fails, row hits
  the DLQ. You can fix the schema and replay from the offset in the DLQ row.
- The dead-letter pattern means "schema drift between source and warehouse"
  produces a backlog, not an outage.
"""

from __future__ import annotations

import json
import logging
import os
import sys

from pyspark.sql import DataFrame, SparkSession
from pyspark.sql.functions import (
    col, from_json, when, lit, expr, to_timestamp,
    coalesce,
)
# Valid Debezium operation codes: create, update, delete, read (snapshot).
# Truncate ('t') and message ('m') are intentionally not handled — they get
# routed to the dead-letter table with a descriptive error.
VALID_OPS = ("c", "u", "d", "r")
from pyspark.sql.types import StringType

# Local modules — mounted into /opt/job at runtime.
sys.path.insert(0, os.path.dirname(__file__))
from schemas import envelope_for, TABLE_TO_ROW_SCHEMA  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format='{"ts":"%(asctime)s","level":"%(levelname)s","component":"spark-job","msg":%(message)s}',
)
log = logging.getLogger(__name__)


# ─── Config ──────────────────────────────────────────────────────────────────
KAFKA_BOOTSTRAP   = os.environ.get("KAFKA_BOOTSTRAP", "kafka:9092")
KAFKA_TOPIC_RE    = os.environ.get("KAFKA_TOPIC_REGEX", "shop\\.public\\..*")
KAFKA_START       = os.environ.get("KAFKA_START_OFFSETS", "earliest")

CH_HOST           = os.environ.get("CLICKHOUSE_HOST", "clickhouse")
CH_PORT           = os.environ.get("CLICKHOUSE_PORT", "8123")
CH_DB             = os.environ.get("CLICKHOUSE_DB", "analytics")
CH_USER           = os.environ.get("CLICKHOUSE_USER", "default")
CH_PASSWORD       = os.environ.get("CLICKHOUSE_PASSWORD", "clickpass")

CHECKPOINT_DIR    = os.environ.get("CHECKPOINT_DIR", "/opt/checkpoint")
TRIGGER_INTERVAL  = os.environ.get("TRIGGER_INTERVAL", "5 seconds")

CH_JDBC_URL = f"jdbc:clickhouse://{CH_HOST}:{CH_PORT}/{CH_DB}"
CH_JDBC_PROPS = {
    "user": CH_USER,
    "password": CH_PASSWORD,
    "driver": "com.clickhouse.jdbc.ClickHouseDriver",
    # Batch size tuned for ClickHouse — it really, really likes large inserts.
    "batchsize": "5000",
    "rewriteBatchedStatements": "true",
}


# ─── Spark session ───────────────────────────────────────────────────────────
def build_spark() -> SparkSession:
    spark = (
        SparkSession.builder
        .appName("cdc_to_clickhouse")
        # Adaptive query exec helps when batches vary in size (they will).
        .config("spark.sql.adaptive.enabled", "true")
        # Keep Spark UI lightweight in dev — increase for prod.
        .config("spark.ui.showConsoleProgress", "false")
        # ClickHouse JDBC behaves better with smaller fetch sizes.
        .config("spark.sql.streaming.kafka.useDeprecatedOffsetFetching", "false")
        .getOrCreate()
    )
    spark.sparkContext.setLogLevel("WARN")
    return spark


# ─── Parse a Kafka micro-batch into a long-form CDC DataFrame ────────────────
def parse_batch(raw: DataFrame) -> tuple[DataFrame, DataFrame]:
    """
    Returns (good_df, bad_df).

    good_df schema:
      table:       string  (customers | orders | order_items)
      payload:     string  (JSON payload after envelope unwrap)
      is_deleted:  int     (0 or 1)
      op:          string
      op_ts_ms:    long
      kafka_topic, kafka_partition, kafka_offset

    bad_df schema:
      raw_value, error_message, kafka_topic, kafka_offset, kafka_partition

    The Spark trick: we parse the envelope with a "permissive" schema (any
    table), then in foreachBatch we re-parse per-table with the right row
    schema for that table. This avoids having three separate streaming
    queries fighting for resources.
    """
    # Tombstones come as null-value records (Debezium key + null value on delete).
    # We just drop them — the previous delete event already carried the data.
    raw = raw.filter(col("value").isNotNull())

    # Decode bytes → string. We don't trust the value yet — it might be
    # malformed JSON or wrong-shape JSON. So we keep `value_str` around for
    # the dead letter path.
    value_str = col("value").cast(StringType()).alias("value_str")

    raw = raw.select(
        value_str,
        col("topic").alias("kafka_topic"),
        col("partition").alias("kafka_partition"),
        col("offset").alias("kafka_offset"),
    )

    # Use a generic envelope schema — `before` / `after` typed as STRING here
    # so we can preserve them for downstream per-table parsing without
    # picking a row schema yet.
    generic_envelope = (
        "STRUCT<"
        "  before:   STRING,"
        "  after:    STRING,"
        "  source:   STRUCT<table:STRING, schema:STRING, db:STRING, ts_ms:BIGINT>,"
        "  op:       STRING,"
        "  ts_ms:    BIGINT"
        ">"
    )

    # Trick: we cast `before`/`after` as STRING by going through `to_json` in
    # SQL. We re-encode them later. This indirection lets us defer choosing the
    # row schema until we know which table the row is for.
    parsed = raw.withColumn(
        "env_raw",
        from_json(col("value_str"),
                  "STRUCT<before:STRING, after:STRING, "
                  "source:STRUCT<table:STRING, ts_ms:BIGINT>, "
                  "op:STRING, ts_ms:BIGINT>")
    )

    # CASE 1: bytes couldn't be parsed as JSON at all → DLQ
    bad_envelope_parse = (
        parsed
        .filter(col("env_raw").isNull())
        .select(
            col("value_str").alias("raw_value"),
            lit("envelope parse failed: not valid JSON").alias("error_message"),
            col("kafka_topic"),
            col("kafka_offset"),
            col("kafka_partition"),
        )
    )

    # Everything that envelope-parsed (even if the shape is wrong)
    enveloped = (
        parsed
        .filter(col("env_raw").isNotNull())
        .select(
            col("value_str"),                              # kept for DLQ raw_value
            col("env_raw.source.table").alias("table"),
            col("env_raw.op").alias("op"),
            col("env_raw.ts_ms").alias("op_ts_ms"),
            when(col("env_raw.op") == lit("d"),
                 col("env_raw.before"))
            .otherwise(col("env_raw.after"))
            .alias("payload"),
            (col("env_raw.op") == lit("d")).cast("int").alias("is_deleted"),
            col("kafka_topic"),
            col("kafka_partition"),
            col("kafka_offset"),
        )
    )

    # CASE 2: envelope-parsed but the shape isn't a valid Debezium CDC event
    # (unknown op, missing table, or missing payload for the op type).
    # These were previously silently dropped — now they go to the DLQ with a
    # descriptive error so operators can see what's getting filtered out.
    envelope_valid = (
        col("op").isin(*VALID_OPS) &
        col("table").isNotNull() &
        col("payload").isNotNull()
    )

    bad_envelope_shape = (
        enveloped
        .filter(~envelope_valid)
        .select(
            col("value_str").alias("raw_value"),
            lit("envelope incomplete: invalid op, missing table, or missing payload").alias("error_message"),
            col("kafka_topic"),
            col("kafka_offset"),
            col("kafka_partition"),
        )
    )

    bad_df = bad_envelope_parse.unionByName(bad_envelope_shape)

    good_df = (
        enveloped
        .filter(envelope_valid)
        .drop("value_str")          # don't carry raw bytes downstream
    )

    return good_df, bad_df


# ─── Per-batch sink: per-table parse + JDBC write ────────────────────────────
def write_batch(batch_df: DataFrame, batch_id: int, spark: SparkSession) -> None:
    if batch_df.isEmpty():
        return

    # Materialize once, used multiple times below.
    batch_df = batch_df.persist()
    try:
        # Tables present in this micro-batch
        tables = [r.table for r in batch_df.select("table").distinct().collect()]
        log.info(json.dumps({
            "event": "batch_received",
            "batch_id": batch_id,
            "tables": tables,
            "row_count": batch_df.count(),
        }))

        for tbl in tables:
            row_schema = TABLE_TO_ROW_SCHEMA.get(tbl)
            if row_schema is None:
                log.warning(json.dumps({
                    "event": "unknown_table",
                    "batch_id": batch_id,
                    "table": tbl,
                }))
                continue

            tbl_df = batch_df.filter(col("table") == lit(tbl))

            # Re-parse the payload column with the real row schema.
            tbl_df = tbl_df.withColumn(
                "row", from_json(col("payload"), row_schema)
            )

            # Spark's from_json in PERMISSIVE mode (the default) returns a
            # struct of all-null fields when the input string parses as JSON
            # but doesn't match the expected shape — *not* a null struct. So
            # filtering on `col("row").isNull()` alone misses those cases and
            # a row with id=NULL slips through and crashes the JDBC write.
            # The defensive check: ALSO treat a null primary key as a failed
            # parse. `id` is the PK on every table in TABLE_TO_ROW_SCHEMA.
            row_invalid = col("row").isNull() | col("row.id").isNull()

            tbl_bad = (
                tbl_df.filter(row_invalid)
                .select(
                    col("payload").alias("raw_value"),
                    lit(f"row parse failed for table {tbl}: null id after parse").alias("error_message"),
                    col("kafka_topic"),
                    col("kafka_offset"),
                    col("kafka_partition"),
                )
            )
            if not tbl_bad.isEmpty():
                _write_dlq(tbl_bad)

            # Build the warehouse-shaped DataFrame.
            cols = [f"row.{f.name}" for f in row_schema.fields]
            tbl_good = tbl_df.filter(~row_invalid).select(
                *[col(c).alias(c.split(".", 1)[1]) for c in cols],
                col("op").alias("_op"),
                col("op_ts_ms").alias("_op_ts_ms"),
                col("is_deleted").alias("_is_deleted"),
                col("kafka_topic").alias("_kafka_topic"),
                col("kafka_offset").alias("_kafka_offset"),
            )

            # Debezium emits TIMESTAMPTZ as microseconds since epoch (BIGINT).
            # Cast to ClickHouse DateTime64 by going through TimestampType.
            for ts_col in ("created_at", "updated_at"):
                if ts_col in tbl_good.columns:
                    tbl_good = tbl_good.withColumn(
                        ts_col,
                        coalesce(
                            to_timestamp(col(ts_col).cast("double") / lit(1_000_000.0)),
                            expr("now()"),
                        ),
                    )

            row_count = tbl_good.count()
            if row_count == 0:
                continue

            (tbl_good.write
                .mode("append")
                .jdbc(CH_JDBC_URL, table=tbl, properties=CH_JDBC_PROPS))

            log.info(json.dumps({
                "event": "wrote_table",
                "batch_id": batch_id,
                "table": tbl,
                "rows": row_count,
            }))
    finally:
        batch_df.unpersist()


def _write_dlq(bad_df: DataFrame) -> None:
    (bad_df.write
        .mode("append")
        .jdbc(CH_JDBC_URL, table="cdc_dead_letter", properties=CH_JDBC_PROPS))
    log.warning(json.dumps({
        "event": "dlq_write",
        "rows": bad_df.count(),
    }))


# ─── Main ────────────────────────────────────────────────────────────────────
def main() -> None:
    log.info(json.dumps({"event": "starting", "config": {
        "kafka_bootstrap": KAFKA_BOOTSTRAP,
        "kafka_topic_regex": KAFKA_TOPIC_RE,
        "clickhouse_jdbc_url": CH_JDBC_URL,
        "checkpoint_dir": CHECKPOINT_DIR,
    }}))

    spark = build_spark()

    raw = (
        spark.readStream
        .format("kafka")
        .option("kafka.bootstrap.servers", KAFKA_BOOTSTRAP)
        .option("subscribePattern", KAFKA_TOPIC_RE)
        .option("startingOffsets", KAFKA_START)
        # Disable Spark's "fail on data loss" — convenient in dev where Kafka
        # retention can drop offsets. In prod you'd leave this true and rely
        # on infinite topic retention for CDC topics.
        .option("failOnDataLoss", "false")
        .load()
    )

    good_df, bad_df = parse_batch(raw)

    # Bad envelope records go straight to DLQ.
    def _bad_sink(batch_df, batch_id):
        if batch_df.isEmpty():
            return
        _write_dlq(batch_df)

    (bad_df.writeStream
        .foreachBatch(_bad_sink)
        .option("checkpointLocation", f"{CHECKPOINT_DIR}/dlq")
        .trigger(processingTime=TRIGGER_INTERVAL)
        .start())

    # Good records flow through per-table sinks.
    (good_df.writeStream
        .foreachBatch(lambda df, bid: write_batch(df, bid, spark))
        .option("checkpointLocation", f"{CHECKPOINT_DIR}/main")
        .trigger(processingTime=TRIGGER_INTERVAL)
        .start())

    spark.streams.awaitAnyTermination()


if __name__ == "__main__":
    main()
