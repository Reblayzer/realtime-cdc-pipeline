-- ============================================================================
-- 02_seed.sql — small seed dataset so the warehouse isn't empty on first boot.
-- The data generator (Step 3) will continuously add more after this.
-- ============================================================================

INSERT INTO customers (email, full_name, country) VALUES
    ('alice@example.com',  'Alice Anderson', 'IT'),
    ('bob@example.com',    'Bob Becker',     'DE'),
    ('carol@example.com',  'Carol Cohen',    'FR'),
    ('dan@example.com',    'Dan Davies',     'ES'),
    ('eve@example.com',    'Eve Evans',      'IT');

INSERT INTO orders (customer_id, status, total_cents, currency) VALUES
    (1, 'paid',      4990, 'EUR'),
    (1, 'pending',   1299, 'EUR'),
    (2, 'shipped',  12500, 'EUR'),
    (3, 'delivered', 3499, 'EUR'),
    (4, 'cancelled', 0,    'EUR');

INSERT INTO order_items (order_id, sku, qty, unit_price_cents) VALUES
    (1, 'SKU-COFFEE-250G', 2,  2495),
    (2, 'SKU-MUG-CERAMIC', 1,  1299),
    (3, 'SKU-FRENCHPRESS', 1, 12500),
    (4, 'SKU-FILTERS-100', 3,  1166);
