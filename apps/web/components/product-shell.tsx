import Link from "next/link";
import type { ReactNode } from "react";

type ActiveRoute = "home" | "strategy" | "accounts";

type ProductShellProps = {
  active: ActiveRoute;
  children: ReactNode;
};

const navigation: Array<{ href: string; key: ActiveRoute; label: string }> = [
  { href: "/strategy", key: "strategy", label: "Strategy" },
  { href: "/accounts", key: "accounts", label: "Accounts" },
];

export function ProductShell({ active, children }: ProductShellProps) {
  return (
    <div className="site-shell product-shell">
      <div className="demo-banner" role="status">
        <span className="demo-dot" aria-hidden="true" />
        Synthetic public demo
        <span className="demo-divider" aria-hidden="true" />
        No prospect or client data
      </div>
      <header className="site-header product-header">
        <Link className="brand" href="/" aria-label="GTM State and Signal Engine home">
          <span className="brand-mark" aria-hidden="true">
            GS
          </span>
          <span>
            GTM State
            <small>Signal Engine</small>
          </span>
        </Link>
        <nav aria-label="Product navigation">
          {navigation.map((item) => (
            <Link
              className={active === item.key ? "nav-link nav-link-active" : "nav-link"}
              href={item.href}
              key={item.key}
            >
              {item.label}
            </Link>
          ))}
        </nav>
        <span className="phase-badge">M1B.1 / Read only</span>
      </header>
      {children}
      <footer>
        <p>Northstar Revenue Systems Demo</p>
        <p>Synthetic snapshot / No external actions</p>
      </footer>
    </div>
  );
}
