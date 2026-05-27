import type { DlqRow } from "../../types";
import { ShieldAlert } from "lucide-react";

interface Props { rows: DlqRow[]; }

function fmtTime(iso: string) {
  const d = new Date(iso);
  return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

export default function DlqPanel({ rows }: Props) {
  return (
    <div className="rounded-lg border border-ops-700 bg-ops-800 p-4">
      <div className="mb-3 flex items-center gap-2">
        <ShieldAlert className="h-4 w-4 text-accent-amber" />
        <h3 className="text-sm font-semibold text-ops-100">Dead-letter queue</h3>
        <span className="ml-auto text-xs text-ops-400">
          {rows.length === 0
            ? "no rejected records"
            : `${rows.length} recent rejections`}
        </span>
      </div>
      {rows.length === 0 ? (
        <p className="rounded-md border border-dashed border-ops-700 p-6 text-center text-sm text-ops-400">
          🎉 Empty. Every CDC event has been accepted by the warehouse.
        </p>
      ) : (
        <ul className="scrollbar-ops max-h-56 divide-y divide-ops-700 overflow-y-auto">
          {rows.map((r, i) => (
            <li key={`${r.kafka_topic}-${r.kafka_offset}-${i}`} className="py-2 text-xs">
              <div className="flex items-center justify-between">
                <span className="font-mono text-ops-400">{fmtTime(r.failed_at)}</span>
                <span className="font-mono text-ops-500">{r.kafka_topic}#{r.kafka_offset}</span>
              </div>
              <div className="mt-0.5 text-accent-amber">{r.error}</div>
              <div className="mt-0.5 truncate font-mono text-ops-300/80">{r.raw_value}</div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
