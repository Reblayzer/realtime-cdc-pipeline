import { useEffect, useRef, useState } from "react";

// Generic polling hook.
//
// Calls `fetcher` immediately, then on a fixed interval. Stores result + error
// + loading state. Stops cleanly on unmount.
//
// Trade-offs vs WebSockets:
//   - Simpler: no connection state, no reconnect logic, no message dispatch.
//   - More predictable: ops dashboards love steady tick rates.
//   - Less efficient: a few hundred bytes per interval per panel.
//
// For this demo (a handful of clients, 3s tick, small JSON) polling wins.
export function usePolling<T>(
  fetcher: () => Promise<T>,
  intervalMs = 3000,
  deps: unknown[] = [],
): { data: T | null; error: string | null; loading: boolean } {
  const [data,    setData]    = useState<T | null>(null);
  const [error,   setError]   = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const cancelled = useRef(false);

  useEffect(() => {
    cancelled.current = false;

    async function tick() {
      try {
        const res = await fetcher();
        if (cancelled.current) return;
        setData(res);
        setError(null);
      } catch (e) {
        if (cancelled.current) return;
        setError(e instanceof Error ? e.message : String(e));
      } finally {
        if (!cancelled.current) setLoading(false);
      }
    }

    tick();
    const id = window.setInterval(tick, intervalMs);
    return () => {
      cancelled.current = true;
      window.clearInterval(id);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  return { data, error, loading };
}
