# Build journal - M1B.1 deterministic signals

**Date:** 2026-09-30

**Problem:** Derive time-bound commercial events from evidence without treating fit or relationship
context as signals, losing negative results, or duplicating an event whenever it is reevaluated.

**Evidence / context:** M1A preserves provenance but its normalized fact text is not a safe
machine-executable boundary. The approved M1B.1 design requires exact-key FACT inputs, strict demo
time, explicit evaluator versions, relational provenance, and complete evaluation history.

**Hypothesis:** Separating immutable evaluations from stable signal-event identity will make
freshness changes reproducible while keeping the commercial event canonical.

**Decision:** Add paired `fact_key` and `fact_assertion` fields, versioned signal definitions with
explicit evaluator keys, an immutable evaluation ledger, relational evaluation-evidence links, and
canonical signals fingerprinted independently of both clocks. Resolve presentation freshness from
the latest linked evaluation.

**Implementation:** Added migration 0003, a synchronous code-owned evaluator registry, idempotent
recomputation, two synthetic definitions, five typed event-evidence records, four read-only API
routes, committed contracts, and restrained signal/evaluation views on account detail.

**Validation:** Python and frontend formatting/lint/type checks, 17 unit tests, 6 frontend tests,
15 PostgreSQL integration tests, one-step migration downgrade/re-upgrade, deterministic reseeding,
contract drift, production frontend build without a live API, Compose validation, dependency audit,
diff hygiene, and working-tree/history secret scans all passed.

**Result:** The fixed snapshot yields six evaluations and three canonical signal events. Unchanged
recomputation changes no IDs, hashes, execution timestamps, links, or counts. Advancing semantic
time creates new evaluations while reusing all three event identities.

**Failure / learning:** The first integration run accessed ORM instances after rollback and used an
incorrect expected stale count. Persisting the aggregate before rollback and counting the initial
plus later stale evaluations fixed the test; no product or migration behavior changed. An early
frontend validation also exposed an optional generated contract field and a duplicate text query;
both boundaries were corrected and rerun. The optional in-app visual smoke-test runtime could not
initialize its local kernel assets, so visual verification is limited to component tests and the
production build in this environment.

**Next action:** Stop after M1B.1. M1B.2 should derive versioned account-state snapshots from strategy,
fit evidence, relationship evidence, and latest signal evaluations without adding decisions or
policy.
