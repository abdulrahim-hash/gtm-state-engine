import Link from "next/link";
import { notFound } from "next/navigation";

type Fact = {
  evidence_id: string;
  fact_key: string;
  assertion: string;
  observed_at: string;
  source_observed_at: string;
  source_observation_id: string;
  normalization_result_id: string;
  source_url: string;
  paraphrase: string;
};
type Result = { id: string; result: string; input_hash: string };
type AccountTrace = {
  account_id: string;
  company_name: string;
  domain: string;
  evidence: Fact[];
  signal: Result & { reason: string; evidence_ids: string[] };
  state: {
    id: string;
    fit: string;
    timing: string;
    relationship: string;
    sufficiency: string;
    input_hash: string;
    evidence_ids: string[];
    signal_evaluation_ids: string[];
  };
  decision: Result;
  policy: Result;
  action: { id: string; type: string; input_hash: string; policy_evaluation_id: string } | null;
};
type Summary = {
  accounts: number;
  signal: Record<string, number>;
  fit: Record<string, number>;
  timing: Record<string, number>;
  relationship: Record<string, number>;
  decision: Record<string, number>;
  policy: Record<string, number>;
  action: Record<string, number>;
};
type Trace = {
  label: string;
  strategy_status: string;
  semantic_as_of: string;
  coverage_status: string;
  fingerprint: { schema: string; sha256: string };
  summaries: Record<string, Summary>;
  cohorts: Record<string, AccountTrace[]>;
};

export const dynamic = "force-dynamic";

async function loadTrace(): Promise<Trace> {
  const base = process.env.API_BASE_URL ?? "http://localhost:8000";
  let response: Response;
  try {
    response = await fetch(`${base}/api/v1/pilot/m2b/trace`, { cache: "no-store" });
  } catch {
    notFound();
  }
  if (!response.ok) notFound();
  return (await response.json()) as Trace;
}

function DateText({ value }: { value: string }) {
  return <time dateTime={value}>{new Date(value).toISOString().slice(0, 10)}</time>;
}

function MetricList({ title, values }: { title: string; values: Record<string, number> }) {
  return (
    <div className="pilot-metric">
      <span>{title}</span>
      <strong>
        {Object.entries(values)
          .map(([key, count]) => `${key} ${count}`)
          .join(" · ")}
      </strong>
    </div>
  );
}

function AccountCard({ account }: { account: AccountTrace }) {
  return (
    <article className="pilot-account">
      <div className="pilot-account-heading">
        <div>
          <span className="pilot-domain">{account.domain}</span>
          <h3>{account.company_name}</h3>
        </div>
        <span className={`pilot-result pilot-${account.signal.result.toLowerCase()}`}>
          {account.signal.result}
        </span>
      </div>
      <p className="pilot-chain">
        <span>Fit {account.state.fit}</span>
        <span>Timing {account.state.timing}</span>
        <span>Relationship {account.state.relationship}</span>
        <span>Evidence sufficiency {account.state.sufficiency}</span>
        <span>Decision {account.decision.result}</span>
        <span>Policy {account.policy.result}</span>
        <span>{account.action ? `Proposal ${account.action.type}` : "No Action proposal"}</span>
      </p>
      <details>
        <summary>Inspect evidence and provenance</summary>
        <div className="pilot-details">
          <p>
            <strong>Signal reason:</strong>{" "}
            {account.signal.reason === "QUALIFYING_EVENT_OUTSIDE_WINDOW"
              ? "Stale based on verified pilot evidence"
              : account.signal.reason.replaceAll("_", " ")}
          </p>
          {account.evidence.map((fact) => (
            <div className="pilot-fact" key={fact.evidence_id}>
              <p>
                <strong>{fact.fact_key}</strong> · {fact.assertion}
              </p>
              <p>{fact.paraphrase}</p>
              <p>
                Observed <DateText value={fact.source_observed_at} /> · Fact time{" "}
                <DateText value={fact.observed_at} />
              </p>
              <a href={fact.source_url} target="_blank" rel="noreferrer">
                Official source ↗
              </a>
              <small>
                Observation {fact.source_observation_id} · Normalization{" "}
                {fact.normalization_result_id} · Evidence {fact.evidence_id}
              </small>
            </div>
          ))}
          <small>
            Signal Evidence: {account.signal.evidence_ids.join(", ") || "none verified"}; State
            Evidence: {account.state.evidence_ids.join(", ") || "none"}; State Signal:
            {account.state.signal_evaluation_ids.join(", ")}
          </small>
          <small>
            Signal {account.signal.id} → State {account.state.id} → Decision {account.decision.id} →
            Policy {account.policy.id}
            {account.action ? ` → Action ${account.action.id}` : ""}
          </small>
        </div>
      </details>
    </article>
  );
}

export default async function PilotPage() {
  if (process.env.NODE_ENV === "production") notFound();
  const trace = await loadTrace();
  return (
    <div className="pilot-shell">
      <div className="pilot-banner">
        REAL PUBLIC-DATA PILOT <span>Local only · No external execution</span>
      </div>
      <header className="pilot-header">
        <Link href="/" className="brand">
          <span className="brand-mark">GS</span>
          <span>
            GTM State<small>Signal Engine</small>
          </span>
        </Link>
        <Link href="/">SYNTHETIC DEMO ↗</Link>
      </header>
      <main className="pilot-main">
        <section className="pilot-intro">
          <p className="eyebrow">M2B / Technical reasoning, timing, governance</p>
          <h1>Real sources. Inspectable decisions.</h1>
          <p>
            Twenty B2B sales enablement software vendors, sampled before leadership screening. The
            strategy is <strong>{trace.strategy_status}</strong>.
          </p>
          <div className="pilot-meta">
            <div>
              <span>Semantic snapshot</span>
              <strong>
                <DateText value={trace.semantic_as_of} />
              </strong>
            </div>
            <div>
              <span>Source standard</span>
              <strong>Verified official company pages</strong>
            </div>
            <div>
              <span>Coverage</span>
              <strong>{trace.coverage_status.replaceAll("_", " ")}</strong>
            </div>
          </div>
          <p className="pilot-caveat">
            Fit MATCH only confirms the narrow public offering criterion. It does not validate ICP
            fit, buying intent, or market demand. STALE means stale based on verified pilot
            evidence.
          </p>
        </section>
        {(["BASE_SAMPLE", "TRACE_COVERAGE"] as const).map((group) => (
          <section className="pilot-group" key={group} aria-labelledby={`${group}-title`}>
            <div className="pilot-group-heading">
              <div>
                <p className="eyebrow">{group.replaceAll("_", " ")}</p>
                <h2 id={`${group}-title`}>
                  {group === "BASE_SAMPLE"
                    ? "Selection-blind base sample"
                    : "Disclosed trace coverage"}
                </h2>
              </div>
              <strong>{trace.summaries[group].accounts} accounts</strong>
            </div>
            <p>
              {group === "BASE_SAMPLE"
                ? "Hash-selected from the frozen featured-page roster before Signal screening. These counts describe only this base sample."
                : "Screened separately for trace paths. Never combine these accounts with the base sample for prevalence claims."}
            </p>
            <div className="pilot-metrics">
              <MetricList title="Signal" values={trace.summaries[group].signal} />
              <MetricList title="Fit" values={trace.summaries[group].fit} />
              <MetricList title="Decision" values={trace.summaries[group].decision} />
              <MetricList title="Policy" values={trace.summaries[group].policy} />
              <MetricList title="Action" values={trace.summaries[group].action} />
            </div>
            <div className="pilot-grid">
              {trace.cohorts[group].map((account) => (
                <AccountCard key={account.account_id} account={account} />
              ))}
            </div>
          </section>
        ))}
        <aside className="pilot-footer-note">
          <h2>System outcomes only</h2>
          <p>
            No outreach, CRM update, external seller task, reply, meeting, opportunity, conversion,
            or revenue occurred. REQUEST_RESEARCH is a local governed proposal.
          </p>
          <p>
            Fingerprint {trace.fingerprint.schema}: <code>{trace.fingerprint.sha256}</code>
          </p>
        </aside>
      </main>
    </div>
  );
}
