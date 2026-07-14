"""Deterministic discovery rules for the admitted MEM HTML regulations list."""

import re
from datetime import UTC, datetime
from html.parser import HTMLParser
from urllib.parse import urljoin

from srbg_api.acquisition.contracts import (
    DiscoveryBatch,
    DiscoveryRecord,
    FetchResult,
    SourceCheckpoint,
)
from srbg_api.acquisition.http import ResilientHttpClient

_EXTERNAL_ID = re.compile(r"/(t\d{8}_\d+)\.shtml$")
_DATE_IN_ID = re.compile(r"t(\d{4})(\d{2})(\d{2})_")


class _ListParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._in_title_paragraph = False
        self._active_href: str | None = None
        self._active_text: list[str] = []
        self.links: list[tuple[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag == "p" and "bt" in (values.get("class") or "").split():
            self._in_title_paragraph = True
        elif tag == "a" and self._in_title_paragraph:
            self._active_href = values.get("href")
            self._active_text = []

    def handle_data(self, data: str) -> None:
        if self._active_href is not None:
            self._active_text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._active_href is not None:
            title = _normalize_text("".join(self._active_text))
            if title:
                self.links.append((self._active_href, title))
            self._active_href = None
            self._active_text = []
        elif tag == "p" and self._in_title_paragraph:
            self._in_title_paragraph = False


class MemSafetyRegulationAdapter:
    """MEM adapter rules; network transport is injected by acquisition orchestration."""

    def __init__(
        self,
        client: ResilientHttpClient | None = None,
        *,
        list_url: str = "https://www.mem.gov.cn/gk/zfxxgkpt/fdzdgknr/gz11/index.shtml",
    ) -> None:
        self._client = client
        self._list_url = list_url

    async def discover(self, checkpoint: SourceCheckpoint) -> DiscoveryBatch:
        if self._client is None:
            raise RuntimeError("live MEM adapter requires an acquisition HTTP client")
        result = await self._client.get(self._list_url, checkpoint=checkpoint)
        if result.not_modified:
            return DiscoveryBatch(records=(), next_checkpoint=checkpoint)
        if result.content is None:
            raise OSError("MEM list response has no HTML body")
        records = self.discover_from_html(
            result.content,
            list_url=result.url,
            discovered_at=result.fetched_at,
        )
        return DiscoveryBatch(
            records=tuple(records),
            next_checkpoint=SourceCheckpoint(
                cursor=records[0].external_id if records else checkpoint.cursor,
                etag=result.etag,
                last_modified=result.last_modified,
            ),
        )

    async def fetch(
        self,
        record: DiscoveryRecord,
        checkpoint: SourceCheckpoint,
    ) -> FetchResult:
        if self._client is None:
            raise RuntimeError("live MEM adapter requires an acquisition HTTP client")
        return await self._client.get(record.url, checkpoint=checkpoint)

    def discover_from_html(
        self,
        content: bytes,
        *,
        list_url: str,
        discovered_at: datetime,
    ) -> list[DiscoveryRecord]:
        parser = _ListParser()
        parser.feed(content.decode("utf-8"))
        records: list[DiscoveryRecord] = []
        seen: set[str] = set()
        for href, title in parser.links:
            canonical_url = urljoin(list_url, href)
            external_match = _EXTERNAL_ID.search(canonical_url)
            if external_match is None:
                continue
            external_id = external_match.group(1)
            if external_id in seen:
                continue
            seen.add(external_id)
            date_match = _DATE_IN_ID.match(external_id)
            published_at = None
            if date_match is not None:
                year, month, day = (int(part) for part in date_match.groups())
                published_at = datetime(year, month, day, tzinfo=UTC)
            records.append(
                DiscoveryRecord(
                    external_id=external_id,
                    url=canonical_url,
                    title=title,
                    published_at=published_at,
                    discovered_at=discovered_at,
                )
            )
        return records


class FixedMemFixtureAdapter:
    """Approved deterministic replay of one official list/detail snapshot pair."""

    def __init__(
        self,
        *,
        list_content: bytes,
        detail_content: bytes,
        list_etag: str,
        detail_etag: str,
        detail_url: str,
        fetched_at: datetime,
    ) -> None:
        self._list_content = list_content
        self._detail_content = detail_content
        self._list_etag = list_etag
        self._detail_etag = detail_etag
        self._detail_url = detail_url
        self._fetched_at = fetched_at
        self._rules = MemSafetyRegulationAdapter()

    async def discover(self, checkpoint: SourceCheckpoint) -> DiscoveryBatch:
        if checkpoint.etag == self._list_etag:
            return DiscoveryBatch(records=(), next_checkpoint=checkpoint)
        records = self._rules.discover_from_html(
            self._list_content,
            list_url="https://www.mem.gov.cn/gk/zfxxgkpt/fdzdgknr/gz11/index_1.shtml",
            discovered_at=self._fetched_at,
        )
        selected = tuple(record for record in records if record.url == self._detail_url)
        if len(selected) != 1:
            raise ValueError("fixed MEM list fixture does not contain the approved detail URL")
        return DiscoveryBatch(
            records=selected,
            next_checkpoint=SourceCheckpoint(
                cursor=selected[0].external_id,
                etag=self._list_etag,
            ),
        )

    async def fetch(
        self,
        record: DiscoveryRecord,
        checkpoint: SourceCheckpoint,
    ) -> FetchResult:
        if record.url != self._detail_url:
            raise ValueError("fixture adapter refused an unapproved document URL")
        not_modified = checkpoint.etag == self._detail_etag
        return FetchResult(
            url=record.url,
            status_code=304 if not_modified else 200,
            content=None if not_modified else self._detail_content,
            content_type="text/html",
            etag=self._detail_etag,
            last_modified=None,
            fetched_at=self._fetched_at,
            not_modified=not_modified,
        )


def _normalize_text(value: str) -> str:
    return " ".join(value.replace("\xa0", " ").split())
