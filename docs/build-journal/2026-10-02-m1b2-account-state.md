# Build journal - M1B.2 deterministic account state

**Date:** 2026-10-02

**Problem:** Derive a reproducible current account description from strategy-relative fit evidence,
same-time signal evaluations, and relationship evidence without collapsing missing, negative,
stale, ambiguous, or contradictory inputs.

**Evidence / context:** M1B.1 already provides exact-key FACT evidence and immutable signal
evaluations. The original fit and Cinderlake relationship fixture rows were intentionally
prose-only, while Asterwind and Bramble contained no explicit relationship-absence evidence.

**Hypothesis:** Four bounded categorical facets plus normalized provenance will make account state
auditable without introducing ranking or downstream authority.

**Decision:** Add strategy fit criteria, immutable state snapshots, normalized reasons, frozen
per-criterion keys/source/expected/observed assertions, direct evidence links, and
signal-evaluation links.
Use demo_as_of for semantic time and a versioned code-owned evaluator registry. Keep relationship
absence explicit: a missing row yields UNKNOWN.

**Fixture normalization:** The deterministic seed definition enriches the three existing fit rows
and Cinderlake's existing-relationship row with fact keys/assertions. IDs, prose, source references,
and their pre-normalization raw-payload hashes remain unchanged. This is fixture normalization only,
not a production evidence-update pattern. No duplicate semantic evidence is created. No synthetic
relationship-absence facts were added for Asterwind or Bramble because their scenarios do not
establish absence.

**Implementation:** PostgreSQL now stores versioned fit criteria and state history. The internal
state pipeline recomputes same-time signals, evaluates the four facets, hashes only relevant inputs,
and reuses identical snapshots. Three GET routes expose current state, history, and immutable
snapshot detail. Account detail presents the four facets and expandable provenance.

**Validation:** Unit, PostgreSQL integration, frontend, contract, migration, build, and hygiene
checks are recorded in the M1B.2 completion report.

**Result:** The demo produces MATCH/ACTIVE/UNKNOWN/PARTIAL for Asterwind,
MATCH/INCONCLUSIVE/UNKNOWN/PARTIAL for Bramble, and
MATCH/ACTIVE/EXISTING_RELATIONSHIP/PARTIAL for Cinderlake.

**Failure / learning:** Initial integration assertions accessed ORM rows after an intentional
rollback; capturing scalar values before rollback corrected the test harness. Initial frontend
validation found formatting drift and one expected text count changed by the added provenance view.
Neither issue changed product semantics.

**Next action:** Stop at descriptive account state. Plan the later M1C boundary separately; do not
add downstream authority to M1B.2.
