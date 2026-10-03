# ADR-014: Governed canonical Action proposals and local operational Outcomes

## Context

M1C separates commercial Decision from Policy authority and preserves the exact immutable
Account State chain. M1D must represent a concrete GTM operational intent and record what happened
after local validation without interpreting upstream evidence again or implying provider execution.
The public demo has no authentication, seller owner, contact, message, or external adapter.

## Decision

An Action is an immutable, vendor-neutral **proposal of business intent**. M1D supports only
`REQUEST_RESEARCH` and `CREATE_SELLER_TASK`, each with a strict versioned, bounded payload. The
deriver consumes only the exact PolicyEvaluation, its DecisionEvaluation, definition/version
metadata, Policy target, and ordered Policy reason codes. It does not inspect Evidence, Signals,
Account State facets, CRM-like records, or company identity. BLOCK creates no Action. Unsupported
conclusions project `NO_SUPPORTED_ACTION`; BLOCK projects `BLOCKED_BY_POLICY`. Neither projection
is an Action row.

The canonical Action hash attests to the exact Policy and upstream Decision/snapshot identities,
versions, ordered reasons, action type, and payload. Canonical JSON is SHA-256 hashed; UUIDv5
derives the Action ID. Operational timestamps do not affect identity. PostgreSQL uniqueness protects
against retries and concurrency. A new PolicyEvaluation identity therefore creates a new Action
identity, even if the disposition and payload are unchanged.

Action lifecycle is a read projection, not a mutable status:
`REVIEW_REQUIRED`, `READY_FOR_DRY_RUN`, or `REJECTED`. A REQUIRE_REVIEW Action needs one
immutable terminal Review before dry-run. Approval authorizes **local validation only**; rejection
prevents advancement. ALLOW needs no Review but still cannot authorize external execution.

M1D's only Attempt mode is `DRY_RUN`. It validates the stored Action's typed payload, deterministic
hash/ID/derivation, exact M1C chain, and review authority without invoking a provider. Its sole
Outcome vocabulary is `SUCCEEDED / CANONICAL_ACTION_VALIDATED` or
`FAILED / CANONICAL_ACTION_INVALID`. An integrity defect creates a failed Attempt/Outcome.
Ordinary client or lifecycle misuse (invalid command, missing approval, rejected proposal) returns
an API error without an Attempt. Outcome and Attempt identities are deterministic, and retries
replay the existing immutable trace.

The client cannot assert reviewer/requester identity. Local mutation routes stamp
`UNVERIFIED_DEMO_HUMAN` with server-controlled non-identity references. Cinderlake's seeded
approval and dry-run stamp `SYNTHETIC_FIXTURE` with fixed fixture references and idempotency
identity. Review keys have a bounded format, are never logged raw, and only their hashes are stored.
One terminal Review per Action is enforced by service and database uniqueness.

`ACTION_MUTATIONS_ENABLED` defaults false. Enabling it in `APP_ENV=production` fails startup
settings validation. Only controlled local use and tests may invoke the narrow review and dry-run
mutation routes. No request parameter or header overrides this gate. All M1D Action/read
projections declare `external_execution_authorized=false`.

The immutable normalized chain is Outcome -> Attempt -> Action -> Policy -> Decision -> State ->
existing provenance, with Review as an orthogonal authority event. No duplicate Action-to-Evidence
or Outcome-to-Signal links are stored.

## Consequences

- Asterwind has a review-required relationship-research proposal, not outreach.
- Bramble has a read-only BLOCK projection and no Action.
- Cinderlake has a controlled seller-task **proposal**, synthetic fixture approval, and successful
  local validation; no actual seller task, owner, CRM update, message, or external request exists.
- An isolated ALLOW fixture is test-only and progresses only to dry-run readiness.
- Historical Actions, Reviews, Attempts, and Outcomes remain immutable; later provider execution
  needs a separately reviewed authority model and schema.
- The public hosted demo remains read-only, and production authentication is not implied.

## Status

Accepted for M1D
