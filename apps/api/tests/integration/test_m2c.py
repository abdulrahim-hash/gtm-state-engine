"""Isolated PostgreSQL M2C source-read, replay, and governance tests."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Session

from gtm_state_api import m2c_run, m2c_workspace, private_company_read
from gtm_state_api.database import get_engine
from gtm_state_api.hubspot_company_read import CompanyRead, CompanyRecord, ProviderReadError
from gtm_state_api.models import (
    Account,
    AccountStateSnapshot,
    Action,
    Evidence,
    SourceObservation,
    SourceReadRun,
)
from gtm_state_api.private_company_read import CustomerStageMapping, read_company_into_evidence
from gtm_state_api.types import EvidenceAssertion

pytestmark = pytest.mark.integration
FIXTURE_TIME = datetime(2026, 10, 4, 21, 36, tzinfo=UTC)
OBSERVED = FIXTURE_TIME + timedelta(minutes=1)
AS_OF = FIXTURE_TIME + timedelta(minutes=2)


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


def isolated_workspace(connection: Connection, monkeypatch: pytest.MonkeyPatch) -> UUID:
    workspace_id = uuid4()
    strategy_id = uuid4()
    test_slug = f"m2c-crm-relationship-test-{str(workspace_id)[:8]}"
    monkeypatch.setattr(m2c_workspace, "WORKSPACE_SLUG", test_slug)
    monkeypatch.setattr(private_company_read, "WORKSPACE_SLUG", test_slug)
    monkeypatch.setattr(m2c_workspace, "WORKSPACE_ID", workspace_id)
    monkeypatch.setattr(m2c_workspace, "STRATEGY_ID", strategy_id)
    monkeypatch.setattr(m2c_run, "WORKSPACE_ID", workspace_id)
    monkeypatch.setattr(m2c_run, "STRATEGY_ID", strategy_id)
    with session_for(connection) as session:
        m2c_workspace.setup(session, fixture_as_of=FIXTURE_TIME)
    return workspace_id


def record(
    company_id: str, *, stage: str = "customer", domain: str | None = None, name: str | None = None
) -> CompanyRecord:
    is_customer = company_id == "123"
    return CompanyRecord(
        provider_company_id=company_id,
        company_name=name or ("M2C Customer Test" if is_customer else "M2C Lead Test"),
        company_domain=domain
        or ("m2c-customer.example.com" if is_customer else "m2c-lead.example.com"),
        lifecycle_stage=stage,
        provider_updated_at=FIXTURE_TIME,
    )


def pull(
    connection: Connection,
    workspace_id: UUID,
    company: CompanyRecord,
    *,
    observed_at: datetime = OBSERVED,
) -> UUID:
    def reader(company_id: str, *, credential: str) -> CompanyRead:
        assert credential == "synthetic-fixture-token"
        assert company_id == company.provider_company_id
        return CompanyRead(company, 0, None)

    with session_for(connection) as session:
        return read_company_into_evidence(
            session,
            workspace_id=workspace_id,
            portal_id="12345",
            company_id=company.provider_company_id,
            credential="synthetic-fixture-token",
            mapping=CustomerStageMapping("customer", "1.0.0"),
            observed_at=observed_at,
            reader=reader,
        )


def test_full_crm_read_to_action_and_replay(
    isolated_connection: Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = isolated_workspace(isolated_connection, monkeypatch)
    customer_run = pull(isolated_connection, workspace, record("123"))
    lead_run = pull(isolated_connection, workspace, record("456", stage="lead"))
    with session_for(isolated_connection) as session:
        first = m2c_run.inspect_run(session, customer_run)
        second = m2c_run.inspect_run(session, lead_run)
        assert first["status"] == second["status"] == "SUCCEEDED"
        assert first["evidence"]["assertion"] == "PRESENT"
        assert second["evidence"]["assertion"] == "INCONCLUSIVE"
        assert first["evidence"]["source_uri"] is None
        assert first["downstream_materialized_by_read"] is False
        assert (
            session.scalar(
                select(func.count())
                .select_from(AccountStateSnapshot)
                .where(AccountStateSnapshot.workspace_id == workspace)
            )
            == 0
        )
    with session_for(isolated_connection) as session:
        with pytest.raises(ValueError, match="inspect every"):
            m2c_run.materialize_stage(
                session, stage="signals", as_of=AS_OF, inspected_run_ids=(customer_run,)
            )
        session.rollback()
    first_outputs: dict[str, list[str]] = {}
    for stage in ("signals", "state", "decisions", "policies", "actions"):
        with session_for(isolated_connection) as session:
            output = m2c_run.materialize_stage(
                session,
                stage=stage,
                as_of=AS_OF,
                inspected_run_ids=(customer_run, lead_run),
            )
            assert output["semantic_as_of"] == AS_OF.isoformat()
            assert output["no_external_side_effects"] is True
            assert output["created"] == 2
            first_outputs[stage] = output["output_ids"]
    with session_for(isolated_connection) as session:
        trace = m2c_run.export_trace(session, as_of=AS_OF)
    assert len(trace["accounts"]) == 2
    by_domain = {item["domain"]: item for item in trace["accounts"]}
    customer = by_domain["m2c-customer.example.com"]
    lead = by_domain["m2c-lead.example.com"]
    assert customer["state"]["relationship"] == "EXISTING_RELATIONSHIP"
    assert lead["state"]["relationship"] == "UNKNOWN"
    assert customer["decision"]["result"] == lead["decision"]["result"] == "ENGAGE"
    assert customer["policy"]["result"] == lead["policy"]["result"] == "REQUIRE_REVIEW"
    assert customer["action"]["type"] == "CREATE_SELLER_TASK"
    assert lead["action"]["type"] == "REQUEST_RESEARCH"
    assert customer["policy"]["reason_codes"] == [
        "EXISTING_RELATIONSHIP_REQUIRES_CONTROLLED_HANDLING"
    ]
    assert "RELATIONSHIP_UNKNOWN_REQUIRES_REVIEW" in lead["policy"]["reason_codes"]
    for account_trace in (customer, lead):
        assert account_trace["decision"]["state_snapshot_id"] == account_trace["state"]["id"]
        assert account_trace["policy"]["decision_evaluation_id"] == account_trace["decision"]["id"]
        assert account_trace["action"]["policy_evaluation_id"] == account_trace["policy"]["id"]
    assert customer["relationship_evidence"][0]["source_read_run_id"] == str(customer_run)
    assert lead["relationship_evidence"][0]["source_read_run_id"] == str(lead_run)
    for stage in ("signals", "state", "decisions", "policies", "actions"):
        with session_for(isolated_connection) as session:
            repeated = m2c_run.materialize_stage(
                session,
                stage=stage,
                as_of=AS_OF,
                inspected_run_ids=(customer_run, lead_run),
            )
            assert repeated["created"] == 0
            assert repeated["output_ids"] == first_outputs[stage]
    with session_for(isolated_connection) as session:
        assertions = set(
            session.scalars(
                select(Evidence.fact_assertion).where(
                    Evidence.account_id.in_(
                        select(Account.id).where(Account.workspace_id == workspace)
                    )
                )
            ).all()
        )
        assert EvidenceAssertion.ABSENT not in assertions
        assert (
            session.scalar(
                select(func.count()).select_from(Action).where(Action.workspace_id == workspace)
            )
            == 2
        )


def test_source_identity_idempotency_history_and_same_time_conflict(
    isolated_connection: Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = isolated_workspace(isolated_connection, monkeypatch)
    first = pull(isolated_connection, workspace, record("123"))
    repeat = pull(isolated_connection, workspace, record("123"))
    with session_for(isolated_connection) as session:
        first_run = session.get(SourceReadRun, first)
        repeat_run = session.get(SourceReadRun, repeat)
        assert first_run is not None and repeat_run is not None
        assert first_run.observation_id == repeat_run.observation_id
        assert (
            session.scalar(
                select(func.count())
                .select_from(SourceObservation)
                .where(SourceObservation.workspace_id == workspace)
            )
            == 1
        )
    conflict = pull(
        isolated_connection,
        workspace,
        record("123", stage="lead"),
        observed_at=OBSERVED,
    )
    with session_for(isolated_connection) as session:
        failed = session.get(SourceReadRun, conflict)
        assert failed is not None and failed.status == "CONFLICT"
        assert failed.observation_id is None
        assert (
            session.scalar(
                select(func.count())
                .select_from(SourceObservation)
                .where(SourceObservation.workspace_id == workspace)
            )
            == 1
        )
    later = pull(
        isolated_connection,
        workspace,
        record("123", stage="lead"),
        observed_at=OBSERVED + timedelta(minutes=1),
    )
    with session_for(isolated_connection) as session:
        later_run = session.get(SourceReadRun, later)
        assert later_run is not None and later_run.status == "SUCCEEDED"
        assert later_run.observation_id != first_run.observation_id
        assert (
            session.scalar(
                select(func.count())
                .select_from(SourceObservation)
                .where(SourceObservation.workspace_id == workspace)
            )
            == 2
        )
        session.rollback()
        with pytest.raises(ValueError, match="conflict blocks"):
            m2c_run.materialize_stage(
                session,
                stage="signals",
                as_of=AS_OF + timedelta(minutes=1),
                inspected_run_ids=(first, later),
            )
        session.rollback()


def test_duplicate_provider_id_binding_cannot_merge(
    isolated_connection: Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = isolated_workspace(isolated_connection, monkeypatch)
    pull(isolated_connection, workspace, record("123"))
    duplicate = pull(
        isolated_connection,
        workspace,
        record("789", name="M2C Customer Test", domain="m2c-customer.example.com"),
        observed_at=OBSERVED + timedelta(seconds=1),
    )
    with session_for(isolated_connection) as session:
        result = m2c_run.inspect_run(session, duplicate)
        assert result["status"] == "UNRESOLVED"
        assert result["evidence"] is None
        assert result["normalization"]["outcome"] == "UNRESOLVED"


def test_failed_read_does_not_create_observation_or_absence(
    isolated_connection: Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = isolated_workspace(isolated_connection, monkeypatch)

    def failed(_company_id: str, *, credential: str) -> CompanyRead:
        raise ProviderReadError("UNAUTHORIZED")

    with session_for(isolated_connection) as session:
        run_id = read_company_into_evidence(
            session,
            workspace_id=workspace,
            portal_id="12345",
            company_id="123",
            credential="bad-test-token",
            mapping=CustomerStageMapping("customer", "1.0.0"),
            observed_at=OBSERVED,
            reader=failed,
        )
    with session_for(isolated_connection) as session:
        run = m2c_run.inspect_run(session, run_id)
        assert run["status"] == "FAILED"
        assert run["failure_code"] == "UNAUTHORIZED"
        assert run["observation"] is None
        assert run["evidence"] is None
        assert (
            session.scalar(
                select(func.count())
                .select_from(SourceObservation)
                .where(SourceObservation.workspace_id == workspace)
            )
            == 0
        )


@pytest.mark.parametrize(
    ("changed_domain", "changed_name", "expected_reason"),
    [
        ("wrong.example.com", "M2C Customer Test", "SOURCE_ID_CONFLICT"),
        ("m2c-customer.example.com", "Different Name", "AMBIGUOUS_IDENTITY"),
    ],
)
def test_bound_provider_identity_conflicts_remain_unresolved(
    isolated_connection: Connection,
    monkeypatch: pytest.MonkeyPatch,
    changed_domain: str,
    changed_name: str,
    expected_reason: str,
) -> None:
    workspace = isolated_workspace(isolated_connection, monkeypatch)
    pull(isolated_connection, workspace, record("123"))
    conflicting = pull(
        isolated_connection,
        workspace,
        record("123", domain=changed_domain, name=changed_name),
        observed_at=OBSERVED + timedelta(seconds=1),
    )
    with session_for(isolated_connection) as session:
        run = m2c_run.inspect_run(session, conflicting)
        assert run["status"] == "UNRESOLVED"
        assert run["failure_code"] == expected_reason
        assert run["evidence"] is None


def test_missing_domain_cannot_create_new_account(
    isolated_connection: Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = isolated_workspace(isolated_connection, monkeypatch)
    missing_domain = CompanyRecord(
        provider_company_id="987",
        company_name="Unbound Synthetic Company",
        company_domain=None,
        lifecycle_stage="customer",
        provider_updated_at=FIXTURE_TIME,
    )
    run_id = pull(isolated_connection, workspace, missing_domain)
    with session_for(isolated_connection) as session:
        run = m2c_run.inspect_run(session, run_id)
        assert run["status"] == "UNRESOLVED"
        assert run["failure_code"] == "MISSING_IDENTITY"
        assert run["evidence"] is None


def test_provider_404_records_run_without_relationship_fact(
    isolated_connection: Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = isolated_workspace(isolated_connection, monkeypatch)

    def missing(_company_id: str, *, credential: str) -> CompanyRead:
        return CompanyRead(None, 0, None)

    with session_for(isolated_connection) as session:
        run_id = read_company_into_evidence(
            session,
            workspace_id=workspace,
            portal_id="12345",
            company_id="123",
            credential="synthetic-fixture-token",
            mapping=CustomerStageMapping("customer", "1.0.0"),
            observed_at=OBSERVED,
            reader=missing,
        )
    with session_for(isolated_connection) as session:
        result = m2c_run.inspect_run(session, run_id)
        assert result["status"] == "NOT_FOUND"
        assert result["observation"] is None
        assert result["evidence"] is None
        assert (
            session.scalar(
                select(func.count())
                .select_from(Evidence)
                .where(
                    Evidence.account_id.in_(
                        select(Account.id).where(Account.workspace_id == workspace)
                    ),
                    Evidence.fact_key == "relationship.crm_reports_customer_status",
                )
            )
            == 0
        )


def test_missing_credential_creates_failed_read_run_without_network_or_fact(
    isolated_connection: Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = isolated_workspace(isolated_connection, monkeypatch)
    with session_for(isolated_connection) as session:
        run_id = read_company_into_evidence(
            session,
            workspace_id=workspace,
            portal_id="12345",
            company_id="123",
            credential="",
            mapping=CustomerStageMapping("customer", "1.0.0"),
            observed_at=OBSERVED,
        )
    with session_for(isolated_connection) as session:
        result = m2c_run.inspect_run(session, run_id)
        assert result["status"] == "FAILED"
        assert result["failure_code"] == "MISSING_CREDENTIAL"
        assert result["observation"] is None
        assert result["evidence"] is None


def test_out_of_scope_company_does_not_create_synthetic_account(
    isolated_connection: Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = isolated_workspace(isolated_connection, monkeypatch)
    outside = CompanyRecord(
        provider_company_id="987",
        company_name="Unlisted Test Company",
        company_domain="unlisted.example.com",
        lifecycle_stage="customer",
        provider_updated_at=FIXTURE_TIME,
    )
    run_id = pull(isolated_connection, workspace, outside)
    with session_for(isolated_connection) as session:
        result = m2c_run.inspect_run(session, run_id)
        assert result["status"] == "UNRESOLVED"
        assert result["evidence"] is None
        assert (
            session.scalar(
                select(func.count()).select_from(Account).where(Account.workspace_id == workspace)
            )
            == 2
        )


def test_future_source_observation_cannot_materialize_at_earlier_as_of(
    isolated_connection: Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = isolated_workspace(isolated_connection, monkeypatch)
    customer_run = pull(isolated_connection, workspace, record("123"))
    lead_run = pull(isolated_connection, workspace, record("456", stage="lead"))
    with session_for(isolated_connection) as session:
        with pytest.raises(ValueError, match="after semantic state_as_of"):
            m2c_run.materialize_stage(
                session,
                stage="signals",
                as_of=FIXTURE_TIME,
                inspected_run_ids=(customer_run, lead_run),
            )
        session.rollback()
