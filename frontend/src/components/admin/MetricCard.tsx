interface Props {
  label: string;
  value: string;
  sub?: string;
  accent?: "default" | "good" | "warn" | "bad";
}

export default function MetricCard({ label, value, sub, accent = "default" }: Props) {
  const valueColor = {
    default: "text-ops-100",
    good:    "text-accent-green",
    warn:    "text-accent-amber",
    bad:     "text-accent-red",
  }[accent];

  return (
    <div className="rounded-lg border border-ops-700 bg-ops-800 p-4 shadow-sm">
      <div className="text-xs font-medium uppercase tracking-wider text-ops-400">{label}</div>
      <div className={`mt-1 font-mono text-3xl font-semibold ${valueColor}`}>{value}</div>
      {sub && <div className="mt-0.5 text-xs text-ops-400">{sub}</div>}
    </div>
  );
}
