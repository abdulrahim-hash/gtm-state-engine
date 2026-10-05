"""Single-record, read-only HubSpot Company adapter for a developer test portal."""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from time import sleep
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

ADAPTER_KEY = "hubspot_company_read"
ADAPTER_VERSION = "1.0.0"
SOURCE_SYSTEM_KEY = "hubspot_crm"
MAX_RETRIES = 2
MAX_BODY_BYTES = 16_384
COMPANY_ID_RE = re.compile(r"^[0-9]{1,30}$")
CORRELATION_RE = re.compile(r"^[a-zA-Z0-9-]{1,120}$")
Transport = Callable[[Request], tuple[int, bytes, Mapping[str, str]]]


class ProviderReadError(Exception):
    """Bounded error without a provider body, company fields, or credential."""

    def __init__(self, code: str, *, status: int | None = None, retries: int = 0) -> None:
        super().__init__(code)
        self.code = code
        self.status = status
        self.retries = retries


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(
        self,
        request: Request,
        fp: object,
        code: int,
        msg: str,
        headers: object,
        newurl: str,
    ) -> None:
        return None


def _transport(request: Request) -> tuple[int, bytes, Mapping[str, str]]:
    allowed_company = request.full_url.startswith(
        "https://api.hubapi.com/crm/v3/objects/companies/"
    )
    allowed_portal = request.full_url == "https://api.hubapi.com/account-info/v3/details"
    if request.get_method() != "GET" or not (allowed_company or allowed_portal):
        raise ProviderReadError("DISALLOWED_REQUEST")
    try:
        with build_opener(_NoRedirect()).open(request, timeout=5) as response:
            body = response.read(MAX_BODY_BYTES + 1)
            return response.status, body, dict(response.headers.items())
    except HTTPError as exc:
        return exc.code, b"", dict(exc.headers.items()) if exc.headers else {}
    except (OSError, URLError) as exc:
        raise ProviderReadError("TIMEOUT_OR_NETWORK") from exc


@dataclass(frozen=True)
class CompanyRecord:
    provider_company_id: str
    company_name: str
    company_domain: str | None
    lifecycle_stage: str
    provider_updated_at: datetime | None


@dataclass(frozen=True)
class CompanyRead:
    record: CompanyRecord | None
    retry_count: int
    provider_correlation_id: str | None


def _validate_record(body: bytes, requested_id: str) -> CompanyRecord:
    if len(body) > MAX_BODY_BYTES:
        raise ProviderReadError("MALFORMED_RESPONSE")
    try:
        data = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProviderReadError("MALFORMED_RESPONSE") from exc
    if not isinstance(data, dict):
        raise ProviderReadError("MALFORMED_RESPONSE")
    if "paging" in data:
        raise ProviderReadError("INCOMPLETE_PAGINATION")
    fields = data.get("properties")
    if not isinstance(fields, dict) or str(data.get("id")) != requested_id:
        raise ProviderReadError("MALFORMED_RESPONSE")
    name = fields.get("name")
    domain = fields.get("domain")
    stage = fields.get("lifecyclestage")
    if (
        not isinstance(name, str)
        or not name.strip()
        or len(name) > 200
        or domain is not None
        and (not isinstance(domain, str) or len(domain) > 253)
        or stage is None
        and "lifecyclestage" not in fields
        or stage is not None
        and (not isinstance(stage, str) or len(stage) > 80)
    ):
        raise ProviderReadError("MISSING_REQUIRED_FIELD")
    updated = data.get("updatedAt")
    if updated is not None:
        if not isinstance(updated, str):
            raise ProviderReadError("MALFORMED_RESPONSE")
        try:
            updated_at = datetime.fromisoformat(updated.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ProviderReadError("MALFORMED_RESPONSE") from exc
        if updated_at.tzinfo is None:
            raise ProviderReadError("MALFORMED_RESPONSE")
    else:
        updated_at = None
    return CompanyRecord(
        provider_company_id=requested_id,
        company_name=name.strip(),
        company_domain=domain.strip() if isinstance(domain, str) and domain.strip() else None,
        lifecycle_stage=stage or "",
        provider_updated_at=updated_at,
    )


def verify_developer_test_portal(
    *,
    credential: str,
    expected_portal_id: str,
    transport: Transport = _transport,
    sleep_fn: Callable[[float], None] = sleep,
) -> None:
    """Fail closed before any Company read outside a developer test account."""

    if not credential or credential.isspace():
        raise ProviderReadError("MISSING_CREDENTIAL")
    request = Request(
        "https://api.hubapi.com/account-info/v3/details",
        headers={"Authorization": f"Bearer {credential}", "Accept": "application/json"},
        method="GET",
    )
    for retries in range(MAX_RETRIES + 1):
        try:
            status, body, _headers = transport(request)
        except ProviderReadError as exc:
            raise ProviderReadError(exc.code, retries=retries) from exc
        if status == 429 or 500 <= status <= 599:
            if retries < MAX_RETRIES:
                sleep_fn(0.25 * (2**retries))
                continue
            raise ProviderReadError(
                "RATE_LIMIT" if status == 429 else "PROVIDER_5XX",
                status=status,
                retries=retries,
            )
        break
    if status == 401:
        raise ProviderReadError("UNAUTHORIZED", status=status)
    if status == 403:
        raise ProviderReadError("FORBIDDEN", status=status)
    if status != 200 or len(body) > MAX_BODY_BYTES:
        raise ProviderReadError("PORTAL_VERIFICATION_FAILED", status=status)
    try:
        info = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProviderReadError("PORTAL_VERIFICATION_FAILED") from exc
    if not isinstance(info, dict):
        raise ProviderReadError("PORTAL_VERIFICATION_FAILED")
    if str(info.get("portalId")) != expected_portal_id:
        raise ProviderReadError("PORTAL_MISMATCH")
    if info.get("accountType") != "DEVELOPER_TEST":
        raise ProviderReadError("NOT_DEVELOPER_TEST")


def read_company(
    company_id: str,
    *,
    credential: str,
    transport: Transport = _transport,
    sleep_fn: Callable[[float], None] = sleep,
) -> CompanyRead:
    """GET one ID; never search, follow redirects, or issue a provider write."""

    if not COMPANY_ID_RE.fullmatch(company_id):
        raise ProviderReadError("INVALID_REQUEST")
    if not credential or credential.isspace():
        raise ProviderReadError("MISSING_CREDENTIAL")
    request = Request(
        f"https://api.hubapi.com/crm/v3/objects/companies/{company_id}"
        "?properties=name,domain,lifecyclestage&archived=false",
        headers={"Authorization": f"Bearer {credential}", "Accept": "application/json"},
        method="GET",
    )
    for retries in range(MAX_RETRIES + 1):
        try:
            status, body, headers = transport(request)
        except ProviderReadError as exc:
            raise ProviderReadError(exc.code, status=exc.status, retries=retries) from exc
        correlation = headers.get("X-HubSpot-Correlation-Id")
        if correlation is not None and not CORRELATION_RE.fullmatch(correlation):
            correlation = None
        if status == 404:
            return CompanyRead(None, retries, correlation)
        if status in {429} or 500 <= status <= 599:
            if retries < MAX_RETRIES:
                sleep_fn(0.25 * (2**retries))
                continue
            raise ProviderReadError(
                "RATE_LIMIT" if status == 429 else "PROVIDER_5XX",
                status=status,
                retries=retries,
            )
        if status == 401:
            raise ProviderReadError("UNAUTHORIZED", status=status, retries=retries)
        if status == 403:
            raise ProviderReadError("FORBIDDEN", status=status, retries=retries)
        if status != 200:
            raise ProviderReadError("PROVIDER_RESPONSE", status=status, retries=retries)
        return CompanyRead(_validate_record(body, company_id), retries, correlation)
    raise AssertionError("bounded retry loop exhausted unexpectedly")
