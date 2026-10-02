# ADR-012: Versioned descriptive account-state snapshots

## Context

M1B.1 preserves canonical evidence, deterministic signal evaluations, and stable commercial-event
identity. The next layer must describe what the system currently believes about an account without
introducing ranking or downstream execution semantics.

Late-arriving relevant evidence may change what is known while the business time represented by the
snapshot remains unchanged. Fit must remain relative to an explicit synthetic strategy hypothesis,
and missing relationship evidence must not be interpreted as evidence of no relationship.

## Decision

Persist immutable account_state_snapshots with four non-numeric facets: Fit Context, Timing State,
Relationship State, and Evidence Sufficiency. state_as_of is semantic time; computed_at is
operational materialization time and never participates in facet evaluation or snapshot identity.

Use code-owned, versioned evaluators. Derive a canonical SHA-256 input hash from state-relevant
criteria, evidence, enabled signal definitions, same-time signal evaluations, and the evaluator
manifest. Derive the snapshot UUID from that hash. Unchanged inputs reuse the existing snapshot.

Preserve normalized provenance through snapshot reasons, direct evidence links, signal-evaluation
links, and a frozen snapshot-to-fit-criterion interpretation. The snapshot link freezes the
criterion stable key, input fact key, source strategy-evidence ID, expected assertion, observed
assertion, and criterion result. Historical fit therefore remains exactly inspectable without
reconstructing executable semantics from mutable prose.

NO_EXISTING_RELATIONSHIP requires explicit current FACT evidence with an ABSENT assertion.
Missing relationship evidence produces UNKNOWN.

The current-state read returns the latest materialized snapshot for the applicable semantic
state_as_of. Operational ordering selects among same-time knowledge revisions but does not change
GTM semantic time. Every revision remains addressable by immutable snapshot ID.

## Consequences

- Fit is inspectable and explicitly relative to an unvalidated synthetic hypothesis.
- A detected current event can establish ACTIVE timing while incomplete coverage yields
  PARTIAL Evidence Sufficiency.
- Relevant older evidence is part of the provenance set and therefore creates a new snapshot even
  when the latest facet result is unchanged.
- Unrelated evidence and operational timestamps do not change snapshot identity.
- GET endpoints remain side-effect free; materialization occurs only in internal deterministic
  application logic.
- Relationship context remains descriptive and has no blocking behavior.

## Status

Accepted
