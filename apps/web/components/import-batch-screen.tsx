"use client";

import { useEffect, useState } from "react";

import {
  getIngestionBatch,
  getIngestionBatchRows,
  type BatchInspection,
  type BatchRows,
} from "@/lib/api";

type Props = { workspaceId: string; batchId: string };

export function ImportBatchScreen({ workspaceId, batchId }: Props) {
  const [batch, setBatch] = useState<BatchInspection | null>(null);
  const [rows, setRows] = useState<BatchRows | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    let cancelled = false;
    void Promise.all([
      getIngestionBatch(workspaceId, batchId),
      getIngestionBatchRows(workspaceId, batchId),
    ])
      .then(([batchResult, rowResult]) => {
        if (!cancelled) {
          setBatch(batchResult);
          setRows(rowResult);
        }
      })
      .catch(() => {
        if (!cancelled) setError(true);
      });
    return () => {
      cancelled = true;
    };
  }, [workspaceId, batchId]);

  return (
    <div className="site-shell product-shell">
      <div className="demo-banner" role="status">
        Local imported-data inspection · Unavailable in the public hosted demo
      </div>
      <main className="product-main import-main">
        <section className="product-intro product-intro-compact">
          <p className="eyebrow">M2A / Input provenance</p>
          <h1>Follow an imported observation into Evidence.</h1>
          <p>
            A committed import ends at canonical Evidence. Signal, State, Decision, Policy, Action,
            and Outcome materialization remain separate.
          </p>
        </section>
        {error ? (
          <p className="data-notice data-notice-error">
            This local batch is unavailable. Public mode does not expose imported workspace data.
          </p>
        ) : null}
        {!error && batch === null ? <p className="data-notice">Loading batch trace…</p> : null}
        {batch !== null ? (
          <section className="import-summary" aria-labelledby="import-summary-title">
            <p className="eyebrow">Batch identity</p>
            <h2 id="import-summary-title">{batch.dataset_key}</h2>
            <dl className="provenance-grid">
              <div>
                <dt>Workspace</dt>
                <dd className="mono">{batch.workspace_id}</dd>
              </div>
              <div>
                <dt>Batch</dt>
                <dd className="mono">{batch.batch_id}</dd>
              </div>
              <div>
                <dt>Source</dt>
                <dd>{batch.source_system_key}</dd>
              </div>
              <div>
                <dt>Schema</dt>
                <dd>
                  {batch.schema_key} · {batch.schema_version}
                </dd>
              </div>
              <div>
                <dt>Mapper</dt>
                <dd>
                  {batch.mapper_key} · {batch.mapper_version}
                </dd>
              </div>
              <div>
                <dt>Identity rule</dt>
                <dd>{batch.identity_rule_version}</dd>
              </div>
              <div>
                <dt>File SHA-256</dt>
                <dd className="mono">{batch.file_sha256}</dd>
              </div>
              <div>
                <dt>Ingested at</dt>
                <dd>{batch.ingested_at}</dd>
              </div>
            </dl>
            <div className="import-counts" aria-label="Row outcome counts">
              {(["accepted", "rejected", "unresolved", "duplicate"] as const).map((key) => (
                <div key={key}>
                  <strong>{batch.counts[key] ?? 0}</strong>
                  <span>{key}</span>
                </div>
              ))}
            </div>
          </section>
        ) : null}
        {rows !== null ? (
          <section className="import-rows" aria-labelledby="import-rows-title">
            <h2 id="import-rows-title">Source rows and results</h2>
            <div className="import-row-list">
              {rows.items.map((row) => (
                <article className="evidence-card" key={row.row_id}>
                  <div className="evidence-card-topline">
                    <span className="evidence-tag">Row {row.ordinal}</span>
                    <span className="freshness">{row.outcome}</span>
                  </div>
                  {row.reason_code !== null ? <p>Reason: {row.reason_code}</p> : null}
                  {row.observation !== null ? (
                    <>
                      <p className="evidence-statement">
                        {row.observation.original_fields.company_name} ·{" "}
                        {row.observation.original_fields.fact_code}
                      </p>
                      <dl className="provenance-grid">
                        <div>
                          <dt>Source record</dt>
                          <dd>{row.observation.external_record_id}</dd>
                        </div>
                        <div>
                          <dt>Observed at source</dt>
                          <dd>{row.observation.source_observed_at}</dd>
                        </div>
                        <div>
                          <dt>Source observation</dt>
                          <dd className="mono">{row.observation.observation_id}</dd>
                        </div>
                        <div>
                          <dt>First observed in batch</dt>
                          <dd className="mono">{row.observation.first_batch_id}</dd>
                        </div>
                        <div>
                          <dt>Citation</dt>
                          <dd className="mono">{row.observation.original_fields.source_url}</dd>
                        </div>
                        {row.normalization !== null ? (
                          <>
                            <div>
                              <dt>Normalization</dt>
                              <dd className="mono">{row.normalization.result_id}</dd>
                            </div>
                            <div>
                              <dt>Result</dt>
                              <dd>{row.normalization.outcome}</dd>
                            </div>
                            <div>
                              <dt>Canonical Account</dt>
                              <dd className="mono">
                                {row.normalization.account_id ?? "Unresolved"}
                              </dd>
                            </div>
                            <div>
                              <dt>Canonical fact</dt>
                              <dd>{row.normalization.fact_key ?? "No Evidence created"}</dd>
                            </div>
                            <div>
                              <dt>Assertion</dt>
                              <dd>{row.normalization.fact_assertion ?? "None"}</dd>
                            </div>
                            <div>
                              <dt>Event time</dt>
                              <dd>{row.normalization.fact_observed_at ?? "Unestablished"}</dd>
                            </div>
                            <div>
                              <dt>Normalized Evidence</dt>
                              <dd>{row.normalization.normalized_fact ?? "None"}</dd>
                            </div>
                          </>
                        ) : null}
                        <div>
                          <dt>Evidence</dt>
                          <dd className="mono">{row.evidence_id ?? "None"}</dd>
                        </div>
                      </dl>
                    </>
                  ) : (
                    <p>The row failed validation before a source observation was admitted.</p>
                  )}
                </article>
              ))}
            </div>
          </section>
        ) : null}
      </main>
    </div>
  );
}
