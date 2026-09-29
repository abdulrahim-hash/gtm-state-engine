# ADR-002: HubSpot is an operational adapter

## Context

Sellers may work in HubSpot, while provider-specific identity and history are insufficient as
canonical system memory.

## Decision

HubSpot will be a future seller-facing operational adapter, not the canonical identity store.

## Consequences

Mappings require stable IDs, idempotency, explicit ownership rules, and protection for human-owned
fields.

## Status

Accepted

