"""
Pure-functional transforms over Debezium envelopes.

Kept pure (no SparkSession dependencies, no I/O) so they can be unit-tested in
plain Python — see tests/test_transforms.py.

Two responsibilities:
  1. choose_payload: pick the "current state" row from a Debezium envelope.
     For inserts/updates/reads, that's `after`. For deletes, `after` is null,
     so we take `before` (the last-known state) and mark the row as deleted.
  2. enrich: add the CDC metadata columns the warehouse needs.

Both operate on a Python dict that mirrors what Spark would produce from
`from_json` on a parsed Debezium envelope. This makes them testable without
spinning up Spark.
"""

from __future__ import annotations

from typing import Any


def choose_payload(envelope: dict[str, Any]) -> tuple[dict[str, Any] | None, int]:
    """
    Returns (row_dict, is_deleted_flag).

    - op = 'c' (create), 'u' (update), 'r' (read/snapshot)  → use `after`
    - op = 'd' (delete)                                     → use `before`, mark deleted

    Returns (None, 0) if the envelope is malformed (caller routes to DLQ).
    """
    if not isinstance(envelope, dict):
        return None, 0
    op = envelope.get("op")
    if op in ("c", "u", "r"):
        after = envelope.get("after")
        if isinstance(after, dict):
            return after, 0
        return None, 0
    if op == "d":
        before = envelope.get("before")
        if isinstance(before, dict):
            return before, 1
        return None, 0
    # Unknown op (truncate "t", message "m", etc.) — skip but don't DLQ.
    return None, 0


def enrich(
    row: dict[str, Any],
    *,
    op: str,
    op_ts_ms: int,
    is_deleted: int,
    kafka_topic: str,
    kafka_offset: int,
) -> dict[str, Any]:
    """Attach the CDC metadata columns the warehouse needs for upsert + lineage."""
    return {
        **row,
        "_op": op,
        "_op_ts_ms": op_ts_ms,
        "_is_deleted": is_deleted,
        "_kafka_topic": kafka_topic,
        "_kafka_offset": kafka_offset,
    }


def table_from_topic(topic: str, prefix: str = "shop") -> str | None:
    """
    Debezium publishes to topics named "<prefix>.<schema>.<table>"
    (e.g. "shop.public.orders"). Extract the table name, return None on miss.
    """
    if not isinstance(topic, str):
        return None
    parts = topic.split(".")
    if len(parts) != 3 or parts[0] != prefix:
        return None
    return parts[2]
