"""M2A local boundary tests: bounded CSV, clocks, mapping, and source safety."""

from __future__ import annotations

import csv
import socket
from pathlib import Path

import pytest

from gtm_state_api.ingestion_mapping import MappingRejection, get_mapper
from gtm_state_api.local_csv import CSV_HEADER, ImportFileError, parse_local_csv
from gtm_state_api.types import EvidenceAssertion, EvidenceClassification, IngestionReason


def row(**changes: str) -> dict[str, str]:
    item = dict(
        zip(
            CSV_HEADER,
            (
                "row-1",
                "company-1",
                "Example Company",
                "example.com",
                "2026-09-15T12:00:00Z",
                "2026-09-14T12:00:00Z",
                "https://example.com/news/leader",
                "new_revenue_leader",
                "PRESENT",
                "The company appointed a new revenue leader.",
            ),
            strict=True,
        )
    )
    item.update(changes)
    return item


def file(path: Path, rows: list[dict[str, str]], *, header: tuple[str, ...] = CSV_HEADER) -> Path:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=header, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    return path


@pytest.mark.parametrize(
    ("change", "reason"),
    [
        ({"source_observed_at": "yesterday"}, IngestionReason.INVALID_DATE),
        ({"event_at": ""}, None),
        ({"event_at": "2026-10-01T00:00:00Z"}, IngestionReason.INVALID_DATE),
        ({"company_name": "=1+1"}, IngestionReason.INVALID_ROW),
        ({"source_excerpt": "@SUM(A1)"}, IngestionReason.INVALID_ROW),
        ({"source_url": "http://example.com/news"}, IngestionReason.INVALID_CITATION),
        ({"source_url": "https://user:pass@example.com/news"}, IngestionReason.INVALID_CITATION),
        ({"source_url": "https://localhost/news"}, IngestionReason.INVALID_CITATION),
        ({"source_url": "https://example.com/news?token=secret"}, IngestionReason.INVALID_CITATION),
        ({"source_url": "https://wrong.example/news"}, IngestionReason.INVALID_CITATION),
        ({"source_excerpt": "x" * 241}, IngestionReason.FIELD_TOO_LARGE),
        ({"company_domain": "127.0.0.1"}, IngestionReason.INVALID_ROW),
    ],
)
def test_row_validation_is_bounded(
    tmp_path: Path, change: dict[str, str], reason: IngestionReason | None
) -> None:
    path = file(tmp_path / "input.csv", [row(**change)])
    _, parsed = parse_local_csv(path, dataset_key="company_public_events")
    assert len(parsed) == 1
    assert parsed[0].reason is reason


def test_missing_event_time_cannot_be_replaced_by_ingestion_clock(tmp_path: Path) -> None:
    _, parsed = parse_local_csv(
        file(tmp_path / "input.csv", [row(event_at="")]),
        dataset_key="company_public_events",
    )
    observation = parsed[0].observation
    assert observation is not None
    mapper = get_mapper("company_public_event", "1.0.0", "public_company_leader_event", "1.0.0")
    with pytest.raises(MappingRejection) as raised:
        mapper.normalize(observation)
    assert raised.value.reason is IngestionReason.EVENT_TIME_REQUIRED


@pytest.mark.parametrize(
    "content",
    [
        pytest.param(b"", id="empty"),
        pytest.param(b"not,a,header\n", id="bad-header"),
        pytest.param(b"\xff\xfeinvalid", id="bad-encoding"),
        pytest.param(b"x" * 1_048_577, id="too-large"),
        pytest.param(b"bad\x00content", id="null-byte"),
    ],
)
def test_file_level_refusal(tmp_path: Path, content: bytes) -> None:
    path = tmp_path / "input.csv"
    path.write_bytes(content)
    with pytest.raises(ImportFileError):
        parse_local_csv(path, dataset_key="company_public_events")


def test_exact_header_row_limit_and_extension(tmp_path: Path) -> None:
    bad_header = tmp_path / "bad.csv"
    bad_header.write_bytes(b"bad,header\n")
    with pytest.raises(ImportFileError):
        parse_local_csv(bad_header, dataset_key="company_public_events")
    with pytest.raises(ImportFileError):
        parse_local_csv(
            file(tmp_path / "over.csv", [row() for _ in range(501)]),
            dataset_key="company_public_events",
        )
    with pytest.raises(ImportFileError):
        parse_local_csv(file(tmp_path / "bad.txt", [row()]), dataset_key="company_public_events")
    with pytest.raises(ImportFileError):
        parse_local_csv(file(tmp_path / "unknown.csv", [row()]), dataset_key="unknown")


def test_mapper_registry_rejects_arbitrary_fact_and_assertion(tmp_path: Path) -> None:
    mapper = get_mapper("company_public_event", "1.0.0", "public_company_leader_event", "1.0.0")
    assert mapper.supported_fact_key == "commercial_event.new_revenue_leader"
    assert mapper.classification is EvidenceClassification.FACT
    assert EvidenceAssertion.ABSENT in mapper.allowed_assertions
    for values, reason in [
        ({"fact_code": "arbitrary.executable.fact"}, IngestionReason.UNSUPPORTED_FACT),
        ({"assertion": "FACT"}, IngestionReason.INVALID_ASSERTION),
        ({"assertion": ""}, IngestionReason.INVALID_ASSERTION),
    ]:
        _, parsed = parse_local_csv(
            file(tmp_path / "input.csv", [row(**values)]), dataset_key="company_public_events"
        )
        observation = parsed[0].observation
        assert observation is not None
        with pytest.raises(MappingRejection) as raised:
            mapper.normalize(observation)
        assert raised.value.reason is reason
    with pytest.raises(ValueError, match="unsupported"):
        get_mapper("company_public_event", "1.0.0", "unregistered", "1.0.0")


def test_parser_and_mapper_do_not_call_network(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def no_network(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("network called")

    monkeypatch.setattr(socket.socket, "connect", no_network)
    _, parsed = parse_local_csv(
        file(tmp_path / "input.csv", [row()]), dataset_key="company_public_events"
    )
    observation = parsed[0].observation
    assert observation is not None
    fact = get_mapper(
        "company_public_event", "1.0.0", "public_company_leader_event", "1.0.0"
    ).normalize(observation)
    assert fact.observed_at.isoformat() == "2026-09-14T12:00:00+00:00"


@pytest.mark.parametrize(
    ("batch_exists", "null_segment_exists", "message"),
    [
        (True, False, "imported batches"),
        (False, True, "null segment"),
    ],
)
def test_m2a_downgrade_refuses_unrepresentable_data(
    monkeypatch: pytest.MonkeyPatch,
    batch_exists: bool,
    null_segment_exists: bool,
    message: str,
) -> None:
    import runpy

    migration = (
        Path(__file__).resolve().parents[1] / "alembic/versions/20261003_0007_m2a_ingestion.py"
    )
    namespace = runpy.run_path(str(migration))

    class FakeBind:
        calls = 0

        def scalar(self, _statement: object) -> bool:
            self.calls += 1
            return batch_exists if self.calls == 1 else null_segment_exists

    bind = FakeBind()
    monkeypatch.setattr(namespace["op"], "get_bind", lambda: bind)
    monkeypatch.setattr(
        namespace["op"], "drop_table", lambda *_args: pytest.fail("downgrade mutated schema")
    )
    with pytest.raises(RuntimeError, match=message):
        namespace["downgrade"]()
