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

## Services

```powershell
uv run --project apps/api uvicorn gtm_state_api.main:app --app-dir apps/api/src --reload
npm run web:dev
```

Run those commands in separate terminals.

The frontend proxies read-only `/api/*` requests to `API_BASE_URL` (default
`http://localhost:8000`). Keep this server-side setting in `.env`; it is not a public credential.

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
npm run web:build
```

Integration tests require migrated PostgreSQL. Unit and failure-path tests do not.

## Troubleshooting

- If `uv` cannot use its user cache, set `UV_CACHE_DIR` to a writable workspace-local directory.
- If port 5432 is occupied, stop the conflicting local PostgreSQL service before starting Compose.
- If contract drift fails, regenerate contracts and inspect both committed artifacts before
  accepting the change.
