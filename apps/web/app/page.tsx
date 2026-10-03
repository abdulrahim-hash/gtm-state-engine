import Link from "next/link";

import { ProductShell } from "@/components/product-shell";

const boundaries = [
  ["Strategy", "Versioned synthetic hypotheses with explicit epistemic labels."],
  ["Evidence", "Source, time, freshness, and hash provenance retained for inspection."],
  ["Signals", "Deterministic commercial events with complete evidence traces."],
  ["Account state", "Versioned descriptive facets with normalized provenance."],
  ["Decision", "A categorical response posture anchored to one exact state snapshot."],
  ["Policy", "An independent gate that never authorizes external execution."],
  ["Action", "An immutable, governed proposal for vendor-neutral GTM work."],
  ["Outcome", "An operational record of local dry-run validation."],
] as const;

export default function Home() {
  return (
    <ProductShell active="home">
      <main>
        <section className="hero m1a-hero" aria-labelledby="hero-title">
          <div className="hero-copy">
            <p className="eyebrow">M1D / Governed Action and Outcome trace</p>
            <h1 id="hero-title">
              Start with what is
              <br />
              <em>known - and what is not.</em>
            </h1>
            <p className="hero-summary">
              Follow exact evidence and Policy provenance into a governed Action proposal and local
              dry-run validation result.
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
              <p id="boundary-title">M1D boundary</p>
              <span>Read only</span>
            </div>
            <div className="boundary-item">
              <span className="status-icon status-ready" aria-hidden="true">
                OK
              </span>
              <div>
                <strong>Decision through Outcome trace</strong>
                <p>
                  Every Action proposal resolves to one exact Policy, Decision, and state snapshot.
                </p>
              </div>
            </div>
            <div className="boundary-item">
              <span className="status-icon status-locked" aria-hidden="true">
                -
              </span>
              <div>
                <strong>External execution remains off</strong>
                <p>
                  Dry-run validation creates no seller task, CRM write, message, or external
                  request.
                </p>
              </div>
            </div>
            <p className="boundary-note">All strategy assertions are synthetic demo hypotheses.</p>
          </aside>
        </section>
        <section className="principles m1a-foundations" aria-labelledby="foundations-title">
          <div className="section-heading">
            <div>
              <p className="eyebrow">M1D foundations</p>
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
