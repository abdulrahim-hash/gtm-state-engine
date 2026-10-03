# Architecture

## Current M1D boundary

M0 established the engineering foundation. M1A added the versioned synthetic strategy, minimal
workspace boundary, canonical accounts, and evidence provenance. M1B.1 adds deterministic
commercial-event evaluation and preserves every result, including negative and inconclusive ones.
M1B.2 derives immutable descriptive account state from explicit strategy-relative fit criteria,
canonical evidence, and same-time signal evaluations.
M1C consumes one exact state snapshot to produce a deterministic Decision and then applies a
separate deterministic Policy gate to that Decision and the same snapshot.
M1D consumes that exact chain to propose one bounded Action intent or an explicit non-Action
projection. It records immutable review, local dry-run Attempt, and operational Outcome traces.

It still contains no contacts, owners, messages, scoring, ranking, external execution, commercial
outcomes, workers, model providers, vendor adapters, or live integrations.

```text
Next.js (read-only hosted state, Decision, Policy, Action, and Outcome views)
        | typed HTTP contract
        v
FastAPI + Pydantic (typed reads; local-only narrow review and dry-run commands)
        | synchronous SQLAlchemy 2.x / psycopg 3
        v
PostgreSQL (canonical provenance plus immutable Action, Review, Attempt, and Outcome history)
```

M1D's review approval authorizes only local deterministic validation. Even Policy ALLOW never
authorizes an external action. Production configuration rejects enabled Action mutations.

## Component responsibilities

### Web

Next.js provides the read-only product surface. Account detail separates Account State (“What is
true?”), Decision (“What response merits consideration?”), and Policy (“May it advance?”), followed
by canonical commercial events and evidence traces. The internal Decision enum `ENGAGE` is rendered
as “Engagement merits consideration,” never as an execution command.
Client-side requests through the same-origin `API_BASE_URL` rewrite keep production builds
independent of a running API.

### API and evaluator registries

FastAPI owns typed read boundaries. Deterministic evaluator implementations live in a code-owned
registry keyed by `(evaluator_key, evaluator_version)`. Definitions select a registered evaluator
explicitly; stable signal keys do not imply executable behavior, and definitions contain no
user-authored expressions.

The initial evaluator accepts exact-match, FACT-only normalized evidence. It uses
`evaluation_as_of` for freshness and records `evaluated_at` only as execution time.

The account-state engine is also code-owned and versioned. Its manifest selects explicit fit,
timing, relationship, and evidence-sufficiency evaluators. Fit executes only normalized strategy
criteria; it never parses strategy prose. Timing consumes the exact same-time evaluations returned
by signal recomputation. Relationship absence requires explicit FACT evidence.

Decision and Policy use separate code-owned registries keyed by `(evaluator_key,
evaluator_version)`. Database definitions choose registered implementations. PostgreSQL partial
unique indexes allow at most one enabled definition in each scope; materialization requires exactly
one and fails closed on zero or unsupported registry selection. No fallback or executable JSON is
available.

The Decision evaluator consumes only one explicit immutable `state_snapshot_id`. Policy consumes
that Decision and the exact same snapshot. Neither reads evidence or signals directly, invokes the
state engine, or changes M1B.2 facets. Relationship is a Policy input only in version 1.

### Database

PostgreSQL is canonical analytical/event memory. SQLAlchemy 2.x uses synchronous psycopg 3 access on
Python 3.13; there is still no demonstrated need for async database complexity.

Evaluations are immutable conclusions at a semantic time. Signals are canonical commercial events.
An event fingerprint excludes evaluation time, allowing detected and stale reevaluations to link to
the same signal. Relational `evaluation_evidence` rows preserve the input trace.

Account-state snapshots are immutable descriptive conclusions. Their UUIDv5 identity derives from a
canonical SHA-256 hash of state-relevant inputs and the evaluator manifest. The hash excludes
operational clocks, UI presentation, and unrelated evidence. Normalized junctions preserve reason,
fit-criterion, evidence, and signal-evaluation provenance.

`state_as_of` is GTM semantic time. `computed_at` is operational materialization time. The current
read selects the latest materialized snapshot for the applicable semantic state_as_of; all earlier
same-time knowledge revisions remain addressable by snapshot ID.

Decision and Policy evaluations are immutable ledgers. Their UUIDv5 identities derive from
canonical SHA-256 hashes containing the complete snapshot attestation and exact
definition/evaluator versions. Operational evaluation time is excluded. A relationship-only
snapshot revision therefore creates a new Decision identity even if its result remains ENGAGE.

Ordered normalized reason rows preserve deterministic explanations. Policy records BLOCK reasons,
then REQUIRE_REVIEW reasons, and emits ALLOW support reasons only for ALLOW. Provenance follows
Policy → Decision → Account State → existing M1B.2 evidence and signal provenance; no redundant
Decision/Policy evidence junctions exist.

The composed disposition is a read projection, not a stored table. Every response is
`PROPOSED_ONLY` with `external_action_authorized = false`. Even Policy `ALLOW` is not external-action
authority.

### Contracts

```text
FastAPI/Pydantic schemas
        -> app.openapi()
        -> committed openapi.json
        -> openapi-typescript
        -> committed generated TypeScript types
```

Generation imports the application directly and does not require a running API server. Stable JSON
key ordering and committed generated output make contract drift reviewable and CI-blocking.

### Migrations and fixtures

Alembic owns PostgreSQL schema evolution. Seed logic remains outside migrations. The idempotent demo
seed creates typed criteria, normalized evidence, signal definitions, and validated Decision/Policy
definitions, then invokes the production evaluator services. It does not insert hand-authored
signal, state, Decision, or Policy outcomes. Fixture-owned normalization preserves original
evidence IDs, prose, sources, and raw-payload hashes and is not a production evidence-update
pattern.

## Deployment portability

The architecture assumes a portable Next.js host, a container-capable FastAPI host, and standard
PostgreSQL. Supabase may host PostgreSQL but is not embedded into domain architecture.

## M1D governed Action boundary

The account surface presents Action proposal and Outcome/Trace after Policy. Local-only review and
dry-run controls appear only when the server enables Action mutations; the browser never submits
reviewer or requester identity. Cinderlake's seeded approval is visibly synthetic.

Action derivation reads only the exact M1C PolicyEvaluation, its DecisionEvaluation, Policy
target/result/ordered reasons, and immutable identity/version metadata. It never reruns Policy or
queries raw Evidence, Signals, Account State facets, or company-specific records. Strict
type/version payload schemas reject unknown keys. BLOCK and unsupported conclusions are
non-Action current projections, while plural Action history contains only persisted proposals.

PostgreSQL stores immutable `actions`, `action_reviews`, `action_attempts`, and
`action_outcomes`. Action UUIDv5 identity derives from SHA-256 canonical full-chain semantic
input, excluding operational clocks. Review and dry-run identities are deterministic, with
uniqueness constraints for retries. Lifecycle is projected from Policy and the one terminal
Review. DRY_RUN validates canonical integrity and authority locally; Outcomes describe only
`CANONICAL_ACTION_VALIDATED` or `CANONICAL_ACTION_INVALID`. The trace follows Outcome ->
Attempt -> Action -> Policy -> Decision -> State -> existing provenance without redundant
Evidence/Signal links. No provider adapter or execution simulator exists.

The M1D Alembic revision contains schema only. Demo seed invokes production Action/workflow
services with fixed synthetic review identity; it does not alter M1C/M1B.2 fixture records.
