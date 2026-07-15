import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from srbg_api.acquisition.contracts import SourceCheckpoint
from srbg_api.technology_products.source import FixedProductFixtureAdapter, VendorProductAdapter

FIXTURE_CONTENT = {
    filename: Path(f"apps/api/tests/fixtures/round07/{filename}").read_bytes()
    for filename in ("glodon-software.json", "dji-low-altitude.json")
}


@pytest.mark.asyncio
async def test_live_vendor_adapter_requires_server_computed_active_source() -> None:
    adapter = VendorProductAdapter(
        external_id="glodon-platform-v5",
        url="https://www.glodon.com/product/example",
        title="数字项目平台",
        source_active=False,
        client=None,
    )
    with pytest.raises(RuntimeError, match="ACTIVE source admission"):
        await adapter.discover(SourceCheckpoint())


@pytest.mark.asyncio
async def test_fixed_vendor_fixtures_replay_without_vendor_images() -> None:
    for filename in ("glodon-software.json", "dji-low-altitude.json"):
        content = FIXTURE_CONTENT[filename]
        payload = json.loads(content)
        adapter = FixedProductFixtureAdapter(
            external_id=payload["external_id"],
            url=payload["source_url"],
            title=payload["title"],
            content=content,
            fetched_at=datetime(2026, 7, 15, tzinfo=UTC),
        )
        batch = await adapter.discover(SourceCheckpoint())
        fetched = await adapter.fetch(batch.records[0], SourceCheckpoint())

        assert fetched.content == content
        assert fetched.content_type == "application/json"
        assert payload["image_downloaded"] is False
        assert "image_url" not in payload
