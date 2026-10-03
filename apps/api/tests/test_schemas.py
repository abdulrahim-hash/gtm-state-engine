"""Unit tests for M1A evidence boundary validation."""

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import ValidationError

from gtm_state_api.main import app
from gtm_state_api.schemas import EvidenceValidationInput
from gtm_state_api.types import (
    EvidenceAssertion,
    EvidenceClassification,
    EvidenceFreshness,
)


def _payload() -> dict[str, object]:
    return {
        "account_id": uuid4(),
        "classification": EvidenceClassification.FACT,
        "source_provider": "synthetic_demo_fixture",
        "source_reference": "synthetic://fixture/evidence/1",
        "observed_at": datetime(2026, 9, 15, tzinfo=UTC),
        "ingested_at": datetime(2026, 9, 15, tzinfo=UTC),
        "normalized_fact": "Synthetic fixture observation.",
        "freshness": EvidenceFreshness.CURRENT,
    }


def test_fact_evidence_requires_null_epistemic_confidence() -> None:
    payload = _payload()
    payload["confidence"] = Decimal("0.90")

    with pytest.raises(ValidationError, match="FACT evidence"):
        EvidenceValidationInput.model_validate(payload)


def test_inference_and_hypothesis_allow_epistemic_confidence() -> None:
    for classification in (EvidenceClassification.INFERENCE, EvidenceClassification.HYPOTHESIS):
        payload = _payload()
        payload["classification"] = classification
        payload["confidence"] = Decimal("0.70")

        assert EvidenceValidationInput.model_validate(payload).confidence == Decimal("0.70")


def test_evidence_requires_exactly_one_m1a_target() -> None:
    payload = _payload()
    payload["strategy_version_id"] = uuid4()

    with pytest.raises(ValidationError, match="exactly one"):
        EvidenceValidationInput.model_validate(payload)


def test_evidence_rejects_invalid_raw_payload_hash() -> None:
    payload = _payload()
    payload["raw_payload_hash"] = "not-a-sha256"

    with pytest.raises(ValidationError):
        EvidenceValidationInput.model_validate(payload)


def test_normalized_fact_key_and_assertion_are_required_together() -> None:
    payload = _payload()
    payload["fact_key"] = "commercial_event.new_revenue_leader"

    with pytest.raises(ValidationError, match="provided together"):
        EvidenceValidationInput.model_validate(payload)

    payload["fact_assertion"] = EvidenceAssertion.PRESENT
    validated = EvidenceValidationInput.model_validate(payload)
    assert validated.fact_assertion is EvidenceAssertion.PRESENT


def test_strategy_evidence_cannot_be_normalized_as_an_account_fact() -> None:
    payload = _payload()
    payload["account_id"] = None
    payload["strategy_version_id"] = uuid4()
    payload["strategy_topic"] = "MARKET"
    payload["fact_key"] = "commercial_event.new_revenue_leader"
    payload["fact_assertion"] = EvidenceAssertion.PRESENT

    with pytest.raises(ValidationError, match="strategy evidence"):
        EvidenceValidationInput.model_validate(payload)


def test_m1c_openapi_paths_are_get_only() -> None:
    schema = app.openapi()
    paths = schema["paths"]
    m1c_paths = (
        "/api/v1/accounts/{account_id}/decision",
        "/api/v1/accounts/{account_id}/decision/history",
        "/api/v1/decision-evaluations/{decision_evaluation_id}",
        "/api/v1/policy-evaluations/{policy_evaluation_id}",
    )

    for path in m1c_paths:
        assert set(paths[path]) == {"get"}
