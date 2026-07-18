"""Round 10 portal application service; no publication state changes live here."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from datetime import UTC, date, datetime
from typing import Literal, Protocol, cast
from uuid import UUID

from srbg_contracts import (
    CollectionSummary,
    DailyReport,
    EventSummary,
    FeedNotice,
    FeedPage,
    FingerprintResponse,
    ItemDetail,
    SearchContext,
)

from srbg_api.auth import Principal
from srbg_api.discovery.domain import CursorBindingError, CursorCodec, escape_spreadsheet_formula
from srbg_api.discovery.repository import PostgresPortalRepository, SearchHit
from srbg_api.identifiers import uuid7


class IntelligenceReader(Protocol):
    async def get_item(self, item_id: UUID) -> ItemDetail: ...

    async def get_event_summary_for_item(self, item_id: UUID) -> EventSummary: ...

    async def get_event_summary(self, event_id: UUID) -> EventSummary: ...

    async def search_events(self, query: str, *, limit: int) -> list[EventSummary]: ...


class EmbeddingProvider(Protocol):
    async def embed(self, text: str) -> Sequence[float]: ...


class PortalApplicationService:
    def __init__(
        self,
        *,
        repository: PostgresPortalRepository,
        intelligence: IntelligenceReader,
        cursor_signing_key: bytes,
        semantic_enabled: bool = False,
        embedding_provider: EmbeddingProvider | None = None,
        semantic_timeout_seconds: float = 0.3,
    ) -> None:
        self._repository = repository
        self._intelligence = intelligence
        self._cursor = CursorCodec(cursor_signing_key)
        self._semantic_enabled = semantic_enabled
        self._embedding_provider = embedding_provider
        self._semantic_timeout = semantic_timeout_seconds

    async def close(self) -> None:
        await self._repository.close()

    async def search(
        self,
        *,
        query: str,
        tokens: tuple[str, ...],
        domain: str | None,
        content_type: str | None,
        region: str | None,
        source_id: UUID | None,
        evidence_status: str | None,
        sort: str,
        cursor: str | None,
        limit: int,
        principal: Principal,
    ) -> FeedPage:
        binding = {
            "query": list(tokens),
            "domain": domain,
            "content_type": content_type,
            "region": region,
            "source_id": str(source_id) if source_id else None,
            "evidence_status": evidence_status,
            "sort": sort,
            "roles": sorted(role.value for role in principal.roles),
        }
        cursor_values = None if cursor is None else self._cursor.decode(cursor, binding=binding)
        embedding: Sequence[float] | None = None
        semantic_status: Literal["DISABLED", "ENABLED", "DEGRADED"] = "DISABLED"
        if self._semantic_enabled:
            semantic_status = "DEGRADED"
            if self._embedding_provider is not None:
                try:
                    embedding = await asyncio.wait_for(
                        self._embedding_provider.embed(" ".join(tokens)),
                        timeout=self._semantic_timeout,
                    )
                    if len(embedding) != 1536:
                        raise ValueError("embedding dimension must be 1536")
                    semantic_status = "ENABLED"
                except (TimeoutError, ValueError):
                    embedding = None
        projection_search = getattr(self._intelligence, "search_events", None)
        if projection_search is not None:
            items = await projection_search(query, limit=limit)
            return FeedPage(
                items=items,
                next_cursor=None,
                fingerprint="search:published-v1:event",
                generated_at=datetime.now(UTC),
                freshness="fresh",
                notices=[],
            )
        hits, next_values, generation = await self._repository.search(
            query=query,
            tokens=tokens,
            domain=domain,
            content_type=content_type,
            region=region,
            source_id=source_id,
            evidence_status=evidence_status,
            sort=sort,
            cursor_values=cursor_values,
            limit=limit,
            embedding=embedding,
        )
        items = await self._summaries_for_hits(hits, semantic_status=semantic_status)
        notices: list[FeedNotice] = []
        if semantic_status == "DEGRADED":
            notices.append(
                FeedNotice(
                    code="SEMANTIC_SEARCH_DEGRADED",
                    level="warning",
                    message="语义召回暂不可用, 当前结果来自精确编号和关键词检索。",
                )
            )
        next_cursor = (
            None
            if next_values is None
            else self._cursor.encode(sort_values=next_values, binding=binding)
        )
        return FeedPage(
            items=items,
            next_cursor=next_cursor,
            fingerprint=f"search:{generation}",
            generated_at=datetime.now(UTC),
            freshness="fresh",
            notices=notices,
        )

    async def _summaries_for_hits(
        self,
        hits: list[SearchHit],
        *,
        semantic_status: Literal["DISABLED", "ENABLED", "DEGRADED"],
    ) -> list[EventSummary]:
        items: list[EventSummary] = []
        for hit in hits:
            summary = await self._intelligence.get_event_summary_for_item(hit.item_id)
            items.append(
                summary.model_copy(
                    update={
                        "search_context": SearchContext(
                            match_kind=hit.match_kind,
                            matched_fields=list(hit.matched_fields),
                            matched_identifiers=list(hit.matched_identifiers),
                            semantic_status=semantic_status,
                        )
                    }
                )
            )
        return items

    async def list_saved(
        self,
        *,
        owner_id: UUID,
        collection_id: UUID | None,
        cursor: str | None,
        limit: int,
        principal: Principal,
    ) -> FeedPage:
        binding = {
            "owner_id": str(owner_id),
            "collection_id": str(collection_id) if collection_id else None,
            "roles": sorted(role.value for role in principal.roles),
        }
        values = None if cursor is None else self._cursor.decode(cursor, binding=binding)
        item_ids, next_values, generation = await self._repository.list_saved_ids(
            owner_id=owner_id,
            collection_id=collection_id,
            cursor_values=values,
            limit=limit,
        )
        items: list[EventSummary] = []
        for event_id in item_ids:
            summary = await self._intelligence.get_event_summary(event_id)
            items.append(summary.model_copy(update={"is_saved": True}))
        return FeedPage(
            items=items,
            next_cursor=None
            if next_values is None
            else self._cursor.encode(sort_values=next_values, binding=binding),
            fingerprint=f"saved:{owner_id}:{generation}",
            generated_at=datetime.now(UTC),
            freshness="fresh",
            notices=[],
        )

    async def save_item(
        self,
        *,
        owner_id: UUID,
        item_id: UUID,
        collection_id: UUID | None,
        idempotency_key: str,
    ) -> None:
        await self._repository.save_item(
            owner_id=owner_id,
            item_id=item_id,
            collection_id=collection_id,
            idempotency_key=idempotency_key,
            saved_at=datetime.now(UTC),
        )

    async def resolve_item_event(self, item_id: UUID) -> UUID:
        summary = await self._intelligence.get_event_summary_for_item(item_id)
        return summary.id

    async def remove_saved_item(
        self, *, owner_id: UUID, item_id: UUID, collection_id: UUID | None
    ) -> None:
        await self._repository.remove_saved_item(
            owner_id=owner_id, item_id=item_id, collection_id=collection_id
        )

    async def save_event(
        self,
        *,
        owner_id: UUID,
        event_id: UUID,
        collection_id: UUID | None,
        idempotency_key: str,
    ) -> None:
        await self._intelligence.get_event_summary(event_id)
        await self._repository.save_event(
            owner_id=owner_id,
            event_id=event_id,
            collection_id=collection_id,
            idempotency_key=idempotency_key,
            saved_at=datetime.now(UTC),
        )

    async def remove_saved_event(
        self, *, owner_id: UUID, event_id: UUID, collection_id: UUID | None
    ) -> None:
        await self._repository.remove_saved_event(
            owner_id=owner_id, event_id=event_id, collection_id=collection_id
        )

    async def list_collections(
        self, *, owner_id: UUID, include_archived: bool
    ) -> list[CollectionSummary]:
        return await self._repository.list_collections(
            owner_id=owner_id, include_archived=include_archived
        )

    async def create_collection(
        self, *, owner_id: UUID, name: str, idempotency_key: str
    ) -> CollectionSummary:
        return await self._repository.create_collection(
            collection_id=uuid7(),
            owner_id=owner_id,
            name=name.strip(),
            idempotency_key=idempotency_key,
            created_at=datetime.now(UTC),
        )

    async def patch_collection(
        self,
        *,
        owner_id: UUID,
        collection_id: UUID,
        name: str | None,
        archived: bool | None,
        expected_version: int,
    ) -> CollectionSummary:
        return await self._repository.patch_collection(
            owner_id=owner_id,
            collection_id=collection_id,
            name=None if name is None else name.strip(),
            archived=archived,
            expected_version=expected_version,
            updated_at=datetime.now(UTC),
        )

    @staticmethod
    def _include_draft(principal: Principal) -> bool:
        return principal.local_identity

    async def get_daily(self, *, report_date: date | None, principal: Principal) -> DailyReport:
        projection_daily = getattr(self._intelligence, "get_daily_report", None)
        if projection_daily is not None and not self._include_draft(principal):
            return cast(DailyReport, await projection_daily(report_date=report_date))
        return await self._repository.get_daily(
            report_date=report_date, include_draft=self._include_draft(principal)
        )

    async def get_report(self, *, report_id: UUID, principal: Principal) -> DailyReport:
        projection_daily = getattr(self._intelligence, "get_daily_report", None)
        if projection_daily is not None and not self._include_draft(principal):
            return cast(DailyReport, await projection_daily(report_id=report_id))
        return await self._repository.get_report(
            report_id=report_id, include_draft=self._include_draft(principal)
        )

    async def export_markdown(self, *, report_id: UUID, principal: Principal) -> str:
        report = await self.get_report(report_id=report_id, principal=principal)
        lines = [f"# 四川路桥行业日报 · {report.report_date.isoformat()}", ""]
        for section in report.sections:
            lines.extend((f"## {_markdown_cell(section.title)}", ""))
            if not section.items:
                lines.extend(("本节暂无条目。", ""))
                continue
            for item in section.items:
                title = _markdown_cell(escape_spreadsheet_formula(item.title))
                state = " (已撤回)" if item.current_state == "WITHDRAWN" else ""
                lines.append(f"- [{title}]({item.original_url}){state}")
                if item.summary is not None and item.current_state == "PUBLISHED":
                    lines.append(f"  - {_markdown_cell(item.summary)}")
            lines.append("")
        return "\n".join(lines).rstrip() + "\n"

    async def fingerprint(self, *, principal: Principal) -> FingerprintResponse:
        del principal
        return await self._repository.fingerprint()


def _markdown_cell(value: str) -> str:
    return " ".join(value.splitlines()).replace("|", "\\|").replace("[", "\\[").replace("]", "\\]")


__all__ = ["CursorBindingError", "PortalApplicationService"]
