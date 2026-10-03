# Build journal - M1C deterministic Decision and Policy

**Date:** 2026-10-03

**Problem:** Given one immutable descriptive account-state snapshot, determine whether engagement
merits consideration and independently determine whether the proposal may advance, without
creating an action or weakening M1B.2 provenance.

**Evidence / context:** M1B.2 already preserves Fit, Timing, Relationship, and Evidence Sufficiency
with exact evidence and signal-evaluation traces. Asterwind and Bramble intentionally have UNKNOWN
relationship state. Cinderlake intentionally has EXISTING_RELATIONSHIP. All three have PARTIAL
evidence sufficiency.

**Hypothesis:** Separate categorical Decision and Policy ledgers can expose commercial relevance
and safety constraints without scores, model authority, or action execution.

**Decision:** Add versioned database definitions that select code-owned evaluator versions,
immutable Decision and Policy evaluations, normalized ordered reasons, UUIDv5 identities from
canonical hashes, exact snapshot provenance, GET-only APIs, and a composed non-executing read
model. `ENGAGE` is presented as “Engagement merits consideration.”

**Implementation:** The Decision evaluator consumes one explicit state snapshot. Policy consumes
that Decision and the same snapshot. Definition selection requires exactly one enabled definition,
while PostgreSQL enforces at most one. Policy reasons are ordered as BLOCK constraints, then
REQUIRE_REVIEW constraints, with ALLOW support reasons emitted only for ALLOW. Demo seed
materialization uses production services after state recomputation and does not hand-author
outcomes.

**Validation:** 49 non-integration API tests, 38 PostgreSQL integration tests, and 9 frontend tests
pass. Ruff format/lint, strict mypy, ESLint, Prettier, TypeScript, contract drift, the production
Next.js build, upgrade/downgrade/re-upgrade, repeated seed, `git diff --check`, and the pinned
gitleaks scan pass.

**Result:** Asterwind is ENGAGE/REQUIRE_REVIEW, Bramble is ABSTAIN/BLOCK, and Cinderlake is
ENGAGE/REQUIRE_REVIEW. All dispositions are PROPOSED_ONLY and cannot authorize external action.

**Failure / learning:** The first frontend run had three failed assertions because the tests
expected the human-facing response label twice while the component intentionally renders it once
and keeps the raw enum only in explanatory provenance copy. Correcting the assertion cardinality
produced the intended nine-test pass without changing product behavior. A subsequent integration
run exposed that the first relationship-only identity fixture added relationship evidence through
M1B.2, which also moved evidence sufficiency from PARTIAL to SUFFICIENT and correctly yielded
ALLOW. The fixture now creates an isolated second immutable snapshot whose sole categorical change
is relationship state, preserving PARTIAL sufficiency and the intended REQUIRE_REVIEW assertion.
A final requirements audit found that an explicit definition-ID test hook could bypass enabled
definition selection. Removing that hook made every materialization require the sole enabled
definition; version-change tests now promote the new definition explicitly. These failures and the
corrective changes are preserved here rather than omitted.

**Next action:** Review the next milestone against the existing roadmap. Do not begin M1D or add
actions, approvals, outcomes, providers, or models as part of M1C.
