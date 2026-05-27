"""
Storefront endpoints — the user-facing write path.

These insert rows into Postgres, which the existing CDC pipeline
(Debezium → Kafka → PySpark) immediately picks up and propagates into
the ClickHouse warehouse. The admin dashboard then sees the order
appear ~5 seconds later.

That delay is the whole point of the demo: you can *see* the pipeline
working.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, status

from ..db import pg_conn
from ..models import (
    Product, PlaceOrderIn, PlaceOrderOut,
)

log = logging.getLogger("app.storefront")
router = APIRouter()


# ─── Static product catalog ──────────────────────────────────────────────────
# Hardcoded so the storefront has a stable visual identity. The SKUs match
# the data-generator's SKU list so the synthetic background traffic and the
# user-placed orders share the same product space.
CATALOG: list[Product] = [
    Product(sku="SKU-COFFEE-250G",   name="House Blend, 250g",        description="Smooth medium roast, washed Ethiopian + natural Brazilian.", unit_price_cents=2495, image_emoji="☕"),
    Product(sku="SKU-COFFEE-1KG",    name="House Blend, 1kg",         description="Same blend, family size. Pairs well with mornings.",          unit_price_cents=8995, image_emoji="🛍️"),
    Product(sku="SKU-MUG-CERAMIC",   name="Ceramic Mug",              description="350ml, fired in our local kiln. Dishwasher safe.",            unit_price_cents=1299, image_emoji="🍵"),
    Product(sku="SKU-MUG-STEEL",     name="Insulated Steel Mug",      description="Keeps your brew hot for 6h, cold for 12h.",                   unit_price_cents=1799, image_emoji="🥤"),
    Product(sku="SKU-FRENCHPRESS",   name="French Press, 1L",         description="Borosilicate glass, brushed steel frame.",                    unit_price_cents=12500, image_emoji="🫖"),
    Product(sku="SKU-FILTERS-100",   name="Paper Filters (×100)",     description="Bleached, V60-compatible.",                                   unit_price_cents=1166, image_emoji="📄"),
    Product(sku="SKU-GRINDER-MANUAL",name="Hand Grinder",             description="Conical burr, 15 grind settings. Quiet enough for 6am.",      unit_price_cents=4499, image_emoji="⚙️"),
    Product(sku="SKU-GRINDER-ELEC",  name="Electric Grinder",         description="40 grind settings, espresso to French press.",                unit_price_cents=9999, image_emoji="🔌"),
    Product(sku="SKU-DESCALER",      name="Descaler",                 description="Citric-acid based, food-safe. Treats up to 5 cycles.",        unit_price_cents=899,  image_emoji="🧴"),
    Product(sku="SKU-BEANS-SAMPLER", name="Origin Sampler (4×100g)",  description="Four single-origin beans to compare side by side.",           unit_price_cents=3499, image_emoji="🎁"),
]
SKU_TO_PRODUCT = {p.sku: p for p in CATALOG}


# ─── Routes ──────────────────────────────────────────────────────────────────
@router.get("/products", response_model=list[Product], summary="List the storefront catalog")
def list_products() -> list[Product]:
    return CATALOG


@router.post(
    "/orders",
    response_model=PlaceOrderOut,
    status_code=status.HTTP_201_CREATED,
    summary="Place an order",
    description=(
        "Inserts a customer (upserting by email), an order, and N order_items "
        "in a single transaction. All writes are picked up by Debezium and "
        "stream into the ClickHouse warehouse — the admin dashboard should "
        "reflect the new order within ~5 seconds."
    ),
)
def place_order(body: PlaceOrderIn) -> PlaceOrderOut:
    # Validate all SKUs upfront so we don't insert a half-valid order.
    unknown = [it.sku for it in body.items if it.sku not in SKU_TO_PRODUCT]
    if unknown:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unknown SKUs: {unknown}",
        )

    total_cents = sum(
        SKU_TO_PRODUCT[it.sku].unit_price_cents * it.qty for it in body.items
    )

    with pg_conn() as conn, conn.cursor() as cur:
        # 1. Upsert customer by email. ON CONFLICT lets repeat-shoppers keep
        #    the same customer_id, which makes the admin "top customers"
        #    panel actually meaningful.
        cur.execute(
            """
            INSERT INTO customers (email, full_name, country)
            VALUES (%s, %s, %s)
            ON CONFLICT (email) DO UPDATE
                SET full_name = EXCLUDED.full_name,
                    country   = EXCLUDED.country
            RETURNING id
            """,
            (body.email, body.full_name, body.country.upper()),
        )
        customer_id = cur.fetchone()[0]

        # 2. Create the order in 'pending' state. The data generator
        #    advances statuses too — for storefront orders we leave them
        #    pending so they're easy to spot in the admin view.
        cur.execute(
            """
            INSERT INTO orders (customer_id, status, total_cents, currency)
            VALUES (%s, 'pending', %s, 'EUR')
            RETURNING id, created_at
            """,
            (customer_id, total_cents),
        )
        order_id, created_at = cur.fetchone()

        # 3. Items
        item_rows = [
            (order_id, it.sku, it.qty, SKU_TO_PRODUCT[it.sku].unit_price_cents)
            for it in body.items
        ]
        cur.executemany(
            "INSERT INTO order_items (order_id, sku, qty, unit_price_cents) VALUES (%s, %s, %s, %s)",
            item_rows,
        )
        # Single COMMIT — one Postgres transaction = one logical CDC event group.
        conn.commit()

    log.info(
        "placed_order order_id=%s customer_id=%s total_cents=%s items=%s",
        order_id, customer_id, total_cents, len(body.items),
    )

    return PlaceOrderOut(
        order_id=order_id,
        customer_id=customer_id,
        total_cents=total_cents,
        item_count=len(body.items),
        placed_at=created_at if isinstance(created_at, datetime) else datetime.now(timezone.utc),
    )
