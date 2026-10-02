import type { AccountState } from "@/lib/api";
import { formatSnapshot } from "@/lib/api";

type AccountStateSectionProps = {
  data: AccountState;
};

function humanize(value: string): string {
  return value.replaceAll("_", " ").toLowerCase();
}

function facetReasons(data: AccountState, facet: string): string[] {
  return data.reasons
    .filter((item) => item.facet === facet)
    .sort((left, right) => left.position - right.position)
    .map((item) => humanize(item.reason_code));
}

export function AccountStateSection({ data }: AccountStateSectionProps) {
  const snapshot = data.snapshot;
  const facets = [
    ["Fit", snapshot.fit_context],
    ["Timing", snapshot.timing_state],
    ["Relationship", snapshot.relationship_state],
    ["Evidence", snapshot.evidence_sufficiency],
  ] as const;

  return (
    <section className="account-state-section" aria-labelledby="account-state-title">
      <div className="section-heading product-section-heading">
        <div>
          <p className="eyebrow">Account state</p>
          <h2 id="account-state-title">What the record currently supports</h2>
        </div>
        <p>
          A descriptive snapshot at the fixed semantic time, relative to the active synthetic
          strategy hypothesis.
        </p>
      </div>
      <div className="state-facet-grid">
        {facets.map(([label, value]) => (
          <article className="state-facet" key={label}>
            <span>{label}</span>
            <strong>{humanize(value)}</strong>
          </article>
        ))}
      </div>
      <dl className="state-snapshot-meta">
        <div>
          <dt>Snapshot</dt>
          <dd>{formatSnapshot(snapshot.state_as_of)}</dd>
        </div>
        <div>
          <dt>Strategy version</dt>
          <dd className="mono">{snapshot.strategy_version_id}</dd>
        </div>
        <div>
          <dt>State engine</dt>
          <dd className="mono">{snapshot.state_engine_version}</dd>
        </div>
      </dl>
      <details className="state-provenance">
        <summary>Inspect state reasons and provenance</summary>
        <div className="state-provenance-body">
          <section aria-labelledby="state-reasons-title">
            <h3 id="state-reasons-title">Facet reasons</h3>
            <div className="state-reason-grid">
              {[
                ["Fit", "FIT_CONTEXT"],
                ["Timing", "TIMING_STATE"],
                ["Relationship", "RELATIONSHIP_STATE"],
                ["Evidence", "EVIDENCE_SUFFICIENCY"],
              ].map(([label, facet]) => (
                <div key={facet}>
                  <strong>{label}</strong>
                  <ul>
                    {facetReasons(data, facet).map((reason) => (
                      <li key={reason}>{reason}</li>
                    ))}
                  </ul>
                </div>
              ))}
            </div>
          </section>
          <section aria-labelledby="fit-trace-title">
            <h3 id="fit-trace-title">Fit interpretation</h3>
            {data.fit_criteria.map((trace) => (
              <article className="state-trace-card" key={trace.fit_criterion_id}>
                <div>
                  <span className="record-label">{humanize(trace.criterion_result)}</span>
                  <h4>{trace.criterion.display_name}</h4>
                  <p>{trace.criterion.description}</p>
                </div>
                <dl>
                  <div>
                    <dt>Criterion key</dt>
                    <dd className="mono">{trace.criterion_stable_key}</dd>
                  </div>
                  <div>
                    <dt>Input fact</dt>
                    <dd className="mono">{trace.input_fact_key}</dd>
                  </div>
                  <div>
                    <dt>Expected</dt>
                    <dd>{humanize(trace.expected_assertion)}</dd>
                  </div>
                  <div>
                    <dt>Observed</dt>
                    <dd>
                      {trace.observed_assertion === null
                        ? "No determinate assertion"
                        : humanize(trace.observed_assertion)}
                    </dd>
                  </div>
                  <div>
                    <dt>Hypothesis source</dt>
                    <dd className="mono">{trace.source_strategy_evidence.source_reference}</dd>
                  </div>
                  <div>
                    <dt>Account evidence</dt>
                    <dd>
                      {trace.account_evidence.length === 0
                        ? "No eligible evidence at this snapshot"
                        : trace.account_evidence.map((item) => item.source_reference).join(", ")}
                    </dd>
                  </div>
                </dl>
              </article>
            ))}
          </section>
          <section aria-labelledby="relationship-trace-title">
            <h3 id="relationship-trace-title">Relationship evidence</h3>
            <p>
              {data.relationship_evidence.length === 0
                ? "No eligible relationship evidence at this snapshot."
                : data.relationship_evidence.map((item) => item.source_reference).join(", ")}
            </p>
          </section>
          <section aria-labelledby="timing-trace-title">
            <h3 id="timing-trace-title">Timing evaluations</h3>
            <div className="state-timing-list">
              {data.signal_evaluations.map((trace) => (
                <div key={trace.evaluation.evaluation_id}>
                  <strong>{trace.definition.display_name}</strong>
                  <span>
                    {humanize(trace.evaluation.result)} / {humanize(trace.evaluation.reason_code)}
                  </span>
                </div>
              ))}
            </div>
          </section>
          <section aria-labelledby="state-technical-title">
            <h3 id="state-technical-title">Snapshot identity</h3>
            <dl className="state-technical-grid">
              <div>
                <dt>Snapshot ID</dt>
                <dd className="mono">{snapshot.state_snapshot_id}</dd>
              </div>
              <div>
                <dt>Input hash</dt>
                <dd className="mono">{snapshot.input_hash}</dd>
              </div>
              <div>
                <dt>Materialized</dt>
                <dd>{formatSnapshot(snapshot.computed_at)}</dd>
              </div>
              <div>
                <dt>Evaluators</dt>
                <dd className="mono">
                  fit {data.evaluator_manifest.fit.evaluator_key}@
                  {data.evaluator_manifest.fit.version}; timing{" "}
                  {data.evaluator_manifest.timing.evaluator_key}@
                  {data.evaluator_manifest.timing.version}; relationship{" "}
                  {data.evaluator_manifest.relationship.evaluator_key}@
                  {data.evaluator_manifest.relationship.version}; evidence{" "}
                  {data.evaluator_manifest.evidence_sufficiency.evaluator_key}@
                  {data.evaluator_manifest.evidence_sufficiency.version}
                </dd>
              </div>
            </dl>
          </section>
        </div>
      </details>
    </section>
  );
}
