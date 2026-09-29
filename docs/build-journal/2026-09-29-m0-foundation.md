# Build journal — M0 foundation

**Date:** 2026-09-29

**Problem:** Establish a production-style foundation without prematurely implementing GTM domain
logic or vendor integrations.

**Evidence / context:** The canonical brief requires Next.js, FastAPI, PostgreSQL/Supabase
compatibility, typed contracts, migrations, CI, a demo banner, and auditable architecture.

**Hypothesis:** A small synchronous service boundary, deterministic contract pipeline, empty
migration baseline, and honest visual shell provide enough structure for a safe M1 vertical slice.

**Decision:** Use Next.js 16, FastAPI/Pydantic, SQLAlchemy 2.x with synchronous psycopg 3, Alembic,
PostgreSQL, npm workspaces, and uv. Keep M0 free of domain tables and provider adapters.

**Implementation:** Added the web/API/contract workspaces, local database configuration,
documentation, concise ADRs, quality gates, and synthetic-data safety language.

**Validation:** Fresh dependency installs from `package-lock.json` and `uv.lock`, formatting,
linting, Python type checking, unit tests, PostgreSQL integration tests, Alembic
downgrade/upgrade validation, contract-drift checks, a production frontend build, Docker Compose
configuration, `npm audit`, and a Gitleaks working-tree scan were run locally.

**Result:** All available local M0 gates passed. The CI workflow mirrors the required blocking
gates; it has been syntax-validated locally but has not yet run on GitHub.

**What failed:** The initial sandbox shell could not start and the default patch helper could not
write to the workspace. The approved workspace shell and patch executable were used without
changing scope. TypeScript 7 conflicted with `openapi-typescript`, so the shared compiler pin moved
to 5.9. ESLint 10 satisfied Next.js's declared peer range but failed inside its React plugin, so the
latest ESLint 9 patch remains pinned until that upstream plugin is compatible.

**What changed:** The repository moved from canonical briefs only to the M0 engineering foundation.

**Next action:** Begin the approved M1 account-state vertical slice only after this foundation is
reviewed.

**Related issue/ADR/commit:** ADR-001 through ADR-010; commit plan to be proposed after validation.
