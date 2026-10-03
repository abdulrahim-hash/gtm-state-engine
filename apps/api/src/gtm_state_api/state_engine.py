"""Deterministic strategy/evidence/signal-to-account-state materialization."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from hashlib import sha256
from json import dumps
from uuid import UUID, uuid5

from sqlalchemy import select
from sqlalchemy.orm import Session

from gtm_state_api.current_evidence import current_evidence_condition
from gtm_state_api.models import (
    Account,
    AccountStateSnapshot,
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
from gtm_state_api.signal_engine import recompute_workspace_signals
from gtm_state_api.types import (
    AccountEvidenceSufficiency,
    AccountFitContext,
    AccountRelationshipState,
    AccountStateFacet,
    AccountStateReasonCode,
    AccountTimingState,
    EvidenceAssertion,
    EvidenceClassification,
    EvidenceFreshness,
    FitCriterionResult,
    SignalDefinitionStatus,
    SignalEvaluationResult,
    SignalReasonCode,
    StrategyStatus,
    StrategyTopic,
)

STATE_SNAPSHOT_NAMESPACE = UUID("1a1206b7-243c-4f22-8d7f-53aa00000701")
STATE_ENGINE_KEY = "deterministic_account_state"
STATE_ENGINE_VERSION = "1.0.0"
STATE_INPUT_SCHEMA_VERSION = "1.0.0"
RELATIONSHIP_FACT_KEY = "relationship.existing_relationship"


class Coverage(StrEnum):
    """Internal non-numeric coverage lattice for evidence sufficiency."""

    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    MISSING = "MISSING"
    CONTRADICTORY = "CONTRADICTORY"


@dataclass(frozen=True)
class StateEngineManifest:
    """Code-owned facet evaluator selection for one engine version."""

    fit: tuple[str, str]
    timing: tuple[str, str]
    relationship: tuple[str, str]
    evidence_sufficiency: tuple[str, str]


STATE_ENGINE_REGISTRY: Mapping[str, StateEngineManifest] = {
    STATE_ENGINE_VERSION: StateEngineManifest(
        fit=("required_fit_criteria", "1.0.0"),
        timing=("signal_evaluation_rollup", "1.0.0"),
        relationship=("latest_relationship_assertion", "1.0.0"),
        evidence_sufficiency=("facet_coverage", "1.0.0"),
    )
}


@dataclass(frozen=True)
class FitCriterionDecision:
    """One criterion's exact result and direct account evidence."""

    criterion: StrategyFitCriterion
    result: FitCriterionResult
    observed_assertion: EvidenceAssertion | None
    reason_code: AccountStateReasonCode
    coverage: Coverage
    evidence: tuple[Evidence, ...]


@dataclass(frozen=True)
class FitDecision:
    """Pure fit evaluator output."""

    value: AccountFitContext
    reason_codes: tuple[AccountStateReasonCode, ...]
    coverage: Coverage
    criteria: tuple[FitCriterionDecision, ...]


@dataclass(frozen=True)
class TimingDecision:
    """Pure timing evaluator output."""

    value: AccountTimingState
    reason_codes: tuple[AccountStateReasonCode, ...]
    coverage: Coverage
    evaluations: tuple[SignalEvaluation, ...]


@dataclass(frozen=True)
class RelationshipDecision:
    """Pure relationship evaluator output."""

    value: AccountRelationshipState
    reason_codes: tuple[AccountStateReasonCode, ...]
    coverage: Coverage
    evidence: tuple[Evidence, ...]


@dataclass(frozen=True)
class SufficiencyDecision:
    """Pure evidence-sufficiency output."""

    value: AccountEvidenceSufficiency
    reason_codes: tuple[AccountStateReasonCode, ...]


def _unique_reasons(
    values: Sequence[AccountStateReasonCode],
) -> tuple[AccountStateReasonCode, ...]:
    return tuple(dict.fromkeys(values))


def _aggregate_coverage(values: Sequence[Coverage]) -> Coverage:
    if Coverage.CONTRADICTORY in values:
        return Coverage.CONTRADICTORY
    if values and all(item is Coverage.COMPLETE for item in values):
        return Coverage.COMPLETE
    if any(item is not Coverage.MISSING for item in values):
        return Coverage.PARTIAL
    return Coverage.MISSING


def evaluate_fit_context(
    criteria: Sequence[StrategyFitCriterion],
    evidence: Sequence[Evidence],
) -> FitDecision:
    """Evaluate required exact-key criteria without parsing strategy prose."""

    if not criteria:
        raise ValueError("active strategy requires at least one fit criterion")

    criterion_decisions: list[FitCriterionDecision] = []
    for criterion in sorted(criteria, key=lambda item: item.stable_key):
        relevant = tuple(
            sorted(
                (item for item in evidence if item.fact_key == criterion.input_fact_key),
                key=lambda item: (item.observed_at, str(item.id)),
            )
        )
        if not relevant:
            criterion_decisions.append(
                FitCriterionDecision(
                    criterion=criterion,
                    result=FitCriterionResult.UNKNOWN,
                    observed_assertion=None,
                    reason_code=AccountStateReasonCode.FIT_EVIDENCE_MISSING,
                    coverage=Coverage.MISSING,
                    evidence=(),
                )
            )
            continue

        latest_at = max(item.observed_at for item in relevant)
        latest = tuple(item for item in relevant if item.observed_at == latest_at)
        assertions = {item.fact_assertion for item in latest}
        if None in assertions:
            raise ValueError("fit evidence must carry a fact assertion")
        if len(assertions) != 1:
            criterion_decisions.append(
                FitCriterionDecision(
                    criterion=criterion,
                    result=FitCriterionResult.INCONCLUSIVE,
                    observed_assertion=None,
                    reason_code=AccountStateReasonCode.FIT_EVIDENCE_CONTRADICTORY,
                    coverage=Coverage.CONTRADICTORY,
                    evidence=relevant,
                )
            )
            continue

        assertion = assertions.pop()
        if assertion is None:
            raise ValueError("fit evidence must carry a fact assertion")
        if any(item.freshness is not EvidenceFreshness.CURRENT for item in latest):
            criterion_decisions.append(
                FitCriterionDecision(
                    criterion=criterion,
                    result=FitCriterionResult.UNKNOWN,
                    observed_assertion=assertion,
                    reason_code=AccountStateReasonCode.FIT_EVIDENCE_NOT_CURRENT,
                    coverage=Coverage.PARTIAL,
                    evidence=relevant,
                )
            )
        elif assertion is EvidenceAssertion.INCONCLUSIVE:
            criterion_decisions.append(
                FitCriterionDecision(
                    criterion=criterion,
                    result=FitCriterionResult.INCONCLUSIVE,
                    observed_assertion=assertion,
                    reason_code=AccountStateReasonCode.FIT_EVIDENCE_AMBIGUOUS,
                    coverage=Coverage.PARTIAL,
                    evidence=relevant,
                )
            )
        elif assertion is criterion.expected_assertion:
            criterion_decisions.append(
                FitCriterionDecision(
                    criterion=criterion,
                    result=FitCriterionResult.MATCH,
                    observed_assertion=assertion,
                    reason_code=AccountStateReasonCode.FIT_CRITERION_MATCH,
                    coverage=Coverage.COMPLETE,
                    evidence=relevant,
                )
            )
        else:
            criterion_decisions.append(
                FitCriterionDecision(
                    criterion=criterion,
                    result=FitCriterionResult.MISMATCH,
                    observed_assertion=assertion,
                    reason_code=AccountStateReasonCode.REQUIRED_FIT_CRITERION_MISMATCH,
                    coverage=Coverage.COMPLETE,
                    evidence=relevant,
                )
            )

    results = {item.result for item in criterion_decisions}
    detail_reasons = [item.reason_code for item in criterion_decisions]
    if FitCriterionResult.INCONCLUSIVE in results:
        value = AccountFitContext.INCONCLUSIVE
        reasons = _unique_reasons(detail_reasons)
    elif FitCriterionResult.MISMATCH in results:
        value = AccountFitContext.MISMATCH
        reasons = _unique_reasons(detail_reasons)
    elif results == {FitCriterionResult.MATCH}:
        value = AccountFitContext.MATCH
        reasons = (AccountStateReasonCode.ALL_REQUIRED_FIT_CRITERIA_MATCH,)
    elif FitCriterionResult.MATCH in results:
        value = AccountFitContext.PARTIAL
        reasons = _unique_reasons(
            [AccountStateReasonCode.SOME_REQUIRED_FIT_CRITERIA_MATCH, *detail_reasons]
        )
    else:
        value = AccountFitContext.UNKNOWN
        reasons = _unique_reasons(detail_reasons)

    return FitDecision(
        value=value,
        reason_codes=reasons,
        coverage=_aggregate_coverage([item.coverage for item in criterion_decisions]),
        criteria=tuple(criterion_decisions),
    )


def evaluate_timing_state(
    definitions: Sequence[SignalDefinition],
    evaluations: Sequence[SignalEvaluation],
) -> TimingDecision:
    """Roll up same-time signal evaluations while preserving coverage gaps."""

    ordered_definitions = tuple(sorted(definitions, key=lambda item: item.stable_key))
    if not ordered_definitions:
        return TimingDecision(
            value=AccountTimingState.UNKNOWN,
            reason_codes=(AccountStateReasonCode.NO_ENABLED_SIGNAL_DEFINITIONS,),
            coverage=Coverage.MISSING,
            evaluations=(),
        )

    by_definition: dict[UUID, SignalEvaluation] = {}
    for evaluation in evaluations:
        if evaluation.signal_definition_id in by_definition:
            raise ValueError("timing input contains duplicate evaluations for one definition")
        by_definition[evaluation.signal_definition_id] = evaluation

    applicable: list[SignalEvaluation] = []
    reasons: list[AccountStateReasonCode] = []
    missing_evaluation = False
    missing_evidence = False
    ambiguous = False
    contradictory = False
    detected = False
    stale = False
    no_match = False

    for definition in ordered_definitions:
        current_evaluation = by_definition.get(definition.signal_definition_id)
        if current_evaluation is None:
            missing_evaluation = True
            reasons.append(AccountStateReasonCode.SIGNAL_EVALUATION_MISSING)
            continue
        applicable.append(current_evaluation)
        if current_evaluation.result is SignalEvaluationResult.DETECTED:
            detected = True
            reasons.append(AccountStateReasonCode.CURRENT_SIGNAL_DETECTED)
        elif current_evaluation.result is SignalEvaluationResult.STALE:
            stale = True
            reasons.append(AccountStateReasonCode.STALE_SIGNAL_PRESENT)
        elif current_evaluation.result is SignalEvaluationResult.NO_MATCH:
            no_match = True
        elif current_evaluation.result is SignalEvaluationResult.INCONCLUSIVE:
            if current_evaluation.reason_code is SignalReasonCode.REQUIRED_EVIDENCE_MISSING:
                missing_evidence = True
                reasons.append(AccountStateReasonCode.SIGNAL_EVIDENCE_MISSING)
            elif current_evaluation.reason_code is SignalReasonCode.EVIDENCE_AMBIGUOUS:
                ambiguous = True
                reasons.append(AccountStateReasonCode.SIGNAL_EVIDENCE_AMBIGUOUS)
            elif current_evaluation.reason_code is SignalReasonCode.EVIDENCE_CONTRADICTORY:
                contradictory = True
                reasons.append(AccountStateReasonCode.SIGNAL_EVIDENCE_CONTRADICTORY)
            else:
                raise ValueError("unsupported inconclusive signal reason")
        else:
            raise ValueError("unsupported signal evaluation result")

    if detected:
        value = AccountTimingState.ACTIVE
    elif ambiguous or contradictory:
        value = AccountTimingState.INCONCLUSIVE
    elif missing_evaluation or missing_evidence:
        value = AccountTimingState.UNKNOWN
    elif stale:
        value = AccountTimingState.STALE
    elif no_match and len(applicable) == len(ordered_definitions):
        value = AccountTimingState.NONE
        reasons.append(AccountStateReasonCode.ALL_SIGNAL_EVALUATIONS_NO_MATCH)
    else:
        value = AccountTimingState.UNKNOWN
        reasons.append(AccountStateReasonCode.SIGNAL_EVALUATION_MISSING)

    if contradictory:
        coverage = Coverage.CONTRADICTORY
    elif missing_evaluation or missing_evidence or ambiguous:
        has_determinate = any(
            item.result
            in {
                SignalEvaluationResult.DETECTED,
                SignalEvaluationResult.NO_MATCH,
                SignalEvaluationResult.STALE,
            }
            for item in applicable
        )
        coverage = Coverage.PARTIAL if has_determinate or ambiguous else Coverage.MISSING
    else:
        coverage = Coverage.COMPLETE

    return TimingDecision(
        value=value,
        reason_codes=_unique_reasons(reasons),
        coverage=coverage,
        evaluations=tuple(applicable),
    )


def evaluate_relationship_state(evidence: Sequence[Evidence]) -> RelationshipDecision:
    """Resolve only explicit current existing-relationship assertions."""

    relevant = tuple(
        sorted(
            (item for item in evidence if item.fact_key == RELATIONSHIP_FACT_KEY),
            key=lambda item: (item.observed_at, str(item.id)),
        )
    )
    if not relevant:
        return RelationshipDecision(
            value=AccountRelationshipState.UNKNOWN,
            reason_codes=(AccountStateReasonCode.RELATIONSHIP_EVIDENCE_MISSING,),
            coverage=Coverage.MISSING,
            evidence=(),
        )

    latest_at = max(item.observed_at for item in relevant)
    latest = tuple(item for item in relevant if item.observed_at == latest_at)
    assertions = {item.fact_assertion for item in latest}
    if None in assertions:
        raise ValueError("relationship evidence must carry a fact assertion")
    if len(assertions) != 1:
        return RelationshipDecision(
            value=AccountRelationshipState.INCONCLUSIVE,
            reason_codes=(AccountStateReasonCode.RELATIONSHIP_EVIDENCE_CONTRADICTORY,),
            coverage=Coverage.CONTRADICTORY,
            evidence=relevant,
        )

    assertion = assertions.pop()
    if assertion is None:
        raise ValueError("relationship evidence must carry a fact assertion")
    if any(item.freshness is not EvidenceFreshness.CURRENT for item in latest):
        return RelationshipDecision(
            value=AccountRelationshipState.UNKNOWN,
            reason_codes=(AccountStateReasonCode.RELATIONSHIP_EVIDENCE_NOT_CURRENT,),
            coverage=Coverage.PARTIAL,
            evidence=relevant,
        )
    if assertion is EvidenceAssertion.INCONCLUSIVE:
        return RelationshipDecision(
            value=AccountRelationshipState.INCONCLUSIVE,
            reason_codes=(AccountStateReasonCode.RELATIONSHIP_EVIDENCE_AMBIGUOUS,),
            coverage=Coverage.PARTIAL,
            evidence=relevant,
        )
    if assertion is EvidenceAssertion.PRESENT:
        return RelationshipDecision(
            value=AccountRelationshipState.EXISTING_RELATIONSHIP,
            reason_codes=(AccountStateReasonCode.EXISTING_RELATIONSHIP_PRESENT,),
            coverage=Coverage.COMPLETE,
            evidence=relevant,
        )
    return RelationshipDecision(
        value=AccountRelationshipState.NO_EXISTING_RELATIONSHIP,
        reason_codes=(AccountStateReasonCode.EXISTING_RELATIONSHIP_ABSENT,),
        coverage=Coverage.COMPLETE,
        evidence=relevant,
    )


def evaluate_evidence_sufficiency(
    *,
    fit: Coverage,
    timing: Coverage,
    relationship: Coverage,
) -> SufficiencyDecision:
    """Classify completeness and consistency without numeric confidence."""

    coverage = {
        AccountStateFacet.FIT_CONTEXT: fit,
        AccountStateFacet.TIMING_STATE: timing,
        AccountStateFacet.RELATIONSHIP_STATE: relationship,
    }
    if Coverage.CONTRADICTORY in coverage.values():
        return SufficiencyDecision(
            value=AccountEvidenceSufficiency.CONTRADICTORY,
            reason_codes=(AccountStateReasonCode.CONTRADICTORY_STATE_INPUTS,),
        )
    if all(item is Coverage.COMPLETE for item in coverage.values()):
        return SufficiencyDecision(
            value=AccountEvidenceSufficiency.SUFFICIENT,
            reason_codes=(AccountStateReasonCode.ALL_REQUIRED_STATE_INPUTS_SUPPORTED,),
        )

    reasons: list[AccountStateReasonCode] = []
    if fit is not Coverage.COMPLETE:
        reasons.append(AccountStateReasonCode.FIT_COVERAGE_INCOMPLETE)
    if timing is not Coverage.COMPLETE:
        reasons.append(AccountStateReasonCode.TIMING_COVERAGE_INCOMPLETE)
    if relationship is not Coverage.COMPLETE:
        reasons.append(AccountStateReasonCode.RELATIONSHIP_COVERAGE_INCOMPLETE)
    value = (
        AccountEvidenceSufficiency.INSUFFICIENT
        if all(item is Coverage.MISSING for item in coverage.values())
        else AccountEvidenceSufficiency.PARTIAL
    )
    return SufficiencyDecision(value=value, reason_codes=tuple(reasons))


def _canonical_hash(payload: object) -> str:
    encoded = dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return sha256(encoded).hexdigest()


def _evidence_hash_input(evidence: Evidence) -> dict[str, str | None]:
    """Return only state-semantic fields for relevant canonical evidence."""

    return {
        "classification": evidence.classification.value,
        "fact_assertion": (
            evidence.fact_assertion.value if evidence.fact_assertion is not None else None
        ),
        "fact_key": evidence.fact_key,
        "freshness": evidence.freshness.value,
        "id": str(evidence.id),
        "observed_at": evidence.observed_at.isoformat(),
        "raw_payload_hash": evidence.raw_payload_hash,
    }


def _criterion_hash_input(
    criterion: StrategyFitCriterion,
    source_evidence: Evidence,
) -> dict[str, object]:
    return {
        "expected_assertion": criterion.expected_assertion.value,
        "fit_criterion_id": str(criterion.fit_criterion_id),
        "input_fact_key": criterion.input_fact_key,
        "source_strategy_evidence": {
            "classification": source_evidence.classification.value,
            "id": str(source_evidence.id),
        },
        "stable_key": criterion.stable_key,
    }


def _definition_hash_input(definition: SignalDefinition) -> dict[str, object]:
    return {
        "evaluator_key": definition.evaluator_key,
        "freshness_window_days": definition.freshness_window_days,
        "input_fact_key": definition.input_fact_key,
        "rule_version": definition.rule_version,
        "signal_definition_id": str(definition.signal_definition_id),
        "stable_key": definition.stable_key,
    }


def _evaluation_hash_input(evaluation: SignalEvaluation) -> dict[str, str | None]:
    return {
        "evaluation_as_of": evaluation.evaluation_as_of.isoformat(),
        "evaluation_id": str(evaluation.evaluation_id),
        "input_hash": evaluation.input_hash,
        "reason_code": evaluation.reason_code.value,
        "result": evaluation.result.value,
        "rule_version": evaluation.rule_version,
        "signal_definition_id": str(evaluation.signal_definition_id),
        "signal_id": str(evaluation.signal_id) if evaluation.signal_id is not None else None,
    }


def state_input_hash(
    *,
    workspace_id: UUID,
    account_id: UUID,
    strategy_version_id: UUID,
    state_as_of: datetime,
    criteria: Sequence[StrategyFitCriterion],
    source_evidence: Mapping[UUID, Evidence],
    account_evidence: Sequence[Evidence],
    definitions: Sequence[SignalDefinition],
    evaluations: Sequence[SignalEvaluation],
    state_engine_version: str = STATE_ENGINE_VERSION,
) -> str:
    """Hash the exact semantic inputs; operational clocks and presentation are excluded."""

    manifest = STATE_ENGINE_REGISTRY.get(state_engine_version)
    if manifest is None:
        raise ValueError(f"unsupported state engine version {state_engine_version}")
    return _canonical_hash(
        {
            "account_evidence": [
                _evidence_hash_input(item)
                for item in sorted(account_evidence, key=lambda item: str(item.id))
            ],
            "account_id": str(account_id),
            "fit_criteria": [
                _criterion_hash_input(item, source_evidence[item.source_strategy_evidence_id])
                for item in sorted(criteria, key=lambda item: str(item.fit_criterion_id))
            ],
            "input_schema_version": STATE_INPUT_SCHEMA_VERSION,
            "signal_definitions": [
                _definition_hash_input(item)
                for item in sorted(definitions, key=lambda item: str(item.signal_definition_id))
            ],
            "signal_evaluations": [
                _evaluation_hash_input(item)
                for item in sorted(evaluations, key=lambda item: str(item.evaluation_id))
            ],
            "state_as_of": state_as_of.isoformat(),
            "state_engine": {
                "evidence_sufficiency": list(manifest.evidence_sufficiency),
                "fit": list(manifest.fit),
                "key": STATE_ENGINE_KEY,
                "relationship": list(manifest.relationship),
                "timing": list(manifest.timing),
                "version": state_engine_version,
            },
            "strategy_version_id": str(strategy_version_id),
            "workspace_id": str(workspace_id),
        }
    )


def _resolve_state_as_of(workspace: Workspace, requested: datetime | None) -> datetime:
    if workspace.demo_mode:
        if workspace.demo_as_of is None:
            raise ValueError("demo workspace requires demo_as_of")
        if requested is not None and requested != workspace.demo_as_of:
            raise ValueError("demo state_as_of must equal workspace.demo_as_of")
        return workspace.demo_as_of
    if requested is None:
        raise ValueError("non-demo state computation requires an explicit state_as_of")
    return requested


def _reason_rows(
    *,
    snapshot_id: UUID,
    fit: FitDecision,
    timing: TimingDecision,
    relationship: RelationshipDecision,
    sufficiency: SufficiencyDecision,
) -> list[StateSnapshotReason]:
    groups = (
        (AccountStateFacet.FIT_CONTEXT, fit.reason_codes),
        (AccountStateFacet.TIMING_STATE, timing.reason_codes),
        (AccountStateFacet.RELATIONSHIP_STATE, relationship.reason_codes),
        (AccountStateFacet.EVIDENCE_SUFFICIENCY, sufficiency.reason_codes),
    )
    return [
        StateSnapshotReason(
            state_snapshot_id=snapshot_id,
            facet=facet,
            position=position,
            reason_code=reason,
        )
        for facet, reasons in groups
        for position, reason in enumerate(reasons)
    ]


def _expected_reason_values(
    *,
    fit: FitDecision,
    timing: TimingDecision,
    relationship: RelationshipDecision,
    sufficiency: SufficiencyDecision,
) -> list[tuple[AccountStateFacet, int, AccountStateReasonCode]]:
    return [
        (item.facet, item.position, item.reason_code)
        for item in _reason_rows(
            snapshot_id=UUID(int=0),
            fit=fit,
            timing=timing,
            relationship=relationship,
            sufficiency=sufficiency,
        )
    ]


def _validate_existing_snapshot(
    session: Session,
    snapshot: AccountStateSnapshot,
    *,
    fit: FitDecision,
    timing: TimingDecision,
    relationship: RelationshipDecision,
    sufficiency: SufficiencyDecision,
) -> None:
    if (
        snapshot.fit_context is not fit.value
        or snapshot.timing_state is not timing.value
        or snapshot.relationship_state is not relationship.value
        or snapshot.evidence_sufficiency is not sufficiency.value
    ):
        raise ValueError("existing snapshot does not match deterministic facet output")

    actual_reasons = session.scalars(
        select(StateSnapshotReason)
        .where(StateSnapshotReason.state_snapshot_id == snapshot.state_snapshot_id)
        .order_by(StateSnapshotReason.facet, StateSnapshotReason.position)
    ).all()
    actual_reason_values = sorted(
        [(item.facet, item.position, item.reason_code) for item in actual_reasons],
        key=lambda item: (item[0].value, item[1]),
    )
    expected_reason_values = sorted(
        _expected_reason_values(
            fit=fit,
            timing=timing,
            relationship=relationship,
            sufficiency=sufficiency,
        ),
        key=lambda item: (item[0].value, item[1]),
    )
    if actual_reason_values != expected_reason_values:
        raise ValueError("existing snapshot reasons do not match deterministic output")

    actual_criteria = session.scalars(
        select(StateSnapshotFitCriterion).where(
            StateSnapshotFitCriterion.state_snapshot_id == snapshot.state_snapshot_id
        )
    ).all()
    actual_criterion_values = {
        (
            item.fit_criterion_id,
            item.criterion_stable_key,
            item.input_fact_key,
            item.source_strategy_evidence_id,
            item.expected_assertion,
            item.observed_assertion,
            item.criterion_result,
        )
        for item in actual_criteria
    }
    expected_criterion_values = {
        (
            item.criterion.fit_criterion_id,
            item.criterion.stable_key,
            item.criterion.input_fact_key,
            item.criterion.source_strategy_evidence_id,
            item.criterion.expected_assertion,
            item.observed_assertion,
            item.result,
        )
        for item in fit.criteria
    }
    if actual_criterion_values != expected_criterion_values:
        raise ValueError("existing snapshot fit provenance does not match deterministic output")

    actual_evidence = session.scalars(
        select(StateSnapshotEvidence).where(
            StateSnapshotEvidence.state_snapshot_id == snapshot.state_snapshot_id
        )
    ).all()
    actual_evidence_values = {
        (item.evidence_id, item.facet, item.fit_criterion_id) for item in actual_evidence
    }
    expected_evidence_values = {
        (
            item.id,
            AccountStateFacet.FIT_CONTEXT,
            criterion.criterion.fit_criterion_id,
        )
        for criterion in fit.criteria
        for item in criterion.evidence
    } | {(item.id, AccountStateFacet.RELATIONSHIP_STATE, None) for item in relationship.evidence}
    if actual_evidence_values != expected_evidence_values:
        raise ValueError("existing snapshot evidence provenance is incomplete")

    actual_evaluations = set(
        session.scalars(
            select(StateSnapshotSignalEvaluation.evaluation_id).where(
                StateSnapshotSignalEvaluation.state_snapshot_id == snapshot.state_snapshot_id
            )
        ).all()
    )
    expected_evaluations = {item.evaluation_id for item in timing.evaluations}
    if actual_evaluations != expected_evaluations:
        raise ValueError("existing snapshot evaluation provenance is incomplete")


def recompute_workspace_account_states(
    session: Session,
    workspace_id: UUID,
    *,
    state_as_of: datetime | None = None,
    computed_at: datetime | None = None,
) -> list[AccountStateSnapshot]:
    """Materialize idempotent snapshots after same-time signal recomputation."""

    workspace = session.get(Workspace, workspace_id)
    if workspace is None:
        raise ValueError("workspace not found")
    semantic_time = _resolve_state_as_of(workspace, state_as_of)
    execution_time = computed_at or datetime.now(UTC)
    evaluations = recompute_workspace_signals(
        session,
        workspace_id,
        evaluation_as_of=semantic_time,
        evaluated_at=execution_time,
    )

    strategy = session.scalar(
        select(StrategyVersion).where(
            StrategyVersion.workspace_id == workspace_id,
            StrategyVersion.status == StrategyStatus.ACTIVE,
        )
    )
    if strategy is None:
        raise ValueError("active strategy not found")

    criteria = session.scalars(
        select(StrategyFitCriterion)
        .where(
            StrategyFitCriterion.workspace_id == workspace_id,
            StrategyFitCriterion.strategy_version_id == strategy.id,
        )
        .order_by(StrategyFitCriterion.stable_key)
    ).all()
    if not criteria:
        raise ValueError("active strategy requires at least one fit criterion")

    source_evidence: dict[UUID, Evidence] = {}
    for criterion in criteria:
        source = session.get(Evidence, criterion.source_strategy_evidence_id)
        if source is None or source.strategy_version_id != strategy.id:
            raise ValueError("fit criterion source strategy evidence is missing")
        if (
            source.classification is not EvidenceClassification.HYPOTHESIS
            or source.strategy_topic not in {StrategyTopic.SEGMENTATION, StrategyTopic.ICP}
        ):
            raise ValueError(
                "fit criterion must be justified by segmentation or ICP hypothesis evidence"
            )
        source_evidence[source.id] = source

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
    relevant_fact_keys = {
        *(item.input_fact_key for item in criteria),
        RELATIONSHIP_FACT_KEY,
    }

    evaluations_by_account: dict[UUID, list[SignalEvaluation]] = {}
    for evaluation in evaluations:
        if evaluation.evaluation_as_of != semantic_time:
            raise ValueError("signal evaluation time does not match state_as_of")
        evaluations_by_account.setdefault(evaluation.account_id, []).append(evaluation)

    snapshots: list[AccountStateSnapshot] = []
    for account in accounts:
        account_evidence = session.scalars(
            select(Evidence)
            .where(
                Evidence.account_id == account.id,
                Evidence.classification == EvidenceClassification.FACT,
                Evidence.fact_key.in_(relevant_fact_keys),
                Evidence.observed_at <= semantic_time,
                current_evidence_condition(),
            )
            .order_by(Evidence.observed_at, Evidence.id)
        ).all()
        fit = evaluate_fit_context(criteria, account_evidence)
        timing = evaluate_timing_state(
            definitions,
            evaluations_by_account.get(account.id, []),
        )
        relationship = evaluate_relationship_state(account_evidence)
        sufficiency = evaluate_evidence_sufficiency(
            fit=fit.coverage,
            timing=timing.coverage,
            relationship=relationship.coverage,
        )
        input_hash = state_input_hash(
            workspace_id=workspace_id,
            account_id=account.id,
            strategy_version_id=strategy.id,
            state_as_of=semantic_time,
            criteria=criteria,
            source_evidence=source_evidence,
            account_evidence=account_evidence,
            definitions=definitions,
            evaluations=timing.evaluations,
        )
        snapshot_id = uuid5(STATE_SNAPSHOT_NAMESPACE, input_hash)
        snapshot = session.get(AccountStateSnapshot, snapshot_id)
        if snapshot is not None:
            _validate_existing_snapshot(
                session,
                snapshot,
                fit=fit,
                timing=timing,
                relationship=relationship,
                sufficiency=sufficiency,
            )
            snapshots.append(snapshot)
            continue

        snapshot = AccountStateSnapshot(
            state_snapshot_id=snapshot_id,
            workspace_id=workspace_id,
            account_id=account.id,
            strategy_version_id=strategy.id,
            state_as_of=semantic_time,
            computed_at=execution_time,
            input_hash=input_hash,
            state_engine_version=STATE_ENGINE_VERSION,
            fit_context=fit.value,
            timing_state=timing.value,
            relationship_state=relationship.value,
            evidence_sufficiency=sufficiency.value,
            created_at=execution_time,
        )
        session.add(snapshot)
        session.flush()

        session.add_all(
            _reason_rows(
                snapshot_id=snapshot_id,
                fit=fit,
                timing=timing,
                relationship=relationship,
                sufficiency=sufficiency,
            )
        )
        for item in fit.criteria:
            session.add(
                StateSnapshotFitCriterion(
                    state_snapshot_id=snapshot_id,
                    fit_criterion_id=item.criterion.fit_criterion_id,
                    workspace_id=workspace_id,
                    account_id=account.id,
                    strategy_version_id=strategy.id,
                    criterion_stable_key=item.criterion.stable_key,
                    input_fact_key=item.criterion.input_fact_key,
                    source_strategy_evidence_id=item.criterion.source_strategy_evidence_id,
                    expected_assertion=item.criterion.expected_assertion,
                    observed_assertion=item.observed_assertion,
                    criterion_result=item.result,
                )
            )
        session.flush()

        for item in fit.criteria:
            for evidence in item.evidence:
                session.add(
                    StateSnapshotEvidence(
                        state_snapshot_id=snapshot_id,
                        evidence_id=evidence.id,
                        facet=AccountStateFacet.FIT_CONTEXT,
                        account_id=account.id,
                        fit_criterion_id=item.criterion.fit_criterion_id,
                    )
                )
        for evidence in relationship.evidence:
            session.add(
                StateSnapshotEvidence(
                    state_snapshot_id=snapshot_id,
                    evidence_id=evidence.id,
                    facet=AccountStateFacet.RELATIONSHIP_STATE,
                    account_id=account.id,
                    fit_criterion_id=None,
                )
            )
        for evaluation in timing.evaluations:
            session.add(
                StateSnapshotSignalEvaluation(
                    state_snapshot_id=snapshot_id,
                    evaluation_id=evaluation.evaluation_id,
                    workspace_id=workspace_id,
                    account_id=account.id,
                    strategy_version_id=strategy.id,
                    signal_definition_id=evaluation.signal_definition_id,
                )
            )
        snapshots.append(snapshot)

    session.flush()
    return snapshots
