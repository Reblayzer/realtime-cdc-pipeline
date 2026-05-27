import { Minus, Plus, ShoppingCart, Trash2, X } from "lucide-react";
import type { CartLine } from "../../types";

interface Props {
  open: boolean;
  onClose: () => void;
  lines: CartLine[];
  totalCents: number;
  setQty: (sku: string, qty: number) => void;
  remove: (sku: string) => void;
  onCheckout: () => void;
}

export default function CartSidebar({
  open, onClose, lines, totalCents, setQty, remove, onCheckout,
}: Props) {
  return (
    <>
      {/* backdrop */}
      <div
        className={`fixed inset-0 z-40 bg-black/40 transition-opacity ${
          open ? "opacity-100" : "pointer-events-none opacity-0"
        }`}
        onClick={onClose}
        aria-hidden
      />
      {/* drawer */}
      <aside
        className={`fixed right-0 top-0 z-50 flex h-full w-full max-w-md flex-col bg-white shadow-xl transition-transform ${
          open ? "translate-x-0" : "translate-x-full"
        }`}
      >
        <div className="flex items-center justify-between border-b border-coffee-100 p-4">
          <h2 className="flex items-center gap-2 text-lg font-semibold text-coffee-900">
            <ShoppingCart className="h-5 w-5" /> Your basket
          </h2>
          <button onClick={onClose} className="text-coffee-600 hover:text-coffee-900" aria-label="Close cart">
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="scrollbar-ops flex-1 overflow-y-auto">
          {lines.length === 0 ? (
            <p className="p-8 text-center text-sm text-coffee-600">
              Empty basket. Add a few items from the shop to see them here.
            </p>
          ) : (
            <ul className="divide-y divide-coffee-100">
              {lines.map((l) => (
                <li key={l.product.sku} className="flex items-start gap-3 p-4">
                  <div className="flex h-14 w-14 shrink-0 items-center justify-center rounded-md bg-coffee-50 text-3xl">
                    {l.product.image_emoji}
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="truncate font-medium text-coffee-900">{l.product.name}</div>
                    <div className="text-xs text-coffee-600">
                      €{(l.product.unit_price_cents / 100).toFixed(2)} each
                    </div>
                    <div className="mt-2 inline-flex items-center gap-1.5 rounded-md border border-coffee-200">
                      <button
                        onClick={() => setQty(l.product.sku, l.qty - 1)}
                        className="px-1.5 py-1 text-coffee-700 hover:bg-coffee-50"
                        aria-label="Decrease quantity"
                      >
                        <Minus className="h-3.5 w-3.5" />
                      </button>
                      <span className="w-6 text-center text-sm font-medium">{l.qty}</span>
                      <button
                        onClick={() => setQty(l.product.sku, l.qty + 1)}
                        className="px-1.5 py-1 text-coffee-700 hover:bg-coffee-50"
                        aria-label="Increase quantity"
                      >
                        <Plus className="h-3.5 w-3.5" />
                      </button>
                    </div>
                  </div>
                  <div className="flex flex-col items-end gap-2">
                    <span className="font-semibold text-coffee-900">
                      €{((l.product.unit_price_cents * l.qty) / 100).toFixed(2)}
                    </span>
                    <button
                      onClick={() => remove(l.product.sku)}
                      className="text-coffee-500 hover:text-accent-red"
                      aria-label="Remove from cart"
                    >
                      <Trash2 className="h-4 w-4" />
                    </button>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className="border-t border-coffee-100 p-4">
          <div className="mb-3 flex items-center justify-between text-base font-semibold text-coffee-900">
            <span>Total</span>
            <span>€{(totalCents / 100).toFixed(2)}</span>
          </div>
          <button
            onClick={onCheckout}
            disabled={lines.length === 0}
            className="w-full rounded-md bg-coffee-700 px-4 py-2.5 text-sm font-semibold text-coffee-50 transition-colors hover:bg-coffee-800 disabled:cursor-not-allowed disabled:opacity-50"
          >
            Checkout
          </button>
        </div>
      </aside>
    </>
  );
}
