"""M2C bounded adapter, mapper, and versioned relationship semantics."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from urllib.request import Request
from uuid import uuid4

import pytest

from gtm_state_api.hubspot_company_read import (
    MAX_RETRIES,
    ProviderReadError,
    read_company,
    verify_developer_test_portal,
)
from gtm_state_api.ingestion_mapping import CRM_CUSTOMER_MAPPER
from gtm_state_api.models import Evidence
from gtm_state_api.private_company_read import CustomerStageMapping, scoped_dataset_key
from gtm_state_api.source_observation import SourceObservationInput, canonical_hash
from gtm_state_api.state_engine import (
    CRM_RELATIONSHIP_WINDOW_HOURS,
    CRM_STATE_ENGINE_VERSION,
    STATE_ENGINE_REGISTRY,
    evaluate_crm_reported_relationship,
)
from gtm_state_api.types import (
    AccountRelationshipState,
    EvidenceAssertion,
    EvidenceClassification,
    EvidenceFreshness,
)

TIME = datetime(2026, 10, 4, 21, 37, 20, tzinfo=UTC)


def body(stage: str = "customer", domain: str | None = "m2c-customer.example.com") -> bytes:
    return json.dumps(
        {
            "id": "123",
            "updatedAt": "2026-10-04T20:00:00Z",
            "properties": {
                "name": "M2C Customer Test",
                "domain": domain,
                "lifecyclestage": stage,
                "phone": "DO_NOT_KEEP",
                "email": "DO_NOT_KEEP",
            },
        }
    ).encode()


def test_adapter_only_requests_bounded_company_fields_and_discards_other_fields() -> None:
    requests: list[Request] = []

    def transport(request: Request) -> tuple[int, bytes, dict[str, str]]:
        requests.append(request)
        return 200, body(), {}

    result = read_company("123", credential="secret-test", transport=transport)
    assert result.record is not None
    assert result.record.company_domain == "m2c-customer.example.com"
    assert "phone" not in vars(result.record)
    assert "email" not in vars(result.record)
    assert len(requests) == 1
    assert requests[0].get_method() == "GET"
    assert requests[0].full_url.endswith("?properties=name,domain,lifecyclestage&archived=false")


@pytest.mark.parametrize(
    ("status", "code"),
    [
        (401, "UNAUTHORIZED"),
        (403, "FORBIDDEN"),
        (400, "PROVIDER_RESPONSE"),
    ],
)
def test_adapter_fails_without_retry_or_body_leak(status: int, code: str) -> None:
    calls = 0

    def transport(_request: Request) -> tuple[int, bytes, dict[str, str]]:
        nonlocal calls
        calls += 1
        return status, b"private response with token-secret", {}

    with pytest.raises(ProviderReadError) as raised:
        read_company("123", credential="token-secret", transport=transport)
    assert raised.value.code == code
    assert "token-secret" not in str(raised.value)
    assert calls == 1


@pytest.mark.parametrize(("status", "code"), [(429, "RATE_LIMIT"), (500, "PROVIDER_5XX")])
def test_adapter_bounded_retries(status: int, code: str) -> None:
    calls = 0
    sleeps: list[float] = []

    def transport(_request: Request) -> tuple[int, bytes, dict[str, str]]:
        nonlocal calls
        calls += 1
        return status, b"", {}

    with pytest.raises(ProviderReadError, match=code) as raised:
        read_company("123", credential="test", transport=transport, sleep_fn=sleeps.append)
    assert calls == MAX_RETRIES + 1
    assert raised.value.retries == MAX_RETRIES
    assert sleeps == [0.25, 0.5]


def test_adapter_404_is_not_absence_evidence() -> None:
    result = read_company("123", credential="test", transport=lambda _: (404, b"", {}))
    assert result.record is None


@pytest.mark.parametrize(
    "payload",
    [
        b"not-json",
        b"[]",
        b'{"id":"123","properties":{}}',
        json.dumps(
            {
                "id": "123",
                "properties": {"name": "Test", "domain": "x.com", "lifecyclestage": "customer"},
                "paging": {"next": "x"},
            }
        ).encode(),
    ],
)
def test_adapter_rejects_malformed_or_paginated_response(payload: bytes) -> None:
    with pytest.raises(ProviderReadError):
        read_company("123", credential="test", transport=lambda _: (200, payload, {}))


def test_portal_verification_requires_exact_developer_test_scope() -> None:
    verify_developer_test_portal(
        credential="test",
        expected_portal_id="11",
        transport=lambda _: (200, b'{"portalId":11,"accountType":"DEVELOPER_TEST"}', {}),
    )
    with pytest.raises(ProviderReadError, match="NOT_DEVELOPER_TEST"):
        verify_developer_test_portal(
            credential="test",
            expected_portal_id="11",
            transport=lambda _: (200, b'{"portalId":11,"accountType":"STANDARD"}', {}),
        )
    with pytest.raises(ProviderReadError, match="PORTAL_MISMATCH"):
        verify_developer_test_portal(
            credential="test",
            expected_portal_id="12",
            transport=lambda _: (200, b'{"portalId":11,"accountType":"DEVELOPER_TEST"}', {}),
        )


def observation(stage: str, at: datetime = TIME) -> SourceObservationInput:
    fields = {
        "company_name": "Test",
        "company_domain": "test.example.com",
        "lifecycle_stage": stage,
        "configured_customer_stage": "customer",
        "stage_mapping_version": "1.0.0",
        "provider_updated_at": "",
    }
    return SourceObservationInput(
        external_record_id="123",
        external_account_id="123",
        company_name="Test",
        company_domain="test.example.com",
        source_observed_at=at,
        event_at=None,
        citation_url=None,
        fact_code="crm_reports_customer_status",
        assertion="PRESENT" if stage == "customer" else "INCONCLUSIVE",
        excerpt="bounded test",
        original_fields=fields,
        payload_sha256=canonical_hash(fields),
    )


def test_mapper_positive_and_noncustomer_are_both_facts_without_absent() -> None:
    positive = CRM_CUSTOMER_MAPPER.normalize(observation("customer"))
    other = CRM_CUSTOMER_MAPPER.normalize(observation("lead"))
    assert positive.assertion is EvidenceAssertion.PRESENT
    assert other.assertion is EvidenceAssertion.INCONCLUSIVE
    assert positive.classification is EvidenceClassification.FACT
    assert other.classification is EvidenceClassification.FACT
    assert positive.output_sha256 != other.output_sha256


def evidence(assertion: EvidenceAssertion, at: datetime) -> Evidence:
    return Evidence(
        id=uuid4(),
        account_id=uuid4(),
        classification=EvidenceClassification.FACT,
        source_provider="test",
        source_reference="test",
        source_uri=None,
        observed_at=at,
        ingested_at=TIME,
        normalized_fact="test",
        raw_payload_hash="a" * 64,
        freshness=EvidenceFreshness.UNKNOWN,
        fact_key="relationship.crm_reports_customer_status",
        fact_assertion=assertion,
    )


def test_crm_relationship_freshness_boundary_and_noncustomer_revocation() -> None:
    assert CRM_STATE_ENGINE_VERSION == "1.2.0"
    assert STATE_ENGINE_REGISTRY[CRM_STATE_ENGINE_VERSION].relationship == (
        "crm_reported_customer_observation_window",
        "1.0.0",
    )
    positive = evidence(EvidenceAssertion.PRESENT, TIME)
    latest_allowed = TIME + timedelta(hours=CRM_RELATIONSHIP_WINDOW_HOURS)
    assert (
        evaluate_crm_reported_relationship([positive], state_as_of=latest_allowed).value
        is AccountRelationshipState.EXISTING_RELATIONSHIP
    )
    assert (
        evaluate_crm_reported_relationship(
            [positive], state_as_of=latest_allowed + timedelta(microseconds=1)
        ).value
        is AccountRelationshipState.UNKNOWN
    )
    assert (
        evaluate_crm_reported_relationship(
            [positive], state_as_of=TIME - timedelta(microseconds=1)
        ).value
        is AccountRelationshipState.UNKNOWN
    )
    later_noncustomer = evidence(EvidenceAssertion.INCONCLUSIVE, TIME + timedelta(minutes=1))
    assert (
        evaluate_crm_reported_relationship(
            [positive, later_noncustomer], state_as_of=TIME + timedelta(minutes=2)
        ).value
        is AccountRelationshipState.UNKNOWN
    )


def test_portal_scope_and_stage_mapping_are_versioned() -> None:
    assert scoped_dataset_key("123") != scoped_dataset_key("124")
    assert CustomerStageMapping("customer", "1.0.0").customer_value == "customer"
    with pytest.raises(ValueError):
        CustomerStageMapping("customer", "unversioned")


def test_missing_credential_and_timeout_are_bounded() -> None:
    with pytest.raises(ProviderReadError, match="MISSING_CREDENTIAL"):
        read_company("123", credential="")

    def timeout(_request: Request) -> tuple[int, bytes, dict[str, str]]:
        raise ProviderReadError("TIMEOUT_OR_NETWORK")

    with pytest.raises(ProviderReadError, match="TIMEOUT_OR_NETWORK") as raised:
        read_company("123", credential="sensitive-token", transport=timeout)
    assert "sensitive-token" not in str(raised.value)


def test_m2c_private_api_is_not_available_in_production(monkeypatch: pytest.MonkeyPatch) -> None:
    from fastapi.testclient import TestClient

    from gtm_state_api.config import get_settings
    from gtm_state_api.main import app

    monkeypatch.setenv("APP_ENV", "production")
    get_settings.cache_clear()
    try:
        with TestClient(app) as client:
            trace = client.get("/api/v1/pilot/m2c/trace?as_of=2026-10-04T21:37:20Z")
            run = client.get(f"/api/v1/pilot/m2c/runs/{uuid4()}")
        assert trace.status_code == run.status_code == 404
        assert "CRM TEST" not in trace.text
    finally:
        get_settings.cache_clear()


def test_portal_verification_retries_rate_limit_without_company_read() -> None:
    calls = 0
    sleeps: list[float] = []

    def transport(request: Request) -> tuple[int, bytes, dict[str, str]]:
        nonlocal calls
        calls += 1
        assert request.get_method() == "GET"
        assert request.full_url.endswith("/account-info/v3/details")
        if calls < 3:
            return 429, b"private provider body", {}
        return 200, b'{"portalId":11,"accountType":"DEVELOPER_TEST"}', {}

    verify_developer_test_portal(
        credential="synthetic-token",
        expected_portal_id="11",
        transport=transport,
        sleep_fn=sleeps.append,
    )
    assert calls == 3
    assert sleeps == [0.25, 0.5]
