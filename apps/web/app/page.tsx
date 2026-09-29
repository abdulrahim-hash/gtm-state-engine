const stages = [
  "Strategy",
  "Evidence",
  "Signal",
  "State",
  "Decision",
  "Policy",
  "Action",
  "Outcome",
] as const;

const foundations = [
  {
    index: "01",
    title: "Evidence before conclusion",
    body: "Material decisions will remain traceable to sources, timestamps, versions, and reason codes.",
  },
  {
    index: "02",
    title: "Policy before action",
    body: "Deterministic rules and explicit review gates will govern authority—not model confidence.",
  },
  {
    index: "03",
    title: "Tools remain adapters",
    body: "PostgreSQL is canonical memory. CRM, enrichment, orchestration, and models plug into it.",
  },
] as const;

export default function Home() {
  return (
    <div className="site-shell">
      <div className="demo-banner" role="status">
        <span className="demo-dot" aria-hidden="true" />
        Synthetic demo environment
        <span className="demo-divider" aria-hidden="true" />
        No prospect or client data
      </div>

      <header className="site-header">
        <a className="brand" href="#top" aria-label="GTM State & Signal Engine home">
          <span className="brand-mark" aria-hidden="true">
            GS
          </span>
          <span>
            GTM State
            <small>Signal Engine</small>
          </span>
        </a>
        <span className="phase-badge">M0 · Foundation</span>
      </header>

      <main id="top">
        <section className="hero" aria-labelledby="hero-title">
          <div className="hero-copy">
            <p className="eyebrow">Strategy-aware GTM infrastructure</p>
            <h1 id="hero-title">
              Know who matters.
              <br />
              See <em>why now.</em>
            </h1>
            <p className="hero-summary">
              A trustworthy account-state and decision system that turns fragmented evidence into
              policy-governed next actions.
            </p>
            <div className="scope-row" aria-label="Current operating boundaries">
              <span>Evidence-backed</span>
              <span>Human-governed</span>
              <span>Vendor-neutral</span>
            </div>
          </div>

          <aside className="boundary-card" aria-labelledby="boundary-title">
            <div className="boundary-header">
              <p id="boundary-title">Current boundary</p>
              <span>Safe by default</span>
            </div>
            <div className="boundary-item">
              <span className="status-icon status-ready" aria-hidden="true">
                ✓
              </span>
              <div>
                <strong>Engineering foundation</strong>
                <p>
                  Typed web and API contracts, PostgreSQL migrations, and blocking quality gates.
                </p>
              </div>
            </div>
            <div className="boundary-item">
              <span className="status-icon status-locked" aria-hidden="true">
                —
              </span>
              <div>
                <strong>External actions disabled</strong>
                <p>No CRM writes, outbound sends, model authority, or live provider connections.</p>
              </div>
            </div>
            <p className="boundary-note">GTM domain data begins in M1, not this foundation.</p>
          </aside>
        </section>

        <section className="system-flow" aria-labelledby="flow-title">
          <div className="section-heading">
            <div>
              <p className="eyebrow">The system spine</p>
              <h2 id="flow-title">One auditable operating loop</h2>
            </div>
            <p>Strategy governs the loop. Evidence supports every material transition.</p>
          </div>
          <ol className="stage-list">
            {stages.map((stage, index) => (
              <li key={stage}>
                <span>{String(index + 1).padStart(2, "0")}</span>
                <strong>{stage}</strong>
              </li>
            ))}
          </ol>
        </section>

        <section className="principles" aria-labelledby="principles-title">
          <div className="section-heading">
            <div>
              <p className="eyebrow">Control plane principles</p>
              <h2 id="principles-title">Trust is an architectural feature</h2>
            </div>
          </div>
          <div className="principle-grid">
            {foundations.map((foundation) => (
              <article key={foundation.index}>
                <span>{foundation.index}</span>
                <h3>{foundation.title}</h3>
                <p>{foundation.body}</p>
              </article>
            ))}
          </div>
        </section>
      </main>

      <footer>
        <p>GTM State &amp; Signal Engine</p>
        <p>Foundation only · Synthetic data · External actions off</p>
      </footer>
    </div>
  );
}
