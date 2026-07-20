from datetime import UTC, datetime
from hashlib import sha256
from uuid import UUID

import pytest
from srbg_api.acquisition.contracts import (
    DiscoveryBatch,
    DiscoveryRecord,
    FetchResult,
    SourceCheckpoint,
)
from srbg_worker.controlled_shadow import ControlledShadowCollector, ShadowAuthorization

NOW = datetime(2026, 7, 20, 8, 0, tzinfo=UTC)
SOURCE_ID = UUID("019f8500-0000-7000-8000-000000000001")
STREAM_ID = UUID("019f8500-0000-7000-8000-000000000002")
RUN_ID = UUID("019f8500-0000-7000-8000-000000000003")
VERSION_ID = UUID("019f8500-0000-7000-8000-000000000004")


class _Adapter:
    def __init__(self, *, content: bytes, content_type: str) -> None:
        self.content = content
        self.content_type = content_type

    async def discover(self, checkpoint: SourceCheckpoint) -> DiscoveryBatch:
        assert checkpoint == SourceCheckpoint()
        return DiscoveryBatch(
            records=(
                DiscoveryRecord(
                    external_id="fixture-1",
                    url="https://public.example.gov.cn/items/1",
                    title="铁路隧道安全监测更新",
                    published_at=NOW,
                    discovered_at=NOW,
                ),
            ),
            next_checkpoint=SourceCheckpoint(cursor="1"),
        )

    async def fetch(
        self, record: DiscoveryRecord, checkpoint: SourceCheckpoint
    ) -> FetchResult:
        assert checkpoint.cursor == "1"
        return FetchResult(
            url=record.url,
            request_url=record.url,
            status_code=200,
            content=self.content,
            content_type=self.content_type,
            etag=None,
            last_modified=None,
            fetched_at=NOW,
            response_sha256=sha256(self.content).hexdigest(),
        )


class _Gateway:
    def __init__(self, *, authorization_current: bool = True) -> None:
        self.authorization_current = authorization_current
        self.calls: list[str] = []
        self.raw_bytes: bytes | None = None

    async def authorization_is_current(self, authorization: ShadowAuthorization) -> bool:
        self.calls.append("authorize")
        return self.authorization_current

    async def persist_raw(
        self, authorization: ShadowAuthorization, fetched: FetchResult
    ) -> UUID:
        self.calls.append("raw")
        self.raw_bytes = fetched.content
        return UUID("019f8500-0000-7000-8000-000000000005")

    async def persist_document(
        self,
        authorization: ShadowAuthorization,
        *,
        raw_object_id: UUID,
        record: DiscoveryRecord,
        detected_mime: str,
    ) -> UUID:
        self.calls.append(f"document:{detected_mime}")
        return VERSION_ID

    async def enqueue_qualification(self, document_version_id: UUID) -> None:
        assert document_version_id == VERSION_ID
        self.calls.append("qualification")

    async def record_parse_failure(self, raw_object_id: UUID, reason_code: str) -> None:
        self.calls.append(f"parse_failed:{reason_code}")


def _authorization() -> ShadowAuthorization:
    return ShadowAuthorization(
        source_id=SOURCE_ID,
        source_stream_id=STREAM_ID,
        run_id=RUN_ID,
        authorized_at=NOW,
        expires_at=NOW.replace(hour=9),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("content", "declared", "detected"),
    [
        (b"<!doctype html><p>railway tunnel construction safety</p>", "text/plain", "text/html"),
        (b"%PDF-1.7\nfixture", "application/octet-stream", "application/pdf"),
        (b"<?xml version='1.0'?><rss><channel/></rss>", "text/plain", "application/rss+xml"),
    ],
)
async def test_shadow_collection_persists_raw_before_real_mime_and_handoff(
    content: bytes, declared: str, detected: str
) -> None:
    gateway = _Gateway()
    collector = ControlledShadowCollector(
        gateway=gateway,
        adapter=_Adapter(content=content, content_type=declared),
    )

    result = await collector.run(_authorization())

    assert result.document_version_ids == (VERSION_ID,)
    assert gateway.raw_bytes == content
    assert gateway.calls == [
        "authorize",
        "authorize",
        "raw",
        f"document:{detected}",
        "qualification",
    ]


@pytest.mark.asyncio
async def test_parse_failure_preserves_raw_and_never_hands_off() -> None:
    gateway = _Gateway()
    content = b"not a supported public document"
    collector = ControlledShadowCollector(
        gateway=gateway,
        adapter=_Adapter(content=content, content_type="text/html"),
    )

    result = await collector.run(_authorization())

    assert result.document_version_ids == ()
    assert gateway.raw_bytes == content
    assert gateway.calls == [
        "authorize",
        "authorize",
        "raw",
        "parse_failed:UNSUPPORTED_MIME",
    ]


@pytest.mark.asyncio
async def test_revocation_before_fetch_stops_without_raw_or_downstream_side_effects() -> None:
    gateway = _Gateway(authorization_current=False)
    collector = ControlledShadowCollector(
        gateway=gateway,
        adapter=_Adapter(content=b"<p>fixture</p>", content_type="text/html"),
    )

    result = await collector.run(_authorization())

    assert result.revoked is True
    assert gateway.calls == ["authorize"]
