"""Explicit local M2C materialization and bounded provenance inspection."""

from __future__ import annotations

from collections import Counter
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from gtm_state_api.action_engine import materialize_policy_action
from gtm_state_api.decision_engine import (
    materialize_decision_evaluation,
    materialize_policy_evaluation,
)
from gtm_state_api.ingestion_service import require_local_ingestion
from gtm_state_api.m2c_workspace import STRATEGY_ID, TEST_ACCOUNTS, WORKSPACE_ID
from gtm_state_api.models import (
    Account,
    AccountStateSnapshot,
    Action,
    DecisionEvaluation,
    DecisionEvaluationReason,
    Evidence,
    NormalizationResult,
    PolicyEvaluation,
    PolicyEvaluationReason,
    SignalEvaluation,
    SourceObservation,
    SourceReadRun,
    StateSnapshotEvidence,
    StateSnapshotSignalEvaluation,
)
from gtm_state_api.signal_engine import recompute_workspace_signals
from gtm_state_api.state_engine import (
    CRM_RELATIONSHIP_WINDOW_HOURS,
    CRM_STATE_ENGINE_VERSION,
    recompute_workspace_account_states,
)
from gtm_state_api.types import AccountStateFacet


def inspect_run(session: Session, run_id: UUID) -> dict[str, Any]:
    """Return only the approved, bounded provider observation and its provenance."""

    require_local_ingestion()
    run = session.get(SourceReadRun, run_id)
    if run is None or run.workspace_id != WORKSPACE_ID:
        raise ValueError("M2C source read run not found")
    observation = session.get(SourceObservation, run.observation_id) if run.observation_id else None
    normalization = (
        session.scalar(
            select(NormalizationResult).where(
                NormalizationResult.source_observation_id == observation.id
            )
        )
        if observation
        else None
    )
    evidence = (
        session.scalar(select(Evidence).where(Evidence.normalization_result_id == normalization.id))
        if normalization
        else None
    )
    return {
        "run_id": str(run.id),
        "workspace_id": str(run.workspace_id),
        "adapter_key": run.adapter_key,
        "adapter_version": run.adapter_version,
        "source_category": "private_crm_company",
        "provider_scope_sha256": run.scope_sha256,
        "request_sha256": run.request_sha256,
        "response_sha256": run.response_sha256,
        "mapping_version": run.mapping_version,
        "started_at": run.started_at.isoformat(),
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        "status": run.status,
        "counts": {
            "accepted": run.accepted_count,
            "unresolved": run.unresolved_count,
            "rejected": run.rejected_count,
        },
        "retry_count": run.retry_count,
        "failure_code": run.failure_code,
        "provider_correlation_id": run.provider_correlation_id,
        "observation": (
            {
                "id": str(observation.id),
                "provider_company_id": observation.external_record_id,
                "observed_at": observation.source_observed_at.isoformat(),
                "payload_sha256": observation.payload_sha256,
                "fields": observation.original_fields,
            }
            if observation
            else None
        ),
        "normalization": (
            {
                "id": str(normalization.id),
                "outcome": normalization.outcome.value,
                "reason_code": (
                    normalization.reason_code.value if normalization.reason_code else None
                ),
                "mapper_key": normalization.mapper_key,
                "mapper_version": normalization.mapper_version,
                "fact_key": normalization.fact_key,
                "fact_assertion": normalization.fact_assertion,
                "output_sha256": normalization.output_sha256,
            }
            if normalization
            else None
        ),
        "evidence": (
            {
                "id": str(evidence.id),
                "classification": evidence.classification.value,
                "fact_key": evidence.fact_key,
                "assertion": evidence.fact_assertion.value if evidence.fact_assertion else None,
                "observed_at": evidence.observed_at.isoformat(),
                "source_uri": evidence.source_uri,
            }
            if evidence
            else None
        ),
        "downstream_materialized_by_read": False,
    }


def _accounts(session: Session) -> list[Account]:
    accounts = list(
        session.scalars(
            select(Account).where(Account.workspace_id == WORKSPACE_ID).order_by(Account.id)
        ).all()
    )
    if {item.domain for item in accounts} != {domain for domain, _ in TEST_ACCOUNTS}:
        raise ValueError("M2C synthetic Account fixture shape changed")
    return accounts


def _snapshots(session: Session, as_of: datetime) -> list[AccountStateSnapshot]:
    values = list(
        session.scalars(
            select(AccountStateSnapshot).where(
                AccountStateSnapshot.workspace_id == WORKSPACE_ID,
                AccountStateSnapshot.state_as_of == as_of,
                AccountStateSnapshot.state_engine_version == CRM_STATE_ENGINE_VERSION,
            )
        ).all()
    )
    if len(values) != 2 or len({item.account_id for item in values}) != 2:
        raise ValueError("expected one exact M2C State snapshot per account at as_of")
    return values


def _verified_runs(session: Session, run_ids: tuple[UUID, ...], as_of: datetime) -> None:
    if not run_ids:
        raise ValueError("inspect at least one successful CRM read before materialization")
    inspected_observations: set[UUID] = set()
    for run_id in run_ids:
        run = session.get(SourceReadRun, run_id)
        if (
            run is None
            or run.workspace_id != WORKSPACE_ID
            or run.status != "SUCCEEDED"
            or run.observation_id is None
        ):
            raise ValueError("materialization requires inspected successful source reads")
        observation = session.get(SourceObservation, run.observation_id)
        if observation is None or observation.source_observed_at > as_of:
            raise ValueError("source observation is after semantic state_as_of")
        inspected_observations.add(observation.id)
        normalization = session.scalar(
            select(NormalizationResult).where(
                NormalizationResult.source_observation_id == observation.id
            )
        )
        if normalization is None:
            raise ValueError("successful source observation lacks normalization")
        evidence = session.scalar(
            select(Evidence.id).where(Evidence.normalization_result_id == normalization.id)
        )
        if evidence is None:
            raise ValueError("successful source observation lacks canonical Evidence")
    required_observations = set(
        session.scalars(
            select(SourceObservation.id).where(
                SourceObservation.workspace_id == WORKSPACE_ID,
                SourceObservation.source_read_run_id.is_not(None),
                SourceObservation.source_observed_at <= as_of,
            )
        ).all()
    )
    if len(required_observations) < 2 or not required_observations.issubset(inspected_observations):
        raise ValueError("inspect every eligible CRM source observation before materialization")
    conflict = session.scalar(
        select(SourceReadRun.id).where(
            SourceReadRun.workspace_id == WORKSPACE_ID,
            SourceReadRun.status == "CONFLICT",
        )
    )
    if conflict:
        raise ValueError("unresolved same-time source conflict blocks M2C materialization")


def materialize_stage(
    session: Session,
    *,
    stage: str,
    as_of: datetime,
    inspected_run_ids: tuple[UUID, ...],
) -> dict[str, Any]:
    """Materialize exactly one stage after manual source inspection."""

    require_local_ingestion()
    if as_of.tzinfo is None:
        raise ValueError("state_as_of must be explicit and timezone-aware")
    with session.begin():
        _verified_runs(session, inspected_run_ids, as_of)
        accounts = _accounts(session)
        items: list[Any]
        before: set[str]
        input_ids: list[str]
        if stage == "signals":
            before = {
                str(item.evaluation_id)
                for item in session.scalars(
                    select(SignalEvaluation).where(
                        SignalEvaluation.workspace_id == WORKSPACE_ID,
                        SignalEvaluation.evaluation_as_of == as_of,
                    )
                )
            }
            items = recompute_workspace_signals(session, WORKSPACE_ID, evaluation_as_of=as_of)
            input_ids = [str(item.id) for item in accounts]
            output_ids = [str(item.evaluation_id) for item in items]
        elif stage == "state":
            previous = list(
                session.scalars(
                    select(SignalEvaluation).where(
                        SignalEvaluation.workspace_id == WORKSPACE_ID,
                        SignalEvaluation.evaluation_as_of == as_of,
                    )
                ).all()
            )
            if len(previous) != 2:
                raise ValueError("materialize and inspect two Signal evaluations first")
            expected = {
                str(item.account_id): (str(item.evaluation_id), item.input_hash, item.result.value)
                for item in previous
            }
            before = {
                str(item.state_snapshot_id)
                for item in session.scalars(
                    select(AccountStateSnapshot).where(
                        AccountStateSnapshot.workspace_id == WORKSPACE_ID,
                        AccountStateSnapshot.state_as_of == as_of,
                    )
                )
            }
            items = recompute_workspace_account_states(
                session,
                WORKSPACE_ID,
                state_as_of=as_of,
                state_engine_version=CRM_STATE_ENGINE_VERSION,
            )
            after = list(
                session.scalars(
                    select(SignalEvaluation).where(
                        SignalEvaluation.workspace_id == WORKSPACE_ID,
                        SignalEvaluation.evaluation_as_of == as_of,
                    )
                ).all()
            )
            actual = {
                str(item.account_id): (str(item.evaluation_id), item.input_hash, item.result.value)
                for item in after
            }
            if actual != expected or len(after) != 2:
                raise ValueError("State internal Signal recomputation diverged")
            for snapshot in items:
                links = list(
                    session.scalars(
                        select(StateSnapshotSignalEvaluation).where(
                            StateSnapshotSignalEvaluation.state_snapshot_id
                            == snapshot.state_snapshot_id
                        )
                    ).all()
                )
                if (
                    len(links) != 1
                    or str(links[0].evaluation_id) != expected[str(snapshot.account_id)][0]
                ):
                    raise ValueError("State linked a divergent Signal evaluation")
            input_ids = sorted(value[0] for value in expected.values())
            output_ids = [str(item.state_snapshot_id) for item in items]
        elif stage == "decisions":
            snapshots = _snapshots(session, as_of)
            before = {
                str(item.decision_evaluation_id)
                for item in session.scalars(
                    select(DecisionEvaluation).where(
                        DecisionEvaluation.state_snapshot_id.in_(
                            [snapshot.state_snapshot_id for snapshot in snapshots]
                        )
                    )
                )
            }
            items = [
                materialize_decision_evaluation(session, snapshot.state_snapshot_id)
                for snapshot in snapshots
            ]
            input_ids = [str(item.state_snapshot_id) for item in snapshots]
            output_ids = [str(item.decision_evaluation_id) for item in items]
        elif stage == "policies":
            snapshots = _snapshots(session, as_of)
            decisions = list(
                session.scalars(
                    select(DecisionEvaluation).where(
                        DecisionEvaluation.state_snapshot_id.in_(
                            [snapshot.state_snapshot_id for snapshot in snapshots]
                        )
                    )
                ).all()
            )
            if len(decisions) != 2:
                raise ValueError("materialize and inspect two Decisions first")
            before = {
                str(item.policy_evaluation_id)
                for item in session.scalars(
                    select(PolicyEvaluation).where(
                        PolicyEvaluation.decision_evaluation_id.in_(
                            [item.decision_evaluation_id for item in decisions]
                        )
                    )
                )
            }
            items = [
                materialize_policy_evaluation(session, decision.decision_evaluation_id)
                for decision in decisions
            ]
            input_ids = [str(item.decision_evaluation_id) for item in decisions]
            output_ids = [str(item.policy_evaluation_id) for item in items]
        elif stage == "actions":
            snapshots = _snapshots(session, as_of)
            policies = list(
                session.scalars(
                    select(PolicyEvaluation).where(
                        PolicyEvaluation.state_snapshot_id.in_(
                            [snapshot.state_snapshot_id for snapshot in snapshots]
                        )
                    )
                ).all()
            )
            if len(policies) != 2:
                raise ValueError("materialize and inspect two Policies first")
            before = {
                str(item.action_id)
                for item in session.scalars(
                    select(Action).where(
                        Action.policy_evaluation_id.in_(
                            [item.policy_evaluation_id for item in policies]
                        )
                    )
                )
            }
            projections = [
                materialize_policy_action(session, item.policy_evaluation_id) for item in policies
            ]
            items = [action for _, action in projections if action is not None]
            input_ids = [str(item.policy_evaluation_id) for item in policies]
            output_ids = [str(item.action_id) for item in items]
        else:
            raise ValueError("unsupported M2C stage")
        results = Counter(item.result.value for item in items if hasattr(item, "result"))
        if stage == "state":
            results = Counter(
                item.relationship_state.value
                for item in items
                if isinstance(item, AccountStateSnapshot)
            )
        if stage == "actions":
            results = Counter(item.action_type.value for item in items if isinstance(item, Action))
        return {
            "stage": stage,
            "semantic_as_of": as_of.isoformat(),
            "workspace_id": str(WORKSPACE_ID),
            "strategy_version_id": str(STRATEGY_ID),
            "state_engine_version": CRM_STATE_ENGINE_VERSION,
            "input_ids": sorted(input_ids),
            "output_ids": sorted(output_ids),
            "result_counts": dict(sorted(results.items())),
            "created": len(set(output_ids) - before),
            "reused": len(set(output_ids) & before),
            "no_external_side_effects": True,
        }


def export_trace(session: Session, *, as_of: datetime) -> dict[str, Any]:
    """Read one fully materialized semantic time without contacting the CRM."""

    require_local_ingestion()
    accounts = _accounts(session)
    snapshots = _snapshots(session, as_of)
    by_account = {item.account_id: item for item in snapshots}
    traces: list[dict[str, Any]] = []
    for account in accounts:
        snapshot = by_account[account.id]
        relationship_ids = list(
            session.scalars(
                select(StateSnapshotEvidence.evidence_id).where(
                    StateSnapshotEvidence.state_snapshot_id == snapshot.state_snapshot_id,
                    StateSnapshotEvidence.facet == AccountStateFacet.RELATIONSHIP_STATE,
                )
            ).all()
        )
        relationship_evidence = []
        for evidence_id in relationship_ids:
            evidence = session.get(Evidence, evidence_id)
            if evidence is None or evidence.normalization_result_id is None:
                raise ValueError("Relationship provenance is incomplete")
            normalization = session.get(NormalizationResult, evidence.normalization_result_id)
            if normalization is None:
                raise ValueError("Relationship normalization is missing")
            observation = session.get(SourceObservation, normalization.source_observation_id)
            if observation is None:
                raise ValueError("Relationship source observation is missing")
            run = session.get(SourceReadRun, observation.source_read_run_id)
            if run is None:
                raise ValueError("Relationship source read run is missing")
            relationship_evidence.append(
                {
                    "evidence_id": str(evidence.id),
                    "fact_key": evidence.fact_key,
                    "assertion": evidence.fact_assertion.value if evidence.fact_assertion else None,
                    "observed_at": evidence.observed_at.isoformat(),
                    "freshness_at_as_of": (
                        "WITHIN_24_HOURS"
                        if 0
                        <= (as_of - evidence.observed_at).total_seconds()
                        <= CRM_RELATIONSHIP_WINDOW_HOURS * 3600
                        else "EXPIRED"
                    ),
                    "normalization_result_id": str(normalization.id),
                    "mapper_key": normalization.mapper_key,
                    "mapper_version": normalization.mapper_version,
                    "source_observation_id": str(observation.id),
                    "source_read_run_id": str(run.id),
                    "provider_company_id": observation.external_record_id,
                    "provider_scope_sha256": run.scope_sha256,
                    "source_category": "private_crm_company",
                    "source_stage_value": observation.original_fields.get("lifecycle_stage", ""),
                    "configured_customer_stage": observation.original_fields.get(
                        "configured_customer_stage", ""
                    ),
                }
            )
        decision = session.scalar(
            select(DecisionEvaluation).where(
                DecisionEvaluation.state_snapshot_id == snapshot.state_snapshot_id
            )
        )
        policy = (
            session.scalar(
                select(PolicyEvaluation).where(
                    PolicyEvaluation.decision_evaluation_id == decision.decision_evaluation_id
                )
            )
            if decision
            else None
        )
        action = (
            session.scalar(
                select(Action).where(Action.policy_evaluation_id == policy.policy_evaluation_id)
            )
            if policy
            else None
        )
        traces.append(
            {
                "account_id": str(account.id),
                "company_name": account.canonical_name,
                "domain": account.domain,
                "synthetic": account.is_synthetic,
                "relationship_evidence": relationship_evidence,
                "state": {
                    "id": str(snapshot.state_snapshot_id),
                    "fit": snapshot.fit_context.value,
                    "timing": snapshot.timing_state.value,
                    "relationship": snapshot.relationship_state.value,
                    "sufficiency": snapshot.evidence_sufficiency.value,
                    "input_hash": snapshot.input_hash,
                },
                "decision": (
                    {
                        "id": str(decision.decision_evaluation_id),
                        "result": decision.result.value,
                        "state_snapshot_id": str(decision.state_snapshot_id),
                        "reason_codes": [
                            code.value
                            for code in session.scalars(
                                select(DecisionEvaluationReason.reason_code)
                                .where(
                                    DecisionEvaluationReason.decision_evaluation_id
                                    == decision.decision_evaluation_id
                                )
                                .order_by(DecisionEvaluationReason.position)
                            ).all()
                        ],
                    }
                    if decision
                    else None
                ),
                "policy": (
                    {
                        "id": str(policy.policy_evaluation_id),
                        "result": policy.result.value,
                        "decision_evaluation_id": str(policy.decision_evaluation_id),
                        "reason_codes": [
                            code.value
                            for code in session.scalars(
                                select(PolicyEvaluationReason.reason_code)
                                .where(
                                    PolicyEvaluationReason.policy_evaluation_id
                                    == policy.policy_evaluation_id
                                )
                                .order_by(PolicyEvaluationReason.position)
                            ).all()
                        ],
                    }
                    if policy
                    else None
                ),
                "action": (
                    {
                        "id": str(action.action_id),
                        "type": action.action_type.value,
                        "policy_evaluation_id": str(action.policy_evaluation_id),
                    }
                    if action
                    else None
                ),
            }
        )
    return {
        "label": "CRM TEST WORKSPACE - SYNTHETIC / DEVELOPER TEST DATA",
        "meaning": "CRM-reported Customer is not proof of an active contract or revenue.",
        "semantic_as_of": as_of.isoformat(),
        "workspace_id": str(WORKSPACE_ID),
        "strategy_version_id": str(STRATEGY_ID),
        "state_engine_version": CRM_STATE_ENGINE_VERSION,
        "accounts": traces,
        "external_side_effects": False,
    }
