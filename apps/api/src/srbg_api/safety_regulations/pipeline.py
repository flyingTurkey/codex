"""One acquisition-to-review orchestration shared by API fixtures and Worker tasks."""

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal, Protocol
from uuid import UUID

from srbg_contracts import FixtureUploadResponse

from srbg_api.acquisition.contracts import (
    DocumentParser,
    FetchedAttachment,
    SourceAdapter,
    SourceCheckpoint,
)
from srbg_api.safety_regulations.parser import ParsedSafetyRegulation
from srbg_api.safety_regulations.scanner import (
    RuleBasedSemanticScanner,
    SemanticSafetyResult,
)

logger = logging.getLogger(__name__)


class SourceNotAdmitted(PermissionError):
    pass


@dataclass(frozen=True, slots=True)
class SourceAuthorization:
    source_id: UUID
    effective_active: bool


@dataclass(frozen=True, slots=True)
class RecordLease:
    record_id: UUID
    should_fetch: bool
    checkpoint: SourceCheckpoint = field(default_factory=SourceCheckpoint)


@dataclass(frozen=True, slots=True)
class IngestionRunResult:
    run_id: UUID
    discovered_records: int
    fetched_records: int
    created_items: int
    failed_records: int


class SourceAuthorizer(Protocol):
    async def authorize(self, source_id: UUID) -> SourceAuthorization: ...


class DocumentVault(Protocol):
    async def upload(
        self,
        source_id: UUID,
        *,
        content: bytes,
        filename: str,
        declared_mime: str,
        canonical_url: str,
        actor_id: UUID,
        request_id: str,
        acquired_at: datetime,
        admission_fixture: bool,
    ) -> FixtureUploadResponse: ...

    async def store_attachments(
        self,
        document_version_id: UUID,
        *,
        attachments: tuple[FetchedAttachment, ...],
        acquired_at: datetime,
    ) -> tuple[UUID, ...]: ...


class IngestionStore(Protocol):
    async def get_checkpoint(self, connector_id: UUID) -> SourceCheckpoint: ...

    async def start_run(
        self,
        *,
        connector_id: UUID,
        trigger: str,
        request_id: str,
    ) -> UUID: ...

    async def lease_record(
        self,
        *,
        run_id: UUID,
        connector_id: UUID,
        record: object,
    ) -> RecordLease: ...

    async def link_document(
        self,
        *,
        record_id: UUID,
        document_id: UUID,
        document_version_id: UUID,
        etag: str | None,
        last_modified: str | None,
    ) -> None: ...

    async def mark_not_modified(self, *, record_id: UUID) -> None: ...

    async def persist_parsed(
        self,
        *,
        record_id: UUID,
        source_id: UUID,
        document_id: UUID,
        document_version_id: UUID,
        parsed: ParsedSafetyRegulation,
        semantic_scan: SemanticSafetyResult,
        submitted_by: UUID,
    ) -> tuple[UUID, UUID]: ...

    async def fail_record(self, *, record_id: UUID, error_code: str) -> None: ...

    async def complete_run(
        self,
        *,
        run_id: UUID,
        checkpoint: SourceCheckpoint,
        status: str,
        discovered_count: int,
        fetched_count: int,
        failed_count: int,
    ) -> None: ...


class SafetyRegulationIngestionService:
    def __init__(
        self,
        *,
        authorizer: SourceAuthorizer,
        store: IngestionStore,
        document_vault: DocumentVault,
        parser: DocumentParser[ParsedSafetyRegulation],
        semantic_scanner: RuleBasedSemanticScanner,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._authorizer = authorizer
        self._store = store
        self._document_vault = document_vault
        self._parser = parser
        self._semantic_scanner = semantic_scanner
        self._now = now or (lambda: datetime.now(UTC))

    async def run(
        self,
        *,
        source_id: UUID,
        connector_id: UUID,
        adapter: SourceAdapter,
        actor_id: UUID,
        request_id: str,
        trigger: Literal["SCHEDULED", "MANUAL", "FIXTURE"],
    ) -> IngestionRunResult:
        authorization = await self._authorizer.authorize(source_id)
        if not authorization.effective_active:
            raise SourceNotAdmitted("source is not server-authorized for acquisition")

        checkpoint = await self._store.get_checkpoint(connector_id)
        run_id = await self._store.start_run(
            connector_id=connector_id,
            trigger=trigger,
            request_id=request_id,
        )
        if (
            checkpoint.circuit_open_until is not None
            and checkpoint.circuit_open_until > self._now()
        ):
            await self._store.complete_run(
                run_id=run_id,
                checkpoint=checkpoint,
                status="CIRCUIT_OPEN",
                discovered_count=0,
                fetched_count=0,
                failed_count=0,
            )
            return IngestionRunResult(
                run_id=run_id,
                discovered_records=0,
                fetched_records=0,
                created_items=0,
                failed_records=0,
            )
        try:
            batch = await adapter.discover(checkpoint)
        except Exception:
            await self._store.complete_run(
                run_id=run_id,
                checkpoint=checkpoint,
                status="FAILED",
                discovered_count=0,
                fetched_count=0,
                failed_count=1,
            )
            raise
        fetched_count = 0
        created_items = 0
        failed_count = 0

        for record in batch.records:
            lease = await self._store.lease_record(
                run_id=run_id,
                connector_id=connector_id,
                record=record,
            )
            if not lease.should_fetch:
                continue
            try:
                fetched = await adapter.fetch(record, lease.checkpoint)
                if fetched.not_modified:
                    await self._store.mark_not_modified(record_id=lease.record_id)
                    continue
                if fetched.content is None:
                    raise ValueError("fetched HTML response has no content")
                uploaded = await self._document_vault.upload(
                    source_id,
                    content=fetched.content,
                    filename=_source_filename(record.external_id, fetched.content_type),
                    declared_mime=(fetched.content_type or "text/html").split(";", 1)[0].strip(),
                    canonical_url=fetched.url,
                    actor_id=actor_id,
                    request_id=request_id,
                    acquired_at=fetched.fetched_at,
                    admission_fixture=False,
                )
                document = uploaded.document
                version = document.current_version
                await self._store.link_document(
                    record_id=lease.record_id,
                    document_id=document.id,
                    document_version_id=version.id,
                    etag=fetched.etag,
                    last_modified=fetched.last_modified,
                )
                if fetched.attachments:
                    await self._document_vault.store_attachments(
                        version.id,
                        attachments=fetched.attachments,
                        acquired_at=fetched.fetched_at,
                    )
                parsed = self._parser.parse(
                    fetched.content,
                    document_version_id=str(version.id),
                    canonical_url=fetched.url,
                )
                semantic_scan = self._semantic_scanner.scan(parsed.paragraphs)
                if not semantic_scan.passed:
                    raise ValueError("semantic safety scan quarantined the source document")
                await self._store.persist_parsed(
                    record_id=lease.record_id,
                    source_id=source_id,
                    document_id=document.id,
                    document_version_id=version.id,
                    parsed=parsed,
                    semantic_scan=semantic_scan,
                    submitted_by=actor_id,
                )
                fetched_count += 1
                if uploaded.version_created:
                    created_items += 1
            except Exception as exc:
                failed_count += 1
                logger.exception(
                    "safety regulation record processing failed",
                    extra={"fetch_record_id": str(lease.record_id)},
                )
                error_code = getattr(exc, "code", type(exc).__name__)
                await self._store.fail_record(
                    record_id=lease.record_id,
                    error_code=str(error_code),
                )

        await self._store.complete_run(
            run_id=run_id,
            checkpoint=batch.next_checkpoint,
            status="PARTIAL" if failed_count else "SUCCEEDED",
            discovered_count=len(batch.records),
            fetched_count=fetched_count,
            failed_count=failed_count,
        )
        return IngestionRunResult(
            run_id=run_id,
            discovered_records=len(batch.records),
            fetched_records=fetched_count,
            created_items=created_items,
            failed_records=failed_count,
        )


def _source_filename(external_id: str, content_type: str | None) -> str:
    media_type = (content_type or "").split(";", 1)[0].strip().lower()
    suffix = ".pdf" if media_type == "application/pdf" else ".html"
    return f"{external_id}{suffix}"
