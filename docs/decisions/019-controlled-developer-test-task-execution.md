# ADR-019: Controlled developer-test Task execution

Status: accepted for M5A; live validation pending

Date: 2026-10-06

## Context

M1D has canonical Action proposals, Reviews, dry-run Attempts, and local validation Outcomes. Its `action_attempts` and `action_outcomes` explicitly have no external side effects. M2C supplies a portal-scoped, read-only Customer relationship fact for two synthetic Companies. M5A tests whether one reviewed `CREATE_SELLER_TASK` can cross a provider write boundary without confusing proposal approval, delivery, provider acceptance, read-back, or commercial impact.

## Decision

Keep M1D and M2C tables and meanings intact. Add separate `execution_plans`, `execution_authorizations`, `execution_attempts`, append-only attempt events, bounded provider receipts, reconciliations, and operational outcomes. A plan freezes the canonical chain and a typed HubSpot Task projection, including portal scope, synthetic Company, synthetic owner, association type, adapter version, fields, and opaque marker. The local operator authorizes the exact plan under `LOCAL_OPERATOR_ATTESTATION`; a demo Review alone cannot authorize a POST.

The only writer is an explicit local CLI command. Production config rejects M5A write enablement. The CLI verifies the developer-test portal, exact synthetic Company and Customer stage, one active allowlisted test owner, the unlabelled Task-to-Company association type, current chain and relationship freshness, plan hash, live authorization, and unused durable intent before claiming dispatch. It commits `IN_FLIGHT` with the single POST budget reserved, then issues at most one Task create call. There is no POST retry. Ambiguous network/provider results remain `UNKNOWN_DELIVERY`; read-only reconciliation may recover an exact Task by provider ID or bounded marker scan. A provider Task ID is a receipt, not proof of the planned Task. Only exact read-back of fields, owner, marker, archived state, and Company association can produce `CRM_TASK_CONFIRMED_CREATED`.

The operational outcome says that the synthetic Task was observed in the developer-test portal at reconciliation time. It does not say the Task was completed, a seller engaged, a prospect replied, or revenue was generated. The local inspection API/UI remains read-only and is unavailable in production.

## Safety and tradeoffs

- PostgreSQL is the durable intent and audit memory. No queue or worker is needed for this one operator-run write.
- One attempt is allowed per canonical Action; one physical POST budget per attempt. A plan may be superseded before intent, but cannot create a second attempted write for the same Action.
- A crash after `IN_FLIGHT` is conservatively treated as possible delivery. Even if transport had not started, M5A does not automatically release the POST budget.
- HubSpot's marker is for reconciliation and is not a provider idempotency guarantee.
- A `400` is treated as no-write only when HubSpot explicitly returns `VALIDATION_ERROR`; `401` and `403` are no-write rejections. Timeouts, resets, `429`, ambiguous `5xx`, malformed success, and death before receipt persistence require read-only reconciliation.
- Portal-specific Task scopes and ownership must be checked in HubSpot before the one live write. A short-lived ignored local scope proof binds the operator's exact granted-scope inspection to the credential fingerprint, portal, and owner. This remains local operator attestation, not enterprise authentication or token introspection.
- This milestone does not improve Timing coverage or prove recommendation quality.

## Consequences

M5A has a truthful provider operational outcome and can later support seller/GTM outcome ingestion. M5A does not implement that ingestion, measurement, attribution, production writes, remote write APIs, additional Action types, additional providers, or M5B.
