# Architecture & Design Rationale

> This document is built up incrementally as each pipeline component is added. The final version covers all components, trade-offs, edge cases, and a scaling discussion (10x growth).

## Pipeline overview

```
Postgres ──WAL──▶ Debezium ──CDC events──▶ Kafka ──micro-batch──▶ PySpark ──upsert──▶ ClickHouse
```

Each arrow is a different boundary with its own delivery semantics, failure mode, and back-pressure behavior. The bulk of this document explains why each link was chosen and what would break first at 10x volume.

## Components

(To be filled in as we build.)

## Trade-offs

(To be filled in as we build.)

## Scaling to 10x

(To be filled in as we build.)
