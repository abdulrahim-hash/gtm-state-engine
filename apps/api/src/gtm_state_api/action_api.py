"""M1D Action, Review, dry-run, Outcome, and end-to-end trace API."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Body, Depends, Header, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from gtm_state_api.action_engine import (
    ACTION_DERIVATION_KEY,
    ACTION_DERIVATION_VERSION,
    derive_action,
    policy_chain,
)
from gtm_state_api.action_workflow import (
    IDEMPOTENCY_KEY_PATTERN,
    LOCAL_DEMO_REQUESTER_REF,
    LOCAL_DEMO_REVIEWER_REF,
    ActionTransitionError,
    IdempotencyConflictError,
    action_lifecycle,
    create_action_review,
    run_action_dry_run,
)
from gtm_state_api.config import get_settings
from gtm_state_api.database import get_session
from gtm_state_api.decision_api import (
    _detail_response as decision_detail_response,
)
from gtm_state_api.decision_api import (
    _enabled_policy_for_decision,
)
from gtm_state_api.demo_seed import DEMO_WORKSPACE_ID
from gtm_state_api.models import (
    Account,
    AccountStateSnapshot,
    Action,
    ActionAttempt,
    ActionOutcome,
    ActionReview,
    DecisionDefinition,
    DecisionEvaluation,
    Evidence,
    PolicyEvaluation,
    StrategyVersion,
    Workspace,
)
from gtm_state_api.schemas import (
    AccountActionHistoryResponse,
    ActionAttemptResponse,
    ActionAttemptTraceResponse,
    ActionDetailResponse,
    ActionDryRunMutationResponse,
    ActionOutcomeListResponse,
    ActionOutcomeResponse,
    ActionResponse,
    ActionReviewMutationResponse,
    ActionReviewRequest,
    ActionReviewResponse,
    ActionTraceResponse,
    CurrentAccountActionResponse,
    CurrentActionProjectionResponse,
    EvidenceResponse,
    StrategyResponse,
    WorkspaceResponse,
)
from gtm_state_api.state_api import _detail_response as state_detail_response
from gtm_state_api.state_read_service import current_materialized_state_snapshot
from gtm_state_api.types import (
    ActionActorKind,
    ActionCurrentProjection,
    EvaluationDefinitionStatus,
)

router = APIRouter(prefix="/api/v1", tags=["M1D governed Action and Outcome"])
SessionDependency = Annotated[Session, Depends(get_session)]


def _not_found(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)


def _account(session: Session, account_id: UUID) -> Account:
    account = session.get(Account, account_id)
    if account is None or account.workspace_id != DEMO_WORKSPACE_ID:
        raise _not_found("account not found")
    return account


def _workspace(session: Session, workspace_id: UUID) -> Workspace:
    workspace = session.get(Workspace, workspace_id)
    if workspace is None or workspace.workspace_id != DEMO_WORKSPACE_ID:
        raise _not_found("workspace not found")
    return workspace


def _current_disposition(
    session: Session,
    account: Account,
) -> tuple[Workspace, AccountStateSnapshot, DecisionEvaluation, PolicyEvaluation]:
    workspace = _workspace(session, account.workspace_id)
    strategy = session.scalar(
        select(StrategyVersion).where(
            StrategyVersion.workspace_id == workspace.workspace_id,
            StrategyVersion.status == "ACTIVE",
        )
    )
    if strategy is None:
        raise _not_found("active strategy not found")
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
        raise _not_found("Decision is not materialized for the current state snapshot")
    policy = _enabled_policy_for_decision(session, decision)
    if policy is None:
        raise _not_found("Policy is not materialized for the current Decision")
    return workspace, snapshot, decision, policy


def _attempt_trace(
    session: Session,
    attempt: ActionAttempt,
) -> ActionAttemptTraceResponse:
    outcome = session.scalar(
        select(ActionOutcome).where(ActionOutcome.action_attempt_id == attempt.action_attempt_id)
    )
    if outcome is None:
        raise RuntimeError("Action Attempt has no terminal Outcome")
    return ActionAttemptTraceResponse(
        attempt=ActionAttemptResponse.model_validate(attempt),
        outcome=ActionOutcomeResponse.model_validate(outcome),
    )


def _action_detail(session: Session, action: Action) -> ActionDetailResponse:
    review = session.scalar(select(ActionReview).where(ActionReview.action_id == action.action_id))
    attempts = session.scalars(
        select(ActionAttempt)
        .where(ActionAttempt.action_id == action.action_id)
        .order_by(ActionAttempt.attempted_at, ActionAttempt.action_attempt_id)
    ).all()
    return ActionDetailResponse(
        action=ActionResponse.model_validate(action),
        lifecycle=action_lifecycle(session, action, review=review),
        review=(None if review is None else ActionReviewResponse.model_validate(review)),
        attempts=[_attempt_trace(session, attempt) for attempt in attempts],
        mutations_enabled=get_settings().action_mutations_enabled,
    )


def _require_mutations_enabled() -> None:
    if not get_settings().action_mutations_enabled:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Action mutations are disabled in this environment",
        )


@router.get(
    "/accounts/{account_id}/action",
    response_model=CurrentAccountActionResponse,
)
def get_current_account_action(
    account_id: UUID,
    session: SessionDependency,
) -> CurrentAccountActionResponse:
    """Return the current M1D projection separately from persisted Action history."""

    account = _account(session, account_id)
    workspace, snapshot, decision, policy = _current_disposition(session, account)
    (
        _,
        policy_definition,
        chain_decision,
        _,
        ordered_reasons,
    ) = policy_chain(session, policy.policy_evaluation_id)
    derivation = derive_action(
        decision=chain_decision,
        policy=policy,
        policy_target=policy_definition.target,
        ordered_reason_codes=ordered_reasons,
    )
    action_detail: ActionDetailResponse | None = None
    projection = derivation.projection
    if projection is ActionCurrentProjection.ACTION_PROPOSED:
        action = session.scalar(
            select(Action).where(
                Action.policy_evaluation_id == policy.policy_evaluation_id,
                Action.derivation_key == ACTION_DERIVATION_KEY,
                Action.derivation_version == ACTION_DERIVATION_VERSION,
            )
        )
        if action is None:
            raise _not_found("Action is not materialized for the current exact Policy")
        action_detail = _action_detail(session, action)
    return CurrentAccountActionResponse(
        workspace=WorkspaceResponse.model_validate(workspace),
        account_id=account.id,
        upstream=decision_detail_response(
            session,
            workspace,
            snapshot,
            decision,
            policy,
        ),
        current=CurrentActionProjectionResponse(
            projection=projection,
            policy_evaluation_id=policy.policy_evaluation_id,
            policy_result=policy.result,
            policy_reason_codes=list(ordered_reasons),
            action=action_detail,
        ),
    )


@router.get(
    "/accounts/{account_id}/actions",
    response_model=AccountActionHistoryResponse,
)
def list_account_action_history(
    account_id: UUID,
    session: SessionDependency,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> AccountActionHistoryResponse:
    """Return persisted Actions only; BLOCK and abstention projections are excluded."""

    account = _account(session, account_id)
    workspace = _workspace(session, account.workspace_id)
    actions = session.scalars(
        select(Action)
        .where(
            Action.workspace_id == workspace.workspace_id,
            Action.account_id == account.id,
        )
        .order_by(Action.proposed_at.desc(), Action.action_id.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    return AccountActionHistoryResponse(
        workspace=WorkspaceResponse.model_validate(workspace),
        account_id=account.id,
        items=[_action_detail(session, action) for action in actions],
        limit=limit,
        offset=offset,
    )


@router.get("/actions/{action_id}", response_model=ActionDetailResponse)
def get_action(
    action_id: UUID,
    session: SessionDependency,
) -> ActionDetailResponse:
    """Return one immutable Action proposal and its projected governance state."""

    action = session.get(Action, action_id)
    if action is None:
        raise _not_found("Action not found")
    _workspace(session, action.workspace_id)
    return _action_detail(session, action)


@router.get(
    "/actions/{action_id}/outcomes",
    response_model=ActionOutcomeListResponse,
)
def list_action_outcomes(
    action_id: UUID,
    session: SessionDependency,
) -> ActionOutcomeListResponse:
    """Return operational dry-run Outcomes only."""

    action = session.get(Action, action_id)
    if action is None:
        raise _not_found("Action not found")
    _workspace(session, action.workspace_id)
    outcomes = session.scalars(
        select(ActionOutcome)
        .where(ActionOutcome.action_id == action_id)
        .order_by(ActionOutcome.observed_at, ActionOutcome.outcome_id)
    ).all()
    return ActionOutcomeListResponse(
        action_id=action_id,
        items=[ActionOutcomeResponse.model_validate(item) for item in outcomes],
    )


@router.get("/actions/{action_id}/trace", response_model=ActionTraceResponse)
def get_action_trace(
    action_id: UUID,
    session: SessionDependency,
) -> ActionTraceResponse:
    """Compose Strategy through Outcome without adding redundant provenance rows."""

    action = session.get(Action, action_id)
    if action is None:
        raise _not_found("Action not found")
    policy, _, decision, _, _ = policy_chain(
        session,
        action.policy_evaluation_id,
    )
    snapshot = session.get(AccountStateSnapshot, policy.state_snapshot_id)
    strategy = session.get(StrategyVersion, action.strategy_version_id)
    workspace = _workspace(session, action.workspace_id)
    if snapshot is None or strategy is None:
        raise RuntimeError("Action upstream state or strategy provenance is missing")
    claims = session.scalars(
        select(Evidence)
        .where(Evidence.strategy_version_id == strategy.id)
        .order_by(Evidence.strategy_topic, Evidence.id)
    ).all()
    strategy_response = StrategyResponse(
        id=strategy.id,
        workspace_id=strategy.workspace_id,
        semantic_version=strategy.semantic_version,
        status=strategy.status,
        name=strategy.name,
        summary=strategy.summary,
        synthetic_disclaimer=strategy.synthetic_disclaimer,
        created_at=strategy.created_at,
        activated_at=strategy.activated_at,
        claims=[EvidenceResponse.model_validate(item) for item in claims],
    )
    return ActionTraceResponse(
        strategy=strategy_response,
        state=state_detail_response(session, workspace, snapshot),
        upstream=decision_detail_response(
            session,
            workspace,
            snapshot,
            decision,
            policy,
        ),
        action=_action_detail(session, action),
    )


@router.post(
    "/actions/{action_id}/reviews",
    response_model=ActionReviewMutationResponse,
)
def review_action(
    action_id: UUID,
    command: ActionReviewRequest,
    session: SessionDependency,
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            min_length=1,
            max_length=128,
            pattern=IDEMPOTENCY_KEY_PATTERN,
        ),
    ],
) -> ActionReviewMutationResponse:
    """Record one bounded local-demo review without claiming authenticated identity."""

    _require_mutations_enabled()
    action = session.get(Action, action_id)
    if action is None:
        raise _not_found("Action not found")
    _workspace(session, action.workspace_id)
    try:
        review, replay = create_action_review(
            session,
            action_id,
            resolution=command.resolution,
            reason_code=command.reason_code,
            idempotency_key=idempotency_key,
            reviewer_kind=ActionActorKind.UNVERIFIED_DEMO_HUMAN,
            reviewer_ref=LOCAL_DEMO_REVIEWER_REF,
        )
        session.commit()
    except (ActionTransitionError, IdempotencyConflictError, ValueError) as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    return ActionReviewMutationResponse(
        review=ActionReviewResponse.model_validate(review),
        lifecycle=action_lifecycle(session, action, review=review),
        idempotent_replay=replay,
    )


@router.post(
    "/actions/{action_id}/dry-runs",
    response_model=ActionDryRunMutationResponse,
)
def dry_run_action(
    action_id: UUID,
    session: SessionDependency,
    _body: Annotated[None, Body()] = None,
) -> ActionDryRunMutationResponse:
    """Run local deterministic validation; never simulate external execution."""

    _require_mutations_enabled()
    action = session.get(Action, action_id)
    if action is None:
        raise _not_found("Action not found")
    _workspace(session, action.workspace_id)
    try:
        attempt, outcome, replay = run_action_dry_run(
            session,
            action_id,
            requested_by_kind=ActionActorKind.UNVERIFIED_DEMO_HUMAN,
            requested_by_ref=LOCAL_DEMO_REQUESTER_REF,
        )
        session.commit()
    except (ActionTransitionError, ValueError) as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    return ActionDryRunMutationResponse(
        trace=ActionAttemptTraceResponse(
            attempt=ActionAttemptResponse.model_validate(attempt),
            outcome=ActionOutcomeResponse.model_validate(outcome),
        ),
        idempotent_replay=replay,
    )
