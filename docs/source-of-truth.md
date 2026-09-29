# Source of truth

- **PostgreSQL/Supabase:** canonical normalized entities, events, evidence, state snapshots,
  decisions, actions, outcomes, costs, and workflow history when those capabilities exist.
- **HubSpot:** future operational seller-facing adapter, not canonical identity memory.
- **Clay, Apollo, and other providers:** future evidence suppliers only.
- **n8n:** optional future orchestration adapter; irreplaceable business logic remains in code or
  versioned configuration.

M0 implements only the PostgreSQL foundation. Naming future adapters here does not enable or
configure them.

