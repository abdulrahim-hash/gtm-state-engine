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
