# Local development

## Runtime pins

- Node.js: major version 24 via `.nvmrc`
- npm: major version 11 via the root engine constraint
- Python: minor version 3.13 via `.python-version`
- Python dependencies: exact resolutions in `uv.lock`
- JavaScript dependencies: exact resolutions in `package-lock.json`

## Install

```powershell
Copy-Item .env.example .env
npm ci
uv sync --project apps/api --locked --all-groups
```

Use `cp .env.example .env` on macOS/Linux.

## Database

```powershell
docker-compose --env-file .env -f infra/compose.yaml up -d postgres
npm run db:migrate
npm run db:seed-demo
npm run db:current
```

`docker compose` may be used instead of `docker-compose` where the plugin is available.

The M0 migration is a deliberate no-op baseline. M1A adds workspace, strategy, account, and evidence
tables. M1B.1 adds typed event facts, signal definitions, immutable evaluations, relational
provenance, and canonical signal events. `db:seed-demo` is deterministic and idempotent; it seeds
the fixed Northstar Revenue Systems Demo snapshot and runs the real evaluator outside Alembic.
M1D adds schema-only Action, Review, Attempt, and Outcome tables. The seed uses production
derivation/workflow services to record Asterwind's review-required research proposal, Bramble's
non-Action BLOCK projection, and Cinderlake's synthetic approval plus local dry-run validation.
Repeated seed runs replay fixed identities without creating duplicates.

## Services

```powershell
uv run --project apps/api uvicorn gtm_state_api.main:app --app-dir apps/api/src --reload
npm run web:dev
```

Run those commands in separate terminals.

The frontend proxies `/api/*` requests to `API_BASE_URL` (default
`http://localhost:8000`). Keep this server-side setting in `.env`; it is not a public credential.
M1D mutation routes are disabled by default. Only for controlled local review/dry-run testing,
set `APP_ENV=development` and `ACTION_MUTATIONS_ENABLED=true` before starting the API.
Never enable this for a publicly accessible demo: there is no production authentication.
`APP_ENV=production` with mutations enabled fails startup. Review requests require a bounded
`Idempotency-Key`; the client cannot submit reviewer or requester identity.

## Contract workflow

To update the committed artifacts after an intentional API-schema change:

```powershell
npm run contracts:generate
```

This imports FastAPI in-process, writes deterministically sorted `openapi.json`, and generates
TypeScript with `openapi-typescript`. Never edit either generated artifact by hand.

To check for contract drift without running an API server:

```powershell
npm run contracts:check
```

## Quality checks

```powershell
npm run format:check
npm run lint
npm run typecheck
npm test
npm run api:test:integration
npm run contracts:check
npm run web:build
```

Integration tests require migrated PostgreSQL. Unit and failure-path tests do not.

## Troubleshooting

- If `uv` cannot use its user cache, set `UV_CACHE_DIR` to a writable workspace-local directory.
- If port 5432 is occupied, stop the conflicting local PostgreSQL service before starting Compose.
- If contract drift fails, regenerate contracts and inspect both committed artifacts before
  accepting the change.
## M2A local ingestion

Migrate to revision `20261003_0007`, then create a separate local workspace:

```powershell
uv run --project apps/api python apps/api/scripts/ingest_local.py create-workspace --slug local-import --name "Local import workspace"
uv run --project apps/api python apps/api/scripts/ingest_local.py validate .\\path\\to\\approved.csv
uv run --project apps/api python apps/api/scripts/ingest_local.py import .\\path\\to\\approved.csv --workspace-id <workspace-uuid>
uv run --project apps/api python apps/api/scripts/ingest_local.py inspect --batch-id <batch-uuid>
```

The exact header is:

```text
source_record_id,source_account_id,company_name,company_domain,source_observed_at,event_at,source_url,fact_code,assertion,source_excerpt
```

The only registered dataset is `company_public_events`, schema `company_public_event/1.0.0`,
mapper `public_company_leader_event/1.0.0`, identity rule `1.0.0`. `fact_code` must be
`new_revenue_leader`; assertion must be `PRESENT`, `ABSENT`, or `INCONCLUSIVE`. An explicit
`event_at` and public HTTPS citation are required to create Evidence. Timestamps must have an
explicit UTC offset. A missing domain remains unresolved unless a safe source-ID binding exists.
Do not put real company files in Git. This milestone does not start a real-data pilot.

For a future reviewed mapper/identity version, use `reprocess --observation-id ... --mapper-key ...
--mapper-version ... --identity-rule-version ...` to create a preview result. Inspect it before
`promote --normalization-result-id ...`. Reprocessing alone leaves current Evidence unchanged.
The local provenance view is `/imports/<workspace-uuid>/<batch-uuid>`; its workspace-scoped API
returns 404 in production. Import never materializes downstream reasoning.

Downgrade to M1D requires no ingestion batches and no null Account segment. Alembic refuses rather
than deleting imported history or inventing segments. Dispose of an isolated local test database
through an explicit data procedure before downgrading; M0-M1D records remain untouched.
