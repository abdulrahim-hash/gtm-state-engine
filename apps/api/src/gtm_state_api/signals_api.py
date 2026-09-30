"""Read-only M1B.1 API for definitions, canonical signals, and evaluation traces."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from gtm_state_api.database import get_session
from gtm_state_api.models import (
    Account,
    EvaluationEvidence,
    Evidence,
    Signal,
    SignalDefinition,
    SignalEvaluation,
    StrategyVersion,
    Workspace,
)
from gtm_state_api.schemas import (
    AccountSignalEvaluationListResponse,
    AccountSignalListResponse,
    CanonicalSignalResponse,
    EvidenceResponse,
    SignalDefinitionListResponse,
    SignalDefinitionResponse,
    SignalEvaluationResponse,
    SignalEvaluationTraceResponse,
    SignalReadModel,
    WorkspaceResponse,
)
from gtm_state_api.types import (
    SignalEvaluationResult,
    SignalResolvedFreshness,
    SignalResolvedStatus,
    StrategyStatus,
)

router = APIRouter(prefix="/api/v1", tags=["M1B.1 signal read model"])
SessionDependency = Annotated[Session, Depends(get_session)]


def _not_found(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)


def _active_context(session: Session) -> tuple[Workspace, StrategyVersion]:
    strategy = session.scalar(
        select(StrategyVersion)
        .where(StrategyVersion.status == StrategyStatus.ACTIVE)
        .options(selectinload(StrategyVersion.workspace))
    )
    if strategy is None:
        raise _not_found("active strategy not found")
    return strategy.workspace, strategy


def _account(session: Session, account_id: UUID, workspace_id: UUID) -> Account:
    account = session.scalar(
        select(Account).where(
            Account.id == account_id,
            Account.workspace_id == workspace_id,
        )
    )
    if account is None:
        raise _not_found("account not found")
    return account


def _workspace_response(workspace: Workspace) -> WorkspaceResponse:
    return WorkspaceResponse.model_validate(workspace)


def _definition_response(definition: SignalDefinition) -> SignalDefinitionResponse:
    return SignalDefinitionResponse.model_validate(definition)


def _evaluation_response(evaluation: SignalEvaluation) -> SignalEvaluationResponse:
    return SignalEvaluationResponse.model_validate(evaluation)


def _evidence_for_evaluation(session: Session, evaluation_id: UUID) -> list[Evidence]:
    return list(
        session.scalars(
            select(Evidence)
            .join(
                EvaluationEvidence,
                EvaluationEvidence.evidence_id == Evidence.id,
            )
            .where(EvaluationEvidence.evaluation_id == evaluation_id)
            .order_by(Evidence.observed_at.desc(), Evidence.id)
        ).all()
    )


def _trace_response(
    session: Session,
    evaluation: SignalEvaluation,
    definition: SignalDefinition,
) -> SignalEvaluationTraceResponse:
    return SignalEvaluationTraceResponse(
        evaluation=_evaluation_response(evaluation),
        definition=_definition_response(definition),
        evidence=[
            EvidenceResponse.model_validate(item)
            for item in _evidence_for_evaluation(session, evaluation.evaluation_id)
        ],
    )


def _definition_for_evaluation(session: Session, evaluation: SignalEvaluation) -> SignalDefinition:
    definition = session.get(SignalDefinition, evaluation.signal_definition_id)
    if definition is None:
        raise RuntimeError("evaluation definition is missing")
    return definition


@router.get("/signal-definitions", response_model=SignalDefinitionListResponse)
def list_signal_definitions(
    session: SessionDependency,
) -> SignalDefinitionListResponse:
    """List deterministic definitions governed by the active strategy."""

    workspace, strategy = _active_context(session)
    definitions = session.scalars(
        select(SignalDefinition)
        .where(
            SignalDefinition.workspace_id == workspace.workspace_id,
            SignalDefinition.strategy_version_id == strategy.id,
        )
        .order_by(SignalDefinition.display_name)
    ).all()
    return SignalDefinitionListResponse(
        workspace=_workspace_response(workspace),
        strategy_version_id=strategy.id,
        items=[_definition_response(item) for item in definitions],
    )


@router.get(
    "/accounts/{account_id}/signals",
    response_model=AccountSignalListResponse,
)
def list_account_signals(
    account_id: UUID,
    session: SessionDependency,
) -> AccountSignalListResponse:
    """Return canonical commercial events with status resolved from latest evaluations."""

    workspace, strategy = _active_context(session)
    _account(session, account_id, workspace.workspace_id)
    signals = session.scalars(
        select(Signal)
        .where(
            Signal.workspace_id == workspace.workspace_id,
            Signal.account_id == account_id,
            Signal.strategy_version_id == strategy.id,
        )
        .order_by(Signal.observed_at.desc(), Signal.signal_id)
    ).all()

    items: list[SignalReadModel] = []
    for signal in signals:
        evaluation_statement = (
            select(SignalEvaluation)
            .where(SignalEvaluation.signal_id == signal.signal_id)
            .order_by(
                SignalEvaluation.evaluation_as_of.desc(),
                SignalEvaluation.evaluated_at.desc(),
                SignalEvaluation.evaluation_id.desc(),
            )
        )
        if workspace.demo_as_of is not None:
            evaluation_statement = evaluation_statement.where(
                SignalEvaluation.evaluation_as_of <= workspace.demo_as_of
            )
        evaluation = session.scalar(evaluation_statement.limit(1))
        if evaluation is None:
            raise RuntimeError("canonical signal has no applicable evaluation")
        definition = _definition_for_evaluation(session, evaluation)
        if evaluation.result is SignalEvaluationResult.DETECTED:
            resolved_status = SignalResolvedStatus.ACTIVE
            resolved_freshness = SignalResolvedFreshness.CURRENT
        elif evaluation.result is SignalEvaluationResult.STALE:
            resolved_status = SignalResolvedStatus.EXPIRED
            resolved_freshness = SignalResolvedFreshness.STALE
        else:
            raise RuntimeError("canonical signal has a non-affirmative evaluation")
        items.append(
            SignalReadModel(
                signal=CanonicalSignalResponse.model_validate(signal),
                definition=_definition_response(definition),
                current_evaluation=_evaluation_response(evaluation),
                current_status=resolved_status,
                current_freshness=resolved_freshness,
                evidence=[
                    EvidenceResponse.model_validate(item)
                    for item in _evidence_for_evaluation(session, evaluation.evaluation_id)
                ],
            )
        )

    return AccountSignalListResponse(
        workspace=_workspace_response(workspace),
        account_id=account_id,
        items=items,
    )


@router.get(
    "/accounts/{account_id}/signal-evaluations",
    response_model=AccountSignalEvaluationListResponse,
)
def list_account_signal_evaluations(
    account_id: UUID,
    session: SessionDependency,
    result: Annotated[SignalEvaluationResult | None, Query()] = None,
) -> AccountSignalEvaluationListResponse:
    """Return affirmative, negative, stale, and inconclusive evaluation history."""

    workspace, strategy = _active_context(session)
    _account(session, account_id, workspace.workspace_id)
    statement = select(SignalEvaluation).where(
        SignalEvaluation.workspace_id == workspace.workspace_id,
        SignalEvaluation.account_id == account_id,
        SignalEvaluation.strategy_version_id == strategy.id,
    )
    if result is not None:
        statement = statement.where(SignalEvaluation.result == result)
    evaluations = session.scalars(
        statement.order_by(
            SignalEvaluation.evaluation_as_of.desc(),
            SignalEvaluation.evaluated_at.desc(),
            SignalEvaluation.evaluation_id,
        )
    ).all()
    return AccountSignalEvaluationListResponse(
        workspace=_workspace_response(workspace),
        account_id=account_id,
        items=[
            _trace_response(
                session,
                evaluation,
                _definition_for_evaluation(session, evaluation),
            )
            for evaluation in evaluations
        ],
    )


@router.get(
    "/signal-evaluations/{evaluation_id}",
    response_model=SignalEvaluationTraceResponse,
)
def get_signal_evaluation(
    evaluation_id: UUID,
    session: SessionDependency,
) -> SignalEvaluationTraceResponse:
    """Return one reproducible evaluation and its relational evidence trace."""

    workspace, strategy = _active_context(session)
    evaluation = session.scalar(
        select(SignalEvaluation).where(
            SignalEvaluation.evaluation_id == evaluation_id,
            SignalEvaluation.workspace_id == workspace.workspace_id,
            SignalEvaluation.strategy_version_id == strategy.id,
        )
    )
    if evaluation is None:
        raise _not_found("signal evaluation not found")
    return _trace_response(
        session,
        evaluation,
        _definition_for_evaluation(session, evaluation),
    )
