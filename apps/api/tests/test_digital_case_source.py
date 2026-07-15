from datetime import UTC, datetime

import pytest
from srbg_api.acquisition.contracts import SourceCheckpoint
from srbg_api.digital_cases.source import (
    FixedDigitalCaseFixtureAdapter,
    MotDigitalCaseAdapter,
    ShudaoDigitalCaseAdapter,
)


@pytest.mark.asyncio
async def test_live_adapters_refuse_network_without_injected_resilient_client() -> None:
    with pytest.raises(RuntimeError, match="acquisition HTTP client"):
        await MotDigitalCaseAdapter().discover(SourceCheckpoint())
    with pytest.raises(RuntimeError, match="acquisition HTTP client"):
        await ShudaoDigitalCaseAdapter().discover(SourceCheckpoint())


@pytest.mark.asyncio
async def test_fixed_adapter_replays_only_approved_url_and_honors_etag() -> None:
    fetched_at = datetime(2026, 7, 14, tzinfo=UTC)
    adapter = FixedDigitalCaseFixtureAdapter(
        external_id="shudao-smart-beam-factory-2",
        url="https://www.shudaojt.com/public/uploads/files/2022/03/fixture.pdf",
        title="智慧梁厂2.0",
        content="固定短摘录".encode(),
        etag='"sha256:fixture"',
        fetched_at=fetched_at,
    )

    batch = await adapter.discover(SourceCheckpoint())
    result = await adapter.fetch(batch.records[0], SourceCheckpoint())
    cached = await adapter.fetch(batch.records[0], SourceCheckpoint(etag='"sha256:fixture"'))

    assert len(batch.records) == 1
    assert result.content == "固定短摘录".encode()
    assert result.content_type == "application/pdf"
    assert cached.not_modified is True
    assert cached.content is None
