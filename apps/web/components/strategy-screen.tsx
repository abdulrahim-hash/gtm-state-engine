"use client";

import { useEffect, useState } from "react";

import { EvidenceCard } from "@/components/evidence-card";
import { ProductShell } from "@/components/product-shell";
import { formatSnapshot, getActiveStrategy, type ActiveStrategy } from "@/lib/api";

export function StrategyScreen() {
  const [data, setData] = useState<ActiveStrategy | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    let cancelled = false;
    void getActiveStrategy()
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
    <ProductShell active="strategy">
      <main className="product-main">
        <section className="product-intro" aria-labelledby="strategy-title">
          <p className="eyebrow">Strategy version</p>
          <h1 id="strategy-title">Evidence-first strategy, kept honest.</h1>
          <p>
            Strategy assertions are visible as synthetic hypotheses. This is a fixed public demo
            snapshot, not market validation.
          </p>
        </section>
        {data === null && !error ? (
          <p className="data-notice">Loading synthetic strategy…</p>
        ) : null}
        {error ? (
          <p className="data-notice data-notice-error">
            The synthetic demo API is unavailable. No fallback data is fabricated in the UI.
          </p>
        ) : null}
        {data !== null ? (
          <>
            <section className="strategy-summary" aria-label="Active synthetic strategy">
              <div>
                <p className="eyebrow">{data.workspace.name}</p>
                <h2>{data.strategy.name}</h2>
                <p>{data.strategy.summary}</p>
              </div>
              <dl className="snapshot-panel">
                <div>
                  <dt>Demo snapshot</dt>
                  <dd>{formatSnapshot(data.workspace.demo_as_of)}</dd>
                </div>
                <div>
                  <dt>Version</dt>
                  <dd>{data.strategy.semantic_version}</dd>
                </div>
                <div>
                  <dt>Status</dt>
                  <dd>{data.strategy.status}</dd>
                </div>
              </dl>
            </section>
            <aside className="synthetic-callout">
              <strong>Synthetic / demo hypothesis boundary</strong>
              <p>{data.strategy.synthetic_disclaimer}</p>
            </aside>
            <section className="evidence-section" aria-labelledby="strategy-evidence-title">
              <div className="section-heading product-section-heading">
                <div>
                  <p className="eyebrow">Strategy provenance</p>
                  <h2 id="strategy-evidence-title">Twelve explicit assumptions</h2>
                </div>
                <p>
                  Confidence, where present, refers to the hypothesis interpretation—not extraction.
                </p>
              </div>
              <div className="evidence-grid">
                {data.strategy.claims.map((claim) => (
                  <EvidenceCard evidence={claim} key={claim.id} />
                ))}
              </div>
            </section>
          </>
        ) : null}
      </main>
    </ProductShell>
  );
}
