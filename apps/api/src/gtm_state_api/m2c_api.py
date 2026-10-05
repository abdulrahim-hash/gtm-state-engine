"""Local-only, read-only inspection of M2C source reads and semantic traces."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from gtm_state_api.config import get_settings
from gtm_state_api.database import get_session
from gtm_state_api.m2c_run import export_trace, inspect_run

router = APIRouter(prefix="/api/v1/pilot/m2c", tags=["M2C local CRM test"])
SessionDependency = Annotated[Session, Depends(get_session)]


def _local_only() -> None:
    if get_settings().app_env == "production":
        raise HTTPException(status_code=404, detail="not found")


@router.get("/runs/{run_id}", response_model=dict[str, Any])
def get_source_read_run(run_id: UUID, session: SessionDependency) -> dict[str, Any]:
    _local_only()
    try:
        return inspect_run(session, run_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="source read run unavailable") from exc


@router.get("/trace", response_model=dict[str, Any])
def get_crm_test_trace(as_of: datetime, session: SessionDependency) -> dict[str, Any]:
    _local_only()
    try:
        return export_trace(session, as_of=as_of)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="M2C trace unavailable") from exc
