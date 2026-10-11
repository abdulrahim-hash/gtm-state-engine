"""PostgreSQL M5A intent, authority, read-back, and immutable provenance tests."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from collections.abc import Iterator, Mapping
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Event
from time import sleep
from typing import cast
from urllib.request import Request
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import Connection
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from gtm_state_api import m2c_run, m2c_workspace, m5a_execution, private_company_read
from gtm_state_api.action_workflow import create_action_review
from gtm_state_api.database import get_engine
from gtm_state_api.hubspot_company_read import CompanyRead, CompanyRecord
from gtm_state_api.hubspot_task import TaskFields, TaskReadResult, create_task_once
from gtm_state_api.m5a_api import get_execution
from gtm_state_api.m5a_execution import (
    ExecutionGateError,
    authorize_plan,
    claim_dispatch,
    create_intent,
    create_plan,
    expire_in_flight,
    preflight,
    record_reconciliation,
    record_write_result,
    validate_plan,
)
from gtm_state_api.models import (
    AccountStateSnapshot,
    Action,
    Evidence,
    ExecutionAttempt,
    ExecutionPlan,
    OperationalOutcome,
    PolicyEvaluation,
    StateSnapshotEvidence,
)
from gtm_state_api.private_company_read import CustomerStageMapping, read_company_into_evidence
from gtm_state_api.types import (
    AccountStateFacet,
    ActionActorKind,
    ActionReviewReasonCode,
    ActionReviewResolution,
    EvidenceAssertion,
    EvidenceClassification,
    EvidenceFreshness,
)

pytestmark = pytest.mark.integration


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


def prepared(
    connection: Connection,
    monkeypatch: pytest.MonkeyPatch,
    *,
    history: bool = False,
) -> tuple[UUID, UUID, datetime, UUID]:
    start = datetime.now(UTC) - timedelta(minutes=3)
    observed = start + timedelta(minutes=1)
    as_of = start + timedelta(minutes=2)
    workspace = uuid4()
    strategy = uuid4()
    slug = f"m5a-test-{str(workspace)[:8]}"
    for module in (m2c_workspace, private_company_read):
        monkeypatch.setattr(module, "WORKSPACE_SLUG", slug)
    monkeypatch.setattr(m2c_workspace, "WORKSPACE_ID", workspace)
    monkeypatch.setattr(m2c_workspace, "STRATEGY_ID", strategy)
    monkeypatch.setattr(m2c_run, "WORKSPACE_ID", workspace)
    monkeypatch.setattr(m2c_run, "STRATEGY_ID", strategy)
    monkeypatch.setattr(m5a_execution, "WORKSPACE_ID", workspace)
    with session_for(connection) as session:
        m2c_workspace.setup(session, fixture_as_of=start)
    runs = []
    if history:
        expired_at = observed - timedelta(days=3)
        historical = CompanyRecord(
            provider_company_id="123",
            company_name="M2C Customer Test",
            company_domain="m2c-customer.example.com",
            lifecycle_stage="customer",
            provider_updated_at=expired_at,
        )

        def historical_reader(company_id: str, *, credential: str) -> CompanyRead:
            assert company_id == "123" and credential == "fixture-token"
            return CompanyRead(historical, 0, None)

        with session_for(connection) as session:
            runs.append(
                read_company_into_evidence(
                    session,
                    workspace_id=workspace,
                    portal_id="12345",
                    company_id="123",
                    credential="fixture-token",
                    mapping=CustomerStageMapping("customer", "1.0.0"),
                    observed_at=expired_at,
                    reader=historical_reader,
                )
            )
    for company_id, stage, name, domain in (
        ("123", "customer", "M2C Customer Test", "m2c-customer.example.com"),
        ("456", "lead", "M2C Lead Test", "m2c-lead.example.com"),
    ):
        record = CompanyRecord(
            provider_company_id=company_id,
            company_name=name,
            company_domain=domain,
            lifecycle_stage=stage,
            provider_updated_at=start,
        )

        def reader(
            requested: str, *, credential: str, fixed: CompanyRecord = record
        ) -> CompanyRead:
            assert requested == fixed.provider_company_id and credential == "fixture-token"
            return CompanyRead(fixed, 0, None)

        with session_for(connection) as session:
            runs.append(
                read_company_into_evidence(
                    session,
                    workspace_id=workspace,
                    portal_id="12345",
                    company_id=company_id,
                    credential="fixture-token",
                    mapping=CustomerStageMapping("customer", "1.0.0"),
                    observed_at=observed,
                    reader=reader,
                )
            )
    for stage in ("signals", "state", "decisions", "policies", "actions"):
        with session_for(connection) as session:
            m2c_run.materialize_stage(
                session, stage=stage, as_of=as_of, inspected_run_ids=tuple(runs)
            )
    with session_for(connection) as session:
        actions = session.scalars(select(Action).where(Action.workspace_id == workspace)).all()
        customer_action = next(a for a in actions if a.action_type.value == "CREATE_SELLER_TASK")
        lead_action = next(a for a in actions if a.action_type.value == "REQUEST_RESEARCH")
        customer_action_id = customer_action.action_id
        lead_action_id = lead_action.action_id
        create_action_review(
            session,
            customer_action.action_id,
            resolution=ActionReviewResolution.APPROVED,
            reason_code=ActionReviewReasonCode.APPROVED_AS_PROPOSED,
            idempotency_key=f"m5a-review-{customer_action.action_id}",
            reviewer_kind=ActionActorKind.UNVERIFIED_DEMO_HUMAN,
            reviewer_ref="local-fixture",
            reviewed_at=datetime.now(UTC),
        )
        session.commit()
    return customer_action_id, lead_action_id, datetime.now(UTC), workspace


def plan_for(session: Session, action_id: UUID, now: datetime) -> ExecutionPlan:
    return create_plan(
        session,
        action_id,
        portal_id="12345",
        company_id="123",
        owner_id="789",
        association_type_id=192,
        due_at=now + timedelta(hours=2),
        now=now,
    )


def snapshot_for_action(session: Session, action_id: UUID) -> AccountStateSnapshot:
    action = session.get(Action, action_id)
    assert action is not None
    policy = session.get(PolicyEvaluation, action.policy_evaluation_id)
    assert policy is not None
    snapshot = session.get(AccountStateSnapshot, policy.state_snapshot_id)
    assert snapshot is not None
    return snapshot


def add_customer_observation(
    connection: Connection, *, workspace: UUID, stage: str, observed_at: datetime
) -> None:
    record = CompanyRecord(
        provider_company_id="123",
        company_name="M2C Customer Test",
        company_domain="m2c-customer.example.com",
        lifecycle_stage=stage,
        provider_updated_at=observed_at,
    )

    def reader(company_id: str, *, credential: str) -> CompanyRead:
        assert company_id == "123" and credential == "fixture-token"
        return CompanyRead(record, 0, None)

    with session_for(connection) as session:
        read_company_into_evidence(
            session,
            workspace_id=workspace,
            portal_id="12345",
            company_id="123",
            credential="fixture-token",
            mapping=CustomerStageMapping("customer", "1.0.0"),
            observed_at=observed_at,
            reader=reader,
        )


def link_relationship_evidence(
    session: Session, snapshot: AccountStateSnapshot, evidence: Evidence
) -> None:
    session.add(
        StateSnapshotEvidence(
            state_snapshot_id=snapshot.state_snapshot_id,
            evidence_id=evidence.id,
            facet=AccountStateFacet.RELATIONSHIP_STATE,
            account_id=snapshot.account_id,
            fit_criterion_id=None,
        )
    )
    session.flush()


def competing_relationship_evidence(
    *, account_id: UUID, observed_at: datetime, ingested_at: datetime
) -> Evidence:
    return Evidence(
        id=uuid4(),
        account_id=account_id,
        classification=EvidenceClassification.FACT,
        source_provider="synthetic-test",
        source_reference="same-time competing relationship observation",
        source_uri=None,
        observed_at=observed_at,
        ingested_at=ingested_at,
        normalized_fact="synthetic competing observation",
        raw_payload_hash="a" * 64,
        freshness=EvidenceFreshness.UNKNOWN,
        fact_key="relationship.crm_reports_customer_status",
        fact_assertion=EvidenceAssertion.PRESENT,
    )


def test_historical_relationship_provenance_selects_fresh_effective_evidence(
    isolated_connection: Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    action_id, _, now, _ = prepared(isolated_connection, monkeypatch, history=True)
    with session_for(isolated_connection) as session:
        snapshot = snapshot_for_action(session, action_id)
        linked = session.scalars(
            select(Evidence)
            .join(StateSnapshotEvidence, StateSnapshotEvidence.evidence_id == Evidence.id)
            .where(
                StateSnapshotEvidence.state_snapshot_id == snapshot.state_snapshot_id,
                StateSnapshotEvidence.facet == AccountStateFacet.RELATIONSHIP_STATE,
            )
            .order_by(Evidence.observed_at)
        ).all()
        assert len(linked) == 2
        assert now - linked[0].observed_at > timedelta(hours=24)
        plan = plan_for(session, action_id, now)
        validate_plan(plan)
        assert m5a_execution.execution_trace(session, plan.id)["relationship_evidence_id"] == str(
            linked[1].id
        )
        trace = m2c_run.export_trace(session, as_of=snapshot.state_as_of)
        customer = next(
            item for item in trace["accounts"] if item["account_id"] == str(snapshot.account_id)
        )
        assert {item["evidence_id"] for item in customer["relationship_evidence"]} == {
            str(item.id) for item in linked
        }
        assert {item["freshness_at_as_of"] for item in customer["relationship_evidence"]} == {
            "EXPIRED",
            "WITHIN_24_HOURS",
        }


def test_fresh_inconclusive_latest_link_blocks_historical_positive(
    isolated_connection: Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    action_id, _, now, workspace = prepared(isolated_connection, monkeypatch, history=True)
    with session_for(isolated_connection) as session:
        snapshot = snapshot_for_action(session, action_id)
        later = snapshot.state_as_of - timedelta(seconds=1)
        account_id = snapshot.account_id
        snapshot_id = snapshot.state_snapshot_id
    add_customer_observation(
        isolated_connection, workspace=workspace, stage="lead", observed_at=later
    )
    with session_for(isolated_connection) as session:
        loaded_snapshot = session.get(AccountStateSnapshot, snapshot_id)
        assert loaded_snapshot is not None
        inconclusive = session.scalar(
            select(Evidence).where(
                Evidence.account_id == account_id,
                Evidence.observed_at == later,
                Evidence.fact_assertion == EvidenceAssertion.INCONCLUSIVE,
            )
        )
        assert inconclusive is not None and inconclusive.normalization_result_id is not None
        link_relationship_evidence(session, loaded_snapshot, inconclusive)
        with pytest.raises(ExecutionGateError, match="RELATIONSHIP_EVIDENCE_INVALID"):
            plan_for(session, action_id, now)
        assert (
            session.scalar(select(ExecutionPlan.id).where(ExecutionPlan.action_id == action_id))
            is None
        )


def test_equal_latest_relationship_links_are_ambiguous(
    isolated_connection: Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    action_id, _, now, _ = prepared(isolated_connection, monkeypatch, history=True)
    with session_for(isolated_connection) as session:
        snapshot = snapshot_for_action(session, action_id)
        selected = session.scalar(
            select(Evidence)
            .join(StateSnapshotEvidence, StateSnapshotEvidence.evidence_id == Evidence.id)
            .where(
                StateSnapshotEvidence.state_snapshot_id == snapshot.state_snapshot_id,
                StateSnapshotEvidence.facet == AccountStateFacet.RELATIONSHIP_STATE,
            )
            .order_by(Evidence.observed_at.desc())
        )
        assert selected is not None
        competing = competing_relationship_evidence(
            account_id=snapshot.account_id, observed_at=selected.observed_at, ingested_at=now
        )
        session.add(competing)
        session.flush()
        link_relationship_evidence(session, snapshot, competing)
        with pytest.raises(ExecutionGateError, match="RELATIONSHIP_TRACE_AMBIGUOUS"):
            plan_for(session, action_id, now)
        assert (
            session.scalar(select(ExecutionPlan.id).where(ExecutionPlan.action_id == action_id))
            is None
        )


def test_equal_canonical_relationship_evidence_outside_snapshot_blocks(
    isolated_connection: Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    action_id, _, now, _ = prepared(isolated_connection, monkeypatch, history=True)
    with session_for(isolated_connection) as session:
        snapshot = snapshot_for_action(session, action_id)
        latest_at = session.scalar(
            select(Evidence.observed_at)
            .join(StateSnapshotEvidence, StateSnapshotEvidence.evidence_id == Evidence.id)
            .where(
                StateSnapshotEvidence.state_snapshot_id == snapshot.state_snapshot_id,
                StateSnapshotEvidence.facet == AccountStateFacet.RELATIONSHIP_STATE,
            )
            .order_by(Evidence.observed_at.desc())
        )
        assert latest_at is not None
        session.add(
            competing_relationship_evidence(
                account_id=snapshot.account_id, observed_at=latest_at, ingested_at=now
            )
        )
        session.flush()
        with pytest.raises(ExecutionGateError, match="NEWER_RELATIONSHIP_EVIDENCE"):
            plan_for(session, action_id, now)
        assert (
            session.scalar(select(ExecutionPlan.id).where(ExecutionPlan.action_id == action_id))
            is None
        )


def test_latest_link_stale_at_execution_with_historical_provenance(
    isolated_connection: Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    action_id, _, _, _ = prepared(isolated_connection, monkeypatch, history=True)
    with session_for(isolated_connection) as session:
        snapshot = snapshot_for_action(session, action_id)
        latest_at = session.scalar(
            select(Evidence.observed_at)
            .join(StateSnapshotEvidence, StateSnapshotEvidence.evidence_id == Evidence.id)
            .where(
                StateSnapshotEvidence.state_snapshot_id == snapshot.state_snapshot_id,
                StateSnapshotEvidence.facet == AccountStateFacet.RELATIONSHIP_STATE,
            )
            .order_by(Evidence.observed_at.desc())
        )
        assert latest_at is not None
        with pytest.raises(ExecutionGateError, match="RELATIONSHIP_STALE"):
            plan_for(session, action_id, latest_at + timedelta(hours=24, microseconds=1))
        assert (
            session.scalar(select(ExecutionPlan.id).where(ExecutionPlan.action_id == action_id))
            is None
        )


def test_exact_chain_review_plan_and_lead_block(
    isolated_connection: Connection,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    action_id, lead_id, now, _ = prepared(isolated_connection, monkeypatch)
    with session_for(isolated_connection) as session:
        plan = plan_for(session, action_id, now)
        validate_plan(plan)
        trace = get_execution(plan.id, session)
        assert trace.action_type == "CREATE_SELLER_TASK"
        assert trace.synthetic is True
        assert trace.reviewed is True
        assert plan.task_fields["hs_task_status"] == "NOT_STARTED"
        assert plan.marker in plan.task_fields["hs_task_body"]
        assert plan_for(session, action_id, now).id == plan.id
        with pytest.raises(ExecutionGateError, match="WRONG_ACTION_TYPE"):
            plan_for(session, lead_id, now)
        with pytest.raises(ExecutionGateError, match="RELATIONSHIP_STALE"):
            create_plan(
                session,
                action_id,
                portal_id="12345",
                company_id="123",
                owner_id="789",
                association_type_id=192,
                due_at=now + timedelta(days=2),
                now=now + timedelta(days=1, minutes=1),
            )
        authorize_plan(
            session,
            plan.id,
            operator_ref="local-fixture",
            now=now,
            expires_at=now + timedelta(minutes=30),
        )
        create_intent(session, plan.id, now=now)
        changed_plan = create_plan(
            session,
            action_id,
            portal_id="12345",
            company_id="123",
            owner_id="789",
            association_type_id=192,
            due_at=now + timedelta(hours=3),
            now=now,
        )
        assert changed_plan.id != plan.id
        authorize_plan(
            session,
            changed_plan.id,
            operator_ref="local-fixture",
            now=now,
            expires_at=now + timedelta(minutes=30),
        )
        with pytest.raises(ExecutionGateError, match="ACTION_ALREADY_HAS_EXECUTION_INTENT"):
            create_intent(session, changed_plan.id, now=now)
        session.commit()


def test_single_dispatch_receipt_and_confirmed_operational_outcome(
    isolated_connection: Connection,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    action_id, _, now, _ = prepared(isolated_connection, monkeypatch)
    with session_for(isolated_connection) as session:
        plan = plan_for(session, action_id, now)
        auth = authorize_plan(
            session,
            plan.id,
            operator_ref="local-fixture",
            now=now,
            expires_at=now + timedelta(minutes=30),
        )
        assert auth.assurance_type == "LOCAL_OPERATOR_ATTESTATION"
        attempt = create_intent(session, plan.id, now=now)
        assert attempt.status == "NOT_ATTEMPTED" and attempt.physical_post_count == 0
        session.commit()
        preflight(session, plan.id, portal_id="12345", company_id="123", owner_id="789", now=now)
        claimed = claim_dispatch(
            session, plan.id, portal_id="12345", company_id="123", owner_id="789", now=now
        )
        session.commit()
        assert claimed.status == "IN_FLIGHT" and claimed.physical_post_count == 1
        with pytest.raises(ExecutionGateError, match="ATTEMPT_NOT_DISPATCHABLE"):
            claim_dispatch(
                session, plan.id, portal_id="12345", company_id="123", owner_id="789", now=now
            )
        receipt = record_write_result(
            session,
            attempt.id,
            task_id="321",
            correlation="fixture-correlation",
            provider_timestamp=now,
            response_projection={"id": "321", "http": "201"},
            result_code="201_CREATED",
            now=now,
        )
        assert receipt is not None and receipt.provider_object_id == "321"
        session.commit()
        read_fields = cast(dict[str, str | None], dict(plan.task_fields))
        read_fields["hs_timestamp"] = str(
            int(
                datetime.fromisoformat(
                    plan.task_fields["hs_timestamp"].replace("Z", "+00:00")
                ).timestamp()
                * 1000
            )
        )
        task = TaskReadResult("321", False, read_fields, ("123",), "fixture-correlation")
        result = record_reconciliation(
            session,
            attempt.id,
            task=task,
            marker_match_count=1,
            lookup_complete=True,
            read_count=2,
            read_error=False,
            now=now,
        )
        assert result.result == "CONFIRMED"
        outcome = session.scalar(
            select(OperationalOutcome).where(OperationalOutcome.execution_attempt_id == attempt.id)
        )
        assert outcome is not None and outcome.reason_code == "CRM_TASK_CONFIRMED_CREATED"
        session.commit()


def test_unknown_delivery_and_immutable_history(
    isolated_connection: Connection,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    action_id, _, now, _ = prepared(isolated_connection, monkeypatch)
    with session_for(isolated_connection) as session:
        plan = plan_for(session, action_id, now)
        authorize_plan(
            session,
            plan.id,
            operator_ref="local-fixture",
            now=now,
            expires_at=now + timedelta(minutes=30),
        )
        attempt = create_intent(session, plan.id, now=now)
        session.commit()
        claim_dispatch(
            session, plan.id, portal_id="12345", company_id="123", owner_id="789", now=now
        )
        session.commit()
        expire_in_flight(session, attempt.id, now=now + timedelta(minutes=3))
        session.commit()
        stored_attempt = session.get(ExecutionAttempt, attempt.id)
        assert stored_attempt is not None and stored_attempt.status == "UNKNOWN_DELIVERY"
        with pytest.raises(ExecutionGateError, match="ATTEMPT_NOT_DISPATCHABLE"):
            claim_dispatch(
                session,
                plan.id,
                portal_id="12345",
                company_id="123",
                owner_id="789",
                now=now + timedelta(minutes=3),
            )
        unknown = record_reconciliation(
            session,
            attempt.id,
            task=None,
            marker_match_count=0,
            lookup_complete=True,
            read_count=1,
            read_error=False,
            now=now + timedelta(minutes=3),
        )
        assert unknown.result == "NOT_FOUND"
        assert (
            session.scalar(
                select(OperationalOutcome).where(
                    OperationalOutcome.execution_attempt_id == attempt.id
                )
            )
            is None
        )
        session.commit()
        with pytest.raises(DBAPIError):
            plan.provider_owner_id = "999"
            session.flush()
        session.rollback()


def test_crash_after_possible_post_recovers_by_read_without_second_dispatch(
    isolated_connection: Connection,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    action_id, _, now, _ = prepared(isolated_connection, monkeypatch)
    with session_for(isolated_connection) as session:
        plan = plan_for(session, action_id, now)
        authorize_plan(
            session,
            plan.id,
            operator_ref="local-fixture",
            now=now,
            expires_at=now + timedelta(minutes=30),
        )
        attempt = create_intent(session, plan.id, now=now)
        session.commit()
        claim_dispatch(
            session, plan.id, portal_id="12345", company_id="123", owner_id="789", now=now
        )
        session.commit()
        # Simulate a Task created by HubSpot and process death before its ID was persisted.
        expire_in_flight(session, attempt.id, now=now + timedelta(minutes=3))
        session.commit()
        recovered_task = TaskReadResult(
            "321",
            False,
            cast(dict[str, str | None], plan.task_fields),
            ("123",),
            None,
        )
        result = record_reconciliation(
            session,
            attempt.id,
            task=recovered_task,
            marker_match_count=1,
            lookup_complete=True,
            read_count=2,
            read_error=False,
            now=now + timedelta(minutes=3),
        )
        session.commit()
        assert result.result == "CONFIRMED"
        assert (
            session.scalar(
                select(OperationalOutcome).where(
                    OperationalOutcome.execution_attempt_id == attempt.id
                )
            )
            is not None
        )
        with pytest.raises(ExecutionGateError, match="ATTEMPT_NOT_DISPATCHABLE"):
            claim_dispatch(
                session,
                plan.id,
                portal_id="12345",
                company_id="123",
                owner_id="789",
                now=now + timedelta(minutes=3),
            )


def test_mismatched_owner_never_materializes_operational_outcome(
    isolated_connection: Connection,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    action_id, _, now, _ = prepared(isolated_connection, monkeypatch)
    with session_for(isolated_connection) as session:
        plan = plan_for(session, action_id, now)
        authorize_plan(
            session,
            plan.id,
            operator_ref="local-fixture",
            now=now,
            expires_at=now + timedelta(minutes=30),
        )
        attempt = create_intent(session, plan.id, now=now)
        session.commit()
        claim_dispatch(
            session, plan.id, portal_id="12345", company_id="123", owner_id="789", now=now
        )
        session.commit()
        record_write_result(
            session,
            attempt.id,
            task_id="321",
            correlation=None,
            provider_timestamp=None,
            response_projection={"id": "321"},
            result_code="201_CREATED",
            now=now,
        )
        session.commit()
        wrong_fields = dict(plan.task_fields)
        wrong_fields["hubspot_owner_id"] = "999"
        task = TaskReadResult(
            "321",
            False,
            cast(dict[str, str | None], wrong_fields),
            ("123",),
            None,
        )
        reconciliation = record_reconciliation(
            session,
            attempt.id,
            task=task,
            marker_match_count=1,
            lookup_complete=True,
            read_count=2,
            read_error=False,
            now=now,
        )
        assert reconciliation.result == "MISMATCH"
        assert reconciliation.reason_code == "TASK_FIELDS_MISMATCH"
        assert (
            session.scalar(
                select(OperationalOutcome).where(
                    OperationalOutcome.execution_attempt_id == attempt.id
                )
            )
            is None
        )
        session.commit()


def test_provider_id_then_receipt_persistence_failure_recovers_without_repost(
    isolated_connection: Connection,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    action_id, _, now, _ = prepared(isolated_connection, monkeypatch)
    with session_for(isolated_connection) as session:
        plan = plan_for(session, action_id, now)
        authorize_plan(
            session,
            plan.id,
            operator_ref="local-fixture",
            now=now,
            expires_at=now + timedelta(minutes=30),
        )
        attempt = create_intent(session, plan.id, now=now)
        session.commit()
        claim_dispatch(
            session, plan.id, portal_id="12345", company_id="123", owner_id="789", now=now
        )
        session.commit()
        attempt_id = attempt.id
        plan_id = plan.id
        task_fields = dict(plan.task_fields)
        calls = 0

        def transport(_request: Request) -> tuple[int, bytes, Mapping[str, str]]:
            nonlocal calls
            calls += 1
            return 201, json.dumps({"id": "321"}).encode(), {}

        written = create_task_once(
            credential="fixture-token",
            fields=TaskFields(
                due_at=task_fields["hs_timestamp"],
                subject=task_fields["hs_task_subject"],
                body=task_fields["hs_task_body"],
                owner_id=task_fields["hubspot_owner_id"],
            ),
            company_id="123",
            association_type_id=192,
            transport=transport,
        )
        assert written.task_id == "321" and calls == 1

        def fail_receipt_flush() -> None:
            raise RuntimeError("injected receipt persistence failure")

        with monkeypatch.context() as patch:
            patch.setattr(session, "flush", fail_receipt_flush)
            with pytest.raises(RuntimeError, match="injected receipt persistence failure"):
                record_write_result(
                    session,
                    attempt_id,
                    task_id=written.task_id,
                    correlation=None,
                    provider_timestamp=None,
                    response_projection=written.response_projection,
                    result_code="201_CREATED",
                    now=now,
                )
        session.rollback()
    with session_for(isolated_connection) as session:
        stored = session.get(ExecutionAttempt, attempt_id)
        assert stored is not None and stored.status == "IN_FLIGHT"
        expire_in_flight(session, attempt_id, now=now + timedelta(minutes=3))
        session.commit()
        recovered = TaskReadResult(
            "321",
            False,
            cast(dict[str, str | None], task_fields),
            ("123",),
            None,
        )
        result = record_reconciliation(
            session,
            attempt_id,
            task=recovered,
            marker_match_count=1,
            lookup_complete=True,
            read_count=2,
            read_error=False,
            now=now + timedelta(minutes=3),
        )
        session.commit()
        assert result.result == "CONFIRMED"
        assert calls == 1
        with pytest.raises(ExecutionGateError, match="ATTEMPT_NOT_DISPATCHABLE"):
            claim_dispatch(
                session,
                plan_id,
                portal_id="12345",
                company_id="123",
                owner_id="789",
                now=now + timedelta(minutes=3),
            )


def test_wrong_portal_owner_and_expired_authority_block_dispatch(
    isolated_connection: Connection,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    action_id, _, now, _ = prepared(isolated_connection, monkeypatch)
    with session_for(isolated_connection) as session:
        plan = plan_for(session, action_id, now)
        authorize_plan(
            session,
            plan.id,
            operator_ref="local-fixture",
            now=now,
            expires_at=now + timedelta(minutes=5),
        )
        create_intent(session, plan.id, now=now)
        session.commit()
        with pytest.raises(ExecutionGateError, match="PORTAL_MISMATCH"):
            preflight(
                session, plan.id, portal_id="99999", company_id="123", owner_id="789", now=now
            )
        with pytest.raises(ExecutionGateError, match="TARGET_MISMATCH"):
            preflight(
                session, plan.id, portal_id="12345", company_id="123", owner_id="999", now=now
            )
        with pytest.raises(ExecutionGateError, match="AUTH_INVALID"):
            preflight(
                session,
                plan.id,
                portal_id="12345",
                company_id="123",
                owner_id="789",
                now=now + timedelta(minutes=6),
            )


def test_newer_conflicting_relationship_evidence_blocks_old_action(
    isolated_connection: Connection,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    action_id, _, now, workspace = prepared(isolated_connection, monkeypatch, history=True)
    later = now + timedelta(seconds=1)
    changed = CompanyRecord(
        provider_company_id="123",
        company_name="M2C Customer Test",
        company_domain="m2c-customer.example.com",
        lifecycle_stage="lead",
        provider_updated_at=later,
    )

    def reader(company_id: str, *, credential: str) -> CompanyRead:
        assert company_id == "123" and credential == "fixture-token"
        return CompanyRead(changed, 0, None)

    with session_for(isolated_connection) as session:
        read_company_into_evidence(
            session,
            workspace_id=workspace,
            portal_id="12345",
            company_id="123",
            credential="fixture-token",
            mapping=CustomerStageMapping("customer", "1.0.0"),
            observed_at=later,
            reader=reader,
        )
    with (
        session_for(isolated_connection) as session,
        pytest.raises(ExecutionGateError, match="NEWER_RELATIONSHIP_EVIDENCE"),
    ):
        plan_for(session, action_id, now + timedelta(seconds=2))


def test_two_database_transactions_cannot_both_claim_one_post(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Use a disposable PostgreSQL database for a real two-connection race."""

    name = f"gtm_state_m5a_race_{uuid4().hex[:12]}"
    assert name.startswith("gtm_state_m5a_race_") and name.replace("_", "").isalnum()
    api_root = Path(__file__).resolve().parents[2]
    target_url = get_engine().url.set(database=name)
    with get_engine().connect().execution_options(isolation_level="AUTOCOMMIT") as admin:
        admin.execute(text(f"CREATE DATABASE {name}"))
    engine = create_engine(target_url, pool_pre_ping=True)
    try:
        env = os.environ.copy()
        env["DATABASE_URL"] = target_url.render_as_string(hide_password=False)
        migrated = subprocess.run(
            [
                sys.executable,
                "-m",
                "alembic",
                "-c",
                str(api_root / "alembic.ini"),
                "upgrade",
                "head",
            ],
            cwd=api_root,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        assert migrated.returncode == 0, migrated.stderr
        with engine.connect() as connection:
            setup_transaction = connection.begin()
            action_id, _, now, _ = prepared(connection, monkeypatch)
            with session_for(connection) as session:
                plan = plan_for(session, action_id, now)
                authorize_plan(
                    session,
                    plan.id,
                    operator_ref="local-fixture",
                    now=now,
                    expires_at=now + timedelta(minutes=30),
                )
                attempt = create_intent(session, plan.id, now=now)
                plan_id, attempt_id = plan.id, attempt.id
                session.commit()
            setup_transaction.commit()
        first_claimed = Event()

        def first() -> str:
            with Session(engine) as session:
                claim_dispatch(
                    session, plan_id, portal_id="12345", company_id="123", owner_id="789", now=now
                )
                first_claimed.set()
                sleep(0.2)
                session.commit()
                return "claimed"

        def second() -> str:
            assert first_claimed.wait(timeout=5)
            with Session(engine) as session:
                try:
                    claim_dispatch(
                        session,
                        plan_id,
                        portal_id="12345",
                        company_id="123",
                        owner_id="789",
                        now=now,
                    )
                except ExecutionGateError as exc:
                    return str(exc)
                return "unexpected-second-claim"

        with ThreadPoolExecutor(max_workers=2) as pool:
            first_result = pool.submit(first)
            second_result = pool.submit(second)
            assert first_result.result(timeout=10) == "claimed"
            assert second_result.result(timeout=10) == "ATTEMPT_NOT_DISPATCHABLE"
        with Session(engine) as session:
            stored = session.get(ExecutionAttempt, attempt_id)
            assert stored is not None and stored.physical_post_count == 1
            assert stored.status == "IN_FLIGHT"
        refused = subprocess.run(
            [
                sys.executable,
                "-m",
                "alembic",
                "-c",
                str(api_root / "alembic.ini"),
                "downgrade",
                "20261005_0008",
            ],
            cwd=api_root,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        assert refused.returncode != 0
        assert "M5A execution history exists" in refused.stderr
    finally:
        engine.dispose()
        with get_engine().connect().execution_options(isolation_level="AUTOCOMMIT") as admin:
            admin.execute(text(f"DROP DATABASE {name} WITH (FORCE)"))
