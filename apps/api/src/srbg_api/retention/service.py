"""Fail-closed retention sequencing without copying evidence payloads."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from srbg_api.observability import RETENTION_RESULTS


@dataclass(frozen=True, slots=True)
class RetentionCandidate:
    execution_id: UUID
    source_id: UUID
    raw_object_id: UUID
    document_version_id: UUID | None
    policy_version_id: UUID
    object_key: str
    content_sha256: str
    byte_size: int
    mime: str
    legal_hold_active: bool
    unique_published_evidence: bool
    reason: str


class PublicationInvalidator(Protocol):
    async def invalidate_for_retention(self, document_version_id: UUID, *, reason: str) -> None: ...

    async def retention_invalidation_confirmed(self, document_version_id: UUID) -> bool: ...


class EvidenceEraser(Protocol):
    async def erase(self, object_key: str) -> None: ...


class RetentionRecorder(Protocol):
    async def record(
        self,
        candidate: RetentionCandidate,
        *,
        status: str,
        publication_invalidated: bool,
        erasure_method: str | None,
    ) -> None: ...


class RetentionService:
    """Enforce legal hold and publication invalidation before object erasure."""

    def __init__(
        self,
        *,
        publication: PublicationInvalidator,
        eraser: EvidenceEraser,
        recorder: RetentionRecorder,
    ) -> None:
        self._publication = publication
        self._eraser = eraser
        self._recorder = recorder

    async def execute(self, candidate: RetentionCandidate) -> str:
        if candidate.legal_hold_active:
            await self._recorder.record(
                candidate,
                status="BLOCKED_LEGAL_HOLD",
                publication_invalidated=False,
                erasure_method=None,
            )
            RETENTION_RESULTS.labels(outcome="BLOCKED_LEGAL_HOLD").inc()
            return "BLOCKED_LEGAL_HOLD"
        invalidated = False
        if candidate.unique_published_evidence:
            if candidate.document_version_id is None:
                await self._recorder.record(
                    candidate,
                    status="BLOCKED_UNIQUE_EVIDENCE",
                    publication_invalidated=False,
                    erasure_method=None,
                )
                RETENTION_RESULTS.labels(outcome="BLOCKED_UNIQUE_EVIDENCE").inc()
                return "BLOCKED_UNIQUE_EVIDENCE"
            await self._publication.invalidate_for_retention(
                candidate.document_version_id,
                reason=candidate.reason,
            )
            invalidated = await self._publication.retention_invalidation_confirmed(
                candidate.document_version_id
            )
            if not invalidated:
                await self._recorder.record(
                    candidate,
                    status="INVALIDATING",
                    publication_invalidated=False,
                    erasure_method=None,
                )
                RETENTION_RESULTS.labels(outcome="INVALIDATING").inc()
                return "INVALIDATING"
        await self._eraser.erase(candidate.object_key)
        await self._recorder.record(
            candidate,
            status="ERASED",
            publication_invalidated=invalidated,
            erasure_method="OBJECT_DELETE",
        )
        RETENTION_RESULTS.labels(outcome="ERASED").inc()
        return "ERASED"
