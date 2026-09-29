# ADR-008: Core logic stays outside vendor UIs

## Context

Business logic hidden in orchestration or vendor interfaces is difficult to test, review, migrate,
and reproduce.

## Decision

Irreplaceable identity, evidence, state, decision, and policy logic stays in versioned code or
configuration. n8n may be a future adapter.

## Consequences

Vendor replacement does not erase system behavior. Core logic receives normal tests and change
review.

## Status

Accepted

