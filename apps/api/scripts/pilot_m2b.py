"""Explicit local M2B pilot runbook; no stage runs from CSV ingestion."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from sqlalchemy import select

from gtm_state_api.database import get_session_factory
from gtm_state_api.ingestion_service import require_local_ingestion
from gtm_state_api.local_csv import parse_local_csv
from gtm_state_api.models import IngestionBatch, StrategyVersion, Workspace
from gtm_state_api.pilot_m2b import STRATEGY_ID, WORKSPACE_ID, load_manifest, setup
from gtm_state_api.pilot_m2b_run import (
    DATASETS,
    acceptance_payload,
    as_of,
    export_trace,
    import_datasets,
    inspect_batches,
    inspect_stage,
    materialize,
    validate_dataset,
    verify_acceptance,
)

DEFAULT_ROOT = Path("docs/pilot/m2b")


def write_exact(path: Path, value: dict[str, Any]) -> bool:
    encoded = (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode()
    if path.exists():
        if path.read_bytes() != encoded:
            raise ValueError(f"immutable pilot artifact differs: {path}")
        return False
    path.write_bytes(encoded)
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Local gated M2B pilot stages")
    parser.add_argument(
        "stage",
        choices=(
            "setup",
            "validate",
            "import",
            "inspect",
            "inspect-signals",
            "inspect-state",
            "accept",
            "signals",
            "state",
            "decisions",
            "policies",
            "actions",
            "export",
        ),
    )
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--confirm-reviewed", action="store_true")
    args = parser.parse_args()
    require_local_ingestion()
    root: Path = args.root
    manifest, manifest_hash = load_manifest(root / "selection_manifest.v2.json")
    ledger: dict[str, Any] = json.loads((root / "selection_ledger.v1.json").read_text())
    if ledger["manifest_sha256"] != manifest_hash:
        raise ValueError("selection ledger does not match frozen manifest")
    output: dict[str, Any]
    if args.stage == "validate":
        output = validate_dataset(root, manifest, ledger)
    else:
        with get_session_factory()() as session:
            if args.stage == "setup":
                existing = sum(
                    session.get(model, identity) is not None
                    for model, identity in (
                        (Workspace, WORKSPACE_ID),
                        (StrategyVersion, STRATEGY_ID),
                    )
                )
                session.rollback()
                output = dict[str, Any](setup(session, manifest, manifest_hash))
                output.update(
                    created=2 - existing,
                    reused=existing,
                    identity_unit="workspace_or_strategy_version",
                )
            elif args.stage == "import":
                validation = validate_dataset(root, manifest, ledger)
                previous = set()
                for filename, dataset, _ in DATASETS:
                    file_hash, _rows = parse_local_csv(root / filename, dataset_key=dataset)
                    batch_id = session.scalar(
                        select(IngestionBatch.id).where(
                            IngestionBatch.workspace_id == WORKSPACE_ID,
                            IngestionBatch.dataset_key == dataset,
                            IngestionBatch.file_sha256 == file_hash,
                        )
                    )
                    if batch_id:
                        previous.add(str(batch_id))
                session.rollback()
                batches = import_datasets(session, root)
                output = {
                    "batches": batches,
                    "input_ids": [validation[dataset]["file_sha256"] for _, dataset, _ in DATASETS],
                    "result_counts": {"ingestion_batches": len(batches)},
                    "created": len(set(batches.values()) - previous),
                    "reused": len(set(batches.values()) & previous),
                    "identity_unit": "ingestion_batch",
                    "downstream_materialized": False,
                }
            elif args.stage == "inspect":
                output = inspect_batches(session, root)
            elif args.stage == "accept":
                if not args.confirm_reviewed:
                    raise ValueError("inspect every row, then pass --confirm-reviewed")
                payload = acceptance_payload(session, root, manifest, manifest_hash, ledger)
                created = write_exact(root / "acceptance.v1.json", payload)
                output = {
                    "acceptance": payload,
                    "created": int(created),
                    "reused": int(not created),
                    "identity_unit": "immutable_acceptance_artifact",
                }
            else:
                verify_acceptance(session, root, manifest, manifest_hash, ledger)
                if args.stage in {"inspect-signals", "inspect-state"}:
                    output = inspect_stage(
                        session, args.stage.removeprefix("inspect-"), as_of(manifest)
                    )
                elif args.stage == "export":
                    trace = export_trace(session, manifest, ledger)
                    fingerprint = trace["fingerprint"]
                    fingerprint_created = write_exact(
                        root / "expected_fingerprint.v1.json", fingerprint
                    )
                    trace_created = write_exact(root / "trace.v2.json", trace)
                    output = {
                        "fingerprint": fingerprint,
                        "trace": str(root / "trace.v2.json"),
                        "created": int(fingerprint_created) + int(trace_created),
                        "reused": 2 - int(fingerprint_created) - int(trace_created),
                        "identity_unit": "immutable_export_artifact",
                    }
                else:
                    session.rollback()  # Finish the read-only acceptance transaction.
                    output = materialize(session, args.stage, as_of(manifest))
    output.setdefault("stage", args.stage)
    output.setdefault("semantic_as_of", manifest["state_as_of"])
    output.setdefault("workspace_id", str(WORKSPACE_ID))
    output.setdefault("strategy_version_id", str(STRATEGY_ID))
    output.setdefault("manifest_version", manifest["manifest_version"])
    output.setdefault(
        "version_ids",
        {
            "strategy": "0.1.0",
            "signal_rule": "1.0.0",
            "state_engine": "1.1.0",
            "decision_evaluator": "1.0.0",
            "policy_evaluator": "1.0.0",
            "mappers": {dataset: "1.0.0" for _, dataset, _ in DATASETS},
            "identity_rule": "1.0.0",
        },
    )
    output.setdefault("input_ids", [manifest_hash])
    if args.stage == "validate":
        counts = {
            "profile_rows": output["company_public_profiles"]["rows"],
            "leader_rows": output["company_public_events"]["rows"],
        }
    elif args.stage == "setup":
        counts = {
            "workspace": 1,
            "strategy_version": 1,
            "strategy_evidence": 6,
            "fit_criterion": 1,
            "signal_definition": 1,
            "decision_definition": 1,
            "policy_definition": 1,
        }
    elif args.stage == "inspect":
        counts = {dataset: output[dataset]["counts"] for _, dataset, _ in DATASETS}
    elif args.stage == "accept":
        counts = {
            dataset: info["counts"] for dataset, info in output["acceptance"]["batches"].items()
        }
    elif args.stage in {"inspect-signals", "inspect-state"}:
        counts = {"inspected_accounts": output["count"]}
    elif args.stage == "export":
        counts = output["fingerprint"]["object_counts"]
    else:
        counts = output.get("results", {})
    output.setdefault("result_counts", counts)
    output.setdefault("created", None)
    output.setdefault("reused", None)
    output.setdefault("failures", 0)
    print(json.dumps(output, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
