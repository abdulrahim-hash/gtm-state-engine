"""Focused M2B manifest, profile freshness, and local exposure tests."""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path
from shutil import copyfile
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from gtm_state_api.config import get_settings
from gtm_state_api.ingestion_mapping import MAPPER_REGISTRY, PROFILE_MAPPER, MappingRejection
from gtm_state_api.local_csv import parse_local_csv
from gtm_state_api.main import app
from gtm_state_api.models import Evidence, StrategyFitCriterion
from gtm_state_api.pilot_m2b import load_manifest
from gtm_state_api.pilot_m2b_run import validate_dataset
from gtm_state_api.state_engine import evaluate_fit_context
from gtm_state_api.types import (
    AccountFitContext,
    EvidenceAssertion,
    EvidenceClassification,
    EvidenceFreshness,
    IngestionReason,
)

ROOT = Path(__file__).resolve().parents[3] / "docs" / "pilot" / "m2b"
AS_OF = datetime(2026, 10, 5, tzinfo=UTC)
PROFILE_KEY = "account_profile.offers_sales_enablement_software"


def test_frozen_manifest_hash_order_and_cohort_separation() -> None:
    manifest, manifest_hash = load_manifest(ROOT / "selection_manifest.v2.json")
    base = manifest["base_candidates"]
    queue = manifest["trace_coverage_screening_queue"]
    assert isinstance(base, list) and isinstance(queue, list)
    assert len(base) == 18
    assert len(queue) == 5
    assert manifest["state_as_of"] == "2026-10-05T00:00:00Z"
    assert manifest_hash == sha256((ROOT / "selection_manifest.v2.json").read_bytes()).hexdigest()
    ledger = json.loads((ROOT / "selection_ledger.v1.json").read_text())
    assert ledger["manifest_sha256"] == manifest_hash
    assert {x["domain"] for x in ledger["trace_coverage"]}.isdisjoint(base)
    assert ledger["trace_coverage"][0]["coverage_status"] == "PILOT_COVERAGE_NOT_MET"
    assert not ledger["eligibility_skips"] and not ledger["post_result_replacements"]
    assert validate_dataset(ROOT, manifest, ledger)["company_public_profiles"]["rows"] == 20


def test_manifest_revisions_cannot_be_silently_substituted(tmp_path: Path) -> None:
    original = (ROOT / "selection_manifest.v2.json").read_text()
    tampered = tmp_path / "tampered.json"
    tampered.write_text(original.replace("2026-10-05T00:00:00Z", "2026-10-06T00:00:00Z", 1))
    with pytest.raises(ValueError, match="semantic times"):
        load_manifest(tampered)


@pytest.mark.parametrize(
    ("old", "new", "error"),
    [
        (
            "2026-09-22T00:00:00Z",
            "2026-09-23T00:00:00Z",
            "CSV claim does not match manual verification ledger",
        ),
        (
            "2026-10-04T10:19:27Z",
            "2026-10-06T10:19:27Z",
            "source was observed after frozen snapshot",
        ),
    ],
)
def test_verified_event_or_observation_time_cannot_drift(
    tmp_path: Path, old: str, new: str, error: str
) -> None:
    for filename in ("profiles.v1.csv", "leaders.v1.csv", "source_verification.v1.json"):
        copyfile(ROOT / filename, tmp_path / filename)
    leaders = tmp_path / "leaders.v1.csv"
    body = leaders.read_text(encoding="utf-8")
    assert old in body
    leaders.write_text(body.replace(old, new, 1), encoding="utf-8")
    manifest, _ = load_manifest(ROOT / "selection_manifest.v2.json")
    ledger = json.loads((ROOT / "selection_ledger.v1.json").read_text(encoding="utf-8"))
    with pytest.raises(ValueError, match=error):
        validate_dataset(tmp_path, manifest, ledger)


def test_profile_mapper_is_versioned_dated_and_rejects_absent_or_event_time() -> None:
    _, rows = parse_local_csv(ROOT / "profiles.v1.csv", dataset_key="company_public_profiles")
    observation = rows[0].observation
    assert observation is not None
    fact = PROFILE_MAPPER.normalize(observation)
    assert fact.fact_key == PROFILE_KEY
    assert fact.classification is EvidenceClassification.FACT
    assert fact.assertion is EvidenceAssertion.PRESENT
    assert fact.observed_at == observation.source_observed_at
    assert PROFILE_MAPPER.mapper_version == "1.0.0"
    assert len(MAPPER_REGISTRY) == 2
    with pytest.raises(MappingRejection) as rejected:
        PROFILE_MAPPER.normalize(replace(observation, assertion="ABSENT"))
    assert rejected.value.reason is IngestionReason.INVALID_ASSERTION
    with pytest.raises(MappingRejection) as rejected:
        PROFILE_MAPPER.normalize(replace(observation, event_at=AS_OF - timedelta(days=1)))
    assert rejected.value.reason is IngestionReason.INVALID_DATE


def test_profile_observation_has_bounded_snapshot_freshness() -> None:
    criterion = StrategyFitCriterion(
        fit_criterion_id=uuid4(),
        workspace_id=uuid4(),
        strategy_version_id=uuid4(),
        stable_key="official_sales_enablement_offering",
        display_name="Pilot criterion",
        description="Narrow public offering criterion",
        input_fact_key=PROFILE_KEY,
        expected_assertion=EvidenceAssertion.PRESENT,
        source_strategy_evidence_id=uuid4(),
        created_at=AS_OF,
    )
    evidence = Evidence(
        id=uuid4(),
        account_id=uuid4(),
        strategy_version_id=None,
        strategy_topic=None,
        classification=EvidenceClassification.FACT,
        source_provider="manual_test",
        source_reference="source-observation:test",
        source_uri="https://example.com/offering",
        observed_at=AS_OF - timedelta(days=14),
        ingested_at=AS_OF,
        normalized_fact="Official public offering",
        raw_payload_hash=None,
        freshness=EvidenceFreshness.UNKNOWN,
        confidence=None,
        fact_key=PROFILE_KEY,
        fact_assertion=EvidenceAssertion.PRESENT,
    )
    assert (
        evaluate_fit_context([criterion], [evidence], pilot_state_as_of=AS_OF).value
        is AccountFitContext.MATCH
    )
    assert (
        evaluate_fit_context(
            [criterion], [evidence], pilot_state_as_of=AS_OF + timedelta(seconds=1)
        ).value
        is AccountFitContext.UNKNOWN
    )
    assert (
        evaluate_fit_context(
            [criterion], [evidence], pilot_state_as_of=AS_OF - timedelta(days=15)
        ).value
        is AccountFitContext.UNKNOWN
    )
    evidence.fact_assertion = EvidenceAssertion.INCONCLUSIVE
    assert (
        evaluate_fit_context([criterion], [evidence], pilot_state_as_of=AS_OF).value
        is AccountFitContext.INCONCLUSIVE
    )


def test_production_pilot_trace_is_not_exposed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    get_settings.cache_clear()
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/pilot/m2b/trace")
        assert response.status_code == 404
        assert "Consensus" not in response.text
    finally:
        get_settings.cache_clear()
