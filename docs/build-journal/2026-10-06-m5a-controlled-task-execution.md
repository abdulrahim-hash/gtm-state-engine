# 2026-10-06 — M5A controlled developer-test Task execution

## Problem and context

M1D proves reviewed proposals and dry-run local Outcomes; M2C proves read-only CRM relationship input. Neither proves a bounded external write. The accepted M5A gate calls for one synthetic Customer-test `CREATE_SELLER_TASK` to become one verified Task in the HubSpot developer-test portal, without reinterpreting M1D records.

## Hypothesis and decision

A separate PostgreSQL execution ledger, exact immutable provider plan, one-use local operator authorization, and conservative single-POST reservation can cross the Task write boundary safely. HubSpot acceptance remains distinct from read-back confirmation and commercial impact. ADR-019 records the boundary and tradeoffs.

## Implementation

Added an additive seven-table execution ledger with plan and audit immutability, authority binding, one attempt per Action, one POST reservation per attempt, bounded receipt, reconciliation, and operational outcome. Added a narrow 2026-09 HubSpot Task adapter, local CLI, local-only read API, and read-only trace page. M1D `action_attempts`/`action_outcomes` and M2C read semantics were left intact. The Task fields are a fixed synthetic subject/body, due timestamp, `NOT_STARTED`, one configured synthetic owner, one exact Company association, and a deterministic opaque marker.

## Validation and learning

Local tests exercise adapter success and failures, chain freshness, plan hash, authority, durable intent, a real two-connection PostgreSQL dispatch race, uncertainty, immutable plan, scope-proof binding, and exact read-back. An injected receipt-persistence failure after a simulated provider Task ID recovers through read-only reconciliation without a second POST. Migration up/down/up was exercised on an empty M5A schema. A clean isolated PostgreSQL run passed 207 backend tests; 22 frontend tests, lint, types, build, and generated-contract drift checks passed. A later focused integration rerun was interrupted when the local PostgreSQL container lost its published port and Docker reported an image storage I/O error; the 123 database-independent backend tests still passed. The container was subsequently reported stopped, so the failed rerun's temporary race database could not be inspected or cleaned yet. A read-only live M2C probe verified the configured portal is `DEVELOPER_TEST`, and the exact synthetic Customer Company still reports Customer. The probe created no observation and no external effect. No real HubSpot POST has been made. The M5A write credential and synthetic owner are not configured; granted Task scopes and association behavior therefore remain unverified. These are explicit M5A exit blockers, not reasons to relax the gates.

## Next action

Identify exactly one synthetic test owner in the verified developer-test portal, inspect the token's exact Task/Company/owner grants, verify Task-to-Company association behavior through read-only probes, refresh M2C Customer Evidence and materialize a fresh chain, then conduct one operator-run live POST and read-back. Do not start M5B or richer Timing work in this milestone.
