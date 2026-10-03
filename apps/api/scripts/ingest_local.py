"""Local-only M2A workspace, CSV import, replay, and promotion commands."""

from __future__ import annotations

import argparse
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid5

from gtm_state_api.database import get_session_factory
from gtm_state_api.ingestion_replay import promote_normalization_result, reprocess_observation
from gtm_state_api.ingestion_service import (
    batch_counts,
    import_local_csv,
    require_local_ingestion,
)
from gtm_state_api.local_csv import parse_local_csv
from gtm_state_api.models import IngestionBatch, Workspace
from gtm_state_api.source_observation import ACCOUNT_NAMESPACE

SLUG_RE = re.compile(r"^[a-z][a-z0-9-]{2,79}$")


def main() -> None:
    parser = argparse.ArgumentParser(description="Local, read-only-transport M2A ingestion")
    commands = parser.add_subparsers(dest="command", required=True)
    workspace_command = commands.add_parser("create-workspace")
    workspace_command.add_argument("--slug", required=True)
    workspace_command.add_argument("--name", required=True)
    validate_command = commands.add_parser("validate")
    validate_command.add_argument("path", type=Path)
    validate_command.add_argument("--dataset", default="company_public_events")
    import_command = commands.add_parser("import")
    import_command.add_argument("path", type=Path)
    import_command.add_argument("--workspace-id", type=UUID, required=True)
    import_command.add_argument("--dataset", default="company_public_events")
    import_command.add_argument("--mapper-key", default="public_company_leader_event")
    import_command.add_argument("--mapper-version", default="1.0.0")
    import_command.add_argument("--identity-rule-version", default="1.0.0")
    replay_command = commands.add_parser("reprocess")
    replay_command.add_argument("--observation-id", type=UUID, required=True)
    replay_command.add_argument("--mapper-key", required=True)
    replay_command.add_argument("--mapper-version", required=True)
    replay_command.add_argument("--identity-rule-version", required=True)
    promote_command = commands.add_parser("promote")
    promote_command.add_argument("--normalization-result-id", type=UUID, required=True)
    inspect_command = commands.add_parser("inspect")
    inspect_command.add_argument("--batch-id", type=UUID, required=True)
    args = parser.parse_args()
    require_local_ingestion()
    if args.command == "validate":
        file_hash, rows = parse_local_csv(args.path, dataset_key=args.dataset)
        print(json.dumps({"file_sha256": file_hash, "rows": len(rows), "database_writes": 0}))
        return
    factory = get_session_factory()
    with factory() as session:
        if args.command == "create-workspace":
            if not SLUG_RE.fullmatch(args.slug) or not (1 <= len(args.name) <= 200):
                parser.error("invalid workspace slug or name")
            workspace_id = uuid5(ACCOUNT_NAMESPACE, f"local-workspace:{args.slug}")
            with session.begin():
                workspace = session.get(Workspace, workspace_id)
                if workspace is None:
                    workspace = Workspace(
                        workspace_id=workspace_id,
                        slug=args.slug,
                        name=args.name,
                        demo_mode=False,
                        demo_as_of=None,
                        created_at=datetime.now(UTC),
                    )
                    session.add(workspace)
                elif (
                    workspace.slug != args.slug
                    or workspace.name != args.name
                    or workspace.demo_mode
                ):
                    raise ValueError("workspace identity already has different semantics")
            print(json.dumps({"workspace_id": str(workspace_id), "local_only": True}))
        elif args.command == "import":
            batch_id = import_local_csv(
                session,
                args.path,
                workspace_id=args.workspace_id,
                dataset_key=args.dataset,
                mapper_key=args.mapper_key,
                mapper_version=args.mapper_version,
                identity_rule_version=args.identity_rule_version,
            )
            print(json.dumps({"batch_id": str(batch_id), "ingestion_only": True}))
        elif args.command == "reprocess":
            result_id = reprocess_observation(
                session,
                args.observation_id,
                mapper_key=args.mapper_key,
                mapper_version=args.mapper_version,
                identity_rule_version=args.identity_rule_version,
            )
            print(json.dumps({"normalization_result_id": str(result_id), "promoted": False}))
        elif args.command == "promote":
            evidence_id = promote_normalization_result(session, args.normalization_result_id)
            print(json.dumps({"evidence_id": str(evidence_id), "promoted": True}))
        elif args.command == "inspect":
            batch = session.get(IngestionBatch, args.batch_id)
            if batch is None:
                parser.error("batch not found")
            print(
                json.dumps(
                    {
                        "batch_id": str(batch.id),
                        "workspace_id": str(batch.workspace_id),
                        "dataset_key": batch.dataset_key,
                        "schema_version": batch.schema_version,
                        "mapper_version": batch.mapper_version,
                        "counts": batch_counts(session, batch.id),
                    }
                )
            )


if __name__ == "__main__":
    main()
