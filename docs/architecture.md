# Architecture & Design Rationale

This is the long-form companion to the [README](../README.md). It covers *why* each component was chosen, what the trade-offs are, what edge cases I considered, and how the architecture scales — the questions the challenge explicitly asks about, and the questions an interviewer is likely to dig into.

---

## 1. End-to-end data flow

```
┌──────────────┐   1. INSERT/UPDATE/DELETE       ┌────────────┐
│ data-gen.py  │ ──────────────────────────────▶ │  Postgres  │
└──────────────┘                                  │ (source)   │
                                                 └──────┬─────┘
                                                        │  2. WAL writes (logical, pgoutput plugin)
                                                        ▼
                                                ┌───────────────┐
                                                │ replication   │
                                                │  slot         │
                                                └──────┬────────┘
                                                       │  3. Debezium streams the slot
                                                       ▼
                                                ┌───────────────┐
                                                │ Debezium      │
                                                │ (Kafka        │
                                                │  Connect)     │
                                                └──────┬────────┘
                                                       │  4. Produces JSON envelopes
                                                       ▼
                              ┌─────────────────────────────────────────────┐
                              │ Kafka topics                                │
                              │   shop.public.customers                     │
                              │   shop.public.orders                        │
                              │   shop.public.order_items                   │
                              └──────────────────────┬──────────────────────┘
                                                     │  5. subscribePattern("shop\.public\..*")
                                                     ▼
                                              ┌──────────────┐
                                              │ PySpark      │
                                              │ Structured   │  — parse envelope, route by source.table,
                                              │ Streaming    │    pick after|before, enrich with CDC metadata,
                                              │              │    DLQ malformed rows
                                              └──────┬───────┘
                                                     │  6. JDBC append (foreachBatch)
                                                     ▼
                              ┌─────────────────────────────────────────────┐
                              │ ClickHouse                                  │
                              │   analytics.customers     (ReplacingMT)     │
                              │   analytics.orders        (ReplacingMT)     │
                              │   analytics.order_items   (ReplacingMT)     │
                              │   analytics.cdc_dead_letter (MergeTree)     │
                              │   analytics.v_customers   (latest-state)    │
                              │   analytics.v_orders                        │
                              │   analytics.v_order_items                   │
                              └──────────────────────┬──────────────────────┘
                                                     │  7. SELECT
                                                     ▼
                                              ┌──────────────┐
                                              │   Jupyter    │
                                              └──────────────┘
```

Each numbered hop is a *boundary* with its own delivery guarantee, failure mode, and back-pressure behavior. The rest of this doc walks through each one.

---

## 2. Source database: Postgres

### Why a SQL database over NoSQL

The challenge gave a free choice. I picked Postgres because:
- **Logical replication is first-class.** WAL-based CDC is built in. No polling, no triggers, no application changes.
- **The schema is the contract.** Strong typing at the source means fewer surprises downstream. For analytics, that's worth a lot.
- **Operational maturity.** Postgres + Debezium is the most heavily-trodden CDC path in industry today. Plenty of documentation, well-understood failure modes.

### The three settings that turn Postgres into a CDC source

| Setting | Default | Set to | Why |
|---|---|---|---|
| `wal_level` | `replica` | `logical` | Writes enough info into the WAL to reconstruct row-level changes. `replica` only supports physical streaming replication. |
| `max_wal_senders` | `10` | `10` | Number of concurrent WAL streaming connections. One per replication slot consumer. |
| `max_replication_slots` | `10` | `10` | Persistent server-side cursors. Debezium uses one. |

### `REPLICA IDENTITY FULL`

By default Postgres only writes the primary key into the WAL for UPDATE/DELETE. That identifies the row but doesn't tell you what changed. With `REPLICA IDENTITY FULL`, Postgres writes the *complete old row* — meaning Debezium can emit a `before` image and downstream consumers can:

- compute exactly which columns changed
- audit / diff
- soft-delete based on the deleted-row's columns
- correctly handle deletes (otherwise you only know the PK was deleted, not the rest of the data)

The cost is WAL volume. For three small tables this is fine. At 10x volume on a wide table, you'd switch to `REPLICA IDENTITY USING INDEX (some_index)` per-table, accepting partial pre-images.

### The publication

```sql
CREATE PUBLICATION dbz_publication FOR TABLE customers, orders, order_items;
```

A publication is the *server-side declaration* of which tables to expose for logical replication. We explicitly enumerate tables instead of `FOR ALL TABLES` so an accidental CREATE TABLE (e.g. a temporary admin table) doesn't start streaming sensitive data.

---

## 3. CDC: Debezium

### Why Debezium

The challenge mentions Debezium, MongoDB Change Streams, or a custom polling solution.

| | Polling | MongoDB Change Streams | Debezium |
|---|---|---|---|
| Latency | seconds–minutes | ms | ms |
| Coverage | only inserts/updates; deletes need soft-delete | inserts/updates/deletes | inserts/updates/deletes, including pre-images |
| Source-DB load | high (every poll scans) | low | low (reads WAL) |
| Schema evolution | manual | implicit, schema-less | explicit, evolvable |
| Operational complexity | very low | low (just a Mongo flag) | medium (Kafka Connect cluster) |
| Source DB requirement | none | MongoDB | Postgres/MySQL/SQL Server/etc. + WAL config |

Polling is simplest and cheapest to build, but strictly worse than log-based CDC at every other axis. For a challenge titled "real-time ETL with CDC," log-based capture is the right answer.

### The `pgoutput` plugin

Postgres ships three logical decoding plugins:

| Plugin | Status | Notes |
|---|---|---|
| `pgoutput` | Built in since v10 | Modern default. Compact wire format. No extensions to install. |
| `wal2json` | Extension | JSON output. Used in older Debezium versions. |
| `decoderbufs` | Extension | Protobuf output. Rarely used in practice. |

`pgoutput` is the right modern pick — fewer moving parts, fully supported, and what Debezium recommends.

### Replication slots: the #1 CDC footgun

A replication slot is a persistent cursor at the Postgres side. It says "Debezium has consumed up to LSN X." This is what gives CDC its exactly-once-at-the-source property — if Debezium disconnects, it resumes from the slot's LSN.

**The catch:** Postgres *cannot* recycle WAL segments past an active slot's `confirmed_flush_lsn`. If Debezium dies and the slot is left behind, WAL accumulates until the disk fills.

What I do here:
- `slot.drop.on.stop=false` — preserve the slot on Connect restart (intentional; otherwise we'd re-snapshot every restart).
- `heartbeat.interval.ms=10000` — Debezium emits heartbeat messages every 10 s so the slot's LSN advances even when the source DB is idle.

What I'd add in production:
- A `pg_replication_slots` monitor that pages on lag > N minutes.
- A WAL disk-usage alert at 70 / 85 / 95 %.
- A runbook for "delete the abandoned slot and re-snapshot" (`SELECT pg_drop_replication_slot('debezium_slot')`).

### Delivery semantics

| Hop | Semantics | How |
|---|---|---|
| Postgres → Debezium | **At-least-once** | Slot only advances when Debezium confirms commit |
| Debezium → Kafka | **At-least-once** | Connect commits offset after broker ack |
| Kafka → Spark | **At-least-once** (effectively exactly-once with checkpoint) | Spark commits Kafka offsets to its checkpoint atomically |
| Spark → ClickHouse | **At-least-once** | JDBC append, but `ReplacingMergeTree(_op_ts_ms)` dedups |

The "effectively exactly-once" trick: Spark's structured streaming checkpoint persists Kafka offsets *together* with downstream state. If a write to ClickHouse succeeds but the checkpoint commit fails, on restart Spark re-reads the same Kafka batch → ClickHouse sees the row twice → `ReplacingMergeTree` keeps the version with the highest `_op_ts_ms`. Net effect: end-to-end exactly-once **for the warehouse query result**, even though no single hop is exactly-once.

### Ordering

Kafka preserves order within a partition. Debezium hashes events by PK by default, so all events for a given row land in the same partition → strict per-row ordering. Across rows, ordering is not preserved, which is fine for this use case.

### Deduplication

- **At source:** Debezium guarantees no duplicates as long as the slot is healthy.
- **In transit:** A Kafka producer retry can produce a duplicate; we don't enable Kafka idempotent producers in Debezium (it's possible — `producer.override.enable.idempotence=true` — and would be a hardening step at scale).
- **At sink:** ClickHouse `ReplacingMergeTree(_op_ts_ms)` removes duplicates on background merge, and the `v_*` views use `FINAL` to dedup at read time as well.

---

## 4. Message queue: Kafka

### Why Kafka

| | Kafka | RabbitMQ | Redis Streams |
|---|---|---|---|
| Replayable | yes | no (consumed messages are gone) | yes |
| Partition ordering | yes | per-queue | yes |
| Throughput | very high | medium | high |
| Operational complexity | medium-high | low | low |
| Ecosystem (CDC, Spark, etc.) | dominant | smaller | smaller |

For CDC, **replayability** is the killer feature. If the warehouse schema changes and we need to back-fill, we re-read from offset 0 — no source-DB re-snapshot required.

### Topic naming

Debezium creates one topic per table, named `<topic.prefix>.<schema>.<table>`. We use `shop.public.<table>`. The benefit of one-topic-per-table: each table can have its own retention, partitioning, and consumer group. At 100 tables you'd build automation around it.

### Replication factor

Single-broker setup → `replication.factor=1` everywhere. **In production this would be 3, with `min.insync.replicas=2`** — the standard "tolerate one broker loss" config.

---

## 5. Processing: PySpark Structured Streaming

### Why Spark over alternatives

The challenge allowed PySpark or Apache Beam.

- **Hiring market.** Spark is the #1 distributed-processing skill in data engineering job descriptions.
- **Tooling maturity.** Spark UI, structured streaming metrics, exactly-once Kafka integration — all production-grade.
- **Python API parity.** Most of the Scala features are exposed; the few that aren't (some custom state stores) don't matter here.

### `foreachBatch` vs. native sinks

Structured Streaming has native sinks for Parquet, Delta, Iceberg, files, console, memory — but **not JDBC**. For JDBC, the canonical pattern is `foreachBatch`:

```python
def write_to_warehouse(batch_df, batch_id):
    batch_df.write.format("jdbc").options(...).mode("append").save()

stream.writeStream.foreachBatch(write_to_warehouse).start()
```

This is what every production Spark-to-JDBC pipeline does. Not a hack — the official recommendation.

### Schema evolution (the bonus question)

What happens when Postgres changes its schema while the pipeline is running?

| Change | What happens | Action needed |
|---|---|---|
| Add NULLABLE column | Debezium adds the field to the JSON envelope. Spark's `from_json` against the old schema silently drops it. **Pipeline keeps running**, new field invisible until you update `schemas.py` and add the warehouse column. | Update at convenience. |
| Add NOT NULL column with default | Same as above. | Same as above. |
| Add NOT NULL column **without default** | Insert at source already fails. Pipeline unaffected. | Coordinate the DDL across writers. |
| Drop a column | Spark's parser sees `null` for the dropped column. Warehouse rows get `null` in that column going forward. | Decide whether to drop the warehouse column too. |
| Change column type compatibly (varchar→text) | Transparent. | None. |
| Change column type incompatibly (text→int) | Spark's `from_json` returns null for the whole row. Row hits the **dead-letter table**. | Investigate via DLQ, fix schema, replay. |

The **dead-letter table** is the key resilience pattern. The pipeline never crashes on bad data — it routes it aside and keeps going.

### Malformed input handling

Three failure modes are caught:

1. **Bytes aren't valid JSON.** `from_json` returns null → routed to DLQ in `parse_batch`.
2. **JSON parses but isn't a Debezium envelope.** Falls through filter on `env_raw.isNull()` → DLQ.
3. **Envelope OK but row payload doesn't match the per-table schema.** Per-table re-parse in `write_batch` catches this → DLQ.

In all three cases, the original raw bytes are preserved along with the topic/offset/partition for replay.

---

## 6. Warehouse: ClickHouse

### Why ClickHouse over BigQuery / Snowflake / Redshift

The challenge listed BigQuery/Redshift/Snowflake as examples.

| | ClickHouse | BigQuery | Snowflake |
|---|---|---|---|
| Runs locally | yes | no | no |
| Reviewer can clone & run | yes | needs GCP | needs Snowflake account |
| Cost | free | usage-based | usage-based |
| Production-grade OLAP | yes | yes | yes |
| Native upsert support | via `ReplacingMergeTree` | via MERGE | via MERGE |

For a portfolio project, **reproducibility wins**. Anyone who clones this repo can `docker compose up` and see it work without a cloud account. The architectural pattern (CDC → streaming → columnar warehouse) is identical regardless of the warehouse choice, and the [section below](#10-what-id-build-next) discusses how I'd swap in a managed warehouse.

### `ReplacingMergeTree` for CDC

ClickHouse's CDC-friendly engine. On background merge, it keeps the row with the highest value of the version column per ORDER BY key.

```sql
CREATE TABLE orders (
    id Int64,
    -- ... business columns ...
    _op_ts_ms Int64,
    _is_deleted UInt8 DEFAULT 0
) ENGINE = ReplacingMergeTree(_op_ts_ms)
ORDER BY (id);
```

Inserts, updates, and deletes all become "insert one row." Background merges asynchronously dedup. Queries either:
- accept transient duplicates and live with eventual consistency, or
- use `FINAL` (or `argMax`) to dedup at read time — slower but always correct.

Our `v_*` views use `FINAL` for simplicity. At higher traffic, you'd materialize them with `INSERT … SELECT … FINAL` on a schedule.

### Partitioning

`PARTITION BY toYYYYMM(created_at)` — monthly partitions. Merges happen within a partition, so this bounds merge work and makes time-range queries hit far fewer parts. Bump to weekly/daily at 10x.

---

## 7. Resilience checklist

| Failure scenario | Behavior | Recovery |
|---|---|---|
| Postgres restarts | Debezium reconnects, resumes from slot LSN. No data loss. | Automatic. |
| Debezium Connect crashes | Slot stays put. Kafka topic retention covers the gap. | `docker compose restart kafka-connect`. |
| Kafka broker restarts | Spark + Debezium reconnect. | Automatic. |
| Spark job crashes | Checkpoint preserves Kafka offsets + downstream state. | Auto-restart via `restart: unless-stopped`. |
| ClickHouse restarts | Spark JDBC write fails, batch retried, succeeds on reconnect. | Automatic. |
| Malformed Kafka record | Routed to `analytics.cdc_dead_letter`. Stream continues. | Inspect DLQ, fix upstream, optionally replay. |
| Disk fills with WAL (orphaned slot) | Postgres refuses writes. **Critical.** | Drop the slot, re-snapshot. |
| Schema changes upstream | New columns silently dropped until schemas updated. Type changes → DLQ. | Update `spark/jobs/schemas.py` + warehouse DDL. |

---

## 8. Trade-offs I chose

| Trade-off | Chose | Sacrificed |
|---|---|---|
| Single Kafka broker | Simpler local setup | Production-grade durability (would be 3-broker, RF=3, min.ISR=2) |
| No Schema Registry | Fewer services, simpler | Compile-time schema enforcement at the broker |
| Zookeeper-mode Kafka | Most documented Debezium setup | One more container vs. KRaft mode |
| Spark in local-mode | Single container, less ops | Doesn't exercise the master/worker boundary |
| `REPLICA IDENTITY FULL` everywhere | Full before-images | Extra WAL volume |
| `FINAL` in views | Correct results without materialization | Slower reads — at scale, you'd materialize |
| JDBC sink | Universal pattern, easy to swap warehouses | Worse perf than ClickHouse's native HTTP bulk insert |

---

## 9. Scaling to 10x — what breaks first

The challenge specifically asks about 10x scaling.

### Postgres
- WAL volume grows 10x → disk fills faster. Faster disk, more aggressive checkpoints, monitor slot lag.
- `REPLICA IDENTITY FULL` on hot tables becomes painful. Switch to `USING INDEX` for write-heavy tables.
- **First thing to break:** WAL disk if slot lag is unmonitored.

### Debezium
- Single connector → single-threaded WAL reader. Hits CPU ceiling. Split into multiple connectors by table.
- Bigger bottleneck: connector restart → snapshot phase scans all rows. Mitigation: incremental snapshots (Debezium 1.6+), `snapshot.mode=schema_only` for greenfield.

### Kafka
- 10x writes → more partitions per topic. Currently 1 partition per topic → would scale to 12–24.
- Retention sizing matters more.
- **First thing to break:** consumer lag if Spark can't keep up.

### Spark
- 10x events/sec → current `local[*]` mode hits CPU/memory ceiling. Move to Spark Standalone or Kubernetes, add workers, increase parallelism via more Kafka partitions.
- `foreachBatch` with JDBC becomes the bottleneck — synchronous writes per micro-batch. Parallelize writes per table, or switch to ClickHouse's native HTTP bulk insert.
- Trigger interval (currently 5 s) — at 10x you might *increase* it to 30 s for bigger batches and fewer JDBC round-trips.

### ClickHouse
- ReplacingMergeTree merges struggle at high write rates. Bigger merge tree settings, more aggressive `OPTIMIZE`, switch to `AggregatingMergeTree` for some metrics.
- `FINAL` in views becomes unusable. Materialize the latest-state views into a separate table on a schedule.
- **First thing to break:** ClickHouse merge lag → `FINAL` queries get slow → BI users complain. Happens before raw insert performance breaks.

### Network / orchestration
- Single-host Docker Compose isn't a 10x story. Move to Kubernetes (Strimzi Kafka, Debezium operator, Spark operator), managed ClickHouse.

### Overall: who screams first as load goes up

1. **ClickHouse merge lag → slow `FINAL` queries** (most user-visible)
2. **Spark JDBC writes** (saturated batches, growing Kafka lag)
3. **WAL disk** (silent until critical, then fatal)
4. **Debezium snapshot time on restart** (only matters on incidents)

---

## 10. What I'd build next

In rough priority order:

1. **Monitoring & alerts.** Prometheus exporters for Postgres (slot lag, WAL size), Kafka (consumer lag), Spark (batch processing time), ClickHouse (merge backlog). Grafana dashboard. PagerDuty on slot lag > 10 min and WAL disk > 70 %.
2. **Schema Registry + Avro.** Compile-time schema enforcement, automatic schema evolution, smaller payloads.
3. **Incremental snapshots.** Debezium's signaling-table pattern for adding new tables without a full re-snapshot.
4. **Multi-broker Kafka with RF=3.** The minimum durable production config.
5. **Managed warehouse swap.** Same Spark job, different `.options()` — point at BigQuery or Snowflake via JDBC, and add per-warehouse upsert patterns (`MERGE`).
6. **Outbox pattern at the source.** When the source app does its own multi-table operations, switching from "CDC of internal tables" to "CDC of an outbox table" gives cleaner semantics.
7. **Tests for the streaming layer.** Right now we unit-test the pure transforms. Add a `pyspark.testing.utils.assertDataFrameEqual` integration test against a fake Kafka source.
8. **Lineage.** OpenLineage hooks in Spark → Marquez → data catalog.

---

## 11. Five-line interview summary

> "It's a Debezium → Kafka → Spark Structured Streaming → ClickHouse pipeline. Postgres is configured with `wal_level=logical` and `REPLICA IDENTITY FULL` so Debezium captures complete before/after images via the `pgoutput` plugin. Spark subscribes to all `shop.public.*` topics with one streaming query, parses the envelope, picks `after` for c/u/r ops or `before` for deletes, enriches with CDC metadata, and JDBC-writes per-table in `foreachBatch`. ClickHouse uses `ReplacingMergeTree(_op_ts_ms)` so deletes become `_is_deleted=1` rows and the latest version always wins on merge. Malformed records go to a dead-letter table instead of crashing the stream."
