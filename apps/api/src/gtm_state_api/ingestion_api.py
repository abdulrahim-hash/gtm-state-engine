"""Local-only read APIs for immutable M2A ingestion provenance."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from gtm_state_api.config import get_settings
from gtm_state_api.database import get_session
from gtm_state_api.ingestion_service import batch_counts
from gtm_state_api.models import (
    Evidence,
    IngestionBatch,
    IngestionBatchRow,
    NormalizationResult,
    SourceObservation,
)
from gtm_state_api.types import IngestionReason, IngestionRowOutcome, NormalizationOutcome

router = APIRouter(
    prefix="/api/v1/workspaces/{workspace_id}/ingestion", tags=["M2A local inspection"]
)
SessionDependency = Annotated[Session, Depends(get_session)]


class BatchInspectionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    batch_id: UUID
    workspace_id: UUID
    source_system_key: str
    dataset_key: str
    schema_key: str
    schema_version: str
    mapper_key: str
    mapper_version: str
    identity_rule_version: str
    file_sha256: str
    expected_rows: int
    ingested_at: datetime
    counts: dict[str, int]


class ObservationInspectionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    observation_id: UUID
    external_record_id: str
    source_observed_at: datetime
    payload_sha256: str
    original_fields: dict[str, str]
    first_batch_id: UUID


class NormalizationInspectionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    result_id: UUID
    mapper_key: str
    mapper_version: str
    identity_rule_version: str
    output_schema_version: str
    outcome: NormalizationOutcome
    reason_code: IngestionReason | None
    account_id: UUID | None
    fact_key: str | None
    fact_assertion: str | None
    evidence_classification: str | None
    normalized_fact: str | None
    fact_observed_at: datetime | None
    output_sha256: str | None


class BatchRowInspectionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    row_id: UUID
    ordinal: int
    row_sha256: str
    outcome: IngestionRowOutcome
    reason_code: IngestionReason | None
    observation: ObservationInspectionResponse | None
    normalization: NormalizationInspectionResponse | None
    evidence_id: UUID | None


class BatchRowsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    batch_id: UUID
    items: list[BatchRowInspectionResponse]
    limit: int
    offset: int


class EvidenceOriginResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evidence_id: UUID
    account_id: UUID
    normalization: NormalizationInspectionResponse
    observation: ObservationInspectionResponse
    batch: BatchInspectionResponse


def _local_only() -> None:
    if get_settings().app_env == "production":
        raise HTTPException(status_code=404, detail="not found")


def _batch(session: Session, workspace_id: UUID, batch_id: UUID) -> IngestionBatch:
    batch = session.get(IngestionBatch, batch_id)
    if batch is None or batch.workspace_id != workspace_id:
        raise HTTPException(status_code=404, detail="batch not found")
    return batch


def _batch_response(session: Session, batch: IngestionBatch) -> BatchInspectionResponse:
    return BatchInspectionResponse(
        batch_id=batch.id,
        workspace_id=batch.workspace_id,
        source_system_key=batch.source_system_key,
        dataset_key=batch.dataset_key,
        schema_key=batch.schema_key,
        schema_version=batch.schema_version,
        mapper_key=batch.mapper_key,
        mapper_version=batch.mapper_version,
        identity_rule_version=batch.identity_rule_version,
        file_sha256=batch.file_sha256,
        expected_rows=batch.expected_rows,
        ingested_at=batch.ingested_at,
        counts=batch_counts(session, batch.id),
    )


def _observation_response(observation: SourceObservation) -> ObservationInspectionResponse:
    return ObservationInspectionResponse(
        observation_id=observation.id,
        external_record_id=observation.external_record_id,
        source_observed_at=observation.source_observed_at,
        payload_sha256=observation.payload_sha256,
        original_fields=observation.original_fields,
        first_batch_id=observation.first_batch_id,
    )


def _normalization_response(result: NormalizationResult) -> NormalizationInspectionResponse:
    return NormalizationInspectionResponse(
        result_id=result.id,
        mapper_key=result.mapper_key,
        mapper_version=result.mapper_version,
        identity_rule_version=result.identity_rule_version,
        output_schema_version=result.output_schema_version,
        outcome=result.outcome,
        reason_code=result.reason_code,
        account_id=result.account_id,
        fact_key=result.fact_key,
        fact_assertion=result.fact_assertion,
        evidence_classification=result.evidence_classification,
        normalized_fact=result.normalized_fact,
        fact_observed_at=result.fact_observed_at,
        output_sha256=result.output_sha256,
    )


@router.get("/batches/{batch_id}", response_model=BatchInspectionResponse)
def get_ingestion_batch(
    workspace_id: UUID, batch_id: UUID, session: SessionDependency
) -> BatchInspectionResponse:
    _local_only()
    return _batch_response(session, _batch(session, workspace_id, batch_id))


@router.get("/batches/{batch_id}/rows", response_model=BatchRowsResponse)
def get_ingestion_batch_rows(
    workspace_id: UUID,
    batch_id: UUID,
    session: SessionDependency,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> BatchRowsResponse:
    _local_only()
    _batch(session, workspace_id, batch_id)
    rows = session.scalars(
        select(IngestionBatchRow)
        .where(IngestionBatchRow.batch_id == batch_id)
        .order_by(IngestionBatchRow.ordinal)
        .limit(limit)
        .offset(offset)
    ).all()
    items: list[BatchRowInspectionResponse] = []
    for row in rows:
        observation = (
            session.get(SourceObservation, row.source_observation_id)
            if row.source_observation_id
            else None
        )
        result = (
            session.get(NormalizationResult, row.normalization_result_id)
            if row.normalization_result_id
            else None
        )
        evidence_id = (
            session.scalar(select(Evidence.id).where(Evidence.normalization_result_id == result.id))
            if result
            else None
        )
        items.append(
            BatchRowInspectionResponse(
                row_id=row.id,
                ordinal=row.ordinal,
                row_sha256=row.row_sha256,
                outcome=row.outcome,
                reason_code=row.reason_code,
                observation=_observation_response(observation) if observation else None,
                normalization=_normalization_response(result) if result else None,
                evidence_id=evidence_id,
            )
        )
    return BatchRowsResponse(batch_id=batch_id, items=items, limit=limit, offset=offset)


@router.get("/evidence/{evidence_id}/origin", response_model=EvidenceOriginResponse)
def get_imported_evidence_origin(
    workspace_id: UUID, evidence_id: UUID, session: SessionDependency
) -> EvidenceOriginResponse:
    _local_only()
    evidence = session.get(Evidence, evidence_id)
    if evidence is None or evidence.account_id is None or evidence.normalization_result_id is None:
        raise HTTPException(status_code=404, detail="imported Evidence not found")
    result = session.get(NormalizationResult, evidence.normalization_result_id)
    if result is None or result.workspace_id != workspace_id:
        raise HTTPException(status_code=404, detail="imported Evidence not found")
    observation = session.get(SourceObservation, result.source_observation_id)
    if observation is None:
        raise RuntimeError("import origin is incomplete")
    batch = _batch(session, workspace_id, observation.first_batch_id)
    return EvidenceOriginResponse(
        evidence_id=evidence.id,
        account_id=evidence.account_id,
        normalization=_normalization_response(result),
        observation=_observation_response(observation),
        batch=_batch_response(session, batch),
    )
