# ADR-001: PostgreSQL/Supabase is canonical memory

## Context

Account evidence, state, decisions, and outcomes require durable, queryable history independent of
individual GTM vendors.

## Decision

PostgreSQL is the canonical analytical/event memory. Supabase may provide hosted PostgreSQL.

## Consequences

Adapters must preserve stable internal IDs and provenance. Vendor records may inform or receive
state but do not replace canonical history.

## Status

Accepted

