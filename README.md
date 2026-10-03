# GTM State & Signal Engine

**Know who matters, why now, and what to do next—with evidence.**

The GTM State & Signal Engine is strategy-aware, evidence-backed infrastructure for maintaining
trustworthy account state and producing auditable, policy-governed GTM decisions.

This repository is intentionally not an AI SDR, lead scraper, CRM replacement, email generator, or
vendor workflow showcase.

## Current status: M2A controlled local Evidence ingestion

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

M1C adds:

- versioned Decision and Policy definitions selecting code-owned deterministic evaluators;
- immutable evaluations anchored to one exact account-state snapshot;
- categorical response posture without numeric scoring or ranking;
- an independent, reason-coded prospecting Policy gate;
- GET-only current, history, and immutable evaluation APIs;
- a separate Decision and Policy account-detail surface;
- a permanently non-executing `PROPOSED_ONLY` disposition.

M1D adds immutable, vendor-neutral `REQUEST_RESEARCH` and `CREATE_SELLER_TASK` **Action
proposals** derived from the exact M1C chain, one terminal review for review-required proposals,
and local deterministic dry-run validation with strictly operational Outcomes. BLOCK creates no
Action. The public demo remains read-only; `ACTION_MUTATIONS_ENABLED` defaults false and cannot
be enabled in production. Cinderlake's approval and dry-run are synthetic fixtures, not actual
seller work or provider execution. No contact, owner, channel, message, CRM update, external
request, or commercial result is implied.

The stored Decision result `ENGAGE` still means **engagement merits consideration**. Neither it,
Policy ALLOW, review approval, nor a successful dry-run authorizes external execution.

M2A adds a **local-only** UTF-8 CSV importer, provider-neutral source-observation and normalization
ledgers, deterministic Account matching with abstention, and exact Evidence provenance. The public
Northstar demo stays synthetic. Imports stop at Evidence and never recompute downstream layers.
A local inspection page traces a batch row to its source observation, normalization result,
Account, and Evidence. There is no live supplier, HTTP upload, or real-data pilot in this milestone.
See [Local development](docs/local-development.md) and [ADR-015](docs/decisions/015-controlled-source-observations.md).

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

- `apps/web`: read-only hosted strategy-to-Outcome trace, with local-only review/dry-run controls
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

The project is currently at **M2A - Controlled local CSV ingestion into canonical Evidence**.

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
- Immutable Decision and Policy evaluations
- Deterministic ordered reason codes
- Exact state-snapshot Decision/Policy provenance
- Non-executing proposed dispositions
- Immutable vendor-neutral Action proposals and terminal Review history
- Deterministic local dry-run Attempts and strictly operational Outcomes
- Read-only hosted FastAPI surface; narrow local-only review/dry-run commands
- Local CSV-to-Evidence import with immutable observation/normalization provenance
- Strategy, account state, Decision, Policy, Action, Outcome, evidence, and signal UI
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
->
Decision
->
Policy
->
Action proposal
->
Local dry-run Outcome

### Current boundary

M2A imports registered local CSV observations into canonical Evidence with conservative Account
identity, bounded provenance, and explicit replay/promotion. Ingestion success does not mean
downstream reasoning is current. Reprocessing does not promote. Source identity is distinct from
canonical Account identity. M1D still ends at an immutable Action proposal, explicit review
authority where required, and a local canonical-validation Outcome. `ALLOW`, review approval, and dry-run success do not authorize
external execution. Contacts, owners, messages, live activation, commercial outcomes, AI
authority, and external providers remain intentionally out of scope.

