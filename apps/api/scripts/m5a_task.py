"""Operator-only M5A Task execution; never imported by an HTTP write route."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from time import monotonic_ns
from uuid import UUID

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from gtm_state_api.action_workflow import create_action_review
from gtm_state_api.config import get_settings
from gtm_state_api.database import get_session_factory
from gtm_state_api.hubspot_company_read import read_company
from gtm_state_api.hubspot_task import (
    TaskAdapterError,
    TaskFields,
    create_task_once,
    find_marker_task_ids,
    get_task,
    verify_owner,
    verify_portal,
    verify_task_company_association,
)
from gtm_state_api.ingestion_service import require_local_ingestion
from gtm_state_api.m5a_execution import (
    M2C_CUSTOMER_DOMAIN,
    M2C_CUSTOMER_NAME,
    ExecutionGateError,
    authorize_plan,
    claim_dispatch,
    create_intent,
    create_plan,
    execution_trace,
    expire_in_flight,
    preflight,
    record_reconciliation,
    record_write_result,
    validate_plan,
)
from gtm_state_api.m5a_scope_proof import (
    ScopeProofError,
    credential_fingerprint,
    verify_scope_proof,
)
from gtm_state_api.models import ExecutionAttempt, ExecutionPlan, ProviderReceipt
from gtm_state_api.private_company_read import portal_scope_hash
from gtm_state_api.types import (
    ActionActorKind,
    ActionReviewReasonCode,
    ActionReviewResolution,
)


class LocalM5ASettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[3] / ".env.m2c.local",
        extra="ignore",
    )

    m5a_hubspot_access_token: SecretStr | None = None
    m2c_hubspot_portal_id: str | None = None
    m2c_hubspot_customer_company_id: str | None = None
    m2c_hubspot_customer_stage_value: str | None = None
    m5a_hubspot_test_owner_id: str | None = None


SCOPE_PROOF_FILE = Path(__file__).resolve().parents[3] / ".m5a-scopes.local.json"


def _time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ExecutionGateError("TIMEZONE_REQUIRED")
    return parsed.astimezone(UTC)


def _identity(settings: LocalM5ASettings) -> tuple[str, str, str, str]:
    token = settings.m5a_hubspot_access_token
    portal = settings.m2c_hubspot_portal_id
    company = settings.m2c_hubspot_customer_company_id
    owner = settings.m5a_hubspot_test_owner_id
    if token is None or not portal or not company or not owner:
        raise ExecutionGateError("M5A_PORTAL_COMPANY_OWNER_OR_CREDENTIAL_MISSING")
    return token.get_secret_value(), portal, company, owner


def _provider_preflight(
    token: str,
    portal: str,
    company: str,
    owner: str,
    association_type_id: int,
    *,
    expected_customer_stage: str | None,
    attest_owner: bool,
    attest_scopes: bool,
) -> None:
    if not attest_owner or not attest_scopes or not expected_customer_stage:
        raise ExecutionGateError("OWNER_AND_SCOPE_ATTESTATIONS_REQUIRED")
    verify_scope_proof(
        SCOPE_PROOF_FILE,
        credential=token,
        portal_id=portal,
        owner_id=owner,
        now=datetime.now(UTC),
    )
    verify_portal(credential=token, portal_id=portal)
    read = read_company(company, credential=token)
    if (
        read.record is None
        or read.record.company_name != M2C_CUSTOMER_NAME
        or read.record.company_domain != M2C_CUSTOMER_DOMAIN
        or read.record.lifecycle_stage != expected_customer_stage
    ):
        raise ExecutionGateError("SYNTHETIC_COMPANY_NOT_VERIFIED")
    verify_owner(owner, credential=token)
    verify_task_company_association(association_type_id, credential=token)


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="M5A local developer-test Task execution")
    parser.add_argument(
        "stage",
        choices=(
            "scope-fingerprint",
            "review",
            "plan",
            "inspect-plan",
            "authorize",
            "intent",
            "preflight",
            "dispatch",
            "reconcile",
            "inspect-execution",
        ),
    )
    parser.add_argument("--action-id")
    parser.add_argument("--plan-id")
    parser.add_argument("--plan-hash")
    parser.add_argument("--due-at", help="Task due time with timezone")
    parser.add_argument("--association-type-id", type=int)
    parser.add_argument(
        "--operator-ref", help="Local operator label; no identity assurance implied"
    )
    parser.add_argument("--attest-synthetic-owner", action="store_true")
    parser.add_argument("--attest-task-scopes", action="store_true")
    parser.add_argument("--confirm-local-authorization", action="store_true")
    parser.add_argument("--confirm-developer-test-write", action="store_true")
    return parser.parse_args()


def _plan_id(args: argparse.Namespace) -> UUID:
    if not args.plan_id or not args.plan_hash:
        raise ExecutionGateError("EXACT_PLAN_ID_AND_HASH_REQUIRED")
    return UUID(args.plan_id)


def _exact_plan(session: Session, args: argparse.Namespace) -> ExecutionPlan:
    plan = session.get(ExecutionPlan, _plan_id(args))
    if plan is None or plan.plan_hash != args.plan_hash:
        raise ExecutionGateError("EXACT_PLAN_HASH_MISMATCH")
    validate_plan(plan)
    return plan


def main() -> None:
    args = _arguments()
    require_local_ingestion()
    settings = LocalM5ASettings()
    now = datetime.now(UTC)
    output: dict[str, object]
    with get_session_factory()() as session:
        if args.stage == "scope-fingerprint":
            secret = settings.m5a_hubspot_access_token
            if secret is None:
                raise ExecutionGateError("M5A_CREDENTIAL_MISSING")
            output = {"credential_sha256": credential_fingerprint(secret.get_secret_value())}
        elif args.stage == "review":
            if not args.action_id or not args.operator_ref:
                raise ExecutionGateError("ACTION_AND_OPERATOR_REQUIRED")
            review, replay = create_action_review(
                session,
                UUID(args.action_id),
                resolution=ActionReviewResolution.APPROVED,
                reason_code=ActionReviewReasonCode.APPROVED_AS_PROPOSED,
                idempotency_key=f"m5a-review-{args.action_id}",
                reviewer_kind=ActionActorKind.UNVERIFIED_DEMO_HUMAN,
                reviewer_ref=args.operator_ref,
                reviewed_at=now,
            )
            session.commit()
            output = {
                "review_id": str(review.review_id),
                "review_replay": replay,
                "assurance": "UNVERIFIED_DEMO_HUMAN",
                "authorizes_post": False,
            }
        elif args.stage == "plan":
            if not args.action_id or not args.due_at or args.association_type_id is None:
                raise ExecutionGateError("PLAN_ARGUMENTS_REQUIRED")
            token, portal, company, owner = _identity(settings)
            _provider_preflight(
                token,
                portal,
                company,
                owner,
                args.association_type_id,
                expected_customer_stage=settings.m2c_hubspot_customer_stage_value,
                attest_owner=args.attest_synthetic_owner,
                attest_scopes=args.attest_task_scopes,
            )
            plan = create_plan(
                session,
                UUID(args.action_id),
                portal_id=portal,
                company_id=company,
                owner_id=owner,
                association_type_id=args.association_type_id,
                due_at=_time(args.due_at),
                now=now,
            )
            session.commit()
            output = {
                "plan_id": str(plan.id),
                "plan_hash": plan.plan_hash,
                "marker": plan.marker,
                "schema_version": plan.schema_version,
                "operation": plan.operation,
                "authorizes_post": False,
            }
        else:
            plan = _exact_plan(session, args)
            if args.stage == "inspect-plan":
                output = {
                    "plan_id": str(plan.id),
                    "plan_hash": plan.plan_hash,
                    "schema_version": plan.schema_version,
                    "adapter_version": plan.adapter_version,
                    "operation": plan.operation,
                    "synthetic_company": M2C_CUSTOMER_NAME,
                    "company_id": plan.provider_company_id,
                    "owner_id": plan.provider_owner_id,
                    "portal_scope_hash": plan.portal_scope_hash,
                    "association_type_id": plan.association_type_id,
                    "task_fields": plan.task_fields,
                    "marker": plan.marker,
                }
            elif args.stage == "authorize":
                if not args.confirm_local_authorization or not args.operator_ref:
                    raise ExecutionGateError("EXPLICIT_LOCAL_AUTHORIZATION_REQUIRED")
                auth = authorize_plan(
                    session,
                    plan.id,
                    operator_ref=args.operator_ref,
                    now=now,
                    expires_at=now + timedelta(minutes=30),
                )
                session.commit()
                output = {
                    "authorization_id": str(auth.id),
                    "plan_id": str(plan.id),
                    "assurance": auth.assurance_type,
                    "expires_at": auth.expires_at.isoformat(),
                }
            elif args.stage == "intent":
                attempt = create_intent(session, plan.id, now=now)
                session.commit()
                output = {
                    "attempt_id": str(attempt.id),
                    "status": attempt.status,
                    "physical_post_count": attempt.physical_post_count,
                }
            elif args.stage in {"preflight", "dispatch"}:
                token, portal, company, owner = _identity(settings)
                if args.stage == "dispatch":
                    if (
                        not get_settings().m5a_task_write_enabled
                        or not args.confirm_developer_test_write
                    ):
                        raise ExecutionGateError("EXPLICIT_M5A_WRITE_ENABLEMENT_REQUIRED")
                    if get_settings().app_env == "production":
                        raise ExecutionGateError("PRODUCTION_WRITE_PROHIBITED")
                _provider_preflight(
                    token,
                    portal,
                    company,
                    owner,
                    plan.association_type_id,
                    expected_customer_stage=settings.m2c_hubspot_customer_stage_value,
                    attest_owner=args.attest_synthetic_owner,
                    attest_scopes=args.attest_task_scopes,
                )
                preflight(
                    session,
                    plan.id,
                    portal_id=portal,
                    company_id=company,
                    owner_id=owner,
                    now=datetime.now(UTC),
                )
                if args.stage == "preflight":
                    output = {
                        "plan_id": str(plan.id),
                        "preflight": "PASSED",
                        "external_side_effects": False,
                    }
                else:
                    attempt = claim_dispatch(
                        session,
                        plan.id,
                        portal_id=portal,
                        company_id=company,
                        owner_id=owner,
                        now=datetime.now(UTC),
                    )
                    session.commit()  # durable single-POST reservation before networking
                    fields = TaskFields(
                        due_at=plan.task_fields["hs_timestamp"],
                        subject=plan.task_fields["hs_task_subject"],
                        body=plan.task_fields["hs_task_body"],
                        owner_id=plan.task_fields["hubspot_owner_id"],
                    )
                    started_ns = monotonic_ns()
                    try:
                        written = create_task_once(
                            credential=token,
                            fields=fields,
                            company_id=company,
                            association_type_id=plan.association_type_id,
                        )
                    except TaskAdapterError as exc:
                        record_write_result(
                            session,
                            attempt.id,
                            task_id=None,
                            correlation=exc.correlation,
                            provider_timestamp=None,
                            response_projection=None,
                            result_code=exc.code,
                            now=datetime.now(UTC),
                            duration_ms=(monotonic_ns() - started_ns) // 1_000_000,
                        )
                        session.commit()
                        output = {
                            "attempt_id": str(attempt.id),
                            "status": attempt.status,
                            "result_code": exc.code,
                            "physical_post_count_reserved": 1,
                        }
                    else:
                        receipt = record_write_result(
                            session,
                            attempt.id,
                            task_id=written.task_id,
                            correlation=written.correlation,
                            provider_timestamp=written.created_at,
                            response_projection=written.response_projection,
                            result_code="201_CREATED",
                            now=datetime.now(UTC),
                            duration_ms=(monotonic_ns() - started_ns) // 1_000_000,
                        )
                        session.commit()
                        output = {
                            "attempt_id": str(attempt.id),
                            "status": attempt.status,
                            "task_id": receipt.provider_object_id if receipt else None,
                            "physical_post_count_reserved": 1,
                            "next": "reconcile; do not dispatch again",
                        }
            elif args.stage == "reconcile":
                token, portal, company, owner = _identity(settings)
                verify_portal(credential=token, portal_id=portal)
                if (
                    plan.portal_scope_hash != portal_scope_hash(portal)
                    or plan.provider_company_id != company
                    or plan.provider_owner_id != owner
                ):
                    raise ExecutionGateError("RECONCILIATION_SCOPE_MISMATCH")
                reconciliation_attempt = session.scalar(
                    select(ExecutionAttempt).where(ExecutionAttempt.execution_plan_id == plan.id)
                )
                if reconciliation_attempt is None:
                    raise ExecutionGateError("INTENT_MISSING")
                if reconciliation_attempt.status == "IN_FLIGHT":
                    expire_in_flight(session, reconciliation_attempt.id, now=now)
                    session.commit()
                receipt = session.scalar(
                    select(ProviderReceipt).where(
                        ProviderReceipt.execution_attempt_id == reconciliation_attempt.id
                    )
                )
                try:
                    matches, scan_reads, complete = find_marker_task_ids(
                        marker=plan.marker,
                        company_id=company,
                        credential=token,
                    )
                    selected_id = (
                        receipt.provider_object_id
                        if receipt
                        else matches[0]
                        if len(matches) == 1
                        else None
                    )
                    task, task_reads = (
                        get_task(selected_id, credential=token) if selected_id else (None, 0)
                    )
                    read_error = False
                except TaskAdapterError:
                    matches, scan_reads, complete, task, task_reads, read_error = (
                        [],
                        0,
                        False,
                        None,
                        0,
                        True,
                    )
                reconciliation = record_reconciliation(
                    session,
                    reconciliation_attempt.id,
                    task=task,
                    marker_match_count=len(matches),
                    lookup_complete=complete,
                    read_count=scan_reads + task_reads,
                    read_error=read_error,
                    now=datetime.now(UTC),
                )
                session.commit()
                output = {
                    "attempt_id": str(reconciliation_attempt.id),
                    "result": reconciliation.result,
                    "reason_code": reconciliation.reason_code,
                    "task_id": reconciliation.provider_task_id,
                    "operational_outcome": "CRM_TASK_CONFIRMED_CREATED"
                    if reconciliation.result == "CONFIRMED"
                    else None,
                }
            else:
                output = execution_trace(session, plan.id)
    print(json.dumps(output, indent=2, sort_keys=True))


if __name__ == "__main__":
    try:
        main()
    except (ExecutionGateError, ScopeProofError, TaskAdapterError) as exc:
        raise SystemExit(f"M5A_STOP: {exc}") from None
