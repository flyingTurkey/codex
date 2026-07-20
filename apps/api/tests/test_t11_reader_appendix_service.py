from collections.abc import Mapping
from contextlib import AbstractAsyncContextManager
from typing import Any
from uuid import UUID

import pytest
import srbg_api.intelligence_v2.service as service_module
from srbg_api.intelligence_v2.service import PostgresV2IntelligenceService, ProjectionNotFound

EVENT_ID = UUID("019f7c00-0000-7000-8000-000000000211")
CASE_ID = UUID("019f7c00-0000-7000-8000-000000000212")


class _MappingsResult:
    def __init__(self, row: Mapping[str, Any] | None) -> None:
        self._row = row

    def mappings(self) -> "_MappingsResult":
        return self

    def one_or_none(self) -> Mapping[str, Any] | None:
        return self._row


class _Connection:
    def __init__(self, row: Mapping[str, Any] | None) -> None:
        self._row = row

    async def execute(self, *_: object, **__: object) -> _MappingsResult:
        return _MappingsResult(self._row)


class _Connect(AbstractAsyncContextManager[_Connection]):
    def __init__(self, row: Mapping[str, Any] | None) -> None:
        self._connection = _Connection(row)

    async def __aexit__(self, *_: object) -> None:
        return None

    async def __aenter__(self) -> _Connection:
        return self._connection


class _ReaderEngine:
    def __init__(self, row: Mapping[str, Any] | None) -> None:
        self._row = row

    def connect(self) -> _Connect:
        return _Connect(self._row)

    async def dispose(self) -> None:
        return None


class _Metric:
    def __init__(self) -> None:
        self.outcomes: list[str] = []

    def labels(self, *, outcome: str) -> "_Metric":
        self.outcomes.append(outcome)
        return self

    def inc(self) -> None:
        return None


@pytest.mark.asyncio
async def test_appendix_combines_only_the_fail_closed_governance_view(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    row = {
        "event_id": EVENT_ID,
        "appendix_payload": {"event_id": str(EVENT_ID), "claims": []},
        "evidence": [],
        "evidence_total": 501,
        "automatic_results": [],
        "automatic_results_total": 0,
        "relationships": [],
        "relationships_total": 0,
        "automatic_relationships": [],
        "automatic_relationships_total": 0,
        "corrections": [],
        "corrections_total": 0,
        "review_case_id": CASE_ID,
    }
    reader = _ReaderEngine(row)
    service = PostgresV2IntelligenceService(reader, reader)  # type: ignore[arg-type]
    metric = _Metric()
    monkeypatch.setattr(service_module, "INTELLIGENCE_V2_APPENDIX_READS", metric)

    appendix = await service.appendix(EVENT_ID)

    assert appendix.review_context is not None
    assert appendix.review_context.href == f"/review?case_id={CASE_ID}"
    assert appendix.review_href == "/review"
    assert appendix.content_summary.total_items == 501
    assert appendix.content_summary.heavy_content is True
    assert appendix.content_summary.truncated_sections == ["EVIDENCE"]
    assert metric.outcomes == ["HEAVY"]


@pytest.mark.asyncio
async def test_appendix_returns_not_found_when_the_security_view_has_no_full_row(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reader = _ReaderEngine(None)
    service = PostgresV2IntelligenceService(reader, reader)  # type: ignore[arg-type]
    metric = _Metric()
    monkeypatch.setattr(service_module, "INTELLIGENCE_V2_APPENDIX_READS", metric)

    with pytest.raises(ProjectionNotFound):
        await service.appendix(EVENT_ID)
    assert metric.outcomes == ["FAIL_CLOSED"]
