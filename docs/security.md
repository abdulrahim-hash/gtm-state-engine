# Security and data governance

## Public demo data

The public demo must use clearly labeled synthetic data. Real prospect/client PII, private CRM
exports, customer records, and proprietary paid datasets are prohibited from the repository and
public demo.

## Secrets

Secrets are supplied through environment variables or a deployment secret store. Only
`.env.example`, containing safe local placeholders, is committed. Local `.env` variants are
ignored. CI performs blocking secret detection.

## External actions

External actions are disabled by default. M1D has no CRM, webhook, messaging, enrichment, or
outbound adapter and no hidden live-write path. Every Action/read projection declares
`external_execution_authorized=false`; even Policy ALLOW and Review approval grant no external
execution authority.

`ACTION_MUTATIONS_ENABLED=false` is the default. Setting it true when `APP_ENV=production`
fails API startup validation. The hosted/public demo is read-only. Local-only review and dry-run
commands cannot be enabled by a request header or parameter. With no production authentication,
the client cannot submit reviewer/requester identity: the API stamps fixed
`UNVERIFIED_DEMO_HUMAN` non-identity references. Seeded Cinderlake uses
`SYNTHETIC_FIXTURE`, never a claimed real approver. Review Idempotency-Key is format/length
bounded, hashed before storage, and not logged raw.

A successful M1D dry-run means only that the canonical proposal and exact authority chain passed
local deterministic validation. It never contacts a provider. Operational Outcomes cannot claim
commercial success or external side effects.

Future risky actions require:

1. schema and business-rule validation;
2. stable idempotency keys;
3. dry-run support;
4. an explicit policy result;
5. human review by default;
6. an auditable execution result.

Model confidence cannot authorize a risky action.

## Repository and data boundaries

The repository may contain source code, schema migrations, synthetic fixtures, generated contracts,
tests, sanitized examples, and public documentation. It must not contain credentials, live tokens,
prospect PII, client data, production CRM exports, private notes, or proprietary datasets.

PostgreSQL is the canonical analytical/event memory. Future external systems remain bounded
adapters and must not silently overwrite human-owned fields.

## Public surface

Health responses are intentionally minimal. Readiness reports only `ready` or `not_ready` and
does not expose connection strings, hosts, usernames, exceptions, or database diagnostics.
Interactive API documentation is disabled when `APP_ENV=production`.
