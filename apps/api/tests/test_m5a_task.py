"""Narrow Task adapter contracts and failure semantics without provider access."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast
from urllib.request import Request

import pytest
from fastapi.testclient import TestClient

from gtm_state_api import m5a_api
from gtm_state_api.config import Settings
from gtm_state_api.hubspot_task import (
    API_VERSION,
    TASKS_PATH,
    TaskAdapterError,
    TaskFields,
    _request,
    _transport,
    create_task_once,
    find_marker_task_ids,
    get_task,
    verify_owner,
    verify_task_company_association,
)
from gtm_state_api.m5a_scope_proof import (
    ScopeProofError,
    credential_fingerprint,
    verify_scope_proof,
)

FIELDS = TaskFields(
    due_at="2026-10-07T12:00:00Z",
    subject="SYNTHETIC: Review relationship context",
    body="DEVELOPER TEST ONLY. Synthetic relationship review. GTM-M5A:abc123",
    owner_id="789",
)


def wire(status: int, value: object) -> tuple[int, bytes, Mapping[str, str]]:
    return status, json.dumps(value).encode(), {"X-HubSpot-Correlation-Id": "test-correlation"}


def test_create_uses_one_exact_post_and_bounded_payload() -> None:
    calls: list[Request] = []

    def transport(request: Request) -> tuple[int, bytes, Mapping[str, str]]:
        calls.append(request)
        return wire(201, {"id": "456", "createdAt": "2026-10-06T12:00:00Z"})

    result = create_task_once(
        credential="fixture-token",
        fields=FIELDS,
        company_id="123",
        association_type_id=192,
        transport=transport,
    )
    assert result.task_id == "456"
    assert len(calls) == 1
    assert calls[0].get_method() == "POST"
    assert calls[0].full_url == f"https://api.hubapi.com{TASKS_PATH}"
    assert calls[0].data is not None
    body = json.loads(cast(bytes, calls[0].data))
    assert body == {
        "properties": FIELDS.properties(),
        "associations": [
            {
                "to": {"id": "123"},
                "types": [{"associationCategory": "HUBSPOT_DEFINED", "associationTypeId": 192}],
            }
        ],
    }
    assert "fixture-token" not in json.dumps(body)


@pytest.mark.parametrize(
    "status,body,code",
    [
        (400, {"category": "VALIDATION_ERROR"}, "PROVIDER_REJECTED_NO_WRITE"),
        (401, {}, "PROVIDER_REJECTED_NO_WRITE"),
        (403, {}, "PROVIDER_REJECTED_NO_WRITE"),
        (400, {"category": "UNKNOWN"}, "AMBIGUOUS_WRITE_RESPONSE"),
        (429, {}, "AMBIGUOUS_WRITE_RESPONSE"),
        (500, {}, "AMBIGUOUS_WRITE_RESPONSE"),
        (201, {"id": "invalid"}, "AMBIGUOUS_WRITE_RESPONSE"),
    ],
)
def test_post_never_retries_and_classifies_uncertainty(
    status: int,
    body: object,
    code: str,
) -> None:
    calls = 0

    def transport(_request: Request) -> tuple[int, bytes, Mapping[str, str]]:
        nonlocal calls
        calls += 1
        return wire(status, body)

    with pytest.raises(TaskAdapterError) as error:
        create_task_once(
            credential="fixture-token",
            fields=FIELDS,
            company_id="123",
            association_type_id=192,
            transport=transport,
        )
    assert error.value.code == code
    assert calls == 1


def test_task_get_requires_exact_company_association_shape() -> None:
    def transport(_request: Request) -> tuple[int, bytes, Mapping[str, str]]:
        return wire(
            200,
            {
                "id": "456",
                "archived": False,
                "properties": FIELDS.properties(),
                "associations": {"companies": {"results": [{"id": "123"}]}},
            },
        )

    task, reads = get_task("456", credential="fixture-token", transport=transport)
    assert reads == 1
    assert task is not None and task.company_ids == ("123",)
    assert task.properties == FIELDS.properties()


def test_task_get_without_company_association_is_explicit_empty_set() -> None:
    def transport(_request: Request) -> tuple[int, bytes, Mapping[str, str]]:
        return wire(
            200,
            {
                "id": "456",
                "archived": False,
                "properties": FIELDS.properties(),
                "associations": {},
            },
        )

    task, _ = get_task("456", credential="fixture-token", transport=transport)
    assert task is not None and task.company_ids == ()


def test_marker_scan_never_proves_absence_when_page_cap_reached() -> None:
    calls = 0

    def transport(_request: Request) -> tuple[int, bytes, Mapping[str, str]]:
        nonlocal calls
        calls += 1
        return wire(200, {"results": [], "paging": {"next": {"after": str(calls)}}})

    matches, reads, complete = find_marker_task_ids(
        marker="GTM-M5A:abc123",
        company_id="123",
        credential="fixture-token",
        transport=transport,
    )
    assert matches == [] and reads == calls == 3 and complete is False


def test_owner_and_association_proof_are_exact() -> None:
    def owner_transport(request: Request) -> tuple[int, bytes, Mapping[str, str]]:
        assert request.full_url.endswith(f"/crm/owners/{API_VERSION}/789")
        return wire(200, {"id": "789", "archived": False, "userId": 100})

    def association_transport(request: Request) -> tuple[int, bytes, Mapping[str, str]]:
        assert request.full_url.endswith(f"/crm/associations/{API_VERSION}/tasks/companies/labels")
        return wire(
            200, {"results": [{"category": "HUBSPOT_DEFINED", "typeId": 192, "label": None}]}
        )

    assert verify_owner("789", credential="fixture-token", transport=owner_transport)
    assert verify_task_company_association(
        192, credential="fixture-token", transport=association_transport
    )


def test_request_allowlist_rejects_other_writes_and_paths() -> None:
    with pytest.raises(TaskAdapterError, match="DISALLOWED_REQUEST"):
        _request("POST", "/crm/objects/2026-09/companies", "fixture-token")
    with pytest.raises(TaskAdapterError, match="DISALLOWED_REQUEST"):
        _request("PATCH", TASKS_PATH, "fixture-token")
    with pytest.raises(TaskAdapterError, match="DISALLOWED_REQUEST"):
        _request("GET", TASKS_PATH + "/123/associations/contacts", "fixture-token")
    with pytest.raises(TaskAdapterError, match="DISALLOWED_REQUEST"):
        _transport(Request("https://api.hubapi.com/crm/objects/2026-09/notes", method="GET"))


def test_production_execution_route_is_404_without_database_use(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from gtm_state_api.main import app

    monkeypatch.setattr(m5a_api, "get_settings", lambda: Settings(app_env="production"))
    with TestClient(app) as client:
        response = client.get("/api/v1/pilot/m5a/executions/00000000-0000-0000-0000-000000000001")
        write_response = client.post(
            "/api/v1/pilot/m5a/executions/00000000-0000-0000-0000-000000000001"
        )
    assert response.status_code == 404
    assert write_response.status_code == 405


def test_production_write_enablement_is_invalid() -> None:
    with pytest.raises(ValueError, match="M5A_TASK_WRITE_ENABLED"):
        Settings(app_env="production", m5a_task_write_enabled=True)


def test_scope_proof_binds_exact_token_portal_owner_and_time(tmp_path: Path) -> None:
    now = datetime(2026, 10, 6, 17, 0, tzinfo=UTC)
    proof = {
        "source": "HUBSPOT_PORTAL_UI",
        "portal_id": "12345",
        "owner_id": "789",
        "credential_sha256": credential_fingerprint("fixture-token"),
        "inspected_at": now.isoformat(),
        "operator_ref": "local-fixture",
        "capabilities": {
            name: ["crm.objects.companies.read"]
            for name in (
                "TASK_CREATE",
                "TASK_READ",
                "COMPANY_READ",
                "TASK_COMPANY_ASSOCIATION",
                "OWNER_READ",
            )
        },
    }
    path = tmp_path / "scope-proof.json"
    path.write_text(json.dumps(proof), encoding="utf-8")
    verify_scope_proof(path, credential="fixture-token", portal_id="12345", owner_id="789", now=now)
    with pytest.raises(ScopeProofError, match="SCOPE_PROOF_BINDING_INVALID"):
        verify_scope_proof(
            path, credential="different-token", portal_id="12345", owner_id="789", now=now
        )
    with pytest.raises(ScopeProofError, match="SCOPE_PROOF_BINDING_INVALID"):
        verify_scope_proof(
            path, credential="fixture-token", portal_id="99999", owner_id="789", now=now
        )
    with pytest.raises(ScopeProofError, match="SCOPE_PROOF_EXPIRED"):
        verify_scope_proof(
            path,
            credential="fixture-token",
            portal_id="12345",
            owner_id="789",
            now=now + timedelta(hours=1, seconds=1),
        )
