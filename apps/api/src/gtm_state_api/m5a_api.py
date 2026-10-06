"""Local read-only M5A execution inspection; no external-write HTTP surface."""

from __future__ import annotations

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from gtm_state_api.config import get_settings
from gtm_state_api.database import get_session
from gtm_state_api.m5a_execution import ExecutionGateError, execution_trace

router = APIRouter(prefix="/api/v1/pilot/m5a", tags=["M5A local execution trace"])
SessionDependency = Annotated[Session, Depends(get_session)]


class ExecutionEventResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    from_state: str | None = Field(alias="from")
    to: str
    reason: str


class ExecutionTraceResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: Literal["DEVELOPER TEST EXECUTION"]
    synthetic: Literal[True]
    message: str
    action_id: str
    action_type: Literal["CREATE_SELLER_TASK"]
    review_id: str | None
    policy_evaluation_id: str
    decision_evaluation_id: str
    state_snapshot_id: str
    relationship_evidence_id: str | None
    source_observation_id: str | None
    source_read_run_id: str | None
    plan_id: str
    plan_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    plan_schema_version: str
    adapter_version: str
    synthetic_company: Literal["M2C Customer Test"]
    company_id: str
    portal_scope_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    reviewed: bool
    authority_assurance: Literal["LOCAL_OPERATOR_ATTESTATION"] | None
    authorization_id: str | None
    authorized: bool
    attempt_id: str | None
    attempt_status: str | None
    physical_post_count: int = Field(ge=0, le=1)
    delivery_duration_ms: int | None = Field(default=None, ge=0)
    events: list[ExecutionEventResponse]
    provider_task_id: str | None
    receipt_recorded: bool
    receipt_id: str | None
    receipt_result_class: str | None
    reconciliations: list[str]
    reconciliation_ids: list[str]
    read_back: str | None
    operational_outcome: Literal["CRM_TASK_CONFIRMED_CREATED"] | None
    operational_outcome_id: str | None


@router.get("/executions/{plan_id}", response_model=ExecutionTraceResponse)
def get_execution(plan_id: UUID, session: SessionDependency) -> ExecutionTraceResponse:
    if get_settings().app_env == "production":
        raise HTTPException(status_code=404, detail="not found")
    try:
        return ExecutionTraceResponse.model_validate(execution_trace(session, plan_id))
    except ExecutionGateError as exc:
        raise HTTPException(status_code=404, detail="execution unavailable") from exc
