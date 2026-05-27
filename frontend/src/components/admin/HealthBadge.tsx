import type { HealthMetrics } from "../../types";
import { AlertCircle, CheckCircle2, XCircle } from "lucide-react";

interface Props { health: HealthMetrics | null; }

export default function HealthBadge({ health }: Props) {
  const status = health?.status ?? "down";
  const map = {
    healthy:  { color: "text-accent-green", icon: CheckCircle2, label: "Healthy"  },
    degraded: { color: "text-accent-amber", icon: AlertCircle,  label: "Degraded" },
    down:     { color: "text-accent-red",   icon: XCircle,      label: "Down"     },
  }[status];
  const Icon = map.icon;

  return (
    <div className="inline-flex items-center gap-2 rounded-md border border-ops-700 bg-ops-800/60 px-3 py-1.5 text-sm">
      <Icon className={`h-4 w-4 ${map.color}`} />
      <span className="font-medium text-ops-100">Pipeline: {map.label}</span>
      {health && (
        <span className="font-mono text-xs text-ops-400">
          {health.lag_rows >= 0 ? "+" : ""}{health.lag_rows} lag · p95 {health.latency_p95_ms ?? "—"} ms
        </span>
      )}
    </div>
  );
}
