# ADR-015: Controlled source observations and explicit Evidence promotion

## Context

M1D has a complete synthetic Strategy -> Evidence -> Signal -> State -> Decision -> Policy -> Action -> Outcome trace. M2A must accept external or locally sourced company observations without letting a file, supplier, or operational clock become authority over canonical reasoning. The hosted demo has no production authentication and must remain synthetic.

## Decision

A local CLI imports one exact UTF-8 CSV schema into provider-neutral `source_observations`. Code registers source system `local_csv`, dataset `company_public_events`, source schema `company_public_event/1.0.0`, mapper `public_company_leader_event/1.0.0`, and identity rule `1.0.0`. These are code-owned keys, not database catalog tables or executable configuration. The sole supported fact slot is `commercial_event.new_revenue_leader`; the mapper declares accepted assertions, FACT epistemics, consumed source fields, required source and event times, and output schema version. Missing event time rejects the row. Missing values never imply ABSENT. The file is transport; the observation and normalization contracts are source-neutral.

A batch is identified by workspace, source system, dataset, schema version, and exact file-byte SHA-256. Every row occurrence has a batch and ordinal even when its observation is reused. An observation is identified by scoped external record ID, source observation time, and canonical hash of the exact allowed fields. The same record ID/time with different allowed content is a conflict, never an overwrite or silent second accepted claim. A normalization result is identified by observation plus mapper/version and identity-rule version. Imported Evidence is identified by result plus the single `primary` fact slot. UUIDv5 semantic IDs exclude ingestion and processing clocks; PostgreSQL uniqueness reinforces retries. Accepted, rejected, unresolved, conflict, and duplicate outcomes use bounded enums/reason codes. One transaction commits all accepted and rejected row outcomes, source observations, bindings, Accounts, normalization results, and Evidence. An unexpected mapper or database defect rolls the batch back.

`Account.id` remains canonical identity. External account IDs are immutable bindings scoped to workspace, source system, and dataset, with the establishing source observation recorded. Preflight abstains on conflicting names for a new domain or conflicting domains for one source ID before Account creation; row order does not decide identity. Exact normalized domain plus compatible normalized name may match. A safe existing source-ID binding may match if new claims do not conflict. Domainless observations need an existing safe binding. Name similarity, parent inference, subdomain stripping beyond `www.`, merge, rebind, and Account reassignment are absent. Newly imported Accounts have `segment = null`; Northstar segment values remain fixed. The resolver records its input hash and version in each result.

Only approved parsed fields are stored as `original_fields`; PostgreSQL limits their JSONB textual size to 4 KiB, and the importer limits individual values. No complete file blob, arbitrary column, executable JSON, contact, or secret is retained. Source observation time, semantic event time, `ingested_at`, and `processed_at` remain distinct. Citation HTTPS URLs are syntactically checked and never fetched. The batch carries the file hash. PostgreSQL enforces workspace/source consistency for the first batch and immutable external-ID origin, workspace consistency for normalization and Account, and Account consistency for Evidence. Batch-row observation/result scope, result-to-observation source alignment, and supersession's same-Account rule remain service-enforced and integration-tested because the existing normalized chain does not duplicate their scope columns.

Canonical imported Evidence points to exactly one accepted `normalization_result_id`; legacy synthetic/manual Evidence retains a null pointer and is not rewritten. Origin is Evidence -> result -> observation -> first batch, while batch rows preserve all later occurrences. Reprocessing writes only a new immutable result. Promotion is a separate explicit local command that creates Evidence and appends a supersession edge. A previously unresolved observation may resolve later. An already accepted claim may be promoted only to the same Account. Current-Evidence selection is centralized: legacy Evidence and unsuperseded imported Evidence are eligible for new Signal/State materialization. Old evaluations and snapshots keep their historical Evidence links. Import does not invoke any downstream engine.

M2A inspection is GET-only, explicitly workspace-scoped, and disabled with HTTP 404 in production. The local CLI owns workspace creation, validation, import, reprocess, promotion, and inspection. Public Northstar reads explicitly select its fixed demo workspace; local imported data has a separate workspace and truthful label. Production CLI import/replay/promotion is disabled. No HTTP upload or supplier mutation endpoint exists.

## Consequences

- A committed batch means canonical Evidence is available. It does not mean Signals, State, Decision, Policy, Action, or Outcome are current.
- Reprocessing does not promote. A reviewed local promotion changes eligibility for future materialization without altering historical traces.
- A source ID is provenance, not an Account ID. Conflicting identity remains unresolved.
- The local source's citation and excerpt are bounded claims, not independent verification of the website's truth. A real pilot requires a separate reviewed source-quality procedure and remains outside M2A.
- The schema-only downgrade refuses while any import batch exists or any Account has null segment; it never fabricates a segment or deletes M0-M1D data.
- A later supplier can produce validated source observations through the same contract and register its own code-owned decoder/mapper after review. No live adapter is implemented here.

## Status

Accepted for M2A implementation; no M2B authorization implied.
