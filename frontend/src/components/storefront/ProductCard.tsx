import type { Product } from "../../types";
import { Plus } from "lucide-react";

interface Props {
  product: Product;
  onAdd: (p: Product) => void;
}

export default function ProductCard({ product, onAdd }: Props) {
  const price = (product.unit_price_cents / 100).toFixed(2);
  return (
    <article className="group flex flex-col overflow-hidden rounded-xl border border-coffee-200 bg-white shadow-sm transition-all hover:-translate-y-1 hover:shadow-lg">
      <div className="flex h-40 items-center justify-center bg-gradient-to-br from-coffee-50 to-coffee-100 text-7xl">
        {product.image_emoji}
      </div>
      <div className="flex flex-1 flex-col gap-2 p-4">
        <h3 className="text-base font-semibold text-coffee-900">{product.name}</h3>
        <p className="flex-1 text-sm leading-snug text-coffee-700/80">{product.description}</p>
        <div className="mt-2 flex items-center justify-between">
          <span className="text-lg font-bold text-coffee-800">€{price}</span>
          <button
            onClick={() => onAdd(product)}
            className="inline-flex items-center gap-1.5 rounded-md bg-coffee-700 px-3 py-1.5 text-sm font-medium text-coffee-50 transition-colors hover:bg-coffee-800 active:bg-coffee-900"
          >
            <Plus className="h-4 w-4" />
            Add
          </button>
        </div>
      </div>
    </article>
  );
}
