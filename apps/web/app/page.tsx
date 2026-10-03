import Link from "next/link";

import { ProductShell } from "@/components/product-shell";

const boundaries = [
  ["Strategy", "Versioned synthetic hypotheses with explicit epistemic labels."],
  ["Evidence", "Source, time, freshness, and hash provenance retained for inspection."],
  ["Signals", "Deterministic commercial events with complete evidence traces."],
  ["Account state", "Versioned descriptive facets with normalized provenance."],
  ["Decision", "A categorical response posture anchored to one exact state snapshot."],
  ["Policy", "An independent gate that never authorizes external execution."],
] as const;

export default function Home() {
  return (
    <ProductShell active="home">
      <main>
        <section className="hero m1a-hero" aria-labelledby="hero-title">
          <div className="hero-copy">
            <p className="eyebrow">M1C / State to Decision and Policy</p>
            <h1 id="hero-title">
              Start with what is
              <br />
              <em>known - and what is not.</em>
            </h1>
            <p className="hero-summary">
              Deterministic rules preserve descriptive Account State, propose whether engagement
              merits consideration, and independently apply a non-executing Policy gate.
            </p>
            <div className="hero-actions">
              <Link className="button button-primary" href="/strategy">
                Inspect strategy
              </Link>
              <Link className="button" href="/accounts">
                Browse accounts
              </Link>
            </div>
          </div>
          <aside className="boundary-card" aria-labelledby="boundary-title">
            <div className="boundary-header">
              <p id="boundary-title">M1C boundary</p>
              <span>Read only</span>
            </div>
            <div className="boundary-item">
              <span className="status-icon status-ready" aria-hidden="true">
                OK
              </span>
              <div>
                <strong>Deterministic Decision and Policy trace</strong>
                <p>
                  Every result resolves to an exact immutable state snapshot and ordered reasons.
                </p>
              </div>
            </div>
            <div className="boundary-item">
              <span className="status-icon status-locked" aria-hidden="true">
                -
              </span>
              <div>
                <strong>Downstream execution remains off</strong>
                <p>Every disposition is proposed only and cannot authorize an external action.</p>
              </div>
            </div>
            <p className="boundary-note">All strategy assertions are synthetic demo hypotheses.</p>
          </aside>
        </section>
        <section className="principles m1a-foundations" aria-labelledby="foundations-title">
          <div className="section-heading">
            <div>
              <p className="eyebrow">M1C foundations</p>
              <h2 id="foundations-title">The trace begins before the conclusion.</h2>
            </div>
          </div>
          <div className="principle-grid">
            {boundaries.map(([title, body], index) => (
              <article key={title}>
                <span>{String(index + 1).padStart(2, "0")}</span>
                <h3>{title}</h3>
                <p>{body}</p>
              </article>
            ))}
          </div>
        </section>
      </main>
    </ProductShell>
  );
}
