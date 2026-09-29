"""Health endpoints with intentionally bounded public responses."""

from typing import Annotated

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse

from gtm_state_api import __version__
from gtm_state_api.database import database_is_ready
from gtm_state_api.schemas import LivenessResponse, ReadinessResponse

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live", response_model=LivenessResponse)
def liveness() -> LivenessResponse:
    """Report process liveness without checking external dependencies."""

    return LivenessResponse(version=__version__)


def readiness_check() -> bool:
    """Dependency seam kept explicit for testing and future observability."""

    return database_is_ready()


@router.get(
    "/ready",
    response_model=ReadinessResponse,
    responses={status.HTTP_503_SERVICE_UNAVAILABLE: {"model": ReadinessResponse}},
)
def readiness(
    is_ready: Annotated[bool, Depends(readiness_check)],
) -> ReadinessResponse | JSONResponse:
    """Report only the bounded readiness state, never connection details."""

    response = ReadinessResponse(status="ready" if is_ready else "not_ready")
    if not is_ready:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content=response.model_dump(),
        )
    return response
