"use client";

import { useState } from "react";

import { dryRunAction, reviewAction, type CurrentAccountAction } from "@/lib/api";

type Props = {
  data: CurrentAccountAction;
  onRefresh: () => Promise<void>;
};

function humanize(value: string): string {
  return value.replaceAll("_", " ").toLowerCase();
}

export function ActionOutcomeSection({ data, onRefresh }: Props) {
  const current = data.current;
  const detail = current.action;
  const action = detail?.action;
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [rejectionReason, setRejectionReason] = useState<
    "REJECTED_INSUFFICIENT_CONTEXT" | "REJECTED_ACTION_NOT_APPROPRIATE"
  >("REJECTED_INSUFFICIENT_CONTEXT");

  async function submitReview(resolution: "APPROVED" | "REJECTED") {
    if (action === undefined) return;
    setBusy(true);
    setError(null);
    try {
      await reviewAction(
        action.action_id,
        {
          resolution,
          reason_code: resolution === "APPROVED" ? "APPROVED_AS_PROPOSED" : rejectionReason,
        },
        crypto.randomUUID(),
      );
      await onRefresh();
    } catch {
      setError("Review could not be recorded. Reload the account and check its current state.");
    } finally {
      setBusy(false);
    }
  }

  async function submitDryRun() {
    if (action === undefined) return;
    setBusy(true);
    setError(null);
    try {
      await dryRunAction(action.action_id);
      await onRefresh();
    } catch {
      setError("Dry-run validation could not advance. Reload the account and check its review.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="action-outcome-section" aria-labelledby="action-title">
      <div className="section-heading product-section-heading">
        <div>
          <p className="eyebrow">Action → Outcome / Trace</p>
          <h2 id="action-title">What is proposed, and what happened afterward?</h2>
        </div>
        <p>The Action preserves business intent. Dry-run results describe local validation only.</p>
      </div>
      {current.projection === "BLOCKED_BY_POLICY" ? (
        <div className="action-card">
          <p className="eyebrow">No Action proposal</p>
          <h3>Blocked by Policy</h3>
          <p>Policy blocked progression. No canonical Action row or dry-run attempt exists.</p>
          <ul>
            {current.policy_reason_codes.map((reason) => (
              <li key={reason}>{humanize(reason)}</li>
            ))}
          </ul>
        </div>
      ) : null}
      {current.projection === "NO_SUPPORTED_ACTION" ? (
        <div className="action-card">
          <p className="eyebrow">No Action proposal</p>
          <h3>No supported Action</h3>
          <p>The exact Decision and Policy do not map to an M1D Action type.</p>
        </div>
      ) : null}
      {detail !== null && action !== undefined ? (
        <div className="action-grid">
          <article className="action-card">
            <p className="eyebrow">Action proposal</p>
            <h3>{humanize(action.action_type)}</h3>
            <p>
              {action.action_type === "REQUEST_RESEARCH"
                ? "Research the account-level relationship context before engagement planning."
                : "Assess a controlled engagement path with a seller. No seller task exists yet."}
            </p>
            <dl className="action-fields">
              {Object.entries(action.payload).map(([key, value]) => (
                <div key={key}>
                  <dt>{humanize(key)}</dt>
                  <dd>{humanize(String(value))}</dd>
                </div>
              ))}
            </dl>
            <span className="action-badge">{humanize(detail.lifecycle)}</span>
          </article>
          <article className="action-card">
            <p className="eyebrow">Human review</p>
            <h3>
              {detail.review === null
                ? detail.lifecycle === "REVIEW_REQUIRED"
                  ? "Review required"
                  : "No review required"
                : humanize(detail.review.resolution)}
            </h3>
            {detail.review !== null ? (
              <p>
                {detail.review.reviewer_kind === "SYNTHETIC_FIXTURE"
                  ? "Synthetic fixture approval or rejection; no real human identity is asserted."
                  : "Local demo review; reviewer identity is unverified."}{" "}
                Reason: {humanize(detail.review.reason_code)}.
              </p>
            ) : null}
            {detail.mutations_enabled && detail.lifecycle === "REVIEW_REQUIRED" ? (
              <div className="action-controls">
                <button disabled={busy} onClick={() => void submitReview("APPROVED")}>
                  Approve for local dry-run
                </button>
                <label htmlFor="rejection-reason">Rejection reason</label>
                <select
                  id="rejection-reason"
                  value={rejectionReason}
                  onChange={(event) =>
                    setRejectionReason(
                      event.target.value as
                        | "REJECTED_INSUFFICIENT_CONTEXT"
                        | "REJECTED_ACTION_NOT_APPROPRIATE",
                    )
                  }
                >
                  <option value="REJECTED_INSUFFICIENT_CONTEXT">Insufficient context</option>
                  <option value="REJECTED_ACTION_NOT_APPROPRIATE">Action not appropriate</option>
                </select>
                <button disabled={busy} onClick={() => void submitReview("REJECTED")}>
                  Reject
                </button>
              </div>
            ) : null}
            {detail.mutations_enabled && detail.lifecycle === "READY_FOR_DRY_RUN" ? (
              <div className="action-controls">
                <button disabled={busy} onClick={() => void submitDryRun()}>
                  Validate canonical Action locally
                </button>
              </div>
            ) : null}
            {!detail.mutations_enabled ? (
              <p className="action-readonly">Public demo is read only.</p>
            ) : null}
            {error !== null ? <p role="alert">{error}</p> : null}
          </article>
        </div>
      ) : null}
      <div className="action-outcome-panel">
        <p className="eyebrow">Outcome / Trace</p>
        {detail === null || detail.attempts.length === 0 ? (
          <p>No dry-run validation outcome has been recorded.</p>
        ) : (
          detail.attempts.map(({ attempt, outcome }) => (
            <div key={attempt.action_attempt_id}>
              <strong>
                {outcome.result === "SUCCEEDED"
                  ? "Dry-run validation succeeded"
                  : "Dry-run validation failed"}
              </strong>
              <p>
                {outcome.result === "SUCCEEDED"
                  ? "The canonical Action and its authority chain passed local deterministic validation."
                  : "The stored canonical Action or its authority chain failed local validation."}
              </p>
              <p>
                {humanize(attempt.mode)} · {humanize(outcome.reason_code)} · External side effects:{" "}
                {outcome.external_side_effects ? "yes" : "none"}
              </p>
            </div>
          ))
        )}
        <details>
          <summary>Inspect exact M1D provenance</summary>
          <dl className="action-fields">
            <div>
              <dt>Policy evaluation</dt>
              <dd className="mono">{current.policy_evaluation_id}</dd>
            </div>
            <div>
              <dt>Decision evaluation</dt>
              <dd className="mono">{data.upstream.decision.evaluation.decision_evaluation_id}</dd>
            </div>
            <div>
              <dt>State snapshot</dt>
              <dd className="mono">{data.upstream.state_snapshot.state_snapshot_id}</dd>
            </div>
            {action !== undefined ? (
              <>
                <div>
                  <dt>Action ID</dt>
                  <dd className="mono">{action.action_id}</dd>
                </div>
                <div>
                  <dt>Semantic hash</dt>
                  <dd className="mono">{action.semantic_input_hash}</dd>
                </div>
                <div>
                  <dt>Derivation</dt>
                  <dd className="mono">
                    {action.derivation_key}@{action.derivation_version}
                  </dd>
                </div>
              </>
            ) : null}
          </dl>
          <p>Evidence and signal provenance is preserved in Account State above.</p>
        </details>
      </div>
      <p className="proposed-only-notice">
        External execution is not implemented or authorized. No seller task was created, no CRM
        system was touched, no owner was assigned, no message was sent, and no external request
        occurred.
      </p>
    </section>
  );
}
