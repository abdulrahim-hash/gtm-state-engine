# ADR 018: Controlled CRM Relationship Read

Status: Accepted for M2C implementation (2026-10-05)

## Context

M2A's public CSV `SourceObservation` requires a batch and public citation. A private CRM record has neither. M2B left every real pilot Relationship `UNKNOWN`, correctly preventing inference of a missing relationship from public silence. M2C needs one factual company-level CRM observation without moving canonical identity or policy into HubSpot.

## Decision

Add one additive `source_read_runs` origin and permit exactly one of `first_batch_id` or `source_read_run_id` on `source_observations`. Preserve M2A's CSV parser, citation validation, file hash, and batch contract. A read run records adapter/version, source scope hash, bounded request/response hashes, operational times, status, counts, retries, failure code, and optional provider correlation. It is a source-acquisition result, never an `ActionOutcome`.

The HubSpot adapter can only GET one allowlisted Company ID and the account-info endpoint used to verify a `DEVELOPER_TEST` portal. Company properties requested: `name`, `domain`, `lifecyclestage`; `id` and `updatedAt` are response metadata. Unknown response fields are discarded. No full response, credential, contacts, owners, associations, activities, or deals are persisted. Redirects are disallowed. The operator supplies the token and portal ID through the ignored `.env.m2c.local`; there is no credential API.

The provider-neutral canonical fact is `relationship.crm_reports_customer_status` (mapper `crm_customer_stage@1.0.0`). The configured exact Customer-stage value and mapping version are in the semantic observation/hash. A matching stage yields `FACT/PRESENT`; another or empty stage yields `FACT/INCONCLUSIVE`; no M2C path yields `ABSENT`. `CRM-reported Customer` is an operational assertion and does not prove an active contract, revenue, subscription, opportunity, or seller activity.

State engine `1.2.0` uses `crm_reported_customer_observation_window@1.0.0`. At an explicit `state_as_of`, only a single latest positive observation no older than **24 inclusive hours** yields `EXISTING_RELATIONSHIP`. Missing, later non-Customer, conflicting, future, or expired evidence yields `UNKNOWN`. This version leaves Northstar's `1.0.0` and M2B's `1.1.0` evaluators unchanged. No `NO_EXISTING_RELATIONSHIP` can result from this CRM fact.

Provider ID is scoped to workspace + source system + portal hash. An immutable provider binding or exact normalized domain plus compatible normalized name can resolve an Account. Missing domain cannot create a new Account. In this two-Company synthetic test workspace, unlisted domains cannot create new Accounts either. Conflicts and duplicate source IDs to one Account remain unresolved; no fuzzy match, parent-domain inference, merge, or rebind occurs.

The local CLI enforces an explicit boundary: setup, read, inspect, then individually materialize Signals, State, Decision, Policy, and Action proposal. Each stage requires all effective observations to have been inspected. State reuses the exact Signal evaluations. A source read does not trigger downstream materialization. Existing Decision, Policy, and Action rules remain authoritative; `CREATE_SELLER_TASK` is only an internal proposal.

## Failure and security consequences

401/403 fail without retry. 404 is `NOT_FOUND`, never absence Evidence. 429/5xx retry at most twice on each approved GET. Timeouts, malformed/paginated responses, missing fields, and portal mismatch fail closed. Same provider ID/time with changed bounded content records `CONFLICT` and blocks materialization; exact replay reuses semantic observation and Evidence. A later observation time creates history. Production private API routes return 404; the local web page is unavailable in a production Next build. The migration refuses downgrade while any source read run exists, preserving private provenance.

No provider write method, webhook, scheduler, contact read, external execution, or commercial outcome exists in M2C. The developer-test portal and synthetic companies are the only permitted live-read target.
