# 2026-10-11 — M5A/M2C relationship provenance contract

## Problem and evidence

The live synthetic M2C Customer snapshot at `2026-10-07T18:28:00Z` preserves an expired October 4 CRM `PRESENT` relationship observation and a fresh October 7 `PRESENT` observation. M2C state engine 1.2.0 evaluates only the latest observation while preserving both Evidence links. M5A assumed one relationship link and correctly stopped with `RELATIONSHIP_TRACE_AMBIGUOUS`. No execution plan or provider write resulted from that attempt.

## Hypothesis and decision

Selecting the unique latest linked CRM relationship Evidence, then applying the existing M5A chain, freshness, source, portal, Company, and supersession guards, should accept this provenance shape without changing the M2C state conclusion. ADR-020 records the contract.

## Implementation

Added one M5A helper to select the unique latest CRM relationship Evidence linked to the exact State snapshot and Action Account. The plan gate verifies `FACT/PRESENT`, the expected freshness marker, normalization provenance, the 24-hour windows, and no equal or newer canonical competitor. The M5A execution trace uses the same selection. M2C snapshot materialization and historical links are unchanged.

## Validation and result

All 14 M5A PostgreSQL integration tests passed, including historical plus fresh Evidence, a newer inconclusive linked row, equal-time latest links, an equal-time canonical competitor outside the snapshot, expiry at execution, superseding Evidence, and the existing single-evidence chain. Full API unit tests passed (123). A first full integration run against the history-bearing local database reported 15 failures in older tests that assume database-wide counts start empty; 73 integration tests passed. A fresh disposable PostgreSQL database was created and migrated; all 89 integration tests passed there, including unchanged M2C tests. API format, lint, and strict type checks passed; generated-contract drift and `git diff --check` passed. The API source distribution and wheel built successfully. A read-only count for the existing live synthetic Action confirmed zero M5A plans, attempts, receipts, and operational outcomes.

The first full integration run invoked the idempotent demo seeder against the history-bearing local database. No full before/after table fingerprint was captured. A read-only recheck confirmed that the specified M2C snapshot still has both relationship links and the expected latest observation; subsequent full integration runs used only the fresh disposable database.

## Learning and next action

Historical State provenance is a set of observations, not an instruction to execute against every row. Keep M5A fail-closed selection explicit. The existing October 7 observation is outside its 24-hour execution window on October 11; refresh the synthetic CRM read, materialize the new M2C chain, and review its new Action before retrying `m5a_task.py plan`. The plan step is separate from authorization, intent, and dispatch.
