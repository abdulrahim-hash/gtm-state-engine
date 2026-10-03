"""Read-only M1A API for the active strategy, accounts, and provenance."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from gtm_state_api.database import get_session
from gtm_state_api.demo_seed import DEMO_WORKSPACE_ID
from gtm_state_api.models import Account, Evidence, StrategyVersion, Workspace
from gtm_state_api.schemas import (
    AccountDetailResponse,
    AccountListResponse,
    AccountResponse,
    ActiveStrategyResponse,
    EvidenceListResponse,
    EvidenceResponse,
    StrategyResponse,
    WorkspaceResponse,
)
from gtm_state_api.types import StrategyStatus

router = APIRouter(prefix="/api/v1", tags=["M1A read model"])
SessionDependency = Annotated[Session, Depends(get_session)]


def _not_found(detail: str) -> HTTPException:
    """Return a concise public not-found response."""

    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)


def _workspace_response(workspace: Workspace) -> WorkspaceResponse:
    return WorkspaceResponse.model_validate(workspace)


def _evidence_response(evidence: Evidence) -> EvidenceResponse:
    return EvidenceResponse.model_validate(evidence)


def _account_response(account: Account) -> AccountResponse:
    return AccountResponse.model_validate(account)


def _active_strategy(session: Session) -> StrategyVersion:
    statement = (
        select(StrategyVersion)
        .where(
            StrategyVersion.status == StrategyStatus.ACTIVE,
            StrategyVersion.workspace_id == DEMO_WORKSPACE_ID,
        )
        .options(selectinload(StrategyVersion.workspace), selectinload(StrategyVersion.evidence))
    )
    strategy = session.scalar(statement)
    if strategy is None:
        raise _not_found("active strategy not found")
    return strategy


@router.get("/strategy/active", response_model=ActiveStrategyResponse)
def get_active_strategy(session: SessionDependency) -> ActiveStrategyResponse:
    """Return the workspace's active synthetic strategy and its evidence-backed claims."""

    strategy = _active_strategy(session)
    return ActiveStrategyResponse(
        workspace=_workspace_response(strategy.workspace),
        strategy=StrategyResponse(
            id=strategy.id,
            workspace_id=strategy.workspace_id,
            semantic_version=strategy.semantic_version,
            status=strategy.status,
            name=strategy.name,
            summary=strategy.summary,
            synthetic_disclaimer=strategy.synthetic_disclaimer,
            created_at=strategy.created_at,
            activated_at=strategy.activated_at,
            claims=[_evidence_response(item) for item in strategy.evidence],
        ),
    )


@router.get("/accounts", response_model=AccountListResponse)
def list_accounts(
    session: SessionDependency,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> AccountListResponse:
    """List canonical accounts belonging to the active strategy's workspace."""

    strategy = _active_strategy(session)
    accounts = session.scalars(
        select(Account)
        .where(Account.workspace_id == strategy.workspace_id)
        .order_by(Account.canonical_name)
        .limit(limit)
        .offset(offset)
    ).all()
    return AccountListResponse(
        workspace=_workspace_response(strategy.workspace),
        items=[_account_response(account) for account in accounts],
        limit=limit,
        offset=offset,
    )


@router.get("/accounts/{account_id}", response_model=AccountDetailResponse)
def get_account(account_id: UUID, session: SessionDependency) -> AccountDetailResponse:
    """Return one canonical account without deriving state or policy."""

    strategy = _active_strategy(session)
    account = session.scalar(
        select(Account).where(
            Account.id == account_id, Account.workspace_id == strategy.workspace_id
        )
    )
    if account is None:
        raise _not_found("account not found")
    return AccountDetailResponse(
        workspace=_workspace_response(strategy.workspace), account=_account_response(account)
    )


@router.get("/evidence", response_model=EvidenceListResponse)
def list_evidence(
    session: SessionDependency,
    account_id: UUID | None = None,
    strategy_version_id: UUID | None = None,
) -> EvidenceListResponse:
    """List provenance for exactly one account or strategy-version target."""

    if (account_id is None) == (strategy_version_id is None):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="provide exactly one account_id or strategy_version_id",
        )

    strategy = _active_strategy(session)
    if account_id is not None:
        account = session.scalar(
            select(Account.id).where(
                Account.id == account_id, Account.workspace_id == strategy.workspace_id
            )
        )
        if account is None:
            raise _not_found("account not found")
        statement = select(Evidence).where(Evidence.account_id == account_id)
    else:
        if strategy_version_id != strategy.id:
            raise _not_found("strategy version not found")
        statement = select(Evidence).where(Evidence.strategy_version_id == strategy_version_id)

    evidence = session.scalars(statement.order_by(Evidence.observed_at.desc())).all()
    return EvidenceListResponse(items=[_evidence_response(item) for item in evidence])
