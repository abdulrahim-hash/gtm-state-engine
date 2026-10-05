import Link from "next/link";
import { notFound } from "next/navigation";

type RelationshipEvidence = {
  evidence_id: string;
  fact_key: string;
  assertion: string;
  observed_at: string;
  freshness_at_as_of: string;
  mapper_key: string;
  mapper_version: string;
  normalization_result_id: string;
  source_observation_id: string;
  source_read_run_id: string;
  provider_company_id: string;
  provider_scope_sha256: string;
  source_category: string;
  source_stage_value: string;
  configured_customer_stage: string;
};

type Trace = {
  label: string;
  meaning: string;
  semantic_as_of: string;
  workspace_id: string;
  state_engine_version: string;
  external_side_effects: false;
  accounts: Array<{
    account_id: string;
    company_name: string;
    domain: string;
    synthetic: boolean;
    relationship_evidence: RelationshipEvidence[];
    state: {
      id: string;
      fit: string;
      timing: string;
      relationship: string;
      sufficiency: string;
      input_hash: string;
    };
    decision: {
      id: string;
      result: string;
      state_snapshot_id: string;
      reason_codes: string[];
    } | null;
    policy: {
      id: string;
      result: string;
      decision_evaluation_id: string;
      reason_codes: string[];
    } | null;
    action: { id: string; type: string; policy_evaluation_id: string } | null;
  }>;
};

export const dynamic = "force-dynamic";

async function loadTrace(asOf: string): Promise<Trace> {
  const base = process.env.API_BASE_URL ?? "http://localhost:8000";
  let response: Response;
  try {
    response = await fetch(`${base}/api/v1/pilot/m2c/trace?as_of=${encodeURIComponent(asOf)}`, {
      cache: "no-store",
    });
  } catch {
    notFound();
  }
  if (!response.ok) notFound();
  return (await response.json()) as Trace;
}

export default async function CrmTestPage({
  searchParams,
}: {
  searchParams: Promise<{ as_of?: string }>;
}) {
  if (process.env.NODE_ENV === "production") notFound();
  const { as_of: asOf } = await searchParams;
  if (!asOf) {
    return (
      <main className="pilot-main">
        <h1>CRM test trace</h1>
        <p>Choose an explicit semantic timestamp with the as_of query parameter.</p>
      </main>
    );
  }
  const trace = await loadTrace(asOf);
  return (
    <div className="pilot-shell">
      <div className="pilot-banner">
        CRM TEST DATA <span>Developer / synthetic provider account | Local only</span>
      </div>
      <header className="pilot-header">
        <Link href="/" className="brand">
          <span className="brand-mark">GS</span>
          <span>
            GTM State<small>Signal Engine</small>
          </span>
        </Link>
        <Link href="/">SYNTHETIC DEMO </Link>
      </header>
      <main className="pilot-main">
        <section className="pilot-intro">
          <p className="eyebrow">M2C / Controlled CRM Relationship Read</p>
          <h1>One CRM read. A governed relationship trace.</h1>
          <p>{trace.label}</p>
          <p className="pilot-caveat">
            {trace.meaning} Fit and Timing here come from clearly synthetic fixtures. No CRM write,
            external seller task, outreach, or commercial outcome occurred.
          </p>
          <div className="pilot-meta">
            <div>
              <span>Semantic state as of</span>
              <strong>{trace.semantic_as_of}</strong>
            </div>
            <div>
              <span>Relationship evaluator</span>
              <strong>{trace.state_engine_version}</strong>
            </div>
            <div>
              <span>Execution</span>
              <strong>Read only No external effects</strong>
            </div>
          </div>
        </section>
        <section className="pilot-group">
          <div className="pilot-group-heading">
            <div>
              <p className="eyebrow">Synthetic Company fixtures</p>
              <h2>Relationship changes the governed proposal</h2>
            </div>
            <strong>{trace.accounts.length} accounts</strong>
          </div>
          <div className="pilot-grid">
            {trace.accounts.map((account) => (
              <article className="pilot-account" key={account.account_id}>
                <div className="pilot-account-heading">
                  <div>
                    <span className="pilot-domain">{account.domain}</span>
                    <h3>{account.company_name}</h3>
                  </div>
                  <span className="pilot-result">{account.state.relationship}</span>
                </div>
                <p className="pilot-chain">
                  <span>Fit {account.state.fit}</span>
                  <span>Timing {account.state.timing}</span>
                  <span>Relationship {account.state.relationship}</span>
                  <span>Decision {account.decision?.result ?? "Not materialized"}</span>
                  <span>Policy {account.policy?.result ?? "Not materialized"}</span>
                  <span>Proposal {account.action?.type ?? "None"}</span>
                </p>
                <p className="pilot-caveat">
                  Decision reasons: {account.decision?.reason_codes.join(", ") || "None"}. Policy
                  reasons: {account.policy?.reason_codes.join(", ") || "None"}.
                </p>
                <details>
                  <summary>Inspect CRM-reported Evidence and provenance</summary>
                  <div className="pilot-details">
                    {account.relationship_evidence.length === 0 ? (
                      <p>No qualifying CRM relationship Evidence at this snapshot.</p>
                    ) : (
                      account.relationship_evidence.map((item) => (
                        <div className="pilot-fact" key={item.evidence_id}>
                          <p>
                            <strong>{item.fact_key}</strong> {item.assertion}
                          </p>
                          <p>
                            Source stage: {item.source_stage_value || "empty"}
                            Configured Customer: {item.configured_customer_stage}
                          </p>
                          <p>
                            Observed {item.observed_at} {item.freshness_at_as_of}
                          </p>
                          <small>
                            {item.source_category} Provider company {item.provider_company_id}
                            Scope hash {item.provider_scope_sha256}
                          </small>
                          <small>
                            Run {item.source_read_run_id} Observation {item.source_observation_id}
                            Normalization {item.normalization_result_id}
                            Evidence {item.evidence_id} State {account.state.id}
                          </small>
                          <small>
                            Decision {account.decision?.id ?? "none"} Policy{" "}
                            {account.policy?.id ?? "none"} Proposal {account.action?.id ?? "none"}
                          </small>
                        </div>
                      ))
                    )}
                  </div>
                </details>
              </article>
            ))}
          </div>
        </section>
      </main>
    </div>
  );
}
