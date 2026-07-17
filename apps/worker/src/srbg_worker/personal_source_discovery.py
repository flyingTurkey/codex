"""PERS-05 free discovery and quota-bound personal auto enable orchestration."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from html import unescape
from typing import Protocol
from urllib.parse import urlsplit
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine
from srbg_api.identifiers import uuid7

from srbg_worker.source_discovery import (
    DISCOVERY_ACTOR_ID,
    PublicDiscoveryChannel,
    PublicDiscoverySeed,
    RegistrationOutcome,
    VerifiedDiscoveryTarget,
)

MAX_AUTO_ENABLE_PER_RUN = 20
MAX_EXISTING_SCORE_BATCH = 100
_URL_PATTERN = re.compile(
    rb"(?:href\s*=\s*[\"']|<loc>|<link>)(https?://[^<\"'\s]+)",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class AutoEnableCandidate:
    source_id: UUID
    total_score: int
    first_discovered_at: datetime

    def __post_init__(self) -> None:
        if not 70 <= self.total_score <= 100:
            raise ValueError("auto-enable candidate score must be between 70 and 100")
        if self.first_discovered_at.tzinfo is None:
            raise ValueError("first discovery time must be timezone-aware")

    def sort_key(self) -> tuple[int, datetime, int]:
        return (-self.total_score, self.first_discovered_at, self.source_id.int)


@dataclass(frozen=True, slots=True)
class AutoEnableOutcome:
    considered: int
    enabled: int
    deferred: int


class AutoEnableGateway(Protocol):
    async def list_eligible(self, *, limit: int) -> tuple[AutoEnableCandidate, ...]: ...

    async def try_auto_enable(self, source_id: UUID, *, now: datetime) -> bool: ...


class PersonalAutoEnableExecutor:
    def __init__(self, gateway: AutoEnableGateway) -> None:
        self._gateway = gateway

    async def run(self, *, now: datetime) -> AutoEnableOutcome:
        if now.tzinfo is None:
            raise ValueError("auto-enable time must be timezone-aware")
        rows = await self._gateway.list_eligible(limit=101)
        ordered = sorted(rows, key=AutoEnableCandidate.sort_key)
        enabled = 0
        for row in ordered:
            if enabled >= MAX_AUTO_ENABLE_PER_RUN:
                break
            if await self._gateway.try_auto_enable(row.source_id, now=now):
                enabled += 1
        return AutoEnableOutcome(
            considered=len(ordered),
            enabled=enabled,
            deferred=max(0, len(ordered) - enabled),
        )


class PostgresAutoEnableGateway:
    """Calls the database-owned transaction that rechecks sticky and current evidence."""

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def discovery_enabled(self) -> bool:
        async with self._engine.connect() as connection:
            value = await connection.scalar(
                text(
                    "SELECT automation_enabled FROM personal_automation_setting "
                    "WHERE singleton_slot=1"
                )
            )
        return value is True

    async def list_eligible(self, *, limit: int) -> tuple[AutoEnableCandidate, ...]:
        async with self._engine.connect() as connection:
            rows = (
                (
                    await connection.execute(
                        text(
                            """
                            SELECT score.source_id,score.total_score,
                              COALESCE(MIN(occurrence.first_discovered_at),source.created_at)
                                AS first_discovered_at
                            FROM source_auto_score_snapshot score
                            JOIN source ON source.id=score.source_id
                            LEFT JOIN discovery_occurrence occurrence
                              ON occurrence.source_id=source.id
                            WHERE score.version=(
                              SELECT MAX(latest.version) FROM source_auto_score_snapshot latest
                              WHERE latest.source_id=score.source_id
                            ) AND score.auto_enable_eligible AND score.total_score>=70
                              AND score.rule_version='personal-source-auto-score-v1'
                              AND source.enabled=false AND source.manual_disabled_at IS NULL
                            GROUP BY score.source_id,score.total_score,source.created_at
                            ORDER BY score.total_score DESC,first_discovered_at,score.source_id
                            LIMIT :limit
                            """
                        ),
                        {"limit": limit},
                    )
                )
                .mappings()
                .all()
            )
        return tuple(
            AutoEnableCandidate(
                source_id=row["source_id"],
                total_score=row["total_score"],
                first_discovered_at=row["first_discovered_at"],
            )
            for row in rows
        )

    async def try_auto_enable(self, source_id: UUID, *, now: datetime) -> bool:
        async with self._engine.begin() as connection:
            enabled = await connection.scalar(
                text("SELECT auto_enable_personal_source(:source,:event,:outbox,:now)"),
                {
                    "source": source_id,
                    "event": uuid7(),
                    "outbox": uuid7(),
                    "now": now,
                },
            )
        return enabled is True


async def queue_existing_source_scoring(engine: AsyncEngine, *, now: datetime) -> dict[str, int]:
    """Advance migration-enqueued sources without performing network I/O in migration."""

    queued_profiles = 0
    queued_probes = 0
    deferred = 0
    async with engine.begin() as connection:
        rows = (
            (
                await connection.execute(
                    text(
                        """
                        SELECT run.id AS run_id,source.id AS source_id,
                          COALESCE(source.normalized_origin,source.base_url) AS url,
                          EXISTS(SELECT 1 FROM stream_probe_run probe
                            WHERE probe.source_id=source.id AND probe.status='SUCCEEDED'
                            AND jsonb_array_length(probe.capture_manifest)>0) has_evidence
                        FROM source_auto_score_run run
                        JOIN source ON source.id=run.source_id
                        WHERE run.status IN ('QUEUED','DEFERRED') AND run.next_attempt_at<=:now
                        ORDER BY source.created_at,source.id LIMIT :limit
                        FOR UPDATE OF run SKIP LOCKED
                        """
                    ),
                    {"now": now, "limit": MAX_EXISTING_SCORE_BATCH},
                )
            )
            .mappings()
            .all()
        )
        for row in rows:
            if row["has_evidence"]:
                await connection.execute(
                    text(
                        "INSERT INTO source_profile_run(id,source_id,status,next_attempt_at,"
                        "created_at,updated_at) VALUES(:id,:source,'QUEUED',:now,:now,:now) "
                        "ON CONFLICT(source_id) WHERE status IN ('QUEUED','RUNNING') DO NOTHING"
                    ),
                    {"id": uuid7(), "source": row["source_id"], "now": now},
                )
                await connection.execute(
                    text(
                        "UPDATE source_auto_score_run SET status='DEFERRED',"
                        "next_attempt_at=:next,updated_at=:now WHERE id=:id"
                    ),
                    {"next": now.replace(microsecond=0), "now": now, "id": row["run_id"]},
                )
                queued_profiles += 1
                continue
            origin = _safe_origin(str(row["url"]))
            if origin is None or not await connection.scalar(
                text("SELECT reserve_personal_probe_budget(:now)"), {"now": now}
            ):
                await connection.execute(
                    text(
                        "UPDATE source_auto_score_run SET status='DEFERRED',"
                        "next_attempt_at=:now+interval '6 hours',updated_at=:now WHERE id=:id"
                    ),
                    {"now": now, "id": row["run_id"]},
                )
                deferred += 1
                continue
            host = urlsplit(origin).hostname
            if host is None:
                deferred += 1
                continue
            stream_id = await connection.scalar(
                text(
                    "SELECT id FROM source_stream WHERE source_id=:source "
                    "ORDER BY created_at,id LIMIT 1"
                ),
                {"source": row["source_id"]},
            )
            if stream_id is None:
                stream_id = uuid7()
                await connection.execute(
                    text(
                        "INSERT INTO source_stream(id,source_id,stream_key,name,canonical_url,"
                        "authorization_boundary,status,rule_version,automatically_managed,"
                        "created_at,updated_at,stream_type,allowed_hosts,discovery_method) "
                        "VALUES(:id,:source,:key,:origin,:origin,:host,'PROBING',"
                        "'personal-source-probe-v1',true,:now,:now,'UNKNOWN',"
                        "ARRAY[CAST(:host AS varchar(253))],'EXISTING_SOURCE')"
                    ),
                    {
                        "id": stream_id,
                        "source": row["source_id"],
                        "key": "RESCORE_" + sha256(origin.encode()).hexdigest()[:20],
                        "origin": origin,
                        "host": host,
                        "now": now,
                    },
                )
            await connection.execute(
                text(
                    "INSERT INTO stream_probe_run(id,source_id,stream_id,requested_url,"
                    "normalized_url,normalized_origin,input_kind,status,requested_by,"
                    "request_id,created_at,updated_at) VALUES(:id,:source,:stream,:origin,"
                    ":origin,:origin,'UNKNOWN','QUEUED',:actor,'pers05-existing-rescore',"
                    ":now,:now) ON CONFLICT(source_id,normalized_url) "
                    "WHERE status IN ('QUEUED','RUNNING') DO NOTHING"
                ),
                {
                    "id": uuid7(),
                    "source": row["source_id"],
                    "stream": stream_id,
                    "origin": origin,
                    "actor": DISCOVERY_ACTOR_ID,
                    "now": now,
                },
            )
            await connection.execute(
                text(
                    "UPDATE source_auto_score_run SET status='DEFERRED',"
                    "next_attempt_at=:now+interval '6 hours',updated_at=:now WHERE id=:id"
                ),
                {"now": now, "id": row["run_id"]},
            )
            queued_probes += 1
    return {
        "profiles": queued_profiles,
        "probes": queued_probes,
        "deferred": deferred,
    }


class PostgresPersonalOccurrenceTracker:
    """Idempotently records discovery before consuming the 100-origin probe budget."""

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def register_occurrence(
        self,
        url: str,
        *,
        discovery_channel: str,
        industries: tuple[str, ...],
        content_domains: tuple[str, ...],
        parent_source_id: UUID | None,
        depth: int,
        now: datetime,
    ) -> bool:
        if depth not in {0, 1}:
            return False
        origin = _safe_origin(url)
        if origin is None:
            return False
        digest = sha256(origin.encode()).hexdigest()
        topic_codes = _topic_codes(industries, content_domains)
        async with self._engine.begin() as connection:
            await connection.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:origin,0))"),
                {"origin": origin},
            )
            source_id = await connection.scalar(
                text("SELECT id FROM source WHERE normalized_origin=:origin"),
                {"origin": origin},
            )
            existing_status = await connection.scalar(
                text(
                    "SELECT status FROM discovery_occurrence WHERE canonical_origin_sha256=:hash "
                    "AND discovery_channel=:channel "
                    "AND parent_source_id IS NOT DISTINCT FROM :parent "
                    "ORDER BY first_discovered_at,id LIMIT 1 FOR UPDATE"
                ),
                {"hash": digest, "channel": discovery_channel, "parent": parent_source_id},
            )
            if source_id is not None:
                next_status = "SCORED"
                should_probe = False
            elif existing_status == "DISCOVERED":
                next_status = "DISCOVERED"
                should_probe = False
            else:
                should_probe = bool(
                    await connection.scalar(
                        text("SELECT reserve_personal_probe_budget(:now)"), {"now": now}
                    )
                )
                next_status = "DISCOVERED" if should_probe else "DEFERRED"
            topic_ids = (
                await connection.execute(
                    text(
                        "SELECT id FROM discovery_topic WHERE enabled AND code=ANY(:codes) "
                        "ORDER BY code"
                    ),
                    {"codes": list(topic_codes)},
                )
            ).scalars()
            for topic_id in topic_ids:
                await connection.execute(
                    text(
                        "INSERT INTO discovery_occurrence(id,topic_id,canonical_origin,"
                        "canonical_origin_sha256,discovery_channel,parent_source_id,depth,"
                        "first_discovered_at,last_discovered_at,discovery_count,source_id,status) "
                        "VALUES(:id,:topic,:origin,:hash,:channel,:parent,:depth,"
                        ":now,:now,1,:source,:status) "
                        "ON CONFLICT(topic_id,canonical_origin_sha256,discovery_channel,"
                        "COALESCE(parent_source_id,'00000000-0000-0000-0000-000000000000'::uuid)) "
                        "DO UPDATE SET last_discovered_at=EXCLUDED.last_discovered_at,"
                        "discovery_count=discovery_occurrence.discovery_count+1,"
                        "source_id=COALESCE(discovery_occurrence.source_id,EXCLUDED.source_id),"
                        "status=CASE WHEN discovery_occurrence.status='ENABLED' THEN 'ENABLED' "
                        "ELSE EXCLUDED.status END"
                    ),
                    {
                        "id": uuid7(),
                        "topic": topic_id,
                        "origin": origin,
                        "hash": digest,
                        "channel": discovery_channel,
                        "now": now,
                        "source": source_id,
                        "status": next_status,
                        "parent": parent_source_id,
                        "depth": depth,
                    },
                )
        return should_probe


class EvidenceObjectStore(Protocol):
    async def get_bytes(self, key: str, *, max_bytes: int | None = None) -> bytes: ...


class PostgresSavedEvidenceAdapter:
    """Extract cross-institution links only from already saved public evidence."""

    def __init__(
        self,
        engine: AsyncEngine,
        object_store: EvidenceObjectStore,
        *,
        adapter_code: str,
        channel: PublicDiscoveryChannel,
        stream_type: str,
    ) -> None:
        self._engine = engine
        self._objects = object_store
        self.adapter_code = adapter_code
        self.channel = channel
        self._stream_type = stream_type

    async def discover(self, *, limit: int) -> tuple[PublicDiscoverySeed, ...]:
        async with self._engine.connect() as connection:
            rows = (
                (
                    await connection.execute(
                        text(
                            """
                            SELECT source.id,source.normalized_origin,probe.capture_manifest,
                              COALESCE(profile.industries,ARRAY['GENERAL_TRANSPORT']) industries,
                              COALESCE(profile.content_domains,
                                ARRAY['DIGITAL_TRANSFORMATION_CASE']) content_domains
                            FROM source
                            JOIN source_stream stream ON stream.source_id=source.id
                            JOIN LATERAL (
                              SELECT capture_manifest FROM stream_probe_run
                              WHERE source_id=source.id AND status='SUCCEEDED'
                              ORDER BY completed_at DESC,id DESC LIMIT 1
                            ) probe ON true
                            LEFT JOIN LATERAL (
                              SELECT industries,content_domains FROM source_profile_snapshot
                              WHERE source_id=source.id ORDER BY version DESC LIMIT 1
                            ) profile ON true
                            WHERE source.enabled AND stream.stream_type=:stream_type
                              AND source.normalized_origin IS NOT NULL
                              AND NOT EXISTS(
                                SELECT 1 FROM discovery_occurrence occurrence
                                WHERE occurrence.source_id=source.id AND occurrence.depth=1
                              )
                            ORDER BY source.id LIMIT :limit
                            """
                        ),
                        {"stream_type": self._stream_type, "limit": limit},
                    )
                )
                .mappings()
                .all()
            )
        seeds: dict[str, PublicDiscoverySeed] = {}
        for row in rows:
            for capture in row["capture_manifest"]:
                key = capture.get("object_key")
                if not isinstance(key, str):
                    continue
                try:
                    body = await self._objects.get_bytes(key, max_bytes=2 * 1024 * 1024)
                except (OSError, TimeoutError):
                    continue
                for origin in discover_public_origins(
                    body, parent_origin=row["normalized_origin"], depth=0
                ):
                    seeds.setdefault(
                        origin,
                        PublicDiscoverySeed(
                            origin,
                            tuple(row["industries"]),
                            tuple(row["content_domains"]),
                            row["id"],
                            1,
                        ),
                    )
                    if len(seeds) >= limit:
                        return tuple(seeds.values())
        return tuple(seeds.values())


class PostgresPersonalDiscoveryGateway:
    """Materialize a verified occurrence into the personal probe/profile flow."""

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def register_and_request(
        self,
        target: VerifiedDiscoveryTarget,
        *,
        discovery_channel: str,
        industries: tuple[str, ...],
        content_domains: tuple[str, ...],
        evidence_ref: str,
        discovery_run_id: UUID,
        now: datetime,
    ) -> RegistrationOutcome:
        del industries, content_domains, evidence_ref
        source_id = uuid7()
        stream_id = uuid7()
        host = urlsplit(target.canonical_url).hostname
        if host is None:
            raise ValueError("verified discovery origin has no host")
        request_id = f"pers05:{discovery_run_id}:{target.material_fingerprint[:16]}"
        created = False
        async with self._engine.begin() as connection:
            await connection.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:origin,0))"),
                {"origin": target.canonical_url},
            )
            existing = await connection.scalar(
                text("SELECT id FROM source WHERE normalized_origin=:origin FOR UPDATE"),
                {"origin": target.canonical_url},
            )
            if existing is None:
                created = True
                await connection.execute(
                    text(
                        "SELECT register_source_candidate(:id,:name,:origin,'BOTH',"
                        "'personal_public','B2','P2','auto_probe',1440,'Local Personal Owner',"
                        "NULL,ARRAY[]::text[],ARRAY[]::text[],ARRAY[]::text[],ARRAY[]::text[],"
                        "ARRAY[]::text[],ARRAY[]::text[],:actor,:request,:audit,:now)"
                    ),
                    {
                        "id": source_id,
                        "name": host,
                        "origin": target.canonical_url,
                        "actor": DISCOVERY_ACTOR_ID,
                        "request": request_id,
                        "audit": uuid7(),
                        "now": now,
                    },
                )
                await connection.execute(
                    text(
                        "UPDATE source SET normalized_origin=:origin,desired_enabled=false,"
                        "runtime_state='PENDING_CONFIGURATION',updated_at=:now WHERE id=:id"
                    ),
                    {"origin": target.canonical_url, "now": now, "id": source_id},
                )
            else:
                source_id = existing
            existing_stream = await connection.scalar(
                text("SELECT id FROM source_stream WHERE source_id=:source AND canonical_url=:url"),
                {"source": source_id, "url": target.canonical_url},
            )
            if existing_stream is None:
                await connection.execute(
                    text(
                        "INSERT INTO source_stream(id,source_id,stream_key,name,canonical_url,"
                        "authorization_boundary,status,rule_version,automatically_managed,"
                        "created_at,updated_at,stream_type,allowed_hosts,discovery_method) "
                        "VALUES(:id,:source,:key,:url,:url,:host,'PROBING',"
                        "'personal-source-probe-v1',true,:now,:now,'UNKNOWN',ARRAY[:host],:method)"
                    ),
                    {
                        "id": stream_id,
                        "source": source_id,
                        "key": "AUTO_" + target.material_fingerprint[:24],
                        "url": target.canonical_url,
                        "host": host,
                        "now": now,
                        "method": discovery_channel,
                    },
                )
                await connection.execute(
                    text(
                        "INSERT INTO stream_probe_run(id,source_id,stream_id,requested_url,"
                        "normalized_url,normalized_origin,input_kind,status,requested_by,"
                        "request_id,created_at,updated_at) VALUES(:id,:source,:stream,:url,:url,"
                        ":url,'UNKNOWN','QUEUED',:actor,:request,:now,:now)"
                    ),
                    {
                        "id": uuid7(),
                        "source": source_id,
                        "stream": stream_id,
                        "url": target.canonical_url,
                        "actor": DISCOVERY_ACTOR_ID,
                        "request": request_id,
                        "now": now,
                    },
                )
            await connection.execute(
                text(
                    "UPDATE discovery_occurrence SET source_id=:source,status='PROBING',"
                    "last_discovered_at=:now WHERE canonical_origin_sha256=:hash"
                ),
                {
                    "source": source_id,
                    "hash": sha256(target.canonical_url.encode()).hexdigest(),
                    "now": now,
                },
            )
        return RegistrationOutcome(source_id, None, created)

    async def close(self) -> None:
        await self._engine.dispose()


def discover_public_origins(
    body: bytes,
    *,
    parent_origin: str,
    depth: int,
) -> tuple[str, ...]:
    """Extract cross-institution HTTPS origins from saved RSS/Sitemap/HTML evidence.

    A seed discovered at depth one is terminal: it may be probed but cannot expand again.
    """

    if depth not in {0, 1}:
        raise ValueError("public discovery depth must be zero or one")
    if depth == 1:
        return ()
    parent = _safe_origin(parent_origin)
    if parent is None:
        raise ValueError("parent origin must be a public-shaped HTTPS origin")
    origins: set[str] = set()
    for match in _URL_PATTERN.finditer(body[: 2 * 1024 * 1024]):
        candidate = _safe_origin(unescape(match.group(1).decode("utf-8", errors="ignore")))
        if candidate is not None and candidate != parent:
            origins.add(candidate)
    return tuple(sorted(origins))


def _safe_origin(url: str) -> str | None:
    parsed = urlsplit(url.strip())
    hostname = parsed.hostname
    if (
        parsed.scheme != "https"
        or hostname is None
        or parsed.username is not None
        or parsed.password is not None
        or parsed.port not in {None, 443}
        or "." not in hostname
    ):
        return None
    host = hostname.encode("idna").decode("ascii").lower().rstrip(".")
    return f"https://{host}"


def _topic_codes(industries: tuple[str, ...], content_domains: tuple[str, ...]) -> tuple[str, ...]:
    codes: set[str] = set()
    industry_map = {
        "HIGHWAY": "HIGHWAY",
        "BRIDGE": "BRIDGE",
        "TUNNEL": "TUNNEL",
        "RAILWAY": "RAIL",
        "RAIL_TRANSIT": "RAIL",
    }
    codes.update(industry_map[item] for item in industries if item in industry_map)
    if any(
        "SAFETY" in item or item in {"ACCIDENT_INVESTIGATION", "PENALTY", "RECTIFICATION"}
        for item in content_domains
    ):
        codes.add("SAFETY")
    if any(
        item in {"IOT_EQUIPMENT", "LOW_ALTITUDE_EQUIPMENT", "AI_APPLICATION"}
        for item in content_domains
    ):
        codes.add("AI_IOT_LOW_ALTITUDE")
    if any(
        item in {"DIGITAL_TRANSFORMATION_CASE", "SOFTWARE_PLATFORM", "RESEARCH_PAPER"}
        for item in content_domains
    ):
        codes.add("DIGITAL")
    return tuple(sorted(codes or {"DIGITAL"}))
