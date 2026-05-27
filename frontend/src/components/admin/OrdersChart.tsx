import {
  Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import type { MinuteBucket } from "../../types";

interface Props { data: MinuteBucket[]; }

function fmtMinute(iso: string) {
  const d = new Date(iso);
  return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

export default function OrdersChart({ data }: Props) {
  const series = data.map((b) => ({
    label: fmtMinute(b.minute),
    orders: b.orders,
    revenue: Number(b.revenue_eur.toFixed(2)),
  }));

  return (
    <div className="rounded-lg border border-ops-700 bg-ops-800 p-4">
      <div className="mb-3 flex items-baseline justify-between">
        <h3 className="text-sm font-semibold text-ops-100">Orders per minute</h3>
        <span className="text-xs text-ops-400">last 30 min · refreshes every 3s</span>
      </div>
      <ResponsiveContainer width="100%" height={220}>
        <AreaChart data={series} margin={{ top: 5, right: 10, left: -10, bottom: 0 }}>
          <defs>
            <linearGradient id="grad-orders" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%"   stopColor="#10b981" stopOpacity={0.5} />
              <stop offset="100%" stopColor="#10b981" stopOpacity={0}   />
            </linearGradient>
          </defs>
          <CartesianGrid stroke="#1e293b" strokeDasharray="2 4" />
          <XAxis dataKey="label" stroke="#64748b" fontSize={11} tickLine={false} axisLine={false} />
          <YAxis stroke="#64748b" fontSize={11} tickLine={false} axisLine={false} width={32} />
          <Tooltip
            contentStyle={{ backgroundColor: "#0f172a", border: "1px solid #1e293b", borderRadius: 8, fontSize: 12 }}
            labelStyle={{ color: "#94a3b8" }}
            itemStyle={{ color: "#e2e8f0" }}
          />
          <Area type="monotone" dataKey="orders" stroke="#10b981" strokeWidth={2} fill="url(#grad-orders)" />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
