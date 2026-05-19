-- ============================================================================
-- 03_replication.sql — CDC plumbing.
--
-- 1. REPLICA IDENTITY FULL
--    By default Postgres only writes the primary key into the WAL for an
--    UPDATE/DELETE. That's enough to identify the row, but Debezium can't
--    give you the full "before" image — so downstream you can't diff old vs
--    new, you can't soft-delete with the deleted attributes, and you can't
--    audit which column changed. REPLICA IDENTITY FULL makes Postgres log
--    the entire old row.
--    Cost: more WAL bytes. Worth it at this scale; at 10x volume you'd
--    weigh per-table and possibly fall back to USING INDEX or DEFAULT.
--
-- 2. PUBLICATION
--    A publication is the *server-side declaration* of which tables to
--    expose for logical replication. Debezium subscribes to it from the
--    other side. We publish all three tables under one publication so
--    Debezium can mirror them with a single connector.
-- ============================================================================

ALTER TABLE customers   REPLICA IDENTITY FULL;
ALTER TABLE orders      REPLICA IDENTITY FULL;
ALTER TABLE order_items REPLICA IDENTITY FULL;

CREATE PUBLICATION dbz_publication FOR TABLE customers, orders, order_items;

-- The connecting Debezium user needs REPLICATION + SELECT on the published
-- tables. In a production setup you'd create a dedicated `debezium` role
-- with the minimum needed grants. Here we reuse the bootstrap user, which
-- already has REPLICATION because it was created via POSTGRES_USER.
GRANT SELECT ON ALL TABLES IN SCHEMA public TO CURRENT_USER;
