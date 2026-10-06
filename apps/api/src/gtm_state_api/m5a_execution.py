"""One developer-test seller Task, with separate authority and durable delivery."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4, uuid5

from sqlalchemy import select
from sqlalchemy.orm import Session

from gtm_state_api.action_engine import canonical_hash
from gtm_state_api.action_workflow import _validate_stored_action
from gtm_state_api.decision_engine import (
    decision_input_hash,
    evaluate_decision_v1,
    evaluate_policy_v1,
    policy_input_hash,
)
from gtm_state_api.hubspot_task import (
    ADAPTER_KEY,
    ADAPTER_VERSION,
    API_VERSION,
    TaskFields,
    TaskReadResult,
)
from gtm_state_api.m2c_workspace import (
    TEST_ACCOUNTS,
    WORKSPACE_ID,
)
from gtm_state_api.m2c_workspace import (
    account_id as m2c_account_id,
)
from gtm_state_api.models import (
    Account,
    AccountSourceId,
    AccountStateSnapshot,
    Action,
    ActionReview,
    DecisionDefinition,
    DecisionEvaluation,
    DecisionEvaluationReason,
    Evidence,
    ExecutionAttempt,
    ExecutionAttemptEvent,
    ExecutionAuthorization,
    ExecutionPlan,
    ExecutionReconciliation,
    NormalizationResult,
    OperationalOutcome,
    PolicyDefinition,
    PolicyEvaluation,
    PolicyEvaluationReason,
    ProviderReceipt,
    SourceObservation,
    SourceReadRun,
    StateSnapshotEvidence,
)
from gtm_state_api.private_company_read import portal_scope_hash, scoped_dataset_key
from gtm_state_api.types import (
    AccountFitContext,
    AccountRelationshipState,
    AccountStateFacet,
    AccountTimingState,
    ActionActorKind,
    ActionReviewResolution,
    ActionType,
    DecisionResult,
    EvidenceAssertion,
    PolicyResult,
)

PLAN_NAMESPACE = UUID("1a1206b7-243c-4f22-8d7f-53aa00000f01")
PLAN_SCHEMA_VERSION = "1.0.0"
MAX_AUTH_HOURS = 1
M2C_CUSTOMER_DOMAIN, M2C_CUSTOMER_NAME = TEST_ACCOUNTS[0]
IN_FLIGHT_LEASE = timedelta(minutes=2)
VALID_TRANSITIONS = {
    "NOT_ATTEMPTED": {"IN_FLIGHT"},
    "IN_FLIGHT": {"PROVIDER_ACCEPTED", "REJECTED_NO_WRITE", "UNKNOWN_DELIVERY"},
    "PROVIDER_ACCEPTED": {"CONFIRMED", "MISMATCH", "UNKNOWN_DELIVERY"},
    "UNKNOWN_DELIVERY": {"PROVIDER_ACCEPTED", "CONFIRMED", "MISMATCH"},
    "REJECTED_NO_WRITE": set(),
    "CONFIRMED": set(),
    "MISMATCH": set(),
}


class ExecutionGateError(ValueError):
    """An explicit fail-closed M5A guard."""


def _require(condition: bool, code: str) -> None:
    if not condition:
        raise ExecutionGateError(code)


def _utc(value: datetime) -> datetime:
    _require(value.tzinfo is not None, "TIMEZONE_REQUIRED")
    return value.astimezone(UTC)


def _hubspot_task_time(value: str) -> datetime:
    """Compare UTC and Unix-millisecond Task timestamps by instant."""

    if value.isdecimal() and len(value) == 13:
        return datetime.fromtimestamp(int(value) / 1000, tz=UTC)
    return _utc(datetime.fromisoformat(value.replace("Z", "+00:00")))


def _chain(
    session: Session, action_id: UUID, *, portal_id: str, company_id: str, now: datetime
) -> tuple[Action, PolicyEvaluation, DecisionEvaluation, AccountStateSnapshot, ActionReview]:
    """Validate the exact stored chain and latest fresh M2C Relationship Evidence."""

    now = _utc(now)
    action = session.get(Action, action_id)
    _require(action is not None, "ACTION_MISSING")
    assert action is not None
    _require(action.action_type is ActionType.CREATE_SELLER_TASK, "WRONG_ACTION_TYPE")
    _require(action.workspace_id == WORKSPACE_ID, "WRONG_WORKSPACE")
    _require(action.account_id == m2c_account_id(M2C_CUSTOMER_DOMAIN), "WRONG_ACCOUNT")
    _require(
        action.payload
        == {
            "task_kind": "RELATIONSHIP_COORDINATION",
            "objective_code": "ASSESS_CONTROLLED_ENGAGEMENT_PATH",
        },
        "WRONG_ACTION_OBJECTIVE",
    )
    account = session.get(Account, action.account_id)
    _require(
        account is not None
        and account.is_synthetic
        and account.domain == M2C_CUSTOMER_DOMAIN
        and account.canonical_name == M2C_CUSTOMER_NAME,
        "WRONG_SYNTHETIC_TARGET",
    )
    _validate_stored_action(session, action)
    policy = session.get(PolicyEvaluation, action.policy_evaluation_id)
    _require(
        policy is not None and policy.result is PolicyResult.REQUIRE_REVIEW, "POLICY_NOT_REVIEW"
    )
    assert policy is not None
    decision = session.get(DecisionEvaluation, policy.decision_evaluation_id)
    snapshot = session.get(AccountStateSnapshot, policy.state_snapshot_id)
    _require(decision is not None and snapshot is not None, "INCOMPLETE_CHAIN")
    assert decision is not None and snapshot is not None
    _require(
        decision.state_snapshot_id == snapshot.state_snapshot_id
        and decision.result is DecisionResult.ENGAGE
        and snapshot.fit_context is AccountFitContext.MATCH
        and snapshot.timing_state is AccountTimingState.ACTIVE
        and snapshot.relationship_state is AccountRelationshipState.EXISTING_RELATIONSHIP
        and snapshot.state_engine_version == "1.2.0",
        "STATE_NOT_ELIGIBLE",
    )
    _require(snapshot.state_as_of <= now, "FUTURE_STATE")
    latest_snapshot = session.scalar(
        select(AccountStateSnapshot)
        .where(
            AccountStateSnapshot.workspace_id == WORKSPACE_ID,
            AccountStateSnapshot.account_id == action.account_id,
        )
        .order_by(
            AccountStateSnapshot.state_as_of.desc(),
            AccountStateSnapshot.computed_at.desc(),
            AccountStateSnapshot.state_snapshot_id.desc(),
        )
        .limit(1)
    )
    _require(
        latest_snapshot is not None
        and latest_snapshot.state_snapshot_id == snapshot.state_snapshot_id,
        "STATE_SUPERSEDED",
    )
    decision_definition = session.get(DecisionDefinition, decision.decision_definition_id)
    policy_definition = session.get(PolicyDefinition, policy.policy_definition_id)
    _require(
        decision_definition is not None and policy_definition is not None, "DEFINITION_MISSING"
    )
    assert decision_definition is not None and policy_definition is not None
    _require(
        decision.input_hash == decision_input_hash(snapshot, decision_definition),
        "DECISION_HASH_MISMATCH",
    )
    _require(
        policy.input_hash == policy_input_hash(snapshot, decision, policy_definition),
        "POLICY_HASH_MISMATCH",
    )
    current_decision = evaluate_decision_v1(snapshot)
    current_policy = evaluate_policy_v1(snapshot, decision)
    _require(current_decision.result is decision.result, "DECISION_CHANGED")
    _require(current_policy.result is policy.result, "POLICY_CHANGED")
    decision_reasons = session.scalars(
        select(DecisionEvaluationReason)
        .where(DecisionEvaluationReason.decision_evaluation_id == decision.decision_evaluation_id)
        .order_by(DecisionEvaluationReason.position)
    ).all()
    policy_reasons = session.scalars(
        select(PolicyEvaluationReason)
        .where(PolicyEvaluationReason.policy_evaluation_id == policy.policy_evaluation_id)
        .order_by(PolicyEvaluationReason.position)
    ).all()
    _require(
        tuple(row.reason_code for row in decision_reasons) == current_decision.reason_codes,
        "DECISION_REASONS_CHANGED",
    )
    _require(
        tuple(row.reason_code for row in policy_reasons) == current_policy.reason_codes,
        "POLICY_REASONS_CHANGED",
    )
    review = session.scalar(select(ActionReview).where(ActionReview.action_id == action_id))
    _require(
        review is not None
        and review.resolution is ActionReviewResolution.APPROVED
        and review.reviewer_kind is ActionActorKind.UNVERIFIED_DEMO_HUMAN
        and review.reason_code.value == "APPROVED_AS_PROPOSED"
        and review.reviewed_at <= now,
        "LOCAL_REVIEW_REQUIRED",
    )
    assert review is not None
    scope = portal_scope_hash(portal_id)
    binding = session.scalar(
        select(AccountSourceId).where(
            AccountSourceId.workspace_id == WORKSPACE_ID,
            AccountSourceId.source_system_key == "hubspot_crm",
            AccountSourceId.dataset_key == scoped_dataset_key(portal_id),
            AccountSourceId.external_account_id == company_id,
            AccountSourceId.account_id == action.account_id,
        )
    )
    _require(binding is not None, "COMPANY_BINDING_MISSING")
    linked_ids = session.scalars(
        select(StateSnapshotEvidence.evidence_id).where(
            StateSnapshotEvidence.state_snapshot_id == snapshot.state_snapshot_id,
            StateSnapshotEvidence.facet == AccountStateFacet.RELATIONSHIP_STATE,
        )
    ).all()
    _require(len(linked_ids) == 1, "RELATIONSHIP_TRACE_AMBIGUOUS")
    evidence = session.get(Evidence, linked_ids[0])
    _require(
        evidence is not None
        and evidence.fact_key == "relationship.crm_reports_customer_status"
        and evidence.fact_assertion is EvidenceAssertion.PRESENT
        and evidence.normalization_result_id is not None,
        "RELATIONSHIP_EVIDENCE_INVALID",
    )
    assert evidence is not None and evidence.normalization_result_id is not None
    _require(
        timedelta(0) <= snapshot.state_as_of - evidence.observed_at <= timedelta(hours=24)
        and timedelta(0) <= now - evidence.observed_at <= timedelta(hours=24),
        "RELATIONSHIP_STALE",
    )
    newer = session.scalar(
        select(Evidence.id)
        .where(
            Evidence.account_id == action.account_id,
            Evidence.fact_key == "relationship.crm_reports_customer_status",
            Evidence.observed_at >= evidence.observed_at,
            Evidence.id != evidence.id,
        )
        .limit(1)
    )
    _require(newer is None, "NEWER_RELATIONSHIP_EVIDENCE")
    normalization = session.get(NormalizationResult, evidence.normalization_result_id)
    observation = (
        session.get(SourceObservation, normalization.source_observation_id)
        if normalization
        else None
    )
    run = session.get(SourceReadRun, observation.source_read_run_id) if observation else None
    _require(
        observation is not None
        and run is not None
        and run.status == "SUCCEEDED"
        and observation.external_record_id == company_id
        and run.scope_sha256 == scope,
        "RELATIONSHIP_SOURCE_SCOPE_INVALID",
    )
    return action, policy, decision, snapshot, review


def _plan_input(plan: ExecutionPlan) -> dict[str, object]:
    return {
        "schema_version": plan.schema_version,
        "action_id": str(plan.action_id),
        "action_hash": plan.action_hash,
        "policy_evaluation_id": str(plan.policy_evaluation_id),
        "policy_hash": plan.policy_hash,
        "decision_evaluation_id": str(plan.decision_evaluation_id),
        "state_snapshot_id": str(plan.state_snapshot_id),
        "workspace_id": str(plan.workspace_id),
        "account_id": str(plan.account_id),
        "adapter_key": plan.adapter_key,
        "adapter_version": plan.adapter_version,
        "api_version": plan.api_version,
        "operation": plan.operation,
        "portal_scope_hash": plan.portal_scope_hash,
        "provider_company_id": plan.provider_company_id,
        "provider_owner_id": plan.provider_owner_id,
        "association_type_id": plan.association_type_id,
        "task_fields": plan.task_fields,
        "marker": plan.marker,
    }


def validate_plan(plan: ExecutionPlan) -> None:
    _require(plan.schema_version == PLAN_SCHEMA_VERSION, "PLAN_VERSION_MISMATCH")
    _require(
        plan.adapter_key == ADAPTER_KEY and plan.adapter_version == ADAPTER_VERSION,
        "ADAPTER_VERSION_MISMATCH",
    )
    _require(
        plan.api_version == API_VERSION and plan.operation == "CREATE_SELLER_TASK",
        "OPERATION_MISMATCH",
    )
    _require(plan.plan_hash == canonical_hash(_plan_input(plan)), "PLAN_HASH_MISMATCH")
    _require(plan.id == uuid5(PLAN_NAMESPACE, plan.plan_hash), "PLAN_ID_MISMATCH")
    fields = TaskFields(
        due_at=plan.task_fields["hs_timestamp"],
        subject=plan.task_fields["hs_task_subject"],
        body=plan.task_fields["hs_task_body"],
        owner_id=plan.task_fields["hubspot_owner_id"],
    )
    _require(fields.properties() == plan.task_fields, "PLAN_TASK_FIELDS_INVALID")
    _require(plan.marker in fields.body, "PLAN_MARKER_MISSING")


def create_plan(
    session: Session,
    action_id: UUID,
    *,
    portal_id: str,
    company_id: str,
    owner_id: str,
    association_type_id: int,
    due_at: datetime,
    now: datetime,
) -> ExecutionPlan:
    action, policy, decision, snapshot, _ = _chain(
        session, action_id, portal_id=portal_id, company_id=company_id, now=now
    )
    _require(owner_id.isdecimal() and 1 <= len(owner_id) <= 30, "TEST_OWNER_REQUIRED")
    _require(association_type_id > 0, "ASSOCIATION_TYPE_REQUIRED")
    raw_due = _utc(due_at)
    due = raw_due.replace(microsecond=(raw_due.microsecond // 1000) * 1000)
    _require(due > _utc(now), "DUE_TIME_MUST_BE_FUTURE")
    seed = canonical_hash(
        {
            "action_id": str(action_id),
            "action_hash": action.semantic_input_hash,
            "portal": portal_scope_hash(portal_id),
            "company": company_id,
            "owner": owner_id,
            "association_type_id": association_type_id,
            "due_at": due.isoformat(),
            "adapter_version": ADAPTER_VERSION,
        }
    )
    marker = f"GTM-M5A:{seed[:24]}"
    fields = TaskFields(
        due_at=due.isoformat().replace("+00:00", "Z"),
        subject="SYNTHETIC: Review relationship context",
        body=(
            "DEVELOPER TEST ONLY. Assess a controlled engagement path for the synthetic "
            f"Customer-test Company. No customer communication. {marker}"
        ),
        owner_id=owner_id,
    )
    plan = ExecutionPlan(
        action_id=action_id,
        action_hash=action.semantic_input_hash,
        policy_evaluation_id=policy.policy_evaluation_id,
        policy_hash=policy.input_hash,
        decision_evaluation_id=decision.decision_evaluation_id,
        state_snapshot_id=snapshot.state_snapshot_id,
        workspace_id=action.workspace_id,
        account_id=action.account_id,
        adapter_key=ADAPTER_KEY,
        adapter_version=ADAPTER_VERSION,
        api_version=API_VERSION,
        operation="CREATE_SELLER_TASK",
        portal_scope_hash=portal_scope_hash(portal_id),
        provider_company_id=company_id,
        provider_owner_id=owner_id,
        association_type_id=association_type_id,
        task_fields=fields.properties(),
        marker=marker,
        schema_version=PLAN_SCHEMA_VERSION,
        created_at=_utc(now),
    )
    plan.plan_hash = canonical_hash(_plan_input(plan))
    plan.id = uuid5(PLAN_NAMESPACE, plan.plan_hash)
    existing = session.get(ExecutionPlan, plan.id)
    if existing is not None:
        validate_plan(existing)
        return existing
    session.add(plan)
    session.flush()
    return plan


def authorize_plan(
    session: Session,
    plan_id: UUID,
    *,
    operator_ref: str,
    now: datetime,
    expires_at: datetime,
) -> ExecutionAuthorization:
    plan = session.get(ExecutionPlan, plan_id)
    _require(plan is not None, "PLAN_MISSING")
    assert plan is not None
    validate_plan(plan)
    _require(1 <= len(operator_ref) <= 120 and operator_ref.isascii(), "OPERATOR_REF_INVALID")
    now = _utc(now)
    expiry = _utc(expires_at)
    _require(now < expiry <= now + timedelta(hours=MAX_AUTH_HOURS), "AUTH_EXPIRY_INVALID")
    existing = session.scalar(
        select(ExecutionAuthorization).where(ExecutionAuthorization.execution_plan_id == plan_id)
    )
    _require(existing is None, "PLAN_ALREADY_AUTHORIZED")
    auth = ExecutionAuthorization(
        id=uuid4(),
        execution_plan_id=plan.id,
        action_id=plan.action_id,
        action_hash=plan.action_hash,
        plan_hash=plan.plan_hash,
        portal_scope_hash=plan.portal_scope_hash,
        provider_company_id=plan.provider_company_id,
        provider_owner_id=plan.provider_owner_id,
        operation=plan.operation,
        assurance_type="LOCAL_OPERATOR_ATTESTATION",
        operator_ref=operator_ref,
        status="ACTIVE",
        authorized_at=now,
        expires_at=expiry,
    )
    session.add(auth)
    session.flush()
    return auth


def create_intent(session: Session, plan_id: UUID, *, now: datetime) -> ExecutionAttempt:
    plan = session.get(ExecutionPlan, plan_id)
    _require(plan is not None, "PLAN_MISSING")
    assert plan is not None
    auth = session.scalar(
        select(ExecutionAuthorization).where(ExecutionAuthorization.execution_plan_id == plan_id)
    )
    _require(
        auth is not None and auth.status == "ACTIVE" and auth.expires_at > _utc(now),
        "AUTH_REQUIRED",
    )
    assert auth is not None
    existing = session.scalar(
        select(ExecutionAttempt).where(ExecutionAttempt.execution_plan_id == plan_id)
    )
    if existing is not None:
        return existing
    sibling = session.scalar(
        select(ExecutionAttempt.id).where(ExecutionAttempt.action_id == plan.action_id).limit(1)
    )
    _require(sibling is None, "ACTION_ALREADY_HAS_EXECUTION_INTENT")
    attempt = ExecutionAttempt(
        id=uuid4(),
        execution_plan_id=plan_id,
        action_id=plan.action_id,
        authorization_id=auth.id,
        status="NOT_ATTEMPTED",
        dispatch_id=None,
        physical_post_count=0,
        lease_until=None,
        dispatched_at=None,
        failure_code=None,
        safe_correlation=None,
        delivery_duration_ms=None,
        created_at=_utc(now),
        updated_at=_utc(now),
    )
    session.add(attempt)
    session.flush()
    session.add(
        ExecutionAttemptEvent(
            id=uuid4(),
            execution_attempt_id=attempt.id,
            sequence=0,
            previous_state=None,
            new_state="NOT_ATTEMPTED",
            reason_code="INTENT_COMMITTED",
            safe_correlation=None,
            occurred_at=_utc(now),
        )
    )
    session.flush()
    return attempt


def _transition(
    session: Session,
    attempt: ExecutionAttempt,
    new_state: str,
    reason: str,
    *,
    now: datetime,
    correlation: str | None = None,
) -> None:
    _require(new_state in VALID_TRANSITIONS[attempt.status], "INVALID_ATTEMPT_TRANSITION")
    prior = attempt.status
    with session.no_autoflush:
        sequence = session.scalar(
            select(ExecutionAttemptEvent.sequence)
            .where(ExecutionAttemptEvent.execution_attempt_id == attempt.id)
            .order_by(ExecutionAttemptEvent.sequence.desc())
            .limit(1)
        )
    attempt.status = new_state
    attempt.updated_at = _utc(now)
    attempt.failure_code = (
        reason if new_state in {"UNKNOWN_DELIVERY", "REJECTED_NO_WRITE", "MISMATCH"} else None
    )
    attempt.safe_correlation = correlation
    session.add(
        ExecutionAttemptEvent(
            id=uuid4(),
            execution_attempt_id=attempt.id,
            sequence=(sequence or 0) + 1,
            previous_state=prior,
            new_state=new_state,
            reason_code=reason,
            safe_correlation=correlation,
            occurred_at=_utc(now),
        )
    )
    session.flush()


def preflight(
    session: Session,
    plan_id: UUID,
    *,
    portal_id: str,
    company_id: str,
    owner_id: str,
    now: datetime,
) -> tuple[ExecutionPlan, ExecutionAuthorization, ExecutionAttempt]:
    plan = session.get(ExecutionPlan, plan_id)
    _require(plan is not None, "PLAN_MISSING")
    assert plan is not None
    validate_plan(plan)
    _require(plan.portal_scope_hash == portal_scope_hash(portal_id), "PORTAL_MISMATCH")
    _require(
        plan.provider_company_id == company_id and plan.provider_owner_id == owner_id,
        "TARGET_MISMATCH",
    )
    action, policy, decision, snapshot, _ = _chain(
        session, plan.action_id, portal_id=portal_id, company_id=company_id, now=now
    )
    _require(
        plan.action_hash == action.semantic_input_hash
        and plan.policy_evaluation_id == policy.policy_evaluation_id
        and plan.policy_hash == policy.input_hash
        and plan.decision_evaluation_id == decision.decision_evaluation_id
        and plan.state_snapshot_id == snapshot.state_snapshot_id,
        "PLAN_CHAIN_MISMATCH",
    )
    auth = session.scalar(
        select(ExecutionAuthorization).where(ExecutionAuthorization.execution_plan_id == plan_id)
    )
    _require(
        auth is not None
        and auth.status == "ACTIVE"
        and auth.expires_at > _utc(now)
        and auth.assurance_type == "LOCAL_OPERATOR_ATTESTATION"
        and auth.action_id == plan.action_id
        and auth.action_hash == plan.action_hash
        and auth.plan_hash == plan.plan_hash
        and auth.portal_scope_hash == plan.portal_scope_hash
        and auth.provider_company_id == company_id
        and auth.provider_owner_id == owner_id
        and auth.operation == plan.operation,
        "AUTH_INVALID",
    )
    assert auth is not None
    attempt = session.scalar(
        select(ExecutionAttempt).where(ExecutionAttempt.execution_plan_id == plan_id)
    )
    _require(
        attempt is not None
        and attempt.authorization_id == auth.id
        and attempt.status == "NOT_ATTEMPTED"
        and attempt.physical_post_count == 0,
        "ATTEMPT_NOT_DISPATCHABLE",
    )
    assert attempt is not None
    return plan, auth, attempt


def claim_dispatch(
    session: Session,
    plan_id: UUID,
    *,
    portal_id: str,
    company_id: str,
    owner_id: str,
    now: datetime,
) -> ExecutionAttempt:
    """Caller commits this row lock transition before any network write."""

    attempt = session.scalar(
        select(ExecutionAttempt)
        .where(ExecutionAttempt.execution_plan_id == plan_id)
        .with_for_update()
    )
    _require(attempt is not None, "INTENT_MISSING")
    assert attempt is not None
    _, _, checked = preflight(
        session,
        plan_id,
        portal_id=portal_id,
        company_id=company_id,
        owner_id=owner_id,
        now=now,
    )
    _require(checked.id == attempt.id, "ATTEMPT_CHANGED")
    attempt.physical_post_count = 1  # reserve the single possible POST before networking
    attempt.dispatch_id = uuid4()
    attempt.dispatched_at = _utc(now)
    attempt.lease_until = _utc(now) + IN_FLIGHT_LEASE
    _transition(session, attempt, "IN_FLIGHT", "SINGLE_POST_RESERVED", now=now)
    return attempt


def record_write_result(
    session: Session,
    attempt_id: UUID,
    *,
    task_id: str | None,
    correlation: str | None,
    provider_timestamp: datetime | None,
    response_projection: dict[str, str] | None,
    result_code: str,
    now: datetime,
    duration_ms: int | None = None,
) -> ProviderReceipt | None:
    """Persist a bounded receipt or preserve delivery uncertainty."""

    attempt = session.get(ExecutionAttempt, attempt_id)
    _require(attempt is not None and attempt.status == "IN_FLIGHT", "ATTEMPT_NOT_IN_FLIGHT")
    assert attempt is not None
    _require(duration_ms is None or duration_ms >= 0, "INVALID_DELIVERY_DURATION")
    attempt.delivery_duration_ms = duration_ms
    plan = session.get(ExecutionPlan, attempt.execution_plan_id)
    _require(plan is not None, "PLAN_MISSING")
    assert plan is not None
    if task_id is None:
        if result_code == "PROVIDER_REJECTED_NO_WRITE":
            _transition(
                session, attempt, "REJECTED_NO_WRITE", result_code, now=now, correlation=correlation
            )
        else:
            _transition(
                session, attempt, "UNKNOWN_DELIVERY", result_code, now=now, correlation=correlation
            )
        return None
    _require(task_id.isdecimal() and 1 <= len(task_id) <= 30, "INVALID_PROVIDER_TASK_ID")
    receipt = ProviderReceipt(
        id=uuid4(),
        execution_plan_id=plan.id,
        execution_attempt_id=attempt.id,
        provider_type="HUBSPOT",
        portal_scope_hash=plan.portal_scope_hash,
        provider_object_type="TASK",
        provider_object_id=task_id,
        request_correlation=correlation,
        http_result_class="201_CREATED",
        provider_timestamp=provider_timestamp,
        adapter_version=plan.adapter_version,
        api_version=plan.api_version,
        request_hash=canonical_hash(
            {
                "task_fields": plan.task_fields,
                "company_id": plan.provider_company_id,
                "association_type_id": plan.association_type_id,
            }
        ),
        response_hash=canonical_hash(response_projection or {"id": task_id}),
        recorded_at=_utc(now),
    )
    session.add(receipt)
    _transition(
        session, attempt, "PROVIDER_ACCEPTED", "TASK_ID_RECEIVED", now=now, correlation=correlation
    )
    session.flush()
    return receipt


def expire_in_flight(session: Session, attempt_id: UUID, *, now: datetime) -> None:
    attempt = session.get(ExecutionAttempt, attempt_id)
    _require(attempt is not None and attempt.status == "IN_FLIGHT", "ATTEMPT_NOT_IN_FLIGHT")
    assert attempt is not None
    _require(
        attempt.lease_until is not None and _utc(now) > attempt.lease_until, "LEASE_STILL_ACTIVE"
    )
    _transition(session, attempt, "UNKNOWN_DELIVERY", "IN_FLIGHT_LEASE_EXPIRED", now=now)


def record_reconciliation(
    session: Session,
    attempt_id: UUID,
    *,
    task: TaskReadResult | None,
    marker_match_count: int,
    lookup_complete: bool,
    read_count: int,
    read_error: bool,
    now: datetime,
) -> ExecutionReconciliation:
    attempt = session.get(ExecutionAttempt, attempt_id)
    _require(
        attempt is not None and attempt.status in {"PROVIDER_ACCEPTED", "UNKNOWN_DELIVERY"},
        "ATTEMPT_NOT_RECONCILABLE",
    )
    assert attempt is not None
    _require(0 <= read_count <= 20 and 0 <= marker_match_count <= 300, "INVALID_READ_COUNT")
    plan = session.get(ExecutionPlan, attempt.execution_plan_id)
    _require(plan is not None, "PLAN_MISSING")
    assert plan is not None
    receipt = session.scalar(
        select(ProviderReceipt).where(ProviderReceipt.execution_attempt_id == attempt_id)
    )
    task_fields_match = False
    if task is not None:
        actual_fields = task.properties
        expected_fields = plan.task_fields
        try:
            expected_due = _hubspot_task_time(expected_fields["hs_timestamp"])
            actual_due = _hubspot_task_time(str(actual_fields["hs_timestamp"]))
            task_fields_match = expected_due == actual_due and all(
                actual_fields.get(key) == expected_fields.get(key)
                for key in ("hs_task_subject", "hs_task_body", "hs_task_status", "hubspot_owner_id")
            )
        except (KeyError, ValueError, TypeError, OverflowError):
            task_fields_match = False
    if task is None:
        if read_error or not lookup_complete:
            result, reason_code = "UNKNOWN", "READ_BACK_UNAVAILABLE"
        elif marker_match_count > 1:
            result, reason_code = "MISMATCH", "DUPLICATE_MARKER_MATCHES"
        else:
            result, reason_code = "NOT_FOUND", "TASK_NOT_OBSERVED"
    elif not lookup_complete:
        result, reason_code = "UNKNOWN", "MARKER_LOOKUP_INCOMPLETE"
    elif marker_match_count == 0:
        result, reason_code = "UNKNOWN", "MARKER_NOT_YET_OBSERVED"
    elif marker_match_count != 1:
        result, reason_code = "MISMATCH", "DUPLICATE_MARKER_MATCHES"
    elif receipt is not None and receipt.provider_object_id != task.task_id:
        result, reason_code = "MISMATCH", "RECEIPT_TASK_ID_MISMATCH"
    elif task.archived:
        result, reason_code = "MISMATCH", "TASK_ARCHIVED"
    elif tuple(task.company_ids) != (plan.provider_company_id,):
        result, reason_code = "MISMATCH", "COMPANY_ASSOCIATION_MISMATCH"
    elif not task_fields_match:
        result, reason_code = "MISMATCH", "TASK_FIELDS_MISMATCH"
    else:
        result, reason_code = "CONFIRMED", "EXACT_TASK_READ_BACK"
    task_id = task.task_id if task else None
    observed_hash = (
        canonical_hash(
            {
                "task_id": task.task_id,
                "archived": task.archived,
                "properties": task.properties,
                "company_ids": task.company_ids,
            }
        )
        if task
        else None
    )
    if result == "CONFIRMED" and receipt is None:
        receipt = ProviderReceipt(
            id=uuid4(),
            execution_plan_id=plan.id,
            execution_attempt_id=attempt.id,
            provider_type="HUBSPOT",
            portal_scope_hash=plan.portal_scope_hash,
            provider_object_type="TASK",
            provider_object_id=task_id,
            request_correlation=task.correlation if task else None,
            http_result_class="RECOVERED_BY_READ",
            provider_timestamp=None,
            adapter_version=plan.adapter_version,
            api_version=plan.api_version,
            request_hash=canonical_hash(
                {
                    "task_fields": plan.task_fields,
                    "company_id": plan.provider_company_id,
                    "association_type_id": plan.association_type_id,
                }
            ),
            response_hash=observed_hash,
            recorded_at=_utc(now),
        )
        session.add(receipt)
        session.flush()
    reconciliation = ExecutionReconciliation(
        id=uuid4(),
        execution_attempt_id=attempt_id,
        provider_receipt_id=receipt.id if receipt else None,
        result=result,
        reason_code=reason_code,
        provider_task_id=task_id,
        read_count=read_count,
        observed_hash=observed_hash,
        reconciled_at=_utc(now),
    )
    session.add(reconciliation)
    session.flush()
    if result == "CONFIRMED":
        _require(task_id is not None and observed_hash is not None, "CONFIRMATION_REQUIRES_TASK")
        _transition(session, attempt, "CONFIRMED", "TASK_READ_BACK_CONFIRMED", now=now)
        prior = session.scalar(
            select(OperationalOutcome).where(OperationalOutcome.execution_attempt_id == attempt_id)
        )
        if prior is None:
            session.add(
                OperationalOutcome(
                    id=uuid4(),
                    execution_plan_id=attempt.execution_plan_id,
                    execution_attempt_id=attempt_id,
                    execution_reconciliation_id=reconciliation.id,
                    reason_code="CRM_TASK_CONFIRMED_CREATED",
                    observed_at=_utc(now),
                )
            )
    elif result == "MISMATCH":
        _transition(session, attempt, "MISMATCH", reason_code, now=now)
    elif attempt.status == "PROVIDER_ACCEPTED":
        _transition(session, attempt, "UNKNOWN_DELIVERY", reason_code, now=now)
    session.flush()
    return reconciliation


def execution_trace(session: Session, plan_id: UUID) -> dict[str, object]:
    """Sanitized local read projection; no Task body or credential."""

    plan = session.get(ExecutionPlan, plan_id)
    _require(plan is not None and plan.workspace_id == WORKSPACE_ID, "PLAN_MISSING")
    assert plan is not None
    review = session.scalar(select(ActionReview).where(ActionReview.action_id == plan.action_id))
    auth = session.scalar(
        select(ExecutionAuthorization).where(ExecutionAuthorization.execution_plan_id == plan_id)
    )
    attempt = session.scalar(
        select(ExecutionAttempt).where(ExecutionAttempt.execution_plan_id == plan_id)
    )
    receipt = session.scalar(
        select(ProviderReceipt).where(ProviderReceipt.execution_plan_id == plan_id)
    )
    events = (
        session.scalars(
            select(ExecutionAttemptEvent)
            .where(ExecutionAttemptEvent.execution_attempt_id == attempt.id)
            .order_by(ExecutionAttemptEvent.sequence)
        ).all()
        if attempt
        else []
    )
    reconciliations = (
        session.scalars(
            select(ExecutionReconciliation)
            .where(ExecutionReconciliation.execution_attempt_id == attempt.id)
            .order_by(ExecutionReconciliation.reconciled_at)
        ).all()
        if attempt
        else []
    )
    outcome = session.scalar(
        select(OperationalOutcome).where(OperationalOutcome.execution_plan_id == plan_id)
    )
    linked_evidence_id = session.scalar(
        select(StateSnapshotEvidence.evidence_id).where(
            StateSnapshotEvidence.state_snapshot_id == plan.state_snapshot_id,
            StateSnapshotEvidence.facet == AccountStateFacet.RELATIONSHIP_STATE,
        )
    )
    relationship_evidence = (
        session.get(Evidence, linked_evidence_id) if linked_evidence_id else None
    )
    normalization = (
        session.get(NormalizationResult, relationship_evidence.normalization_result_id)
        if relationship_evidence and relationship_evidence.normalization_result_id
        else None
    )
    observation = (
        session.get(SourceObservation, normalization.source_observation_id)
        if normalization
        else None
    )
    return {
        "label": "DEVELOPER TEST EXECUTION",
        "synthetic": True,
        "message": (
            "Synthetic HubSpot developer-test execution trace. "
            "No customer communication or commercial outcome is claimed."
        ),
        "action_id": str(plan.action_id),
        "action_type": "CREATE_SELLER_TASK",
        "review_id": str(review.review_id) if review else None,
        "policy_evaluation_id": str(plan.policy_evaluation_id),
        "decision_evaluation_id": str(plan.decision_evaluation_id),
        "state_snapshot_id": str(plan.state_snapshot_id),
        "relationship_evidence_id": str(linked_evidence_id) if linked_evidence_id else None,
        "source_observation_id": str(observation.id) if observation else None,
        "source_read_run_id": str(observation.source_read_run_id) if observation else None,
        "plan_id": str(plan.id),
        "plan_hash": plan.plan_hash,
        "plan_schema_version": plan.schema_version,
        "adapter_version": plan.adapter_version,
        "synthetic_company": M2C_CUSTOMER_NAME,
        "company_id": plan.provider_company_id,
        "portal_scope_hash": plan.portal_scope_hash,
        "reviewed": review is not None and review.resolution is ActionReviewResolution.APPROVED,
        "authority_assurance": auth.assurance_type if auth else None,
        "authorization_id": str(auth.id) if auth else None,
        "authorized": auth is not None and auth.status == "ACTIVE",
        "attempt_id": str(attempt.id) if attempt else None,
        "attempt_status": attempt.status if attempt else None,
        "physical_post_count": attempt.physical_post_count if attempt else 0,
        "delivery_duration_ms": attempt.delivery_duration_ms if attempt else None,
        "events": [
            {"from": e.previous_state, "to": e.new_state, "reason": e.reason_code} for e in events
        ],
        "provider_task_id": receipt.provider_object_id if receipt else None,
        "receipt_recorded": receipt is not None,
        "receipt_id": str(receipt.id) if receipt else None,
        "receipt_result_class": receipt.http_result_class if receipt else None,
        "reconciliations": [r.result for r in reconciliations],
        "reconciliation_ids": [str(r.id) for r in reconciliations],
        "read_back": reconciliations[-1].result if reconciliations else None,
        "operational_outcome": outcome.reason_code if outcome else None,
        "operational_outcome_id": str(outcome.id) if outcome else None,
    }
