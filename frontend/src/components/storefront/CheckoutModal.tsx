import { useState } from "react";
import { CheckCircle2, Loader2, X } from "lucide-react";
import type { CartLine, PlaceOrderOut } from "../../types";
import { api } from "../../api/client";

interface Props {
  open: boolean;
  onClose: () => void;
  lines: CartLine[];
  totalCents: number;
  onSuccess: (result: PlaceOrderOut) => void;
}

const COUNTRIES = [
  ["IT", "Italy"], ["DE", "Germany"], ["FR", "France"], ["ES", "Spain"],
  ["NL", "Netherlands"], ["BE", "Belgium"], ["PT", "Portugal"], ["AT", "Austria"],
  ["IE", "Ireland"], ["PL", "Poland"], ["US", "United States"], ["GB", "United Kingdom"],
];

export default function CheckoutModal({
  open, onClose, lines, totalCents, onSuccess,
}: Props) {
  const [email,    setEmail]    = useState("");
  const [fullName, setFullName] = useState("");
  const [country,  setCountry]  = useState("IT");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!open) return null;

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const result = await api.placeOrder({
        email,
        full_name: fullName,
        country,
        items: lines.map((l) => ({ sku: l.product.sku, qty: l.qty })),
      });
      onSuccess(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/50 p-4 animate-fade-in">
      <div className="w-full max-w-lg rounded-xl bg-white shadow-2xl">
        <div className="flex items-center justify-between border-b border-coffee-100 p-5">
          <h2 className="text-lg font-semibold text-coffee-900">Checkout</h2>
          <button onClick={onClose} className="text-coffee-600 hover:text-coffee-900" aria-label="Close">
            <X className="h-5 w-5" />
          </button>
        </div>

        <form onSubmit={submit} className="space-y-4 p-5">
          <div className="rounded-md bg-coffee-50 p-3 text-sm text-coffee-800">
            <div className="flex justify-between font-medium">
              <span>{lines.reduce((s, l) => s + l.qty, 0)} item(s)</span>
              <span>€{(totalCents / 100).toFixed(2)}</span>
            </div>
          </div>

          <div>
            <label className="mb-1 block text-sm font-medium text-coffee-800">Email</label>
            <input
              type="email" required
              value={email} onChange={(e) => setEmail(e.target.value)}
              placeholder="you@example.com"
              className="w-full rounded-md border border-coffee-200 px-3 py-2 text-sm focus:border-coffee-500 focus:outline-none focus:ring-2 focus:ring-coffee-200"
            />
          </div>

          <div>
            <label className="mb-1 block text-sm font-medium text-coffee-800">Full name</label>
            <input
              type="text" required minLength={1} maxLength={100}
              value={fullName} onChange={(e) => setFullName(e.target.value)}
              placeholder="Alex Coffee"
              className="w-full rounded-md border border-coffee-200 px-3 py-2 text-sm focus:border-coffee-500 focus:outline-none focus:ring-2 focus:ring-coffee-200"
            />
          </div>

          <div>
            <label className="mb-1 block text-sm font-medium text-coffee-800">Country</label>
            <select
              value={country} onChange={(e) => setCountry(e.target.value)}
              className="w-full rounded-md border border-coffee-200 bg-white px-3 py-2 text-sm focus:border-coffee-500 focus:outline-none focus:ring-2 focus:ring-coffee-200"
            >
              {COUNTRIES.map(([code, name]) => (
                <option key={code} value={code}>{name}</option>
              ))}
            </select>
          </div>

          {error && (
            <div className="rounded-md border border-accent-red/30 bg-accent-red/5 p-3 text-sm text-accent-red">
              {error}
            </div>
          )}

          <button
            type="submit"
            disabled={submitting}
            className="inline-flex w-full items-center justify-center gap-2 rounded-md bg-coffee-700 px-4 py-2.5 text-sm font-semibold text-coffee-50 transition-colors hover:bg-coffee-800 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {submitting ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" /> Placing order…
              </>
            ) : (
              <>
                <CheckCircle2 className="h-4 w-4" /> Place order
              </>
            )}
          </button>

          <p className="text-center text-xs text-coffee-600">
            No real payment, no real account — this is a CDC pipeline demo.
            Your order is inserted into the source DB and flows through the
            warehouse within ~5 seconds.
          </p>
        </form>
      </div>
    </div>
  );
}
