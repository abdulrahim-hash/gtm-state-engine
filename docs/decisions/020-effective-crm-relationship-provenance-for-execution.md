# ADR-020: Resolve effective CRM Relationship Evidence from snapshot history

Status: accepted for M5A validation; live plan retry pending

Date: 2026-10-11

## Context

M2C state engine 1.2.0 evaluates the latest CRM-reported Customer observation but keeps every relevant relationship Evidence row in `StateSnapshotEvidence`. A valid synthetic Customer snapshot therefore links both an expired historical `PRESENT` row and a fresh `PRESENT` row. M5A required exactly one relationship link and stopped with `RELATIONSHIP_TRACE_AMBIGUOUS` before creating a plan.

## Decision

M5A selects the unique latest `relationship.crm_reports_customer_status` Evidence linked to the exact snapshot and Action Account. Historical links remain intact. The selected row must be `FACT/PRESENT`, have the CRM evaluator's expected freshness marker and a normalization result, and be within the inclusive 24-hour window at both snapshot time and execution validation time. M5A continues to reject any other canonical relationship Evidence for the Account with an equal or later observation time, and continues to verify the selected Evidence's normalization, source observation, successful read run, configured synthetic Company, and developer-test portal scope.

The read-only M5A execution trace reports this selected Evidence rather than whichever relationship link the database returns first. M2C evaluation and provenance storage do not change. No migration or provider behavior changes.

## Consequences

An expired historical relationship observation no longer blocks an otherwise valid current chain. A latest tie, non-positive or invalid latest row, stale row, superseding canonical row, missing source provenance, or mismatched provider scope still blocks execution. The M5A plan remains bound to the State snapshot ID rather than storing a separate effective Evidence ID; validation repeats the selection at plan and execution gates.
