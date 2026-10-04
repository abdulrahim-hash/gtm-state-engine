"""Local-only read view of the accepted M2B public-company pilot."""

from __future__ import annotations

from json import loads
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from gtm_state_api.config import get_settings
from gtm_state_api.database import get_session
from gtm_state_api.pilot_m2b import load_manifest
from gtm_state_api.pilot_m2b_run import export_trace, verify_acceptance

router = APIRouter(prefix="/api/v1/pilot/m2b", tags=["M2B local pilot"])
SessionDependency = Annotated[Session, Depends(get_session)]
PILOT_ROOT = Path(__file__).resolve().parents[4] / "docs" / "pilot" / "m2b"


@router.get("/trace", response_model=dict[str, Any])
def get_local_pilot_trace(session: SessionDependency) -> dict[str, Any]:
    """Serve the verified semantic trace only from a local application process."""

    if get_settings().app_env == "production":
        raise HTTPException(status_code=404, detail="pilot trace unavailable")
    try:
        manifest, manifest_hash = load_manifest(PILOT_ROOT / "selection_manifest.v2.json")
        ledger = loads((PILOT_ROOT / "selection_ledger.v1.json").read_text(encoding="utf-8"))
        verify_acceptance(session, PILOT_ROOT, manifest, manifest_hash, ledger)
        return export_trace(session, manifest, ledger)
    except (OSError, ValueError, KeyError) as exc:
        raise HTTPException(status_code=404, detail="accepted pilot trace unavailable") from exc
