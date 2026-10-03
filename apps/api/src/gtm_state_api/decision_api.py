"""Read-only M1C API for immutable Decision and Policy evaluations."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from gtm_state_api.database import get_session
from gtm_state_api.models import (
    Account,
    AccountStateSnapshot,
    DecisionDefinition,
    DecisionEvaluation,
    DecisionEvaluationReason,
    PolicyDefinition,
    PolicyEvaluation,
    PolicyEvaluationReason,
    StrategyVersion,
    Workspace,
)
from gtm_state_api.schemas import (
    AccountDecisionHistoryResponse,
    AccountStateSnapshotResponse,
    DecisionDefinitionResponse,
    DecisionEvaluationReasonResponse,
    DecisionEvaluationResponse,
    DecisionPolicyDetailResponse,
    DecisionPolicyHistoryItemResponse,
    DecisionTraceResponse,
    PolicyDefinitionResponse,
    PolicyEvaluationReasonResponse,
    PolicyEvaluationResponse,
    PolicyTraceResponse,
    ProposedDispositionResponse,
    WorkspaceResponse,
)
from gtm_state_api.state_read_service import current_materialized_state_snapshot
from gtm_state_api.types import (
    DecisionResult,
    EvaluationDefinitionStatus,
    PolicyTarget,
    StrategyStatus,
)

router = APIRouter(prefix="/api/v1", tags=["M1C Decision and Policy read model"])
SessionDependency = Annotated[Session, Depends(get_session)]


def _not_found(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)


def _account(session: Session, account_id: UUID) -> Account:
    account = session.get(Account, account_id)
    if account is None:
        raise _not_found("account not found")
    return account


def _workspace(session: Session, workspace_id: UUID) -> Workspace:
    workspace = session.get(Workspace, workspace_id)
    if workspace is None:
        raise _not_found("workspace not found")
    return workspace


def _active_strategy(session: Session, workspace_id: UUID) -> StrategyVersion:
    strategy = session.scalar(
        select(StrategyVersion).where(
            StrategyVersion.workspace_id == workspace_id,
            StrategyVersion.status == StrategyStatus.ACTIVE,
        )
    )
    if strategy is None:
        raise _not_found("active strategy not found")
    return strategy


def _response_label(result: DecisionResult) -> str:
    labels = {
        DecisionResult.ENGAGE: "Engagement merits consideration",
        DecisionResult.HOLD: "Hold until a future state change",
        DecisionResult.NO_ACTION: "No engagement response proposed",
        DecisionResult.ABSTAIN: "Insufficient basis to propose a response",
    }
    return labels[result]


def _decision_trace(
    session: Session,
    evaluation: DecisionEvaluation,
) -> DecisionTraceResponse:
    definition = session.get(DecisionDefinition, evaluation.decision_definition_id)
    if definition is None:
        raise RuntimeError("Decision evaluation definition is missing")
    reasons = session.scalars(
        select(DecisionEvaluationReason)
        .where(DecisionEvaluationReason.decision_evaluation_id == evaluation.decision_evaluation_id)
        .order_by(DecisionEvaluationReason.position)
    ).all()
    return DecisionTraceResponse(
        definition=DecisionDefinitionResponse.model_validate(definition),
        evaluation=DecisionEvaluationResponse.model_validate(evaluation),
        reasons=[DecisionEvaluationReasonResponse.model_validate(item) for item in reasons],
    )


def _policy_trace(
    session: Session,
    evaluation: PolicyEvaluation,
) -> PolicyTraceResponse:
    definition = session.get(PolicyDefinition, evaluation.policy_definition_id)
    if definition is None:
        raise RuntimeError("Policy evaluation definition is missing")
    reasons = session.scalars(
        select(PolicyEvaluationReason)
        .where(PolicyEvaluationReason.policy_evaluation_id == evaluation.policy_evaluation_id)
        .order_by(PolicyEvaluationReason.position)
    ).all()
    return PolicyTraceResponse(
        definition=PolicyDefinitionResponse.model_validate(definition),
        evaluation=PolicyEvaluationResponse.model_validate(evaluation),
        reasons=[PolicyEvaluationReasonResponse.model_validate(item) for item in reasons],
    )


def _history_item(
    session: Session,
    snapshot: AccountStateSnapshot,
    decision: DecisionEvaluation,
    policy: PolicyEvaluation,
) -> DecisionPolicyHistoryItemResponse:
    return DecisionPolicyHistoryItemResponse(
        state_snapshot=AccountStateSnapshotResponse.model_validate(snapshot),
        decision=_decision_trace(session, decision),
        policy=_policy_trace(session, policy),
        disposition=ProposedDispositionResponse(
            state_snapshot_id=snapshot.state_snapshot_id,
            decision_evaluation_id=decision.decision_evaluation_id,
            policy_evaluation_id=policy.policy_evaluation_id,
            proposed_response=decision.result,
            proposed_response_label=_response_label(decision.result),
            policy_result=policy.result,
        ),
    )


def _detail_response(
    session: Session,
    workspace: Workspace,
    snapshot: AccountStateSnapshot,
    decision: DecisionEvaluation,
    policy: PolicyEvaluation,
) -> DecisionPolicyDetailResponse:
    item = _history_item(session, snapshot, decision, policy)
    return DecisionPolicyDetailResponse(
        workspace=WorkspaceResponse.model_validate(workspace),
        **item.model_dump(),
    )


def _enabled_policy_for_decision(
    session: Session,
    decision: DecisionEvaluation,
) -> PolicyEvaluation | None:
    return session.scalar(
        select(PolicyEvaluation)
        .join(
            PolicyDefinition,
            PolicyDefinition.policy_definition_id == PolicyEvaluation.policy_definition_id,
        )
        .where(
            PolicyEvaluation.decision_evaluation_id == decision.decision_evaluation_id,
            PolicyDefinition.status == EvaluationDefinitionStatus.ENABLED,
            PolicyDefinition.target == PolicyTarget.PROSPECTING_ACTIVATION,
        )
        .order_by(PolicyEvaluation.evaluated_at.desc(), PolicyEvaluation.policy_evaluation_id)
        .limit(1)
    )


@router.get(
    "/accounts/{account_id}/decision",
    response_model=DecisionPolicyDetailResponse,
)
def get_current_account_decision(
    account_id: UUID,
    session: SessionDependency,
) -> DecisionPolicyDetailResponse:
    """Return persisted Decision and Policy; ENGAGE means consideration, never execution."""

    account = _account(session, account_id)
    workspace = _workspace(session, account.workspace_id)
    strategy = _active_strategy(session, workspace.workspace_id)
    snapshot = current_materialized_state_snapshot(
        session,
        workspace=workspace,
        account_id=account.id,
        strategy_version_id=strategy.id,
    )
    if snapshot is None:
        raise _not_found("current account state snapshot not found")
    decision = session.scalar(
        select(DecisionEvaluation)
        .join(
            DecisionDefinition,
            DecisionDefinition.decision_definition_id == DecisionEvaluation.decision_definition_id,
        )
        .where(
            DecisionEvaluation.state_snapshot_id == snapshot.state_snapshot_id,
            DecisionDefinition.status == EvaluationDefinitionStatus.ENABLED,
        )
        .limit(1)
    )
    if decision is None:
        raise _not_found(
            "Decision is not materialized for the current exact account-state snapshot"
        )
    policy = _enabled_policy_for_decision(session, decision)
    if policy is None:
        raise _not_found(
            "Policy is not materialized for the current exact Decision and state snapshot"
        )
    return _detail_response(session, workspace, snapshot, decision, policy)


@router.get(
    "/accounts/{account_id}/decision/history",
    response_model=AccountDecisionHistoryResponse,
)
def list_account_decision_history(
    account_id: UUID,
    session: SessionDependency,
    strategy_version_id: Annotated[UUID | None, Query()] = None,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> AccountDecisionHistoryResponse:
    """Return previously materialized immutable Decision and Policy pairs only."""

    account = _account(session, account_id)
    workspace = _workspace(session, account.workspace_id)
    statement = (
        select(DecisionEvaluation)
        .join(
            AccountStateSnapshot,
            AccountStateSnapshot.state_snapshot_id == DecisionEvaluation.state_snapshot_id,
        )
        .where(
            DecisionEvaluation.workspace_id == workspace.workspace_id,
            DecisionEvaluation.account_id == account.id,
        )
    )
    if strategy_version_id is not None:
        strategy_exists = session.scalar(
            select(StrategyVersion.id).where(
                StrategyVersion.id == strategy_version_id,
                StrategyVersion.workspace_id == workspace.workspace_id,
            )
        )
        if strategy_exists is None:
            raise _not_found("strategy version not found")
        statement = statement.where(DecisionEvaluation.strategy_version_id == strategy_version_id)
    decisions = session.scalars(
        statement.order_by(
            AccountStateSnapshot.state_as_of.desc(),
            AccountStateSnapshot.computed_at.desc(),
            DecisionEvaluation.evaluated_at.desc(),
            DecisionEvaluation.decision_evaluation_id.desc(),
        )
        .limit(limit)
        .offset(offset)
    ).all()
    items: list[DecisionPolicyHistoryItemResponse] = []
    for decision in decisions:
        policy = session.scalar(
            select(PolicyEvaluation)
            .where(PolicyEvaluation.decision_evaluation_id == decision.decision_evaluation_id)
            .order_by(
                PolicyEvaluation.evaluated_at.desc(),
                PolicyEvaluation.policy_evaluation_id.desc(),
            )
            .limit(1)
        )
        snapshot = session.get(AccountStateSnapshot, decision.state_snapshot_id)
        if policy is None or snapshot is None:
            raise RuntimeError("materialized Decision history has incomplete provenance")
        items.append(_history_item(session, snapshot, decision, policy))
    return AccountDecisionHistoryResponse(
        workspace=WorkspaceResponse.model_validate(workspace),
        account_id=account.id,
        items=items,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/decision-evaluations/{decision_evaluation_id}",
    response_model=DecisionPolicyDetailResponse,
)
def get_decision_evaluation(
    decision_evaluation_id: UUID,
    session: SessionDependency,
) -> DecisionPolicyDetailResponse:
    """Return one immutable Decision, its Policy, and exact snapshot reference."""

    decision = session.get(DecisionEvaluation, decision_evaluation_id)
    if decision is None:
        raise _not_found("Decision evaluation not found")
    policy = session.scalar(
        select(PolicyEvaluation)
        .where(PolicyEvaluation.decision_evaluation_id == decision.decision_evaluation_id)
        .order_by(
            PolicyEvaluation.evaluated_at.desc(),
            PolicyEvaluation.policy_evaluation_id.desc(),
        )
        .limit(1)
    )
    if policy is None:
        raise _not_found("Policy evaluation is not materialized for this Decision")
    snapshot = session.get(AccountStateSnapshot, decision.state_snapshot_id)
    if snapshot is None:
        raise RuntimeError("Decision state snapshot is missing")
    workspace = _workspace(session, decision.workspace_id)
    return _detail_response(session, workspace, snapshot, decision, policy)


@router.get(
    "/policy-evaluations/{policy_evaluation_id}",
    response_model=DecisionPolicyDetailResponse,
)
def get_policy_evaluation(
    policy_evaluation_id: UUID,
    session: SessionDependency,
) -> DecisionPolicyDetailResponse:
    """Return one immutable Policy, its Decision, and exact snapshot reference."""

    policy = session.get(PolicyEvaluation, policy_evaluation_id)
    if policy is None:
        raise _not_found("Policy evaluation not found")
    decision = session.get(DecisionEvaluation, policy.decision_evaluation_id)
    if decision is None:
        raise RuntimeError("Policy Decision evaluation is missing")
    snapshot = session.get(AccountStateSnapshot, policy.state_snapshot_id)
    if snapshot is None:
        raise RuntimeError("Policy state snapshot is missing")
    workspace = _workspace(session, policy.workspace_id)
    return _detail_response(session, workspace, snapshot, decision, policy)
