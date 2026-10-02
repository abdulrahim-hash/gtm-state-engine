"""PostgreSQL integration tests for deterministic M1B.2 account state."""

from datetime import datetime, timedelta
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from gtm_state_api.database import get_session, get_session_factory
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
    AccountStateSnapshot,
    Evidence,
    StateSnapshotEvidence,
    StateSnapshotFitCriterion,
    StateSnapshotReason,
    StateSnapshotSignalEvaluation,
    StrategyFitCriterion,
)
from gtm_state_api.state_engine import recompute_workspace_account_states
from gtm_state_api.types import (
    AccountEvidenceSufficiency,
    AccountFitContext,
    AccountRelationshipState,
    AccountStateFacet,
    AccountTimingState,
    EvidenceAssertion,
    EvidenceClassification,
    EvidenceFreshness,
)

pytestmark = pytest.mark.integration


def _new_evidence(
    *,
    account_id: UUID,
    fact_key: str,
    assertion: EvidenceAssertion,
    observed_at: datetime,
    normalized_fact: str,
) -> Evidence:
    return Evidence(
        id=uuid4(),
        strategy_version_id=None,
        account_id=account_id,
        strategy_topic=None,
        classification=EvidenceClassification.FACT,
        source_provider="synthetic_test",
        source_reference=f"synthetic://m1b2-test/{uuid4()}",
        source_uri=None,
        observed_at=observed_at,
        ingested_at=DEMO_AS_OF,
        normalized_fact=normalized_fact,
        raw_payload_hash=None,
        freshness=EvidenceFreshness.CURRENT,
        confidence=None,
        fact_key=fact_key,
        fact_assertion=assertion,
    )


def test_demo_state_matrix_and_normalized_provenance() -> None:
    with get_session_factory()() as session:
        seed_demo(session)
        rows = session.execute(
            select(
                Account.slug,
                AccountStateSnapshot.fit_context,
                AccountStateSnapshot.timing_state,
                AccountStateSnapshot.relationship_state,
                AccountStateSnapshot.evidence_sufficiency,
                AccountStateSnapshot.state_as_of,
            ).join(AccountStateSnapshot, AccountStateSnapshot.account_id == Account.id)
        ).all()
        matrix = {
            row.slug: (
                row.fit_context,
                row.timing_state,
                row.relationship_state,
                row.evidence_sufficiency,
            )
            for row in rows
        }
        fit_links = session.scalar(select(func.count()).select_from(StateSnapshotFitCriterion))
        evidence_links = session.scalar(select(func.count()).select_from(StateSnapshotEvidence))
        evaluation_links = session.scalar(
            select(func.count()).select_from(StateSnapshotSignalEvaluation)
        )
        reason_links = session.scalar(select(func.count()).select_from(StateSnapshotReason))

    assert matrix["asterwind-instruments"] == (
        AccountFitContext.MATCH,
        AccountTimingState.ACTIVE,
        AccountRelationshipState.UNKNOWN,
        AccountEvidenceSufficiency.PARTIAL,
    )
    assert matrix["bramble-logic-systems"] == (
        AccountFitContext.MATCH,
        AccountTimingState.INCONCLUSIVE,
        AccountRelationshipState.UNKNOWN,
        AccountEvidenceSufficiency.PARTIAL,
    )
    assert matrix["cinderlake-revenue-studio"] == (
        AccountFitContext.MATCH,
        AccountTimingState.ACTIVE,
        AccountRelationshipState.EXISTING_RELATIONSHIP,
        AccountEvidenceSufficiency.PARTIAL,
    )
    assert all(row.state_as_of == DEMO_AS_OF for row in rows)
    assert fit_links == 3
    assert evidence_links == 4
    assert evaluation_links == 6
    assert reason_links is not None
    assert reason_links > 0


def test_repeated_seed_preserves_fixture_semantics_and_snapshot_identity() -> None:
    with get_session_factory()() as session:
        seed_demo(session)
        evidence_before = {
            item.id: (
                item.normalized_fact,
                item.source_provider,
                item.source_reference,
                item.raw_payload_hash,
                item.fact_key,
                item.fact_assertion,
            )
            for item in session.scalars(select(Evidence)).all()
        }
        snapshots_before = {
            item.state_snapshot_id: (
                item.input_hash,
                item.computed_at,
                item.created_at,
            )
            for item in session.scalars(select(AccountStateSnapshot)).all()
        }

        seed_demo(session)

        evidence_after = {
            item.id: (
                item.normalized_fact,
                item.source_provider,
                item.source_reference,
                item.raw_payload_hash,
                item.fact_key,
                item.fact_assertion,
            )
            for item in session.scalars(select(Evidence)).all()
        }
        snapshots_after = {
            item.state_snapshot_id: (
                item.input_hash,
                item.computed_at,
                item.created_at,
            )
            for item in session.scalars(select(AccountStateSnapshot)).all()
        }
        evidence_count = session.scalar(select(func.count()).select_from(Evidence))

    assert evidence_count == 24
    assert evidence_after == evidence_before
    assert snapshots_after == snapshots_before


def test_unchanged_recomputation_ignores_computed_at_for_identity() -> None:
    with get_session_factory()() as session:
        seed_demo(session)
        before = {
            item.state_snapshot_id: (item.input_hash, item.computed_at)
            for item in session.scalars(select(AccountStateSnapshot)).all()
        }

        recompute_workspace_account_states(
            session,
            DEMO_WORKSPACE_ID,
            computed_at=DEMO_EVALUATED_AT + timedelta(days=1),
        )
        session.commit()

        after = {
            item.state_snapshot_id: (item.input_hash, item.computed_at)
            for item in session.scalars(select(AccountStateSnapshot)).all()
        }

    assert after == before


def test_changed_relevant_fit_evidence_creates_new_immutable_snapshot() -> None:
    with get_session_factory()() as session:
        seed_demo(session)
        before = session.scalars(
            select(AccountStateSnapshot).where(
                AccountStateSnapshot.account_id == DEMO_ACCOUNTS[0]["id"]
            )
        ).all()
        session.add(
            _new_evidence(
                account_id=DEMO_ACCOUNTS[0]["id"],
                fact_key="account_profile.target_operating_complexity",
                assertion=EvidenceAssertion.ABSENT,
                observed_at=DEMO_AS_OF,
                normalized_fact="Synthetic correction: target context is absent.",
            )
        )
        session.flush()

        recompute_workspace_account_states(
            session,
            DEMO_WORKSPACE_ID,
            computed_at=DEMO_EVALUATED_AT + timedelta(hours=1),
        )
        after = session.scalars(
            select(AccountStateSnapshot)
            .where(AccountStateSnapshot.account_id == DEMO_ACCOUNTS[0]["id"])
            .order_by(AccountStateSnapshot.computed_at)
        ).all()
        after_values = [(item.state_snapshot_id, item.fit_context) for item in after]
        session.rollback()

    assert len(before) == 1
    assert len(after_values) == 2
    assert after_values[0][0] != after_values[1][0]
    assert after_values[0][1] is AccountFitContext.MATCH
    assert after_values[1][1] is AccountFitContext.MISMATCH


def test_changed_relevant_signal_evaluation_creates_new_snapshot() -> None:
    with get_session_factory()() as session:
        seed_demo(session)
        before_count = session.scalar(
            select(func.count())
            .select_from(AccountStateSnapshot)
            .where(AccountStateSnapshot.account_id == DEMO_ACCOUNTS[0]["id"])
        )
        session.add(
            _new_evidence(
                account_id=DEMO_ACCOUNTS[0]["id"],
                fact_key="commercial_event.sales_team_hiring_expansion",
                assertion=EvidenceAssertion.PRESENT,
                observed_at=DEMO_AS_OF - timedelta(days=1),
                normalized_fact="Synthetic change: current hiring expansion is present.",
            )
        )
        session.flush()

        recompute_workspace_account_states(
            session,
            DEMO_WORKSPACE_ID,
            computed_at=DEMO_EVALUATED_AT + timedelta(hours=1),
        )
        snapshots = session.scalars(
            select(AccountStateSnapshot)
            .where(AccountStateSnapshot.account_id == DEMO_ACCOUNTS[0]["id"])
            .order_by(AccountStateSnapshot.computed_at)
        ).all()
        snapshot_values = [(item.input_hash, item.timing_state) for item in snapshots]
        session.rollback()

    assert before_count == 1
    assert len(snapshot_values) == 2
    assert snapshot_values[0][0] != snapshot_values[1][0]
    assert snapshot_values[1][1] is AccountTimingState.ACTIVE


def test_unrelated_evidence_does_not_change_state_identity() -> None:
    with get_session_factory()() as session:
        seed_demo(session)
        before = {
            item.state_snapshot_id: item.input_hash
            for item in session.scalars(select(AccountStateSnapshot)).all()
        }
        session.add(
            _new_evidence(
                account_id=DEMO_ACCOUNTS[0]["id"],
                fact_key="unrelated.account.fact",
                assertion=EvidenceAssertion.PRESENT,
                observed_at=DEMO_AS_OF,
                normalized_fact="Synthetic unrelated fact excluded from account state.",
            )
        )
        session.flush()

        recompute_workspace_account_states(
            session,
            DEMO_WORKSPACE_ID,
            computed_at=DEMO_EVALUATED_AT + timedelta(hours=1),
        )
        after = {
            item.state_snapshot_id: item.input_hash
            for item in session.scalars(select(AccountStateSnapshot)).all()
        }
        session.rollback()

    assert after == before


def test_older_relevant_evidence_creates_provenance_revision_without_changing_fit() -> None:
    with get_session_factory()() as session:
        seed_demo(session)
        session.add(
            _new_evidence(
                account_id=DEMO_ACCOUNTS[0]["id"],
                fact_key="account_profile.target_operating_complexity",
                assertion=EvidenceAssertion.ABSENT,
                observed_at=DEMO_AS_OF - timedelta(days=30),
                normalized_fact="Synthetic older target-context history.",
            )
        )
        session.flush()

        recompute_workspace_account_states(
            session,
            DEMO_WORKSPACE_ID,
            computed_at=DEMO_EVALUATED_AT + timedelta(hours=1),
        )
        snapshots = session.scalars(
            select(AccountStateSnapshot)
            .where(AccountStateSnapshot.account_id == DEMO_ACCOUNTS[0]["id"])
            .order_by(AccountStateSnapshot.computed_at)
        ).all()
        newest_links = session.scalar(
            select(func.count())
            .select_from(StateSnapshotEvidence)
            .where(
                StateSnapshotEvidence.state_snapshot_id == snapshots[-1].state_snapshot_id,
                StateSnapshotEvidence.facet == AccountStateFacet.FIT_CONTEXT,
            )
        )
        snapshot_values = [(item.fit_context, item.input_hash) for item in snapshots]
        session.rollback()

    assert len(snapshot_values) == 2
    assert snapshot_values[0][0] is snapshot_values[1][0] is AccountFitContext.MATCH
    assert snapshot_values[0][1] != snapshot_values[1][1]
    assert newest_links == 2


def test_fit_trace_freezes_criterion_expected_observed_and_evidence_links() -> None:
    with get_session_factory()() as session:
        seed_demo(session)
        cinderlake_snapshot = session.scalar(
            select(AccountStateSnapshot).where(
                AccountStateSnapshot.account_id == DEMO_ACCOUNTS[2]["id"]
            )
        )
        assert cinderlake_snapshot is not None
        fit_row = session.scalar(
            select(StateSnapshotFitCriterion).where(
                StateSnapshotFitCriterion.state_snapshot_id == cinderlake_snapshot.state_snapshot_id
            )
        )
        assert fit_row is not None
        criterion = session.get(StrategyFitCriterion, fit_row.fit_criterion_id)
        assert criterion is not None
        evidence_link = session.scalar(
            select(StateSnapshotEvidence).where(
                StateSnapshotEvidence.state_snapshot_id == cinderlake_snapshot.state_snapshot_id,
                StateSnapshotEvidence.fit_criterion_id == criterion.fit_criterion_id,
            )
        )

    assert criterion.source_strategy_evidence_id is not None
    assert fit_row.criterion_stable_key == criterion.stable_key
    assert fit_row.input_fact_key == criterion.input_fact_key
    assert fit_row.source_strategy_evidence_id == criterion.source_strategy_evidence_id
    assert fit_row.expected_assertion is EvidenceAssertion.PRESENT
    assert fit_row.observed_assertion is EvidenceAssertion.PRESENT
    assert evidence_link is not None
    assert evidence_link.fit_criterion_id == criterion.fit_criterion_id


def test_snapshot_provenance_rejects_cross_account_evidence() -> None:
    with get_session_factory()() as session:
        seed_demo(session)
        asterwind_snapshot = session.scalar(
            select(AccountStateSnapshot).where(
                AccountStateSnapshot.account_id == DEMO_ACCOUNTS[0]["id"]
            )
        )
        bramble_evidence = session.scalar(
            select(Evidence).where(
                Evidence.account_id == DEMO_ACCOUNTS[1]["id"],
                Evidence.fact_key == "account_profile.target_operating_complexity",
            )
        )
        assert asterwind_snapshot is not None
        assert bramble_evidence is not None
        session.add(
            StateSnapshotEvidence(
                state_snapshot_id=asterwind_snapshot.state_snapshot_id,
                evidence_id=bramble_evidence.id,
                facet=AccountStateFacet.RELATIONSHIP_STATE,
                account_id=asterwind_snapshot.account_id,
                fit_criterion_id=None,
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()


def test_state_get_routes_are_read_only_and_expose_history() -> None:
    with get_session_factory()() as session:
        seed_demo(session)
        snapshot_count = session.scalar(select(func.count()).select_from(AccountStateSnapshot))
        cinderlake_snapshot = session.scalar(
            select(AccountStateSnapshot).where(
                AccountStateSnapshot.account_id == DEMO_ACCOUNTS[2]["id"]
            )
        )
        assert cinderlake_snapshot is not None
        snapshot_id = cinderlake_snapshot.state_snapshot_id

    with TestClient(app) as client:
        current = client.get(f"/api/v1/accounts/{DEMO_ACCOUNTS[2]['id']}/state")
        assert current.status_code == 200
        body = current.json()
        assert body["snapshot"]["timing_state"] == "ACTIVE"
        assert body["snapshot"]["relationship_state"] == "EXISTING_RELATIONSHIP"
        assert body["snapshot"]["evidence_sufficiency"] == "PARTIAL"
        assert body["fit_criteria"][0]["expected_assertion"] == "PRESENT"
        assert body["fit_criteria"][0]["observed_assertion"] == "PRESENT"
        assert body["fit_criteria"][0]["criterion_stable_key"] == "target_operating_complexity"
        assert (
            body["fit_criteria"][0]["input_fact_key"]
            == "account_profile.target_operating_complexity"
        )
        assert body["fit_criteria"][0]["source_strategy_evidence_id"] == str(
            body["fit_criteria"][0]["source_strategy_evidence"]["id"]
        )
        assert len(body["signal_evaluations"]) == 2

        history = client.get(f"/api/v1/accounts/{DEMO_ACCOUNTS[2]['id']}/state/history")
        assert history.status_code == 200
        assert len(history.json()["items"]) == 1

        historical = client.get(f"/api/v1/account-state-snapshots/{snapshot_id}")
        assert historical.status_code == 200
        assert historical.json()["snapshot"]["state_snapshot_id"] == str(snapshot_id)

        assert client.get(f"/api/v1/accounts/{uuid4()}/state").status_code == 404
        assert client.get(f"/api/v1/account-state-snapshots/{uuid4()}").status_code == 404
        assert (
            client.get(
                f"/api/v1/accounts/{DEMO_ACCOUNTS[2]['id']}/state/history?limit=0"
            ).status_code
            == 422
        )

    with get_session_factory()() as session:
        after_get_count = session.scalar(select(func.count()).select_from(AccountStateSnapshot))

    assert after_get_count == snapshot_count


def test_current_route_selects_latest_materialized_revision_at_same_semantic_time() -> None:
    with get_session_factory()() as session:
        seed_demo(session)
        original = session.scalar(
            select(AccountStateSnapshot).where(
                AccountStateSnapshot.account_id == DEMO_ACCOUNTS[0]["id"]
            )
        )
        assert original is not None
        original_id = original.state_snapshot_id
        session.add(
            _new_evidence(
                account_id=DEMO_ACCOUNTS[0]["id"],
                fact_key="account_profile.target_operating_complexity",
                assertion=EvidenceAssertion.ABSENT,
                observed_at=DEMO_AS_OF,
                normalized_fact="Synthetic late-arriving correction for current materialization.",
            )
        )
        session.flush()
        recompute_workspace_account_states(
            session,
            DEMO_WORKSPACE_ID,
            computed_at=DEMO_EVALUATED_AT + timedelta(hours=1),
        )

        def override_session() -> object:
            yield session

        app.dependency_overrides[get_session] = override_session
        try:
            with TestClient(app) as client:
                current = client.get(f"/api/v1/accounts/{DEMO_ACCOUNTS[0]['id']}/state")
                history = client.get(f"/api/v1/accounts/{DEMO_ACCOUNTS[0]['id']}/state/history")
                historical = client.get(f"/api/v1/account-state-snapshots/{original_id}")
        finally:
            app.dependency_overrides.clear()
            session.rollback()

    assert current.status_code == 200
    assert current.json()["snapshot"]["fit_context"] == "MISMATCH"
    assert current.json()["snapshot"]["state_as_of"] == DEMO_AS_OF.isoformat().replace(
        "+00:00", "Z"
    )
    assert len(history.json()["items"]) == 2
    assert historical.json()["snapshot"]["fit_context"] == "MATCH"
