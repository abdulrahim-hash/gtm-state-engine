# Source of truth

- **PostgreSQL/Supabase:** canonical normalized entities, events, evidence, state snapshots,
  decisions, actions, outcomes, costs, and workflow history when those capabilities exist.
- **HubSpot:** future operational seller-facing adapter, not canonical identity memory.
- **Clay, Apollo, and other providers:** future evidence suppliers only.
- **n8n:** optional future orchestration adapter; irreplaceable business logic remains in code or
  versioned configuration.

M1C implements PostgreSQL-backed strategy, account, evidence, signal, immutable account-state,
Decision, and Policy memory. Decision and Policy attest to exact state snapshots; they do not copy
evidence provenance or authorize actions. Naming future adapters here does not enable or configure
them.
