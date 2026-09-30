"""PostgreSQL integration tests for the M1A synthetic vertical-slice foundation."""

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from gtm_state_api.database import get_session_factory
from gtm_state_api.demo_seed import (
    DEMO_ACCOUNTS,
    DEMO_STRATEGY_ID,
    DEMO_WORKSPACE_ID,
    seed_demo,
)
from gtm_state_api.main import app
from gtm_state_api.models import Account, Evidence, StrategyVersion, Workspace
from gtm_state_api.types import (
    EvidenceClassification,
    EvidenceFreshness,
    StrategyStatus,
    StrategyTopic,
)

pytestmark = pytest.mark.integration


def test_seed_is_idempotent_and_preserves_synthetic_strategy_hypotheses() -> None:
    with get_session_factory()() as session:
        seed_demo(session)
        first_count = session.scalar(select(func.count()).select_from(Evidence))
        seed_demo(session)
        second_count = session.scalar(select(func.count()).select_from(Evidence))
        strategy = session.scalar(select(StrategyVersion))
        assert strategy is not None
        accounts = session.scalars(
            select(Account).where(Account.workspace_id == DEMO_WORKSPACE_ID)
        ).all()
        strategy_claims = session.scalars(
            select(Evidence).where(Evidence.strategy_version_id == strategy.id)
        ).all()

    assert first_count == second_count == 24
    assert len(accounts) == len(DEMO_ACCOUNTS) == 3
    assert len(strategy_claims) == 12
    assert {item.classification for item in strategy_claims} == {EvidenceClassification.HYPOTHESIS}
    assert all(item.raw_payload_hash is not None for item in strategy_claims)


def test_workspace_scopes_account_domain_uniqueness() -> None:
    with get_session_factory()() as session:
        seed_demo(session)
        timestamp = session.scalar(select(Account.created_at).limit(1))
        duplicate = Account(
            id=uuid4(),
            workspace_id=DEMO_WORKSPACE_ID,
            slug="duplicate-domain",
            canonical_name="Duplicate Synthetic Account",
            domain=DEMO_ACCOUNTS[0]["domain"],
            segment="Synthetic segment",
            is_synthetic=True,
            created_at=timestamp,
            updated_at=timestamp,
        )
        session.add(duplicate)
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()


def test_workspace_boundary_allows_domain_reuse_but_one_active_strategy() -> None:
    with get_session_factory()() as session:
        seed_demo(session)
        timestamp = session.scalar(select(Account.created_at).limit(1))
        assert timestamp is not None
        other_workspace_id = uuid4()
        session.add(
            Workspace(
                workspace_id=other_workspace_id,
                slug=f"synthetic-secondary-{other_workspace_id}",
                name="Synthetic Secondary Workspace",
                demo_mode=True,
                demo_as_of=timestamp,
                created_at=timestamp,
            )
        )
        session.add(
            Account(
                id=uuid4(),
                workspace_id=other_workspace_id,
                slug="reused-domain",
                canonical_name="Reused Domain Synthetic Account",
                domain=DEMO_ACCOUNTS[0]["domain"],
                segment="Synthetic segment",
                is_synthetic=True,
                created_at=timestamp,
                updated_at=timestamp,
            )
        )
        session.add(
            StrategyVersion(
                id=uuid4(),
                workspace_id=other_workspace_id,
                semantic_version="1.0.0",
                status=StrategyStatus.ACTIVE,
                name="Secondary active strategy",
                summary="Synthetic workspace-scope constraint test.",
                synthetic_disclaimer="Synthetic workspace-scope constraint test.",
                created_at=timestamp,
                activated_at=timestamp,
            )
        )
        session.flush()
        session.rollback()
        session.add(
            StrategyVersion(
                id=uuid4(),
                workspace_id=DEMO_WORKSPACE_ID,
                semantic_version="2.0.0",
                status=StrategyStatus.ACTIVE,
                name="Duplicate active strategy",
                summary="Synthetic constraint test.",
                synthetic_disclaimer="Synthetic constraint test.",
                created_at=timestamp,
                activated_at=timestamp,
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()


def test_database_rejects_evidence_with_two_targets() -> None:
    with get_session_factory()() as session:
        seed_demo(session)
        timestamp = session.scalar(select(Account.created_at).limit(1))
        assert timestamp is not None
        session.add(
            Evidence(
                id=uuid4(),
                strategy_version_id=DEMO_STRATEGY_ID,
                account_id=DEMO_ACCOUNTS[0]["id"],
                strategy_topic=StrategyTopic.MARKET,
                classification=EvidenceClassification.FACT,
                source_provider="synthetic_demo_fixture",
                source_reference="synthetic://invalid/evidence",
                source_uri=None,
                observed_at=timestamp,
                ingested_at=timestamp,
                normalized_fact="Invalid two-target synthetic evidence.",
                raw_payload_hash=None,
                freshness=EvidenceFreshness.CURRENT,
                confidence=None,
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()


def test_read_only_m1a_endpoints_and_failure_paths() -> None:
    with get_session_factory()() as session:
        seed_demo(session)

    with TestClient(app) as client:
        strategy = client.get("/api/v1/strategy/active")
        assert strategy.status_code == 200
        strategy_body = strategy.json()
        assert strategy_body["workspace"]["demo_as_of"] == "2026-09-15T12:00:00Z"
        assert len(strategy_body["strategy"]["claims"]) == 12
        assert {claim["classification"] for claim in strategy_body["strategy"]["claims"]} == {
            "HYPOTHESIS"
        }

        accounts = client.get("/api/v1/accounts")
        assert accounts.status_code == 200
        assert len(accounts.json()["items"]) == 3
        account_id = accounts.json()["items"][0]["id"]

        assert client.get(f"/api/v1/accounts/{account_id}").status_code == 200
        evidence = client.get(f"/api/v1/evidence?account_id={account_id}")
        assert evidence.status_code == 200
        assert all(item["classification"] == "FACT" for item in evidence.json()["items"])
        assert client.get("/api/v1/evidence").status_code == 422
        assert client.get(f"/api/v1/accounts/{uuid4()}").status_code == 404
        assert client.get("/api/v1/accounts/not-a-uuid").status_code == 422
