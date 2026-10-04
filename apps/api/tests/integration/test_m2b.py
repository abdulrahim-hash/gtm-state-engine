"""Isolated PostgreSQL replay of the complete local M2B reasoning chain."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from shutil import copyfile
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Session

from gtm_state_api import pilot_m2b_run as pilot_run
from gtm_state_api.database import get_engine
from gtm_state_api.demo_seed import DEMO_WORKSPACE_ID
from gtm_state_api.models import Account, Action, ActionAttempt, ActionOutcome, Evidence
from gtm_state_api.pilot_m2b import load_manifest, setup

pytestmark = pytest.mark.integration
ROOT = Path(__file__).resolve().parents[4] / "docs" / "pilot" / "m2b"


@pytest.fixture
def isolated_connection() -> Iterator[Connection]:
    with get_engine().connect() as connection:
        outer = connection.begin()
        try:
            yield connection
        finally:
            outer.rollback()


def session_for(connection: Connection) -> Session:
    return Session(bind=connection, join_transaction_mode="create_savepoint")


def test_complete_pilot_replay_and_acceptance_gate(
    isolated_connection: Connection,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for filename in (
        "selection_manifest.v2.json",
        "selection_ledger.v1.json",
        "source_verification.v1.json",
        "profiles.v1.csv",
        "leaders.v1.csv",
    ):
        copyfile(ROOT / filename, tmp_path / filename)
    manifest, manifest_hash = load_manifest(tmp_path / "selection_manifest.v2.json")
    ledger = json.loads((tmp_path / "selection_ledger.v1.json").read_text())
    test_workspace = uuid4()
    test_strategy = uuid4()
    monkeypatch.setattr(pilot_run, "WORKSPACE_ID", test_workspace)
    monkeypatch.setattr(pilot_run, "STRATEGY_ID", test_strategy)
    with session_for(isolated_connection) as session:
        northstar_before = session.scalar(
            select(func.count())
            .select_from(Account)
            .where(Account.workspace_id == DEMO_WORKSPACE_ID)
        )
    with session_for(isolated_connection) as session:
        output = setup(
            session,
            manifest,
            manifest_hash,
            workspace_id=test_workspace,
            strategy_id=test_strategy,
            workspace_slug=f"m2b-test-{str(test_workspace)[:8]}",
        )
    assert output["strategy_version"] == "0.1.0"
    with session_for(isolated_connection) as session:
        imported = pilot_run.import_datasets(session, tmp_path)
    assert len(imported) == 2
    with session_for(isolated_connection) as session:
        with pytest.raises(ValueError, match="acceptance record is required"):
            pilot_run.verify_acceptance(session, tmp_path, manifest, manifest_hash, ledger)
        accepted = pilot_run.acceptance_payload(session, tmp_path, manifest, manifest_hash, ledger)
    assert accepted["batches"]["company_public_profiles"]["counts"]["accepted"] == 20
    assert accepted["batches"]["company_public_events"]["counts"]["accepted"] == 2
    (tmp_path / "acceptance.v1.json").write_text(json.dumps(accepted, sort_keys=True))
    with session_for(isolated_connection) as session:
        assert (
            pilot_run.verify_acceptance(session, tmp_path, manifest, manifest_hash, ledger)
            == accepted
        )
    with session_for(isolated_connection) as session:
        hypothesis = session.scalar(
            select(Evidence).where(
                Evidence.strategy_version_id == test_strategy,
                Evidence.source_reference.like("pilot-manifest:%"),
            )
        )
        assert hypothesis is not None
        hypothesis.source_reference = "pilot-manifest:stale-byte-hash"
        session.flush()
        with pytest.raises(ValueError, match="Strategy Evidence does not attest"):
            pilot_run.verify_acceptance(session, tmp_path, manifest, manifest_hash, ledger)
        session.rollback()

    first: dict[str, dict[str, object]] = {}
    for stage in ("signals", "state", "decisions", "policies", "actions"):
        with session_for(isolated_connection) as session:
            first[stage] = pilot_run.materialize(session, stage, pilot_run.as_of(manifest))
        assert first[stage]["failures"] == 0
    assert first["signals"]["results"] == {"DETECTED": 1, "INCONCLUSIVE": 18, "STALE": 1}
    assert first["state"]["signal_recomputation_identical"] is True
    assert first["decisions"]["results"] == {"ABSTAIN": 18, "ENGAGE": 1, "HOLD": 1}
    assert first["policies"]["results"] == {"BLOCK": 19, "REQUIRE_REVIEW": 1}
    assert first["actions"]["results"] == {"REQUEST_RESEARCH": 1}
    with session_for(isolated_connection) as session:
        first_trace = pilot_run.export_trace(session, manifest, ledger)
        first_fingerprint = first_trace["fingerprint"]["sha256"]
        base = first_trace["summaries"]["BASE_SAMPLE"]
        coverage = first_trace["summaries"]["TRACE_COVERAGE"]
        assert base["signal"] == {"DETECTED": 1, "INCONCLUSIVE": 17}
        assert coverage["signal"] == {"INCONCLUSIVE": 1, "STALE": 1}
        assert base["action"] == {"NONE": 17, "REQUEST_RESEARCH": 1}
        assert coverage["action"] == {"NONE": 2}
        assert all(
            x["state"]["relationship"] == "UNKNOWN"
            for group in first_trace["cohorts"].values()
            for x in group
        )
        assert all(
            x["decision"]["result"] != "NO_ACTION"
            for group in first_trace["cohorts"].values()
            for x in group
        )
        assert all(
            x["policy"]["result"] != "ALLOW"
            for group in first_trace["cohorts"].values()
            for x in group
        )
        consensus = next(
            x for x in first_trace["cohorts"]["BASE_SAMPLE"] if x["domain"] == "goconsensus.com"
        )
        assert consensus["action"]["type"] == "REQUEST_RESEARCH"
        assert consensus["signal"]["result"] == "DETECTED"
        assert consensus["action"]["policy_evaluation_id"] == consensus["policy"]["id"]
        assert consensus["policy"]["decision_evaluation_id"] == consensus["decision"]["id"]
        assert consensus["decision"]["state_snapshot_id"] == consensus["state"]["id"]
        assert consensus["state"]["signal_evaluation_ids"] == [consensus["signal"]["id"]]
        leader_fact = next(
            x
            for x in consensus["evidence"]
            if x["fact_key"] == "commercial_event.new_revenue_leader"
        )
        assert leader_fact["evidence_id"] in consensus["signal"]["evidence_ids"]
        assert leader_fact["source_observation_id"]
        assert leader_fact["normalization_result_id"]
        assert any(
            x["fact_key"] == "commercial_event.new_revenue_leader" and x["source_observation_id"]
            for x in consensus["evidence"]
        )
        assert (
            session.scalar(
                select(func.count())
                .select_from(ActionAttempt)
                .join(Action, Action.action_id == ActionAttempt.action_id)
                .where(Action.workspace_id == test_workspace)
            )
            == 0
        )
        assert (
            session.scalar(
                select(func.count())
                .select_from(ActionOutcome)
                .join(Action, Action.action_id == ActionOutcome.action_id)
                .where(Action.workspace_id == test_workspace)
            )
            == 0
        )
        assert (
            session.scalar(
                select(func.count())
                .select_from(Account)
                .where(Account.workspace_id == DEMO_WORKSPACE_ID)
            )
            == northstar_before
        )
    for stage in ("signals", "state", "decisions", "policies", "actions"):
        with session_for(isolated_connection) as session:
            replay = pilot_run.materialize(session, stage, pilot_run.as_of(manifest))
        assert replay["output_ids"] == first[stage]["output_ids"]
        assert replay["created"] == 0
    with session_for(isolated_connection) as session:
        assert (
            pilot_run.fingerprint(session, pilot_run.as_of(manifest))["sha256"] == first_fingerprint
        )
    with session_for(isolated_connection) as session:
        (tmp_path / "acceptance.v1.json").write_text(json.dumps({**accepted, "account_count": 19}))
        with pytest.raises(ValueError, match="does not match"):
            pilot_run.verify_acceptance(session, tmp_path, manifest, manifest_hash, ledger)
