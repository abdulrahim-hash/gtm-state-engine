# M5A local developer-test Task runbook

M5A is a one-write, local operator workflow. It cannot target M2B accounts, the synthetic M2C Lead, production portals, or real owners. The public web app has no Execute button or write API.

## Required local configuration

In the ignored `.env.m2c.local`, configure the existing M2C portal, synthetic Customer Company, and exact Customer stage, plus `M5A_HUBSPOT_ACCESS_TOKEN` and `M5A_HUBSPOT_TEST_OWNER_ID`. The M5A token is dedicated to the verified developer-test portal. Do not place tokens, token metadata, owner email, or screenshots with credentials in Git, CLI arguments, logs, or the database. `M5A_TASK_WRITE_ENABLED` defaults to `false` in application settings and must be enabled only in the local dispatch process. `APP_ENV=production` rejects write enablement.

Before live dispatch, inspect the credential's granted scopes in the HubSpot portal. Confirm the Task create and read operations, Company read/association, and exact owner read work for this developer-test portal. HubSpot's current 2026-09 Task reference does not provide a reliable private-token scope proof in the API response. Create an ignored `.m5a-scopes.local.json` in the repository root, recording the exact names of the granted scopes supporting each capability, the inspected portal and owner IDs, an operator label, and the inspection time. Run `scope-fingerprint` to obtain the SHA-256 fingerprint of the configured M5A token without printing the token. The CLI requires the file to bind to that fingerprint and portal and rejects a proof older than one hour. `--attest-task-scopes` is a truthful local operator statement after portal inspection, not token introspection or enterprise identity verification. If the granted scopes cannot be established, stop. Confirm that the one owner is a synthetic test user and record its **owner ID**, not its user ID. The CLI reads only that exact owner and rejects archived or unassigned owners. If no synthetic owner exists, stop before planning and POST.

The ignored scope proof has exactly these fields; replace every placeholder with a verified value and actual granted scope name:

```json
{
  "source": "HUBSPOT_PORTAL_UI",
  "portal_id": "verified-developer-test-portal-id",
  "owner_id": "verified-synthetic-owner-id",
  "credential_sha256": "sha256-from-scope-fingerprint-command",
  "inspected_at": "2026-10-06T17:00:00Z",
  "operator_ref": "local-operator-label",
  "capabilities": {
    "TASK_CREATE": ["actual-granted-scope-name"],
    "TASK_READ": ["actual-granted-scope-name"],
    "COMPANY_READ": ["actual-granted-scope-name"],
    "TASK_COMPANY_ASSOCIATION": ["actual-granted-scope-name"],
    "OWNER_READ": ["actual-granted-scope-name"]
  }
}
```

The file is a manual scope attestation; the adapter also exercises the read permissions through bounded GETs. The first POST remains prohibited if the Task create grant is uncertain. The proof file must not be committed.

Find the unlabelled `HUBSPOT_DEFINED` Task-to-Company association type ID in the developer-test portal. The `plan` and `preflight` commands verify the supplied ID against `GET /crm/associations/2026-09/tasks/companies/labels` before any write. If the association label contract is unavailable or ambiguous, stop. The adapter pins `POST /crm/objects/2026-09/tasks`, `GET /crm/objects/2026-09/tasks/{taskId}`, and bounded Task listing for marker reconciliation.

## Operator sequence

Run from `apps/api`. Use `.venv\Scripts\python.exe scripts\m2c_crm_read.py` for the existing M2C `probe`, `pull`, `inspect`, `signals`, `state`, `decisions`, `policies`, `actions`, and `trace` sequence documented in [the M2C runbook](m2c-local-runbook.md). Pull a **fresh** synthetic Customer Company observation, inspect it, and materialize a new eligible state chain at a current semantic time. The old October 4 trace is stale. The Lead/UNKNOWN proposal must remain unexecuted.

Then run `.venv\Scripts\python.exe scripts\m5a_task.py` with one stage at a time. Run `scope-fingerprint` after configuring the dedicated M5A credential and before creating the ignored scope proof:

1. `review --action-id <fresh-customer-action-uuid> --operator-ref <local-operator-label>`
2. `plan --action-id <same-uuid> --due-at <future-UTC-timestamp> --association-type-id <verified-id> --attest-synthetic-owner --attest-task-scopes`
3. `inspect-plan --plan-id <uuid> --plan-hash <64-char-hash>` and inspect the exact Company, owner, Task fields, marker, and portal scope.
4. `authorize --plan-id <uuid> --plan-hash <hash> --operator-ref <local-operator-label> --confirm-local-authorization`. This authorization lasts 30 minutes and binds the exact immutable plan.
5. `intent --plan-id <uuid> --plan-hash <hash>` to commit `NOT_ATTEMPTED` and its first audit event.
6. `preflight --plan-id <uuid> --plan-hash <hash> --attest-synthetic-owner --attest-task-scopes` immediately before dispatch.
7. Set `M5A_TASK_WRITE_ENABLED=true` only for the local CLI process. Run `dispatch --plan-id <uuid> --plan-hash <hash> --attest-synthetic-owner --attest-task-scopes --confirm-developer-test-write` **once**. This reserves the one possible POST in PostgreSQL before contacting HubSpot. Do not repeat it after an error.
8. Run `reconcile --plan-id <uuid> --plan-hash <hash>`. This uses only bounded GETs, verifies the exact Company association and owner, and records `CONFIRMED`, `MISMATCH`, `NOT_FOUND`, or `UNKNOWN`.
9. Run `inspect-execution --plan-id <uuid> --plan-hash <hash>` or inspect `/crm-execution?plan_id=<uuid>` locally. Repeat the `dispatch` command only as a negative replay check: it must stop before POST. Verify the marker finds exactly one Task in the developer-test portal.

`NOT_FOUND` after a possible delivery is **not** permission to POST again. A timeout, process death, ambiguous HTTP response, or receipt persistence failure requires read-only reconciliation. A second POST requires a future explicit repair process and is outside M5A.

## Truth boundary

`PROVIDER_ACCEPTED` means HubSpot returned a Task ID. `CONFIRMED` means the exact synthetic Task was observed through read-back, including owner and Company association. `CRM_TASK_CONFIRMED_CREATED` means only that operational fact at reconciliation time. It says nothing about Task completion, seller adoption, outreach, replies, meetings, pipeline, or revenue.

The local operator assurance is `LOCAL_OPERATOR_ATTESTATION`. The existing M1D `UNVERIFIED_DEMO_HUMAN` Review is necessary proposal review and is never sufficient execution authority. No production credential or real customer/person may be used.
