"""Explicit human-review and local deterministic dry-run workflow for M1D."""

from __future__ import annotations

from datetime import UTC, datetime
from re import fullmatch
from uuid import UUID, uuid5

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from gtm_state_api.action_engine import (
    ACTION_DERIVATION_KEY,
    ACTION_DERIVATION_VERSION,
    ACTION_NAMESPACE,
    action_semantic_input,
    canonical_hash,
    derive_action,
    policy_chain,
    validate_action_payload,
)
from gtm_state_api.models import (
    Action,
    ActionAttempt,
    ActionOutcome,
    ActionReview,
)
from gtm_state_api.types import (
    ActionActorKind,
    ActionAttemptMode,
    ActionLifecycle,
    ActionOutcomeReasonCode,
    ActionOutcomeResult,
    ActionReviewReasonCode,
    ActionReviewResolution,
    PolicyResult,
)

REVIEW_NAMESPACE = UUID("1a1206b7-243c-4f22-8d7f-53aa00000b01")
ATTEMPT_NAMESPACE = UUID("1a1206b7-243c-4f22-8d7f-53aa00000c01")
OUTCOME_NAMESPACE = UUID("1a1206b7-243c-4f22-8d7f-53aa00000d01")
DRY_RUN_VALIDATOR_KEY = "canonical_action_validator"
DRY_RUN_VALIDATOR_VERSION = "1.0.0"
OUTCOME_SCHEMA_VERSION = "1.0.0"
LOCAL_DEMO_REVIEWER_REF = "local-demo-reviewer"
LOCAL_DEMO_REQUESTER_REF = "local-demo-requester"
IDEMPOTENCY_KEY_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$"


class ActionTransitionError(ValueError):
    """The requested operation is not valid for the Action governance state."""


class IdempotencyConflictError(ValueError):
    """An idempotency key was reused with different command semantics."""


def _review_for_action(session: Session, action_id: UUID) -> ActionReview | None:
    return session.scalar(select(ActionReview).where(ActionReview.action_id == action_id))


def action_lifecycle(
    session: Session,
    action: Action,
    *,
    review: ActionReview | None = None,
) -> ActionLifecycle:
    """Project Action lifecycle from immutable Policy and Review records."""

    policy, _, _, _, _ = policy_chain(session, action.policy_evaluation_id)
    if policy.result is PolicyResult.BLOCK:
        raise ValueError("BLOCK Policy must never have a canonical Action row")
    if policy.result is PolicyResult.ALLOW:
        if review is not None:
            raise ValueError("ALLOW Action must not have a Review record")
        return ActionLifecycle.READY_FOR_DRY_RUN
    candidate = review if review is not None else _review_for_action(session, action.action_id)
    if candidate is None:
        return ActionLifecycle.REVIEW_REQUIRED
    if candidate.action_id != action.action_id:
        raise ValueError("Review does not belong to the Action")
    if candidate.resolution is ActionReviewResolution.REJECTED:
        return ActionLifecycle.REJECTED
    return ActionLifecycle.READY_FOR_DRY_RUN


def _validate_review_reason(
    resolution: ActionReviewResolution,
    reason_code: ActionReviewReasonCode,
) -> None:
    if (
        resolution is ActionReviewResolution.APPROVED
        and reason_code is not ActionReviewReasonCode.APPROVED_AS_PROPOSED
    ):
        raise ValueError("APPROVED requires APPROVED_AS_PROPOSED")
    if (
        resolution is ActionReviewResolution.REJECTED
        and reason_code is ActionReviewReasonCode.APPROVED_AS_PROPOSED
    ):
        raise ValueError("REJECTED requires a rejection reason")


def create_action_review(
    session: Session,
    action_id: UUID,
    *,
    resolution: ActionReviewResolution,
    reason_code: ActionReviewReasonCode,
    idempotency_key: str,
    reviewer_kind: ActionActorKind,
    reviewer_ref: str,
    reviewed_at: datetime | None = None,
) -> tuple[ActionReview, bool]:
    """Create one terminal review; return the immutable record and replay flag."""

    if fullmatch(IDEMPOTENCY_KEY_PATTERN, idempotency_key) is None:
        raise ValueError("Idempotency-Key has an invalid format")
    _validate_review_reason(resolution, reason_code)
    action = session.get(Action, action_id)
    if action is None:
        raise ValueError("Action not found")
    policy, _, _, _, _ = policy_chain(session, action.policy_evaluation_id)
    if policy.result is not PolicyResult.REQUIRE_REVIEW:
        raise ActionTransitionError("Action Policy does not require review")

    key_hash = canonical_hash({"idempotency_key": idempotency_key})
    request_hash = canonical_hash(
        {
            "action_id": str(action.action_id),
            "resolution": resolution.value,
            "reason_code": reason_code.value,
            "reviewer_kind": reviewer_kind.value,
            "reviewer_ref": reviewer_ref,
        }
    )
    existing = _review_for_action(session, action.action_id)
    if existing is not None:
        if existing.idempotency_key_hash == key_hash and existing.request_hash == request_hash:
            return existing, True
        if existing.idempotency_key_hash == key_hash:
            raise IdempotencyConflictError(
                "Idempotency-Key was already used for a different review request"
            )
        raise ActionTransitionError("Action already has a terminal Review")

    review_id = uuid5(REVIEW_NAMESPACE, f"{action.action_id}:{key_hash}")
    execution_time = reviewed_at or datetime.now(UTC)
    review = ActionReview(
        review_id=review_id,
        action_id=action.action_id,
        resolution=resolution,
        reason_code=reason_code,
        reviewer_kind=reviewer_kind,
        reviewer_ref=reviewer_ref,
        idempotency_key_hash=key_hash,
        request_hash=request_hash,
        reviewed_at=execution_time,
        created_at=execution_time,
    )
    try:
        with session.begin_nested():
            session.add(review)
            session.flush()
    except IntegrityError as exc:
        existing = _review_for_action(session, action.action_id)
        if existing is None:
            raise
        if existing.idempotency_key_hash == key_hash and existing.request_hash == request_hash:
            return existing, True
        raise ActionTransitionError("Action already has a different terminal Review") from exc
    return review, False


def _attempt_input(
    action: Action,
    review: ActionReview | None,
) -> dict[str, object]:
    return {
        "action_id": str(action.action_id),
        "action_type": action.action_type.value,
        "action_schema_version": action.action_schema_version,
        "semantic_input_hash": action.semantic_input_hash,
        "payload": action.payload,
        "policy_evaluation_id": str(action.policy_evaluation_id),
        "review_id": None if review is None else str(review.review_id),
        "review_resolution": None if review is None else review.resolution.value,
        "mode": ActionAttemptMode.DRY_RUN.value,
        "validator_key": DRY_RUN_VALIDATOR_KEY,
        "validator_version": DRY_RUN_VALIDATOR_VERSION,
    }


def _validate_stored_action(
    session: Session,
    action: Action,
) -> None:
    (
        policy,
        policy_definition,
        decision,
        decision_definition,
        ordered_reasons,
    ) = policy_chain(session, action.policy_evaluation_id)
    if (
        action.workspace_id != policy.workspace_id
        or action.account_id != policy.account_id
        or action.strategy_version_id != policy.strategy_version_id
    ):
        raise ValueError("Action scope does not match its exact Policy evaluation")
    payload = validate_action_payload(
        action.action_type,
        action.action_schema_version,
        action.payload,
    )
    derivation = derive_action(
        decision=decision,
        policy=policy,
        policy_target=policy_definition.target,
        ordered_reason_codes=ordered_reasons,
    )
    if (
        derivation.action_type is None
        or derivation.payload is None
        or derivation.action_type is not action.action_type
        or derivation.payload.model_dump(mode="json") != payload.model_dump(mode="json")
    ):
        raise ValueError("stored Action does not match deterministic M1D derivation")
    expected_hash = canonical_hash(
        action_semantic_input(
            policy=policy,
            policy_definition=policy_definition,
            decision=decision,
            decision_definition=decision_definition,
            ordered_reason_codes=ordered_reasons,
            action_type=action.action_type,
            payload=payload,
        )
    )
    if action.semantic_input_hash != expected_hash:
        raise ValueError("stored Action semantic hash does not match its full-chain input")
    if (
        action.action_id != uuid5(ACTION_NAMESPACE, expected_hash)
        or action.derivation_key != ACTION_DERIVATION_KEY
        or action.derivation_version != ACTION_DERIVATION_VERSION
    ):
        raise ValueError("stored Action identity or derivation version is inconsistent")


def _outcome_for_attempt(
    session: Session,
    attempt_id: UUID,
) -> ActionOutcome | None:
    return session.scalar(
        select(ActionOutcome).where(ActionOutcome.action_attempt_id == attempt_id)
    )


def run_action_dry_run(
    session: Session,
    action_id: UUID,
    *,
    requested_by_kind: ActionActorKind,
    requested_by_ref: str,
    attempted_at: datetime | None = None,
) -> tuple[ActionAttempt, ActionOutcome, bool]:
    """Validate one governed canonical Action locally without any external side effect."""

    action = session.get(Action, action_id)
    if action is None:
        raise ValueError("Action not found")
    review = _review_for_action(session, action.action_id)
    lifecycle = action_lifecycle(session, action, review=review)
    if lifecycle is ActionLifecycle.REVIEW_REQUIRED:
        raise ActionTransitionError("required Review must be approved before dry-run")
    if lifecycle is ActionLifecycle.REJECTED:
        raise ActionTransitionError("rejected Action cannot advance to dry-run")

    input_hash = canonical_hash(_attempt_input(action, review))
    attempt_id = uuid5(ATTEMPT_NAMESPACE, input_hash)
    existing_attempt = session.get(ActionAttempt, attempt_id)
    if existing_attempt is not None:
        existing_outcome = _outcome_for_attempt(session, attempt_id)
        if existing_outcome is None:
            raise ValueError("existing dry-run Attempt has no terminal Outcome")
        return existing_attempt, existing_outcome, True

    result = ActionOutcomeResult.SUCCEEDED
    reason_code = ActionOutcomeReasonCode.CANONICAL_ACTION_VALIDATED
    try:
        _validate_stored_action(session, action)
    except ValueError:
        result = ActionOutcomeResult.FAILED
        reason_code = ActionOutcomeReasonCode.CANONICAL_ACTION_INVALID

    execution_time = attempted_at or datetime.now(UTC)
    attempt = ActionAttempt(
        action_attempt_id=attempt_id,
        action_id=action.action_id,
        review_id=None if review is None else review.review_id,
        mode=ActionAttemptMode.DRY_RUN,
        validator_key=DRY_RUN_VALIDATOR_KEY,
        validator_version=DRY_RUN_VALIDATOR_VERSION,
        input_hash=input_hash,
        requested_by_kind=requested_by_kind,
        requested_by_ref=requested_by_ref,
        attempted_at=execution_time,
        created_at=execution_time,
    )
    result_hash = canonical_hash(
        {
            "action_attempt_id": str(attempt_id),
            "attempt_input_hash": input_hash,
            "result": result.value,
            "reason_code": reason_code.value,
            "outcome_schema_version": OUTCOME_SCHEMA_VERSION,
            "external_side_effects": False,
        }
    )
    outcome = ActionOutcome(
        outcome_id=uuid5(OUTCOME_NAMESPACE, result_hash),
        action_id=action.action_id,
        action_attempt_id=attempt_id,
        result=result,
        reason_code=reason_code,
        outcome_schema_version=OUTCOME_SCHEMA_VERSION,
        result_hash=result_hash,
        external_side_effects=False,
        observed_at=execution_time,
        created_at=execution_time,
    )
    try:
        with session.begin_nested():
            session.add(attempt)
            session.add(outcome)
            session.flush()
    except IntegrityError:
        existing_attempt = session.get(ActionAttempt, attempt_id)
        existing_outcome = _outcome_for_attempt(session, attempt_id)
        if existing_attempt is None or existing_outcome is None:
            raise
        return existing_attempt, existing_outcome, True
    return attempt, outcome, False
