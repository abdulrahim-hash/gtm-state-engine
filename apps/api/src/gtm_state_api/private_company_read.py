"""Local-only private Company read into M2A provenance and canonical Evidence."""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from time import monotonic
from uuid import UUID, uuid4

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from gtm_state_api.hubspot_company_read import (
    ADAPTER_KEY,
    ADAPTER_VERSION,
    SOURCE_SYSTEM_KEY,
    CompanyRead,
    ProviderReadError,
    read_company,
    verify_developer_test_portal,
)
from gtm_state_api.ingestion_identity import normalize_domain, resolve_identity
from gtm_state_api.ingestion_mapping import CRM_CUSTOMER_MAPPER
from gtm_state_api.ingestion_service import (
    _new_result,
    create_imported_evidence,
    require_local_ingestion,
)
from gtm_state_api.m2c_workspace import WORKSPACE_SLUG
from gtm_state_api.models import (
    AccountSourceId,
    NormalizationResult,
    SourceObservation,
    SourceReadRun,
    Workspace,
)
from gtm_state_api.source_observation import (
    IDENTITY_RULE_VERSION,
    SourceObservationInput,
    canonical_hash,
    observation_id,
    semantic_id,
)
from gtm_state_api.types import IngestionReason, NormalizationOutcome

logger = logging.getLogger(__name__)
MAPPING_VERSION_RE = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")
PORTAL_RE = re.compile(r"^[0-9]{1,30}$")
DATASET_PREFIX = "crm_company_v1:"


@dataclass(frozen=True)
class CustomerStageMapping:
    """Operator-attested stage interpretation for one test portal."""

    customer_value: str
    version: str

    def __post_init__(self) -> None:
        if not self.customer_value or len(self.customer_value) > 80:
            raise ValueError("configured Customer stage must be a bounded exact value")
        if not MAPPING_VERSION_RE.fullmatch(self.version):
            raise ValueError("Customer stage mapping requires a semantic version")


def portal_scope_hash(portal_id: str) -> str:
    if not PORTAL_RE.fullmatch(portal_id):
        raise ValueError("invalid provider portal ID")
    return sha256(portal_id.encode("ascii")).hexdigest()


def scoped_dataset_key(portal_id: str) -> str:
    return DATASET_PREFIX + portal_scope_hash(portal_id)


def _finish_run(
    session: Session,
    run_id: UUID,
    *,
    status: str,
    failure_code: str | None = None,
    retries: int = 0,
    observation_id_value: UUID | None = None,
    response_sha256: str | None = None,
    correlation_id: str | None = None,
    accepted: int = 0,
    unresolved: int = 0,
    rejected: int = 0,
) -> None:
    run = session.get(SourceReadRun, run_id)
    if run is None or run.status != "RUNNING":
        raise ValueError("source read run is not open")
    run.status = status
    run.failure_code = failure_code
    run.retry_count = retries
    run.finished_at = datetime.now(UTC)
    run.observation_id = observation_id_value
    run.response_sha256 = response_sha256
    run.provider_correlation_id = correlation_id
    run.accepted_count = accepted
    run.unresolved_count = unresolved
    run.rejected_count = rejected


def _store_read(
    session: Session,
    *,
    run_id: UUID,
    workspace_id: UUID,
    portal_id: str,
    read: CompanyRead,
    mapping: CustomerStageMapping,
    observed_at: datetime,
) -> None:
    record = read.record
    if record is None:
        _finish_run(
            session,
            run_id,
            status="NOT_FOUND",
            failure_code="COMPANY_NOT_FOUND",
            retries=read.retry_count,
            correlation_id=read.provider_correlation_id,
        )
        return
    domain = normalize_domain(record.company_domain) if record.company_domain else None
    fields = {
        "company_name": record.company_name,
        "company_domain": domain or "",
        "lifecycle_stage": record.lifecycle_stage,
        "configured_customer_stage": mapping.customer_value,
        "stage_mapping_version": mapping.version,
        "provider_updated_at": (
            record.provider_updated_at.isoformat() if record.provider_updated_at else ""
        ),
    }
    payload_hash = canonical_hash(fields)
    positive = record.lifecycle_stage == mapping.customer_value
    observation = SourceObservationInput(
        external_record_id=record.provider_company_id,
        external_account_id=record.provider_company_id,
        company_name=record.company_name,
        company_domain=domain,
        source_observed_at=observed_at,
        event_at=None,
        citation_url=None,
        fact_code=CRM_CUSTOMER_MAPPER.supported_fact_code,
        assertion="PRESENT" if positive else "INCONCLUSIVE",
        excerpt="Bounded CRM company lifecycle-stage observation",
        original_fields=fields,
        payload_sha256=payload_hash,
    )
    dataset_key = scoped_dataset_key(portal_id)
    prior = session.scalars(
        select(SourceObservation).where(
            SourceObservation.workspace_id == workspace_id,
            SourceObservation.source_system_key == SOURCE_SYSTEM_KEY,
            SourceObservation.dataset_key == dataset_key,
            SourceObservation.external_record_id == record.provider_company_id,
            SourceObservation.source_observed_at == observation.observed_utc,
        )
    ).all()
    if prior and any(item.payload_sha256 != payload_hash for item in prior):
        _finish_run(
            session,
            run_id,
            status="CONFLICT",
            failure_code="SOURCE_RECORD_CONFLICT",
            retries=read.retry_count,
            response_sha256=payload_hash,
            correlation_id=read.provider_correlation_id,
        )
        return
    obs_id = observation_id(workspace_id, SOURCE_SYSTEM_KEY, dataset_key, observation)
    stored = session.get(SourceObservation, obs_id)
    if stored is not None:
        existing = session.scalar(
            select(NormalizationResult).where(
                NormalizationResult.source_observation_id == stored.id,
                NormalizationResult.mapper_key == CRM_CUSTOMER_MAPPER.mapper_key,
                NormalizationResult.mapper_version == CRM_CUSTOMER_MAPPER.mapper_version,
                NormalizationResult.identity_rule_version == IDENTITY_RULE_VERSION,
            )
        )
        status = (
            "SUCCEEDED"
            if existing and existing.outcome is NormalizationOutcome.ACCEPTED
            else "UNRESOLVED"
        )
        _finish_run(
            session,
            run_id,
            status=status,
            failure_code=None if status == "SUCCEEDED" else "PREVIOUSLY_UNRESOLVED",
            retries=read.retry_count,
            observation_id_value=obs_id,
            response_sha256=payload_hash,
            correlation_id=read.provider_correlation_id,
            accepted=int(status == "SUCCEEDED"),
            unresolved=int(status != "SUCCEEDED"),
        )
        return
    stored = SourceObservation(
        id=obs_id,
        workspace_id=workspace_id,
        source_system_key=SOURCE_SYSTEM_KEY,
        dataset_key=dataset_key,
        external_record_id=record.provider_company_id,
        external_account_id=record.provider_company_id,
        source_observed_at=observation.observed_utc,
        original_fields=fields,
        payload_sha256=payload_hash,
        first_batch_id=None,
        source_read_run_id=run_id,
        first_row_ordinal=1,
        created_at=datetime.now(UTC),
    )
    session.add(stored)
    session.flush()

    identity = resolve_identity(
        session,
        workspace_id=workspace_id,
        source_system_key=SOURCE_SYSTEM_KEY,
        dataset_key=dataset_key,
        observation=observation,
        preflight_reason=None,
    )
    reason = identity.reason
    if reason is None and identity.new_account_id is not None:
        reason = IngestionReason.AMBIGUOUS_IDENTITY
    if reason is None and identity.account is not None:
        other_binding = session.scalar(
            select(AccountSourceId.id).where(
                AccountSourceId.workspace_id == workspace_id,
                AccountSourceId.source_system_key == SOURCE_SYSTEM_KEY,
                AccountSourceId.dataset_key == dataset_key,
                AccountSourceId.account_id == identity.account.id,
                AccountSourceId.external_account_id != record.provider_company_id,
            )
        )
        if other_binding is not None:
            reason = IngestionReason.AMBIGUOUS_IDENTITY
    fact = CRM_CUSTOMER_MAPPER.normalize(observation) if reason is None else None
    account_id = identity.account.id if identity.account else identity.new_account_id
    if reason is None and account_id is None:
        raise ValueError("accepted private observation has no Account identity")
    if reason is None:
        binding_id = semantic_id(
            "account-source-id",
            {
                "workspace_id": str(workspace_id),
                "source_system_key": SOURCE_SYSTEM_KEY,
                "dataset_key": dataset_key,
                "external_account_id": record.provider_company_id,
            },
        )
        if session.get(AccountSourceId, binding_id) is None:
            session.add(
                AccountSourceId(
                    id=binding_id,
                    workspace_id=workspace_id,
                    source_system_key=SOURCE_SYSTEM_KEY,
                    dataset_key=dataset_key,
                    external_account_id=record.provider_company_id,
                    account_id=account_id,
                    origin_observation_id=obs_id,
                    created_at=datetime.now(UTC),
                )
            )
            session.flush()
    result = _new_result(
        workspace_id=workspace_id,
        source_observation_id=obs_id,
        mapper_key=CRM_CUSTOMER_MAPPER.mapper_key,
        mapper_version=CRM_CUSTOMER_MAPPER.mapper_version,
        identity_rule_version=IDENTITY_RULE_VERSION,
        output_schema_version=CRM_CUSTOMER_MAPPER.output_schema_version,
        outcome=NormalizationOutcome.UNRESOLVED if reason else NormalizationOutcome.ACCEPTED,
        reason=reason,
        account_id=account_id if reason is None else None,
        fact=fact if reason is None else None,
        resolution_input_hash=identity.input_hash,
        processed_at=datetime.now(UTC),
    )
    session.add(result)
    session.flush()
    if reason is None:
        create_imported_evidence(session, result, stored, ingested_at=datetime.now(UTC))
    _finish_run(
        session,
        run_id,
        status="UNRESOLVED" if reason else "SUCCEEDED",
        failure_code=reason.value if reason else None,
        retries=read.retry_count,
        observation_id_value=obs_id,
        response_sha256=payload_hash,
        correlation_id=read.provider_correlation_id,
        accepted=int(reason is None),
        unresolved=int(reason is not None),
    )


def read_company_into_evidence(
    session: Session,
    *,
    workspace_id: UUID,
    portal_id: str,
    company_id: str,
    credential: str,
    mapping: CustomerStageMapping,
    observed_at: datetime | None = None,
    reader: Callable[..., CompanyRead] | None = None,
) -> UUID:
    """One operator-triggered read; commit no downstream State or Action."""

    require_local_ingestion()
    scope_hash = portal_scope_hash(portal_id)
    dataset_key = scoped_dataset_key(portal_id)
    if observed_at is not None and observed_at.tzinfo is None:
        raise ValueError("source observation time must be timezone-aware")
    run_id = uuid4()
    start = monotonic()
    with session.begin():
        workspace = session.get(Workspace, workspace_id)
        if workspace is None or workspace.slug != WORKSPACE_SLUG or workspace.demo_mode:
            raise ValueError("private read requires the separate M2C local workspace")
        session.add(
            SourceReadRun(
                id=run_id,
                workspace_id=workspace_id,
                source_system_key=SOURCE_SYSTEM_KEY,
                dataset_key=dataset_key,
                adapter_key=ADAPTER_KEY,
                adapter_version=ADAPTER_VERSION,
                mapping_version=mapping.version,
                scope_sha256=scope_hash,
                request_sha256=canonical_hash(
                    {
                        "portal_scope": scope_hash,
                        "provider_company_id": company_id,
                        "configured_customer_stage": mapping.customer_value,
                        "mapping_version": mapping.version,
                    }
                ),
                response_sha256=None,
                started_at=datetime.now(UTC),
                finished_at=None,
                status="RUNNING",
                accepted_count=0,
                unresolved_count=0,
                rejected_count=0,
                retry_count=0,
                failure_code=None,
                provider_correlation_id=None,
                observation_id=None,
            )
        )
    try:
        if reader is None:
            verify_developer_test_portal(credential=credential, expected_portal_id=portal_id)
            read = read_company(company_id, credential=credential)
        else:
            read = reader(company_id, credential=credential)
    except ProviderReadError as exc:
        with session.begin():
            _finish_run(
                session,
                run_id,
                status="FAILED",
                failure_code=exc.code,
                retries=exc.retries,
                rejected=1,
            )
    else:
        try:
            with session.begin():
                lock_key = int.from_bytes(workspace_id.bytes[:8], byteorder="big", signed=True)
                session.execute(
                    text("SELECT pg_advisory_xact_lock(:lock_key)"), {"lock_key": lock_key}
                )
                _store_read(
                    session,
                    run_id=run_id,
                    workspace_id=workspace_id,
                    portal_id=portal_id,
                    read=read,
                    mapping=mapping,
                    observed_at=observed_at or datetime.now(UTC),
                )
        except Exception:
            with session.begin():
                _finish_run(
                    session,
                    run_id,
                    status="FAILED",
                    failure_code="INTERNAL_OR_INVALID_SOURCE",
                    rejected=1,
                    retries=read.retry_count,
                )
            raise
    run = session.get(SourceReadRun, run_id)
    if run is None:
        raise RuntimeError("source read run was not persisted")
    logger.info(
        "source_read_finished %s",
        {
            "run_id": str(run_id),
            "adapter": ADAPTER_KEY,
            "adapter_version": ADAPTER_VERSION,
            "provider_category": "crm_company",
            "scope_hash": scope_hash,
            "status": run.status,
            "accepted": run.accepted_count,
            "unresolved": run.unresolved_count,
            "rejected": run.rejected_count,
            "retry_count": run.retry_count,
            "failure_code": run.failure_code,
            "duration_ms": round((monotonic() - start) * 1000),
        },
    )
    session.rollback()
    return run_id
