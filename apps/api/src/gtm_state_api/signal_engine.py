"""Synchronous deterministic evidence-to-signal evaluation."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from json import dumps
from uuid import UUID, uuid5

from sqlalchemy import select
from sqlalchemy.orm import Session

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
from gtm_state_api.types import (
    EvidenceAssertion,
    EvidenceClassification,
    SignalDefinitionStatus,
    SignalEvaluationResult,
    SignalReasonCode,
    StrategyStatus,
)

EVALUATION_NAMESPACE = UUID("1a1206b7-243c-4f22-8d7f-53aa00000e01")
SIGNAL_NAMESPACE = UUID("1a1206b7-243c-4f22-8d7f-53aa00000501")


@dataclass(frozen=True)
class EvaluationDecision:
    """Pure evaluator output before persistence."""

    result: SignalEvaluationResult
    reason_code: SignalReasonCode
    observed_at: datetime | None
    event_evidence: tuple[Evidence, ...] = ()


Evaluator = Callable[
    [SignalDefinition, Sequence[Evidence], datetime],
    EvaluationDecision,
]


def latest_assertion_with_freshness(
    definition: SignalDefinition,
    evidence: Sequence[Evidence],
    evaluation_as_of: datetime,
) -> EvaluationDecision:
    """Evaluate the latest exact-key FACT assertion against an inclusive window."""

    if not evidence:
        return EvaluationDecision(
            result=SignalEvaluationResult.INCONCLUSIVE,
            reason_code=SignalReasonCode.REQUIRED_EVIDENCE_MISSING,
            observed_at=None,
        )

    latest_observed_at = max(item.observed_at for item in evidence)
    latest = tuple(item for item in evidence if item.observed_at == latest_observed_at)
    assertions = {item.fact_assertion for item in latest}

    if len(assertions) != 1:
        return EvaluationDecision(
            result=SignalEvaluationResult.INCONCLUSIVE,
            reason_code=SignalReasonCode.EVIDENCE_CONTRADICTORY,
            observed_at=latest_observed_at,
        )

    assertion = assertions.pop()
    if assertion is EvidenceAssertion.INCONCLUSIVE:
        return EvaluationDecision(
            result=SignalEvaluationResult.INCONCLUSIVE,
            reason_code=SignalReasonCode.EVIDENCE_AMBIGUOUS,
            observed_at=latest_observed_at,
        )
    if assertion is EvidenceAssertion.ABSENT:
        return EvaluationDecision(
            result=SignalEvaluationResult.NO_MATCH,
            reason_code=SignalReasonCode.SUFFICIENT_EVIDENCE_NO_EVENT,
            observed_at=latest_observed_at,
        )
    if assertion is not EvidenceAssertion.PRESENT:
        raise ValueError("normalized event evidence must carry a supported assertion")

    age = evaluation_as_of - latest_observed_at
    if age <= timedelta(days=definition.freshness_window_days):
        return EvaluationDecision(
            result=SignalEvaluationResult.DETECTED,
            reason_code=SignalReasonCode.QUALIFYING_EVENT_WITHIN_WINDOW,
            observed_at=latest_observed_at,
            event_evidence=latest,
        )
    return EvaluationDecision(
        result=SignalEvaluationResult.STALE,
        reason_code=SignalReasonCode.QUALIFYING_EVENT_OUTSIDE_WINDOW,
        observed_at=latest_observed_at,
        event_evidence=latest,
    )


EVALUATOR_REGISTRY: Mapping[tuple[str, str], Evaluator] = {
    ("latest_assertion_with_freshness", "1.0.0"): latest_assertion_with_freshness,
}


def _canonical_hash(payload: object) -> str:
    encoded = dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return sha256(encoded).hexdigest()


def _evidence_input(evidence: Evidence) -> dict[str, str | None]:
    return {
        "classification": evidence.classification.value,
        "fact_assertion": (
            evidence.fact_assertion.value if evidence.fact_assertion is not None else None
        ),
        "fact_key": evidence.fact_key,
        "id": str(evidence.id),
        "normalized_fact": evidence.normalized_fact,
        "observed_at": evidence.observed_at.isoformat(),
        "raw_payload_hash": evidence.raw_payload_hash,
        "source_reference": evidence.source_reference,
    }


def _evaluation_input_hash(
    *,
    workspace_id: UUID,
    account_id: UUID,
    definition: SignalDefinition,
    evaluation_as_of: datetime,
    evidence: Sequence[Evidence],
) -> str:
    return _canonical_hash(
        {
            "account_id": str(account_id),
            "definition": {
                "evaluator_key": definition.evaluator_key,
                "freshness_window_days": definition.freshness_window_days,
                "input_fact_key": definition.input_fact_key,
                "rule_version": definition.rule_version,
                "signal_definition_id": str(definition.signal_definition_id),
                "stable_key": definition.stable_key,
                "strategy_version_id": str(definition.strategy_version_id),
            },
            "evaluation_as_of": evaluation_as_of.isoformat(),
            "evidence": [
                _evidence_input(item) for item in sorted(evidence, key=lambda item: str(item.id))
            ],
            "workspace_id": str(workspace_id),
        }
    )


def _event_fingerprint(
    *,
    workspace_id: UUID,
    account_id: UUID,
    definition: SignalDefinition,
    decision: EvaluationDecision,
) -> str:
    if decision.observed_at is None or not decision.event_evidence:
        raise ValueError("a canonical event requires affirmative event evidence")
    return _canonical_hash(
        {
            "account_id": str(account_id),
            "event_evidence": [
                _evidence_input(item)
                for item in sorted(decision.event_evidence, key=lambda item: str(item.id))
            ],
            "input_fact_key": definition.input_fact_key,
            "observed_at": decision.observed_at.isoformat(),
            "signal_definition_id": str(definition.signal_definition_id),
            "stable_key": definition.stable_key,
            "strategy_version_id": str(definition.strategy_version_id),
            "workspace_id": str(workspace_id),
        }
    )


def _resolve_evaluation_as_of(workspace: Workspace, requested: datetime | None) -> datetime:
    if workspace.demo_mode:
        if workspace.demo_as_of is None:
            raise ValueError("demo workspace requires demo_as_of")
        if requested is not None and requested != workspace.demo_as_of:
            raise ValueError("demo evaluation_as_of must equal workspace.demo_as_of")
        return workspace.demo_as_of
    if requested is None:
        raise ValueError("non-demo evaluation requires an explicit evaluation_as_of")
    return requested


def _get_evaluator(definition: SignalDefinition) -> Evaluator:
    evaluator = EVALUATOR_REGISTRY.get((definition.evaluator_key, definition.rule_version))
    if evaluator is None:
        raise ValueError(
            f"unsupported evaluator {definition.evaluator_key}@{definition.rule_version}"
        )
    return evaluator


def recompute_workspace_signals(
    session: Session,
    workspace_id: UUID,
    *,
    evaluation_as_of: datetime | None = None,
    evaluated_at: datetime | None = None,
) -> list[SignalEvaluation]:
    """Persist idempotent evaluations and canonical events for one active strategy."""

    workspace = session.get(Workspace, workspace_id)
    if workspace is None:
        raise ValueError("workspace not found")
    semantic_time = _resolve_evaluation_as_of(workspace, evaluation_as_of)
    execution_time = evaluated_at or datetime.now(UTC)

    strategy = session.scalar(
        select(StrategyVersion).where(
            StrategyVersion.workspace_id == workspace_id,
            StrategyVersion.status == StrategyStatus.ACTIVE,
        )
    )
    if strategy is None:
        raise ValueError("active strategy not found")

    definitions = session.scalars(
        select(SignalDefinition)
        .where(
            SignalDefinition.workspace_id == workspace_id,
            SignalDefinition.strategy_version_id == strategy.id,
            SignalDefinition.status == SignalDefinitionStatus.ENABLED,
        )
        .order_by(SignalDefinition.stable_key)
    ).all()
    accounts = session.scalars(
        select(Account).where(Account.workspace_id == workspace_id).order_by(Account.id)
    ).all()

    evaluations: list[SignalEvaluation] = []
    for account in accounts:
        for definition in definitions:
            evidence = session.scalars(
                select(Evidence)
                .where(
                    Evidence.account_id == account.id,
                    Evidence.classification == EvidenceClassification.FACT,
                    Evidence.fact_key == definition.input_fact_key,
                    Evidence.observed_at <= semantic_time,
                )
                .order_by(Evidence.observed_at, Evidence.id)
            ).all()
            evaluator = _get_evaluator(definition)
            decision = evaluator(definition, evidence, semantic_time)
            input_hash = _evaluation_input_hash(
                workspace_id=workspace_id,
                account_id=account.id,
                definition=definition,
                evaluation_as_of=semantic_time,
                evidence=evidence,
            )
            evaluation_id = uuid5(EVALUATION_NAMESPACE, input_hash)
            evaluation = session.get(SignalEvaluation, evaluation_id)
            if evaluation is None:
                evaluation = SignalEvaluation(
                    evaluation_id=evaluation_id,
                    workspace_id=workspace_id,
                    account_id=account.id,
                    signal_definition_id=definition.signal_definition_id,
                    strategy_version_id=strategy.id,
                    signal_id=None,
                    evaluation_as_of=semantic_time,
                    evaluated_at=execution_time,
                    input_hash=input_hash,
                    result=decision.result,
                    reason_code=decision.reason_code,
                    rule_version=definition.rule_version,
                    created_at=execution_time,
                )
                session.add(evaluation)
                session.flush()
            elif (
                evaluation.result is not decision.result
                or evaluation.reason_code is not decision.reason_code
            ):
                raise ValueError("existing evaluation does not match deterministic output")

            for item in evidence:
                key = (evaluation.evaluation_id, item.id)
                if session.get(EvaluationEvidence, key) is None:
                    session.add(
                        EvaluationEvidence(
                            evaluation_id=evaluation.evaluation_id,
                            evidence_id=item.id,
                            account_id=account.id,
                        )
                    )

            if decision.result in {
                SignalEvaluationResult.DETECTED,
                SignalEvaluationResult.STALE,
            }:
                event_fingerprint = _event_fingerprint(
                    workspace_id=workspace_id,
                    account_id=account.id,
                    definition=definition,
                    decision=decision,
                )
                signal = session.scalar(
                    select(Signal).where(Signal.event_fingerprint == event_fingerprint)
                )
                if signal is None:
                    if decision.observed_at is None:
                        raise ValueError("detected event requires observed_at")
                    signal = Signal(
                        signal_id=uuid5(SIGNAL_NAMESPACE, event_fingerprint),
                        workspace_id=workspace_id,
                        account_id=account.id,
                        signal_definition_id=definition.signal_definition_id,
                        strategy_version_id=strategy.id,
                        event_fingerprint=event_fingerprint,
                        observed_at=decision.observed_at,
                        first_detected_at=evaluation.evaluated_at,
                        origin_evaluation_id=evaluation.evaluation_id,
                        created_at=evaluation.evaluated_at,
                    )
                    session.add(signal)
                    session.flush()
                if evaluation.signal_id is None:
                    evaluation.signal_id = signal.signal_id
                elif evaluation.signal_id != signal.signal_id:
                    raise ValueError("evaluation is linked to a different canonical event")
            elif evaluation.signal_id is not None:
                raise ValueError("negative or inconclusive evaluation cannot link a signal")

            evaluations.append(evaluation)

    session.flush()
    return evaluations
