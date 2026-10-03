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

## M1C deterministic Decision and Policy

M1C adds two separate immutable ledgers after Account State:

```text
AccountStateSnapshot -> DecisionEvaluation
AccountStateSnapshot + DecisionEvaluation -> PolicyEvaluation
```

### Definitions

`decision_definitions` and `policy_definitions` belong to a workspace and strategy version. Each
immutable version records a stable key, definition version, code-owned evaluator key/version,
status, and descriptive metadata. Policy definitions additionally declare the bounded target;
M1C supports `PROSPECTING_ACTIVATION` only.

Partial unique indexes enforce **at most one** enabled Decision definition per workspace/strategy
and at most one enabled Policy definition per workspace/strategy/target. The materialization service
requires exactly one and fails closed if zero are enabled or if the selected evaluator pair is not
registered. It never falls back to another definition. Seed reruns validate existing semantic fields
instead of mutating definitions.

### Decision evaluations

`decision_evaluations` references one exact `state_snapshot_id` and definition version. Results are
ENGAGE, HOLD, NO_ACTION, or ABSTAIN. ENGAGE means **engagement merits consideration**; it is not an
action or execution command. `decision_evaluation_reasons` stores the exact ordered explanation.

Decision version 1 uses Fit, Timing, and relevant Evidence Sufficiency semantics. Relationship does
not alter desirability. A complete snapshot remains the authoritative input, so a relationship-only
snapshot revision creates a new Decision identity even if the Decision enum remains ENGAGE.

### Policy evaluations

`policy_evaluations` references the exact Decision and the exact same state snapshot. Results are
ALLOW, REQUIRE_REVIEW, or BLOCK. ALLOW permits progression only to a future planning boundary and
does not authorize external action. `policy_evaluation_reasons` stores every applicable constraint
in deterministic order: BLOCK reasons, REQUIRE_REVIEW reasons, then ALLOW-only support reasons when
the result is ALLOW.

Relationship is a Policy input in version 1. UNKNOWN is not treated as relationship absence;
NO_EXISTING_RELATIONSHIP requires the explicit M1B.2 state.

### Identity and provenance

Canonical SHA-256 hashes include the full snapshot attestation, scope, exact definition identity,
and evaluator version. Policy additionally includes the exact Decision identity/hash/result.
Operational `computed_at`, `evaluated_at`, and `created_at` values are excluded. UUIDv5 derives
stable evaluation IDs from those hashes.

Provenance is normalized and non-duplicative:

```text
PolicyEvaluation
  -> DecisionEvaluation
  -> AccountStateSnapshot
  -> existing M1B.2 reasons, evidence, criteria, and signal evaluations
```

There are no Decision-to-Evidence or Policy-to-Evidence junctions and no stored disposition table.
The API composes the two evaluations as `PROPOSED_ONLY` with
`external_action_authorized = false`.

The synthetic demo outcomes are:

- Asterwind: ENGAGE / REQUIRE_REVIEW.
- Bramble: ABSTAIN / BLOCK.
- Cinderlake: ENGAGE / REQUIRE_REVIEW.

No demo evidence is added or altered to manufacture an ALLOW example; that path exists only in
isolated evaluator tests.

## M1D governed Action and operational Outcome

```text
ActionOutcome -> ActionAttempt -> Action -> PolicyEvaluation
                                     |                 |
                              ActionReview       DecisionEvaluation
                                                       |
                                                AccountStateSnapshot
```

`actions` stores immutable vendor-neutral business-intent proposals, not execution. The only
types are `REQUEST_RESEARCH` and `CREATE_SELLER_TASK`. Each uses strict version-1 bounded
payload codes; provider JSON, commands, contacts, owners, channels, and messages are absent.
BLOCK materializes no Action. Unsupported valid chains project `NO_SUPPORTED_ACTION` without an
Action row. `GET /accounts/{id}/action` reads the current M1D projection, whereas plural
`/actions` reads persisted history only.

The Action semantic input hashes exact Policy and Decision IDs/input hashes, the State snapshot
ID, definition/evaluator versions, ordered Policy reasons, Action type/version, and canonical
payload. SHA-256 plus UUIDv5 gives deterministic identity independent of clocks and JSON key
order. A new PolicyEvaluation ID changes the Action ID. Composite scope foreign keys prevent an
Action from crossing workspace/account/strategy boundaries.

`action_reviews` stores one immutable terminal APPROVED or REJECTED resolution per
review-required Action. The client supplies only bounded resolution/reason and a constrained
Idempotency-Key; only its hash is persisted. Actor kind/ref are server-stamped
`UNVERIFIED_DEMO_HUMAN` for local commands or `SYNTHETIC_FIXTURE` for the seeded trace. No
authenticated identity is implied. The Action lifecycle is derived as REVIEW_REQUIRED,
READY_FOR_DRY_RUN, or REJECTED; no status column exists.

`action_attempts` has only mode DRY_RUN. `action_outcomes` records one immutable operational
result per Attempt: SUCCEEDED/CANONICAL_ACTION_VALIDATED or
FAILED/CANONICAL_ACTION_INVALID. The database enforces `external_side_effects=false`.
Missing approval, rejection, invalid client input, or unavailable actions return errors and create
no Attempt. Stored payload/hash/version/authority integrity faults create FAILED traces.

The three-account demo preserves upstream fixtures exactly: Asterwind proposes relationship
research under review; Bramble projects BLOCKED_BY_POLICY with no Action; Cinderlake proposes
relationship-coordination seller work, has visibly synthetic approval, and passes local dry-run
validation. No seller task was actually created. ALLOW remains an isolated test fixture.
## M2A source and normalization provenance

`accounts.segment` is nullable. Northstar fixtures retain their exact strings; a new imported
Account has null segment until a separately approved classification exists. Existing `evidence`
rows remain unchanged and have null `normalization_result_id`.

| Table | Identity and purpose | Mutability |
| --- | --- | --- |
| `ingestion_batches` | Semantic UUIDv5 from workspace, source/dataset, schema version, exact file-byte SHA-256. Carries mapper/identity versions, ingestion time, correlation ID, expected rows. | Immutable |
| `ingestion_batch_rows` | Batch plus ordinal; preserves every file occurrence and bounded accepted/rejected/unresolved/duplicate outcome. | Immutable |
| `source_observations` | Scoped external record ID, source observation time, and allowed-field payload hash. Stores approved parsed fields only, bounded to 4 KiB JSONB, plus first batch/row origin. | Immutable |
| `account_source_ids` | Workspace/source/dataset/external account ID binding to canonical Account and establishing observation. | Immutable; no rebind |
| `normalization_results` | Observation plus mapper/version and identity-rule version. Stores outcome, reason, resolution-input hash, and one accepted fact slot. | Immutable |
| `evidence_supersessions` | Explicit old/new imported Evidence edge after same-Account promotion. | Append only |

`evidence.normalization_result_id` is nullable for historical/manual/synthetic rows and unique for
imports. An accepted result owns one canonical fact slot. Imported Evidence provenance is
Evidence -> result -> observation -> first batch; batch rows preserve all file occurrences. The
source observation has its own time, accepted fact has semantic event time, batch has `ingested_at`,
and result has `processed_at`. None is substituted for another.

PostgreSQL composite foreign keys enforce workspace scope on batch/observation, Account binding,
normalization, and Evidence-to-result Account. Source/dataset scope is enforced between an
observation and its first batch and between a binding and its establishing observation. Batch-row
observation/result scope, normalization result source agreement beyond workspace, and same-Account
supersession remain service-enforced and tested. These are not duplicated into every table simply
to create redundant foreign-key columns.

Import outcomes are facts about input processing, not mutable workflow status. File-level refusal
commits nothing; row-level rejection retains a bounded reason. Same ID and source time with
changed allowed content records a `SOURCE_RECORD_CONFLICT` result and creates no second accepted
Evidence. A new timestamp is a new observation. Replay never rewrites a previous result or Evidence.
The downgrade refuses while batches exist or any Account has a null segment; it cannot safely
represent those rows in M1D.
