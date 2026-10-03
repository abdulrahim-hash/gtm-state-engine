# Source of truth

- **PostgreSQL/Supabase:** canonical normalized entities, events, evidence, state snapshots,
  decisions, actions, outcomes, costs, and workflow history when those capabilities exist.
- **HubSpot:** future operational seller-facing adapter, not canonical identity memory.
- **Clay, Apollo, and other providers:** future evidence suppliers only.
- **n8n:** optional future orchestration adapter; irreplaceable business logic remains in code or
  versioned configuration.

M1D implements PostgreSQL-backed strategy, account, evidence, signal, immutable account-state,
Decision, Policy, Action proposal, Review, dry-run Attempt, and operational Outcome memory.
Action attests to the exact M1C chain; Outcome links through Attempt and Action instead of copying
Evidence or Signal provenance. These records do not prove external execution. Naming future
adapters here does not enable or configure them.
## M2A source ownership

The local CSV is transport and is never canonical memory. `source_observations` records a bounded,
immutable claim from registered `local_csv/company_public_events`; a code-owned mapper interprets
it into a normalization result and then canonical Evidence. The external record/account IDs are
source-scoped provenance, never `Account.id`. Exact file and allowed-field hashes make repeated
imports deterministic. Source observation time and semantic event time are distinct from import
processing time.

Only canonical Evidence feeds later GTM reasoning. Import success does not materialize Signal,
State, Decision, Policy, Action, or Outcome. Reprocessing does not promote; a separate explicit
local promotion creates new Evidence and a supersession edge. Historical conclusions keep their
original Evidence references. The public Northstar workspace is pinned and remains synthetic.
