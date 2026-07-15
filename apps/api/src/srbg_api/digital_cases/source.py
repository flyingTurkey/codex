"""Approved Round05 PDF source adapters and deterministic fixture replay."""

from datetime import UTC, datetime

from srbg_api.acquisition.contracts import (
    DiscoveryBatch,
    DiscoveryRecord,
    FetchResult,
    SourceCheckpoint,
)
from srbg_api.acquisition.http import ResilientHttpClient


class _DirectPdfAdapter:
    def __init__(
        self,
        *,
        external_id: str,
        url: str,
        title: str,
        published_at: datetime,
        client: ResilientHttpClient | None,
    ) -> None:
        self._external_id = external_id
        self._url = url
        self._title = title
        self._published_at = published_at
        self._client = client

    async def discover(self, checkpoint: SourceCheckpoint) -> DiscoveryBatch:
        if self._client is None:
            raise RuntimeError("live digital-case adapter requires an acquisition HTTP client")
        if checkpoint.cursor == self._external_id:
            return DiscoveryBatch(records=(), next_checkpoint=checkpoint)
        now = datetime.now(UTC)
        record = DiscoveryRecord(
            external_id=self._external_id,
            url=self._url,
            title=self._title,
            published_at=self._published_at,
            discovered_at=now,
        )
        return DiscoveryBatch(
            records=(record,),
            next_checkpoint=SourceCheckpoint(cursor=self._external_id),
        )

    async def fetch(self, record: DiscoveryRecord, checkpoint: SourceCheckpoint) -> FetchResult:
        if self._client is None:
            raise RuntimeError("live digital-case adapter requires an acquisition HTTP client")
        if record.url != self._url:
            raise ValueError("digital-case adapter refused an unapproved URL")
        return await self._client.get(record.url, checkpoint=checkpoint)


class MotDigitalCaseAdapter(_DirectPdfAdapter):
    def __init__(self, client: ResilientHttpClient | None = None) -> None:
        super().__init__(
            external_id="mot-pujiang-rural-road-digitalization",
            url=(
                "https://zizhan.mot.gov.cn/sj2019/gongluj/sihaoncl/"
                "dianxingal/202311/P020250627753815314372.pdf"
            ),
            title="打造智慧交通 赋能蒲江农村公路现代化建设",
            published_at=datetime(2023, 11, 20, tzinfo=UTC),
            client=client,
        )


class ShudaoDigitalCaseAdapter(_DirectPdfAdapter):
    def __init__(self, client: ResilientHttpClient | None = None) -> None:
        super().__init__(
            external_id="shudao-smart-beam-factory-2",
            url="https://www.shudaojt.com/public/uploads/files/2022/03/20220310164807146.pdf",
            title="智慧梁厂2.0",
            published_at=datetime(2022, 3, 10, tzinfo=UTC),
            client=client,
        )


class FixedDigitalCaseFixtureAdapter:
    """Offline short-excerpt fixture; full source PDFs remain private evidence."""

    def __init__(
        self,
        *,
        external_id: str,
        url: str,
        title: str,
        content: bytes,
        etag: str,
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
        self._etag = etag
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
            raise ValueError("fixture adapter refused an unapproved document URL")
        not_modified = checkpoint.etag == self._etag
        return FetchResult(
            url=record.url,
            status_code=304 if not_modified else 200,
            content=None if not_modified else self._content,
            content_type="application/pdf",
            etag=self._etag,
            last_modified=None,
            fetched_at=self._fetched_at,
            not_modified=not_modified,
        )
