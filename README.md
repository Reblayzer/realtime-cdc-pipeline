# Real-Time ETL Pipeline with Change Data Capture

A production-shaped CDC pipeline with a **live storefront** that demonstrates the pipeline in action: place an order on the React frontend, watch it land in the analytics warehouse via the admin dashboard ~5 seconds later.

**Stack:** React + FastAPI · Postgres → Debezium (Kafka Connect) → Kafka → PySpark Structured Streaming → ClickHouse · Jupyter

---

## Architecture

```
   ┌─────────────────┐  POST orders     ┌──────────┐                        ┌──────────────────┐
   │ React storefront │ ───────────────▶ │ FastAPI  │ ─INSERT─┐             │ React admin      │
   │ localhost:3000   │                 │ backend  │         │             │ localhost:3000/  │
   └─────────────────┘                  └──────────┘         │             │            admin │
                                              ▲              ▼             └─────────┬────────┘
                                              │       ┌─────────────┐                │ GET metrics
                                              │       │  Postgres   │                │ (3s polling)
                                              │       │ (source DB) │                │
                                              │       └──────┬──────┘                │
                                              │              │ WAL                   │
                                              │              ▼                       │
                                              │       ┌─────────────┐                │
                                              │       │  Debezium   │                │
                                              │       │ Kafka       │                │
                                              │       │ Connect     │                │
                                              │       └──────┬──────┘                │
                                              │              │ CDC events            │
                                              │              ▼                       │
                                              │       ┌─────────────┐                │
                                              │       │   Kafka     │                │
                                              │       │ shop.public │                │
                                              │       │   topics    │                │
                                              │       └──────┬──────┘                │
                                              │              │ subscribePattern      │
                                              │              ▼                       │
                                              │       ┌──────────────┐               │
                                              │       │   PySpark    │               │
                                              │       │ Structured   │               │
                                              │       │  Streaming   │               │
                                              │       └──────┬───────┘               │
                                              │              │ JDBC upsert           │
                                              │              ▼                       │
                                              │       ┌─────────────┐                │
                                              └───────│ ClickHouse  │◀───────────────┘
                                          SELECT     │  analytics  │ (latency p95, lag,
                                                     │ (warehouse) │  recent events, DLQ)
                                                     └─────────────┘
                                                            ▲
                                                            │ SELECT
                                                            │
                                                     ┌─────────────┐
                                                     │   Jupyter   │
                                                     │ localhost:  │
                                                     │   8888      │
                                                     └─────────────┘
```

Long-form rationale lives in [docs/architecture.md](docs/architecture.md), including the **scaling-to-10x** discussion the challenge asks for.

---

## Quick start

Pre-reqs: Docker Desktop (or Linux Docker + Compose v2), ~10 GB RAM headroom, ~6 GB disk.

```bash
cp .env.example .env
docker compose up -d --build               # ~8 min first time (Spark jars + npm install)
./scripts/register-connector.sh            # registers Debezium against Postgres
```

If `jq` isn't on your host, register the connector from a throwaway container instead:

```bash
docker run --rm --network cdc-net \
    -v "$PWD":/work -w /work alpine \
    sh -c "apk add -q jq curl bash && \
           CONNECT_URL=http://kafka-connect:8083 bash ./scripts/register-connector.sh"
```

Then open:

| URL | What |
|---|---|
| <http://localhost:3000> | **Storefront** — place an order |
| <http://localhost:3000/admin> | **Admin dashboard** — watch it land in the warehouse |
| <http://localhost:8888/?token=cdc> | Jupyter notebook with raw SQL queries |
| <http://localhost:8000/docs> | FastAPI Swagger docs |

**The killer demo:** open the storefront and admin in two tabs. Place an order on the left, switch to the right — the order appears in the recent-events ticker within ~5 seconds, highlighted because the email isn't from the synthetic data generator's `example.com` domain.

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
| [`data-generator/`](data-generator/) | Synthetic background traffic — slow trickle by default so storefront orders stand out |
| [`debezium/register-postgres.json`](debezium/register-postgres.json) | Connector definition; `scripts/register-connector.sh` posts it to Connect |
| [`spark/`](spark/) | Custom Spark image with Kafka + ClickHouse JARs baked in |
| [`spark/jobs/cdc_to_clickhouse.py`](spark/jobs/cdc_to_clickhouse.py) | The streaming job — envelope parsing, per-table routing, **two-stage DLQ** |
| [`spark/jobs/transforms.py`](spark/jobs/transforms.py) | Pure-functional core; unit-tested without Spark |
| [`clickhouse/init/01_schema.sql`](clickhouse/init/01_schema.sql) | `ReplacingMergeTree` warehouse tables, latest-state views, DLQ table |
| [`backend/`](backend/) | **FastAPI** — `/api/storefront/*` write path, `/api/admin/*` read path |
| [`frontend/`](frontend/) | **React + Vite + Tailwind** — storefront + ops dashboard |
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
| **Two-stage DLQ** | Stage 1 in `parse_batch`: malformed envelopes (invalid JSON, missing op/table). Stage 2 in `write_batch`: per-table row parse failures including null primary keys (a Spark `from_json` PERMISSIVE-mode gotcha — see commit `4813d44`). The stream never crashes on bad data. |
| **ClickHouse `ReplacingMergeTree`** | Idempotent upserts via the `_op_ts_ms` version column. Deletes become "insert a row with `_is_deleted=1` and a fresh version" — same code path. Background merges keep the table compact. |
| **`v_*` views with `FINAL`** | Hide the CDC plumbing from BI users. They get current-state rows; the engine handles dedup at read time. For high-traffic dashboards you'd materialize them on a schedule. |
| **FastAPI for the backend** | Async-first, auto-generated OpenAPI docs at `/docs`, Pydantic models double as request/response contracts and validation. |
| **React + Vite + Tailwind for the frontend** | Industry-default modern frontend stack — the broadest hiring market. Multi-stage Dockerfile produces a 30 MB nginx image instead of shipping `node_modules`. |
| **3-second polling, not WebSockets** | Simpler, predictable tick rate, no reconnect logic. The dashboard payload is small enough that the bandwidth cost is negligible. WebSockets would be the upgrade if/when you needed sub-second freshness. |

---

## Resilience features

- **Spark checkpointing** — exactly-once Kafka offsets, resumable on restart (verified by SIGKILL drill: 0 duplicate `(id, _op_ts_ms)` pairs after recovery).
- **Two-stage dead-letter routing** — malformed envelopes and shape-mismatched row payloads both land in `analytics.cdc_dead_letter` instead of crashing the stream.
- **Healthchecks + `depends_on: condition: service_healthy`** — services boot in topology order; no race conditions.
- **Tombstone deletes + heartbeats** — Debezium can advance its LSN even when the source DB is idle, so the replication slot doesn't pin WAL forever.
- **Restart policy `unless-stopped`** on every long-running service — transient failures recover automatically.
- **Idempotent connector registration** — `register-connector.sh` uses `PUT /connectors/{name}/config`, so re-running is safe.

---

## Testing

```bash
# Unit tests for the transform module (no Spark needed, runs in seconds)
docker run --rm -v $(pwd):/app -w /app python:3.12-slim \
    sh -c "pip install -q pytest && python -m pytest -v"
```

22 tests covering envelope parsing, payload selection (insert/update/delete/snapshot), metadata enrichment, and topic→table mapping. The `transforms.py` module is intentionally pure — no Spark imports, no I/O — so the test suite runs in plain Python in under a second.

### Resilience verification scripts

In `scripts/`:

- `verify-debezium-downtime.sh` — stop Debezium, watch WAL accumulate on the slot, restart, watch the warehouse catch up.
- `verify-dlq.sh` — publish three different malformed-record shapes directly to Kafka, verify all three land in the DLQ and the stream stays running.
- `verify-integrity.sh` — full data-integrity audit (PG vs CH row counts, duplicate detection, CDC op distribution, latency percentiles, DLQ).

Run any of them once the stack is up to re-prove the pipeline's behavior on demand.

---

## What's *not* in scope

This is a portfolio project, not a production deployment. Things I left out and would add for production are listed in [docs/architecture.md → "What I'd build next"](docs/architecture.md#10-what-id-build-next).
