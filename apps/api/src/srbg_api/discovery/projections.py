"""Idempotent publisher-role consumers for search and daily-digest projections."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from srbg_api.discovery.domain import normalize_identifier, tokenize_chinese_text


class PostgresDiscoveryProjectionWriter:
    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def close(self) -> None:
        await self._engine.dispose()

    async def apply_search(self, publication_id: UUID, generation: int, visible: bool) -> None:
        async with self._engine.begin() as connection:
            row = (
                (
                    await connection.execute(
                        text(
                            """
                        SELECT p.item_id, event.canonical_event_id AS event_id,
                          p.current_revision_id, p.status,
                          ii.channel, ii.item_type, ii.source_id, ii.risk_level,
                          ii.title, ii.activity_at, pr.snapshot
                        FROM publication p
                        JOIN intelligence_item ii ON ii.id = p.item_id
                        LEFT JOIN publication_revision pr ON pr.id = p.current_revision_id
                        LEFT JOIN event_identity_binding binding ON binding.item_id=p.item_id
                        LEFT JOIN event ON event.id=binding.event_id
                        WHERE p.id = :publication_id
                        """
                        ),
                        {"publication_id": publication_id},
                    )
                )
                .mappings()
                .first()
            )
            if row is None:
                raise RuntimeError("publication projection target was not found")
            item_id = cast(UUID, row["item_id"])
            event_id = cast(UUID | None, row["event_id"])
            if event_id is None:
                raise RuntimeError("publication has no stable Event identity")
            effective_visible = bool(
                visible
                and row["status"] == "PUBLISHED"
                and row["current_revision_id"] is not None
                and row["risk_level"] != "R4"
            )
            if not effective_visible:
                await connection.execute(
                    text(
                        "UPDATE search_projection SET visible = false, embedding = NULL, "
                        "generation = greatest(generation, :generation), indexed_at = :now "
                        "WHERE item_id = :item_id"
                    ),
                    {
                        "generation": generation,
                        "now": datetime.now(UTC),
                        "item_id": item_id,
                    },
                )
                return
            snapshot = row["snapshot"] if isinstance(row["snapshot"], dict) else {}
            entity_text = _flatten_named(snapshot.get("entities"))
            tag_text = _flatten_strings(snapshot.get("tags"))
            accepted_text = " ".join(
                value
                for value in (
                    str(snapshot.get("one_sentence_fact") or ""),
                    str(snapshot.get("summary") or ""),
                    entity_text,
                    tag_text,
                )
                if value
            )
            body_tokens = tokenize_chinese_text(accepted_text)
            region = snapshot.get("region_name") or snapshot.get("region")
            evidence_count = snapshot.get("evidence_count")
            evidence_status = (
                "VERIFIED" if isinstance(evidence_count, int) and evidence_count > 0 else None
            )
            now = datetime.now(UTC)
            await connection.execute(
                text(
                    """
                    INSERT INTO search_projection (
                      item_id, event_id, publication_revision_id, domain, content_type, source_id,
                      region, evidence_status, risk_level, title, entity_text, tag_text,
                      body_tokens, embedding, embedding_model, embedding_input_sha256,
                      visible, generation, activity_at, indexed_at
                    ) VALUES (
                      :item_id, :event_id, :revision_id, :domain, :content_type, :source_id,
                      :region, :evidence_status, :risk_level, :title, :entity_text, :tag_text,
                      :body_tokens, NULL, NULL, NULL, true, :generation, :activity_at, :now
                    )
                    ON CONFLICT (item_id) DO UPDATE SET
                      publication_revision_id = EXCLUDED.publication_revision_id,
                      event_id = EXCLUDED.event_id,
                      domain = EXCLUDED.domain, content_type = EXCLUDED.content_type,
                      source_id = EXCLUDED.source_id, region = EXCLUDED.region,
                      evidence_status = EXCLUDED.evidence_status,
                      risk_level = EXCLUDED.risk_level, title = EXCLUDED.title,
                      entity_text = EXCLUDED.entity_text, tag_text = EXCLUDED.tag_text,
                      body_tokens = EXCLUDED.body_tokens, embedding = NULL,
                      embedding_model = NULL, embedding_input_sha256 = NULL,
                      visible = true, generation = EXCLUDED.generation,
                      activity_at = EXCLUDED.activity_at, indexed_at = EXCLUDED.indexed_at
                    WHERE search_projection.generation <= EXCLUDED.generation
                    """
                ),
                {
                    "item_id": item_id,
                    "event_id": event_id,
                    "revision_id": row["current_revision_id"],
                    "domain": row["channel"],
                    "content_type": row["item_type"],
                    "source_id": row["source_id"],
                    "region": str(region)[:100] if region else None,
                    "evidence_status": evidence_status,
                    "risk_level": row["risk_level"],
                    "title": row["title"],
                    "entity_text": entity_text,
                    "tag_text": tag_text,
                    "body_tokens": body_tokens,
                    "generation": generation,
                    "activity_at": row["activity_at"],
                    "now": now,
                },
            )
            await connection.execute(
                text("DELETE FROM search_identifier WHERE item_id = :item_id"),
                {"item_id": item_id},
            )
            identifiers = list(
                (
                    await connection.execute(
                        text(
                            """
                            SELECT key_type AS kind, normalized_value,
                              normalized_value AS display_value
                            FROM item_identity_key
                            WHERE item_id = :item_id
                              AND key_type IN ('DOCUMENT_NUMBER','DOI','EXTERNAL_ID')
                            UNION ALL
                            SELECT CASE WHEN classification = 'STANDARD_OR_GUIDE'
                                THEN 'STANDARD_NUMBER' ELSE 'DOCUMENT_NUMBER' END,
                              document_number, document_number
                            FROM safety_regulation_profile WHERE item_id = :item_id
                            UNION ALL
                            SELECT 'DOI', normalized_doi, normalized_doi
                            FROM paper_profile
                            WHERE item_id = :item_id AND normalized_doi IS NOT NULL
                            """
                        ),
                        {"item_id": item_id},
                    )
                )
                .mappings()
                .all()
            )
            seen: set[tuple[str, str]] = set()
            for identifier in identifiers:
                normalized = normalize_identifier(str(identifier["normalized_value"]))
                key = (str(identifier["kind"]), normalized)
                if not normalized or key in seen:
                    continue
                seen.add(key)
                await connection.execute(
                    text(
                        "INSERT INTO search_identifier "
                        "(item_id, kind, normalized_value, display_value) "
                        "VALUES (:item_id, :kind, :normalized, :display) ON CONFLICT DO NOTHING"
                    ),
                    {
                        "item_id": item_id,
                        "kind": identifier["kind"],
                        "normalized": normalized,
                        "display": str(identifier["display_value"])[:2048],
                    },
                )

    async def invalidate_daily(self, publication_id: UUID, generation: int, visible: bool) -> None:
        del generation, visible
        async with self._engine.begin() as connection:
            await connection.execute(
                text(
                    """
                    UPDATE daily_report dr SET requires_regeneration = true,
                      version = version + 1
                    WHERE dr.status = 'DRAFT' AND EXISTS (
                      SELECT 1 FROM daily_report_item dri
                      JOIN publication p ON p.item_id = dri.item_id
                      WHERE dri.report_id = dr.id AND p.id = :publication_id
                    )
                    """
                ),
                {"publication_id": publication_id},
            )


def _flatten_strings(value: Any) -> str:
    if isinstance(value, list):
        return " ".join(str(entry) for entry in value if isinstance(entry, (str, int)))[:10000]
    return ""


def _flatten_named(value: Any) -> str:
    if not isinstance(value, list):
        return ""
    names: list[str] = []
    for entry in value:
        if isinstance(entry, dict) and isinstance(entry.get("name"), str):
            names.append(entry["name"])
        elif isinstance(entry, str):
            names.append(entry)
    return " ".join(names)[:10000]
