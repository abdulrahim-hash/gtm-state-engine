"""Public API response contracts."""

from typing import Literal

from pydantic import BaseModel, ConfigDict


class LivenessResponse(BaseModel):
    """Process-level liveness without infrastructure details."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["ok"] = "ok"
    service: Literal["gtm-state-api"] = "gtm-state-api"
    version: str


class ReadinessResponse(BaseModel):
    """Dependency readiness without leaking database details."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["ready", "not_ready"]
