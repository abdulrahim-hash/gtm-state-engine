"""Explicit versioned normalization preview and same-Account Evidence promotion."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from gtm_state_api.current_evidence import current_evidence_condition
from gtm_state_api.ingestion_identity import IDENTITY_RULE_REGISTRY
from gtm_state_api.ingestion_mapping import MappingRejection, NormalizedFact, get_mapper
from gtm_state_api.ingestion_service import (
    _new_result,
    create_imported_evidence,
    require_local_ingestion,
)
from gtm_state_api.local_csv import SOURCE_SYSTEM_KEY, _observation
from gtm_state_api.models import (
    Evidence,
    EvidenceSupersession,
    IngestionBatch,
    NormalizationResult,
    SourceObservation,
    Workspace,
)
from gtm_state_api.source_observation import semantic_id
from gtm_state_api.types import (
    EvidenceSupersessionReason,
    IngestionReason,
    NormalizationOutcome,
)


def _active_observation_evidence(session: Session, observation_id: UUID) -> list[Evidence]:
    return list(
        session.scalars(
            select(Evidence)
            .join(
                NormalizationResult,
                Evidence.normalization_result_id == NormalizationResult.id,
            )
            .where(
                NormalizationResult.source_observation_id == observation_id,
                current_evidence_condition(),
            )
        ).all()
    )


def reprocess_observation(
    session: Session,
    observation_id: UUID,
    *,
    mapper_key: str,
    mapper_version: str,
    identity_rule_version: str,
) -> UUID:
    """Persist a preview result; never create Evidence or change current selection."""
    require_local_ingestion()
    with session.begin():
        observation = session.get(SourceObservation, observation_id)
        if observation is None:
            raise ValueError("source observation not found")
        workspace = session.get(Workspace, observation.workspace_id)
        if workspace is None or workspace.demo_mode:
            raise ValueError("reprocessing requires a local non-demo workspace")
        batch = session.get(IngestionBatch, observation.first_batch_id)
        if batch is None:
            raise ValueError("source observation batch is missing")
        mapper = get_mapper(batch.schema_key, batch.schema_version, mapper_key, mapper_version)
        resolver = IDENTITY_RULE_REGISTRY.get(identity_rule_version)
        if resolver is None:
            raise ValueError("unsupported identity rule version")
        result_id = semantic_id(
            "normalization-result",
            {
                "source_observation_id": str(observation_id),
                "mapper_key": mapper_key,
                "mapper_version": mapper_version,
                "identity_rule_version": identity_rule_version,
            },
        )
        existing = session.get(NormalizationResult, result_id)
        if existing is not None:
            return existing.id
        if observation.source_system_key != SOURCE_SYSTEM_KEY:
            raise ValueError("no registered decoder for source system")
        source = _observation(observation.original_fields)
        identity = resolver(
            session,
            workspace_id=observation.workspace_id,
            source_system_key=observation.source_system_key,
            dataset_key=observation.dataset_key,
            observation=source,
            preflight_reason=None,
        )
        conflicts = session.scalars(
            select(SourceObservation.id).where(
                SourceObservation.workspace_id == observation.workspace_id,
                SourceObservation.source_system_key == observation.source_system_key,
                SourceObservation.dataset_key == observation.dataset_key,
                SourceObservation.external_record_id == observation.external_record_id,
                SourceObservation.source_observed_at == observation.source_observed_at,
                SourceObservation.id != observation.id,
            )
        ).all()
        fact: NormalizedFact | None = None
        mapping_reason: IngestionReason | None = None
        if not conflicts:
            try:
                fact = mapper.normalize(source)
            except MappingRejection as exc:
                mapping_reason = exc.reason
        if conflicts:
            outcome = NormalizationOutcome.CONFLICT
            reason = IngestionReason.SOURCE_RECORD_CONFLICT
        elif mapping_reason:
            outcome = NormalizationOutcome.REJECTED
            reason = mapping_reason
        elif identity.reason or identity.new_account_id is not None:
            outcome = NormalizationOutcome.UNRESOLVED
            reason = identity.reason or IngestionReason.MISSING_IDENTITY
        else:
            outcome = NormalizationOutcome.ACCEPTED
            reason = None
        account_id = identity.account.id if identity.account else None
        active = _active_observation_evidence(session, observation_id)
        if len(active) > 1:
            raise ValueError("observation has multiple current Evidence rows")
        if (
            active
            and outcome is NormalizationOutcome.ACCEPTED
            and active[0].account_id != account_id
        ):
            raise ValueError("M2A cannot reassign accepted Evidence to another Account")
        result = _new_result(
            workspace_id=observation.workspace_id,
            source_observation_id=observation.id,
            mapper_key=mapper_key,
            mapper_version=mapper_version,
            identity_rule_version=identity_rule_version,
            output_schema_version=mapper.output_schema_version,
            outcome=outcome,
            reason=reason,
            account_id=account_id if outcome is NormalizationOutcome.ACCEPTED else None,
            fact=fact if outcome is NormalizationOutcome.ACCEPTED else None,
            resolution_input_hash=identity.input_hash,
            processed_at=datetime.now(UTC),
        )
        session.add(result)
        session.flush()
        return result.id


def promote_normalization_result(session: Session, result_id: UUID) -> UUID:
    """Create Evidence and append its supersession only on an explicit local command."""
    require_local_ingestion()
    with session.begin():
        result = session.get(NormalizationResult, result_id)
        if result is None or result.outcome is not NormalizationOutcome.ACCEPTED:
            raise ValueError("only accepted normalization results can be promoted")
        observation = session.get(SourceObservation, result.source_observation_id)
        if observation is None:
            raise ValueError("source observation is missing")
        workspace = session.get(Workspace, observation.workspace_id)
        if workspace is None or workspace.demo_mode:
            raise ValueError("promotion requires a local non-demo workspace")
        existing = session.scalar(
            select(Evidence).where(Evidence.normalization_result_id == result.id)
        )
        if existing is not None:
            return existing.id
        active = _active_observation_evidence(session, observation.id)
        if len(active) > 1:
            raise ValueError("observation has multiple current Evidence rows")
        prior = active[0] if active else None
        if prior is not None and prior.account_id != result.account_id:
            raise ValueError("M2A cannot move accepted Evidence to another Account")
        evidence = create_imported_evidence(
            session, result, observation, ingested_at=datetime.now(UTC)
        )
        if prior is not None:
            prior_result = session.get(NormalizationResult, prior.normalization_result_id)
            if prior_result is None:
                raise ValueError("prior normalization result is missing")
            reason = (
                EvidenceSupersessionReason.IDENTITY_RULE_PROMOTION
                if result.identity_rule_version != prior_result.identity_rule_version
                else EvidenceSupersessionReason.MAPPER_VERSION_PROMOTION
            )
            session.add(
                EvidenceSupersession(
                    id=semantic_id(
                        "evidence-supersession",
                        {"old_evidence_id": str(prior.id), "new_evidence_id": str(evidence.id)},
                    ),
                    old_evidence_id=prior.id,
                    new_evidence_id=evidence.id,
                    reason=reason,
                    promoted_at=datetime.now(UTC),
                )
            )
            session.flush()
        return evidence.id
