// Thin fetch wrapper — single place to add auth headers later, log errors,
// retry, etc. Right now it does just enough.

import type {
  Product, PlaceOrderIn, PlaceOrderOut,
  DashboardMetrics, RecentEvent, DlqRow, HealthMetrics,
} from "../types";

const BASE = "/api";

async function jsonFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
    ...init,
  });
  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new Error(`API ${path} → ${res.status}: ${body.slice(0, 200)}`);
  }
  return res.json() as Promise<T>;
}

export const api = {
  // Storefront
  listProducts:        ()           => jsonFetch<Product[]>("/storefront/products"),
  placeOrder:          (body: PlaceOrderIn) =>
    jsonFetch<PlaceOrderOut>("/storefront/orders", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  // Admin
  getHealth:           ()           => jsonFetch<HealthMetrics>("/admin/health"),
  getMetrics:          ()           => jsonFetch<DashboardMetrics>("/admin/metrics"),
  getRecentEvents:     (limit = 30) => jsonFetch<RecentEvent[]>(`/admin/recent-events?limit=${limit}`),
  getDlq:              (limit = 20) => jsonFetch<DlqRow[]>(`/admin/dlq?limit=${limit}`),
};
