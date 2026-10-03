import type { AccountDecision } from "@/lib/api";
import { formatSnapshot } from "@/lib/api";

type DecisionPolicySectionProps = {
  data: AccountDecision;
};

function humanize(value: string): string {
  return value.replaceAll("_", " ").toLowerCase();
}

export function DecisionPolicySection({ data }: DecisionPolicySectionProps) {
  const decision = data.decision;
  const policy = data.policy;
  const disposition = data.disposition;

  return (
    <section className="decision-policy-section" aria-labelledby="decision-title">
      <div className="section-heading product-section-heading">
        <div>
          <p className="eyebrow">Decision + Policy</p>
          <h2 id="decision-title">A proposal, then an independent gate</h2>
        </div>
        <p>
          Decision assesses commercial relevance. Policy separately determines whether that proposal
          may advance to future planning.
        </p>
      </div>
      <div className="decision-policy-grid">
        <article className="decision-card">
          <p className="eyebrow">Decision</p>
          <h3>What response does the system propose?</h3>
          <strong className="decision-result">{disposition.proposed_response_label}</strong>
          <p>
            Stored result <span className="mono">{decision.evaluation.result}</span> is a
            non-executing engagement candidate, never a command to contact, send, or activate.
          </p>
          <ul>
            {decision.reasons.map((reason) => (
              <li key={reason.position}>{humanize(reason.reason_code)}</li>
            ))}
          </ul>
        </article>
        <article className={`policy-card policy-${policy.evaluation.result.toLowerCase()}`}>
          <p className="eyebrow">Policy</p>
          <h3>May that proposed response advance?</h3>
          <strong className="policy-result">{humanize(policy.evaluation.result)}</strong>
          <p>
            This gate applies to future prospecting planning only. It cannot authorize an external
            action.
          </p>
          <ul>
            {policy.reasons.map((reason) => (
              <li key={reason.position}>{humanize(reason.reason_code)}</li>
            ))}
          </ul>
        </article>
      </div>
      <div className="disposition-strip" aria-label="Non-executing proposed disposition">
        <div>
          <span>Proposed disposition</span>
          <strong>
            {disposition.proposed_response_label} · {humanize(disposition.policy_result)}
          </strong>
        </div>
        <div>
          <span>Lifecycle</span>
          <strong>{humanize(disposition.lifecycle)}</strong>
        </div>
        <div>
          <span>External action</span>
          <strong>
            {disposition.external_action_authorized ? "Authorized" : "Not authorized"}
          </strong>
        </div>
      </div>
      <details className="decision-provenance">
        <summary>Inspect Decision and Policy provenance</summary>
        <div className="decision-provenance-body">
          <dl>
            <div>
              <dt>Exact state snapshot</dt>
              <dd className="mono">{data.state_snapshot.state_snapshot_id}</dd>
            </div>
            <div>
              <dt>State semantic time</dt>
              <dd>{formatSnapshot(data.state_snapshot.state_as_of)}</dd>
            </div>
            <div>
              <dt>Decision definition</dt>
              <dd className="mono">
                {decision.definition.stable_key}@{decision.definition.definition_version}
              </dd>
            </div>
            <div>
              <dt>Decision evaluator</dt>
              <dd className="mono">
                {decision.definition.evaluator_key}@{decision.definition.evaluator_version}
              </dd>
            </div>
            <div>
              <dt>Decision evaluation</dt>
              <dd className="mono">{decision.evaluation.decision_evaluation_id}</dd>
            </div>
            <div>
              <dt>Decision input hash</dt>
              <dd className="mono">{decision.evaluation.input_hash}</dd>
            </div>
            <div>
              <dt>Policy definition</dt>
              <dd className="mono">
                {policy.definition.stable_key}@{policy.definition.definition_version}
              </dd>
            </div>
            <div>
              <dt>Policy evaluator</dt>
              <dd className="mono">
                {policy.definition.evaluator_key}@{policy.definition.evaluator_version}
              </dd>
            </div>
            <div>
              <dt>Policy evaluation</dt>
              <dd className="mono">{policy.evaluation.policy_evaluation_id}</dd>
            </div>
            <div>
              <dt>Policy input hash</dt>
              <dd className="mono">{policy.evaluation.input_hash}</dd>
            </div>
          </dl>
          <p>
            Full evidence and signal provenance remains attached to the referenced Account State
            snapshot above; M1C does not duplicate or reinterpret it.
          </p>
        </div>
      </details>
      <p className="proposed-only-notice">
        M1C ends at a proposed disposition. No action, approval, task, CRM write, or external
        execution exists here.
      </p>
    </section>
  );
}
