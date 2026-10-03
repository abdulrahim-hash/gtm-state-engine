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
## M2A local import controls

Only company-level public business assertions belong in the M2A schema. The strict ten-column
allowlist excludes contacts, emails, credentials, arbitrary source columns, and long scraped text.
Files must be regular `.csv` UTF-8, at most 1 MiB and 500 data rows, with an exact header. Each
field has a length bound; source observations have a 4 KiB PostgreSQL JSONB bound. Control
characters and spreadsheet-formula prefixes are rejected. HTTPS citations are syntax checked,
require the company domain when supplied, exclude URL user info, query strings, fragments, and
nonstandard ports, and are never fetched. Neither rows nor full URLs are logged.

The importer never stores full file bytes and never invokes a network provider. Batch/row logs
contain IDs, versions, counts, bounded reasons, and duration only. Local CSV mutation is CLI/service
only. The workspace-scoped GET inspection API returns 404 when `APP_ENV=production`; the CLI also
refuses production import/replay/promotion. Public Northstar reads explicitly use the synthetic
workspace. There is no hosted access path to imported local data and no production auth claim.

Real company files and pilot data must remain local and uncommitted. M2A includes no real-data
pilot or external supplier connection.
