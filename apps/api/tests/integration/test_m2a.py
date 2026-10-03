"""M2A PostgreSQL contracts: atomic source ingress, replay, and historical provenance."""

from __future__ import annotations

import csv
from collections.abc import Iterator
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from gtm_state_api.database import get_engine, get_session
from gtm_state_api.demo_seed import DEMO_WORKSPACE_ID, seed_demo
from gtm_state_api.ingestion_identity import IDENTITY_RULE_REGISTRY, resolve_identity
from gtm_state_api.ingestion_mapping import LEADER_MAPPER, MAPPER_REGISTRY, NormalizedFact
from gtm_state_api.ingestion_replay import (
    promote_normalization_result,
    reprocess_observation,
)
from gtm_state_api.ingestion_service import import_local_csv
from gtm_state_api.local_csv import CSV_HEADER
from gtm_state_api.main import app
from gtm_state_api.models import (
    Account,
    Action,
    ActionOutcome,
    EvaluationEvidence,
    Evidence,
    EvidenceSupersession,
    IngestionBatch,
    IngestionBatchRow,
    NormalizationResult,
    SignalDefinition,
    SourceObservation,
    StrategyVersion,
    Workspace,
)
from gtm_state_api.signal_engine import recompute_workspace_signals
from gtm_state_api.source_observation import SourceObservationInput
from gtm_state_api.types import (
    EvidenceAssertion,
    EvidenceClassification,
    IngestionReason,
    IngestionRowOutcome,
    NormalizationOutcome,
    SignalCategory,
    SignalDefinitionStatus,
    StrategyStatus,
)

pytestmark = pytest.mark.integration


@pytest.fixture
def database_scope() -> Iterator[tuple[object, UUID]]:
    """Give each test an outer PostgreSQL transaction; service commits stay savepoints."""
    with get_engine().connect() as connection:
        outer = connection.begin()
        workspace_id = uuid4()
        with Session(bind=connection, join_transaction_mode="create_savepoint") as session:
            session.add(
                Workspace(
                    workspace_id=workspace_id,
                    slug=f"m2a-test-{workspace_id}",
                    name="Synthetic local import test",
                    demo_mode=False,
                    demo_as_of=None,
                    created_at=datetime(2026, 10, 3, tzinfo=UTC),
                )
            )
            session.commit()
        try:
            yield connection, workspace_id
        finally:
            outer.rollback()


def _session(connection: object) -> Session:
    return Session(bind=connection, join_transaction_mode="create_savepoint")  # type: ignore[arg-type]


def _row(
    record_id: str = "record-1",
    account_id: str = "source-company-1",
    name: str = "Meridian Test Systems",
    domain: str = "meridian.example",
    *,
    observed: str = "2026-09-15T12:00:00Z",
    event: str = "2026-09-14T12:00:00Z",
    excerpt: str = "The company appointed a new revenue leader.",
    assertion: str = "PRESENT",
) -> list[str]:
    return [
        record_id,
        account_id,
        name,
        domain,
        observed,
        event,
        f"https://{domain or 'meridian.example'}/announcements/leader",
        "new_revenue_leader",
        assertion,
        excerpt,
    ]


def _csv(path: Path, rows: list[list[str]]) -> Path:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(CSV_HEADER)
        writer.writerows(rows)
    return path


def _import(connection: object, path: Path, workspace_id: UUID) -> UUID:
    with _session(connection) as session:
        return import_local_csv(session, path, workspace_id=workspace_id)


def test_exact_repeat_and_cross_batch_occurrences(
    tmp_path: Path, database_scope: tuple[object, UUID]
) -> None:
    connection, workspace_id = database_scope
    first_path = _csv(tmp_path / "first.csv", [_row()])
    first = _import(connection, first_path, workspace_id)
    repeated = _import(connection, first_path, workspace_id)
    assert repeated == first
    second_path = _csv(tmp_path / "second.csv", [_row("record-2"), _row()])
    second = _import(connection, second_path, workspace_id)
    assert second != first
    with _session(connection) as session:
        assert session.scalar(select(func.count()).select_from(IngestionBatch)) == 2
        assert session.scalar(select(func.count()).select_from(IngestionBatchRow)) == 3
        assert session.scalar(select(func.count()).select_from(SourceObservation)) == 2
        assert (
            session.scalar(
                select(func.count())
                .select_from(Account)
                .where(Account.workspace_id == workspace_id)
            )
            == 1
        )
        assert (
            session.scalar(
                select(func.count())
                .select_from(Evidence)
                .join(Account, Evidence.account_id == Account.id)
                .where(Account.workspace_id == workspace_id)
            )
            == 2
        )
        duplicate = session.scalar(
            select(IngestionBatchRow).where(
                IngestionBatchRow.batch_id == second,
                IngestionBatchRow.outcome == IngestionRowOutcome.DUPLICATE,
            )
        )
        assert duplicate is not None and duplicate.source_observation_id is not None
        account = session.scalar(select(Account).where(Account.workspace_id == workspace_id))
        assert account is not None and account.segment is None


def test_same_record_time_changed_payload_is_conflict(
    tmp_path: Path, database_scope: tuple[object, UUID]
) -> None:
    connection, workspace_id = database_scope
    _import(connection, _csv(tmp_path / "first.csv", [_row()]), workspace_id)
    second = _import(
        connection,
        _csv(tmp_path / "changed.csv", [_row(excerpt="A different source claim.")]),
        workspace_id,
    )
    with _session(connection) as session:
        assert session.scalar(select(func.count()).select_from(SourceObservation)) == 2
        assert (
            session.scalar(
                select(func.count())
                .select_from(Evidence)
                .join(Account, Evidence.account_id == Account.id)
                .where(Account.workspace_id == workspace_id)
            )
            == 1
        )
        row = session.scalar(select(IngestionBatchRow).where(IngestionBatchRow.batch_id == second))
        assert row is not None
        assert row.outcome is IngestionRowOutcome.REJECTED
        assert row.reason_code is IngestionReason.SOURCE_RECORD_CONFLICT
        result = session.get(NormalizationResult, row.normalization_result_id)
        assert result is not None and result.outcome is NormalizationOutcome.CONFLICT


def test_batch_preflight_is_order_independent_and_partially_accepts(
    tmp_path: Path, database_scope: tuple[object, UUID]
) -> None:
    connection, first_workspace = database_scope
    other_workspace = uuid4()
    with _session(connection) as session:
        session.add(
            Workspace(
                workspace_id=other_workspace,
                slug=f"m2a-test-{other_workspace}",
                name="Second synthetic local import test",
                demo_mode=False,
                demo_as_of=None,
                created_at=datetime(2026, 10, 3, tzinfo=UTC),
            )
        )
        session.commit()
    rows = [
        _row("a", "id-a", "Name One", "shared.example"),
        _row("b", "id-b", "Name Two", "shared.example"),
        _row("c", "id-c", "Safe Company", "safe.example"),
        _row("d", "id-d", "Invalid Company", "invalid.example", assertion=""),
    ]
    first = _import(connection, _csv(tmp_path / "one.csv", rows), first_workspace)
    second = _import(connection, _csv(tmp_path / "two.csv", list(reversed(rows))), other_workspace)
    with _session(connection) as session:

        def outcomes(batch_id: UUID) -> dict[str, IngestionRowOutcome]:
            found: dict[str, IngestionRowOutcome] = {}
            batch_rows = session.scalars(
                select(IngestionBatchRow).where(IngestionBatchRow.batch_id == batch_id)
            ).all()
            for item in batch_rows:
                if item.source_observation_id:
                    source = session.get(SourceObservation, item.source_observation_id)
                    assert source is not None
                    found[source.external_record_id] = item.outcome
            return found

        expected = {
            "a": IngestionRowOutcome.UNRESOLVED,
            "b": IngestionRowOutcome.UNRESOLVED,
            "c": IngestionRowOutcome.ACCEPTED,
            "d": IngestionRowOutcome.REJECTED,
        }
        assert outcomes(first) == outcomes(second) == expected
        accounts = session.scalars(
            select(Account).where(Account.workspace_id.in_([first_workspace, other_workspace]))
        ).all()
        assert len(accounts) == 2
        assert {item.canonical_name for item in accounts} == {"Safe Company"}


def test_domainless_holding_and_later_observation(
    tmp_path: Path, database_scope: tuple[object, UUID], monkeypatch: pytest.MonkeyPatch
) -> None:
    connection, workspace_id = database_scope
    unresolved = _import(
        connection,
        _csv(tmp_path / "unresolved.csv", [_row(domain="")]),
        workspace_id,
    )
    with _session(connection) as session:
        row = session.scalar(
            select(IngestionBatchRow).where(IngestionBatchRow.batch_id == unresolved)
        )
        assert row is not None and row.outcome is IngestionRowOutcome.UNRESOLVED
        held_id = row.source_observation_id
        assert held_id is not None
    _import(
        connection,
        _csv(
            tmp_path / "later.csv",
            [_row(record_id="record-2", observed="2026-09-16T12:00:00Z")],
        ),
        workspace_id,
    )
    monkeypatch.setitem(IDENTITY_RULE_REGISTRY, "1.0.1", resolve_identity)
    with _session(connection) as session:
        preview_id = reprocess_observation(
            session,
            held_id,
            mapper_key="public_company_leader_event",
            mapper_version="1.0.0",
            identity_rule_version="1.0.1",
        )
    with _session(connection) as session:
        preview = session.get(NormalizationResult, preview_id)
        assert preview is not None and preview.outcome is NormalizationOutcome.ACCEPTED
        assert (
            session.scalar(
                select(func.count())
                .select_from(Evidence)
                .where(Evidence.normalization_result_id == preview_id)
            )
            == 0
        )
    with _session(connection) as session:
        promote_normalization_result(session, preview_id)
    with _session(connection) as session:
        assert (
            session.scalar(
                select(func.count())
                .select_from(Evidence)
                .where(Evidence.normalization_result_id == preview_id)
            )
            == 1
        )


def test_replay_preview_promotion_and_historical_signal_provenance(
    tmp_path: Path, database_scope: tuple[object, UUID], monkeypatch: pytest.MonkeyPatch
) -> None:
    connection, workspace_id = database_scope
    _import(connection, _csv(tmp_path / "first.csv", [_row()]), workspace_id)
    with _session(connection) as session:
        observation = session.scalar(select(SourceObservation))
        old_evidence = session.scalar(
            select(Evidence)
            .join(Account, Evidence.account_id == Account.id)
            .where(Account.workspace_id == workspace_id)
        )
        assert observation is not None and old_evidence is not None
        observation_id, old_evidence_id = observation.id, old_evidence.id
        session.add(
            StrategyVersion(
                id=uuid4(),
                workspace_id=workspace_id,
                semantic_version="1.0.0",
                status=StrategyStatus.ACTIVE,
                name="Synthetic test strategy",
                summary="Test only",
                synthetic_disclaimer="Synthetic test only",
                created_at=datetime(2026, 10, 3, tzinfo=UTC),
                activated_at=datetime(2026, 10, 3, tzinfo=UTC),
            )
        )
        session.flush()
        strategy = session.scalar(
            select(StrategyVersion).where(StrategyVersion.workspace_id == workspace_id)
        )
        assert strategy is not None
        session.add(
            SignalDefinition(
                signal_definition_id=uuid4(),
                workspace_id=workspace_id,
                strategy_version_id=strategy.id,
                stable_key="new_leader_test",
                display_name="New leader test",
                description="Synthetic test",
                category=SignalCategory.LEADERSHIP,
                input_fact_key="commercial_event.new_revenue_leader",
                evaluator_key="latest_assertion_with_freshness",
                freshness_window_days=90,
                rule_version="1.0.0",
                status=SignalDefinitionStatus.ENABLED,
                created_at=datetime(2026, 10, 3, tzinfo=UTC),
            )
        )
        session.commit()
    evaluation_as_of = datetime(2026, 9, 17, tzinfo=UTC)
    with _session(connection) as session:
        old_evaluation = recompute_workspace_signals(
            session, workspace_id, evaluation_as_of=evaluation_as_of
        )[0]
        old_evaluation_id = old_evaluation.evaluation_id
        session.commit()
    mapper_v2 = replace(LEADER_MAPPER, mapper_version="1.0.1")
    monkeypatch.setitem(
        MAPPER_REGISTRY,
        (
            mapper_v2.schema_key,
            mapper_v2.schema_version,
            mapper_v2.mapper_key,
            mapper_v2.mapper_version,
        ),
        mapper_v2,
    )
    with _session(connection) as session:
        preview_id = reprocess_observation(
            session,
            observation_id,
            mapper_key=mapper_v2.mapper_key,
            mapper_version=mapper_v2.mapper_version,
            identity_rule_version="1.0.0",
        )
    with _session(connection) as session:
        assert (
            session.scalar(
                select(func.count())
                .select_from(Evidence)
                .where(Evidence.normalization_result_id == preview_id)
            )
            == 0
        )
        same = recompute_workspace_signals(
            session, workspace_id, evaluation_as_of=evaluation_as_of
        )[0]
        assert same.evaluation_id == old_evaluation_id
        session.rollback()
    with _session(connection) as session:
        new_evidence_id = promote_normalization_result(session, preview_id)
    with _session(connection) as session:
        supersession = session.scalar(select(EvidenceSupersession))
        assert supersession is not None
        assert supersession.old_evidence_id == old_evidence_id
        assert supersession.new_evidence_id == new_evidence_id
        current = recompute_workspace_signals(
            session, workspace_id, evaluation_as_of=evaluation_as_of
        )[0]
        assert current.evaluation_id != old_evaluation_id
        current_id = current.evaluation_id
        session.commit()
    with _session(connection) as session:
        old_links = session.scalars(
            select(EvaluationEvidence.evidence_id).where(
                EvaluationEvidence.evaluation_id == old_evaluation_id
            )
        ).all()
        new_links = session.scalars(
            select(EvaluationEvidence.evidence_id).where(
                EvaluationEvidence.evaluation_id == current_id
            )
        ).all()
        assert old_links == [old_evidence_id]
        assert new_links == [new_evidence_id]
        assert session.get(Evidence, old_evidence_id) is not None
        assert (
            session.scalar(
                select(func.count()).select_from(Action).where(Action.workspace_id == workspace_id)
            )
            == 0
        )
        assert (
            session.scalar(
                select(func.count())
                .select_from(ActionOutcome)
                .join(Action, ActionOutcome.action_id == Action.action_id)
                .where(Action.workspace_id == workspace_id)
            )
            == 0
        )


def test_cross_workspace_public_scope_and_local_api(
    tmp_path: Path, database_scope: tuple[object, UUID]
) -> None:
    connection, workspace_id = database_scope
    batch_id = _import(connection, _csv(tmp_path / "first.csv", [_row()]), workspace_id)
    with _session(connection) as session:
        seed_demo(session)

    def session_override() -> Iterator[Session]:
        with _session(connection) as session:
            yield session

    app.dependency_overrides[get_session] = session_override
    try:
        client = TestClient(app)
        batch_url = f"/api/v1/workspaces/{workspace_id}/ingestion/batches/{batch_id}"
        assert client.get(batch_url).status_code == 200
        assert (
            client.get(f"/api/v1/workspaces/{uuid4()}/ingestion/batches/{batch_id}").status_code
            == 404
        )
        rows = client.get(f"{batch_url}/rows")
        assert rows.status_code == 200
        evidence_id = rows.json()["items"][0]["evidence_id"]
        assert evidence_id is not None
        origin = client.get(
            f"/api/v1/workspaces/{workspace_id}/ingestion/evidence/{evidence_id}/origin"
        )
        assert origin.status_code == 200
        assert origin.json()["batch"]["batch_id"] == str(batch_id)
        assert origin.json()["observation"]["external_record_id"] == "record-1"
        assert origin.json()["normalization"]["account_id"] is not None
        assert client.post(batch_url).status_code == 405
        account = client.get("/api/v1/accounts")
        assert account.status_code == 200
        assert account.json()["workspace"]["workspace_id"] == str(DEMO_WORKSPACE_ID)
        assert len(account.json()["items"]) == 3
        with _session(connection) as session:
            imported_account = session.scalar(
                select(Account).where(Account.workspace_id == workspace_id)
            )
            assert imported_account is not None
            assert client.get(f"/api/v1/accounts/{imported_account.id}").status_code == 404
            assert client.get(f"/api/v1/accounts/{imported_account.id}/signals").status_code == 404
    finally:
        app.dependency_overrides.clear()


def test_exact_domain_match_and_immutable_source_binding(
    tmp_path: Path, database_scope: tuple[object, UUID]
) -> None:
    connection, workspace_id = database_scope
    _import(connection, _csv(tmp_path / "a.csv", [_row()]), workspace_id)
    _import(
        connection,
        _csv(tmp_path / "b.csv", [_row("other-record", "other-source-id")]),
        workspace_id,
    )
    with _session(connection) as session:
        accounts = session.scalars(
            select(Account).where(Account.workspace_id == workspace_id)
        ).all()
        assert len(accounts) == 1
        assert accounts[0].segment is None
        from gtm_state_api.schemas import AccountResponse

        assert AccountResponse.model_validate(accounts[0]).segment is None
        from gtm_state_api.models import AccountSourceId

        bindings = session.scalars(
            select(AccountSourceId).where(AccountSourceId.workspace_id == workspace_id)
        ).all()
        assert len(bindings) == 2
        assert {binding.account_id for binding in bindings} == {accounts[0].id}
        assert all(binding.origin_observation_id is not None for binding in bindings)


def test_source_id_domain_conflict_and_no_name_only_merge(
    tmp_path: Path, database_scope: tuple[object, UUID]
) -> None:
    connection, workspace_id = database_scope
    _import(connection, _csv(tmp_path / "first.csv", [_row()]), workspace_id)
    source_conflict = _import(
        connection,
        _csv(
            tmp_path / "source-conflict.csv",
            [_row("changed-domain", "source-company-1", "Meridian Test Systems", "other.example")],
        ),
        workspace_id,
    )
    name_conflict = _import(
        connection,
        _csv(
            tmp_path / "name-conflict.csv",
            [_row("same-name", "new-source", "Meridian Test Systems", "another.example")],
        ),
        workspace_id,
    )
    with _session(connection) as session:
        rows = session.scalars(
            select(IngestionBatchRow).where(
                IngestionBatchRow.batch_id.in_([source_conflict, name_conflict])
            )
        ).all()
        assert {item.outcome for item in rows} == {IngestionRowOutcome.UNRESOLVED}
        assert {item.reason_code for item in rows} == {
            IngestionReason.SOURCE_ID_CONFLICT,
            IngestionReason.AMBIGUOUS_IDENTITY,
        }
        assert (
            session.scalar(
                select(func.count())
                .select_from(Account)
                .where(Account.workspace_id == workspace_id)
            )
            == 1
        )


def test_conflicting_explicit_fact_assertions_are_preserved(
    tmp_path: Path, database_scope: tuple[object, UUID]
) -> None:
    connection, workspace_id = database_scope
    _import(
        connection,
        _csv(
            tmp_path / "claims.csv",
            [
                _row("positive", "source-company-1", assertion="PRESENT"),
                _row(
                    "negative",
                    "source-company-1",
                    assertion="ABSENT",
                    excerpt="The company explicitly states no revenue leader appointment.",
                ),
            ],
        ),
        workspace_id,
    )
    with _session(connection) as session:
        claims = session.scalars(
            select(Evidence)
            .join(Account, Evidence.account_id == Account.id)
            .where(Account.workspace_id == workspace_id)
        ).all()
        assert len(claims) == 2
        assert {claim.fact_assertion for claim in claims} == {
            EvidenceAssertion.PRESENT,
            EvidenceAssertion.ABSENT,
        }
        assert all(claim.classification is EvidenceClassification.FACT for claim in claims)
        assert all(claim.confidence is None for claim in claims)


def test_later_source_time_creates_another_immutable_observation(
    tmp_path: Path, database_scope: tuple[object, UUID]
) -> None:
    connection, workspace_id = database_scope
    first = _import(connection, _csv(tmp_path / "first.csv", [_row()]), workspace_id)
    second = _import(
        connection,
        _csv(
            tmp_path / "later.csv",
            [_row(observed="2026-09-16T12:00:00Z", event="2026-09-14T12:00:00Z")],
        ),
        workspace_id,
    )
    assert first != second
    with _session(connection) as session:
        observations = session.scalars(
            select(SourceObservation).where(SourceObservation.workspace_id == workspace_id)
        ).all()
        assert len(observations) == 2
        assert len({item.id for item in observations}) == 2
        assert len({item.source_observed_at for item in observations}) == 2
        facts = session.scalars(
            select(Evidence)
            .join(Account, Evidence.account_id == Account.id)
            .where(Account.workspace_id == workspace_id)
        ).all()
        assert len(facts) == 2
        assert {item.observed_at for item in facts} == {datetime(2026, 9, 14, 12, tzinfo=UTC)}


def test_unexpected_mapper_failure_rolls_back_entire_batch(
    tmp_path: Path, database_scope: tuple[object, UUID], monkeypatch: pytest.MonkeyPatch
) -> None:
    connection, workspace_id = database_scope
    original = LEADER_MAPPER.normalize
    calls = 0

    def fail_on_second(source: SourceObservationInput) -> NormalizedFact:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("mapper defect")
        return original(source)

    broken = replace(LEADER_MAPPER, normalize=fail_on_second)
    monkeypatch.setitem(
        MAPPER_REGISTRY,
        (broken.schema_key, broken.schema_version, broken.mapper_key, broken.mapper_version),
        broken,
    )
    with pytest.raises(RuntimeError, match="mapper defect"):
        _import(
            connection,
            _csv(
                tmp_path / "broken.csv",
                [
                    _row("one", "source-one", "One Company", "one.example"),
                    _row("two", "source-two", "Two Company", "two.example"),
                ],
            ),
            workspace_id,
        )
    with _session(connection) as session:
        assert session.scalar(select(func.count()).select_from(IngestionBatch)) == 0
        assert session.scalar(select(func.count()).select_from(SourceObservation)) == 0
        assert (
            session.scalar(
                select(func.count())
                .select_from(Account)
                .where(Account.workspace_id == workspace_id)
            )
            == 0
        )


def test_replay_cannot_move_accepted_claim_to_another_account(
    tmp_path: Path, database_scope: tuple[object, UUID], monkeypatch: pytest.MonkeyPatch
) -> None:
    connection, workspace_id = database_scope
    _import(connection, _csv(tmp_path / "first.csv", [_row()]), workspace_id)
    with _session(connection) as session:
        observation = session.scalar(
            select(SourceObservation).where(SourceObservation.workspace_id == workspace_id)
        )
        assert observation is not None
        observation_id = observation.id
        other = Account(
            id=uuid4(),
            workspace_id=workspace_id,
            slug="other-account",
            canonical_name="Other Company",
            domain="other.example",
            segment=None,
            is_synthetic=False,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        session.add(other)
        session.commit()
        other_id = other.id
    from gtm_state_api.ingestion_identity import IdentityDecision

    def moved(*_args: object, **_kwargs: object) -> IdentityDecision:
        with _session(connection) as session:
            account = session.get(Account, other_id)
            assert account is not None
            return IdentityDecision(account, None, None, "0" * 64)

    monkeypatch.setitem(IDENTITY_RULE_REGISTRY, "1.0.2", moved)
    with _session(connection) as session, pytest.raises(ValueError, match="cannot reassign"):
        reprocess_observation(
            session,
            observation_id,
            mapper_key="public_company_leader_event",
            mapper_version="1.0.0",
            identity_rule_version="1.0.2",
        )
    with _session(connection) as session:
        assert (
            session.scalar(
                select(func.count())
                .select_from(NormalizationResult)
                .where(NormalizationResult.identity_rule_version == "1.0.2")
            )
            == 0
        )


def test_production_ingestion_reads_and_mutations_fail_closed(
    tmp_path: Path, database_scope: tuple[object, UUID], monkeypatch: pytest.MonkeyPatch
) -> None:
    connection, workspace_id = database_scope
    batch_id = _import(connection, _csv(tmp_path / "first.csv", [_row()]), workspace_id)
    from gtm_state_api.config import get_settings

    monkeypatch.setenv("APP_ENV", "production")
    get_settings.cache_clear()
    try:
        client = TestClient(app)
        assert (
            client.get(
                f"/api/v1/workspaces/{workspace_id}/ingestion/batches/{batch_id}"
            ).status_code
            == 404
        )
        assert (
            client.get(
                f"/api/v1/workspaces/{workspace_id}/ingestion/batches/{batch_id}/rows"
            ).status_code
            == 404
        )
        with (
            _session(connection) as session,
            pytest.raises(ValueError, match="unavailable in production"),
        ):
            import_local_csv(session, tmp_path / "first.csv", workspace_id=workspace_id)
    finally:
        monkeypatch.delenv("APP_ENV")
        get_settings.cache_clear()


def test_source_id_preflight_permutations_abstain_before_account_creation(
    tmp_path: Path, database_scope: tuple[object, UUID]
) -> None:
    connection, first_workspace = database_scope
    second_workspace = uuid4()
    with _session(connection) as session:
        session.add(
            Workspace(
                workspace_id=second_workspace,
                slug=f"m2a-test-{second_workspace}",
                name="Permutation workspace",
                demo_mode=False,
                demo_as_of=None,
                created_at=datetime(2026, 10, 3, tzinfo=UTC),
            )
        )
        session.commit()
    rows = [
        _row("one", "shared-external", "One Company", "one.example"),
        _row("two", "shared-external", "Two Company", "two.example"),
        _row("three", "safe-external", "Safe Company", "safe.example"),
    ]
    first = _import(connection, _csv(tmp_path / "first.csv", rows), first_workspace)
    second = _import(
        connection, _csv(tmp_path / "reversed.csv", list(reversed(rows))), second_workspace
    )
    with _session(connection) as session:
        for workspace_id, batch_id in [(first_workspace, first), (second_workspace, second)]:
            found = session.scalars(
                select(IngestionBatchRow).where(IngestionBatchRow.batch_id == batch_id)
            ).all()
            reasons = {item.reason_code for item in found}
            assert reasons == {IngestionReason.SOURCE_ID_CONFLICT, None}
            assert sum(item.outcome is IngestionRowOutcome.UNRESOLVED for item in found) == 2
            assert sum(item.outcome is IngestionRowOutcome.ACCEPTED for item in found) == 1
            accounts = session.scalars(
                select(Account).where(Account.workspace_id == workspace_id)
            ).all()
            assert [item.canonical_name for item in accounts] == ["Safe Company"]


def test_import_creates_no_downstream_materialization(
    tmp_path: Path, database_scope: tuple[object, UUID]
) -> None:
    from gtm_state_api.models import (
        AccountStateSnapshot,
        DecisionEvaluation,
        PolicyEvaluation,
        SignalEvaluation,
    )

    connection, workspace_id = database_scope
    _import(connection, _csv(tmp_path / "input.csv", [_row()]), workspace_id)
    with _session(connection) as session:
        assert (
            session.scalar(
                select(func.count())
                .select_from(SignalEvaluation)
                .where(SignalEvaluation.workspace_id == workspace_id)
            )
            == 0
        )
        assert (
            session.scalar(
                select(func.count())
                .select_from(AccountStateSnapshot)
                .where(AccountStateSnapshot.workspace_id == workspace_id)
            )
            == 0
        )
        assert (
            session.scalar(
                select(func.count())
                .select_from(DecisionEvaluation)
                .where(DecisionEvaluation.workspace_id == workspace_id)
            )
            == 0
        )
        assert (
            session.scalar(
                select(func.count())
                .select_from(PolicyEvaluation)
                .where(PolicyEvaluation.workspace_id == workspace_id)
            )
            == 0
        )
        assert (
            session.scalar(
                select(func.count()).select_from(Action).where(Action.workspace_id == workspace_id)
            )
            == 0
        )
        assert (
            session.scalar(
                select(func.count())
                .select_from(ActionOutcome)
                .join(Action, ActionOutcome.action_id == Action.action_id)
                .where(Action.workspace_id == workspace_id)
            )
            == 0
        )
