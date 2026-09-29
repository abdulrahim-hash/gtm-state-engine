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

External actions are disabled by default. M0 has no CRM, webhook, messaging, enrichment, or outbound
adapter and no hidden live-write path.

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

