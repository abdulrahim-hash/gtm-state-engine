# Architecture

## M0 boundary

M0 establishes the engineering foundation only. It contains no GTM domain entities, synthetic
accounts, workers, model providers, vendor adapters, live actions, metrics, or outcomes.

```text
Next.js (read-mostly M0)
        │ typed HTTP contract
        ▼
FastAPI + Pydantic
        │ synchronous SQLAlchemy 2.x / psycopg 3
        ▼
PostgreSQL
```

Later milestones add controlled review/approve/reject interactions and dry-run actions. Risky
external actions remain review-gated unless an explicit policy authorizes them.

## Component responsibilities

### Web

Next.js provides the recruiter-facing product surface. In M0 it communicates product intent,
architecture, demo-data status, and safety boundaries. It does not simulate domain data.

### API

FastAPI owns typed HTTP boundaries and application services. M0 exposes process liveness and
bounded PostgreSQL readiness only. Production mode disables interactive API documentation.

### Database

PostgreSQL is canonical analytical/event memory. SQLAlchemy 2.x uses synchronous psycopg 3 access;
there is no demonstrated need for async database complexity in M0.

### Contracts

```text
FastAPI/Pydantic schemas
        → app.openapi()
        → committed openapi.json
        → openapi-typescript
        → committed generated TypeScript types
```

Generation imports the application directly and does not require a running API server. Stable JSON
key ordering and committed generated output make contract drift reviewable and CI-blocking.

### Migrations

Alembic owns PostgreSQL schema evolution. The M0 baseline intentionally creates no domain tables;
Alembic records only its version marker. GTM tables start in M1 through reviewed migrations.

## Deployment portability

The architecture assumes a portable Next.js host, a container-capable FastAPI host, and standard
PostgreSQL. Supabase may host PostgreSQL but is not embedded into domain architecture.

