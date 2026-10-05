# 2026-10-05 — M2C controlled CRM relationship read

## Problem and evidence

M2B proved the public source-to-governed-proposal chain but left Relationship `UNKNOWN` for all 20 real accounts. Public silence cannot establish a missing relationship. M2A's `SourceObservation` required a CSV batch and public citation, neither of which truthfully describes a private CRM read. The next vertical slice needed one company-level, provider-neutral operational assertion and no write boundary crossing.

## Hypothesis

An operator-triggered read of one synthetic Company in a HubSpot developer-test portal, normalized to a dated positive CRM-reported Customer fact, can change the existing Relationship State and governed Action proposal while Decision and Policy rules remain unchanged. A non-Customer stage must leave Relationship `UNKNOWN`.

## Decision and implementation

See ADR 018. Added a small source-read run and alternative private provenance origin; one bounded HubSpot GET adapter; a versioned `relationship.crm_reports_customer_status` mapper; an isolated M2C synthetic test workspace and `1.2.0` Relationship evaluator with a 24-hour inclusive observation window. Added explicit local CLI stages, inspection gate, local-only API and UI trace, generated API contracts, and regression tests. The existing CSV parser, Northstar and M2B semantics, Decision, Policy, and Action rules were not changed.

The test portal was verified as `DEVELOPER_TEST` with a matching configured portal ID before Company reads. Two synthetic Company records used names/domains matching the local fixture. The configured exact Customer value was `customer`, mapping version `1.0.0`. Only `id`, `name`, `domain`, `lifecyclestage`, and optional `updatedAt` were read; unknown provider fields were discarded. The token stayed in ignored `.env.m2c.local` and was never persisted or logged.

## Local live-read validation

Synthetic fixture time: `2026-10-04T21:36:00Z`. Fixed semantic `state_as_of`: `2026-10-04T21:37:20Z`.

- Customer Company read: `SUCCEEDED`, one accepted `FACT/PRESENT` `relationship.crm_reports_customer_status`; source run `4fc93c7a-e293-439b-b9ee-879e2c34515c`.
- Non-Customer Company read: `SUCCEEDED`, one accepted `FACT/INCONCLUSIVE`; source run `51fbeb39-ec41-402c-8171-3e642362ee9c`.
- Each read reported `downstream_materialized_by_read=false`. The operator then ran Signals, State, Decisions, Policies, and Actions separately at the fixed semantic time.
- Both synthetic leader Signals were `DETECTED`; both Fit facets were narrow fixture `MATCH`; both Decisions `ENGAGE`; both Policies `REQUIRE_REVIEW`. The Customer Account's Relationship became `EXISTING_RELATIONSHIP` and its internal proposal `CREATE_SELLER_TASK`, with Policy reason `EXISTING_RELATIONSHIP_REQUIRES_CONTROLLED_HANDLING`. The non-Customer Account's Relationship remained `UNKNOWN` and its internal proposal `REQUEST_RESEARCH`, with Policy reasons `RELATIONSHIP_UNKNOWN_REQUIRES_REVIEW` and `PARTIAL_EVIDENCE_REQUIRES_REVIEW`.
- A complete second materialization reused two identities at every stage and created zero. State's internal Signal recomputation matched the explicit Signal identities, input hashes, and results.
- No `ABSENT`, `NO_EXISTING_RELATIONSHIP`, `ALLOW`, CRM write, external seller task, outreach, `ActionOutcome`, or commercial outcome was created.

## Validation and learning

The first full integration run used a local database already containing the live M2C rows and failed old global-row-count assertions. A separate empty local regression database was created and migrated from M0 through M2C. On that clean database the M0–M2C regression passed. The additive migration downgraded and re-upgraded there with no source-read rows. Legacy test expectations for registry size and migration head were advanced only to reflect the additive M2C version. Four pre-existing mypy typing errors were corrected without changing runtime behavior.

The first frontend pass caught a label mismatch between the page and test; the page now explicitly says no **external** seller task occurred, distinguishing an internal `CREATE_SELLER_TASK` proposal from provider execution. Final check counts appear in the completion report.

## Limitations and next action

The test has one portal, two synthetic Companies, one relationship fact, and no scheduled refresh. HubSpot lifecycle stage remains a CRM-reported assertion and may not mirror contract truth. The 24-hour rule expires the positive state without a fresh observation; it does not infer a negative. The local web view requires an explicit `as_of` query. Keep the M2B public case study separate. M2D/external writes require a separate architecture review and authorization.
