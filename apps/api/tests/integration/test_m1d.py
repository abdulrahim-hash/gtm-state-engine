"""PostgreSQL integration tests for governed M1D Action and Outcome trace."""

from datetime import timedelta
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from gtm_state_api import action_api
from gtm_state_api.action_engine import materialize_policy_action
from gtm_state_api.action_workflow import (
    ActionTransitionError,
    IdempotencyConflictError,
    create_action_review,
    run_action_dry_run,
)
from gtm_state_api.config import Settings
from gtm_state_api.database import get_engine, get_session, get_session_factory
from gtm_state_api.decision_engine import materialize_snapshot_disposition
from gtm_state_api.demo_seed import (
    DEMO_ACCOUNTS,
    DEMO_EVALUATED_AT,
    DEMO_REVIEWED_AT,
    seed_demo,
)
from gtm_state_api.main import app
from gtm_state_api.models import (
    AccountStateSnapshot,
    Action,
    ActionAttempt,
    ActionOutcome,
    ActionReview,
    DecisionEvaluation,
    Evidence,
    PolicyDefinition,
    PolicyEvaluation,
    PolicyEvaluationReason,
    SignalEvaluation,
)
from gtm_state_api.types import (
    AccountEvidenceSufficiency,
    AccountRelationshipState,
    ActionActorKind,
    ActionCurrentProjection,
    ActionLifecycle,
    ActionOutcomeReasonCode,
    ActionOutcomeResult,
    ActionReviewReasonCode,
    ActionReviewResolution,
    ActionType,
    EvaluationDefinitionStatus,
    PolicyResult,
)

pytestmark = pytest.mark.integration


def _action(session: Session, account_id: UUID) -> Action:
    action = session.scalar(select(Action).where(Action.account_id == account_id))
    assert action is not None
    return action


def _counts(session: Session) -> tuple[int, int, int, int]:
    return (
        session.scalar(select(func.count()).select_from(Action)) or 0,
        session.scalar(select(func.count()).select_from(ActionReview)) or 0,
        session.scalar(select(func.count()).select_from(ActionAttempt)) or 0,
        session.scalar(select(func.count()).select_from(ActionOutcome)) or 0,
    )


def _upstream_fingerprint(session: Session) -> tuple[object, ...]:
    return (
        session.execute(
            select(
                AccountStateSnapshot.state_snapshot_id,
                AccountStateSnapshot.input_hash,
                AccountStateSnapshot.relationship_state,
            ).order_by(AccountStateSnapshot.state_snapshot_id)
        ).all(),
        session.execute(
            select(
                DecisionEvaluation.decision_evaluation_id,
                DecisionEvaluation.input_hash,
                DecisionEvaluation.result,
            ).order_by(DecisionEvaluation.decision_evaluation_id)
        ).all(),
        session.execute(
            select(
                PolicyEvaluation.policy_evaluation_id,
                PolicyEvaluation.input_hash,
                PolicyEvaluation.result,
            ).order_by(PolicyEvaluation.policy_evaluation_id)
        ).all(),
        session.scalar(select(func.count()).select_from(Evidence)),
        session.scalar(select(func.count()).select_from(SignalEvaluation)),
    )


def test_demo_matrix_and_composed_trace_are_exact_and_non_executing() -> None:
    with get_session_factory()() as session:
        seed_demo(session)
        assert _counts(session) == (2, 1, 1, 1)
        asterwind = _action(session, DEMO_ACCOUNTS[0]["id"])
        cinderlake = _action(session, DEMO_ACCOUNTS[2]["id"])
        assert asterwind.action_type is ActionType.REQUEST_RESEARCH
        assert asterwind.payload == {
            "research_topic": "RELATIONSHIP_CONTEXT",
            "request_code": "VERIFY_EXISTING_RELATIONSHIP",
        }
        assert cinderlake.action_type is ActionType.CREATE_SELLER_TASK
        assert cinderlake.payload == {
            "task_kind": "RELATIONSHIP_COORDINATION",
            "objective_code": "ASSESS_CONTROLLED_ENGAGEMENT_PATH",
        }
        assert (
            session.scalar(select(Action).where(Action.account_id == DEMO_ACCOUNTS[1]["id"]))
            is None
        )

    with TestClient(app) as client:
        asterwind_response = client.get(f"/api/v1/accounts/{DEMO_ACCOUNTS[0]['id']}/action")
        bramble_response = client.get(f"/api/v1/accounts/{DEMO_ACCOUNTS[1]['id']}/action")
        cinderlake_response = client.get(f"/api/v1/accounts/{DEMO_ACCOUNTS[2]['id']}/action")
        bramble_history = client.get(f"/api/v1/accounts/{DEMO_ACCOUNTS[1]['id']}/actions")
        trace = client.get(f"/api/v1/actions/{cinderlake.action_id}/trace")
        assert all(
            result.status_code == 200
            for result in (
                asterwind_response,
                bramble_response,
                cinderlake_response,
                bramble_history,
                trace,
            )
        )
        asterwind_current = asterwind_response.json()["current"]
        bramble_current = bramble_response.json()["current"]
        cinderlake_current = cinderlake_response.json()["current"]
        assert asterwind_current["projection"] == "ACTION_PROPOSED"
        assert asterwind_current["action"]["lifecycle"] == "REVIEW_REQUIRED"
        assert asterwind_current["action"]["attempts"] == []
        assert bramble_current["projection"] == "BLOCKED_BY_POLICY"
        assert bramble_current["action"] is None
        assert bramble_history.json()["items"] == []
        assert cinderlake_current["action"]["lifecycle"] == "READY_FOR_DRY_RUN"
        review = cinderlake_current["action"]["review"]
        assert review["reviewer_kind"] == "SYNTHETIC_FIXTURE"
        assert review["reviewed_at"] == DEMO_REVIEWED_AT.isoformat().replace("+00:00", "Z")
        outcome = cinderlake_current["action"]["attempts"][0]["outcome"]
        assert outcome["result"] == "SUCCEEDED"
        assert outcome["reason_code"] == "CANONICAL_ACTION_VALIDATED"
        assert outcome["external_side_effects"] is False
        assert cinderlake_current["external_execution_authorized"] is False
        composed = trace.json()
        assert (
            composed["action"]["action"]["policy_evaluation_id"]
            == composed["upstream"]["policy"]["evaluation"]["policy_evaluation_id"]
        )
        assert (
            composed["upstream"]["decision"]["evaluation"]["state_snapshot_id"]
            == composed["state"]["snapshot"]["state_snapshot_id"]
        )
        assert composed["strategy"]["synthetic_disclaimer"].startswith("Synthetic demo only")
        assert composed["state"]["fit_criteria"]
        assert composed["state"]["signal_evaluations"]


def test_repeated_seed_preserves_all_m1d_ids_timestamps_and_upstream_rows() -> None:
    with get_session_factory()() as session:
        seed_demo(session)
        upstream_before = _upstream_fingerprint(session)
        actions_before = session.execute(
            select(
                Action.action_id,
                Action.semantic_input_hash,
                Action.proposed_at,
            ).order_by(Action.action_id)
        ).all()
        reviews_before = session.execute(
            select(
                ActionReview.review_id,
                ActionReview.idempotency_key_hash,
                ActionReview.reviewed_at,
            )
        ).all()
        attempts_before = session.execute(
            select(ActionAttempt.action_attempt_id, ActionAttempt.attempted_at)
        ).all()
        outcomes_before = session.execute(
            select(ActionOutcome.outcome_id, ActionOutcome.observed_at)
        ).all()
        seed_demo(session)
        assert _counts(session) == (2, 1, 1, 1)
        assert _upstream_fingerprint(session) == upstream_before
        assert (
            session.execute(
                select(
                    Action.action_id,
                    Action.semantic_input_hash,
                    Action.proposed_at,
                ).order_by(Action.action_id)
            ).all()
            == actions_before
        )
        assert (
            session.execute(
                select(
                    ActionReview.review_id,
                    ActionReview.idempotency_key_hash,
                    ActionReview.reviewed_at,
                )
            ).all()
            == reviews_before
        )
        assert (
            session.execute(
                select(ActionAttempt.action_attempt_id, ActionAttempt.attempted_at)
            ).all()
            == attempts_before
        )
        assert (
            session.execute(select(ActionOutcome.outcome_id, ActionOutcome.observed_at)).all()
            == outcomes_before
        )


def test_review_and_dry_run_require_authority_and_are_idempotent() -> None:
    with get_session_factory()() as session:
        seed_demo(session)
        action = _action(session, DEMO_ACCOUNTS[0]["id"])
        policy = session.get(PolicyEvaluation, action.policy_evaluation_id)
        assert policy is not None
        upstream_before = _upstream_fingerprint(session)
        policy_projection, repeated_action = materialize_policy_action(
            session,
            policy.policy_evaluation_id,
            proposed_at=DEMO_EVALUATED_AT + timedelta(days=2),
        )
        assert policy_projection is ActionCurrentProjection.ACTION_PROPOSED
        assert repeated_action is not None
        assert repeated_action.action_id == action.action_id
        with pytest.raises(ActionTransitionError, match="required Review"):
            run_action_dry_run(
                session,
                action.action_id,
                requested_by_kind=ActionActorKind.UNVERIFIED_DEMO_HUMAN,
                requested_by_ref="local-demo-requester",
            )
        assert (
            session.scalar(
                select(func.count())
                .select_from(ActionAttempt)
                .where(ActionAttempt.action_id == action.action_id)
            )
            == 0
        )

        review, replay = create_action_review(
            session,
            action.action_id,
            resolution=ActionReviewResolution.APPROVED,
            reason_code=ActionReviewReasonCode.APPROVED_AS_PROPOSED,
            idempotency_key="review-1",
            reviewer_kind=ActionActorKind.UNVERIFIED_DEMO_HUMAN,
            reviewer_ref="local-demo-reviewer",
        )
        same_review, replay_again = create_action_review(
            session,
            action.action_id,
            resolution=ActionReviewResolution.APPROVED,
            reason_code=ActionReviewReasonCode.APPROVED_AS_PROPOSED,
            idempotency_key="review-1",
            reviewer_kind=ActionActorKind.UNVERIFIED_DEMO_HUMAN,
            reviewer_ref="local-demo-reviewer",
        )
        assert not replay and replay_again
        assert same_review.review_id == review.review_id
        with pytest.raises(IdempotencyConflictError):
            create_action_review(
                session,
                action.action_id,
                resolution=ActionReviewResolution.REJECTED,
                reason_code=ActionReviewReasonCode.REJECTED_INSUFFICIENT_CONTEXT,
                idempotency_key="review-1",
                reviewer_kind=ActionActorKind.UNVERIFIED_DEMO_HUMAN,
                reviewer_ref="local-demo-reviewer",
            )
        with pytest.raises(ActionTransitionError, match="terminal Review"):
            create_action_review(
                session,
                action.action_id,
                resolution=ActionReviewResolution.APPROVED,
                reason_code=ActionReviewReasonCode.APPROVED_AS_PROPOSED,
                idempotency_key="review-3",
                reviewer_kind=ActionActorKind.UNVERIFIED_DEMO_HUMAN,
                reviewer_ref="local-demo-reviewer",
            )
        attempt, outcome, first_replay = run_action_dry_run(
            session,
            action.action_id,
            requested_by_kind=ActionActorKind.UNVERIFIED_DEMO_HUMAN,
            requested_by_ref="local-demo-requester",
        )
        second_attempt, second_outcome, second_replay = run_action_dry_run(
            session,
            action.action_id,
            requested_by_kind=ActionActorKind.UNVERIFIED_DEMO_HUMAN,
            requested_by_ref="local-demo-requester",
            attempted_at=DEMO_EVALUATED_AT + timedelta(days=3),
        )
        assert not first_replay and second_replay
        assert second_attempt.action_attempt_id == attempt.action_attempt_id
        assert second_outcome.outcome_id == outcome.outcome_id
        assert second_attempt.attempted_at == attempt.attempted_at
        assert outcome.result is ActionOutcomeResult.SUCCEEDED
        assert outcome.reason_code is ActionOutcomeReasonCode.CANONICAL_ACTION_VALIDATED
        assert outcome.external_side_effects is False
        assert attempt.review_id == review.review_id
        assert _upstream_fingerprint(session) == upstream_before
        session.rollback()


def test_rejection_is_terminal_and_creates_no_attempt_or_outcome() -> None:
    with get_session_factory()() as session:
        seed_demo(session)
        action = _action(session, DEMO_ACCOUNTS[0]["id"])
        review, _ = create_action_review(
            session,
            action.action_id,
            resolution=ActionReviewResolution.REJECTED,
            reason_code=ActionReviewReasonCode.REJECTED_ACTION_NOT_APPROPRIATE,
            idempotency_key="review-2",
            reviewer_kind=ActionActorKind.UNVERIFIED_DEMO_HUMAN,
            reviewer_ref="local-demo-reviewer",
        )
        from gtm_state_api.action_workflow import action_lifecycle

        assert action_lifecycle(session, action, review=review) is ActionLifecycle.REJECTED
        with pytest.raises(ActionTransitionError, match="rejected Action"):
            run_action_dry_run(
                session,
                action.action_id,
                requested_by_kind=ActionActorKind.UNVERIFIED_DEMO_HUMAN,
                requested_by_ref="local-demo-requester",
            )
        assert (
            session.scalar(
                select(func.count())
                .select_from(ActionAttempt)
                .where(ActionAttempt.action_id == action.action_id)
            )
            == 0
        )
        session.rollback()


def test_allow_fixture_is_test_only_ready_for_local_dry_run() -> None:
    with get_session_factory()() as session:
        seed_demo(session)
        original = session.scalar(
            select(AccountStateSnapshot).where(
                AccountStateSnapshot.account_id == DEMO_ACCOUNTS[0]["id"]
            )
        )
        assert original is not None
        fixture = AccountStateSnapshot(
            state_snapshot_id=uuid4(),
            workspace_id=original.workspace_id,
            account_id=original.account_id,
            strategy_version_id=original.strategy_version_id,
            state_as_of=original.state_as_of,
            computed_at=DEMO_EVALUATED_AT + timedelta(days=1),
            input_hash="f" * 64,
            state_engine_version=original.state_engine_version,
            fit_context=original.fit_context,
            timing_state=original.timing_state,
            relationship_state=AccountRelationshipState.NO_EXISTING_RELATIONSHIP,
            evidence_sufficiency=AccountEvidenceSufficiency.SUFFICIENT,
            created_at=DEMO_EVALUATED_AT + timedelta(days=1),
        )
        session.add(fixture)
        session.flush()
        decision, policy = materialize_snapshot_disposition(
            session,
            fixture.state_snapshot_id,
        )
        assert decision.result.value == "ENGAGE"
        assert policy.result is PolicyResult.ALLOW
        _, action = materialize_policy_action(session, policy.policy_evaluation_id)
        assert action is not None
        assert action.action_type is ActionType.CREATE_SELLER_TASK
        assert action.payload["task_kind"] == "ENGAGEMENT_ASSESSMENT"
        from gtm_state_api.action_workflow import action_lifecycle

        assert action_lifecycle(session, action) is ActionLifecycle.READY_FOR_DRY_RUN
        with pytest.raises(ActionTransitionError, match="does not require review"):
            create_action_review(
                session,
                action.action_id,
                resolution=ActionReviewResolution.APPROVED,
                reason_code=ActionReviewReasonCode.APPROVED_AS_PROPOSED,
                idempotency_key="m1d-test-allow-review",
                reviewer_kind=ActionActorKind.UNVERIFIED_DEMO_HUMAN,
                reviewer_ref="local-demo-reviewer",
            )
        attempt, outcome, _ = run_action_dry_run(
            session,
            action.action_id,
            requested_by_kind=ActionActorKind.UNVERIFIED_DEMO_HUMAN,
            requested_by_ref="local-demo-requester",
        )
        assert attempt.review_id is None
        assert outcome.result is ActionOutcomeResult.SUCCEEDED
        assert outcome.external_side_effects is False
        session.rollback()


def test_changed_policy_identity_creates_new_action_even_with_same_result() -> None:
    with get_session_factory()() as session:
        seed_demo(session)
        original_action = _action(session, DEMO_ACCOUNTS[0]["id"])
        original_policy = session.get(PolicyEvaluation, original_action.policy_evaluation_id)
        assert original_policy is not None
        original_definition = session.get(PolicyDefinition, original_policy.policy_definition_id)
        assert original_definition is not None
        new_definition_id = uuid4()
        session.add(
            PolicyDefinition(
                policy_definition_id=new_definition_id,
                workspace_id=original_policy.workspace_id,
                strategy_version_id=original_policy.strategy_version_id,
                stable_key="m1d_test_policy_version",
                definition_version="2.0.0-test",
                display_name="Isolated Policy identity test",
                description="Test-only immutable definition.",
                target=original_definition.target,
                evaluator_key=original_definition.evaluator_key,
                evaluator_version=original_definition.evaluator_version,
                status=EvaluationDefinitionStatus.DISABLED,
                created_at=DEMO_EVALUATED_AT,
            )
        )
        second_policy = PolicyEvaluation(
            policy_evaluation_id=uuid4(),
            workspace_id=original_policy.workspace_id,
            account_id=original_policy.account_id,
            strategy_version_id=original_policy.strategy_version_id,
            state_snapshot_id=original_policy.state_snapshot_id,
            decision_evaluation_id=original_policy.decision_evaluation_id,
            policy_definition_id=new_definition_id,
            definition_version="2.0.0-test",
            evaluated_at=DEMO_EVALUATED_AT,
            input_hash="e" * 64,
            result=original_policy.result,
            created_at=DEMO_EVALUATED_AT,
        )
        session.add(second_policy)
        existing_reasons = session.scalars(
            select(PolicyEvaluationReason)
            .where(
                PolicyEvaluationReason.policy_evaluation_id == original_policy.policy_evaluation_id
            )
            .order_by(PolicyEvaluationReason.position)
        ).all()
        session.add_all(
            [
                PolicyEvaluationReason(
                    policy_evaluation_id=second_policy.policy_evaluation_id,
                    position=reason.position,
                    reason_code=reason.reason_code,
                )
                for reason in existing_reasons
            ]
        )
        session.flush()
        projection, new_action = materialize_policy_action(
            session,
            second_policy.policy_evaluation_id,
        )
        assert projection is ActionCurrentProjection.ACTION_PROPOSED
        assert new_action is not None
        assert new_action.action_type is original_action.action_type
        assert new_action.payload == original_action.payload
        assert new_action.action_id != original_action.action_id
        assert new_action.semantic_input_hash != original_action.semantic_input_hash
        session.rollback()


def test_database_rejects_cross_account_action_scope() -> None:
    with get_session_factory()() as session:
        seed_demo(session)
        cinderlake = _action(session, DEMO_ACCOUNTS[2]["id"])
        session.add(
            Action(
                action_id=uuid4(),
                workspace_id=cinderlake.workspace_id,
                account_id=DEMO_ACCOUNTS[0]["id"],
                strategy_version_id=cinderlake.strategy_version_id,
                policy_evaluation_id=cinderlake.policy_evaluation_id,
                action_type=cinderlake.action_type,
                action_schema_version=cinderlake.action_schema_version,
                derivation_key="m1d_cross_scope_test",
                derivation_version="1.0.0",
                payload=cinderlake.payload,
                semantic_input_hash="d" * 64,
                proposed_at=DEMO_EVALUATED_AT,
                created_at=DEMO_EVALUATED_AT,
            )
        )
        with pytest.raises(IntegrityError):
            session.flush()
        session.rollback()


def test_genuine_stored_action_integrity_failure_creates_failed_dry_run() -> None:
    with get_session_factory()() as session:
        seed_demo(session)
        action = _action(session, DEMO_ACCOUNTS[2]["id"])
        action.semantic_input_hash = "c" * 64
        session.flush()
        attempt, outcome, replay = run_action_dry_run(
            session,
            action.action_id,
            requested_by_kind=ActionActorKind.SYNTHETIC_FIXTURE,
            requested_by_ref="synthetic-fixture-cinderlake-dry-run",
        )
        assert replay is False
        assert attempt.mode.value == "DRY_RUN"
        assert outcome.result is ActionOutcomeResult.FAILED
        assert outcome.reason_code is ActionOutcomeReasonCode.CANONICAL_ACTION_INVALID
        assert outcome.external_side_effects is False
        session.rollback()


def test_read_routes_and_disabled_mutations_do_not_write() -> None:
    with get_session_factory()() as session:
        seed_demo(session)
        action = _action(session, DEMO_ACCOUNTS[0]["id"])
        before = _counts(session)
    with TestClient(app) as client:
        assert client.get(f"/api/v1/accounts/{DEMO_ACCOUNTS[0]['id']}/action").status_code == 200
        assert client.get(f"/api/v1/accounts/{DEMO_ACCOUNTS[0]['id']}/actions").status_code == 200
        assert client.get(f"/api/v1/actions/{action.action_id}").status_code == 200
        assert client.get(f"/api/v1/actions/{action.action_id}/outcomes").status_code == 200
        assert client.get(f"/api/v1/actions/{action.action_id}/trace").status_code == 200
        assert (
            client.post(
                f"/api/v1/actions/{action.action_id}/reviews",
                headers={"Idempotency-Key": "m1d-disabled-review"},
                json={
                    "resolution": "APPROVED",
                    "reason_code": "APPROVED_AS_PROPOSED",
                },
            ).status_code
            == 403
        )
        assert client.post(f"/api/v1/actions/{action.action_id}/dry-runs").status_code == 403
        assert client.post(f"/api/v1/actions/{action.action_id}/outcomes").status_code == 405
        assert (
            client.patch(
                f"/api/v1/actions/{action.action_id}",
                json={"payload": {}},
            ).status_code
            == 405
        )
        assert client.post("/api/v1/actions", json={}).status_code == 404
    with get_session_factory()() as session:
        assert _counts(session) == before


def test_local_api_mutations_enforce_review_and_replay_without_actor_input(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with get_session_factory()() as session:
        seed_demo(session)
        action_id = _action(session, DEMO_ACCOUNTS[0]["id"]).action_id

    monkeypatch.setattr(
        action_api,
        "get_settings",
        lambda: Settings(app_env="test", action_mutations_enabled=True),
    )
    with get_engine().connect() as connection:
        outer_transaction = connection.begin()
        with Session(
            bind=connection,
            join_transaction_mode="create_savepoint",
            expire_on_commit=False,
        ) as session:

            def override_session() -> object:
                yield session

            app.dependency_overrides[get_session] = override_session
            try:
                with TestClient(app) as client:
                    dry_run_url = f"/api/v1/actions/{action_id}/dry-runs"
                    review_url = f"/api/v1/actions/{action_id}/reviews"
                    assert client.post(dry_run_url).status_code == 409
                    assert (
                        client.post(
                            review_url,
                            headers={"Idempotency-Key": "m1d-api-review"},
                            json={
                                "resolution": "APPROVED",
                                "reason_code": "APPROVED_AS_PROPOSED",
                                "reviewer_email": "forbidden@example.test",
                            },
                        ).status_code
                        == 422
                    )
                    assert (
                        client.post(
                            review_url,
                            json={
                                "resolution": "APPROVED",
                                "reason_code": "APPROVED_AS_PROPOSED",
                            },
                        ).status_code
                        == 422
                    )
                    assert (
                        client.post(
                            review_url,
                            headers={"Idempotency-Key": "bad key"},
                            json={
                                "resolution": "APPROVED",
                                "reason_code": "APPROVED_AS_PROPOSED",
                            },
                        ).status_code
                        == 422
                    )
                    body = {
                        "resolution": "APPROVED",
                        "reason_code": "APPROVED_AS_PROPOSED",
                    }
                    headers = {"Idempotency-Key": "m1d-api-review"}
                    first = client.post(review_url, headers=headers, json=body)
                    replay = client.post(review_url, headers=headers, json=body)
                    conflict = client.post(
                        review_url,
                        headers=headers,
                        json={
                            "resolution": "REJECTED",
                            "reason_code": "REJECTED_INSUFFICIENT_CONTEXT",
                        },
                    )
                    assert first.status_code == replay.status_code == 200
                    assert first.json()["idempotent_replay"] is False
                    assert replay.json()["idempotent_replay"] is True
                    assert conflict.status_code == 409
                    assert (
                        client.post(
                            review_url,
                            headers={"Idempotency-Key": "review-4"},
                            json=body,
                        ).status_code
                        == 409
                    )
                    assert first.json()["review"]["reviewer_kind"] == ("UNVERIFIED_DEMO_HUMAN")
                    assert first.json()["review"]["reviewer_ref"] == "local-demo-reviewer"
                    assert (
                        client.post(
                            dry_run_url,
                            json={"requested_by": "forged-identity"},
                        ).status_code
                        == 422
                    )
                    first_dry_run = client.post(dry_run_url)
                    replay_dry_run = client.post(dry_run_url)
                    assert first_dry_run.status_code == replay_dry_run.status_code == 200
                    assert first_dry_run.json()["idempotent_replay"] is False
                    assert replay_dry_run.json()["idempotent_replay"] is True
                    assert (
                        first_dry_run.json()["trace"]["attempt"]["requested_by_kind"]
                        == "UNVERIFIED_DEMO_HUMAN"
                    )
                    assert (
                        first_dry_run.json()["trace"]["outcome"]["external_side_effects"] is False
                    )
                    assert (
                        session.scalar(
                            select(func.count())
                            .select_from(ActionReview)
                            .where(ActionReview.action_id == action_id)
                        )
                        == 1
                    )
                    assert (
                        session.scalar(
                            select(func.count())
                            .select_from(ActionAttempt)
                            .where(ActionAttempt.action_id == action_id)
                        )
                        == 1
                    )
            finally:
                app.dependency_overrides.clear()
        outer_transaction.rollback()
