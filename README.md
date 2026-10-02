# GTM State & Signal Engine

**Know who matters, why now, and what to do next—with evidence.**

The GTM State & Signal Engine is strategy-aware, evidence-backed infrastructure for maintaining
trustworthy account state and producing auditable, policy-governed GTM decisions.

This repository is intentionally not an AI SDR, lead scraper, CRM replacement, email generator, or
vendor workflow showcase.

## Current status: M1B.2 deterministic account-state slice

M0 established:

- a minimal recruiter-facing Next.js shell;
- a synchronous FastAPI service using typed Pydantic boundaries;
- SQLAlchemy 2.x with psycopg 3;
- an Alembic baseline with no artificial GTM domain tables;
- local PostgreSQL through Docker Compose;
- deterministic OpenAPI-to-TypeScript contract generation;
- blocking test, lint, format, type, build, migration, contract, and secret-detection gates;
- architecture, security, source-of-truth, ADR, and build-journal documentation.

M1A adds:

- one fixed synthetic workspace with a deterministic demo snapshot date;
- a versioned synthetic GTM strategy whose assertions are visible hypotheses;
- canonical workspace-scoped accounts and provenance-bearing evidence;
- read-only strategy, account, and evidence APIs with committed typed contracts;
- strategy, account list, account detail, and provenance product views.

M1B.1 adds:

- versioned, strategy-aware deterministic signal definitions;
- immutable evaluation history for detected, stale, negative, and inconclusive results;
- canonical commercial-event identities that remain stable across reevaluation time;
- normalized relational evidence traces;
- read-only signal and evaluation APIs plus restrained account-detail signal views.

M1B.2 adds:

- explicit strategy-relative fit criteria backed by synthetic strategy hypotheses;
- immutable account-state snapshots with Fit, Timing, Relationship, and Evidence Sufficiency facets;
- code-owned, versioned state evaluators and deterministic input-hash identities;
- normalized reason, evidence, fit-criterion, and signal-evaluation provenance;
- read-only current, history, and immutable snapshot APIs;
- a restrained Account State section on account detail.

M1B.2 does not implement contacts, numeric fit or priority scoring, recommendations, downstream
authorization, external execution, outcomes, models, workers, or providers.

## System spine

```text
Strategy → Evidence → Signal → State → Decision → Policy → Action → Outcome
```

Strategy governs the loop. Every material conclusion must remain traceable to evidence and the
strategy or policy version that produced it.

## Safety boundary

- Public demo data is synthetic.
- Prospect/client PII and private CRM exports are prohibited.
- External actions are disabled by default.
- Risky actions will require policy authorization and human review.
- PostgreSQL is canonical analytical/event memory; vendors remain adapters.
- No live provider credentials belong in this repository.

See [Security](docs/security.md) and [Source of truth](docs/source-of-truth.md).

## Prerequisites

- Node.js 24 and npm 11
- Python 3.13 managed by [uv](https://docs.astral.sh/uv/)
- Docker with either `docker compose` or `docker-compose`

## Fresh setup

1. Clone the repository and enter its directory.
2. Create a local environment file:

   ```powershell
   Copy-Item .env.example .env
   ```

   On macOS/Linux, use `cp .env.example .env`.

3. Install pinned dependencies:

   ```powershell
   npm ci
   uv sync --project apps/api --locked --all-groups
   ```

4. Start PostgreSQL:

   ```powershell
   docker-compose --env-file .env -f infra/compose.yaml up -d postgres
   ```

   If your installation uses the Docker CLI plugin, replace `docker-compose` with
   `docker compose`.

5. Apply and inspect migrations:

   ```powershell
   npm run db:migrate
   npm run db:seed-demo
   npm run db:current
   ```

6. Start the API:

   ```powershell
   uv run --project apps/api uvicorn gtm_state_api.main:app --app-dir apps/api/src --reload
   ```

7. In a second terminal, start the web app:

   ```powershell
   npm run web:dev
   ```

The web app is available at `http://localhost:3000`. The API liveness endpoint is
`http://localhost:8000/health/live`.

## Validation

```powershell
npm run contracts:check
npm run format:check
npm run lint
npm run typecheck
npm test
npm run db:migrate
npm run api:test:integration
npm run web:build
```

CI additionally regenerates committed contracts and fails on drift, validates migrations and
seed on PostgreSQL, and runs blocking secret detection.

## Repository map

- `apps/web`: read-only strategy, account, evidence, signal, evaluation, and state views
- `apps/api`: FastAPI service, migration configuration, and tests
- `packages/contracts`: committed OpenAPI artifact and generated TypeScript types
- `infra`: local PostgreSQL configuration
- `docs`: architecture, security, ADRs, setup, and build history

## Documentation

- [Architecture](docs/architecture.md)
- [Data model](docs/data-model.md)
- [Local development](docs/local-development.md)
- [Security](docs/security.md)
- [Source of truth](docs/source-of-truth.md)
- [Architecture decisions](docs/decisions/)
- [Master product brief](PROJECT_1_GTM_STATE_SIGNAL_ENGINE_MASTER_BRIEF.md)

## License

Apache-2.0.

## Current build status

The project is currently at **M1B.2 - Deterministic Account State**.

### Working today

- Versioned synthetic GTM strategy
- Canonical workspaces and accounts
- Evidence provenance with FACT / INFERENCE / HYPOTHESIS separation
- Deterministic signal definitions
- Reproducible signal evaluations
- Canonical commercial-event identity
- DETECTED / STALE / NO_MATCH / INCONCLUSIVE evaluation paths
- Immutable account-state snapshots
- Strategy-relative categorical fit
- ACTIVE / STALE / NONE / UNKNOWN / INCONCLUSIVE timing paths
- Explicit relationship context and evidence sufficiency
- Normalized state provenance
- Read-only FastAPI endpoints
- Strategy, accounts, evidence, and signal UI
- PostgreSQL migrations
- Deterministic demo fixtures
- Contract drift checks
- Unit, integration, and frontend tests
- CI and secret scanning

### Current architecture

Strategy
->
Evidence
->
Deterministic Evaluation
->
Canonical Signal
->
Account State

### Current boundary

M1B.2 ends at descriptive account state. Ranking, recommendations, downstream authorization,
activation, AI, and external providers remain intentionally out of scope.

