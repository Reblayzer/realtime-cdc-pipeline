"""
Unit tests for the pure transformation functions used by the Spark job.

These don't spin up Spark — they exercise the Python-level logic that decides
which payload to take from a Debezium envelope, how to enrich it with CDC
metadata, and how to derive the source table from a Kafka topic name.

Tested behaviors:
  - Inserts/updates/reads pull from `after`, not deleted
  - Deletes pull from `before`, marked deleted
  - Malformed envelopes return None (so the caller can route them to DLQ)
  - Unknown ops (truncate, message) are skipped (not DLQ'd)
  - Topic parser is strict about the Debezium "<prefix>.<schema>.<table>" pattern
"""

import pytest

from transforms import choose_payload, enrich, table_from_topic


# ── choose_payload ────────────────────────────────────────────────────────────

def test_insert_uses_after():
    env = {"op": "c", "before": None, "after": {"id": 1, "x": "hello"}}
    row, deleted = choose_payload(env)
    assert row == {"id": 1, "x": "hello"}
    assert deleted == 0

def test_update_uses_after():
    env = {"op": "u", "before": {"id": 1, "x": "old"}, "after": {"id": 1, "x": "new"}}
    row, deleted = choose_payload(env)
    assert row == {"id": 1, "x": "new"}
    assert deleted == 0

def test_snapshot_read_uses_after():
    env = {"op": "r", "before": None, "after": {"id": 7, "x": "snap"}}
    row, deleted = choose_payload(env)
    assert row == {"id": 7, "x": "snap"}
    assert deleted == 0

def test_delete_uses_before_and_marks_deleted():
    env = {"op": "d", "before": {"id": 3, "x": "bye"}, "after": None}
    row, deleted = choose_payload(env)
    assert row == {"id": 3, "x": "bye"}
    assert deleted == 1

def test_delete_with_null_before_is_unusable():
    env = {"op": "d", "before": None, "after": None}
    row, deleted = choose_payload(env)
    assert row is None
    assert deleted == 0

def test_unknown_op_is_skipped():
    # Truncate, message, etc. — valid envelopes we just don't propagate.
    for op in ("t", "m", "?", ""):
        row, _ = choose_payload({"op": op, "before": None, "after": None})
        assert row is None

@pytest.mark.parametrize("bad", [None, [], "string", 123])
def test_malformed_envelope_returns_none(bad):
    row, _ = choose_payload(bad)
    assert row is None


# ── enrich ────────────────────────────────────────────────────────────────────

def test_enrich_preserves_row_fields_and_adds_metadata():
    out = enrich(
        {"id": 1, "email": "a@b.c"},
        op="c", op_ts_ms=1700000000123, is_deleted=0,
        kafka_topic="shop.public.customers", kafka_offset=42,
    )
    assert out["id"] == 1
    assert out["email"] == "a@b.c"
    assert out["_op"] == "c"
    assert out["_op_ts_ms"] == 1700000000123
    assert out["_is_deleted"] == 0
    assert out["_kafka_topic"] == "shop.public.customers"
    assert out["_kafka_offset"] == 42

def test_enrich_does_not_overwrite_existing_row_columns_named_underscored():
    # Defensive: if a source column shadows a metadata column, our metadata wins.
    out = enrich(
        {"id": 1, "_op": "X-from-source"},
        op="u", op_ts_ms=1, is_deleted=0,
        kafka_topic="t", kafka_offset=0,
    )
    assert out["_op"] == "u"


# ── table_from_topic ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("topic,expected", [
    ("shop.public.customers",   "customers"),
    ("shop.public.orders",      "orders"),
    ("shop.public.order_items", "order_items"),
])
def test_topic_parser_happy_path(topic, expected):
    assert table_from_topic(topic) == expected

@pytest.mark.parametrize("topic", [
    "",
    "shop.public",                # missing table part
    "shop.public.customers.x",    # one part too many
    "other.public.customers",     # wrong prefix
    None,
    42,
])
def test_topic_parser_rejects_garbage(topic):
    assert table_from_topic(topic) is None

def test_topic_parser_respects_prefix_argument():
    assert table_from_topic("inventory.public.skus", prefix="inventory") == "skus"
    assert table_from_topic("inventory.public.skus", prefix="shop") is None
