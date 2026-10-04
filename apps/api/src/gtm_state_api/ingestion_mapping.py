"""Code-owned deterministic source-schema-to-Evidence mapping registry."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from gtm_state_api.source_observation import SourceObservationInput, canonical_hash
from gtm_state_api.types import EvidenceAssertion, EvidenceClassification, IngestionReason


@dataclass(frozen=True)
class NormalizedFact:
    fact_key: str
    assertion: EvidenceAssertion
    classification: EvidenceClassification
    normalized_fact: str
    observed_at: datetime
    output_schema_version: str
    output_sha256: str


@dataclass(frozen=True)
class MapperSpec:
    schema_key: str
    schema_version: str
    mapper_key: str
    mapper_version: str
    output_schema_version: str
    supported_fact_key: str
    supported_fact_code: str
    allowed_assertions: frozenset[EvidenceAssertion]
    classification: EvidenceClassification
    source_fields: tuple[str, ...]
    required_timestamps: tuple[str, ...]
    normalize: Callable[[SourceObservationInput], NormalizedFact]


class MappingRejection(ValueError):
    def __init__(self, reason: IngestionReason) -> None:
        super().__init__(reason.value)
        self.reason = reason


def normalize_public_leader_event(value: SourceObservationInput) -> NormalizedFact:
    if value.fact_code != "new_revenue_leader":
        raise MappingRejection(IngestionReason.UNSUPPORTED_FACT)
    try:
        assertion = EvidenceAssertion(value.assertion)
    except ValueError as exc:
        raise MappingRejection(IngestionReason.INVALID_ASSERTION) from exc
    if assertion not in LEADER_MAPPER.allowed_assertions:
        raise MappingRejection(IngestionReason.INVALID_ASSERTION)
    if value.event_at is None:
        raise MappingRejection(IngestionReason.EVENT_TIME_REQUIRED)
    statement = f"Company page assertion {assertion.value}: {value.excerpt}"
    output = {
        "fact_key": LEADER_MAPPER.supported_fact_key,
        "assertion": assertion.value,
        "classification": LEADER_MAPPER.classification.value,
        "normalized_fact": statement,
        "observed_at": value.event_at.isoformat(),
        "output_schema_version": LEADER_MAPPER.output_schema_version,
    }
    return NormalizedFact(
        fact_key=LEADER_MAPPER.supported_fact_key,
        assertion=assertion,
        classification=LEADER_MAPPER.classification,
        normalized_fact=statement,
        observed_at=value.event_at,
        output_schema_version=LEADER_MAPPER.output_schema_version,
        output_sha256=canonical_hash(output),
    )


def normalize_public_profile(value: SourceObservationInput) -> NormalizedFact:
    """Record a dated official-company profile observation, never an invented event."""

    if value.fact_code != "offers_sales_enablement_software":
        raise MappingRejection(IngestionReason.UNSUPPORTED_FACT)
    try:
        assertion = EvidenceAssertion(value.assertion)
    except ValueError as exc:
        raise MappingRejection(IngestionReason.INVALID_ASSERTION) from exc
    if assertion not in PROFILE_MAPPER.allowed_assertions:
        raise MappingRejection(IngestionReason.INVALID_ASSERTION)
    if value.event_at is not None:
        raise MappingRejection(IngestionReason.INVALID_DATE)
    statement = f"Official company page assertion {assertion.value}: {value.excerpt}"
    output = {
        "fact_key": PROFILE_MAPPER.supported_fact_key,
        "assertion": assertion.value,
        "classification": PROFILE_MAPPER.classification.value,
        "normalized_fact": statement,
        "observed_at": value.observed_utc.isoformat(),
        "output_schema_version": PROFILE_MAPPER.output_schema_version,
    }
    return NormalizedFact(
        fact_key=PROFILE_MAPPER.supported_fact_key,
        assertion=assertion,
        classification=PROFILE_MAPPER.classification,
        normalized_fact=statement,
        observed_at=value.observed_utc,
        output_schema_version=PROFILE_MAPPER.output_schema_version,
        output_sha256=canonical_hash(output),
    )


LEADER_MAPPER = MapperSpec(
    schema_key="company_public_event",
    schema_version="1.0.0",
    mapper_key="public_company_leader_event",
    mapper_version="1.0.0",
    output_schema_version="1.0.0",
    supported_fact_key="commercial_event.new_revenue_leader",
    supported_fact_code="new_revenue_leader",
    allowed_assertions=frozenset(EvidenceAssertion),
    classification=EvidenceClassification.FACT,
    source_fields=(
        "company_name",
        "company_domain",
        "source_observed_at",
        "event_at",
        "source_url",
        "fact_code",
        "assertion",
        "source_excerpt",
    ),
    required_timestamps=("source_observed_at", "event_at"),
    normalize=normalize_public_leader_event,
)


PROFILE_MAPPER = MapperSpec(
    schema_key="company_public_profile",
    schema_version="1.0.0",
    mapper_key="public_sales_enablement_profile",
    mapper_version="1.0.0",
    output_schema_version="1.0.0",
    supported_fact_key="account_profile.offers_sales_enablement_software",
    supported_fact_code="offers_sales_enablement_software",
    allowed_assertions=frozenset({EvidenceAssertion.PRESENT, EvidenceAssertion.INCONCLUSIVE}),
    classification=EvidenceClassification.FACT,
    source_fields=LEADER_MAPPER.source_fields,
    required_timestamps=("source_observed_at",),
    normalize=normalize_public_profile,
)

MAPPER_REGISTRY: dict[tuple[str, str, str, str], MapperSpec] = {
    (
        LEADER_MAPPER.schema_key,
        LEADER_MAPPER.schema_version,
        LEADER_MAPPER.mapper_key,
        LEADER_MAPPER.mapper_version,
    ): LEADER_MAPPER,
    (
        PROFILE_MAPPER.schema_key,
        PROFILE_MAPPER.schema_version,
        PROFILE_MAPPER.mapper_key,
        PROFILE_MAPPER.mapper_version,
    ): PROFILE_MAPPER,
}


def get_mapper(
    schema_key: str, schema_version: str, mapper_key: str, mapper_version: str
) -> MapperSpec:
    try:
        return MAPPER_REGISTRY[(schema_key, schema_version, mapper_key, mapper_version)]
    except KeyError as exc:
        raise ValueError("unsupported source schema or mapper version") from exc
