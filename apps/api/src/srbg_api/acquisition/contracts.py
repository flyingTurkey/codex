"""Canonical source discovery, fetch, and document parsing protocols."""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol, TypeVar, runtime_checkable
from uuid import UUID


class ExecutionDomain(StrEnum):
    """Hard isolation boundary for evidence created by a connector run."""

    FIXTURE = "FIXTURE"
    TRIAL = "TRIAL"
    PRODUCTION = "PRODUCTION"


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
    source_modified_at: datetime | None = None


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
    request_url: str | None = None
    redirect_chain: tuple[str, ...] = ()
    response_sha256: str | None = None


@dataclass(frozen=True, slots=True)
class RawObject:
    """Immutable metadata for bytes persisted before any parsing occurs."""

    id: UUID
    execution_domain: ExecutionDomain
    request_url: str
    final_url: str
    status_code: int
    content_type: str | None
    content_sha256: str
    response_sha256: str
    byte_size: int
    etag: str | None
    last_modified: str | None
    fetched_at: datetime
    redirect_chain: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class DocumentVersion:
    """A domain-scoped READY projection backed by exactly one raw object."""

    id: UUID
    raw_object_id: UUID
    execution_domain: ExecutionDomain
    canonical_url: str
    version_number: int
    status: str
    content_sha256: str
    discovered_at: datetime
    published_at: datetime | None
    source_modified_at: datetime | None = None


ParsedDocument = TypeVar("ParsedDocument", covariant=True)


@runtime_checkable
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
