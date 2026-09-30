"""PostgreSQL integration tests for deterministic M1B.1 signals."""

from datetime import timedelta
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from gtm_state_api.database import get_session_factory
from gtm_state_api.demo_seed import (
    DEMO_ACCOUNTS,
    DEMO_AS_OF,
    DEMO_EVALUATED_AT,
    DEMO_WORKSPACE_ID,
    seed_demo,
)
from gtm_state_api.main import app
from gtm_state_api.models import (
    Account,
    EvaluationEvidence,
    Evidence,
    Signal,
    SignalDefinition,
    SignalEvaluation,
    Workspace,
)
from gtm_state_api.signal_engine import recompute_workspace_signals
from gtm_state_api.types import (
    EvidenceClassification,
    SignalCategory,
    SignalDefinitionStatus,
    SignalEvaluationResult,
)

pytestmark = pytest.mark.integration

RELATIONSHIP_EVIDENCE_ID = UUID("1a1206b7-243c-4f22-8d7f-53aa00000207")


def test_fixture_evaluation_matrix_and_relational_provenance() -> None:
    with get_session_factory()() as session:
        seed_demo(session)
        rows = session.execute(
            select(
                Account.slug,
                SignalDefinition.stable_key,
                SignalEvaluation.result,
                SignalEvaluation.reason_code,
                SignalEvaluation.signal_id,
                SignalEvaluation.evaluation_as_of,
                SignalEvaluation.evaluated_at,
            )
            .join(SignalEvaluation, SignalEvaluation.account_id == Account.id)
            .join(
                SignalDefinition,
                SignalDefinition.signal_definition_id == SignalEvaluation.signal_definition_id,
            )
        ).all()
        matrix = {(row.slug, row.stable_key): (row.result, row.signal_id) for row in rows}
        linked_evidence_count = session.scalar(select(func.count()).select_from(EvaluationEvidence))
        relationship_links = session.scalar(
            select(func.count())
            .select_from(EvaluationEvidence)
            .where(EvaluationEvidence.evidence_id == RELATIONSHIP_EVIDENCE_ID)
        )
        signal_count = session.scalar(select(func.count()).select_from(Signal))

    assert len(rows) == 6
    assert matrix[("asterwind-instruments", "new_revenue_leader")][0] is (
        SignalEvaluationResult.DETECTED
    )
    assert matrix[("asterwind-instruments", "sales_team_hiring_expansion")][0] is (
        SignalEvaluationResult.NO_MATCH
    )
    assert matrix[("bramble-logic-systems", "new_revenue_leader")][0] is (
        SignalEvaluationResult.STALE
    )
    assert matrix[("bramble-logic-systems", "sales_team_hiring_expansion")][0] is (
        SignalEvaluationResult.INCONCLUSIVE
    )
    assert matrix[("cinderlake-revenue-studio", "new_revenue_leader")][0] is (
        SignalEvaluationResult.DETECTED
    )
    assert matrix[("cinderlake-revenue-studio", "sales_team_hiring_expansion")][0] is (
        SignalEvaluationResult.INCONCLUSIVE
    )
    assert matrix[("cinderlake-revenue-studio", "sales_team_hiring_expansion")][1] is None
    assert linked_evidence_count == 5
    assert relationship_links == 0
    assert signal_count == 3
    assert all(row.evaluation_as_of == DEMO_AS_OF for row in rows)
    assert all(row.evaluated_at == DEMO_EVALUATED_AT for row in rows)


def test_unchanged_recomputation_is_idempotent_and_preserves_execution_time() -> None:
    with get_session_factory()() as session:
        seed_demo(session)
        before = {
            item.evaluation_id: (item.input_hash, item.evaluated_at, item.signal_id)
            for item in session.scalars(select(SignalEvaluation)).all()
        }
        signal_fingerprints = {
            item.signal_id: item.event_fingerprint for item in session.scalars(select(Signal)).all()
        }

        recompute_workspace_signals(
            session,
            DEMO_WORKSPACE_ID,
            evaluated_at=DEMO_EVALUATED_AT + timedelta(hours=4),
        )
        session.commit()

        after = {
            item.evaluation_id: (item.input_hash, item.evaluated_at, item.signal_id)
            for item in session.scalars(select(SignalEvaluation)).all()
        }
        after_fingerprints = {
            item.signal_id: item.event_fingerprint for item in session.scalars(select(Signal)).all()
        }

    assert after == before
    assert after_fingerprints == signal_fingerprints


def test_same_events_reuse_canonical_signals_at_a_later_semantic_time() -> None:
    with get_session_factory()() as session:
        seed_demo(session)
        original = {
            item.event_fingerprint: item.signal_id for item in session.scalars(select(Signal)).all()
        }
        workspace = session.get(Workspace, DEMO_WORKSPACE_ID)
        assert workspace is not None
        workspace.demo_as_of = DEMO_AS_OF + timedelta(days=200)
        session.flush()

        recompute_workspace_signals(
            session,
            DEMO_WORKSPACE_ID,
            evaluated_at=DEMO_EVALUATED_AT + timedelta(days=200),
        )
        current = {
            item.event_fingerprint: item.signal_id for item in session.scalars(select(Signal)).all()
        }
        evaluations = session.scalars(select(SignalEvaluation)).all()
        stale_count = sum(item.result is SignalEvaluationResult.STALE for item in evaluations)
        session.rollback()

    assert current == original
    assert len(evaluations) == 12
    assert stale_count == 4


def test_future_evidence_is_excluded_from_demo_snapshot() -> None:
    with get_session_factory()() as session:
        seed_demo(session)
        before_count = session.scalar(select(func.count()).select_from(SignalEvaluation))
        template = session.scalar(
            select(Evidence).where(
                Evidence.account_id == DEMO_ACCOUNTS[0]["id"],
                Evidence.fact_key == "commercial_event.new_revenue_leader",
            )
        )
        assert template is not None
        session.add(
            Evidence(
                id=uuid4(),
                strategy_version_id=None,
                account_id=template.account_id,
                strategy_topic=None,
                classification=template.classification,
                source_provider="synthetic_test",
                source_reference=f"synthetic://future/{uuid4()}",
                source_uri=None,
                observed_at=DEMO_AS_OF + timedelta(days=1),
                ingested_at=DEMO_AS_OF,
                normalized_fact="Synthetic future observation excluded from this snapshot.",
                raw_payload_hash=None,
                freshness=template.freshness,
                confidence=None,
                fact_key=template.fact_key,
                fact_assertion=template.fact_assertion,
            )
        )
        session.flush()
        recompute_workspace_signals(
            session,
            DEMO_WORKSPACE_ID,
            evaluated_at=DEMO_EVALUATED_AT + timedelta(hours=1),
        )
        after_count = session.scalar(select(func.count()).select_from(SignalEvaluation))
        session.rollback()

    assert before_count == after_count == 6


def test_non_fact_evidence_cannot_satisfy_the_v1_evaluator() -> None:
    with get_session_factory()() as session:
        seed_demo(session)
        missing_evaluation = session.scalar(
            select(SignalEvaluation)
            .join(
                SignalDefinition,
                SignalDefinition.signal_definition_id == SignalEvaluation.signal_definition_id,
            )
            .where(
                SignalEvaluation.account_id == DEMO_ACCOUNTS[2]["id"],
                SignalDefinition.stable_key == "sales_team_hiring_expansion",
            )
        )
        assert missing_evaluation is not None
        original_hash = missing_evaluation.input_hash
        template = session.scalar(select(Evidence).where(Evidence.fact_key.is_not(None)))
        assert template is not None
        session.add(
            Evidence(
                id=uuid4(),
                strategy_version_id=None,
                account_id=DEMO_ACCOUNTS[2]["id"],
                strategy_topic=None,
                classification=EvidenceClassification.INFERENCE,
                source_provider="synthetic_test",
                source_reference=f"synthetic://inference/{uuid4()}",
                source_uri=None,
                observed_at=DEMO_AS_OF - timedelta(days=1),
                ingested_at=DEMO_AS_OF,
                normalized_fact="Synthetic inference that cannot produce a v1 signal.",
                raw_payload_hash=None,
                freshness=template.freshness,
                confidence=None,
                fact_key="commercial_event.sales_team_hiring_expansion",
                fact_assertion=template.fact_assertion,
            )
        )
        session.flush()
        recompute_workspace_signals(
            session,
            DEMO_WORKSPACE_ID,
            evaluated_at=DEMO_EVALUATED_AT + timedelta(hours=1),
        )
        refreshed = session.get(SignalEvaluation, missing_evaluation.evaluation_id)
        assert refreshed is not None
        refreshed_hash = refreshed.input_hash
        evaluation_count = session.scalar(select(func.count()).select_from(SignalEvaluation))
        session.rollback()

    assert refreshed_hash == original_hash
    assert evaluation_count == 6


def test_duplicate_evaluation_input_is_rejected_by_database() -> None:
    with get_session_factory()() as session:
        seed_demo(session)
        original = session.scalar(
            select(SignalEvaluation).where(
                SignalEvaluation.result == SignalEvaluationResult.NO_MATCH
            )
        )
        assert original is not None
        session.add(
            SignalEvaluation(
                evaluation_id=uuid4(),
                workspace_id=original.workspace_id,
                account_id=original.account_id,
                signal_definition_id=original.signal_definition_id,
                strategy_version_id=original.strategy_version_id,
                signal_id=None,
                evaluation_as_of=original.evaluation_as_of,
                evaluated_at=original.evaluated_at,
                input_hash=original.input_hash,
                result=original.result,
                reason_code=original.reason_code,
                rule_version=original.rule_version,
                created_at=original.created_at,
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()


def test_signal_scope_and_evidence_linkage_are_enforced_by_database() -> None:
    with get_session_factory()() as session:
        seed_demo(session)
        workspace = session.get(Workspace, DEMO_WORKSPACE_ID)
        assert workspace is not None
        other_workspace_id = uuid4()
        session.add(
            Workspace(
                workspace_id=other_workspace_id,
                slug=f"synthetic-signal-scope-{other_workspace_id}",
                name="Synthetic Signal Scope",
                demo_mode=True,
                demo_as_of=DEMO_AS_OF,
                created_at=DEMO_AS_OF,
            )
        )
        session.flush()
        definition = session.scalar(select(SignalDefinition))
        assert definition is not None
        session.add(
            SignalDefinition(
                signal_definition_id=uuid4(),
                workspace_id=other_workspace_id,
                strategy_version_id=definition.strategy_version_id,
                stable_key="invalid_cross_workspace",
                display_name="Invalid cross-workspace definition",
                description="Synthetic constraint test.",
                category=SignalCategory.LEADERSHIP,
                input_fact_key="commercial_event.invalid",
                evaluator_key="latest_assertion_with_freshness",
                freshness_window_days=30,
                rule_version="1.0.0",
                status=SignalDefinitionStatus.ENABLED,
                created_at=DEMO_AS_OF,
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()

    with get_session_factory()() as session:
        seed_demo(session)
        asterwind_evaluation = session.scalar(
            select(SignalEvaluation).where(SignalEvaluation.account_id == DEMO_ACCOUNTS[0]["id"])
        )
        bramble_evidence = session.scalar(
            select(Evidence).where(
                Evidence.account_id == DEMO_ACCOUNTS[1]["id"],
                Evidence.fact_key.is_not(None),
            )
        )
        assert asterwind_evaluation is not None
        assert bramble_evidence is not None
        session.add(
            EvaluationEvidence(
                evaluation_id=asterwind_evaluation.evaluation_id,
                evidence_id=bramble_evidence.id,
                account_id=asterwind_evaluation.account_id,
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()


def test_signal_read_apis_expose_current_and_non_detected_results() -> None:
    with get_session_factory()() as session:
        seed_demo(session)

    with TestClient(app) as client:
        definitions = client.get("/api/v1/signal-definitions")
        assert definitions.status_code == 200
        assert len(definitions.json()["items"]) == 2
        assert {
            (item["evaluator_key"], item["rule_version"]) for item in definitions.json()["items"]
        } == {("latest_assertion_with_freshness", "1.0.0")}

        asterwind_id = str(DEMO_ACCOUNTS[0]["id"])
        signals = client.get(f"/api/v1/accounts/{asterwind_id}/signals")
        assert signals.status_code == 200
        assert len(signals.json()["items"]) == 1
        assert signals.json()["items"][0]["current_status"] == "ACTIVE"
        assert signals.json()["items"][0]["current_freshness"] == "CURRENT"
        assert len(signals.json()["items"][0]["evidence"]) == 1

        evaluations = client.get(f"/api/v1/accounts/{asterwind_id}/signal-evaluations")
        assert evaluations.status_code == 200
        assert {item["evaluation"]["result"] for item in evaluations.json()["items"]} == {
            "DETECTED",
            "NO_MATCH",
        }
        no_match = client.get(f"/api/v1/accounts/{asterwind_id}/signal-evaluations?result=NO_MATCH")
        assert len(no_match.json()["items"]) == 1
        evaluation_id = evaluations.json()["items"][0]["evaluation"]["evaluation_id"]
        assert client.get(f"/api/v1/signal-evaluations/{evaluation_id}").status_code == 200

        assert (
            client.get(
                f"/api/v1/accounts/{asterwind_id}/signal-evaluations?result=INVALID"
            ).status_code
            == 422
        )
        assert client.get(f"/api/v1/accounts/{uuid4()}/signals").status_code == 404
        assert client.get(f"/api/v1/signal-evaluations/{uuid4()}").status_code == 404
