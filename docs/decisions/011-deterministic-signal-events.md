# ADR-011: Deterministic evaluations and canonical signal events

## Context

A commercial event can be evaluated repeatedly as semantic time advances. Treating each evaluation
as a new signal would duplicate the event and obscure negative, stale, or inconclusive history.

## Decision

Persist immutable evaluations separately from canonical signal events. Derive evaluation identity
from strategy, definition, evidence input, and `evaluation_as_of`; derive event identity from the
affirmative event evidence without either clock. Select code-owned evaluators through explicit
`evaluator_key` and `rule_version` values.

## Consequences

Reevaluation preserves history and reuses the same event. Current signal freshness is resolved from
the latest linked evaluation. New evaluator implementations require reviewed code and versions.

## Status

Accepted
