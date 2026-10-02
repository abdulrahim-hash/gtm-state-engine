"""Deterministic, idempotent synthetic workspace fixture through M1B.2."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from hashlib import sha256
from json import dumps
from typing import TypedDict
from uuid import UUID

from sqlalchemy.orm import Session

from gtm_state_api.models import (
    Account,
    Evidence,
    SignalDefinition,
    StrategyFitCriterion,
    StrategyVersion,
    Workspace,
)
from gtm_state_api.schemas import EvidenceValidationInput
from gtm_state_api.state_engine import recompute_workspace_account_states
from gtm_state_api.types import (
    EvidenceAssertion,
    EvidenceClassification,
    EvidenceFreshness,
    SignalCategory,
    SignalDefinitionStatus,
    StrategyStatus,
    StrategyTopic,
)

DEMO_WORKSPACE_ID = UUID("1a1206b7-243c-4f22-8d7f-53aa00000001")
DEMO_STRATEGY_ID = UUID("1a1206b7-243c-4f22-8d7f-53aa00000002")
DEMO_AS_OF = datetime(2026, 9, 15, 12, 0, tzinfo=UTC)
DEMO_INGESTED_AT = datetime(2026, 9, 15, 12, 5, tzinfo=UTC)
DEMO_EVALUATED_AT = datetime(2026, 9, 15, 12, 10, tzinfo=UTC)
NEW_REVENUE_LEADER_DEFINITION_ID = UUID("1a1206b7-243c-4f22-8d7f-53aa00000401")
HIRING_EXPANSION_DEFINITION_ID = UUID("1a1206b7-243c-4f22-8d7f-53aa00000402")
TARGET_OPERATING_COMPLEXITY_CRITERION_ID = UUID("1a1206b7-243c-4f22-8d7f-53aa00000411")
SEGMENTATION_EVIDENCE_ID = UUID("1a1206b7-243c-4f22-8d7f-53aa00000102")


class DemoAccount(TypedDict):
    """Stable fields for one canonical synthetic account fixture."""

    id: UUID
    slug: str
    canonical_name: str
    domain: str
    segment: str


DEMO_ACCOUNTS: tuple[DemoAccount, ...] = (
    {
        "id": UUID("1a1206b7-243c-4f22-8d7f-53aa00000011"),
        "slug": "asterwind-instruments",
        "canonical_name": "Asterwind Instruments",
        "domain": "asterwind-instruments.example",
        "segment": "Synthetic growth-stage B2B operations teams",
    },
    {
        "id": UUID("1a1206b7-243c-4f22-8d7f-53aa00000012"),
        "slug": "bramble-logic-systems",
        "canonical_name": "Bramble Logic Systems",
        "domain": "bramble-logic-systems.example",
        "segment": "Synthetic growth-stage B2B operations teams",
    },
    {
        "id": UUID("1a1206b7-243c-4f22-8d7f-53aa00000013"),
        "slug": "cinderlake-revenue-studio",
        "canonical_name": "Cinderlake Revenue Studio",
        "domain": "cinderlake-revenue-studio.example",
        "segment": "Synthetic growth-stage B2B operations teams",
    },
)

STRATEGY_CLAIMS: tuple[tuple[StrategyTopic, str, Decimal | None], ...] = (
    (
        StrategyTopic.MARKET,
        "Synthetic demo hypothesis: focused GTM teams need auditable account context.",
        Decimal("0.60"),
    ),
    (
        StrategyTopic.SEGMENTATION,
        "Synthetic demo hypothesis: segment by operating complexity, not company size alone.",
        Decimal("0.55"),
    ),
    (
        StrategyTopic.ICP,
        "Synthetic demo hypothesis: the ideal profile has a growing revenue-operations mandate.",
        Decimal("0.58"),
    ),
    (
        StrategyTopic.BUYER_HYPOTHESES,
        "Synthetic demo hypothesis: revenue-operations leaders shape evaluation criteria.",
        Decimal("0.50"),
    ),
    (
        StrategyTopic.PROBLEM_HYPOTHESIS,
        "Synthetic demo hypothesis: fragmented signals make account prioritization difficult.",
        Decimal("0.65"),
    ),
    (
        StrategyTopic.VALUE_PROPOSITION_HYPOTHESIS,
        "Synthetic demo hypothesis: traceable state reduces ungrounded GTM action.",
        Decimal("0.62"),
    ),
    (
        StrategyTopic.OFFER_HYPOTHESIS,
        "Synthetic demo hypothesis: an evidence-first account-state foundation "
        "is a useful initial offer.",
        Decimal("0.52"),
    ),
    (
        StrategyTopic.PRICING_HYPOTHESIS,
        "Synthetic demo hypothesis: pricing should follow validated operational value, "
        "not this fixture.",
        Decimal("0.40"),
    ),
    (
        StrategyTopic.MESSAGING_FRAMEWORK,
        "Synthetic demo hypothesis: lead with evidence, governance, and measurable "
        "operating clarity.",
        Decimal("0.58"),
    ),
    (
        StrategyTopic.CHANNELS,
        "Synthetic demo hypothesis: customer learning and targeted operator communities "
        "are candidate channels.",
        Decimal("0.45"),
    ),
    (
        StrategyTopic.GTM_MOTION,
        "Synthetic demo hypothesis: a human-reviewed consultative motion is appropriate "
        "for early learning.",
        Decimal("0.48"),
    ),
    (
        StrategyTopic.EXPERIMENT_ASSUMPTIONS,
        "Synthetic demo hypothesis: test source coverage before testing outreach volume.",
        Decimal("0.66"),
    ),
)


def _hash_payload(payload: dict[str, str]) -> str:
    """Return a stable hash without persisting raw synthetic payloads."""

    encoded = dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return sha256(encoded).hexdigest()


def _merge(
    session: Session,
    instance: (
        Workspace | StrategyVersion | Account | Evidence | SignalDefinition | StrategyFitCriterion
    ),
) -> None:
    """Merge a stable fixture object without creating duplicate rows."""

    session.merge(instance)


def _evidence(
    *,
    evidence_id: UUID,
    normalized_fact: str,
    observed_at: datetime,
    freshness: EvidenceFreshness,
    account_id: UUID | None = None,
    strategy_topic: StrategyTopic | None = None,
    classification: EvidenceClassification = EvidenceClassification.FACT,
    confidence: Decimal | None = None,
    fact_key: str | None = None,
    fact_assertion: EvidenceAssertion | None = None,
    include_fact_shape_in_raw_hash: bool = True,
) -> Evidence:
    """Validate and construct one deterministic evidence record."""

    source_reference = f"synthetic://northstar-revenue-systems-demo/evidence/{evidence_id}"
    hash_payload = {
        "classification": classification.value,
        "normalized_fact": normalized_fact,
        "observed_at": observed_at.isoformat(),
        "source_reference": source_reference,
    }
    if include_fact_shape_in_raw_hash and fact_key is not None and fact_assertion is not None:
        hash_payload["fact_key"] = fact_key
        hash_payload["fact_assertion"] = fact_assertion.value
    input_value = EvidenceValidationInput(
        strategy_version_id=DEMO_STRATEGY_ID if strategy_topic is not None else None,
        account_id=account_id,
        strategy_topic=strategy_topic,
        classification=classification,
        source_provider="synthetic_demo_fixture",
        source_reference=source_reference,
        observed_at=observed_at,
        ingested_at=DEMO_INGESTED_AT,
        normalized_fact=normalized_fact,
        raw_payload_hash=_hash_payload(hash_payload),
        freshness=freshness,
        confidence=confidence,
        fact_key=fact_key,
        fact_assertion=fact_assertion,
    )
    return Evidence(id=evidence_id, **input_value.model_dump())


def seed_demo(session: Session) -> None:
    """Upsert and evaluate the fixed synthetic M1B.2 snapshot atomically."""

    _merge(
        session,
        Workspace(
            workspace_id=DEMO_WORKSPACE_ID,
            slug="northstar-revenue-systems-demo",
            name="Northstar Revenue Systems Demo",
            demo_mode=True,
            demo_as_of=DEMO_AS_OF,
            created_at=DEMO_AS_OF,
        ),
    )
    _merge(
        session,
        StrategyVersion(
            id=DEMO_STRATEGY_ID,
            workspace_id=DEMO_WORKSPACE_ID,
            semantic_version="1.0.0",
            status=StrategyStatus.ACTIVE,
            name="Northstar synthetic GTM strategy",
            summary="A deterministic public fixture for testing evidence-first GTM infrastructure.",
            synthetic_disclaimer=(
                "Synthetic demo only. Every strategy assertion is an unvalidated hypothesis, "
                "not a validated market finding."
            ),
            created_at=DEMO_AS_OF,
            activated_at=DEMO_AS_OF,
        ),
    )
    for account in DEMO_ACCOUNTS:
        _merge(
            session,
            Account(
                **account,
                workspace_id=DEMO_WORKSPACE_ID,
                is_synthetic=True,
                created_at=DEMO_AS_OF,
                updated_at=DEMO_AS_OF,
            ),
        )

    for index, (topic, statement, confidence) in enumerate(STRATEGY_CLAIMS, start=1):
        _merge(
            session,
            _evidence(
                evidence_id=UUID(f"1a1206b7-243c-4f22-8d7f-53aa000001{index:02d}"),
                normalized_fact=statement,
                observed_at=DEMO_AS_OF - timedelta(days=index),
                freshness=EvidenceFreshness.CURRENT,
                strategy_topic=topic,
                classification=EvidenceClassification.HYPOTHESIS,
                confidence=confidence,
            ),
        )

    _merge(
        session,
        StrategyFitCriterion(
            fit_criterion_id=TARGET_OPERATING_COMPLEXITY_CRITERION_ID,
            workspace_id=DEMO_WORKSPACE_ID,
            strategy_version_id=DEMO_STRATEGY_ID,
            stable_key="target_operating_complexity",
            display_name="Target operating-complexity context",
            description=(
                "Synthetic executable criterion: the account shows the operating-complexity "
                "context described by the active, unvalidated segmentation hypothesis."
            ),
            input_fact_key="account_profile.target_operating_complexity",
            expected_assertion=EvidenceAssertion.PRESENT,
            source_strategy_evidence_id=SEGMENTATION_EVIDENCE_ID,
            created_at=DEMO_AS_OF,
        ),
    )

    account_evidence = (
        (
            UUID("1a1206b7-243c-4f22-8d7f-53aa00000201"),
            DEMO_ACCOUNTS[0]["id"],
            "Synthetic demo observation: target operating-complexity cues are present.",
            DEMO_AS_OF - timedelta(days=4),
            EvidenceFreshness.CURRENT,
            "account_profile.target_operating_complexity",
            EvidenceAssertion.PRESENT,
        ),
        (
            UUID("1a1206b7-243c-4f22-8d7f-53aa00000202"),
            DEMO_ACCOUNTS[0]["id"],
            "Synthetic demo observation: a current timing event is recorded for later "
            "signal evaluation.",
            DEMO_AS_OF - timedelta(days=2),
            EvidenceFreshness.CURRENT,
            None,
            None,
        ),
        (
            UUID("1a1206b7-243c-4f22-8d7f-53aa00000203"),
            DEMO_ACCOUNTS[1]["id"],
            "Synthetic demo observation: target operating-complexity cues are present.",
            DEMO_AS_OF - timedelta(days=5),
            EvidenceFreshness.CURRENT,
            "account_profile.target_operating_complexity",
            EvidenceAssertion.PRESENT,
        ),
        (
            UUID("1a1206b7-243c-4f22-8d7f-53aa00000204"),
            DEMO_ACCOUNTS[1]["id"],
            "Synthetic demo observation: the only timing reference is stale and inconclusive.",
            DEMO_AS_OF - timedelta(days=190),
            EvidenceFreshness.STALE,
            None,
            None,
        ),
        (
            UUID("1a1206b7-243c-4f22-8d7f-53aa00000205"),
            DEMO_ACCOUNTS[2]["id"],
            "Synthetic demo observation: target operating-complexity cues are present.",
            DEMO_AS_OF - timedelta(days=3),
            EvidenceFreshness.CURRENT,
            "account_profile.target_operating_complexity",
            EvidenceAssertion.PRESENT,
        ),
        (
            UUID("1a1206b7-243c-4f22-8d7f-53aa00000206"),
            DEMO_ACCOUNTS[2]["id"],
            "Synthetic demo observation: a current timing event is recorded for later "
            "signal evaluation.",
            DEMO_AS_OF - timedelta(days=1),
            EvidenceFreshness.CURRENT,
            None,
            None,
        ),
        (
            UUID("1a1206b7-243c-4f22-8d7f-53aa00000207"),
            DEMO_ACCOUNTS[2]["id"],
            "Synthetic demo observation: an existing relationship condition is recorded "
            "as evidence.",
            DEMO_AS_OF - timedelta(days=1),
            EvidenceFreshness.CURRENT,
            "relationship.existing_relationship",
            EvidenceAssertion.PRESENT,
        ),
    )
    for (
        evidence_id,
        account_id,
        statement,
        observed_at,
        freshness,
        fact_key,
        fact_assertion,
    ) in account_evidence:
        _merge(
            session,
            _evidence(
                evidence_id=evidence_id,
                account_id=account_id,
                normalized_fact=statement,
                observed_at=observed_at,
                freshness=freshness,
                fact_key=fact_key,
                fact_assertion=fact_assertion,
                include_fact_shape_in_raw_hash=False,
            ),
        )

    event_evidence = (
        (
            UUID("1a1206b7-243c-4f22-8d7f-53aa00000301"),
            DEMO_ACCOUNTS[0]["id"],
            "Synthetic demo observation: Asterwind appointed a new revenue leader.",
            DEMO_AS_OF - timedelta(days=2),
            EvidenceFreshness.CURRENT,
            "commercial_event.new_revenue_leader",
            EvidenceAssertion.PRESENT,
        ),
        (
            UUID("1a1206b7-243c-4f22-8d7f-53aa00000302"),
            DEMO_ACCOUNTS[0]["id"],
            "Synthetic demo observation: Asterwind showed no sales-team hiring expansion.",
            DEMO_AS_OF - timedelta(days=3),
            EvidenceFreshness.CURRENT,
            "commercial_event.sales_team_hiring_expansion",
            EvidenceAssertion.ABSENT,
        ),
        (
            UUID("1a1206b7-243c-4f22-8d7f-53aa00000303"),
            DEMO_ACCOUNTS[1]["id"],
            "Synthetic demo observation: Bramble appointed a revenue leader 190 days ago.",
            DEMO_AS_OF - timedelta(days=190),
            EvidenceFreshness.STALE,
            "commercial_event.new_revenue_leader",
            EvidenceAssertion.PRESENT,
        ),
        (
            UUID("1a1206b7-243c-4f22-8d7f-53aa00000304"),
            DEMO_ACCOUNTS[1]["id"],
            "Synthetic demo observation: Bramble hiring evidence is inconclusive.",
            DEMO_AS_OF - timedelta(days=5),
            EvidenceFreshness.CURRENT,
            "commercial_event.sales_team_hiring_expansion",
            EvidenceAssertion.INCONCLUSIVE,
        ),
        (
            UUID("1a1206b7-243c-4f22-8d7f-53aa00000305"),
            DEMO_ACCOUNTS[2]["id"],
            "Synthetic demo observation: Cinderlake appointed a new revenue leader.",
            DEMO_AS_OF - timedelta(days=1),
            EvidenceFreshness.CURRENT,
            "commercial_event.new_revenue_leader",
            EvidenceAssertion.PRESENT,
        ),
    )
    for (
        evidence_id,
        account_id,
        statement,
        observed_at,
        freshness,
        fact_key,
        assertion,
    ) in event_evidence:
        _merge(
            session,
            _evidence(
                evidence_id=evidence_id,
                account_id=account_id,
                normalized_fact=statement,
                observed_at=observed_at,
                freshness=freshness,
                fact_key=fact_key,
                fact_assertion=assertion,
            ),
        )

    definitions = (
        SignalDefinition(
            signal_definition_id=NEW_REVENUE_LEADER_DEFINITION_ID,
            workspace_id=DEMO_WORKSPACE_ID,
            strategy_version_id=DEMO_STRATEGY_ID,
            stable_key="new_revenue_leader",
            display_name="New revenue leader",
            description=(
                "Synthetic commercial event: a newly appointed revenue leader "
                "within the configured freshness window."
            ),
            category=SignalCategory.LEADERSHIP,
            input_fact_key="commercial_event.new_revenue_leader",
            evaluator_key="latest_assertion_with_freshness",
            freshness_window_days=90,
            rule_version="1.0.0",
            status=SignalDefinitionStatus.ENABLED,
            created_at=DEMO_AS_OF,
        ),
        SignalDefinition(
            signal_definition_id=HIRING_EXPANSION_DEFINITION_ID,
            workspace_id=DEMO_WORKSPACE_ID,
            strategy_version_id=DEMO_STRATEGY_ID,
            stable_key="sales_team_hiring_expansion",
            display_name="Sales-team hiring expansion",
            description=(
                "Synthetic commercial event: a sustained expansion in sales-team hiring "
                "within the configured freshness window."
            ),
            category=SignalCategory.HIRING,
            input_fact_key="commercial_event.sales_team_hiring_expansion",
            evaluator_key="latest_assertion_with_freshness",
            freshness_window_days=45,
            rule_version="1.0.0",
            status=SignalDefinitionStatus.ENABLED,
            created_at=DEMO_AS_OF,
        ),
    )
    for definition in definitions:
        _merge(session, definition)

    session.flush()
    recompute_workspace_account_states(
        session,
        DEMO_WORKSPACE_ID,
        computed_at=DEMO_EVALUATED_AT,
    )
    session.commit()
