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

## M1B.2 deterministic account state

M1B.2 adds one descriptive layer after signal evaluation:

```text
StrategyFitCriterion + Account Evidence + SignalEvaluation
                         |
                         v
                AccountStateSnapshot
```

### Strategy fit criteria

`strategy_fit_criteria` stores the smallest machine-readable interpretation of a strategy
hypothesis: an exact input fact key and expected PRESENT or ABSENT assertion. Every criterion belongs
to a workspace and strategy version and links to the SEGMENTATION or ICP HYPOTHESIS evidence that
justifies it. There are no weights, scores, prose parsers, or executable expressions.

### Account-state snapshots

`account_state_snapshots` is an immutable ledger with four categorical facets:

- Fit Context: MATCH, PARTIAL, MISMATCH, UNKNOWN, or INCONCLUSIVE.
- Timing State: ACTIVE, STALE, NONE, UNKNOWN, or INCONCLUSIVE.
- Relationship State: EXISTING_RELATIONSHIP, NO_EXISTING_RELATIONSHIP, UNKNOWN, or INCONCLUSIVE.
- Evidence Sufficiency: SUFFICIENT, PARTIAL, INSUFFICIENT, or CONTRADICTORY.

NO_EXISTING_RELATIONSHIP requires explicit current FACT evidence whose relationship assertion is
ABSENT. A missing relationship row yields UNKNOWN.

`state_as_of` is semantic time and equals `workspace.demo_as_of` in the synthetic workspace.
`computed_at` is operational materialization time. Multiple snapshots may share the same semantic
scope when late-arriving relevant evidence changes the known inputs.

The SHA-256 input hash includes only state-relevant criteria, evidence, enabled signal definitions,
same-time evaluations, semantic scope, and evaluator versions. UUIDv5 derives stable snapshot
identity from the hash. Operational timestamps, UI presentation, and unrelated evidence are
excluded.

### State provenance

- `state_snapshot_reasons` stores ordered reason codes per facet.
- `state_snapshot_fit_criteria` freezes each participating criterion's stable key, input fact key,
  source strategy-evidence ID, expected assertion, observed assertion, and result.
- `state_snapshot_evidence` maps fit evidence to the exact criterion and stores direct relationship
  evidence links.
- `state_snapshot_signal_evaluations` links every enabled-definition evaluation used by Timing,
  including negative and inconclusive results.

Canonical signals are reached through affirmative signal evaluations. No duplicate snapshot-to-
signal relationship is stored.

The demo deliberately contains no explicit relationship-absence evidence for Asterwind or Bramble,
so both remain UNKNOWN for Relationship. Cinderlake's existing fixture evidence is normalized as
relationship.existing_relationship = PRESENT and yields EXISTING_RELATIONSHIP.
