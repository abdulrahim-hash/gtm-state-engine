"""Short-lived local operator evidence for developer-test HubSpot API grants."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path

CAPABILITIES = frozenset(
    {
        "TASK_CREATE",
        "TASK_READ",
        "COMPANY_READ",
        "TASK_COMPANY_ASSOCIATION",
        "OWNER_READ",
    }
)
SCOPE_RE = re.compile(r"^[a-z0-9._:-]{3,120}$")
MAX_BYTES = 4096


class ScopeProofError(ValueError):
    """No token, raw file content, or private CRM data enters this exception."""


def credential_fingerprint(credential: str) -> str:
    if not credential or credential.isspace():
        raise ScopeProofError("MISSING_M5A_CREDENTIAL")
    return sha256(credential.encode()).hexdigest()


def verify_scope_proof(
    proof_file: Path,
    *,
    credential: str,
    portal_id: str,
    owner_id: str,
    now: datetime,
) -> None:
    """Verify an ignored, exact-token portal-UI attestation, not OAuth introspection."""

    if now.tzinfo is None:
        raise ScopeProofError("SCOPE_PROOF_TIMEZONE_REQUIRED")
    try:
        if proof_file.stat().st_size > MAX_BYTES:
            raise ScopeProofError("SCOPE_PROOF_TOO_LARGE")
        document = json.loads(proof_file.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ScopeProofError("SCOPE_PROOF_UNAVAILABLE") from exc
    if not isinstance(document, dict) or set(document) != {
        "source",
        "portal_id",
        "owner_id",
        "credential_sha256",
        "inspected_at",
        "operator_ref",
        "capabilities",
    }:
        raise ScopeProofError("SCOPE_PROOF_SCHEMA_INVALID")
    if (
        document["source"] != "HUBSPOT_PORTAL_UI"
        or document["portal_id"] != portal_id
        or document["owner_id"] != owner_id
        or document["credential_sha256"] != credential_fingerprint(credential)
        or not isinstance(document["operator_ref"], str)
        or not 1 <= len(document["operator_ref"]) <= 120
        or not document["operator_ref"].isascii()
    ):
        raise ScopeProofError("SCOPE_PROOF_BINDING_INVALID")
    try:
        inspected = datetime.fromisoformat(document["inspected_at"].replace("Z", "+00:00"))
    except (AttributeError, TypeError, ValueError) as exc:
        raise ScopeProofError("SCOPE_PROOF_TIME_INVALID") from exc
    if inspected.tzinfo is None or not timedelta(0) <= now.astimezone(UTC) - inspected.astimezone(
        UTC
    ) <= timedelta(hours=1):
        raise ScopeProofError("SCOPE_PROOF_EXPIRED")
    capabilities = document["capabilities"]
    if not isinstance(capabilities, dict) or set(capabilities) != CAPABILITIES:
        raise ScopeProofError("SCOPE_PROOF_CAPABILITIES_INVALID")
    for scope_names in capabilities.values():
        if (
            not isinstance(scope_names, list)
            or not 1 <= len(scope_names) <= 4
            or any(
                not isinstance(name, str) or not SCOPE_RE.fullmatch(name) for name in scope_names
            )
        ):
            raise ScopeProofError("SCOPE_PROOF_SCOPES_INVALID")
