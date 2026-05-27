import { useEffect, useState } from "react";
import { ShoppingCart } from "lucide-react";
import { api } from "../api/client";
import { useCart } from "../hooks/useCart";
import type { PlaceOrderOut, Product } from "../types";
import Header from "../components/Header";
import ProductCard from "../components/storefront/ProductCard";
import CartSidebar from "../components/storefront/CartSidebar";
import CheckoutModal from "../components/storefront/CheckoutModal";
import OrderSuccess from "../components/storefront/OrderSuccess";

export default function Storefront() {
  const [products, setProducts] = useState<Product[]>([]);
  const [loading,  setLoading]  = useState(true);
  const [error,    setError]    = useState<string | null>(null);

  const [cartOpen,     setCartOpen]     = useState(false);
  const [checkoutOpen, setCheckoutOpen] = useState(false);
  const [success,      setSuccess]      = useState<PlaceOrderOut | null>(null);

  const cart = useCart();

  useEffect(() => {
    api.listProducts()
      .then(setProducts)
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="min-h-full bg-coffee-50 text-coffee-900">
      <Header
        variant="storefront"
        rightSlot={
          <button
            onClick={() => setCartOpen(true)}
            className="relative inline-flex items-center gap-2 rounded-md bg-coffee-800 px-3 py-1.5 text-sm font-medium hover:bg-coffee-900"
          >
            <ShoppingCart className="h-4 w-4" />
            Basket
            {cart.itemCount > 0 && (
              <span className="absolute -right-2 -top-2 inline-flex h-5 min-w-5 items-center justify-center rounded-full bg-accent-amber px-1.5 text-xs font-bold text-coffee-900">
                {cart.itemCount}
              </span>
            )}
          </button>
        }
      />

      <main className="mx-auto max-w-7xl px-6 py-10">
        <section className="mb-8 rounded-xl bg-gradient-to-r from-coffee-700 to-coffee-900 px-6 py-8 text-coffee-50 shadow-lg">
          <h1 className="text-3xl font-bold tracking-tight md:text-4xl">
            Fresh coffee, served at warehouse-scale.
          </h1>
          <p className="mt-2 max-w-2xl text-coffee-100">
            This storefront is the user-facing edge of a real-time CDC pipeline.
            Every order you place writes to Postgres and shows up in the analytics
            warehouse within ~5 seconds —{" "}
            <a
              href="/admin"
              className="underline decoration-coffee-300 underline-offset-2 hover:decoration-coffee-50"
            >
              open the Ops dashboard
            </a>{" "}
            in a second tab to watch it happen live.
          </p>
        </section>

        <h2 className="mb-4 text-xl font-semibold text-coffee-900">Catalog</h2>
        {loading && <p className="text-coffee-600">Loading products…</p>}
        {error && (
          <div className="rounded-md border border-accent-red/30 bg-accent-red/5 p-4 text-sm text-accent-red">
            Couldn't load catalog: {error}
          </div>
        )}
        {!loading && !error && (
          <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
            {products.map((p) => (
              <ProductCard key={p.sku} product={p} onAdd={cart.add} />
            ))}
          </div>
        )}
      </main>

      <CartSidebar
        open={cartOpen}
        onClose={() => setCartOpen(false)}
        lines={cart.lines}
        totalCents={cart.totalCents}
        setQty={cart.setQty}
        remove={cart.remove}
        onCheckout={() => { setCartOpen(false); setCheckoutOpen(true); }}
      />

      <CheckoutModal
        open={checkoutOpen}
        onClose={() => setCheckoutOpen(false)}
        lines={cart.lines}
        totalCents={cart.totalCents}
        onSuccess={(res) => {
          setSuccess(res);
          setCheckoutOpen(false);
          cart.clear();
        }}
      />

      <OrderSuccess result={success} onDismiss={() => setSuccess(null)} />
    </div>
  );
}
