"""PostgreSQL integration tests for deterministic M1C Decision and Policy."""

from datetime import datetime, timedelta
from typing import cast
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from gtm_state_api import decision_engine
from gtm_state_api.database import get_session, get_session_factory
from gtm_state_api.decision_engine import (
    evaluate_decision_v1,
    evaluate_policy_v1,
    materialize_decision_evaluation,
    materialize_policy_evaluation,
    materialize_snapshot_disposition,
)
from gtm_state_api.demo_seed import (
    DECISION_DEFINITION_ID,
    DEMO_ACCOUNTS,
    DEMO_AS_OF,
    DEMO_EVALUATED_AT,
    POLICY_DEFINITION_ID,
    seed_demo,
)
from gtm_state_api.main import app
from gtm_state_api.models import (
    AccountStateSnapshot,
    DecisionDefinition,
    DecisionEvaluation,
    DecisionEvaluationReason,
    Evidence,
    PolicyDefinition,
    PolicyEvaluation,
    PolicyEvaluationReason,
    StateSnapshotEvidence,
    StateSnapshotFitCriterion,
    StateSnapshotReason,
    StateSnapshotSignalEvaluation,
)
from gtm_state_api.state_engine import recompute_workspace_account_states
from gtm_state_api.types import (
    AccountRelationshipState,
    DecisionResult,
    EvaluationDefinitionStatus,
    EvidenceAssertion,
    EvidenceClassification,
    EvidenceFreshness,
    PolicyResult,
    PolicyTarget,
)

pytestmark = pytest.mark.integration


def _new_relationship_evidence(
    *,
    account_id: UUID,
    assertion: EvidenceAssertion,
    observed_at: datetime,
) -> Evidence:
    return Evidence(
        id=uuid4(),
        strategy_version_id=None,
        account_id=account_id,
        strategy_topic=None,
        classification=EvidenceClassification.FACT,
        source_provider="synthetic_test",
        source_reference=f"synthetic://m1c-test/{uuid4()}",
        source_uri=None,
        observed_at=observed_at,
        ingested_at=DEMO_AS_OF,
        normalized_fact="Synthetic test-only explicit relationship assertion.",
        raw_payload_hash=None,
        freshness=EvidenceFreshness.CURRENT,
        confidence=None,
        fact_key="relationship.existing_relationship",
        fact_assertion=assertion,
    )


def _current_snapshot(session: object, account_id: UUID) -> AccountStateSnapshot:
    candidate = session.scalar(  # type: ignore[attr-defined]
        select(AccountStateSnapshot)
        .where(AccountStateSnapshot.account_id == account_id)
        .order_by(AccountStateSnapshot.computed_at.desc())
        .limit(1)
    )
    assert candidate is not None
    return cast(AccountStateSnapshot, candidate)


def test_demo_decision_policy_matrix_and_exact_ordered_reasons() -> None:
    with get_session_factory()() as session:
        seed_demo(session)
        rows = session.execute(
            select(
                DecisionEvaluation.account_id,
                DecisionEvaluation.result,
                PolicyEvaluation.result,
            )
            .join(
                PolicyEvaluation,
                PolicyEvaluation.decision_evaluation_id
                == DecisionEvaluation.decision_evaluation_id,
            )
            .order_by(DecisionEvaluation.account_id)
        ).all()
        matrix = {account_id: (decision, policy) for account_id, decision, policy in rows}

        assert matrix == {
            DEMO_ACCOUNTS[0]["id"]: (DecisionResult.ENGAGE, PolicyResult.REQUIRE_REVIEW),
            DEMO_ACCOUNTS[1]["id"]: (DecisionResult.ABSTAIN, PolicyResult.BLOCK),
            DEMO_ACCOUNTS[2]["id"]: (DecisionResult.ENGAGE, PolicyResult.REQUIRE_REVIEW),
        }

        expected_policy_reasons = {
            DEMO_ACCOUNTS[0]["id"]: [
                "RELATIONSHIP_UNKNOWN_REQUIRES_REVIEW",
                "PARTIAL_EVIDENCE_REQUIRES_REVIEW",
            ],
            DEMO_ACCOUNTS[1]["id"]: [
                "DECISION_DOES_NOT_SUPPORT_ACTIVATION",
                "TIMING_STATE_BLOCKS_ACTIVATION",
                "RELATIONSHIP_UNKNOWN_REQUIRES_REVIEW",
                "PARTIAL_EVIDENCE_REQUIRES_REVIEW",
            ],
            DEMO_ACCOUNTS[2]["id"]: [
                "EXISTING_RELATIONSHIP_REQUIRES_CONTROLLED_HANDLING",
                "PARTIAL_EVIDENCE_REQUIRES_REVIEW",
            ],
        }
        for account_id, expected in expected_policy_reasons.items():
            policy = session.scalar(
                select(PolicyEvaluation).where(PolicyEvaluation.account_id == account_id)
            )
            assert policy is not None
            reasons = session.scalars(
                select(PolicyEvaluationReason)
                .where(PolicyEvaluationReason.policy_evaluation_id == policy.policy_evaluation_id)
                .order_by(PolicyEvaluationReason.position)
            ).all()
            assert [item.reason_code.value for item in reasons] == expected


def test_repeated_seed_preserves_evaluation_identity_and_operational_time() -> None:
    with get_session_factory()() as session:
        seed_demo(session)
        before_decisions = {
            item.decision_evaluation_id: (item.input_hash, item.evaluated_at, item.result)
            for item in session.scalars(select(DecisionEvaluation)).all()
        }
        before_policies = {
            item.policy_evaluation_id: (item.input_hash, item.evaluated_at, item.result)
            for item in session.scalars(select(PolicyEvaluation)).all()
        }

        seed_demo(session)

        after_decisions = {
            item.decision_evaluation_id: (item.input_hash, item.evaluated_at, item.result)
            for item in session.scalars(select(DecisionEvaluation)).all()
        }
        after_policies = {
            item.policy_evaluation_id: (item.input_hash, item.evaluated_at, item.result)
            for item in session.scalars(select(PolicyEvaluation)).all()
        }

    assert after_decisions == before_decisions
    assert after_policies == before_policies
    assert len(after_decisions) == len(after_policies) == 3


def test_relationship_only_snapshot_revision_gets_new_decision_identity() -> None:
    with get_session_factory()() as session:
        seed_demo(session)
        original = session.scalar(
            select(DecisionEvaluation).where(
                DecisionEvaluation.account_id == DEMO_ACCOUNTS[0]["id"]
            )
        )
        assert original is not None
        original_id = original.decision_evaluation_id
        original_snapshot_id = original.state_snapshot_id
        original_snapshot = session.get(AccountStateSnapshot, original_snapshot_id)
        assert original_snapshot is not None
        revised_snapshot = AccountStateSnapshot(
            state_snapshot_id=uuid4(),
            workspace_id=original_snapshot.workspace_id,
            account_id=original_snapshot.account_id,
            strategy_version_id=original_snapshot.strategy_version_id,
            state_as_of=original_snapshot.state_as_of,
            computed_at=DEMO_EVALUATED_AT + timedelta(hours=1),
            input_hash="d" * 64,
            state_engine_version=original_snapshot.state_engine_version,
            fit_context=original_snapshot.fit_context,
            timing_state=original_snapshot.timing_state,
            relationship_state=AccountRelationshipState.NO_EXISTING_RELATIONSHIP,
            evidence_sufficiency=original_snapshot.evidence_sufficiency,
            created_at=DEMO_EVALUATED_AT + timedelta(hours=1),
        )
        session.add(revised_snapshot)
        session.flush()
        revised, policy = materialize_snapshot_disposition(
            session,
            revised_snapshot.state_snapshot_id,
            evaluated_at=DEMO_EVALUATED_AT + timedelta(hours=1),
        )
        values = (
            revised.decision_evaluation_id,
            revised.state_snapshot_id,
            revised.result,
            policy.result,
        )
        session.rollback()

    assert values[0] != original_id
    assert values[1] != original_snapshot_id
    assert values[2] is DecisionResult.ENGAGE
    assert values[3] is PolicyResult.REQUIRE_REVIEW


def test_evaluator_version_changes_create_new_evaluations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with get_session_factory()() as session:
        seed_demo(session)
        snapshot = _current_snapshot(session, DEMO_ACCOUNTS[0]["id"])
        original_decision = session.scalar(
            select(DecisionEvaluation).where(
                DecisionEvaluation.state_snapshot_id == snapshot.state_snapshot_id
            )
        )
        assert original_decision is not None
        original_policy = session.scalar(
            select(PolicyEvaluation).where(
                PolicyEvaluation.decision_evaluation_id == original_decision.decision_evaluation_id
            )
        )
        assert original_policy is not None

        decision_definition_id = uuid4()
        policy_definition_id = uuid4()
        original_decision_definition = session.get(
            DecisionDefinition,
            DECISION_DEFINITION_ID,
        )
        original_policy_definition = session.get(
            PolicyDefinition,
            POLICY_DEFINITION_ID,
        )
        assert original_decision_definition is not None
        assert original_policy_definition is not None
        original_decision_definition.status = EvaluationDefinitionStatus.DISABLED
        original_policy_definition.status = EvaluationDefinitionStatus.DISABLED
        session.flush()
        session.add(
            DecisionDefinition(
                decision_definition_id=decision_definition_id,
                workspace_id=snapshot.workspace_id,
                strategy_version_id=snapshot.strategy_version_id,
                stable_key="test_account_response_v2",
                definition_version="2.0.0",
                display_name="Test Decision version",
                description="Test-only registered evaluator version.",
                evaluator_key="fit_timing_response_matrix",
                evaluator_version="2.0.0-test",
                status=EvaluationDefinitionStatus.ENABLED,
                created_at=DEMO_AS_OF,
            )
        )
        session.add(
            PolicyDefinition(
                policy_definition_id=policy_definition_id,
                workspace_id=snapshot.workspace_id,
                strategy_version_id=snapshot.strategy_version_id,
                stable_key="test_prospecting_guardrails_v2",
                definition_version="2.0.0",
                display_name="Test Policy version",
                description="Test-only registered evaluator version.",
                target=PolicyTarget.PROSPECTING_ACTIVATION,
                evaluator_key="state_and_relationship_gate",
                evaluator_version="2.0.0-test",
                status=EvaluationDefinitionStatus.ENABLED,
                created_at=DEMO_AS_OF,
            )
        )
        session.flush()
        monkeypatch.setattr(
            decision_engine,
            "DECISION_EVALUATOR_REGISTRY",
            {
                **decision_engine.DECISION_EVALUATOR_REGISTRY,
                ("fit_timing_response_matrix", "2.0.0-test"): evaluate_decision_v1,
            },
        )
        monkeypatch.setattr(
            decision_engine,
            "POLICY_EVALUATOR_REGISTRY",
            {
                **decision_engine.POLICY_EVALUATOR_REGISTRY,
                ("state_and_relationship_gate", "2.0.0-test"): evaluate_policy_v1,
            },
        )

        revised_decision = materialize_decision_evaluation(
            session,
            snapshot.state_snapshot_id,
        )
        revised_policy = materialize_policy_evaluation(
            session,
            revised_decision.decision_evaluation_id,
        )
        values = (
            revised_decision.decision_evaluation_id,
            revised_policy.policy_evaluation_id,
            revised_decision.result,
            revised_policy.result,
        )
        original_values = (
            original_decision.decision_evaluation_id,
            original_policy.policy_evaluation_id,
        )
        session.rollback()

    assert values[0] != original_values[0]
    assert values[1] != original_values[1]
    assert values[2] is DecisionResult.ENGAGE
    assert values[3] is PolicyResult.REQUIRE_REVIEW


def test_definition_selection_fails_closed_without_fallback() -> None:
    with get_session_factory()() as session:
        seed_demo(session)
        snapshot = _current_snapshot(session, DEMO_ACCOUNTS[0]["id"])
        decision_definition = session.get(DecisionDefinition, DECISION_DEFINITION_ID)
        assert decision_definition is not None
        decision_definition.status = EvaluationDefinitionStatus.DISABLED
        session.flush()

        with pytest.raises(ValueError, match="exactly one enabled Decision"):
            materialize_decision_evaluation(session, snapshot.state_snapshot_id)
        session.rollback()

    with get_session_factory()() as session:
        seed_demo(session)
        decision = session.scalar(
            select(DecisionEvaluation).where(
                DecisionEvaluation.account_id == DEMO_ACCOUNTS[0]["id"]
            )
        )
        policy_definition = session.get(PolicyDefinition, POLICY_DEFINITION_ID)
        assert decision is not None
        assert policy_definition is not None
        policy_definition.status = EvaluationDefinitionStatus.DISABLED
        session.flush()

        with pytest.raises(ValueError, match="exactly one enabled Policy"):
            materialize_policy_evaluation(session, decision.decision_evaluation_id)
        session.rollback()


def test_database_enforces_at_most_one_enabled_definition_per_scope() -> None:
    with get_session_factory()() as session:
        seed_demo(session)
        snapshot = _current_snapshot(session, DEMO_ACCOUNTS[0]["id"])
        session.add(
            DecisionDefinition(
                decision_definition_id=uuid4(),
                workspace_id=snapshot.workspace_id,
                strategy_version_id=snapshot.strategy_version_id,
                stable_key="second_enabled_test_definition",
                definition_version="1.0.0",
                display_name="Second enabled test definition",
                description="Test-only duplicate enabled definition.",
                evaluator_key="fit_timing_response_matrix",
                evaluator_version="1.0.0",
                status=EvaluationDefinitionStatus.ENABLED,
                created_at=DEMO_AS_OF,
            )
        )
        with pytest.raises(IntegrityError):
            session.flush()
        session.rollback()

    with get_session_factory()() as session:
        seed_demo(session)
        snapshot = _current_snapshot(session, DEMO_ACCOUNTS[0]["id"])
        session.add(
            PolicyDefinition(
                policy_definition_id=uuid4(),
                workspace_id=snapshot.workspace_id,
                strategy_version_id=snapshot.strategy_version_id,
                stable_key="second_enabled_test_policy",
                definition_version="1.0.0",
                display_name="Second enabled test policy",
                description="Test-only duplicate enabled Policy definition.",
                target=PolicyTarget.PROSPECTING_ACTIVATION,
                evaluator_key="state_and_relationship_gate",
                evaluator_version="1.0.0",
                status=EvaluationDefinitionStatus.ENABLED,
                created_at=DEMO_AS_OF,
            )
        )
        with pytest.raises(IntegrityError):
            session.flush()
        session.rollback()


def test_unsupported_evaluator_fails_closed() -> None:
    with get_session_factory()() as session:
        seed_demo(session)
        snapshot = _current_snapshot(session, DEMO_ACCOUNTS[0]["id"])
        original_decision_definition = session.get(
            DecisionDefinition,
            DECISION_DEFINITION_ID,
        )
        assert original_decision_definition is not None
        original_decision_definition.status = EvaluationDefinitionStatus.DISABLED
        session.flush()
        unsupported_id = uuid4()
        session.add(
            DecisionDefinition(
                decision_definition_id=unsupported_id,
                workspace_id=snapshot.workspace_id,
                strategy_version_id=snapshot.strategy_version_id,
                stable_key="unsupported_test_definition",
                definition_version="1.0.0",
                display_name="Unsupported test definition",
                description="Test-only unsupported evaluator.",
                evaluator_key="unsupported_evaluator",
                evaluator_version="1.0.0",
                status=EvaluationDefinitionStatus.ENABLED,
                created_at=DEMO_AS_OF,
            )
        )
        session.flush()

        with pytest.raises(ValueError, match="unsupported evaluator"):
            materialize_decision_evaluation(session, snapshot.state_snapshot_id)
        session.rollback()

    with get_session_factory()() as session:
        seed_demo(session)
        decision = session.scalar(
            select(DecisionEvaluation).where(
                DecisionEvaluation.account_id == DEMO_ACCOUNTS[0]["id"]
            )
        )
        original_policy_definition = session.get(PolicyDefinition, POLICY_DEFINITION_ID)
        assert decision is not None
        assert original_policy_definition is not None
        original_policy_definition.status = EvaluationDefinitionStatus.DISABLED
        session.flush()
        session.add(
            PolicyDefinition(
                policy_definition_id=uuid4(),
                workspace_id=decision.workspace_id,
                strategy_version_id=decision.strategy_version_id,
                stable_key="unsupported_test_policy",
                definition_version="1.0.0",
                display_name="Unsupported test Policy",
                description="Test-only unsupported Policy evaluator.",
                target=PolicyTarget.PROSPECTING_ACTIVATION,
                evaluator_key="unsupported_policy_evaluator",
                evaluator_version="1.0.0",
                status=EvaluationDefinitionStatus.ENABLED,
                created_at=DEMO_AS_OF,
            )
        )
        session.flush()

        with pytest.raises(ValueError, match="unsupported evaluator"):
            materialize_policy_evaluation(session, decision.decision_evaluation_id)
        session.rollback()


def test_policy_database_scope_requires_decision_and_exact_same_snapshot() -> None:
    with get_session_factory()() as session:
        seed_demo(session)
        asterwind = _current_snapshot(session, DEMO_ACCOUNTS[0]["id"])
        cinderlake_decision = session.scalar(
            select(DecisionEvaluation).where(
                DecisionEvaluation.account_id == DEMO_ACCOUNTS[2]["id"]
            )
        )
        assert cinderlake_decision is not None
        test_definition_id = uuid4()
        session.add(
            PolicyDefinition(
                policy_definition_id=test_definition_id,
                workspace_id=asterwind.workspace_id,
                strategy_version_id=asterwind.strategy_version_id,
                stable_key="cross_snapshot_scope_test",
                definition_version="1.0.0",
                display_name="Cross-snapshot scope test",
                description="Test-only exact provenance constraint.",
                target=PolicyTarget.PROSPECTING_ACTIVATION,
                evaluator_key="state_and_relationship_gate",
                evaluator_version="1.0.0",
                status=EvaluationDefinitionStatus.DISABLED,
                created_at=DEMO_AS_OF,
            )
        )
        session.flush()
        session.add(
            PolicyEvaluation(
                policy_evaluation_id=uuid4(),
                workspace_id=asterwind.workspace_id,
                account_id=asterwind.account_id,
                strategy_version_id=asterwind.strategy_version_id,
                state_snapshot_id=asterwind.state_snapshot_id,
                decision_evaluation_id=cinderlake_decision.decision_evaluation_id,
                policy_definition_id=test_definition_id,
                definition_version="1.0.0",
                evaluated_at=DEMO_EVALUATED_AT,
                input_hash="c" * 64,
                result=PolicyResult.BLOCK,
                created_at=DEMO_EVALUATED_AT,
            )
        )
        with pytest.raises(IntegrityError):
            session.flush()
        session.rollback()


def test_m1c_materialization_does_not_mutate_m1b2_rows_or_provenance() -> None:
    with get_session_factory()() as session:
        seed_demo(session)
        snapshot = _current_snapshot(session, DEMO_ACCOUNTS[2]["id"])
        state_before = session.execute(
            select(
                AccountStateSnapshot.state_snapshot_id,
                AccountStateSnapshot.input_hash,
                AccountStateSnapshot.fit_context,
                AccountStateSnapshot.timing_state,
                AccountStateSnapshot.relationship_state,
                AccountStateSnapshot.evidence_sufficiency,
                AccountStateSnapshot.computed_at,
            ).order_by(AccountStateSnapshot.state_snapshot_id)
        ).all()
        provenance_before = (
            session.scalar(select(func.count()).select_from(StateSnapshotReason)),
            session.scalar(select(func.count()).select_from(StateSnapshotFitCriterion)),
            session.scalar(select(func.count()).select_from(StateSnapshotEvidence)),
            session.scalar(select(func.count()).select_from(StateSnapshotSignalEvaluation)),
        )

        materialize_snapshot_disposition(
            session,
            snapshot.state_snapshot_id,
            evaluated_at=DEMO_EVALUATED_AT + timedelta(days=10),
        )

        state_after = session.execute(
            select(
                AccountStateSnapshot.state_snapshot_id,
                AccountStateSnapshot.input_hash,
                AccountStateSnapshot.fit_context,
                AccountStateSnapshot.timing_state,
                AccountStateSnapshot.relationship_state,
                AccountStateSnapshot.evidence_sufficiency,
                AccountStateSnapshot.computed_at,
            ).order_by(AccountStateSnapshot.state_snapshot_id)
        ).all()
        provenance_after = (
            session.scalar(select(func.count()).select_from(StateSnapshotReason)),
            session.scalar(select(func.count()).select_from(StateSnapshotFitCriterion)),
            session.scalar(select(func.count()).select_from(StateSnapshotEvidence)),
            session.scalar(select(func.count()).select_from(StateSnapshotSignalEvaluation)),
        )

    assert state_after == state_before
    assert provenance_after == provenance_before


def test_get_routes_are_side_effect_free_and_methods_are_read_only() -> None:
    with get_session_factory()() as session:
        seed_demo(session)
        before = (
            session.scalar(select(func.count()).select_from(DecisionEvaluation)),
            session.scalar(select(func.count()).select_from(PolicyEvaluation)),
            session.scalar(select(func.count()).select_from(DecisionEvaluationReason)),
            session.scalar(select(func.count()).select_from(PolicyEvaluationReason)),
        )
        cinderlake_decision = session.scalar(
            select(DecisionEvaluation).where(
                DecisionEvaluation.account_id == DEMO_ACCOUNTS[2]["id"]
            )
        )
        assert cinderlake_decision is not None
        cinderlake_policy = session.scalar(
            select(PolicyEvaluation).where(
                PolicyEvaluation.decision_evaluation_id
                == cinderlake_decision.decision_evaluation_id
            )
        )
        assert cinderlake_policy is not None

    with TestClient(app) as client:
        current = client.get(f"/api/v1/accounts/{DEMO_ACCOUNTS[2]['id']}/decision")
        current_state = client.get(f"/api/v1/accounts/{DEMO_ACCOUNTS[2]['id']}/state")
        history = client.get(f"/api/v1/accounts/{DEMO_ACCOUNTS[2]['id']}/decision/history")
        decision = client.get(
            f"/api/v1/decision-evaluations/{cinderlake_decision.decision_evaluation_id}"
        )
        policy = client.get(f"/api/v1/policy-evaluations/{cinderlake_policy.policy_evaluation_id}")
        assert current.status_code == current_state.status_code == history.status_code == 200
        assert decision.status_code == policy.status_code == 200
        body = current.json()
        assert body["decision"]["evaluation"]["result"] == "ENGAGE"
        assert body["disposition"]["proposed_response_label"] == ("Engagement merits consideration")
        assert body["disposition"]["lifecycle"] == "PROPOSED_ONLY"
        assert body["disposition"]["external_action_authorized"] is False
        assert (
            body["state_snapshot"]["state_snapshot_id"]
            == (current_state.json()["snapshot"]["state_snapshot_id"])
        )
        assert client.post(f"/api/v1/accounts/{DEMO_ACCOUNTS[2]['id']}/decision").status_code == 405
        assert (
            client.patch(
                f"/api/v1/decision-evaluations/{cinderlake_decision.decision_evaluation_id}"
            ).status_code
            == 405
        )

    with get_session_factory()() as session:
        after = (
            session.scalar(select(func.count()).select_from(DecisionEvaluation)),
            session.scalar(select(func.count()).select_from(PolicyEvaluation)),
            session.scalar(select(func.count()).select_from(DecisionEvaluationReason)),
            session.scalar(select(func.count()).select_from(PolicyEvaluationReason)),
        )
    assert after == before


def test_current_get_returns_not_materialized_without_computing() -> None:
    with get_session_factory()() as session:
        seed_demo(session)
        session.add(
            _new_relationship_evidence(
                account_id=DEMO_ACCOUNTS[0]["id"],
                assertion=EvidenceAssertion.ABSENT,
                observed_at=DEMO_AS_OF,
            )
        )
        session.flush()
        recompute_workspace_account_states(
            session,
            _current_snapshot(session, DEMO_ACCOUNTS[0]["id"]).workspace_id,
            computed_at=DEMO_EVALUATED_AT + timedelta(hours=2),
        )
        before = (
            session.scalar(select(func.count()).select_from(DecisionEvaluation)),
            session.scalar(select(func.count()).select_from(PolicyEvaluation)),
        )

        def override_session() -> object:
            yield session

        app.dependency_overrides[get_session] = override_session
        try:
            with TestClient(app) as client:
                response = client.get(f"/api/v1/accounts/{DEMO_ACCOUNTS[0]['id']}/decision")
        finally:
            app.dependency_overrides.clear()
        after = (
            session.scalar(select(func.count()).select_from(DecisionEvaluation)),
            session.scalar(select(func.count()).select_from(PolicyEvaluation)),
        )
        session.rollback()

    assert response.status_code == 404
    assert "not materialized" in response.json()["detail"]
    assert after == before


def test_definition_seed_rejects_semantic_mutation() -> None:
    with get_session_factory()() as session:
        seed_demo(session)
        definition = session.get(PolicyDefinition, POLICY_DEFINITION_ID)
        assert definition is not None
        definition.description = "Mutated semantic definition."
        session.flush()

        with pytest.raises(ValueError, match="does not match the seed definition"):
            seed_demo(session)
        session.rollback()
