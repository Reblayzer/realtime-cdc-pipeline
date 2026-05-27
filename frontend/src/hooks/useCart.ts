import { useCallback, useEffect, useState } from "react";
import type { CartLine, Product } from "../types";

const STORAGE_KEY = "cdc-demo-cart";

// Tiny cart manager. Persists to localStorage so a page reload doesn't blow
// it away — useful when a user clicks through the storefront a few times.
export function useCart() {
  const [lines, setLines] = useState<CartLine[]>(() => {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      return raw ? (JSON.parse(raw) as CartLine[]) : [];
    } catch {
      return [];
    }
  });

  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(lines));
  }, [lines]);

  const add = useCallback((p: Product) => {
    setLines((prev) => {
      const ix = prev.findIndex((l) => l.product.sku === p.sku);
      if (ix === -1) return [...prev, { product: p, qty: 1 }];
      const next = [...prev];
      next[ix] = { ...next[ix], qty: Math.min(20, next[ix].qty + 1) };
      return next;
    });
  }, []);

  const setQty = useCallback((sku: string, qty: number) => {
    setLines((prev) =>
      prev
        .map((l) => (l.product.sku === sku ? { ...l, qty } : l))
        .filter((l) => l.qty > 0),
    );
  }, []);

  const remove = useCallback((sku: string) => {
    setLines((prev) => prev.filter((l) => l.product.sku !== sku));
  }, []);

  const clear = useCallback(() => setLines([]), []);

  const totalCents = lines.reduce(
    (s, l) => s + l.product.unit_price_cents * l.qty,
    0,
  );
  const itemCount = lines.reduce((s, l) => s + l.qty, 0);

  return { lines, add, setQty, remove, clear, totalCents, itemCount };
}
