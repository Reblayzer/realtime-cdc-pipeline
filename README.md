# Real-Time ETL Pipeline with Change Data Capture

A production-shaped CDC pipeline that streams every insert, update, and delete from an OLTP database into an analytics warehouse in near-real time.

**Stack:** Postgres → Debezium (Kafka Connect) → Kafka → PySpark Structured Streaming → ClickHouse → Jupyter

---

## Architecture

```
                                                                          ┌──────────────┐
                                                                          │   Jupyter    │
                                                                          │ (sample      │
                                                                          │  queries)    │
                                                                          └──────┬───────┘
                                                                                 │ SELECT
              ┌─── WAL ───┐                                                      │
              │           │                                                      ▼
┌──────────┐  │  ┌────────┴────────┐  ┌──────────┐  ┌──────────────────┐  ┌────────────┐
│ data-gen │─▶│  │    Postgres     │─▶│ Debezium │─▶│      Kafka       │─▶│  PySpark   │─▶ ┐
│   .py    │  │  │   (source DB)   │  │ Connect  │  │ shop.public.*    │  │ Structured │   │
└──────────┘  │  │  wal_level=     │  │ (CDC)    │  │ topics           │  │ Streaming  │   │
              │  │   logical       │  │          │  │                  │  └────────────┘   │
              └──┴─────────────────┘  └──────────┘  └──────────────────┘                   │
                                                                                           ▼
                                                                                    ┌────────────┐
                                                                                    │ ClickHouse │
                                                                                    │ analytics  │
                                                                                    │ (warehouse)│
                                                                                    └────────────┘
```

A detailed walkthrough lives in [docs/architecture.md](docs/architecture.md), including the **scaling-to-10x** discussion the challenge asks for.

---

## Quick start

Pre-reqs: Docker Desktop (or Linux Docker + Compose v2), ~8 GB RAM headroom, ~5 GB disk.

```bash
cp .env.example .env
docker compose up -d --build               # ~5 min first time (image pulls + Spark jars)
./scripts/register-connector.sh            # registers Debezium against Postgres
```

If `jq` isn't on your host, the connector script also runs from a throwaway container:

```bash
docker run --rm --network cdc-net \
    -v "$PWD":/work -w /work alpine \
    sh -c "apk add -q jq curl bash && \
           CONNECT_URL=http://kafka-connect:8083 bash ./scripts/register-connector.sh"
```

Watch it work:

```bash
# CDC traffic from the simulator
docker compose logs -f data-generator

# Debezium events landing in Kafka
docker exec cdc-kafka kafka-console-consumer \
    --bootstrap-server localhost:9092 \
    --topic shop.public.orders \
    --from-beginning --max-messages 5

# Spark consuming and writing
docker compose logs -f spark-job

# Warehouse contents
docker exec cdc-clickhouse clickhouse-client --password=clickpass \
    --query "SELECT count() FROM analytics.v_orders"
```

Open the demo notebook at <http://localhost:8888/?token=cdc> and run `01_demo_queries.ipynb`.

Shut down:

```bash
docker compose down            # keep volumes (resume where you left off)
docker compose down -v         # nuke volumes — fresh start
```

---

## Component map

| Path | Purpose |
|---|---|
| [`docker-compose.yml`](docker-compose.yml) | Topology and per-service config, with comments on every knob |
| [`postgres/init/`](postgres/init/) | Schema, seed data, `REPLICA IDENTITY FULL`, publication for Debezium |
| [`data-generator/`](data-generator/) | Containerized Python simulator — continuous insert/update/delete traffic |
| [`debezium/register-postgres.json`](debezium/register-postgres.json) | Connector definition; `scripts/register-connector.sh` posts it to Connect |
| [`spark/`](spark/) | Custom Spark image with Kafka + ClickHouse JARs baked in |
| [`spark/jobs/cdc_to_clickhouse.py`](spark/jobs/cdc_to_clickhouse.py) | The streaming job — envelope parsing, per-table routing, DLQ, JDBC write |
| [`spark/jobs/transforms.py`](spark/jobs/transforms.py) | Pure-functional core; unit-tested without Spark |
| [`clickhouse/init/01_schema.sql`](clickhouse/init/01_schema.sql) | `ReplacingMergeTree` warehouse tables, latest-state views, DLQ table |
| [`notebooks/01_demo_queries.ipynb`](notebooks/01_demo_queries.ipynb) | Sample analytics queries against the warehouse |
| [`tests/test_transforms.py`](tests/test_transforms.py) | Unit tests for the transform module (22 tests, runs in plain Python) |

---

## Design decisions (the short version — long form in [docs/architecture.md](docs/architecture.md))

| Decision | What & why |
|---|---|
| **Postgres + Debezium for CDC** | Log-based capture via Postgres logical replication. Lowest possible source-DB overhead, complete history including pre-images, exactly-once Kafka semantics. Trade-off: requires `wal_level=logical` and operational care around replication slots. |
| **`pgoutput` plugin** | Built in to Postgres ≥10. No extension installs, no extra Docker layer. The modern default. |
| **`REPLICA IDENTITY FULL`** | Forces Postgres to log the *complete* old row on UPDATE/DELETE so Debezium emits a full `before` image. Cost: extra WAL bytes. Worth it for analytics; revisit per-table at 10x. |
| **JSON envelope (no Schema Registry)** | One fewer service. Trade-off: schema enforcement happens in `spark/jobs/schemas.py` instead of at the broker. Acceptable here; in a multi-team setup I'd add Avro + Schema Registry. |
| **Kafka with single topic prefix `shop.*`** | Single subscription via `subscribePattern` in Spark → one streaming query, one checkpoint, one set of metrics. Cleaner than three jobs. |
| **PySpark Structured Streaming with `foreachBatch`** | The native streaming JDBC sink doesn't exist; `foreachBatch` is the canonical workaround and is what production teams actually run. |
| **ClickHouse `ReplacingMergeTree`** | Idempotent upserts via the `_op_ts_ms` version column. Deletes become "insert a row with `_is_deleted=1` and a fresh version" — same code path. Background merges keep the table compact. |
| **`v_*` views with `FINAL`** | Hide the CDC plumbing from BI users. They get current-state rows; the engine handles dedup at read time. For high-traffic dashboards you'd materialize them on a schedule. |
| **Dead-letter table** | Malformed records (failed JSON parse, unknown table, type mismatch) go to `analytics.cdc_dead_letter` instead of crashing the stream. Operators can inspect and replay. |

---

## Resilience features

- **Spark checkpointing** — exactly-once Kafka offsets, resumable on restart.
- **Healthchecks + `depends_on: condition: service_healthy`** — services boot in topology order; no race conditions.
- **Tombstone deletes + heartbeats** — Debezium can advance its LSN even when the source DB is idle, so the replication slot doesn't pin WAL forever.
- **Restart policy `unless-stopped`** on every long-running service — transient failures recover automatically.
- **Idempotent connector registration** — `register-connector.sh` uses `PUT /connectors/{name}/config`, so re-running is safe.
- **Dead-letter routing** — bad records are observable, not silent.

---

## Testing

```bash
# Unit tests for the transform module (no Spark needed, runs in seconds)
docker run --rm -v $(pwd):/app -w /app python:3.12-slim \
    sh -c "pip install -q pytest && python -m pytest -v"
```

22 tests covering envelope parsing, payload selection (insert/update/delete/snapshot), metadata enrichment, and topic→table mapping. The `transforms.py` module is intentionally pure — no Spark imports, no I/O — so the test suite runs in plain Python in under a second.

---

## What's *not* in scope

This is a coding challenge, not a production deployment. Things I left out and would add for production are listed in [docs/architecture.md → "What I'd build next"](docs/architecture.md#10-what-id-build-next).
