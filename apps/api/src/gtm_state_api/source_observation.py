"""Provider-neutral, bounded source observation contract and semantic identity helpers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from json import dumps
from typing import Any
from uuid import UUID, uuid5

from gtm_state_api.types import IngestionReason

INGESTION_NAMESPACE = UUID("f05d18dd-7b45-4e63-9e73-3ab010100001")
ACCOUNT_NAMESPACE = UUID("f05d18dd-7b45-4e63-9e73-3ab010100002")
IDENTITY_RULE_VERSION = "1.0.0"


def canonical_hash(value: Any) -> str:
    """Hash semantic JSON, excluding operational clocks from callers' inputs."""
    return sha256(
        dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def semantic_id(kind: str, value: Any) -> UUID:
    return uuid5(INGESTION_NAMESPACE, f"{kind}:{canonical_hash(value)}")


@dataclass(frozen=True)
class SourceObservationInput:
    """Validated source values before Account resolution or fact mapping."""

    external_record_id: str
    external_account_id: str | None
    company_name: str
    company_domain: str | None
    source_observed_at: datetime
    event_at: datetime | None
    citation_url: str | None
    fact_code: str
    assertion: str
    excerpt: str
    original_fields: dict[str, str]
    payload_sha256: str

    def __post_init__(self) -> None:
        if self.source_observed_at.tzinfo is None:
            raise ValueError("source_observed_at must have a timezone")
        if self.event_at is not None and self.event_at.tzinfo is None:
            raise ValueError("event_at must have a timezone")
        if self.payload_sha256 != canonical_hash(self.original_fields):
            raise ValueError("source payload hash does not match approved original fields")

    @property
    def observed_utc(self) -> datetime:
        return self.source_observed_at.astimezone(UTC)


@dataclass(frozen=True)
class ParsedOccurrence:
    """One row occurrence, including a bounded validation failure."""

    ordinal: int
    row_sha256: str
    observation: SourceObservationInput | None
    reason: IngestionReason | None


def observation_id(
    workspace_id: UUID, source_system_key: str, dataset_key: str, value: SourceObservationInput
) -> UUID:
    return semantic_id(
        "source-observation",
        {
            "workspace_id": str(workspace_id),
            "source_system_key": source_system_key,
            "dataset_key": dataset_key,
            "external_record_id": value.external_record_id,
            "source_observed_at": value.observed_utc.isoformat(),
            "payload_sha256": value.payload_sha256,
        },
    )
