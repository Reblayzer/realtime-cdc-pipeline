import {
  Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import type { TopSku } from "../../types";

interface Props { data: TopSku[]; }

export default function TopSkusChart({ data }: Props) {
  // Make labels readable — trim the "SKU-" prefix.
  const series = data.map((s) => ({ ...s, label: s.sku.replace(/^SKU-/, "") }));

  return (
    <div className="rounded-lg border border-ops-700 bg-ops-800 p-4">
      <div className="mb-3 flex items-baseline justify-between">
        <h3 className="text-sm font-semibold text-ops-100">Top SKUs by units sold</h3>
        <span className="text-xs text-ops-400">lifetime</span>
      </div>
      <ResponsiveContainer width="100%" height={220}>
        <BarChart data={series} layout="vertical" margin={{ top: 5, right: 10, left: 20, bottom: 0 }}>
          <CartesianGrid stroke="#1e293b" strokeDasharray="2 4" horizontal={false} />
          <XAxis type="number" stroke="#64748b" fontSize={11} tickLine={false} axisLine={false} />
          <YAxis
            type="category" dataKey="label" stroke="#94a3b8" fontSize={11}
            width={150} tickLine={false} axisLine={false}
          />
          <Tooltip
            contentStyle={{ backgroundColor: "#0f172a", border: "1px solid #1e293b", borderRadius: 8, fontSize: 12 }}
            labelStyle={{ color: "#94a3b8" }}
            itemStyle={{ color: "#e2e8f0" }}
            formatter={(value, _name, props) => [`${value} units · €${props.payload.revenue_eur.toFixed(2)}`, "Sold"]}
          />
          <Bar dataKey="units" fill="#a06f3d" radius={[0, 4, 4, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
