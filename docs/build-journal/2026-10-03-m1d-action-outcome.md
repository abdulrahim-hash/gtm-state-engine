# Build journal - M1D governed Action proposal and Outcome trace

**Date:** 2026-10-03

**Problem:** Represent a concrete operational intent after the exact M1C Decision and Policy,
then record what followed without executing externally or fabricating commercial results.

**Evidence / context:** The authoritative three-account demo remains Asterwind
ENGAGE/REQUIRE_REVIEW, Bramble ABSTAIN/BLOCK, and Cinderlake ENGAGE/REQUIRE_REVIEW.
No owner, buyer contact, channel, message, provider, or production authentication is available.

**Hypothesis:** A tiny typed Action taxonomy, one terminal review, and deterministic local
validation can demonstrate Decision -> Policy -> governed Action -> operational Outcome while
preserving full provenance and preventing accidental external execution.

**Decision:** Adopt ADR-014. BLOCK and unsupported derivation remain non-Action read projections.
Review is an immutable authority event; lifecycle is projected. The sole Attempt mode is DRY_RUN;
Outcome describes only canonical validation. Production mutation enabling fails configuration
validation, and hosted/public use is read-only.

**Implementation:** Add four schema-only M1D tables, deterministic derivation and workflow
services, narrow read/review/dry-run APIs, strict payload contracts, idempotent synthetic demo seed,
and an account-detail Action/Outcome section. No upstream fixture or evaluator was altered.

**Validation:** 56 API unit tests, 48 PostgreSQL integration tests, and 13 frontend tests pass.
Ruff/Prettier format, Ruff/ESLint lint, mypy/TypeScript type checks, generated-contract drift,
and the production Next.js build pass. Migration 0006 upgraded, downgraded to 0005, then
re-upgraded; exact upstream Evidence, Signal Evaluation, State, Decision, and Policy row
fingerprints stayed unchanged. Two repeated seed runs left exactly 2 Actions, 1 Review, 1
Attempt, and 1 Outcome. The pinned gitleaks working-tree scan reported no leaks.

**Result:** Asterwind requests relationship research under review. Bramble has no Action row.
Cinderlake has a seller-task proposal with visibly synthetic approval and successful local
canonical validation only. The ALLOW route is exercised in isolated tests, not the demo.

**Failure / learning:** Initial full checks found Ruff formatting/import order in the new
integration test and three Prettier formatting differences; mechanical formatting fixed these.
The first secret scan flagged four test-only idempotency-key literals as generic API keys.
Replacing those with shorter deterministic test values preserved replay semantics and made the
same pinned scan pass without a suppression rule. M1D frontend assertions cover non-execution
wording and the BLOCK versus unsupported distinction. No provider simulator was added to make
Outcomes appear more dramatic.

**Next action:** Review M1D validation evidence, then reconcile the next milestone against the
authoritative roadmap. No M2 work is authorized by this journal.
