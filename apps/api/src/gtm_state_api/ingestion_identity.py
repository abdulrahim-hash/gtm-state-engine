"""Conservative deterministic Account identity resolution for source observations."""

from __future__ import annotations

import ipaddress
import re
import unicodedata
from dataclasses import dataclass
from uuid import UUID, uuid5

from sqlalchemy import select
from sqlalchemy.orm import Session

from gtm_state_api.models import Account, AccountSourceId
from gtm_state_api.source_observation import (
    ACCOUNT_NAMESPACE,
    IDENTITY_RULE_VERSION,
    SourceObservationInput,
    canonical_hash,
)
from gtm_state_api.types import IngestionReason

LABEL_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")


def normalize_domain(value: str) -> str:
    """Normalize a hostname only; never infer a parent from an arbitrary subdomain."""
    raw = value.strip().rstrip(".")
    if raw.lower().startswith("www."):
        raw = raw[4:]
    try:
        domain = raw.encode("idna").decode("ascii").lower()
    except UnicodeError as exc:
        raise ValueError("invalid company domain") from exc
    if (
        len(domain) > 253
        or "." not in domain
        or any(not LABEL_RE.fullmatch(x) for x in domain.split("."))
    ):
        raise ValueError("invalid company domain")
    try:
        ipaddress.ip_address(domain)
    except ValueError:
        pass
    else:
        raise ValueError("IP address cannot identify an Account")
    if domain.endswith(".local") or domain.endswith(".internal") or domain == "localhost":
        raise ValueError("non-public company domain")
    return domain


def normalize_name(value: str) -> str:
    return " ".join(unicodedata.normalize("NFC", value).casefold().split())


def preflight_identity(
    rows: list[tuple[int, SourceObservationInput]],
) -> dict[int, IngestionReason]:
    """Find conflicting claims before writes, independent of row order."""
    domains: dict[str, set[str]] = {}
    ids: dict[str, set[str]] = {}
    names: dict[str, set[str]] = {}
    for _ordinal, row in rows:
        name = normalize_name(row.company_name)
        domain = normalize_domain(row.company_domain) if row.company_domain else ""
        if domain:
            domains.setdefault(domain, set()).add(name)
            names.setdefault(name, set()).add(domain)
        if row.external_account_id:
            ids.setdefault(row.external_account_id, set()).add(domain)
    result: dict[int, IngestionReason] = {}
    for ordinal, row in rows:
        name = normalize_name(row.company_name)
        domain = normalize_domain(row.company_domain) if row.company_domain else ""
        if row.external_account_id and len(ids[row.external_account_id]) > 1:
            result[ordinal] = IngestionReason.SOURCE_ID_CONFLICT
        elif domain and (len(domains[domain]) > 1 or len(names[name]) > 1):
            result[ordinal] = IngestionReason.AMBIGUOUS_IDENTITY
    return result


@dataclass(frozen=True)
class IdentityDecision:
    account: Account | None
    new_account_id: UUID | None
    reason: IngestionReason | None
    input_hash: str


def resolve_identity(
    session: Session,
    *,
    workspace_id: UUID,
    source_system_key: str,
    dataset_key: str,
    observation: SourceObservationInput,
    preflight_reason: IngestionReason | None,
) -> IdentityDecision:
    """Resolve exact domain and immutable source bindings; return abstention otherwise."""
    domain = normalize_domain(observation.company_domain) if observation.company_domain else None
    name = normalize_name(observation.company_name)
    bound = None
    if observation.external_account_id:
        bound = session.scalar(
            select(AccountSourceId).where(
                AccountSourceId.workspace_id == workspace_id,
                AccountSourceId.source_system_key == source_system_key,
                AccountSourceId.dataset_key == dataset_key,
                AccountSourceId.external_account_id == observation.external_account_id,
            )
        )
    domain_account = (
        session.scalar(
            select(Account).where(Account.workspace_id == workspace_id, Account.domain == domain)
        )
        if domain
        else None
    )
    same_name_accounts = session.scalars(
        select(Account).where(Account.workspace_id == workspace_id)
    ).all()
    name_matches = [
        item for item in same_name_accounts if normalize_name(item.canonical_name) == name
    ]
    bound_account = session.get(Account, bound.account_id) if bound else None
    input_hash = canonical_hash(
        {
            "workspace_id": str(workspace_id),
            "source_system_key": source_system_key,
            "dataset_key": dataset_key,
            "external_account_id": observation.external_account_id,
            "name": name,
            "domain": domain,
            "bound_account_id": str(bound_account.id) if bound_account else None,
            "domain_account_id": str(domain_account.id) if domain_account else None,
            "name_match_ids": sorted(str(item.id) for item in name_matches),
            "preflight_reason": preflight_reason.value if preflight_reason else None,
        }
    )

    def decided(
        account: Account | None = None,
        new_id: UUID | None = None,
        reason: IngestionReason | None = None,
    ) -> IdentityDecision:
        return IdentityDecision(account, new_id, reason, input_hash)

    if preflight_reason:
        return decided(reason=preflight_reason)
    if bound_account:
        if name != normalize_name(bound_account.canonical_name):
            return decided(reason=IngestionReason.AMBIGUOUS_IDENTITY)
        if domain and domain != bound_account.domain:
            return decided(reason=IngestionReason.SOURCE_ID_CONFLICT)
        if domain_account and domain_account.id != bound_account.id:
            return decided(reason=IngestionReason.SOURCE_ID_CONFLICT)
        return decided(account=bound_account)
    if domain_account:
        if name != normalize_name(domain_account.canonical_name):
            return decided(reason=IngestionReason.AMBIGUOUS_IDENTITY)
        return decided(account=domain_account)
    if domain is None:
        return decided(reason=IngestionReason.MISSING_IDENTITY)
    if name_matches:
        return decided(reason=IngestionReason.AMBIGUOUS_IDENTITY)
    return decided(new_id=uuid5(ACCOUNT_NAMESPACE, f"{workspace_id}:{domain}"))


IDENTITY_RULE_REGISTRY = {IDENTITY_RULE_VERSION: resolve_identity}
