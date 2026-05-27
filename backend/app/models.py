"""
Pydantic models for request / response bodies.

These double as the source of truth for the auto-generated OpenAPI docs at
/docs — free CV-bonus: a real API with discoverable schemas.
"""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field, conint


# ─── Storefront ──────────────────────────────────────────────────────────────
class Product(BaseModel):
    sku: str
    name: str
    description: str
    unit_price_cents: int
    image_emoji: str       # Visual placeholder. Real shops would use image_url.


class OrderItemIn(BaseModel):
    sku: str
    qty: int = Field(ge=1, le=20)


class PlaceOrderIn(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=1, max_length=100)
    country: str = Field(min_length=2, max_length=2, description="ISO 3166-1 alpha-2")
    items: list[OrderItemIn] = Field(min_length=1, max_length=20)


class PlaceOrderOut(BaseModel):
    order_id: int
    customer_id: int
    total_cents: int
    item_count: int
    placed_at: datetime
    pipeline_hint: str = "Your order is now flowing through the CDC pipeline. " \
                         "Check the admin dashboard — it should appear within ~5 seconds."


# ─── Admin / pipeline ────────────────────────────────────────────────────────
class HealthMetrics(BaseModel):
    postgres_orders: int
    clickhouse_orders: int
    lag_rows: int                    # postgres - clickhouse (positive = CH behind)
    dlq_rows: int
    latency_p50_ms: int | None
    latency_p95_ms: int | None
    status: Literal["healthy", "degraded", "down"]


class MinuteBucket(BaseModel):
    minute: datetime
    orders: int
    revenue_eur: float


class TopSku(BaseModel):
    sku: str
    units: int
    revenue_eur: float


class RecentEvent(BaseModel):
    """One CDC event as seen in the warehouse."""
    table: str
    op: Literal["c", "u", "d", "r"]
    row_id: int
    op_ts_ms: int
    ingested_at: datetime
    latency_ms: int | None
    # For orders we expose enough to render a useful ticker entry
    status: str | None = None
    total_cents: int | None = None
    customer_email: str | None = None
    is_storefront_order: bool = False


class DashboardMetrics(BaseModel):
    orders_per_minute: list[MinuteBucket]
    top_skus: list[TopSku]
    health: HealthMetrics


class DlqRow(BaseModel):
    failed_at: datetime
    kafka_topic: str
    kafka_offset: int
    error: str
    raw_value: str
