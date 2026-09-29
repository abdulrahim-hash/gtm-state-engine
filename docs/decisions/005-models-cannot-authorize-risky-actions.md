# ADR-005: Models cannot authorize risky actions

## Context

Model confidence is not proof of correctness and generated output may be malformed or unsupported.

## Decision

No model output may directly authorize risky external action. Explicit policy and human review are
required by default.

## Consequences

Model output is validated, logged, and advisory. External-write paths remain disabled until their
policy and review controls exist.

## Status

Accepted

