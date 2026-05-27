import { Link, useLocation } from "react-router-dom";
import { Coffee, Gauge } from "lucide-react";

interface Props {
  variant: "storefront" | "admin";
  rightSlot?: React.ReactNode;
}

export default function Header({ variant, rightSlot }: Props) {
  const isAdmin = variant === "admin";
  const loc = useLocation();
  const otherPath  = isAdmin ? "/"      : "/admin";
  const otherLabel = isAdmin ? "Store"  : "Admin";
  const OtherIcon  = isAdmin ? Coffee   : Gauge;

  return (
    <header
      className={
        isAdmin
          ? "bg-ops-800 border-b border-ops-700 text-ops-100"
          : "bg-coffee-700 text-coffee-50 shadow-md"
      }
    >
      <div className="mx-auto flex max-w-7xl items-center justify-between gap-4 px-6 py-4">
        <Link to="/" className="flex items-center gap-3 text-2xl font-bold tracking-tight">
          {isAdmin ? (
            <>
              <Gauge className="h-7 w-7 text-ops-300" />
              <span>CDC Pipeline · Ops</span>
            </>
          ) : (
            <>
              <Coffee className="h-7 w-7" />
              <span>Reblayzer Coffee</span>
            </>
          )}
        </Link>

        <div className="flex items-center gap-4">
          {rightSlot}
          <Link
            to={otherPath}
            className={
              isAdmin
                ? "inline-flex items-center gap-2 rounded-md border border-ops-600 px-3 py-1.5 text-sm font-medium hover:bg-ops-700"
                : "inline-flex items-center gap-2 rounded-md bg-coffee-800 px-3 py-1.5 text-sm font-medium hover:bg-coffee-900"
            }
            title={`Switch to the ${otherLabel.toLowerCase()} view`}
          >
            <OtherIcon className="h-4 w-4" />
            {otherLabel}
          </Link>
        </div>
      </div>
      {loc.pathname === "/admin" && (
        <div className="border-t border-ops-700 bg-ops-900/50 px-6 py-2 text-xs text-ops-400">
          Live view of the warehouse — refreshes every 3 seconds. Place an order on
          the storefront and watch it appear here within ~5 seconds.
        </div>
      )}
    </header>
  );
}
