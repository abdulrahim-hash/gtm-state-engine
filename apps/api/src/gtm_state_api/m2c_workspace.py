"""Isolated synthetic CRM test workspace and minimal deterministic reasoning fixtures."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid5

from sqlalchemy import select
from sqlalchemy.orm import Session

from gtm_state_api.ingestion_service import require_local_ingestion
from gtm_state_api.models import (
    Account,
    DecisionDefinition,
    Evidence,
    PolicyDefinition,
    SignalDefinition,
    StrategyFitCriterion,
    StrategyVersion,
    Workspace,
)
from gtm_state_api.schemas import EvidenceValidationInput
from gtm_state_api.source_observation import ACCOUNT_NAMESPACE, canonical_hash
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

WORKSPACE_SLUG = "m2c-crm-relationship-test"
WORKSPACE_ID = uuid5(ACCOUNT_NAMESPACE, f"local-workspace:{WORKSPACE_SLUG}")
STRATEGY_VERSION = "0.1.0"
STRATEGY_ID = uuid5(ACCOUNT_NAMESPACE, f"m2c-strategy:{WORKSPACE_ID}:{STRATEGY_VERSION}")
PROFILE_FACT_KEY = "account_profile.offers_sales_enablement_software"
LEADER_FACT_KEY = "commercial_event.new_revenue_leader"
TEST_ACCOUNTS = (
    ("m2c-customer.example.com", "M2C Customer Test"),
    ("m2c-lead.example.com", "M2C Lead Test"),
)


def account_id(domain: str) -> UUID:
    return uuid5(ACCOUNT_NAMESPACE, f"{WORKSPACE_ID}:{domain}")


def _ensure(session: Session, value: object, identity: UUID, fields: tuple[str, ...]) -> None:
    existing = session.get(type(value), identity)
    if existing is None:
        session.add(value)
        session.flush()
    elif any(getattr(existing, field) != getattr(value, field) for field in fields):
        raise ValueError(f"M2C synthetic fixture drift in {type(value).__name__}")


def setup(session: Session, *, fixture_as_of: datetime) -> dict[str, str]:
    """Seed no provider data; fixture facts support an observable policy comparison."""

    require_local_ingestion()
    if fixture_as_of.tzinfo is None:
        raise ValueError("fixture_as_of must be explicit and timezone-aware")
    fixture_as_of = fixture_as_of.astimezone(UTC)
    now = datetime.now(UTC)
    with session.begin():
        _ensure(
            session,
            Workspace(
                workspace_id=WORKSPACE_ID,
                slug=WORKSPACE_SLUG,
                name="CRM TEST WORKSPACE - SYNTHETIC / DEVELOPER TEST DATA",
                demo_mode=False,
                demo_as_of=None,
                created_at=now,
            ),
            WORKSPACE_ID,
            ("slug", "name", "demo_mode", "demo_as_of"),
        )
        _ensure(
            session,
            StrategyVersion(
                id=STRATEGY_ID,
                workspace_id=WORKSPACE_ID,
                semantic_version=STRATEGY_VERSION,
                status=StrategyStatus.ACTIVE,
                name="Synthetic CRM relationship test strategy",
                summary=(
                    "HYPOTHESIS: one narrow offering Fit and one dated leader Signal "
                    "make Relationship governance observable; no commercial validation."
                ),
                synthetic_disclaimer=(
                    "CRM TEST WORKSPACE. SYNTHETIC / DEVELOPER TEST DATA. "
                    "CRM-reported Customer is not an active-contract or revenue claim. "
                    "No external Action was executed."
                ),
                created_at=now,
                activated_at=now,
            ),
            STRATEGY_ID,
            (
                "workspace_id",
                "semantic_version",
                "status",
                "name",
                "summary",
                "synthetic_disclaimer",
            ),
        )
        hypothesis = (
            "Synthetic sales enablement offering is a test Fit criterion only; "
            "it does not validate ICP quality or purchase likelihood."
        )
        hypothesis_id = uuid5(ACCOUNT_NAMESPACE, f"m2c-strategy-icp:{STRATEGY_ID}")
        strategy_evidence = EvidenceValidationInput(
            strategy_version_id=STRATEGY_ID,
            strategy_topic=StrategyTopic.ICP,
            classification=EvidenceClassification.HYPOTHESIS,
            source_provider="m2c_synthetic_fixture",
            source_reference="m2c-synthetic-strategy:1.0.0",
            source_uri=None,
            observed_at=fixture_as_of,
            ingested_at=now,
            normalized_fact=hypothesis,
            raw_payload_hash=canonical_hash({"claim": hypothesis}),
            freshness=EvidenceFreshness.UNKNOWN,
            confidence=None,
        )
        _ensure(
            session,
            Evidence(id=hypothesis_id, **strategy_evidence.model_dump()),
            hypothesis_id,
            (
                "strategy_version_id",
                "strategy_topic",
                "classification",
                "source_reference",
                "observed_at",
                "normalized_fact",
                "raw_payload_hash",
            ),
        )
        criterion_id = uuid5(ACCOUNT_NAMESPACE, f"m2c-fit:{STRATEGY_ID}")
        _ensure(
            session,
            StrategyFitCriterion(
                fit_criterion_id=criterion_id,
                workspace_id=WORKSPACE_ID,
                strategy_version_id=STRATEGY_ID,
                stable_key="synthetic_sales_enablement_offering",
                display_name="Synthetic test offering",
                description="Narrow fixture criterion, never validated ICP fit.",
                input_fact_key=PROFILE_FACT_KEY,
                expected_assertion=EvidenceAssertion.PRESENT,
                source_strategy_evidence_id=hypothesis_id,
                created_at=now,
            ),
            criterion_id,
            (
                "workspace_id",
                "strategy_version_id",
                "input_fact_key",
                "expected_assertion",
                "source_strategy_evidence_id",
            ),
        )
        signal_id = uuid5(ACCOUNT_NAMESPACE, f"m2c-leader-signal:{STRATEGY_ID}")
        _ensure(
            session,
            SignalDefinition(
                signal_definition_id=signal_id,
                workspace_id=WORKSPACE_ID,
                strategy_version_id=STRATEGY_ID,
                stable_key="new_revenue_leader",
                display_name="New revenue leader - synthetic fixture",
                description="Existing 90-day Signal, with synthetic dated Evidence.",
                category=SignalCategory.LEADERSHIP,
                input_fact_key=LEADER_FACT_KEY,
                evaluator_key="latest_assertion_with_freshness",
                freshness_window_days=90,
                rule_version="1.0.0",
                status=SignalDefinitionStatus.ENABLED,
                created_at=now,
            ),
            signal_id,
            (
                "workspace_id",
                "strategy_version_id",
                "input_fact_key",
                "evaluator_key",
                "freshness_window_days",
                "rule_version",
                "status",
            ),
        )
        decision_id = uuid5(ACCOUNT_NAMESPACE, f"m2c-decision:{STRATEGY_ID}")
        _ensure(
            session,
            DecisionDefinition(
                decision_definition_id=decision_id,
                workspace_id=WORKSPACE_ID,
                strategy_version_id=STRATEGY_ID,
                stable_key="m2c_account_response",
                definition_version="1.0.0",
                display_name="Synthetic account response posture",
                description="Existing deterministic Decision evaluator.",
                evaluator_key="fit_timing_response_matrix",
                evaluator_version="1.0.0",
                status=EvaluationDefinitionStatus.ENABLED,
                created_at=now,
            ),
            decision_id,
            ("workspace_id", "strategy_version_id", "evaluator_key", "evaluator_version", "status"),
        )
        policy_id = uuid5(ACCOUNT_NAMESPACE, f"m2c-policy:{STRATEGY_ID}")
        _ensure(
            session,
            PolicyDefinition(
                policy_definition_id=policy_id,
                workspace_id=WORKSPACE_ID,
                strategy_version_id=STRATEGY_ID,
                stable_key="m2c_prospecting_guardrails",
                definition_version="1.0.0",
                display_name="Existing prospecting guardrails",
                description="No external execution authority.",
                target=PolicyTarget.PROSPECTING_ACTIVATION,
                evaluator_key="state_and_relationship_gate",
                evaluator_version="1.0.0",
                status=EvaluationDefinitionStatus.ENABLED,
                created_at=now,
            ),
            policy_id,
            (
                "workspace_id",
                "strategy_version_id",
                "target",
                "evaluator_key",
                "evaluator_version",
                "status",
            ),
        )
        for domain, name in TEST_ACCOUNTS:
            aid = account_id(domain)
            _ensure(
                session,
                Account(
                    id=aid,
                    workspace_id=WORKSPACE_ID,
                    slug=f"account-{str(aid)[:12]}",
                    canonical_name=name,
                    domain=domain,
                    segment="SYNTHETIC CRM TEST",
                    is_synthetic=True,
                    created_at=now,
                    updated_at=now,
                ),
                aid,
                ("workspace_id", "canonical_name", "domain", "is_synthetic"),
            )
            for fact_key, observed_at, fact in (
                (
                    PROFILE_FACT_KEY,
                    fixture_as_of,
                    "Synthetic test company offers sales enablement software.",
                ),
                (
                    LEADER_FACT_KEY,
                    fixture_as_of - timedelta(days=1),
                    "Synthetic test company appointed a revenue leader.",
                ),
            ):
                evidence_id = uuid5(ACCOUNT_NAMESPACE, f"m2c-fixture:{aid}:{fact_key}")
                value = EvidenceValidationInput(
                    account_id=aid,
                    classification=EvidenceClassification.FACT,
                    source_provider="m2c_synthetic_fixture",
                    source_reference="m2c-synthetic-account:1.0.0",
                    source_uri=None,
                    observed_at=observed_at,
                    ingested_at=now,
                    normalized_fact=fact,
                    raw_payload_hash=canonical_hash(
                        {
                            "account_id": str(aid),
                            "fact_key": fact_key,
                            "observed_at": observed_at.isoformat(),
                        }
                    ),
                    freshness=EvidenceFreshness.UNKNOWN,
                    confidence=None,
                    fact_key=fact_key,
                    fact_assertion=EvidenceAssertion.PRESENT,
                )
                _ensure(
                    session,
                    Evidence(id=evidence_id, **value.model_dump()),
                    evidence_id,
                    (
                        "account_id",
                        "classification",
                        "source_reference",
                        "observed_at",
                        "fact_key",
                        "fact_assertion",
                        "raw_payload_hash",
                    ),
                )
        active = session.scalars(
            select(StrategyVersion.id).where(
                StrategyVersion.workspace_id == WORKSPACE_ID,
                StrategyVersion.status == StrategyStatus.ACTIVE,
            )
        ).all()
        if active != [STRATEGY_ID]:
            raise ValueError("M2C workspace has an unexpected active strategy")
    return {
        "workspace_id": str(WORKSPACE_ID),
        "strategy_version_id": str(STRATEGY_ID),
        "strategy_version": STRATEGY_VERSION,
        "fixture_as_of": fixture_as_of.isoformat(),
        "accounts": ",".join(domain for domain, _ in TEST_ACCOUNTS),
    }
