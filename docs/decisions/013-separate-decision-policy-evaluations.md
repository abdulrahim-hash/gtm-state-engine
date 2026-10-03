# ADR-013: Decision desirability and Policy authority remain separate evaluations

## Context

M1B.2 produces immutable descriptive account-state snapshots. The next layer must determine whether
engagement merits consideration and independently constrain whether that proposal may advance. If
those questions are collapsed, commercial relevance can be mistaken for execution authority and
relationship uncertainty can be silently erased.

## Decision

Store Decision and Policy as separate immutable, versioned evaluations. Both attest to one exact
`state_snapshot_id`; Policy also references the exact Decision evaluation. Code-owned registries,
canonical SHA-256 inputs, and UUIDv5 identities make results reproducible.

The internal Decision result `ENGAGE` means **engagement merits consideration**. It is never a send,
campaign, task, CRM write, play selection, or external-action command. Policy returns `ALLOW`,
`REQUIRE_REVIEW`, or `BLOCK`, where even `ALLOW` permits only progression to a future planning
boundary. Every M1C disposition remains `PROPOSED_ONLY` with
`external_action_authorized = false`.

PostgreSQL partial unique indexes enforce at most one enabled definition in each intended scope.
The materialization service requires exactly one and fails closed when none exists or when the
selected evaluator key/version is unsupported. No fallback is permitted.

Decision consumes only the immutable state snapshot. Policy consumes the Decision and the exact
same snapshot. Neither layer reads evidence or signals directly, recomputes state, or duplicates
M1B.2 evidence provenance.

## Consequences

- Cinderlake can be commercially relevant while still requiring controlled relationship handling.
- Asterwind's unknown relationship cannot be treated as relationship absence.
- Bramble can abstain because timing is inconclusive even though fit matches.
- Relationship-only state revisions create new Decision identities even when the Decision enum is
  unchanged, preserving complete-snapshot attestation.
- Read APIs expose stored evaluations only and never materialize on GET.
- Future action or review milestones must reference these evaluations without redefining them as
  execution authority.

## Status

Accepted

