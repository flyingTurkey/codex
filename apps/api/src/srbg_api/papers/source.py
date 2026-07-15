"""OpenAlex discovery and Crossref DOI enrichment through the shared client."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol
from urllib.parse import quote, urlencode

from srbg_api.acquisition.contracts import (
    DiscoveryBatch,
    DiscoveryRecord,
    FetchResult,
    SourceCheckpoint,
)
from srbg_api.papers.domain import normalize_doi


class JsonHttpClient(Protocol):
    async def get(
        self, url: str, *, checkpoint: SourceCheckpoint, accept: str = "text/html"
    ) -> FetchResult: ...


OPENALEX_SELECT = (
    "id,doi,title,type,publication_year,publication_date,is_retracted,authorships,"
    "primary_location,best_oa_location,open_access,biblio,keywords,topics,related_works"
)


class OpenAlexPaperAdapter:
    def __init__(
        self,
        *,
        client: JsonHttpClient,
        api_key: str | None,
        contact: str = "data-platform@srbg.local",
    ) -> None:
        self._client = client
        self._api_key = api_key.strip() if api_key else None
        self._contact = contact

    async def discover(self, checkpoint: SourceCheckpoint) -> DiscoveryBatch:
        if not self._api_key:
            raise RuntimeError("OPENALEX_API_KEY is required for live OpenAlex acquisition")
        cursor = checkpoint.cursor if checkpoint.cursor is not None else "*"
        query = urlencode(
            {
                "cursor": cursor,
                "per-page": 100,
                "select": OPENALEX_SELECT,
                "api_key": self._api_key,
            }
        )
        url = f"https://api.openalex.org/works?{query}"
        result = await self._client.get(
            url, checkpoint=SourceCheckpoint(), accept="application/json"
        )
        payload = _json_object(result)
        results = payload.get("results")
        meta = payload.get("meta")
        if not isinstance(results, list) or not isinstance(meta, dict):
            raise ValueError("OpenAlex response is missing results or meta")
        now = result.fetched_at
        records: list[DiscoveryRecord] = []
        for work in results:
            if not isinstance(work, dict) or not isinstance(work.get("id"), str):
                raise ValueError("OpenAlex work is missing an id")
            external_id = str(work["id"]).rstrip("/").split("/")[-1]
            title = work.get("title")
            if not isinstance(title, str) or not title.strip():
                raise ValueError("OpenAlex work is missing a title")
            published = _date(work.get("publication_date"))
            records.append(
                DiscoveryRecord(
                    external_id=external_id,
                    url=f"https://api.openalex.org/works/{quote(external_id)}",
                    title=title.strip(),
                    published_at=published,
                    discovered_at=now,
                )
            )
        next_cursor = meta.get("next_cursor")
        if next_cursor is not None and not isinstance(next_cursor, str):
            raise ValueError("OpenAlex next_cursor must be a string or null")
        return DiscoveryBatch(
            records=tuple(records), next_checkpoint=SourceCheckpoint(cursor=next_cursor)
        )

    async def fetch(self, record: DiscoveryRecord, checkpoint: SourceCheckpoint) -> FetchResult:
        if not self._api_key:
            raise RuntimeError("OPENALEX_API_KEY is required for live OpenAlex acquisition")
        separator = "&" if "?" in record.url else "?"
        return await self._client.get(
            f"{record.url}{separator}api_key={quote(self._api_key)}",
            checkpoint=checkpoint,
            accept="application/json",
        )


@dataclass(frozen=True, slots=True)
class CrossrefRelation:
    relation_type: str
    target_doi: str
    updated_at: datetime | None


@dataclass(frozen=True, slots=True)
class CrossrefLookup:
    doi: str
    title: str | None
    relations: tuple[CrossrefRelation, ...]
    raw: bytes


class CrossrefPaperAdapter:
    def __init__(self, *, client: JsonHttpClient, contact: str) -> None:
        self._client = client
        self._contact = contact

    async def lookup(self, doi: str) -> CrossrefLookup:
        normalized = normalize_doi(doi)
        if normalized is None:
            raise ValueError("DOI is required")
        query = urlencode({"mailto": self._contact})
        url = f"https://api.crossref.org/works/{quote(normalized, safe='')}?{query}"
        fetched = await self._client.get(
            url, checkpoint=SourceCheckpoint(), accept="application/json"
        )
        payload = _json_object(fetched)
        message = payload.get("message")
        if not isinstance(message, dict):
            raise ValueError("Crossref response is missing message")
        response_doi = normalize_doi(str(message.get("DOI", normalized)))
        if response_doi is None:
            raise ValueError("Crossref response is missing DOI")
        title_value = message.get("title")
        title = title_value[0] if isinstance(title_value, list) and title_value else None
        relations: list[CrossrefRelation] = []
        for value in message.get("update-to", []):
            if not isinstance(value, dict) or not value.get("DOI"):
                continue
            relation = _crossref_relation(str(value.get("type", "update")))
            target = normalize_doi(str(value["DOI"]))
            updated = value.get("updated")
            updated_at = _datetime(updated.get("date-time")) if isinstance(updated, dict) else None
            if target:
                relations.append(CrossrefRelation(relation, target, updated_at))
        return CrossrefLookup(response_doi, title, tuple(relations), fetched.content or b"")


def _crossref_relation(value: str) -> str:
    normalized = value.casefold()
    if "retract" in normalized:
        return "RETRACTS"
    if "correct" in normalized or "errat" in normalized:
        return "CORRECTS"
    return "SUPERSEDES"


def _json_object(result: FetchResult) -> dict[str, object]:
    if result.content_type is None or "json" not in result.content_type.casefold():
        raise ValueError("academic API response must be JSON")
    if result.content is None:
        raise ValueError("academic API response body is empty")
    payload = json.loads(result.content)
    if not isinstance(payload, dict):
        raise ValueError("academic API response must be an object")
    return payload


def _date(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value).replace(tzinfo=UTC)
    except ValueError:
        return None


def _datetime(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
