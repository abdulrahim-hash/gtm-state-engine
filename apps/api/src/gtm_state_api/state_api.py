"""Read-only M1B.2 API for immutable account-state snapshots."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from gtm_state_api.database import get_session
from gtm_state_api.models import (
    Account,
    AccountStateSnapshot,
    EvaluationEvidence,
    Evidence,
    SignalDefinition,
    SignalEvaluation,
    StateSnapshotEvidence,
    StateSnapshotFitCriterion,
    StateSnapshotReason,
    StateSnapshotSignalEvaluation,
    StrategyFitCriterion,
    StrategyVersion,
    Workspace,
)
from gtm_state_api.schemas import (
    AccountStateDetailResponse,
    AccountStateHistoryResponse,
    AccountStateReasonResponse,
    AccountStateSnapshotResponse,
    EvidenceResponse,
    FitCriterionTraceResponse,
    SignalDefinitionResponse,
    SignalEvaluationResponse,
    SignalEvaluationTraceResponse,
    StateEvaluatorManifestResponse,
    StateEvaluatorReferenceResponse,
    StrategyFitCriterionResponse,
    WorkspaceResponse,
)
from gtm_state_api.state_engine import STATE_ENGINE_REGISTRY
from gtm_state_api.types import AccountStateFacet, StrategyStatus

router = APIRouter(prefix="/api/v1", tags=["M1B.2 account-state read model"])
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


def _evidence_for_evaluation(session: Session, evaluation_id: UUID) -> list[Evidence]:
    return list(
        session.scalars(
            select(Evidence)
            .join(EvaluationEvidence, EvaluationEvidence.evidence_id == Evidence.id)
            .where(EvaluationEvidence.evaluation_id == evaluation_id)
            .order_by(Evidence.observed_at.desc(), Evidence.id)
        ).all()
    )


def _evaluation_trace(
    session: Session,
    evaluation: SignalEvaluation,
) -> SignalEvaluationTraceResponse:
    definition = session.get(SignalDefinition, evaluation.signal_definition_id)
    if definition is None:
        raise RuntimeError("state snapshot signal definition is missing")
    return SignalEvaluationTraceResponse(
        evaluation=SignalEvaluationResponse.model_validate(evaluation),
        definition=SignalDefinitionResponse.model_validate(definition),
        evidence=[
            EvidenceResponse.model_validate(item)
            for item in _evidence_for_evaluation(session, evaluation.evaluation_id)
        ],
    )


def _manifest_response(state_engine_version: str) -> StateEvaluatorManifestResponse:
    manifest = STATE_ENGINE_REGISTRY.get(state_engine_version)
    if manifest is None:
        raise RuntimeError("snapshot references an unsupported state-engine version")

    def reference(value: tuple[str, str]) -> StateEvaluatorReferenceResponse:
        return StateEvaluatorReferenceResponse(evaluator_key=value[0], version=value[1])

    return StateEvaluatorManifestResponse(
        fit=reference(manifest.fit),
        timing=reference(manifest.timing),
        relationship=reference(manifest.relationship),
        evidence_sufficiency=reference(manifest.evidence_sufficiency),
    )


def _detail_response(
    session: Session,
    workspace: Workspace,
    snapshot: AccountStateSnapshot,
) -> AccountStateDetailResponse:
    reasons = session.scalars(
        select(StateSnapshotReason)
        .where(StateSnapshotReason.state_snapshot_id == snapshot.state_snapshot_id)
        .order_by(StateSnapshotReason.facet, StateSnapshotReason.position)
    ).all()
    fit_rows = session.scalars(
        select(StateSnapshotFitCriterion)
        .where(StateSnapshotFitCriterion.state_snapshot_id == snapshot.state_snapshot_id)
        .order_by(StateSnapshotFitCriterion.fit_criterion_id)
    ).all()
    fit_traces: list[FitCriterionTraceResponse] = []
    for fit_row in fit_rows:
        criterion = session.get(StrategyFitCriterion, fit_row.fit_criterion_id)
        if criterion is None:
            raise RuntimeError("snapshot fit criterion is missing")
        source = session.get(Evidence, fit_row.source_strategy_evidence_id)
        if source is None:
            raise RuntimeError("fit criterion strategy evidence is missing")
        account_evidence = session.scalars(
            select(Evidence)
            .join(
                StateSnapshotEvidence,
                StateSnapshotEvidence.evidence_id == Evidence.id,
            )
            .where(
                StateSnapshotEvidence.state_snapshot_id == snapshot.state_snapshot_id,
                StateSnapshotEvidence.facet == AccountStateFacet.FIT_CONTEXT,
                StateSnapshotEvidence.fit_criterion_id == fit_row.fit_criterion_id,
            )
            .order_by(Evidence.observed_at, Evidence.id)
        ).all()
        fit_traces.append(
            FitCriterionTraceResponse(
                criterion=StrategyFitCriterionResponse.model_validate(criterion),
                fit_criterion_id=fit_row.fit_criterion_id,
                criterion_stable_key=fit_row.criterion_stable_key,
                input_fact_key=fit_row.input_fact_key,
                source_strategy_evidence_id=fit_row.source_strategy_evidence_id,
                criterion_result=fit_row.criterion_result,
                expected_assertion=fit_row.expected_assertion,
                observed_assertion=fit_row.observed_assertion,
                source_strategy_evidence=EvidenceResponse.model_validate(source),
                account_evidence=[
                    EvidenceResponse.model_validate(item) for item in account_evidence
                ],
            )
        )

    relationship_evidence = session.scalars(
        select(Evidence)
        .join(StateSnapshotEvidence, StateSnapshotEvidence.evidence_id == Evidence.id)
        .where(
            StateSnapshotEvidence.state_snapshot_id == snapshot.state_snapshot_id,
            StateSnapshotEvidence.facet == AccountStateFacet.RELATIONSHIP_STATE,
        )
        .order_by(Evidence.observed_at, Evidence.id)
    ).all()
    evaluations = session.scalars(
        select(SignalEvaluation)
        .join(
            StateSnapshotSignalEvaluation,
            StateSnapshotSignalEvaluation.evaluation_id == SignalEvaluation.evaluation_id,
        )
        .where(StateSnapshotSignalEvaluation.state_snapshot_id == snapshot.state_snapshot_id)
        .order_by(SignalEvaluation.signal_definition_id)
    ).all()
    return AccountStateDetailResponse(
        workspace=WorkspaceResponse.model_validate(workspace),
        snapshot=AccountStateSnapshotResponse.model_validate(snapshot),
        evaluator_manifest=_manifest_response(snapshot.state_engine_version),
        reasons=[AccountStateReasonResponse.model_validate(item) for item in reasons],
        fit_criteria=fit_traces,
        relationship_evidence=[
            EvidenceResponse.model_validate(item) for item in relationship_evidence
        ],
        signal_evaluations=[_evaluation_trace(session, evaluation) for evaluation in evaluations],
    )


@router.get(
    "/accounts/{account_id}/state",
    response_model=AccountStateDetailResponse,
)
def get_current_account_state(
    account_id: UUID,
    session: SessionDependency,
) -> AccountStateDetailResponse:
    """Return the latest materialized snapshot for the semantic state_as_of."""

    account = _account(session, account_id)
    workspace = _workspace(session, account.workspace_id)
    strategy = _active_strategy(session, workspace.workspace_id)
    statement = select(AccountStateSnapshot).where(
        AccountStateSnapshot.workspace_id == workspace.workspace_id,
        AccountStateSnapshot.account_id == account.id,
        AccountStateSnapshot.strategy_version_id == strategy.id,
    )
    if workspace.demo_mode:
        if workspace.demo_as_of is None:
            raise RuntimeError("demo workspace requires demo_as_of")
        statement = statement.where(AccountStateSnapshot.state_as_of == workspace.demo_as_of)
        statement = statement.order_by(
            AccountStateSnapshot.computed_at.desc(),
            AccountStateSnapshot.state_snapshot_id.desc(),
        )
    else:
        statement = statement.order_by(
            AccountStateSnapshot.state_as_of.desc(),
            AccountStateSnapshot.computed_at.desc(),
            AccountStateSnapshot.state_snapshot_id.desc(),
        )
    snapshot = session.scalar(statement.limit(1))
    if snapshot is None:
        raise _not_found("current account state snapshot not found")
    return _detail_response(session, workspace, snapshot)


@router.get(
    "/accounts/{account_id}/state/history",
    response_model=AccountStateHistoryResponse,
)
def list_account_state_history(
    account_id: UUID,
    session: SessionDependency,
    strategy_version_id: Annotated[UUID | None, Query()] = None,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> AccountStateHistoryResponse:
    """Return immutable semantic snapshots, including same-time knowledge revisions."""

    account = _account(session, account_id)
    workspace = _workspace(session, account.workspace_id)
    statement = select(AccountStateSnapshot).where(
        AccountStateSnapshot.workspace_id == workspace.workspace_id,
        AccountStateSnapshot.account_id == account.id,
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
        statement = statement.where(AccountStateSnapshot.strategy_version_id == strategy_version_id)
    snapshots = session.scalars(
        statement.order_by(
            AccountStateSnapshot.state_as_of.desc(),
            AccountStateSnapshot.computed_at.desc(),
            AccountStateSnapshot.state_snapshot_id.desc(),
        )
        .limit(limit)
        .offset(offset)
    ).all()
    return AccountStateHistoryResponse(
        workspace=WorkspaceResponse.model_validate(workspace),
        account_id=account.id,
        items=[AccountStateSnapshotResponse.model_validate(item) for item in snapshots],
        limit=limit,
        offset=offset,
    )


@router.get(
    "/account-state-snapshots/{state_snapshot_id}",
    response_model=AccountStateDetailResponse,
)
def get_account_state_snapshot(
    state_snapshot_id: UUID,
    session: SessionDependency,
) -> AccountStateDetailResponse:
    """Return one immutable historical snapshot by stable identity."""

    snapshot = session.get(AccountStateSnapshot, state_snapshot_id)
    if snapshot is None:
        raise _not_found("account state snapshot not found")
    workspace = _workspace(session, snapshot.workspace_id)
    return _detail_response(session, workspace, snapshot)
