"""Governed product adapters and deterministic offline fixture replay."""

from __future__ import annotations

from datetime import UTC, datetime
from hashlib import sha256
from typing import Protocol

from srbg_api.acquisition.contracts import (
    DiscoveryBatch,
    DiscoveryRecord,
    FetchResult,
    SourceCheckpoint,
)


class ProductHttpClient(Protocol):
    async def get(
        self, url: str, *, checkpoint: SourceCheckpoint, accept: str = "text/html"
    ) -> FetchResult: ...


class VendorProductAdapter:
    def __init__(
        self,
        *,
        external_id: str,
        url: str,
        title: str,
        source_active: bool,
        client: ProductHttpClient | None,
    ) -> None:
        self._record = DiscoveryRecord(
            external_id=external_id,
            url=url,
            title=title,
            published_at=None,
            discovered_at=datetime.now(UTC),
        )
        self._source_active = source_active
        self._client = client

    def _require_active(self) -> ProductHttpClient:
        if not self._source_active:
            raise RuntimeError(
                "live product acquisition requires server-computed ACTIVE source admission"
            )
        if self._client is None:
            raise RuntimeError("live product acquisition requires the shared resilient HTTP client")
        return self._client

    async def discover(self, checkpoint: SourceCheckpoint) -> DiscoveryBatch:
        self._require_active()
        if checkpoint.cursor == self._record.external_id:
            return DiscoveryBatch(records=(), next_checkpoint=checkpoint)
        return DiscoveryBatch(
            records=(self._record,),
            next_checkpoint=SourceCheckpoint(cursor=self._record.external_id),
        )

    async def fetch(self, record: DiscoveryRecord, checkpoint: SourceCheckpoint) -> FetchResult:
        client = self._require_active()
        if record.url != self._record.url:
            raise ValueError("product adapter refused an unapproved URL")
        return await client.get(record.url, checkpoint=checkpoint, accept="text/html")


class FixedProductFixtureAdapter:
    def __init__(
        self,
        *,
        external_id: str,
        url: str,
        title: str,
        content: bytes,
        fetched_at: datetime,
    ) -> None:
        self._record = DiscoveryRecord(
            external_id=external_id,
            url=url,
            title=title,
            published_at=None,
            discovered_at=fetched_at,
        )
        self._content = content
        self._etag = f'"sha256:{sha256(content).hexdigest()}"'
        self._fetched_at = fetched_at

    async def discover(self, checkpoint: SourceCheckpoint) -> DiscoveryBatch:
        if checkpoint.cursor == self._record.external_id:
            return DiscoveryBatch(records=(), next_checkpoint=checkpoint)
        return DiscoveryBatch(
            records=(self._record,),
            next_checkpoint=SourceCheckpoint(cursor=self._record.external_id),
        )

    async def fetch(self, record: DiscoveryRecord, checkpoint: SourceCheckpoint) -> FetchResult:
        if record.url != self._record.url:
            raise ValueError("fixture adapter refused an unapproved product URL")
        not_modified = checkpoint.etag == self._etag
        return FetchResult(
            url=record.url,
            status_code=304 if not_modified else 200,
            content=None if not_modified else self._content,
            content_type="application/json",
            etag=self._etag,
            last_modified=None,
            fetched_at=self._fetched_at,
            not_modified=not_modified,
        )
