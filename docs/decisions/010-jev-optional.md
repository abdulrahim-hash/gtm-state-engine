# ADR-010: Jev is optional and provider-abstracted

## Context

Jev may be useful for bounded decisions, but product architecture must not depend on one emerging
provider.

## Decision

Any future Jev integration will sit behind a provider interface and disabled-by-default feature
flag.

## Consequences

The system runs without Jev. Promotion of model authority requires comparative evaluation against
rules, other models, and human labels.

## Status

Accepted

