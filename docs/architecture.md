# Architecture

## Current M1B.2 boundary

M0 established the engineering foundation. M1A added the versioned synthetic strategy, minimal
workspace boundary, canonical accounts, and evidence provenance. M1B.1 adds deterministic
commercial-event evaluation and preserves every result, including negative and inconclusive ones.
M1B.2 derives immutable descriptive account state from explicit strategy-relative fit criteria,
canonical evidence, and same-time signal evaluations.

It still contains no contacts, scoring, recommendations, downstream authorization, execution,
outcomes, workers, model providers, vendor adapters, or live integrations.

```text
Next.js (read-only product views)
        | typed HTTP contract
        v
FastAPI + Pydantic (read-only strategy/evidence/signal/state API)
        | synchronous SQLAlchemy 2.x / psycopg 3
        v
PostgreSQL (canonical evidence, signal history, and immutable state snapshots)
```

Later milestones add controlled review/approve/reject interactions and dry-run actions. Risky
external actions remain review-gated unless an explicit policy authorizes them.

## Component responsibilities

### Web

Next.js provides the read-only product surface. Account detail shows four descriptive state facets,
canonical commercial events, and their evidence traces while keeping detailed provenance in
collapsed inspection surfaces.
Client-side requests through the same-origin `API_BASE_URL` rewrite keep production builds
independent of a running API.

### API and evaluator registries

FastAPI owns typed read boundaries. Deterministic evaluator implementations live in a code-owned
registry keyed by `(evaluator_key, rule_version)`. Definitions select a registered evaluator
explicitly; stable signal keys do not imply executable behavior, and definitions contain no
user-authored expressions.

The initial evaluator accepts exact-match, FACT-only normalized evidence. It uses
`evaluation_as_of` for freshness and records `evaluated_at` only as execution time.

The account-state engine is also code-owned and versioned. Its manifest selects explicit fit,
timing, relationship, and evidence-sufficiency evaluators. Fit executes only normalized strategy
criteria; it never parses strategy prose. Timing consumes the exact same-time evaluations returned
by signal recomputation. Relationship absence requires explicit FACT evidence.

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
seed creates typed criteria, normalized evidence, and signal definitions, then invokes the
production evaluator services; it does not insert hand-authored evaluation, signal, or state
outcomes. Fixture-owned normalization preserves original evidence IDs, prose, sources, and
raw-payload hashes and is not a production evidence-update pattern.

## Deployment portability

The architecture assumes a portable Next.js host, a container-capable FastAPI host, and standard
PostgreSQL. Supabase may host PostgreSQL but is not embedded into domain architecture.
