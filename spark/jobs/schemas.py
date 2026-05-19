"""
Spark schemas for the Debezium envelope and each table's `after` / `before` payload.

A note on philosophy
--------------------
We declare schemas explicitly rather than rely on Spark's schema inference.
Reasons:
  1. Inference requires a separate pass over the data — wasteful in streaming.
  2. Inference can drift between micro-batches if a field becomes nullable.
  3. Explicit schemas double as data contracts: when Postgres adds a column,
     this file is exactly where you change it (and the diff is easy to review).

When `from_json` encounters a record whose shape doesn't match (extra fields,
missing required fields, wrong types), it sets the parsed struct to NULL.
The streaming job checks for NULL and routes the offending row to the dead-
letter table — see cdc_to_clickhouse.py for that branch.
"""

from pyspark.sql.types import (
    StructType, StructField, StringType, LongType, IntegerType, TimestampType,
)


# ── Per-table row schemas (matches Postgres columns) ──────────────────────────
# Debezium emits timestamps for TIMESTAMPTZ columns as Int64 *microseconds*
# since epoch, not as a string. We declare them as LongType here and cast to
# a real timestamp in the transform step.

CUSTOMERS_ROW = StructType([
    StructField("id",          LongType(),    nullable=False),
    StructField("email",       StringType(),  nullable=True),
    StructField("full_name",   StringType(),  nullable=True),
    StructField("country",     StringType(),  nullable=True),
    StructField("created_at",  LongType(),    nullable=True),
    StructField("updated_at",  LongType(),    nullable=True),
])

ORDERS_ROW = StructType([
    StructField("id",            LongType(),   nullable=False),
    StructField("customer_id",   LongType(),   nullable=True),
    StructField("status",        StringType(), nullable=True),
    StructField("total_cents",   LongType(),   nullable=True),
    StructField("currency",      StringType(), nullable=True),
    StructField("created_at",    LongType(),   nullable=True),
    StructField("updated_at",    LongType(),   nullable=True),
])

ORDER_ITEMS_ROW = StructType([
    StructField("id",                LongType(),    nullable=False),
    StructField("order_id",          LongType(),    nullable=True),
    StructField("sku",               StringType(),  nullable=True),
    StructField("qty",               IntegerType(), nullable=True),
    StructField("unit_price_cents",  LongType(),    nullable=True),
    StructField("created_at",        LongType(),    nullable=True),
    StructField("updated_at",        LongType(),    nullable=True),
])


# ── Debezium envelope schema (generic over which table the row belongs to) ───
def envelope_for(row_schema: StructType) -> StructType:
    """Builds the outer Debezium envelope around a specific row schema."""
    return StructType([
        StructField("before",
                    row_schema,
                    nullable=True),
        StructField("after",
                    row_schema,
                    nullable=True),
        StructField("source",
                    StructType([
                        StructField("table",   StringType(), nullable=True),
                        StructField("schema",  StringType(), nullable=True),
                        StructField("db",      StringType(), nullable=True),
                        StructField("lsn",     LongType(),   nullable=True),
                        StructField("ts_ms",   LongType(),   nullable=True),
                        StructField("txId",    LongType(),   nullable=True),
                        StructField("snapshot", StringType(), nullable=True),
                    ]),
                    nullable=True),
        StructField("op",     StringType(), nullable=True),  # 'c','u','d','r'
        StructField("ts_ms",  LongType(),   nullable=True),
    ])


TABLE_TO_ROW_SCHEMA = {
    "customers":   CUSTOMERS_ROW,
    "orders":      ORDERS_ROW,
    "order_items": ORDER_ITEMS_ROW,
}
