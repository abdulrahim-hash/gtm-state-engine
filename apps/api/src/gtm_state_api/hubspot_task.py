"""Narrow HubSpot developer-test Task adapter; no generic CRM write surface."""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from time import sleep
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener

from gtm_state_api.hubspot_company_read import verify_developer_test_portal

ADAPTER_KEY = "hubspot_task_create"
ADAPTER_VERSION = "1.0.0"
API_VERSION = "2026-09"
BASE = "https://api.hubapi.com"
TASKS_PATH = f"/crm/objects/{API_VERSION}/tasks"
ASSOCIATION_LABELS_PATH = f"/crm/associations/{API_VERSION}/tasks/companies/labels"
TASK_READ_PROPERTIES = ",".join(
    (
        "hs_timestamp",
        "hs_task_subject",
        "hs_task_body",
        "hs_task_status",
        "hubspot_owner_id",
    )
)
MAX_BODY_BYTES = 16_384
MAX_GET_RETRIES = 2
MAX_MARKER_PAGES = 3
ID_RE = re.compile(r"^[0-9]{1,30}$")
CORRELATION_RE = re.compile(r"^[A-Za-z0-9-]{1,120}$")
Transport = Callable[[Request], tuple[int, bytes, Mapping[str, str]]]


def _allowed(method: str, path: str) -> bool:
    if method == "POST":
        return path == TASKS_PATH
    if method != "GET":
        return False
    return bool(
        path == ASSOCIATION_LABELS_PATH
        or re.fullmatch(rf"/crm/owners/{API_VERSION}/[0-9]{{1,30}}", path)
        or re.fullmatch(
            rf"{TASKS_PATH}/[0-9]{{1,30}}\?properties=[A-Za-z0-9_,%]+&associations=companies&archived=false",
            path,
        )
        or re.fullmatch(
            rf"{TASKS_PATH}\?limit=100&properties=hs_task_body(?:&after=[A-Za-z0-9_-]{{1,200}})?",
            path,
        )
    )


class TaskAdapterError(Exception):
    """Safe, bounded error; never includes request, response body, or credential."""

    def __init__(
        self, code: str, *, status: int | None = None, correlation: str | None = None
    ) -> None:
        super().__init__(code)
        self.code = code
        self.status = status
        self.correlation = correlation


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(
        self, request: Request, fp: object, code: int, msg: str, headers: object, newurl: str
    ) -> None:
        return None


def _transport(request: Request) -> tuple[int, bytes, Mapping[str, str]]:
    url = request.full_url
    method = request.get_method()
    if not url.startswith(BASE) or not _allowed(method, url[len(BASE) :]):
        raise TaskAdapterError("DISALLOWED_REQUEST")
    try:
        with build_opener(_NoRedirect()).open(request, timeout=5) as response:
            return (
                response.status,
                response.read(MAX_BODY_BYTES + 1),
                dict(response.headers.items()),
            )
    except HTTPError as exc:
        body = exc.read(MAX_BODY_BYTES + 1)
        return exc.code, body, dict(exc.headers.items()) if exc.headers else {}
    except (OSError, URLError) as exc:
        raise TaskAdapterError("TIMEOUT_OR_NETWORK") from exc


def _request(
    method: str, path: str, credential: str, *, body: dict[str, object] | None = None
) -> Request:
    if not credential or credential.isspace():
        raise TaskAdapterError("MISSING_CREDENTIAL")
    if not _allowed(method, path):
        raise TaskAdapterError("DISALLOWED_REQUEST")
    encoded = json.dumps(body, sort_keys=True, separators=(",", ":")).encode() if body else None
    if encoded and len(encoded) > 4096:
        raise TaskAdapterError("REQUEST_TOO_LARGE")
    return Request(
        BASE + path,
        data=encoded,
        headers={
            "Authorization": f"Bearer {credential}",
            "Accept": "application/json",
            **({"Content-Type": "application/json"} if encoded else {}),
        },
        method=method,
    )


def _perform_get(
    request: Request, *, transport: Transport, sleep_fn: Callable[[float], None] = sleep
) -> tuple[int, bytes, str | None, int]:
    for retries in range(MAX_GET_RETRIES + 1):
        try:
            status, body, headers = transport(request)
        except TaskAdapterError:
            if retries == MAX_GET_RETRIES:
                raise
            sleep_fn(0.25 * (2**retries))
            continue
        correlation = headers.get("X-HubSpot-Correlation-Id")
        if correlation is not None and CORRELATION_RE.fullmatch(correlation) is None:
            correlation = None
        if status == 429 or 500 <= status <= 599:
            if retries == MAX_GET_RETRIES:
                raise TaskAdapterError("READ_UNAVAILABLE", status=status, correlation=correlation)
            sleep_fn(0.25 * (2**retries))
            continue
        if len(body) > MAX_BODY_BYTES:
            raise TaskAdapterError("RESPONSE_TOO_LARGE", status=status)
        return status, body, correlation, retries
    raise AssertionError("bounded GET loop exhausted")


def _json_object(body: bytes) -> dict[str, object]:
    try:
        value = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TaskAdapterError("MALFORMED_RESPONSE") from exc
    if not isinstance(value, dict):
        raise TaskAdapterError("MALFORMED_RESPONSE")
    return value


@dataclass(frozen=True)
class TaskFields:
    due_at: str
    subject: str
    body: str
    owner_id: str

    def __post_init__(self) -> None:
        if not ID_RE.fullmatch(self.owner_id):
            raise ValueError("invalid Task owner ID")
        if not 1 <= len(self.subject) <= 120 or not 1 <= len(self.body) <= 400:
            raise ValueError("Task text exceeds M5A bounds")
        if "SYNTHETIC" not in self.subject or "DEVELOPER TEST" not in self.body:
            raise ValueError("Task must be visibly synthetic developer-test content")
        try:
            parsed = datetime.fromisoformat(self.due_at.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("invalid Task due timestamp") from exc
        if parsed.tzinfo is None:
            raise ValueError("Task due timestamp requires timezone")

    def properties(self) -> dict[str, str]:
        return {
            "hs_timestamp": self.due_at,
            "hs_task_subject": self.subject,
            "hs_task_body": self.body,
            "hs_task_status": "NOT_STARTED",
            "hubspot_owner_id": self.owner_id,
        }


@dataclass(frozen=True)
class TaskWriteResult:
    task_id: str
    correlation: str | None
    created_at: datetime | None
    response_projection: dict[str, str]


@dataclass(frozen=True)
class TaskReadResult:
    task_id: str
    archived: bool
    properties: dict[str, str | None]
    company_ids: tuple[str, ...]
    correlation: str | None


def verify_owner(owner_id: str, *, credential: str, transport: Transport = _transport) -> bool:
    """Read exactly one configured owner; never ingest an owner directory."""

    if not ID_RE.fullmatch(owner_id):
        raise TaskAdapterError("INVALID_OWNER_ID")
    status, body, _, _ = _perform_get(
        _request("GET", f"/crm/owners/{API_VERSION}/{owner_id}", credential), transport=transport
    )
    if status != 200:
        raise TaskAdapterError("OWNER_UNAVAILABLE", status=status)
    value = _json_object(body)
    if (
        str(value.get("id")) != owner_id
        or value.get("archived") is not False
        or value.get("userId") is None
    ):
        raise TaskAdapterError("OWNER_NOT_ACTIVE")
    return True


def verify_task_company_association(
    association_type_id: int, *, credential: str, transport: Transport = _transport
) -> bool:
    """Confirm the exact unlabelled Task-to-Company type in this portal."""

    if association_type_id <= 0:
        raise TaskAdapterError("INVALID_ASSOCIATION_TYPE")
    status, body, _, _ = _perform_get(
        _request("GET", ASSOCIATION_LABELS_PATH, credential), transport=transport
    )
    if status != 200:
        raise TaskAdapterError("ASSOCIATION_TYPE_UNVERIFIED", status=status)
    value = _json_object(body)
    results = value.get("results")
    if not isinstance(results, list) or len(results) > 100:
        raise TaskAdapterError("MALFORMED_RESPONSE")
    matches = [
        item
        for item in results
        if isinstance(item, dict)
        and item.get("category") == "HUBSPOT_DEFINED"
        and item.get("label") is None
        and item.get("typeId") == association_type_id
    ]
    if len(matches) != 1:
        raise TaskAdapterError("ASSOCIATION_TYPE_UNVERIFIED")
    return True


def create_task_once(
    *,
    credential: str,
    fields: TaskFields,
    company_id: str,
    association_type_id: int,
    transport: Transport = _transport,
) -> TaskWriteResult:
    """Issue one POST, without retry; caller must reserve dispatch durably first."""

    if not ID_RE.fullmatch(company_id) or association_type_id <= 0:
        raise TaskAdapterError("INVALID_TARGET")
    payload: dict[str, object] = {
        "properties": fields.properties(),
        "associations": [
            {
                "to": {"id": company_id},
                "types": [
                    {
                        "associationCategory": "HUBSPOT_DEFINED",
                        "associationTypeId": association_type_id,
                    }
                ],
            }
        ],
    }
    request = _request("POST", TASKS_PATH, credential, body=payload)
    status, body, headers = transport(request)  # exactly one physical call
    correlation = headers.get("X-HubSpot-Correlation-Id")
    if correlation is not None and CORRELATION_RE.fullmatch(correlation) is None:
        correlation = None
    deterministic_validation = False
    if status == 400 and len(body) <= MAX_BODY_BYTES:
        try:
            deterministic_validation = _json_object(body).get("category") == "VALIDATION_ERROR"
        except TaskAdapterError:
            deterministic_validation = False
    if status in {401, 403} or deterministic_validation:
        raise TaskAdapterError("PROVIDER_REJECTED_NO_WRITE", status=status, correlation=correlation)
    if status != 201:
        raise TaskAdapterError("AMBIGUOUS_WRITE_RESPONSE", status=status, correlation=correlation)
    if len(body) > MAX_BODY_BYTES:
        raise TaskAdapterError("AMBIGUOUS_WRITE_RESPONSE", status=status, correlation=correlation)
    value = _json_object(body)
    task_id = str(value.get("id", ""))
    if not ID_RE.fullmatch(task_id):
        raise TaskAdapterError("AMBIGUOUS_WRITE_RESPONSE", status=status, correlation=correlation)
    created = value.get("createdAt")
    try:
        created_at = (
            datetime.fromisoformat(str(created).replace("Z", "+00:00")) if created else None
        )
    except ValueError:
        created_at = None
    return TaskWriteResult(
        task_id,
        correlation,
        created_at,
        {"id": task_id, "createdAt": str(created or ""), "http": "201"},
    )


def get_task(
    task_id: str, *, credential: str, transport: Transport = _transport
) -> tuple[TaskReadResult | None, int]:
    if not ID_RE.fullmatch(task_id):
        raise TaskAdapterError("INVALID_TASK_ID")
    query = urlencode(
        {
            "properties": TASK_READ_PROPERTIES,
            "associations": "companies",
            "archived": "false",
        }
    )
    status, body, correlation, retries = _perform_get(
        _request("GET", f"{TASKS_PATH}/{task_id}?{query}", credential), transport=transport
    )
    if status == 404:
        return None, retries + 1
    if status != 200:
        raise TaskAdapterError("TASK_READ_FAILED", status=status, correlation=correlation)
    value = _json_object(body)
    props = value.get("properties")
    associations = value.get("associations")
    if (
        str(value.get("id")) != task_id
        or value.get("archived") is not False
        or not isinstance(props, dict)
        or not isinstance(associations, dict)
    ):
        raise TaskAdapterError("MALFORMED_RESPONSE")
    companies = associations.get("companies")
    if companies is None:
        company_ids: tuple[str, ...] = ()
    else:
        if not isinstance(companies, dict) or not isinstance(companies.get("results"), list):
            raise TaskAdapterError("ASSOCIATION_NOT_VERIFIABLE")
        if "paging" in companies:
            raise TaskAdapterError("ASSOCIATION_NOT_VERIFIABLE")
        if any(
            not isinstance(item, dict) or not ID_RE.fullmatch(str(item.get("id", "")))
            for item in companies["results"]
        ):
            raise TaskAdapterError("ASSOCIATION_NOT_VERIFIABLE")
        company_ids = tuple(str(item["id"]) for item in companies["results"])
    expected_keys = {
        "hs_timestamp",
        "hs_task_subject",
        "hs_task_body",
        "hs_task_status",
        "hubspot_owner_id",
    }
    selected = {
        key: props.get(key) if isinstance(props.get(key), str) else None for key in expected_keys
    }
    if isinstance(props.get("hs_timestamp"), int):
        selected["hs_timestamp"] = str(props["hs_timestamp"])
    return TaskReadResult(
        task_id, value.get("archived") is True, selected, company_ids, correlation
    ), retries + 1


def find_marker_task_ids(
    *, marker: str, company_id: str, credential: str, transport: Transport = _transport
) -> tuple[list[str], int, bool]:
    """Bounded read-only scan; incomplete pagination never proves absence."""

    if not marker.startswith("GTM-M5A:") or not ID_RE.fullmatch(company_id):
        raise TaskAdapterError("INVALID_MARKER_LOOKUP")
    matches: list[str] = []
    after: str | None = None
    reads = 0
    for _page in range(MAX_MARKER_PAGES):
        query = {"limit": "100", "properties": "hs_task_body"}
        if after:
            query["after"] = after
        status, body, _, retries = _perform_get(
            _request("GET", f"{TASKS_PATH}?{urlencode(query)}", credential), transport=transport
        )
        reads += retries + 1
        if status != 200:
            raise TaskAdapterError("MARKER_LOOKUP_FAILED", status=status)
        value = _json_object(body)
        results = value.get("results")
        if not isinstance(results, list) or len(results) > 100:
            raise TaskAdapterError("MALFORMED_RESPONSE")
        for item in results:
            if not isinstance(item, dict):
                raise TaskAdapterError("MALFORMED_RESPONSE")
            props = item.get("properties")
            task_id = str(item.get("id", ""))
            if (
                isinstance(props, dict)
                and marker in str(props.get("hs_task_body", ""))
                and ID_RE.fullmatch(task_id)
            ):
                matches.append(task_id)
        paging = value.get("paging")
        if paging is None:
            return matches, reads, True
        if not isinstance(paging, dict) or not isinstance(paging.get("next"), dict):
            raise TaskAdapterError("MALFORMED_RESPONSE")
        next_after = paging["next"].get("after")
        if not isinstance(next_after, str) or len(next_after) > 200:
            raise TaskAdapterError("MALFORMED_RESPONSE")
        after = next_after
    return matches, reads, False


def verify_portal(*, credential: str, portal_id: str) -> None:
    verify_developer_test_portal(credential=credential, expected_portal_id=portal_id)
