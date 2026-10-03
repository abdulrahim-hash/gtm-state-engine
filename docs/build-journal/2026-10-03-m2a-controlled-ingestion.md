# Build journal - M2A controlled local Evidence ingestion

**Date:** 2026-10-03

**Problem:** M1D proves the complete synthetic GTM reasoning chain, but external account/evidence observations need a safe entry boundary with identity abstention, reproducible normalization, and inspectable provenance.

**Evidence / context:** The accepted M2A review permits a local CSV producer, immutable source observations, conservative Account resolution, versioned normalization, and canonical Evidence. Northstar must remain synthetic and stable. No downstream recomputation or provider integration is authorized.

**Hypothesis:** An exact bounded source schema, batch occurrence ledger, scoped source identity, deterministic mapper, and explicit replay/promotion will make source claims inspectable without weakening the M1 reasoning or authority model.

**Decision:** Adopt ADR-015. Import stops at Evidence. Preflight abstains on ambiguous identity. Local CLI owns mutation, while read APIs are workspace-scoped and production-disabled. Reprocessing and promotion are separate commands.

**Implementation:** Schema-only revision 0007 adds six ingestion/provenance tables, a nullable Evidence result pointer, and nullable Account segment. Code adds CSV validation, source-observation and mapper contracts, atomic import, replay/promotion, centralized current-Evidence selection, local inspection API/UI, and explicit Northstar public scoping. A typed contract and test suite cover the boundary.

**Validation:** Final sequential checks passed: Ruff/Prettier format, Ruff/ESLint lint,
Python mypy and TypeScript type checks, 79 API unit tests, 63 PostgreSQL integration tests,
15 frontend tests, generated-contract drift, and the production Next.js build. The integration
suite includes the complete 48-test M0-M1D PostgreSQL regression and 15 new M2A tests. The
schema cycled 0006 -> 0007 -> 0006 -> 0007; all 24 pre-M2A tables and 103 rows retained the
same SHA-256 fingerprint `016a95b82eac37191fa1d655b93f93761489d6d9d167aa157e92e909e54e5055`.
Two repeated Northstar seeds left the same row count and fingerprint. The pinned gitleaks
working-tree scan found no leaks. No pilot data or fixture was committed.

**Result:** Local input can become traceable canonical Evidence while the hosted synthetic trace remains separate.

**Failure / learning:** Early integration assertions accidentally counted seeded Northstar data; they were scoped to the test workspace. An early frontend mock needed Vitest hoisting. The final schema strengthens source-scoped foreign keys and caps parsed JSONB storage.

**Next action:** Review the M2A validation report before considering a separate M2B pilot milestone.
