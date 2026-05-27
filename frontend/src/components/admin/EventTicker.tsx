import type { RecentEvent } from "../../types";
import { Sparkles } from "lucide-react";

interface Props { events: RecentEvent[]; }

const OP_LABEL: Record<RecentEvent["op"], string> = {
  c: "INSERT", u: "UPDATE", d: "DELETE", r: "SNAPSHOT",
};
const OP_COLOR: Record<RecentEvent["op"], string> = {
  c: "bg-accent-green/20 text-accent-green",
  u: "bg-blue-500/20 text-blue-300",
  d: "bg-accent-red/20 text-accent-red",
  r: "bg-ops-600/40 text-ops-300",
};

function fmtTime(iso: string) {
  const d = new Date(iso);
  return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function fmtLatency(ms: number | null) {
  if (ms === null) return "—";
  if (ms < 1000)   return `${ms} ms`;
  return `${(ms / 1000).toFixed(1)} s`;
}

export default function EventTicker({ events }: Props) {
  return (
    <div className="flex h-[28rem] flex-col rounded-lg border border-ops-700 bg-ops-800">
      <div className="flex items-center justify-between border-b border-ops-700 px-4 py-3">
        <h3 className="text-sm font-semibold text-ops-100">Recent CDC events · orders stream</h3>
        <span className="text-xs text-ops-400">newest first</span>
      </div>
      <ol className="scrollbar-ops flex-1 divide-y divide-ops-700 overflow-y-auto">
        {events.length === 0 && (
          <li className="p-6 text-center text-sm text-ops-400">Waiting for events…</li>
        )}
        {events.map((e) => (
          <li
            key={`${e.row_id}-${e.op_ts_ms}`}
            className={`flex items-center gap-3 px-4 py-2.5 text-sm transition-colors ${
              e.is_storefront_order ? "bg-coffee-700/15" : ""
            }`}
          >
            <span className={`inline-flex w-20 shrink-0 justify-center rounded px-2 py-0.5 text-[10px] font-bold tracking-wider ${OP_COLOR[e.op]}`}>
              {OP_LABEL[e.op]}
            </span>
            <span className="w-16 shrink-0 font-mono text-xs text-ops-400">
              #{e.row_id}
            </span>
            <span className="min-w-0 flex-1 truncate text-ops-200">
              {e.status && <span className="font-medium">{e.status}</span>}
              {e.total_cents !== null && (
                <> · <span className="font-mono">€{(e.total_cents / 100).toFixed(2)}</span></>
              )}
              {e.customer_email && (
                <> · <span className="text-ops-400">{e.customer_email}</span></>
              )}
              {e.is_storefront_order && (
                <span className="ml-2 inline-flex items-center gap-1 rounded bg-coffee-700/30 px-1.5 py-0.5 text-[10px] font-medium text-coffee-200">
                  <Sparkles className="h-3 w-3" />
                  storefront
                </span>
              )}
            </span>
            <span className="w-16 shrink-0 text-right font-mono text-xs text-ops-400">
              {fmtLatency(e.latency_ms)}
            </span>
            <span className="w-20 shrink-0 text-right font-mono text-xs text-ops-500">
              {fmtTime(e.ingested_at)}
            </span>
          </li>
        ))}
      </ol>
    </div>
  );
}
