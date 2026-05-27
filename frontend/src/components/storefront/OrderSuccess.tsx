import { CheckCircle2, ExternalLink, X } from "lucide-react";
import { Link } from "react-router-dom";
import type { PlaceOrderOut } from "../../types";

interface Props {
  result: PlaceOrderOut | null;
  onDismiss: () => void;
}

export default function OrderSuccess({ result, onDismiss }: Props) {
  if (!result) return null;
  return (
    <div className="fixed bottom-6 right-6 z-[70] w-full max-w-sm animate-slide-in rounded-xl border border-coffee-200 bg-white p-4 shadow-xl">
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-2 font-semibold text-accent-green">
          <CheckCircle2 className="h-5 w-5" />
          Order #{result.order_id} placed
        </div>
        <button onClick={onDismiss} className="text-coffee-500 hover:text-coffee-900" aria-label="Dismiss">
          <X className="h-4 w-4" />
        </button>
      </div>
      <p className="mt-2 text-sm text-coffee-700">{result.pipeline_hint}</p>
      <Link
        to="/admin"
        className="mt-3 inline-flex items-center gap-1.5 text-sm font-medium text-coffee-800 hover:text-coffee-900"
      >
        Watch it land in the warehouse <ExternalLink className="h-3.5 w-3.5" />
      </Link>
    </div>
  );
}
