import { api } from "../api/client";
import { usePolling } from "../hooks/usePolling";
import Header from "../components/Header";
import HealthBadge from "../components/admin/HealthBadge";
import MetricCard from "../components/admin/MetricCard";
import OrdersChart from "../components/admin/OrdersChart";
import TopSkusChart from "../components/admin/TopSkusChart";
import EventTicker from "../components/admin/EventTicker";
import DlqPanel from "../components/admin/DlqPanel";

const TICK_MS = 3000;

export default function Admin() {
  const m  = usePolling(() => api.getMetrics(),      TICK_MS);
  const e  = usePolling(() => api.getRecentEvents(50), TICK_MS);
  const dl = usePolling(() => api.getDlq(20),         TICK_MS);

  const metrics = m.data;
  const health  = metrics?.health ?? null;

  // Summary numbers for the metric cards
  const totalOrdersToday = metrics?.orders_per_minute.reduce((s, b) => s + b.orders, 0) ?? 0;
  const totalRevenueToday = metrics?.orders_per_minute.reduce((s, b) => s + b.revenue_eur, 0) ?? 0;
  const ordersInWindow = metrics?.orders_per_minute.length ?? 0;
  const opm = ordersInWindow > 0 ? totalOrdersToday / ordersInWindow : 0;

  return (
    <div className="min-h-full bg-ops-900 text-ops-100">
      <Header variant="admin" rightSlot={<HealthBadge health={health} />} />

      <main className="mx-auto max-w-7xl px-6 py-6 space-y-6">
        {(m.error || e.error || dl.error) && (
          <div className="rounded-md border border-accent-red/40 bg-accent-red/10 p-3 text-sm text-accent-red">
            One or more endpoints are failing: {m.error || e.error || dl.error}
          </div>
        )}

        {/* Metric strip */}
        <section className="grid grid-cols-2 gap-4 md:grid-cols-4">
          <MetricCard
            label="Orders / min (avg, last 30m)"
            value={opm.toFixed(1)}
          />
          <MetricCard
            label="Revenue (last 30m)"
            value={`€${totalRevenueToday.toFixed(2)}`}
          />
          <MetricCard
            label="Pipeline lag"
            value={health ? `${health.lag_rows} row${health.lag_rows === 1 ? "" : "s"}` : "—"}
            sub={health ? `${health.postgres_orders} in PG · ${health.clickhouse_orders} in CH` : ""}
            accent={
              !health ? "default" :
              health.lag_rows <= 50  ? "good" :
              health.lag_rows <= 500 ? "warn" : "bad"
            }
          />
          <MetricCard
            label="End-to-end latency p95"
            value={health?.latency_p95_ms !== null && health?.latency_p95_ms !== undefined
              ? `${(health.latency_p95_ms / 1000).toFixed(1)} s`
              : "—"}
            sub={health?.latency_p50_ms !== null && health?.latency_p50_ms !== undefined
              ? `p50 ${(health.latency_p50_ms / 1000).toFixed(1)} s`
              : ""}
            accent={
              !health || health.latency_p95_ms === null ? "default" :
              health.latency_p95_ms <= 10000 ? "good" :
              health.latency_p95_ms <= 30000 ? "warn" : "bad"
            }
          />
        </section>

        {/* Charts row */}
        <section className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          <OrdersChart  data={metrics?.orders_per_minute ?? []} />
          <TopSkusChart data={metrics?.top_skus ?? []} />
        </section>

        {/* Ticker + DLQ */}
        <section className="grid grid-cols-1 gap-4 lg:grid-cols-[2fr_1fr]">
          <EventTicker events={e.data ?? []} />
          <DlqPanel    rows={dl.data ?? []} />
        </section>

        <footer className="pt-4 text-center text-xs text-ops-500">
          Polling every {TICK_MS / 1000}s ·{" "}
          Backend: <code className="text-ops-300">/api/admin/*</code> ·{" "}
          Read path: ClickHouse <code className="text-ops-300">analytics.*</code>
        </footer>
      </main>
    </div>
  );
}
