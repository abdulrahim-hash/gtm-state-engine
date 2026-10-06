import Link from "next/link";
import { notFound } from "next/navigation";
import type { components } from "@gtm-state/contracts";

type ExecutionTrace = components["schemas"]["ExecutionTraceResponse"];

export const dynamic = "force-dynamic";

async function loadTrace(planId: string): Promise<ExecutionTrace> {
  const base = process.env.API_BASE_URL ?? "http://localhost:8000";
  let response: Response;
  try {
    response = await fetch(`${base}/api/v1/pilot/m5a/executions/${encodeURIComponent(planId)}`, {
      cache: "no-store",
    });
  } catch {
    notFound();
  }
  if (!response.ok) notFound();
  return (await response.json()) as ExecutionTrace;
}

export default async function CrmExecutionPage({
  searchParams,
}: {
  searchParams: Promise<{ plan_id?: string }>;
}) {
  if (process.env.NODE_ENV === "production") notFound();
  const { plan_id: planId } = await searchParams;
  if (!planId) {
    return (
      <main className="pilot-main">
        <h1>Developer test execution</h1>
        <p>Provide the exact plan_id query parameter to inspect a local execution.</p>
      </main>
    );
  }
  const trace = await loadTrace(planId);
  const steps = [
    ["Action Proposal", `${trace.action_type} · ${trace.action_id}`],
    ["Reviewed", trace.review_id ?? "Pending"],
    ["Execution Plan", `${trace.plan_schema_version} · ${trace.plan_hash}`],
    ["Authorized", trace.authorized ? (trace.authority_assurance ?? "Local") : "Pending"],
    ["Delivery Attempt", trace.attempt_status ?? "Not attempted"],
    [
      "Provider Receipt",
      trace.receipt_recorded ? (trace.provider_task_id ?? "Recorded") : "Pending",
    ],
    ["Read-back", trace.read_back ?? "Pending"],
    ["Reconciliation", trace.read_back ?? "Pending"],
    ["Operational Outcome", trace.operational_outcome ?? "None claimed"],
  ];
  return (
    <div className="pilot-shell">
      <div className="pilot-banner">
        DEVELOPER TEST EXECUTION <span>Local only · Read only trace</span>
      </div>
      <header className="pilot-header">
        <Link href="/" className="brand">
          <span className="brand-mark">GS</span>
          <span>
            GTM State<small>Signal Engine</small>
          </span>
        </Link>
      </header>
      <main className="pilot-main">
        <section className="pilot-intro">
          <p className="eyebrow">M5A / Controlled Task execution</p>
          <h1>Governed CRM Task execution trace</h1>
          <p>{trace.message}</p>
          <p className="pilot-caveat">
            {trace.operational_outcome === "CRM_TASK_CONFIRMED_CREATED"
              ? "This was a synthetic HubSpot developer-test Task. "
              : "This trace concerns a synthetic HubSpot developer-test Task proposal; creation is not confirmed. "}
            No customer communication occurred. No commercial outcome is claimed.
          </p>
          <div className="pilot-meta">
            <div>
              <span>Synthetic target</span>
              <strong>{trace.synthetic_company}</strong>
            </div>
            <div>
              <span>Physical POST reservation</span>
              <strong>{trace.physical_post_count} of 1</strong>
            </div>
            <div>
              <span>Provider Task ID</span>
              <strong>{trace.provider_task_id ?? "None"}</strong>
            </div>
          </div>
        </section>
        <section className="pilot-group">
          <div className="pilot-group-heading">
            <div>
              <p className="eyebrow">Execution provenance</p>
              <h2>From proposal to operational observation</h2>
            </div>
          </div>
          <div className="pilot-grid">
            {steps.map(([name, value]) => (
              <article className="pilot-account" key={name}>
                <p className="eyebrow">{name}</p>
                <p>{value}</p>
              </article>
            ))}
          </div>
        </section>
      </main>
    </div>
  );
}
