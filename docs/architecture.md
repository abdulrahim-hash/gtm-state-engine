# Architecture

## Current M1B.1 boundary

M0 established the engineering foundation. M1A added the versioned synthetic strategy, minimal
workspace boundary, canonical accounts, and evidence provenance. M1B.1 adds deterministic
commercial-event evaluation and preserves every result, including negative and inconclusive ones.

It still contains no contacts, scoring, account-state snapshots, relationship state, decisions,
policies, actions, outcomes, workers, model providers, vendor adapters, or live actions.

```text
Next.js (read-only product views)
        | typed HTTP contract
        v
FastAPI + Pydantic (read-only strategy/account/evidence/signal API)
        | synchronous SQLAlchemy 2.x / psycopg 3
        v
PostgreSQL (canonical evidence, evaluation history, and signal events)
```

Later milestones add controlled review/approve/reject interactions and dry-run actions. Risky
external actions remain review-gated unless an explicit policy authorizes them.

## Component responsibilities

### Web

Next.js provides the read-only product surface. Account detail shows canonical commercial events and
their evidence traces while keeping non-detected evaluations in a collapsed inspection surface.
Client-side requests through the same-origin `API_BASE_URL` rewrite keep production builds
independent of a running API.

### API and evaluator registry

FastAPI owns typed read boundaries. Deterministic evaluator implementations live in a code-owned
registry keyed by `(evaluator_key, rule_version)`. Definitions select a registered evaluator
explicitly; stable signal keys do not imply executable behavior, and definitions contain no
user-authored expressions.

The initial evaluator accepts exact-match, FACT-only normalized evidence. It uses
`evaluation_as_of` for freshness and records `evaluated_at` only as execution time.

### Database

PostgreSQL is canonical analytical/event memory. SQLAlchemy 2.x uses synchronous psycopg 3 access on
Python 3.13; there is still no demonstrated need for async database complexity.

Evaluations are immutable conclusions at a semantic time. Signals are canonical commercial events.
An event fingerprint excludes evaluation time, allowing detected and stale reevaluations to link to
the same signal. Relational `evaluation_evidence` rows preserve the input trace.

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
seed creates typed event evidence and signal definitions, then invokes the production evaluator
service; it does not insert hand-authored evaluation or signal outcomes.

## Deployment portability

The architecture assumes a portable Next.js host, a container-capable FastAPI host, and standard
PostgreSQL. Supabase may host PostgreSQL but is not embedded into domain architecture.
