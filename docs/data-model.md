# Data model

## M1A scope

M1A introduces the smallest canonical foundation for the first GTM trace. It contains no contacts,
signals, scores, account states, decisions, policies, actions, outcomes, providers, or workers.

```text
Workspace 1 ──< StrategyVersion 1 ──< Evidence (strategy assertion)
Workspace 1 ──< Account         1 ──< Evidence (account observation)
```

Every evidence row targets exactly one supported M1A target: a strategy version or an account.

## Workspace

`workspaces` is a schema boundary only. It does not implement authentication, billing, workspace
management, or production multitenancy.

- Stable UUID, unique slug, name, demo mode, nullable `demo_as_of`, and creation time.
- M1A seeds only **Northstar Revenue Systems Demo**.
- Its fixed `demo_as_of` is `2026-09-15T12:00:00Z`. Fixture timestamps and freshness are interpreted
  relative to this snapshot—not the viewer's wall clock.

## Strategy versions

`strategy_versions` belongs to a workspace and stores semantic version, lifecycle status, title,
summary, synthetic disclaimer, and creation/activation times.

- Semantic version is unique within a workspace.
- A partial PostgreSQL unique index allows one `ACTIVE` strategy per workspace.
- M1A has no strategy write API. Revisions are new records in a later controlled workflow.

Strategy assertions are `evidence` records with a required strategy topic. The seeded strategy covers
market, segmentation, ICP, buyer, problem, value proposition, offer, pricing, messaging, channels,
motion, and experiment assumptions. Every seeded assertion is visibly synthetic and classified as a
`HYPOTHESIS`, never as validated market research.

## Accounts

`accounts` belongs to a workspace and stores stable canonical identity: UUID, slug, canonical name,
domain, segment, synthetic flag, and timestamps.

Slug and domain uniqueness are scoped to workspace. There are no relationship, opportunity, score,
or state columns. The demo's existing-relationship condition is preserved solely as account evidence.

## Evidence

`evidence` preserves source provider, source reference, optional URI, observed and ingested times,
normalized fact/statement, optional raw-payload SHA-256 hash, freshness, and optional confidence.

Epistemic classification is explicit:

- `FACT`: confidence must be null.
- `INFERENCE`: optional 0–1 epistemic interpretation confidence.
- `HYPOTHESIS`: optional 0–1 epistemic hypothesis confidence.

This confidence is not extraction or model-parsing confidence. A separate evidence-quality/model layer
will be introduced only when such a provider exists.

Freshness is fixture-declared in M1A (`CURRENT`, `STALE`, or `UNKNOWN`) against `demo_as_of`; automatic
production freshness calculation is intentionally not implemented.

## M1B.1 deterministic signals

M1B.1 adds machine-readable `fact_key` and `fact_assertion` fields to account evidence. Both are
nullable as a pair, so strategy, firmographic, and relationship evidence can remain outside signal
processing. The initial evaluator accepts exact-key `FACT` evidence only.

```text
SignalDefinition 1 ---< SignalEvaluation >--- 1 Account
                              |
                              +---< EvaluationEvidence >--- Evidence
                              |
                              +--- 0..1 Signal
```

- `signal_definitions` belongs to one workspace and strategy version. It records the stable signal
  key, input fact key, explicit evaluator key, semantic rule version, and freshness window.
- `signal_evaluations` is an immutable ledger. `evaluation_as_of` is its business clock;
  `evaluated_at` is execution time and never drives freshness.
- `evaluation_evidence` is the normalized many-to-many provenance link. Missing-evidence
  evaluations intentionally have no association rows.
- `signals` stores canonical commercial events. Its unique event fingerprint excludes
  `evaluation_as_of` and `evaluated_at`; later DETECTED or STALE evaluations reuse the same event.
- Current ACTIVE/EXPIRED and CURRENT/STALE presentation values are derived from the latest linked
  evaluation rather than stored on the canonical event.

The demo evaluates two definitions across three accounts. Fit, firmographics, and Cinderlake's
existing-relationship evidence are not signals.
