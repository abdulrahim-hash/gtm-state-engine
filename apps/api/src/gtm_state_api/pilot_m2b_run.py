"""Local M2B gated stages, semantic trace, and reproducibility fingerprint."""

from __future__ import annotations

from collections import Counter
from datetime import datetime
from enum import Enum
from hashlib import sha256
from json import dumps, loads
from pathlib import Path
from typing import Any, cast
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from gtm_state_api.action_engine import materialize_policy_action
from gtm_state_api.current_evidence import current_evidence_condition
from gtm_state_api.decision_engine import (
    materialize_decision_evaluation,
    materialize_policy_evaluation,
)
from gtm_state_api.ingestion_service import batch_counts, import_local_csv, require_local_ingestion
from gtm_state_api.local_csv import parse_local_csv
from gtm_state_api.models import (
    Account,
    AccountStateSnapshot,
    Action,
    DecisionDefinition,
    DecisionEvaluation,
    EvaluationEvidence,
    Evidence,
    IngestionBatch,
    IngestionBatchRow,
    NormalizationResult,
    PolicyDefinition,
    PolicyEvaluation,
    SignalDefinition,
    SignalEvaluation,
    SourceObservation,
    StateSnapshotEvidence,
    StateSnapshotSignalEvaluation,
    StrategyFitCriterion,
    StrategyVersion,
    Workspace,
)
from gtm_state_api.pilot_m2b import (
    STRATEGY_ID,
    WORKSPACE_ID,
    canonical_hash,
)
from gtm_state_api.signal_engine import recompute_workspace_signals
from gtm_state_api.state_engine import (
    PILOT_STATE_ENGINE_VERSION,
    recompute_workspace_account_states,
)
from gtm_state_api.types import EvidenceClassification, IngestionRowOutcome

FINGERPRINT_SCHEMA = "m2b_semantic_fingerprint/1.1.0"
ACCEPTANCE_SCHEMA = "m2b_local_acceptance/1.0.0"
DATASETS = (
    ("profiles.v1.csv", "company_public_profiles", "public_sales_enablement_profile"),
    ("leaders.v1.csv", "company_public_events", "public_company_leader_event"),
)
OPERATIONAL_COLUMNS = {
    "created_at",
    "updated_at",
    "ingested_at",
    "processed_at",
    "evaluated_at",
    "computed_at",
    "proposed_at",
    "activated_at",
    "correlation_id",
}


def as_of(manifest: dict[str, Any]) -> datetime:
    return datetime.fromisoformat(manifest["state_as_of"].replace("Z", "+00:00"))


def expected_domains(manifest: dict[str, Any], ledger: dict[str, Any]) -> list[str]:
    base = manifest["base_candidates"]
    coverage = [entry["domain"] for entry in ledger["trace_coverage"]]
    if len(base) != 18 or len(coverage) != 2 or len(set(base + coverage)) != 20:
        raise ValueError("pilot cohort shape differs from frozen selection")
    if any(domain not in manifest["trace_coverage_screening_queue"] for domain in coverage):
        raise ValueError("coverage account outside frozen queue")
    return cast(list[str], base + coverage)


def validate_dataset(
    root: Path, manifest: dict[str, Any], ledger: dict[str, Any]
) -> dict[str, Any]:
    require_local_ingestion()
    domains = expected_domains(manifest, ledger)
    sources = loads((root / "source_verification.v1.json").read_text(encoding="utf-8"))
    if sources["schema"] != "m2b_manual_source_verification/1.0.0":
        raise ValueError("unsupported source verification contract")
    if len(sources["records"]) != 22:
        raise ValueError("expected 20 profiles and 2 dated leadership assertions")
    result: dict[str, Any] = {
        "semantic_as_of": manifest["state_as_of"],
        "cohorts": {
            "BASE_SAMPLE": len(manifest["base_candidates"]),
            "TRACE_COVERAGE": 2,
        },
    }
    for filename, dataset, _mapper in DATASETS:
        file_hash, rows = parse_local_csv(root / filename, dataset_key=dataset)
        if len(rows) != (20 if dataset == "company_public_profiles" else 2):
            raise ValueError("unexpected CSV row count")
        if any(item.observation is None for item in rows):
            raise ValueError("pilot CSV has invalid rows")
        actual = [item.observation.original_fields for item in rows if item.observation]
        if (
            dataset == "company_public_profiles"
            and [r["company_domain"] for r in actual] != domains
        ):
            raise ValueError("CSV accounts differ from the selection ledger")
        for row in actual:
            if row["assertion"] == "ABSENT":
                raise ValueError("silence-derived ABSENT is prohibited")
            observed_at = datetime.fromisoformat(row["source_observed_at"].replace("Z", "+00:00"))
            if observed_at > as_of(manifest):
                raise ValueError("source was observed after frozen snapshot")
            if row["event_at"] and datetime.fromisoformat(
                row["event_at"].replace("Z", "+00:00")
            ) > as_of(manifest):
                raise ValueError("event date is after frozen snapshot")
            matching = [
                s
                for s in sources["records"]
                if s["domain"] == row["company_domain"] and s["fact_code"] == row["fact_code"]
            ]
            if len(matching) != 1 or matching[0]["source_url"] != row["source_url"]:
                raise ValueError("CSV source does not match manual verification ledger")
            expected_cohort = (
                "BASE_SAMPLE"
                if row["company_domain"] in manifest["base_candidates"]
                else "TRACE_COVERAGE"
            )
            if (
                matching[0]["company_name"] != row["company_name"]
                or matching[0]["cohort"] != expected_cohort
                or matching[0]["source_observed_at"] != row["source_observed_at"]
                or matching[0].get("event_at", "") != row["event_at"]
                or matching[0]["assertion"] != row["assertion"]
                or matching[0]["bounded_paraphrase"] != row["source_excerpt"]
            ):
                raise ValueError("CSV claim does not match manual verification ledger")
        result[dataset] = {"file_sha256": file_hash, "rows": len(rows)}
    return result


def import_datasets(session: Session, root: Path) -> dict[str, str]:
    require_local_ingestion()
    output = {}
    for filename, dataset, mapper in DATASETS:
        output[dataset] = str(
            import_local_csv(
                session,
                root / filename,
                workspace_id=WORKSPACE_ID,
                dataset_key=dataset,
                mapper_key=mapper,
            )
        )
        session.rollback()  # Close M2A batch-count read transaction.
    return output


def inspect_batches(session: Session, root: Path) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for filename, dataset, mapper in DATASETS:
        file_hash, _ = parse_local_csv(root / filename, dataset_key=dataset)
        batch = session.scalar(
            select(IngestionBatch).where(
                IngestionBatch.workspace_id == WORKSPACE_ID,
                IngestionBatch.dataset_key == dataset,
                IngestionBatch.file_sha256 == file_hash,
            )
        )
        if (
            batch is None
            or batch.mapper_key != mapper
            or batch.mapper_version != "1.0.0"
            or batch.identity_rule_version != "1.0.0"
        ):
            raise ValueError("expected versioned ingestion batch is missing")
        details = []
        for row in session.scalars(
            select(IngestionBatchRow)
            .where(IngestionBatchRow.batch_id == batch.id)
            .order_by(IngestionBatchRow.ordinal)
        ):
            obs = (
                session.get(SourceObservation, row.source_observation_id)
                if row.source_observation_id
                else None
            )
            norm = (
                session.get(NormalizationResult, row.normalization_result_id)
                if row.normalization_result_id
                else None
            )
            details.append(
                {
                    "ordinal": row.ordinal,
                    "outcome": row.outcome.value,
                    "reason": row.reason_code.value if row.reason_code else None,
                    "company_domain": obs.original_fields["company_domain"] if obs else None,
                    "source_observation_id": str(obs.id) if obs else None,
                    "normalization_result_id": str(norm.id) if norm else None,
                    "account_id": str(norm.account_id) if norm and norm.account_id else None,
                }
            )
        result[dataset] = {
            "batch_id": str(batch.id),
            "file_sha256": file_hash,
            "mapper_key": mapper,
            "mapper_version": batch.mapper_version,
            "identity_rule_version": batch.identity_rule_version,
            "counts": batch_counts(session, batch.id),
            "rows": details,
        }
    return result


def acceptance_payload(
    session: Session,
    root: Path,
    manifest: dict[str, Any],
    manifest_hash: str,
    ledger: dict[str, Any],
) -> dict[str, Any]:
    validation = validate_dataset(root, manifest, ledger)
    if ledger["manifest_sha256"] != manifest_hash:
        raise ValueError("selection ledger manifest hash mismatch")
    batches = inspect_batches(session, root)
    for dataset, item in batches.items():
        if item["counts"]["accepted"] != validation[dataset]["rows"] or any(
            item["counts"][key] for key in ("rejected", "unresolved", "duplicate")
        ):
            raise ValueError("batch has non-accepted rows requiring manual resolution")
        if any(
            row["outcome"] != IngestionRowOutcome.ACCEPTED.value or row["account_id"] is None
            for row in item["rows"]
        ):
            raise ValueError("not every row resolved to an Account")
    accounts = session.scalars(select(Account).where(Account.workspace_id == WORKSPACE_ID)).all()
    if sorted(account.domain for account in accounts) != sorted(expected_domains(manifest, ledger)):
        raise ValueError("imported Account set differs from frozen selection")
    hypotheses = session.scalars(
        select(Evidence).where(
            Evidence.strategy_version_id == STRATEGY_ID,
            Evidence.classification == EvidenceClassification.HYPOTHESIS,
        )
    ).all()
    expected_reference = f"pilot-manifest:{manifest_hash}"
    if len(hypotheses) != 5 or any(
        item.strategy_topic is None
        or item.source_reference != expected_reference
        or item.raw_payload_hash
        != canonical_hash(
            {
                "topic": item.strategy_topic.value,
                "claim": item.normalized_fact,
                "source": expected_reference,
            }
        )
        for item in hypotheses
    ):
        raise ValueError("pilot Strategy Evidence does not attest to canonical manifest bytes")
    return {
        "schema": ACCEPTANCE_SCHEMA,
        "manifest_version": manifest["manifest_version"],
        "manifest_sha256": manifest_hash,
        "roster_sha256": manifest["roster_sha256"],
        "workspace_id": str(WORKSPACE_ID),
        "strategy_version_id": str(STRATEGY_ID),
        "strategy_version": "0.1.0",
        "semantic_as_of": manifest["state_as_of"],
        "identity_rule_version": "1.0.0",
        "batches": {
            dataset: {
                key: value
                for key, value in info.items()
                if key
                in {
                    "batch_id",
                    "file_sha256",
                    "mapper_key",
                    "mapper_version",
                    "identity_rule_version",
                    "counts",
                }
            }
            for dataset, info in batches.items()
        },
        "account_count": 20,
        "manual_source_verification_sha256": sha256(
            (root / "source_verification.v1.json").read_bytes()
        ).hexdigest(),
    }


def verify_acceptance(
    session: Session,
    root: Path,
    manifest: dict[str, Any],
    manifest_hash: str,
    ledger: dict[str, Any],
) -> dict[str, Any]:
    require_local_ingestion()
    path = root / "acceptance.v1.json"
    if not path.is_file():
        raise ValueError("manual pilot acceptance record is required before materialization")
    actual = loads(path.read_text(encoding="utf-8"))
    expected = acceptance_payload(session, root, manifest, manifest_hash, ledger)
    if actual != expected:
        raise ValueError("pilot acceptance record does not match manifest, CSV, or database")
    return cast(dict[str, Any], actual)


def stage_rows(
    session: Session, model: Any, timestamp_field: str, semantic_time: datetime
) -> list[Any]:
    return list(
        session.scalars(
            select(model).where(
                model.workspace_id == WORKSPACE_ID,
                getattr(model, timestamp_field) == semantic_time,
            )
        ).all()
    )


def materialize(session: Session, stage: str, semantic_time: datetime) -> dict[str, Any]:
    require_local_ingestion()
    with session.begin():
        accounts = session.scalars(
            select(Account).where(Account.workspace_id == WORKSPACE_ID)
        ).all()
        if len(accounts) != 20:
            raise ValueError("expected exactly 20 pilot Accounts")
        items: list[Any] = []
        input_ids: list[str] = []
        before: set[str] = set()
        signal_before: dict[str, tuple[str, str, str]] = {}
        if stage == "signals":
            before = {
                str(x.evaluation_id)
                for x in stage_rows(session, SignalEvaluation, "evaluation_as_of", semantic_time)
            }
            signal_results = recompute_workspace_signals(
                session, WORKSPACE_ID, evaluation_as_of=semantic_time
            )
            items = signal_results
            output_ids = [str(x.evaluation_id) for x in items]
        elif stage == "state":
            previous = stage_rows(session, SignalEvaluation, "evaluation_as_of", semantic_time)
            if len(previous) != 20:
                raise ValueError("inspect 20 explicit Signal evaluations before State")
            signal_before = {
                str(x.account_id): (str(x.evaluation_id), x.input_hash, x.result.value)
                for x in previous
            }
            before = {
                str(x.state_snapshot_id)
                for x in stage_rows(session, AccountStateSnapshot, "state_as_of", semantic_time)
            }
            snapshots = recompute_workspace_account_states(
                session,
                WORKSPACE_ID,
                state_as_of=semantic_time,
                state_engine_version=PILOT_STATE_ENGINE_VERSION,
            )
            after = stage_rows(session, SignalEvaluation, "evaluation_as_of", semantic_time)
            signal_after = {
                str(x.account_id): (str(x.evaluation_id), x.input_hash, x.result.value)
                for x in after
            }
            if signal_after != signal_before or len(after) != 20:
                raise ValueError("State internal Signal recomputation diverged")
            for snapshot in snapshots:
                links = session.scalars(
                    select(StateSnapshotSignalEvaluation).where(
                        StateSnapshotSignalEvaluation.state_snapshot_id
                        == snapshot.state_snapshot_id
                    )
                ).all()
                if (
                    len(links) != 1
                    or str(links[0].evaluation_id) != signal_before[str(snapshot.account_id)][0]
                ):
                    raise ValueError("State linked a different Signal evaluation")
            items = snapshots
            input_ids = [x[0] for x in signal_before.values()]
            output_ids = [str(x.state_snapshot_id) for x in items]
        elif stage == "decisions":
            snapshots = stage_rows(session, AccountStateSnapshot, "state_as_of", semantic_time)
            if len(snapshots) != 20:
                raise ValueError("inspect 20 State snapshots before Decisions")
            before = {
                str(x.decision_evaluation_id)
                for x in session.scalars(
                    select(DecisionEvaluation).where(
                        DecisionEvaluation.workspace_id == WORKSPACE_ID
                    )
                )
            }
            items = [
                materialize_decision_evaluation(session, x.state_snapshot_id) for x in snapshots
            ]
            input_ids = [str(x.state_snapshot_id) for x in snapshots]
            output_ids = [str(x.decision_evaluation_id) for x in items]
        elif stage == "policies":
            decisions = list(
                session.scalars(
                    select(DecisionEvaluation).where(
                        DecisionEvaluation.workspace_id == WORKSPACE_ID
                    )
                ).all()
            )
            if len(decisions) != 20:
                raise ValueError("inspect 20 Decisions before Policies")
            before = {
                str(x.policy_evaluation_id)
                for x in session.scalars(
                    select(PolicyEvaluation).where(PolicyEvaluation.workspace_id == WORKSPACE_ID)
                )
            }
            items = [
                materialize_policy_evaluation(session, x.decision_evaluation_id) for x in decisions
            ]
            input_ids = [str(x.decision_evaluation_id) for x in decisions]
            output_ids = [str(x.policy_evaluation_id) for x in items]
        elif stage == "actions":
            policies = list(
                session.scalars(
                    select(PolicyEvaluation).where(PolicyEvaluation.workspace_id == WORKSPACE_ID)
                ).all()
            )
            if len(policies) != 20:
                raise ValueError("inspect 20 Policies before Actions")
            before = {
                str(x.action_id)
                for x in session.scalars(select(Action).where(Action.workspace_id == WORKSPACE_ID))
            }
            projections = [
                materialize_policy_action(session, x.policy_evaluation_id) for x in policies
            ]
            items = [action for _, action in projections if action is not None]
            input_ids = [str(x.policy_evaluation_id) for x in policies]
            output_ids = [str(x.action_id) for x in items]
        else:
            raise ValueError("unsupported pilot stage")
        if stage == "signals":
            input_ids = [str(x.id) for x in accounts]
        results: Counter[str] = Counter(x.result.value for x in items if hasattr(x, "result"))
        if stage == "state":
            results = Counter(
                f"{x.fit_context.value}/{x.timing_state.value}/{x.relationship_state.value}"
                for x in items
                if isinstance(x, AccountStateSnapshot)
            )
        if stage == "actions":
            results = Counter(x.action_type.value for x in items if isinstance(x, Action))
        output = {
            "stage": stage,
            "semantic_as_of": semantic_time.isoformat(),
            "workspace_id": str(WORKSPACE_ID),
            "strategy_version_id": str(STRATEGY_ID),
            "state_engine_version": PILOT_STATE_ENGINE_VERSION,
            "input_ids": sorted(input_ids),
            "output_ids": sorted(output_ids),
            "count": len(items),
            "created": len(set(output_ids) - before),
            "reused": len(set(output_ids) & before),
            "results": dict(sorted(results.items())),
            "failures": 0,
        }
        if stage == "state":
            output["signal_recomputation_identical"] = True
    return output


def inspect_stage(session: Session, stage: str, semantic_time: datetime) -> dict[str, Any]:
    """Read every account conclusion at a named boundary without materializing anything."""

    require_local_ingestion()
    accounts = session.scalars(select(Account).where(Account.workspace_id == WORKSPACE_ID)).all()
    rows: list[dict[str, Any]] = []
    for account in sorted(accounts, key=lambda item: item.domain):
        if stage == "signals":
            signal_item = session.scalar(
                select(SignalEvaluation).where(
                    SignalEvaluation.account_id == account.id,
                    SignalEvaluation.workspace_id == WORKSPACE_ID,
                    SignalEvaluation.evaluation_as_of == semantic_time,
                )
            )
            details = (
                {
                    "id": str(signal_item.evaluation_id),
                    "result": signal_item.result.value,
                    "reason": signal_item.reason_code.value,
                    "input_hash": signal_item.input_hash,
                }
                if signal_item
                else None
            )
        elif stage == "state":
            state_item = session.scalar(
                select(AccountStateSnapshot).where(
                    AccountStateSnapshot.account_id == account.id,
                    AccountStateSnapshot.workspace_id == WORKSPACE_ID,
                    AccountStateSnapshot.state_as_of == semantic_time,
                    AccountStateSnapshot.state_engine_version == PILOT_STATE_ENGINE_VERSION,
                )
            )
            details = (
                {
                    "id": str(state_item.state_snapshot_id),
                    "fit": state_item.fit_context.value,
                    "timing": state_item.timing_state.value,
                    "relationship": state_item.relationship_state.value,
                    "sufficiency": state_item.evidence_sufficiency.value,
                    "input_hash": state_item.input_hash,
                }
                if state_item
                else None
            )
        else:
            raise ValueError("unsupported inspection stage")
        rows.append({"domain": account.domain, "result": details})
    if len(rows) != 20 or any(row["result"] is None for row in rows):
        raise ValueError(f"{stage} is not complete for all 20 pilot Accounts")
    return {
        "stage": f"inspect-{stage}",
        "semantic_as_of": semantic_time.isoformat(),
        "count": len(rows),
        "rows": rows,
        "database_writes": 0,
    }


def scalar(value: Any) -> Any:
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {str(key): scalar(item) for key, item in sorted(value.items())}
    if isinstance(value, (tuple, list)):
        return [scalar(item) for item in value]
    return value


def semantic_record(instance: Any) -> dict[str, Any]:
    return {
        column.name: scalar(getattr(instance, column.name))
        for column in instance.__table__.columns
        if column.name not in OPERATIONAL_COLUMNS
    }


def semantic_fingerprint_record(instance: Any) -> dict[str, Any]:
    record = semantic_record(instance)
    if (
        isinstance(instance, Evidence)
        and instance.strategy_version_id is not None
        and instance.classification is EvidenceClassification.HYPOTHESIS
        and instance.source_reference.startswith("pilot-manifest:")
    ):
        # Exact manifest bytes are attested by acceptance, not by this semantic digest.
        record.pop("source_reference")
        record.pop("raw_payload_hash")
    return record


def fingerprint(session: Session, semantic_time: datetime) -> dict[str, Any]:
    require_local_ingestion()
    buckets: dict[str, list[dict[str, Any]]] = {}
    models: tuple[Any, ...] = (
        Workspace,
        StrategyVersion,
        StrategyFitCriterion,
        SignalDefinition,
        DecisionDefinition,
        PolicyDefinition,
        Account,
        SourceObservation,
        NormalizationResult,
        Evidence,
        SignalEvaluation,
        AccountStateSnapshot,
        DecisionEvaluation,
        PolicyEvaluation,
        Action,
    )
    for model in models:
        rows: list[Any]
        if model is Workspace:
            rows = [session.get(Workspace, WORKSPACE_ID)]
        elif model is StrategyVersion:
            rows = [session.get(StrategyVersion, STRATEGY_ID)]
        elif model is Evidence:
            rows = list(
                session.scalars(
                    select(Evidence).where(
                        (
                            (
                                Evidence.account_id.in_(
                                    select(Account.id).where(Account.workspace_id == WORKSPACE_ID)
                                )
                            )
                            | (Evidence.strategy_version_id == STRATEGY_ID)
                        ),
                        current_evidence_condition(),
                    )
                ).all()
            )
        else:
            rows = list(
                session.scalars(select(model).where(model.workspace_id == WORKSPACE_ID)).all()
            )
        if any(row is None for row in rows):
            raise ValueError("pilot fingerprint is missing workspace or strategy")
        selected = []
        for row in rows:
            if model is SignalEvaluation and row.evaluation_as_of != semantic_time:
                continue
            if model is AccountStateSnapshot and row.state_as_of != semantic_time:
                continue
            selected.append(semantic_fingerprint_record(row))
        buckets[model.__tablename__] = sorted(
            selected, key=lambda item: dumps(item, sort_keys=True)
        )
    if any(
        len(buckets[name]) != 20
        for name in (
            "accounts",
            "signal_evaluations",
            "account_state_snapshots",
            "decision_evaluations",
            "policy_evaluations",
        )
    ):
        raise ValueError("incomplete pilot cannot establish fingerprint")
    payload = {
        "schema": FINGERPRINT_SCHEMA,
        "semantic_as_of": semantic_time.isoformat(),
        "objects": buckets,
    }
    return {
        "schema": FINGERPRINT_SCHEMA,
        "sha256": canonical_hash(payload),
        "object_counts": {name: len(rows) for name, rows in buckets.items()},
        "semantic_as_of": semantic_time.isoformat(),
    }


def account_trace(session: Session, domain: str, semantic_time: datetime) -> dict[str, Any]:
    account = session.scalar(
        select(Account).where(Account.workspace_id == WORKSPACE_ID, Account.domain == domain)
    )
    if account is None:
        raise ValueError("pilot Account missing")
    evidence = session.scalars(
        select(Evidence).where(Evidence.account_id == account.id, current_evidence_condition())
    ).all()
    facts = []
    for item in evidence:
        norm = session.get(NormalizationResult, item.normalization_result_id)
        obs = session.get(SourceObservation, norm.source_observation_id) if norm else None
        if norm is None or obs is None:
            raise ValueError("imported Evidence lacks source observation")
        facts.append(
            {
                "evidence_id": str(item.id),
                "fact_key": item.fact_key,
                "assertion": item.fact_assertion.value if item.fact_assertion else None,
                "observed_at": item.observed_at.isoformat(),
                "source_observation_id": str(obs.id),
                "normalization_result_id": str(norm.id),
                "source_observed_at": obs.source_observed_at.isoformat(),
                "source_url": item.source_uri,
                "paraphrase": obs.original_fields["source_excerpt"],
            }
        )
    signal = session.scalar(
        select(SignalEvaluation).where(
            SignalEvaluation.account_id == account.id,
            SignalEvaluation.workspace_id == WORKSPACE_ID,
            SignalEvaluation.evaluation_as_of == semantic_time,
        )
    )
    state = session.scalar(
        select(AccountStateSnapshot).where(
            AccountStateSnapshot.account_id == account.id,
            AccountStateSnapshot.workspace_id == WORKSPACE_ID,
            AccountStateSnapshot.state_as_of == semantic_time,
        )
    )
    decision = (
        session.scalar(
            select(DecisionEvaluation).where(
                DecisionEvaluation.state_snapshot_id == state.state_snapshot_id
            )
        )
        if state
        else None
    )
    policy = (
        session.scalar(
            select(PolicyEvaluation).where(
                PolicyEvaluation.decision_evaluation_id == decision.decision_evaluation_id
            )
        )
        if decision
        else None
    )
    action = (
        session.scalar(
            select(Action).where(Action.policy_evaluation_id == policy.policy_evaluation_id)
        )
        if policy
        else None
    )
    signal_evidence_ids = (
        sorted(
            str(x.evidence_id)
            for x in session.scalars(
                select(EvaluationEvidence).where(
                    EvaluationEvidence.evaluation_id == signal.evaluation_id
                )
            )
        )
        if signal
        else []
    )
    state_signal_ids = (
        sorted(
            str(x.evaluation_id)
            for x in session.scalars(
                select(StateSnapshotSignalEvaluation).where(
                    StateSnapshotSignalEvaluation.state_snapshot_id == state.state_snapshot_id
                )
            )
        )
        if state
        else []
    )
    state_evidence_ids = (
        sorted(
            str(x.evidence_id)
            for x in session.scalars(
                select(StateSnapshotEvidence).where(
                    StateSnapshotEvidence.state_snapshot_id == state.state_snapshot_id
                )
            )
        )
        if state
        else []
    )
    if state and signal and state_signal_ids != [str(signal.evaluation_id)]:
        raise ValueError("trace State-to-Signal provenance diverged")
    if decision and state and decision.state_snapshot_id != state.state_snapshot_id:
        raise ValueError("trace Decision-to-State provenance diverged")
    if policy and decision and policy.decision_evaluation_id != decision.decision_evaluation_id:
        raise ValueError("trace Policy-to-Decision provenance diverged")
    if action and policy and action.policy_evaluation_id != policy.policy_evaluation_id:
        raise ValueError("trace Action-to-Policy provenance diverged")
    return {
        "account_id": str(account.id),
        "company_name": account.canonical_name,
        "domain": domain,
        "evidence": sorted(facts, key=lambda x: x["fact_key"] or ""),
        "signal": {
            "id": str(signal.evaluation_id),
            "result": signal.result.value,
            "reason": signal.reason_code.value,
            "input_hash": signal.input_hash,
            "evidence_ids": signal_evidence_ids,
        }
        if signal
        else None,
        "state": {
            "id": str(state.state_snapshot_id),
            "fit": state.fit_context.value,
            "timing": state.timing_state.value,
            "relationship": state.relationship_state.value,
            "sufficiency": state.evidence_sufficiency.value,
            "input_hash": state.input_hash,
            "signal_evaluation_ids": state_signal_ids,
            "evidence_ids": state_evidence_ids,
        }
        if state
        else None,
        "decision": {
            "id": str(decision.decision_evaluation_id),
            "result": decision.result.value,
            "input_hash": decision.input_hash,
            "state_snapshot_id": str(decision.state_snapshot_id),
        }
        if decision
        else None,
        "policy": {
            "id": str(policy.policy_evaluation_id),
            "result": policy.result.value,
            "input_hash": policy.input_hash,
            "decision_evaluation_id": str(policy.decision_evaluation_id),
            "state_snapshot_id": str(policy.state_snapshot_id),
        }
        if policy
        else None,
        "action": {
            "id": str(action.action_id),
            "type": action.action_type.value,
            "input_hash": action.semantic_input_hash,
            "policy_evaluation_id": str(action.policy_evaluation_id),
        }
        if action
        else None,
    }


def export_trace(
    session: Session, manifest: dict[str, Any], ledger: dict[str, Any]
) -> dict[str, Any]:
    semantic_time = as_of(manifest)
    groups: dict[str, list[dict[str, Any]]] = {"BASE_SAMPLE": [], "TRACE_COVERAGE": []}
    for domain in expected_domains(manifest, ledger):
        cohort = "BASE_SAMPLE" if domain in manifest["base_candidates"] else "TRACE_COVERAGE"
        groups[cohort].append(account_trace(session, domain, semantic_time))
    summaries = {}
    for group, accounts in groups.items():
        summaries[group] = {
            "accounts": len(accounts),
            "signal": dict(Counter(a["signal"]["result"] for a in accounts)),
            "fit": dict(Counter(a["state"]["fit"] for a in accounts)),
            "timing": dict(Counter(a["state"]["timing"] for a in accounts)),
            "relationship": dict(Counter(a["state"]["relationship"] for a in accounts)),
            "decision": dict(Counter(a["decision"]["result"] for a in accounts)),
            "policy": dict(Counter(a["policy"]["result"] for a in accounts)),
            "action": dict(
                Counter(a["action"]["type"] if a["action"] else "NONE" for a in accounts)
            ),
        }
    return {
        "schema": "m2b_local_trace/2.0.0",
        "label": "REAL PUBLIC-DATA PILOT",
        "strategy_status": "HYPOTHESIS / COMMERCIALLY UNVALIDATED",
        "semantic_as_of": manifest["state_as_of"],
        "limits": (
            "System outcomes only. No outreach, CRM write, seller task, reply, meeting, "
            "or revenue occurred. Fit MATCH is only the narrow official public page "
            "criterion. STALE means stale based on verified pilot evidence."
        ),
        "coverage_status": ledger["trace_coverage"][0]["coverage_status"],
        "fingerprint": fingerprint(session, semantic_time),
        "summaries": summaries,
        "cohorts": groups,
    }
