# Build journal — M1A strategy and evidence foundation

**Date:** 2026-09-29

**Problem:** Start the first GTM trace without prematurely deriving signals, scores, states, or actions.

**Evidence / context:** M1A requires a versioned synthetic strategy, canonical account identity,
provenance, fixed demo-time semantics, and a minimal workspace boundary.

**Hypothesis:** Explicit epistemic labels and evidence-first relationship modeling make future derived
logic auditable without implying that a current recommendation exists.

**Decision:** Add workspace, strategy version, account, and evidence tables. Scope strategy/account
identity to workspace; allow one active strategy per workspace; seed only Northstar Revenue Systems Demo
at `2026-09-15T12:00:00Z`. Store Account C's existing relationship as evidence, not an account flag.

**Implementation:** Added a reviewed PostgreSQL migration, deterministic idempotent seed, read-only API,
committed OpenAPI/TypeScript contracts, and restrained Strategy/Accounts/Account Detail provenance UI.

**Validation:** Formatting, linting, Python and TypeScript type checks, API unit tests, frontend
view tests, PostgreSQL downgrade/upgrade, idempotent seed, database constraints, read-only API tests,
contract drift, production build, dependency audit, Compose configuration, CI YAML parsing, and secret
detection were run locally.

**Result:** All available local M1A gates passed. The GitHub workflow mirrors those blocking gates but
has not yet run on GitHub.

**What failed:** The first local migration attempt attempted to create each PostgreSQL enum twice.
The transaction rolled back; setting the migration's table enum declarations to `create_type=False`
after explicit enum creation fixed the issue. The downgrade/re-upgrade suite then passed.

**Next action:** Stop at M1A after validation. M1B may add deterministic signal detection only.
