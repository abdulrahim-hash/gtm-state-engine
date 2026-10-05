# M2C local CRM relationship read

M2C is a local, operator-triggered **read-only** test against one HubSpot `DEVELOPER_TEST` account. It is not a CRM deployment or a customer-data sync. Use two unmistakably synthetic Company records, no contacts: one with the portal's configured Customer lifecycle value and one with another value. Company names/domains must match the two pre-seeded isolated fixture accounts (`M2C Customer Test` / `m2c-customer.example.com`; `M2C Lead Test` / `m2c-lead.example.com`). Never use a production portal or client data.

## Configuration

Copy the M2C names from [`.env.example`](../../.env.example) into an ignored repository-root `.env.m2c.local`. Supply a developer-test private-app token with only the Company read and account-info permissions needed by the adapter, the exact portal ID, the two synthetic Company IDs, the attested exact Customer-stage value, and a mapping version. The CLI validates the portal ID and `DEVELOPER_TEST` type before every Company read. Do not paste the token into chat, screenshots, issue bodies, logs, or Git. The ignored file is read from the repository root even when `uv --directory apps/api` changes the command working directory.

`CRM-reported Customer` means only that the configured lifecycle stage matched at observation time. It is **not** independent evidence of an active contract, subscription, revenue, seller activity, or legal customer status. A non-Customer or empty stage produces an `INCONCLUSIVE` relationship assertion, never `ABSENT`.

## Operator sequence

Run these commands from the repository root with PostgreSQL available and Alembic upgraded. Pick an explicit UTC `FIXTURE_AS_OF` immediately before reads. After inspecting both reads, choose one `STATE_AS_OF` at or after both observation times and record it; do not let a wall clock silently supply semantic time.

```powershell
uv run --directory apps/api alembic upgrade head
uv run --directory apps/api python scripts/m2c_crm_read.py setup --as-of 2026-10-04T21:36:00Z
uv run --directory apps/api python scripts/m2c_crm_read.py probe --role customer --attest-customer-stage
uv run --directory apps/api python scripts/m2c_crm_read.py probe --role noncustomer --attest-customer-stage
uv run --directory apps/api python scripts/m2c_crm_read.py pull --role customer --attest-customer-stage
uv run --directory apps/api python scripts/m2c_crm_read.py pull --role noncustomer --attest-customer-stage
```

The timestamps above document the first local validation. The fixture time is immutable for this workspace: rerun `setup` only with the same time. A later read may use a new explicit `STATE_AS_OF` while the synthetic Fit fixture remains within its existing 14-day window. After that window, create a separately versioned test fixture/workspace rather than moving the original time. `probe` creates no source observation. `pull` creates only a bounded source read run, observation, normalization, binding, and Evidence. Inspect each returned `run_id` with `inspect --run-id <UUID>`. Confirm portal-scope hash, exact identity, stage mapping version, assertion, and accepted/unresolved/rejected counts. No downstream stage runs automatically.

For each of `signals`, `state`, `decisions`, `policies`, and `actions`, run the local script separately with `--as-of <STATE_AS_OF> --run-id <CUSTOMER_RUN_UUID> --run-id <NONCUSTOMER_RUN_UUID> --confirm-inspected`. The gate checks all effective observations for that snapshot and fails on a same-time conflict. `state` asserts its internal Signal recomputation reuses the explicit Signal identities/hashes/results. End with `trace --as-of <STATE_AS_OF>` or open local `/crm-test?as_of=<STATE_AS_OF>`. A production build returns 404 for this view; the API returns 404 for its private inspection routes.

## Freshness and failure behavior

The M2C relationship evaluator is `1.2.0`; its positive observation window is **24 inclusive hours** from `source_observed_at` to explicit `state_as_of`. `provider updatedAt` is metadata, never a substitute for the observation clock. At arbitrary future snapshots, the same Evidence expires to Relationship `UNKNOWN`. A newer non-Customer observation also yields `UNKNOWN`. An expired positive does not imply the portal no longer reports Customer; it means the snapshot lacks a fresh CRM report.

401/403, missing credential, malformed response, timeout, wrong portal, or source validation failure create no relationship FACT. 404 creates no FACT. 429 and 5xx on either approved GET have at most two bounded retries. A same provider ID and observation time with changed bounded content records `CONFLICT` and blocks downstream stages. Exact same-time replay reuses semantic observation/Evidence; a later read time creates history. All failures preserve `UNKNOWN` rather than infer absence. Source read success is not an `ActionOutcome`.

The adapter has no write method. `CREATE_SELLER_TASK` is an internal governed proposal, **not** a HubSpot task. No CRM create/update, contact read, owner assignment, outreach, or external action is permitted in M2C. Northstar and M2B remain separate and unchanged.
