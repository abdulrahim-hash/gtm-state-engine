"""Strict local CSV adapter producing provider-neutral source observations."""

from __future__ import annotations

import csv
import io
import re
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from urllib.parse import urlsplit

from gtm_state_api.ingestion_identity import normalize_domain
from gtm_state_api.source_observation import (
    ParsedOccurrence,
    SourceObservationInput,
    canonical_hash,
)
from gtm_state_api.types import IngestionReason

MAX_FILE_BYTES = 1_048_576
MAX_ROWS = 500
CSV_SCHEMA_KEY = "company_public_event"
CSV_SCHEMA_VERSION = "1.0.0"
SOURCE_SYSTEM_KEY = "local_csv"
DATASET_REGISTRY: dict[str, tuple[str, str]] = {
    "company_public_events": (CSV_SCHEMA_KEY, CSV_SCHEMA_VERSION),
}
CSV_HEADER = (
    "source_record_id",
    "source_account_id",
    "company_name",
    "company_domain",
    "source_observed_at",
    "event_at",
    "source_url",
    "fact_code",
    "assertion",
    "source_excerpt",
)
FIELD_LIMITS = {
    "source_record_id": 120,
    "source_account_id": 120,
    "company_name": 200,
    "company_domain": 253,
    "source_observed_at": 40,
    "event_at": 40,
    "source_url": 500,
    "fact_code": 80,
    "assertion": 16,
    "source_excerpt": 240,
}
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")


class ImportFileError(ValueError):
    """Refuse a whole file before any database write."""


class RowValidationError(ValueError):
    def __init__(self, reason: IngestionReason) -> None:
        super().__init__(reason.value)
        self.reason = reason


def _timestamp(value: str, *, required: bool) -> datetime | None:
    if not value:
        if required:
            raise RowValidationError(IngestionReason.INVALID_DATE)
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise RowValidationError(IngestionReason.INVALID_DATE) from exc
    if parsed.tzinfo is None:
        raise RowValidationError(IngestionReason.INVALID_DATE)
    return parsed.astimezone(UTC)


def _citation(value: str, company_domain: str | None) -> None:
    if not value:
        raise RowValidationError(IngestionReason.INVALID_CITATION)
    try:
        url = urlsplit(value)
        host = normalize_domain(url.hostname or "")
        port = url.port
    except (ValueError, TypeError) as exc:
        raise RowValidationError(IngestionReason.INVALID_CITATION) from exc
    if (
        url.scheme != "https"
        or not url.path
        or url.username is not None
        or url.password is not None
        or url.query
        or url.fragment
        or (port is not None and port != 443)
        or (company_domain is not None and host != company_domain)
    ):
        raise RowValidationError(IngestionReason.INVALID_CITATION)


def _observation(row: dict[str, str]) -> SourceObservationInput:
    for field, value in row.items():
        if len(value) > FIELD_LIMITS[field]:
            raise RowValidationError(IngestionReason.FIELD_TOO_LARGE)
        if any(ord(char) < 32 or ord(char) == 127 for char in value):
            raise RowValidationError(IngestionReason.INVALID_ROW)
        if value.lstrip().startswith(("=", "+", "-", "@")):
            raise RowValidationError(IngestionReason.INVALID_ROW)
    external_record_id = row["source_record_id"]
    external_account_id = row["source_account_id"] or None
    if not ID_RE.fullmatch(external_record_id) or (
        external_account_id and not ID_RE.fullmatch(external_account_id)
    ):
        raise RowValidationError(IngestionReason.INVALID_ROW)
    company_name = row["company_name"].strip()
    if not company_name:
        raise RowValidationError(IngestionReason.INVALID_ROW)
    try:
        company_domain = normalize_domain(row["company_domain"]) if row["company_domain"] else None
    except ValueError as exc:
        raise RowValidationError(IngestionReason.INVALID_ROW) from exc
    source_observed_at = _timestamp(row["source_observed_at"], required=True)
    assert source_observed_at is not None
    event_at = _timestamp(row["event_at"], required=False)
    if event_at is not None and event_at > source_observed_at:
        raise RowValidationError(IngestionReason.INVALID_DATE)
    _citation(row["source_url"], company_domain)
    if not row["source_excerpt"].strip():
        raise RowValidationError(IngestionReason.INVALID_ROW)
    return SourceObservationInput(
        external_record_id=external_record_id,
        external_account_id=external_account_id,
        company_name=company_name,
        company_domain=company_domain,
        source_observed_at=source_observed_at,
        event_at=event_at,
        citation_url=row["source_url"],
        fact_code=row["fact_code"],
        assertion=row["assertion"],
        excerpt=row["source_excerpt"],
        original_fields=row,
        payload_sha256=canonical_hash(row),
    )


def parse_local_csv(path: Path, *, dataset_key: str) -> tuple[str, list[ParsedOccurrence]]:
    """Parse a bounded exact-schema file without network or database side effects."""
    if dataset_key not in DATASET_REGISTRY:
        raise ImportFileError("unsupported dataset")
    if path.suffix.lower() != ".csv" or not path.is_file() or path.is_symlink():
        raise ImportFileError("expected a regular .csv file")
    if path.stat().st_size > MAX_FILE_BYTES:
        raise ImportFileError("file exceeds 1 MiB")
    data = path.read_bytes()
    if len(data) > MAX_FILE_BYTES:
        raise ImportFileError("file exceeds 1 MiB")
    if not data:
        raise ImportFileError("empty file")
    try:
        body = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ImportFileError("expected UTF-8 CSV") from exc
    if "\x00" in body:
        raise ImportFileError("invalid CSV content")
    file_sha256 = sha256(data).hexdigest()
    try:
        reader = csv.reader(io.StringIO(body, newline=""), strict=True)
        header = next(reader, None)
        if header != list(CSV_HEADER):
            raise ImportFileError("unsupported CSV header or schema")
        parsed: list[ParsedOccurrence] = []
        for ordinal, cells in enumerate(reader, start=1):
            if ordinal > MAX_ROWS:
                raise ImportFileError("file exceeds 500 rows")
            row_sha256 = canonical_hash(cells)
            if len(cells) != len(CSV_HEADER):
                parsed.append(
                    ParsedOccurrence(ordinal, row_sha256, None, IngestionReason.INVALID_ROW)
                )
                continue
            row = dict(zip(CSV_HEADER, cells, strict=True))
            try:
                observation = _observation(row)
            except RowValidationError as exc:
                parsed.append(ParsedOccurrence(ordinal, row_sha256, None, exc.reason))
            else:
                parsed.append(ParsedOccurrence(ordinal, row_sha256, observation, None))
    except csv.Error as exc:
        raise ImportFileError("malformed CSV structure") from exc
    if not parsed:
        raise ImportFileError("CSV has no records")
    return file_sha256, parsed
