"""Canonical source discovery, fetch, and document parsing protocols."""

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, TypeVar


@dataclass(frozen=True, slots=True)
class SourceCheckpoint:
    cursor: str | None = None
    etag: str | None = None
    last_modified: str | None = None
    consecutive_failures: int = 0
    circuit_open_until: datetime | None = None


@dataclass(frozen=True, slots=True)
class DiscoveryRecord:
    external_id: str
    url: str
    title: str
    published_at: datetime | None
    discovered_at: datetime


@dataclass(frozen=True, slots=True)
class DiscoveryBatch:
    records: tuple[DiscoveryRecord, ...]
    next_checkpoint: SourceCheckpoint


@dataclass(frozen=True, slots=True)
class FetchedAttachment:
    url: str
    filename: str
    content: bytes
    content_type: str


@dataclass(frozen=True, slots=True)
class FetchResult:
    url: str
    status_code: int
    content: bytes | None
    content_type: str | None
    etag: str | None
    last_modified: str | None
    fetched_at: datetime
    not_modified: bool = False
    attachments: tuple[FetchedAttachment, ...] = ()


ParsedDocument = TypeVar("ParsedDocument", covariant=True)


class SourceAdapter(Protocol):
    async def discover(self, checkpoint: SourceCheckpoint) -> DiscoveryBatch: ...

    async def fetch(self, record: DiscoveryRecord, checkpoint: SourceCheckpoint) -> FetchResult: ...


SourceConnector = SourceAdapter


class DocumentParser(Protocol[ParsedDocument]):
    def parse(
        self,
        content: bytes,
        *,
        document_version_id: str,
        canonical_url: str,
    ) -> ParsedDocument: ...
