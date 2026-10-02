"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { ProductShell } from "@/components/product-shell";
import { formatSnapshot, getAccounts, type AccountList } from "@/lib/api";

export function AccountsScreen() {
  const [data, setData] = useState<AccountList | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    let cancelled = false;
    void getAccounts()
      .then((response) => {
        if (!cancelled) setData(response);
      })
      .catch(() => {
        if (!cancelled) setError(true);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <ProductShell active="accounts">
      <main className="product-main">
        <section className="product-intro product-intro-compact" aria-labelledby="accounts-title">
          <p className="eyebrow">Canonical accounts</p>
          <h1 id="accounts-title">A small, inspectable account memory.</h1>
          <p>
            These are synthetic canonical identities. Open an account to inspect its evidence-backed
            signals and descriptive state.
          </p>
        </section>
        {data === null && !error ? (
          <p className="data-notice">Loading synthetic accounts…</p>
        ) : null}
        {error ? (
          <p className="data-notice data-notice-error">
            The synthetic demo API is unavailable. No fallback data is fabricated in the UI.
          </p>
        ) : null}
        {data !== null ? (
          <section aria-labelledby="account-list-title">
            <div className="list-heading">
              <div>
                <p className="eyebrow">{data.workspace.name}</p>
                <h2 id="account-list-title">Synthetic account records</h2>
              </div>
              <p className="snapshot-label">
                Snapshot: {formatSnapshot(data.workspace.demo_as_of)}
              </p>
            </div>
            <div className="account-list">
              {data.items.map((account) => (
                <Link className="account-row" href={`/accounts/${account.id}`} key={account.id}>
                  <div>
                    <span className="record-label">Synthetic canonical account</span>
                    <h3>{account.canonical_name}</h3>
                    <p>{account.segment}</p>
                  </div>
                  <div className="account-domain">
                    <span>{account.domain}</span>
                    <strong aria-hidden="true">→</strong>
                  </div>
                </Link>
              ))}
            </div>
          </section>
        ) : null}
      </main>
    </ProductShell>
  );
}
