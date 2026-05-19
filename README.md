# Real-Time ETL Pipeline with Change Data Capture

A production-shaped CDC pipeline: Postgres → Debezium → Kafka → PySpark Structured Streaming → ClickHouse.

> **Status:** Work in progress. This README will be expanded as components come online.

## Architecture (at a glance)

```
┌─────────────┐    ┌────────────┐    ┌────────────┐    ┌──────────────────────┐    ┌────────────┐
│  Postgres   │───▶│ Debezium   │───▶│   Kafka    │───▶│  PySpark Structured  │───▶│ ClickHouse │
│ (orders DB) │WAL │ (Connect)  │CDC │  (broker)  │    │      Streaming       │    │ (analytics)│
└─────────────┘    └────────────┘    └────────────┘    └──────────────────────┘    └────────────┘
       ▲                                                                                  │
       │                                                                                  ▼
┌─────────────┐                                                                   ┌─────────────┐
│ data-gen.py │                                                                   │ Jupyter     │
│ (writes/    │                                                                   │ (sample     │
│  updates)   │                                                                   │  queries)   │
└─────────────┘                                                                   └─────────────┘
```

## Quick start

```bash
cp .env.example .env
docker compose up -d
scripts/register-connector.sh        # registers Debezium Postgres source
docker compose logs -f spark-job     # watch the streaming job
```

(Detailed setup, design rationale, trade-offs, and scaling discussion will be added as the pipeline is built out.)

## Stack & rationale (preview)

| Layer | Choice | Why |
|---|---|---|
| Source DB | Postgres 16 | First-class logical replication, ubiquitous in production. |
| CDC | Debezium | Log-based, low-latency, captures inserts/updates/deletes including pre-images. |
| Queue | Kafka | Decouples producers/consumers, replayable, partitioned ordering. |
| Processing | PySpark Structured Streaming | Industry-standard streaming, schema-aware, scales horizontally. |
| Warehouse | ClickHouse | Columnar OLAP, fast aggregates, runs locally without cloud accounts. |
