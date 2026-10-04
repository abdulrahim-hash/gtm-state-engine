"""Local M2B pilot identity, manifest, and hypothesis-first strategy setup."""

from __future__ import annotations

from datetime import UTC, datetime
from hashlib import sha256
from json import dumps, loads
from pathlib import Path
from uuid import UUID, uuid5

from sqlalchemy import select
from sqlalchemy.orm import Session

from gtm_state_api.ingestion_service import require_local_ingestion
from gtm_state_api.models import (
    DecisionDefinition,
    Evidence,
    PolicyDefinition,
    SignalDefinition,
    StrategyFitCriterion,
    StrategyVersion,
    Workspace,
)
from gtm_state_api.schemas import EvidenceValidationInput
from gtm_state_api.source_observation import ACCOUNT_NAMESPACE
from gtm_state_api.types import (
    EvaluationDefinitionStatus,
    EvidenceAssertion,
    EvidenceClassification,
    EvidenceFreshness,
    PolicyTarget,
    SignalCategory,
    SignalDefinitionStatus,
    StrategyStatus,
    StrategyTopic,
)

WORKSPACE_SLUG = "m2b-sales-enablement-public-pilot"
WORKSPACE_ID = uuid5(ACCOUNT_NAMESPACE, f"local-workspace:{WORKSPACE_SLUG}")
STRATEGY_VERSION = "0.1.0"
STRATEGY_ID = uuid5(ACCOUNT_NAMESPACE, f"pilot-strategy:{WORKSPACE_ID}:{STRATEGY_VERSION}")
PROFILE_KEY = "account_profile.offers_sales_enablement_software"
LEADER_KEY = "commercial_event.new_revenue_leader"


def canonical_hash(value: object) -> str:
    return sha256(dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def load_manifest(path: Path) -> tuple[dict[str, object], str]:
    raw = path.read_bytes()
    value: dict[str, object] = loads(raw)
    base = value["base_candidates"]
    queue = value["trace_coverage_screening_queue"]
    if not isinstance(base, list) or not isinstance(queue, list):
        raise ValueError("invalid selection cohort lists")
    domains = base + queue
    if value["manifest_schema"] != "m2b_selection_manifest/2.0.0":
        raise ValueError("unsupported pilot manifest")
    if (
        len(base) != 18
        or len(domains) != value["roster_count"]
        or len(set(domains)) != len(domains)
    ):
        raise ValueError("invalid frozen pilot roster")
    if any(not isinstance(domain, str) or domain.lower() != domain for domain in domains):
        raise ValueError("non-normalized pilot domain")
    roster_bytes = ("\n".join(sorted(domains)) + "\n").encode()
    if sha256(roster_bytes).hexdigest() != value["roster_sha256"]:
        raise ValueError("pilot roster hash mismatch")
    order = sorted(
        domains,
        key=lambda domain: (sha256(f"gtm-m2b-v1:{domain}".encode()).hexdigest(), domain),
    )
    if order[:18] != base or order[18:] != queue:
        raise ValueError("pilot sample is not in frozen hash order")
    timestamps = [
        datetime.fromisoformat(str(value[key]).replace("Z", "+00:00"))
        for key in ("collection_cutoff", "evaluation_as_of", "state_as_of")
    ]
    if any(item.tzinfo is None for item in timestamps) or len(set(timestamps)) != 1:
        raise ValueError("pilot semantic times must be one explicit instant")
    if value["signal_window_days"] != 90 or value["profile_window_days"] != 14:
        raise ValueError("pilot rule windows changed")
    return value, sha256(raw).hexdigest()


CLAIMS: tuple[tuple[StrategyTopic, EvidenceClassification, str], ...] = (
    (
        StrategyTopic.MARKET,
        EvidenceClassification.FACT,
        "The G2 Sales Enablement category page reported 194 products in October 2026; "
        "this is a product listing count, not a count of qualified companies.",
    ),
    (
        StrategyTopic.SEGMENTATION,
        EvidenceClassification.HYPOTHESIS,
        "B2B sales enablement software vendors form a bounded technical pilot segment; "
        "category membership does not establish commercial demand.",
    ),
    (
        StrategyTopic.ICP,
        EvidenceClassification.HYPOTHESIS,
        "An official current sales enablement software offering is the sole narrow pilot Fit "
        "criterion, not validated ICP quality or purchase likelihood.",
    ),
    (
        StrategyTopic.BUYER_HYPOTHESES,
        EvidenceClassification.HYPOTHESIS,
        "Revenue operations or revenue leadership might assess evidence-backed account "
        "prioritization; no buyer need has been validated.",
    ),
    (
        StrategyTopic.PROBLEM_HYPOTHESIS,
        EvidenceClassification.HYPOTHESIS,
        "Fragmented account changes might make prioritization and review harder; "
        "the pilot does not measure this problem or willingness to pay.",
    ),
    (
        StrategyTopic.GTM_MOTION,
        EvidenceClassification.HYPOTHESIS,
        "A new revenue leader may justify internal research and human review; "
        "no outreach channel, offer, message, or seller assignment is authorized.",
    ),
)


def ensure(session: Session, instance: object, identity: UUID, fields: tuple[str, ...]) -> None:
    existing = session.get(type(instance), identity)
    if existing is None:
        session.add(instance)
        session.flush()
    elif any(getattr(existing, key) != getattr(instance, key) for key in fields):
        raise ValueError(f"pilot setup drift in {type(instance).__name__}")


def setup(
    session: Session,
    manifest: dict[str, object],
    manifest_hash: str,
    *,
    workspace_id: UUID = WORKSPACE_ID,
    strategy_id: UUID = STRATEGY_ID,
    workspace_slug: str = WORKSPACE_SLUG,
) -> dict[str, str]:
    require_local_ingestion()
    now = datetime.now(UTC)
    observed = datetime.fromisoformat(str(manifest["roster_observed_at"]).replace("Z", "+00:00"))
    with session.begin():
        ensure(
            session,
            Workspace(
                workspace_id=workspace_id,
                slug=workspace_slug,
                name="REAL PUBLIC-DATA PILOT - B2B sales enablement",
                demo_mode=False,
                demo_as_of=None,
                created_at=now,
            ),
            workspace_id,
            ("slug", "name", "demo_mode", "demo_as_of"),
        )
        ensure(
            session,
            StrategyVersion(
                id=strategy_id,
                workspace_id=workspace_id,
                semantic_version=STRATEGY_VERSION,
                status=StrategyStatus.ACTIVE,
                name="B2B sales enablement public-data pilot",
                summary=(
                    "Technical reasoning, timing, and governance with one narrow Fit criterion."
                ),
                synthetic_disclaimer="REAL PUBLIC-DATA PILOT. HYPOTHESIS / COMMERCIALLY "
                "UNVALIDATED. Fit MATCH supports only the official public pilot criterion. "
                "No outreach, CRM write, seller task, reply, meeting, or revenue occurred.",
                created_at=now,
                activated_at=now,
            ),
            strategy_id,
            (
                "workspace_id",
                "semantic_version",
                "status",
                "name",
                "summary",
                "synthetic_disclaimer",
            ),
        )
        evidence_ids: dict[StrategyTopic, UUID] = {}
        for topic, epistemic, claim in CLAIMS:
            eid = uuid5(
                ACCOUNT_NAMESPACE,
                f"pilot-strategy-evidence:{strategy_id}:{topic.value}:"
                f"{sha256(claim.encode()).hexdigest()}",
            )
            source = (
                "https://www.g2.com/categories/sales-enablement"
                if epistemic is EvidenceClassification.FACT
                else f"pilot-manifest:{manifest_hash}"
            )
            data = EvidenceValidationInput(
                strategy_version_id=strategy_id,
                strategy_topic=topic,
                classification=epistemic,
                source_provider="manual_pilot_strategy",
                source_reference=source,
                source_uri=source if epistemic is EvidenceClassification.FACT else None,
                observed_at=observed,
                ingested_at=now,
                normalized_fact=claim,
                raw_payload_hash=canonical_hash(
                    {"topic": topic.value, "claim": claim, "source": source}
                ),
                freshness=EvidenceFreshness.UNKNOWN,
                confidence=None,
            )
            ensure(
                session,
                Evidence(id=eid, **data.model_dump()),
                eid,
                (
                    "strategy_version_id",
                    "strategy_topic",
                    "classification",
                    "source_reference",
                    "normalized_fact",
                    "raw_payload_hash",
                ),
            )
            evidence_ids[topic] = eid
        fit_id = uuid5(ACCOUNT_NAMESPACE, f"pilot-fit:{strategy_id}:profile")
        ensure(
            session,
            StrategyFitCriterion(
                fit_criterion_id=fit_id,
                workspace_id=workspace_id,
                strategy_version_id=strategy_id,
                stable_key="official_sales_enablement_offering",
                display_name="Official public sales enablement software offering",
                description="Narrow pilot criterion only; MATCH is not validated ICP fit.",
                input_fact_key=PROFILE_KEY,
                expected_assertion=EvidenceAssertion.PRESENT,
                source_strategy_evidence_id=evidence_ids[StrategyTopic.ICP],
                created_at=now,
            ),
            fit_id,
            (
                "workspace_id",
                "strategy_version_id",
                "stable_key",
                "input_fact_key",
                "expected_assertion",
                "source_strategy_evidence_id",
            ),
        )
        sid = uuid5(ACCOUNT_NAMESPACE, f"pilot-signal:{strategy_id}:leader")
        ensure(
            session,
            SignalDefinition(
                signal_definition_id=sid,
                workspace_id=workspace_id,
                strategy_version_id=strategy_id,
                stable_key="new_revenue_leader",
                display_name="New revenue leader",
                description="Official dated appointment in the existing inclusive 90-day window.",
                category=SignalCategory.LEADERSHIP,
                input_fact_key=LEADER_KEY,
                evaluator_key="latest_assertion_with_freshness",
                freshness_window_days=90,
                rule_version="1.0.0",
                status=SignalDefinitionStatus.ENABLED,
                created_at=now,
            ),
            sid,
            (
                "workspace_id",
                "strategy_version_id",
                "stable_key",
                "input_fact_key",
                "evaluator_key",
                "freshness_window_days",
                "rule_version",
                "status",
            ),
        )
        did = uuid5(ACCOUNT_NAMESPACE, f"pilot-decision:{strategy_id}")
        ensure(
            session,
            DecisionDefinition(
                decision_definition_id=did,
                workspace_id=workspace_id,
                strategy_version_id=strategy_id,
                stable_key="pilot_account_response",
                definition_version="1.0.0",
                display_name="Pilot account response posture",
                description="ENGAGE means consideration only, never execution.",
                evaluator_key="fit_timing_response_matrix",
                evaluator_version="1.0.0",
                status=EvaluationDefinitionStatus.ENABLED,
                created_at=now,
            ),
            did,
            (
                "workspace_id",
                "strategy_version_id",
                "stable_key",
                "definition_version",
                "evaluator_key",
                "evaluator_version",
                "status",
            ),
        )
        pid = uuid5(ACCOUNT_NAMESPACE, f"pilot-policy:{strategy_id}")
        ensure(
            session,
            PolicyDefinition(
                policy_definition_id=pid,
                workspace_id=workspace_id,
                strategy_version_id=strategy_id,
                stable_key="pilot_prospecting_guardrails",
                definition_version="1.0.0",
                display_name="Pilot prospecting guardrails",
                description="Governance without external-action authorization.",
                target=PolicyTarget.PROSPECTING_ACTIVATION,
                evaluator_key="state_and_relationship_gate",
                evaluator_version="1.0.0",
                status=EvaluationDefinitionStatus.ENABLED,
                created_at=now,
            ),
            pid,
            (
                "workspace_id",
                "strategy_version_id",
                "stable_key",
                "definition_version",
                "target",
                "evaluator_key",
                "evaluator_version",
                "status",
            ),
        )
        active = session.scalars(
            select(StrategyVersion.id).where(
                StrategyVersion.workspace_id == workspace_id,
                StrategyVersion.status == StrategyStatus.ACTIVE,
            )
        ).all()
        if active != [strategy_id]:
            raise ValueError("pilot has an unexpected active strategy")
    return {
        "workspace_id": str(workspace_id),
        "strategy_version_id": str(strategy_id),
        "strategy_version": STRATEGY_VERSION,
        "semantic_as_of": str(manifest["state_as_of"]),
        "manifest_sha256": manifest_hash,
        "status": "HYPOTHESIS / COMMERCIALLY UNVALIDATED",
    }
