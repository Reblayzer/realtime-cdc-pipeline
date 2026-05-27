// Mirrors backend Pydantic models. Kept hand-written (instead of generated)
// for explicitness — it's small enough that a generator would be overkill.

export interface Product {
  sku: string;
  name: string;
  description: string;
  unit_price_cents: number;
  image_emoji: string;
}

export interface OrderItemIn {
  sku: string;
  qty: number;
}

export interface PlaceOrderIn {
  email: string;
  full_name: string;
  country: string;
  items: OrderItemIn[];
}

export interface PlaceOrderOut {
  order_id: number;
  customer_id: number;
  total_cents: number;
  item_count: number;
  placed_at: string;
  pipeline_hint: string;
}

export interface HealthMetrics {
  postgres_orders: number;
  clickhouse_orders: number;
  lag_rows: number;
  dlq_rows: number;
  latency_p50_ms: number | null;
  latency_p95_ms: number | null;
  status: "healthy" | "degraded" | "down";
}

export interface MinuteBucket {
  minute: string;
  orders: number;
  revenue_eur: number;
}

export interface TopSku {
  sku: string;
  units: number;
  revenue_eur: number;
}

export interface RecentEvent {
  table: string;
  op: "c" | "u" | "d" | "r";
  row_id: number;
  op_ts_ms: number;
  ingested_at: string;
  latency_ms: number | null;
  status: string | null;
  total_cents: number | null;
  customer_email: string | null;
  is_storefront_order: boolean;
}

export interface DashboardMetrics {
  orders_per_minute: MinuteBucket[];
  top_skus: TopSku[];
  health: HealthMetrics;
}

export interface DlqRow {
  failed_at: string;
  kafka_topic: string;
  kafka_offset: number;
  error: string;
  raw_value: string;
}

// Local-only shopping-cart line item.
export interface CartLine {
  product: Product;
  qty: number;
}
