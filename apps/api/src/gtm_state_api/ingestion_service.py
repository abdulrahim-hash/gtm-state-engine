"""Atomic local ingestion from validated source observations into canonical Evidence."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path
from time import monotonic
from uuid import UUID, uuid4

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from gtm_state_api.config import get_settings
from gtm_state_api.ingestion_identity import (
    IDENTITY_RULE_REGISTRY,
    normalize_domain,
    preflight_identity,
)
from gtm_state_api.ingestion_mapping import MappingRejection, NormalizedFact, get_mapper
from gtm_state_api.local_csv import (
    CSV_SCHEMA_KEY,
    CSV_SCHEMA_VERSION,
    DATASET_REGISTRY,
    SOURCE_SYSTEM_KEY,
    parse_local_csv,
)
from gtm_state_api.models import (
    Account,
    AccountSourceId,
    Evidence,
    IngestionBatch,
    IngestionBatchRow,
    NormalizationResult,
    SourceObservation,
    Workspace,
)
from gtm_state_api.schemas import EvidenceValidationInput
from gtm_state_api.source_observation import (
    IDENTITY_RULE_VERSION,
    ParsedOccurrence,
    observation_id,
    semantic_id,
)
from gtm_state_api.types import (
    EvidenceAssertion,
    EvidenceClassification,
    EvidenceFreshness,
    IngestionReason,
    IngestionRowOutcome,
    NormalizationOutcome,
)

logger = logging.getLogger(__name__)


def require_local_ingestion() -> None:
    """The unauthenticated hosted/public configuration cannot ingest or inspect pilot data."""
    if get_settings().app_env == "production":
        raise ValueError("local ingestion is unavailable in production")


def batch_counts(session: Session, batch_id: UUID) -> dict[str, int]:
    counts = {outcome.value.lower(): 0 for outcome in IngestionRowOutcome}
    for outcome in session.scalars(
        select(IngestionBatchRow.outcome).where(IngestionBatchRow.batch_id == batch_id)
    ):
        counts[outcome.value.lower()] += 1
    return counts


def _batch_id(workspace_id: UUID, dataset_key: str, file_sha256: str) -> UUID:
    return semantic_id(
        "ingestion-batch",
        {
            "workspace_id": str(workspace_id),
            "source_system_key": SOURCE_SYSTEM_KEY,
            "dataset_key": dataset_key,
            "schema_key": CSV_SCHEMA_KEY,
            "schema_version": CSV_SCHEMA_VERSION,
            "file_sha256": file_sha256,
        },
    )


def _record_conflicts(rows: list[ParsedOccurrence]) -> set[int]:
    versions: dict[tuple[str, datetime], set[str]] = {}
    for item in rows:
        if item.observation is None:
            continue
        source = item.observation
        key = (source.external_record_id, source.observed_utc)
        versions.setdefault(key, set()).add(source.payload_sha256)
    return {
        item.ordinal
        for item in rows
        if item.observation is not None
        and len(versions[(item.observation.external_record_id, item.observation.observed_utc)]) > 1
    }


def _new_result(
    *,
    workspace_id: UUID,
    source_observation_id: UUID,
    mapper_key: str,
    mapper_version: str,
    identity_rule_version: str,
    output_schema_version: str,
    outcome: NormalizationOutcome,
    reason: IngestionReason | None,
    account_id: UUID | None,
    fact: NormalizedFact | None,
    resolution_input_hash: str,
    processed_at: datetime,
) -> NormalizationResult:
    return NormalizationResult(
        id=semantic_id(
            "normalization-result",
            {
                "source_observation_id": str(source_observation_id),
                "mapper_key": mapper_key,
                "mapper_version": mapper_version,
                "identity_rule_version": identity_rule_version,
            },
        ),
        workspace_id=workspace_id,
        source_observation_id=source_observation_id,
        mapper_key=mapper_key,
        mapper_version=mapper_version,
        identity_rule_version=identity_rule_version,
        output_schema_version=output_schema_version,
        outcome=outcome,
        reason_code=reason,
        account_id=account_id,
        fact_key=fact.fact_key if fact else None,
        fact_assertion=fact.assertion.value if fact else None,
        evidence_classification=fact.classification.value if fact else None,
        normalized_fact=fact.normalized_fact if fact else None,
        fact_observed_at=fact.observed_at if fact else None,
        output_sha256=fact.output_sha256 if fact else None,
        resolution_input_sha256=resolution_input_hash,
        processed_at=processed_at,
    )


def create_imported_evidence(
    session: Session,
    result: NormalizationResult,
    observation: SourceObservation,
    *,
    ingested_at: datetime,
) -> Evidence:
    """Create the one canonical Evidence slot of an accepted result."""
    if result.outcome is not NormalizationOutcome.ACCEPTED or result.account_id is None:
        raise ValueError("only accepted results can produce Evidence")
    if (
        result.fact_key is None
        or result.fact_assertion is None
        or result.evidence_classification is None
        or result.normalized_fact is None
        or result.fact_observed_at is None
    ):
        raise ValueError("accepted normalization result is incomplete")
    existing = session.scalar(select(Evidence).where(Evidence.normalization_result_id == result.id))
    if existing is not None:
        return existing
    source_url = observation.original_fields["source_url"]
    evidence_input = EvidenceValidationInput(
        account_id=result.account_id,
        classification=EvidenceClassification(result.evidence_classification),
        source_provider=observation.source_system_key,
        source_reference=f"source-observation:{observation.id}",
        source_uri=source_url,
        observed_at=result.fact_observed_at,
        ingested_at=ingested_at,
        normalized_fact=result.normalized_fact,
        raw_payload_hash=observation.payload_sha256,
        freshness=EvidenceFreshness.UNKNOWN,
        confidence=None,
        fact_key=result.fact_key,
        fact_assertion=EvidenceAssertion(result.fact_assertion),
    )
    evidence = Evidence(
        id=semantic_id(
            "imported-evidence", {"normalization_result_id": str(result.id), "fact_slot": "primary"}
        ),
        normalization_result_id=result.id,
        **evidence_input.model_dump(),
    )
    session.add(evidence)
    session.flush()
    return evidence


def _one_occurrence(
    session: Session,
    *,
    batch: IngestionBatch,
    occurrence: ParsedOccurrence,
    preflight_reason: IngestionReason | None,
    record_conflict: bool,
    processed_at: datetime,
) -> IngestionBatchRow:
    source = occurrence.observation
    if source is None:
        assert occurrence.reason is not None
        return IngestionBatchRow(
            id=semantic_id("batch-row", {"batch_id": str(batch.id), "ordinal": occurrence.ordinal}),
            batch_id=batch.id,
            ordinal=occurrence.ordinal,
            row_sha256=occurrence.row_sha256,
            outcome=IngestionRowOutcome.REJECTED,
            reason_code=occurrence.reason,
            source_observation_id=None,
            normalization_result_id=None,
            processed_at=processed_at,
        )
    source_id = observation_id(
        batch.workspace_id, batch.source_system_key, batch.dataset_key, source
    )
    stored = session.get(SourceObservation, source_id)
    if stored is not None:
        return IngestionBatchRow(
            id=semantic_id("batch-row", {"batch_id": str(batch.id), "ordinal": occurrence.ordinal}),
            batch_id=batch.id,
            ordinal=occurrence.ordinal,
            row_sha256=occurrence.row_sha256,
            outcome=IngestionRowOutcome.DUPLICATE,
            reason_code=IngestionReason.DUPLICATE_OBSERVATION,
            source_observation_id=stored.id,
            normalization_result_id=None,
            processed_at=processed_at,
        )
    stored = SourceObservation(
        id=source_id,
        workspace_id=batch.workspace_id,
        source_system_key=batch.source_system_key,
        dataset_key=batch.dataset_key,
        external_record_id=source.external_record_id,
        external_account_id=source.external_account_id,
        source_observed_at=source.observed_utc,
        original_fields=source.original_fields,
        payload_sha256=source.payload_sha256,
        first_batch_id=batch.id,
        first_row_ordinal=occurrence.ordinal,
        created_at=processed_at,
    )
    session.add(stored)
    session.flush()
    prior_versions = session.scalars(
        select(SourceObservation).where(
            SourceObservation.workspace_id == batch.workspace_id,
            SourceObservation.source_system_key == batch.source_system_key,
            SourceObservation.dataset_key == batch.dataset_key,
            SourceObservation.external_record_id == source.external_record_id,
            SourceObservation.source_observed_at == source.observed_utc,
            SourceObservation.id != stored.id,
        )
    ).all()
    source_conflict = record_conflict or bool(prior_versions)
    resolver = IDENTITY_RULE_REGISTRY[batch.identity_rule_version]
    identity = resolver(
        session,
        workspace_id=batch.workspace_id,
        source_system_key=batch.source_system_key,
        dataset_key=batch.dataset_key,
        observation=source,
        preflight_reason=preflight_reason,
    )
    mapper = get_mapper(
        batch.schema_key, batch.schema_version, batch.mapper_key, batch.mapper_version
    )
    fact: NormalizedFact | None = None
    mapping_reason: IngestionReason | None = None
    if not source_conflict:
        try:
            fact = mapper.normalize(source)
        except MappingRejection as exc:
            mapping_reason = exc.reason
    if source_conflict:
        outcome = NormalizationOutcome.CONFLICT
        reason = IngestionReason.SOURCE_RECORD_CONFLICT
    elif mapping_reason:
        outcome = NormalizationOutcome.REJECTED
        reason = mapping_reason
    elif identity.reason:
        outcome = NormalizationOutcome.UNRESOLVED
        reason = identity.reason
    else:
        outcome = NormalizationOutcome.ACCEPTED
        reason = None
    account_id = identity.account.id if identity.account else identity.new_account_id
    if outcome is NormalizationOutcome.ACCEPTED:
        if account_id is None or fact is None:
            raise ValueError("accepted normalization requires Account and mapped fact")
        if identity.new_account_id is not None:
            account = Account(
                id=identity.new_account_id,
                workspace_id=batch.workspace_id,
                slug=f"account-{str(identity.new_account_id)[:12]}",
                canonical_name=source.company_name,
                domain=normalize_domain(source.company_domain or ""),
                segment=None,
                is_synthetic=False,
                created_at=processed_at,
                updated_at=processed_at,
            )
            session.add(account)
            session.flush()
        if source.external_account_id:
            binding_id = semantic_id(
                "account-source-id",
                {
                    "workspace_id": str(batch.workspace_id),
                    "source_system_key": batch.source_system_key,
                    "dataset_key": batch.dataset_key,
                    "external_account_id": source.external_account_id,
                },
            )
            if session.get(AccountSourceId, binding_id) is None:
                session.add(
                    AccountSourceId(
                        id=binding_id,
                        workspace_id=batch.workspace_id,
                        source_system_key=batch.source_system_key,
                        dataset_key=batch.dataset_key,
                        external_account_id=source.external_account_id,
                        account_id=account_id,
                        origin_observation_id=source_id,
                        created_at=processed_at,
                    )
                )
                session.flush()
    result = _new_result(
        workspace_id=batch.workspace_id,
        source_observation_id=source_id,
        mapper_key=batch.mapper_key,
        mapper_version=batch.mapper_version,
        identity_rule_version=batch.identity_rule_version,
        output_schema_version=mapper.output_schema_version,
        outcome=outcome,
        reason=reason,
        account_id=account_id if outcome is NormalizationOutcome.ACCEPTED else None,
        fact=fact if outcome is NormalizationOutcome.ACCEPTED else None,
        resolution_input_hash=identity.input_hash,
        processed_at=processed_at,
    )
    session.add(result)
    session.flush()
    if outcome is NormalizationOutcome.ACCEPTED:
        create_imported_evidence(session, result, stored, ingested_at=processed_at)
    row_outcome = {
        NormalizationOutcome.ACCEPTED: IngestionRowOutcome.ACCEPTED,
        NormalizationOutcome.REJECTED: IngestionRowOutcome.REJECTED,
        NormalizationOutcome.UNRESOLVED: IngestionRowOutcome.UNRESOLVED,
        NormalizationOutcome.CONFLICT: IngestionRowOutcome.REJECTED,
    }[outcome]
    return IngestionBatchRow(
        id=semantic_id("batch-row", {"batch_id": str(batch.id), "ordinal": occurrence.ordinal}),
        batch_id=batch.id,
        ordinal=occurrence.ordinal,
        row_sha256=occurrence.row_sha256,
        outcome=row_outcome,
        reason_code=reason,
        source_observation_id=source_id,
        normalization_result_id=result.id,
        processed_at=processed_at,
    )


def import_local_csv(
    session: Session,
    path: Path,
    *,
    workspace_id: UUID,
    dataset_key: str = "company_public_events",
    mapper_key: str = "public_company_leader_event",
    mapper_version: str = "1.0.0",
    identity_rule_version: str = IDENTITY_RULE_VERSION,
) -> UUID:
    """Commit a complete, partially accepting batch in one transaction."""
    require_local_ingestion()
    started = monotonic()
    file_sha256, rows = parse_local_csv(path, dataset_key=dataset_key)
    schema_key, schema_version = DATASET_REGISTRY[dataset_key]
    mapper = get_mapper(schema_key, schema_version, mapper_key, mapper_version)
    if identity_rule_version not in IDENTITY_RULE_REGISTRY:
        raise ValueError("unsupported identity rule version")
    batch_id = _batch_id(workspace_id, dataset_key, file_sha256)
    valid_rows = [(item.ordinal, item.observation) for item in rows if item.observation is not None]
    preflight = preflight_identity(valid_rows)
    record_conflicts = _record_conflicts(rows)
    with session.begin():
        workspace = session.get(Workspace, workspace_id)
        if workspace is None or workspace.demo_mode:
            raise ValueError("import requires an existing non-demo local workspace")
        lock_key = int.from_bytes(workspace_id.bytes[:8], byteorder="big", signed=True)
        session.execute(text("SELECT pg_advisory_xact_lock(:lock_key)"), {"lock_key": lock_key})
        existing = session.get(IngestionBatch, batch_id)
        if existing is not None:
            if (
                existing.file_sha256 != file_sha256
                or existing.expected_rows != len(rows)
                or existing.mapper_key != mapper.mapper_key
                or existing.mapper_version != mapper.mapper_version
                or existing.identity_rule_version != identity_rule_version
            ):
                raise ValueError(
                    "batch identity collides with different import settings; use reprocess"
                )
            return existing.id
        now = datetime.now(UTC)
        batch = IngestionBatch(
            id=batch_id,
            workspace_id=workspace_id,
            source_system_key=SOURCE_SYSTEM_KEY,
            dataset_key=dataset_key,
            schema_key=schema_key,
            schema_version=schema_version,
            mapper_key=mapper.mapper_key,
            mapper_version=mapper.mapper_version,
            identity_rule_version=identity_rule_version,
            file_sha256=file_sha256,
            correlation_id=uuid4(),
            expected_rows=len(rows),
            ingested_at=now,
        )
        session.add(batch)
        session.flush()
        for item in sorted(
            rows,
            key=lambda row: (
                str(observation_id(workspace_id, SOURCE_SYSTEM_KEY, dataset_key, row.observation))
                if row.observation is not None
                else f"z{row.ordinal:06d}"
            ),
        ):
            session.add(
                _one_occurrence(
                    session,
                    batch=batch,
                    occurrence=item,
                    preflight_reason=preflight.get(item.ordinal),
                    record_conflict=item.ordinal in record_conflicts,
                    processed_at=now,
                )
            )
        session.flush()
        counts = batch_counts(session, batch_id)
    logger.info(
        "ingestion_batch_committed %s",
        {
            "batch_id": str(batch_id),
            "correlation_id": str(batch.correlation_id),
            "workspace_id": str(workspace_id),
            "dataset_key": dataset_key,
            "schema_version": schema_version,
            "mapper_version": mapper_version,
            "counts": counts,
            "duration_ms": round((monotonic() - started) * 1000),
        },
    )
    return batch_id
