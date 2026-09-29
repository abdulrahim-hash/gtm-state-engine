# AGENTS.md — GTM State & Signal Engine

## Project identity

This repository is a public flagship GTM Engineering project.

The product is the **GTM State & Signal Engine**: a strategy-aware, evidence-backed GTM account-state and decision system.

Primary goal: demonstrate and build real GTM infrastructure, not a tool demo.

## Non-negotiable principles

1. Strategy before automation.
2. Evidence before conclusion.
3. Facts, inferences, and hypotheses must remain distinct.
4. Tools/vendors are adapters, not canonical architecture.
5. PostgreSQL/Supabase is the analytical/event system memory.
6. Deterministic rules/policy before model-driven production action.
7. AI/Jev output is advisory unless explicit policy authorizes an action.
8. Risky external actions require human review by default.
9. Public demo data must be synthetic; no prospect/client PII.
10. No secrets in Git.
11. Idempotency, retries, observability, and recovery are required production qualities.
12. Controlled learning is versioned and approved; no autonomous strategy/policy self-rewrite.
13. Build vertical slices before broad feature expansion.
14. Do not add tools merely to increase stack complexity.
15. Negative/inconclusive results must be preserved honestly.

## Source-of-truth rules

- Postgres/Supabase: canonical analytical/event memory.
- HubSpot: operational seller-facing adapter when enabled.
- Clay/Apollo/providers: data suppliers, never canonical identity stores.
- n8n: optional orchestration adapter; do not hide irreplaceable business logic inside vendor UI workflows.

## Evidence rules

Any material conclusion should be traceable to:
- source
- observed_at
- evidence reference
- strategy/policy/model version
- reason code
- confidence where probabilistic

No unsupported company facts in generated research/copy.

## GTM strategy rules

Do not invent or silently change:
- market
- segment
- ICP
- buyer
- problem
- value proposition
- offer
- pricing
- messaging
- channel
- motion

without explicit evidence and approval.

When strategy work is requested:
- identify FACT vs INFERENCE vs HYPOTHESIS
- preserve source references
- make assumptions testable
- prefer customer/market language over invented marketing language

## Engineering rules

- typed boundaries
- migrations for schema changes
- stable IDs
- idempotency for external writes
- dry-run mode
- bounded retries
- dead-letter handling for exhausted failures
- structured logs with run/correlation IDs
- no silent overwrite of human-owned fields
- schema/business-rule validation before external writes
- provider interfaces for integrations
- feature flags for optional model/providers
- cost tracking for paid API/provider actions where practical

## Model / AI rules

- structured outputs where possible
- validate model output before use
- log model/provider/version/task/input hash/evidence refs/latency/cost
- do not equate confidence with correctness
- support abstention/human review
- Jev must remain optional
- benchmark rules vs model approaches before promoting model authority

## Testing requirements

For any material logic:
- unit tests
- relevant integration/contract tests
- explicit failure-path tests

Critical end-to-end path:
strategy → evidence → signal → state → decision → policy → dry-run action → outcome.

Before task completion:
- run tests
- run lint/type checks
- run build where applicable
- report failed/skipped checks honestly

## Documentation/change control

Material architecture decisions require an ADR.

Meaningful work should update the build journal:
- problem
- evidence/context
- hypothesis
- decision
- implementation
- validation
- result
- failure/learning
- next action

Do not rewrite historical decisions to make the project story cleaner.

## Public-repo rules

Never commit:
- credentials
- real prospect PII
- client data
- private CRM exports
- live tokens
- proprietary paid datasets

Use synthetic fixtures and `.env.example`.

## Scope control

Do not add without a demonstrated need:
- autonomous multi-agent architecture
- Kafka/Kubernetes
- predictive revenue models
- contextual bandits
- giant RAG systems
- paid ads execution
- every outreach channel
- CRM replacement
- production billing/multitenancy
- uncontrolled scraping infrastructure

Prefer a smaller reliable system with measurable behavior.

## UX standard

The hosted app should be:
- polished
- clear
- uncluttered
- GTM-native
- recruiter-readable

A user should understand:
- who matters
- why now
- what evidence exists
- what action is recommended
- why the policy allowed/reviewed/blocked it

without reading the source code.

## Completion behavior

Never claim something works because it appears plausible.

Validate it.

At the end of a task report:
- files changed
- tests/checks run
- results
- limitations
- unresolved issues
- next logical step
