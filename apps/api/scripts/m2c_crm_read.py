"""Operator-triggered, local-only M2C stages. No provider write exists."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from uuid import UUID

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from gtm_state_api.database import get_session_factory
from gtm_state_api.hubspot_company_read import (
    CompanyRead,
    read_company,
    verify_developer_test_portal,
)
from gtm_state_api.ingestion_service import require_local_ingestion
from gtm_state_api.m2c_run import export_trace, inspect_run, materialize_stage
from gtm_state_api.m2c_workspace import setup
from gtm_state_api.private_company_read import (
    CustomerStageMapping,
    read_company_into_evidence,
)


class LocalM2CSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[3] / ".env.m2c.local",
        extra="ignore",
    )

    m2c_hubspot_access_token: SecretStr | None = None
    m2c_hubspot_portal_id: str | None = None
    m2c_hubspot_customer_stage_value: str | None = None
    m2c_hubspot_stage_mapping_version: str | None = None
    m2c_hubspot_customer_company_id: str | None = None
    m2c_hubspot_noncustomer_company_id: str | None = None


def _semantic_time(value: str | None) -> datetime:
    if value is None:
        raise ValueError("explicit timezone-aware --as-of is required")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("--as-of must include a timezone")
    return parsed


def _live_config(settings: LocalM2CSettings) -> tuple[str, str, CustomerStageMapping]:
    token = settings.m2c_hubspot_access_token
    portal = settings.m2c_hubspot_portal_id
    stage = settings.m2c_hubspot_customer_stage_value
    version = settings.m2c_hubspot_stage_mapping_version
    if not portal or not stage or not version:
        raise ValueError("M2C developer-test portal or stage mapping is missing")
    return (token.get_secret_value() if token else ""), portal, CustomerStageMapping(stage, version)


def main() -> None:
    parser = argparse.ArgumentParser(description="M2C local CRM relationship read")
    parser.add_argument(
        "stage",
        choices=(
            "setup",
            "probe",
            "pull",
            "inspect",
            "signals",
            "state",
            "decisions",
            "policies",
            "actions",
            "trace",
        ),
    )
    parser.add_argument("--as-of", help="Explicit semantic time; also fixture time for setup")
    parser.add_argument("--company-id", help="One allowlisted synthetic test Company ID")
    parser.add_argument("--role", choices=("customer", "noncustomer"))
    parser.add_argument(
        "--run-id", action="append", default=[], help="Inspected source read run ID"
    )
    parser.add_argument("--confirm-inspected", action="store_true")
    parser.add_argument("--attest-customer-stage", action="store_true")
    args = parser.parse_args()
    require_local_ingestion()
    output: dict[str, object]
    with get_session_factory()() as session:
        if args.stage == "setup":
            output = dict(setup(session, fixture_as_of=_semantic_time(args.as_of)))
        elif args.stage in {"probe", "pull"}:
            if not args.attest_customer_stage:
                raise ValueError("operator must attest the exact Customer stage mapping")
            settings = LocalM2CSettings()
            token, portal, mapping = _live_config(settings)
            allowed_ids = {
                settings.m2c_hubspot_customer_company_id,
                settings.m2c_hubspot_noncustomer_company_id,
            }
            selected_id: str | None = (
                settings.m2c_hubspot_customer_company_id
                if args.role == "customer"
                else settings.m2c_hubspot_noncustomer_company_id
                if args.role == "noncustomer"
                else str(args.company_id)
                if args.company_id is not None
                else None
            )
            if selected_id is None:
                raise ValueError("Synthetic test Company ID is missing")
            if selected_id not in allowed_ids:
                raise ValueError("Company ID must be one of the two configured synthetic test IDs")

            def verified_reader(company_id: str, *, credential: str) -> CompanyRead:
                verify_developer_test_portal(credential=credential, expected_portal_id=portal)
                return read_company(company_id, credential=credential)

            if args.stage == "probe":
                read = verified_reader(selected_id, credential=token)
                output = {
                    "stage": "probe",
                    "developer_test_verified": True,
                    "record_present": read.record is not None,
                    "company_fields_validated": read.record is not None,
                    "company_name": read.record.company_name if read.record else None,
                    "company_domain": read.record.company_domain if read.record else None,
                    "customer_stage_exact_match": (
                        read.record.lifecycle_stage == mapping.customer_value
                        if read.record
                        else None
                    ),
                    "retry_count": read.retry_count,
                    "source_observation_created": False,
                    "external_side_effects": False,
                }
            else:
                run_id = read_company_into_evidence(
                    session,
                    workspace_id=setup_workspace_id(),
                    portal_id=portal,
                    company_id=selected_id,
                    credential=token,
                    mapping=mapping,
                    reader=verified_reader,
                )
                output = inspect_run(session, run_id)
        elif args.stage == "inspect":
            if len(args.run_id) != 1:
                raise ValueError("inspect requires one --run-id")
            output = inspect_run(session, UUID(args.run_id[0]))
        elif args.stage == "trace":
            output = export_trace(session, as_of=_semantic_time(args.as_of))
        else:
            if not args.confirm_inspected:
                raise ValueError("inspect source runs, then pass --confirm-inspected")
            output = materialize_stage(
                session,
                stage=args.stage,
                as_of=_semantic_time(args.as_of),
                inspected_run_ids=tuple(UUID(item) for item in args.run_id),
            )
    print(json.dumps(output, indent=2, sort_keys=True))


def setup_workspace_id() -> UUID:
    from gtm_state_api.m2c_workspace import WORKSPACE_ID

    return WORKSPACE_ID


if __name__ == "__main__":
    main()
