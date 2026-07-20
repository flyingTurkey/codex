"""Controlled SourceAdapter runner that preserves raw bytes before interpretation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from srbg_api.acquisition.contracts import FetchResult, SourceAdapter, SourceCheckpoint
from srbg_api.observability import SOURCE_SHADOW_COLLECTION


@dataclass(frozen=True, slots=True)
class ShadowAuthorization:
    source_id: UUID
    source_stream_id: UUID
    run_id: UUID
    authorized_at: datetime
    expires_at: datetime

    def __post_init__(self) -> None:
        if self.authorized_at.tzinfo is None or self.expires_at.tzinfo is None:
            raise ValueError("shadow authorization times must include timezone")
        if self.expires_at <= self.authorized_at:
            raise ValueError("shadow authorization expiry must follow authorization")


@dataclass(frozen=True, slots=True)
class ShadowCollectionResult:
    document_version_ids: tuple[UUID, ...]
    revoked: bool
    discovered_count: int
    raw_count: int
    parse_failure_count: int


class ShadowGateway(Protocol):
    async def authorization_is_current(self, authorization: ShadowAuthorization) -> bool: ...

    async def persist_raw(
        self, authorization: ShadowAuthorization, fetched: FetchResult
    ) -> UUID: ...

    async def persist_document(
        self,
        authorization: ShadowAuthorization,
        *,
        raw_object_id: UUID,
        record: object,
        detected_mime: str,
    ) -> UUID: ...

    async def enqueue_qualification(self, document_version_id: UUID) -> None: ...

    async def record_parse_failure(self, raw_object_id: UUID, reason_code: str) -> None: ...


class ControlledShadowCollector:
    """Run one already-authorized stream and hand off only durable document IDs."""

    def __init__(self, *, gateway: ShadowGateway, adapter: SourceAdapter) -> None:
        self._gateway = gateway
        self._adapter = adapter

    async def run(self, authorization: ShadowAuthorization) -> ShadowCollectionResult:
        if not await self._gateway.authorization_is_current(authorization):
            SOURCE_SHADOW_COLLECTION.labels(outcome="revoked", document_kind="none").inc()
            return ShadowCollectionResult((), True, 0, 0, 0)
        batch = await self._adapter.discover(SourceCheckpoint())
        versions: list[UUID] = []
        raw_count = 0
        parse_failures = 0
        for record in batch.records:
            if not await self._gateway.authorization_is_current(authorization):
                SOURCE_SHADOW_COLLECTION.labels(outcome="revoked", document_kind="none").inc()
                return ShadowCollectionResult(
                    tuple(versions), True, len(batch.records), raw_count, parse_failures
                )
            fetched = await self._adapter.fetch(record, batch.next_checkpoint)
            if fetched.not_modified:
                continue
            raw_object_id = await self._gateway.persist_raw(authorization, fetched)
            raw_count += 1
            detected_mime = detect_public_document_mime(fetched.content or b"")
            if detected_mime is None:
                parse_failures += 1
                await self._gateway.record_parse_failure(raw_object_id, "UNSUPPORTED_MIME")
                SOURCE_SHADOW_COLLECTION.labels(
                    outcome="parse_failed", document_kind="unknown"
                ).inc()
                continue
            version_id = await self._gateway.persist_document(
                authorization,
                raw_object_id=raw_object_id,
                record=record,
                detected_mime=detected_mime,
            )
            versions.append(version_id)
            await self._gateway.enqueue_qualification(version_id)
            SOURCE_SHADOW_COLLECTION.labels(
                outcome="handed_off", document_kind=_metric_document_kind(detected_mime)
            ).inc()
        return ShadowCollectionResult(
            tuple(versions), False, len(batch.records), raw_count, parse_failures
        )


def detect_public_document_mime(content: bytes) -> str | None:
    value = content.lstrip()
    lowered = value[:512].lower()
    if value.startswith(b"%PDF-"):
        return "application/pdf"
    if lowered.startswith((b"<!doctype html", b"<html", b"<p", b"<article")):
        return "text/html"
    if lowered.startswith(b"<?xml") and (b"<rss" in lowered or b"<feed" in lowered):
        return "application/rss+xml"
    if lowered.startswith((b"<rss", b"<feed")):
        return "application/rss+xml"
    return None


def _metric_document_kind(mime_type: str) -> str:
    return {
        "text/html": "html",
        "application/pdf": "pdf",
        "application/rss+xml": "rss",
    }.get(mime_type, "unknown")
