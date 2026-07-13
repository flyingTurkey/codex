"""PostgreSQL persistence for source admission and immutable document versions."""

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from typing import Any
from urllib.parse import urlsplit
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import RowMapping
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine
from srbg_contracts import (
    CreateSourceRequest,
    DocumentDetail,
    DocumentVersionSummary,
    FixtureUploadResponse,
    RawObjectSummary,
    ScanStatus,
    SourceState,
)

from srbg_api.document_vault.service import FixtureRecord
from srbg_api.identifiers import uuid7


class SourceNotFound(LookupError):
    pass


class RepositoryConflict(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class SourceRow:
    id: UUID
    registry_code: str | None
    name: str
    base_url: str
    channel: str
    source_type: str
    authority_level: str
    priority: str
    collection_method: str
    poll_interval_minutes: int
    owner: str
    state: SourceState
    enabled: bool
    created_at: datetime


@dataclass(frozen=True, slots=True)
class PolicyRow:
    id: UUID
    policy_version: str
    status: str
    document: dict[str, Any]
    document_sha256: str
    valid_until: datetime
    created_at: datetime


@dataclass(frozen=True, slots=True)
class OnboardingRow:
    id: UUID
    source_policy_id: UUID
    record: dict[str, Any]
    record_sha256: str
    fixture_count: int
    fixture_set_sha256: str | None
    valid_until: datetime
    created_at: datetime


class SourceVaultRepository:
    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def close(self) -> None:
        await self._engine.dispose()

    async def list_sources(self) -> list[SourceRow]:
        async with self._engine.connect() as connection:
            rows = (
                await connection.execute(
                    text(
                        """
                        SELECT id, registry_code, name, base_url, channel, source_type,
                               authority_level, priority, collection_method,
                               poll_interval_minutes, owner, state, enabled, created_at
                        FROM source
                        ORDER BY priority, registry_code NULLS LAST, created_at
                        """
                    )
                )
            ).mappings()
            return [_source_row(row) for row in rows]

    async def get_source(self, source_id: UUID) -> SourceRow:
        async with self._engine.connect() as connection:
            row = (
                (
                    await connection.execute(
                        text(
                            """
                        SELECT id, registry_code, name, base_url, channel, source_type,
                               authority_level, priority, collection_method,
                               poll_interval_minutes, owner, state, enabled, created_at
                        FROM source WHERE id = :source_id
                        """
                        ),
                        {"source_id": source_id},
                    )
                )
                .mappings()
                .first()
            )
        if row is None:
            raise SourceNotFound("source does not exist")
        return _source_row(row)

    async def create_source(
        self,
        payload: CreateSourceRequest,
        *,
        actor_id: UUID,
        request_id: str,
        now: datetime,
    ) -> SourceRow:
        source_id = uuid7()
        values = payload.model_dump(mode="json") | {
            "id": source_id,
            "state": SourceState.CANDIDATE.value,
            "enabled": False,
            "now": now,
        }
        async with self._engine.begin() as connection:
            await connection.execute(
                text(
                    """
                    INSERT INTO source (
                        id, registry_code, name, base_url, channel, source_type,
                        authority_level, priority, collection_method,
                        poll_interval_minutes, owner, state, enabled, created_at, updated_at
                    ) VALUES (
                        :id, NULL, :name, :base_url, :channel, :source_type,
                        :authority_level, :priority, :collection_method,
                        :poll_interval_minutes, :owner, :state, :enabled, :now, :now
                    )
                    """
                ),
                values,
            )
            await self._append_audit(
                connection,
                event_type="SOURCE_REGISTERED",
                actor_id=actor_id,
                target_type="source",
                target_id=source_id,
                before_state=None,
                after_state={"state": SourceState.CANDIDATE.value, "enabled": False},
                reason="Candidate source registered",
                request_id=request_id,
                now=now,
            )
        return await self.get_source(source_id)

    async def latest_policy(self, source_id: UUID) -> PolicyRow | None:
        async with self._engine.connect() as connection:
            row = (
                (
                    await connection.execute(
                        text(
                            """
                        SELECT id, policy_version, status, document, document_sha256,
                               valid_until, created_at
                        FROM source_policy
                        WHERE source_id = :source_id
                        ORDER BY created_at DESC, id DESC LIMIT 1
                        """
                        ),
                        {"source_id": source_id},
                    )
                )
                .mappings()
                .first()
            )
        return None if row is None else _policy_row(row)

    async def latest_onboarding(self, source_id: UUID) -> OnboardingRow | None:
        async with self._engine.connect() as connection:
            row = (
                (
                    await connection.execute(
                        text(
                            """
                        SELECT id, source_policy_id, record, record_sha256, fixture_count,
                               fixture_set_sha256, valid_until, created_at
                        FROM source_onboarding_record
                        WHERE source_id = :source_id
                        ORDER BY created_at DESC, id DESC LIMIT 1
                        """
                        ),
                        {"source_id": source_id},
                    )
                )
                .mappings()
                .first()
            )
        return None if row is None else _onboarding_row(row)

    async def fixture_hashes(self, source_id: UUID) -> list[str]:
        async with self._engine.connect() as connection:
            values = await connection.scalars(
                text(
                    """
                    SELECT DISTINCT document_version.content_hash
                    FROM document_version
                    JOIN document ON document.id = document_version.document_id
                    WHERE document.source_id = :source_id
                    ORDER BY document_version.content_hash
                    """
                ),
                {"source_id": source_id},
            )
            return list(values)

    async def save_policy(
        self,
        source_id: UUID,
        *,
        policy_version: str,
        status: str,
        document: dict[str, Any],
        document_sha256: str,
        valid_until: datetime,
        actor_id: UUID,
        request_id: str,
        now: datetime,
    ) -> None:
        policy_id = uuid7()
        async with self._engine.begin() as connection:
            source = await self._locked_source(connection, source_id)
            await connection.execute(
                text(
                    """
                    INSERT INTO source_policy (
                        id, source_id, policy_version, status, document,
                        document_sha256, valid_until, created_by, created_at
                    ) VALUES (
                        :id, :source_id, :policy_version, :status,
                        CAST(:document AS jsonb), :document_sha256, :valid_until,
                        :actor_id, :now
                    )
                    """
                ),
                {
                    "id": policy_id,
                    "source_id": source_id,
                    "policy_version": policy_version,
                    "status": status,
                    "document": _json(document),
                    "document_sha256": document_sha256,
                    "valid_until": valid_until,
                    "actor_id": actor_id,
                    "now": now,
                },
            )
            if bool(source["enabled"]):
                await connection.execute(
                    text("UPDATE source SET enabled = false, updated_at = :now WHERE id = :id"),
                    {"id": source_id, "now": now},
                )
            await self._append_audit(
                connection,
                event_type="SOURCE_POLICY_CHANGED",
                actor_id=actor_id,
                target_type="source_policy",
                target_id=policy_id,
                before_state=None,
                after_state={
                    "source_id": str(source_id),
                    "policy_version": policy_version,
                    "status": status,
                    "document_sha256": document_sha256,
                    "source_disabled": bool(source["enabled"]),
                },
                reason="Source admission policy recorded",
                request_id=request_id,
                now=now,
            )

    async def save_onboarding(
        self,
        source_id: UUID,
        policy_id: UUID,
        *,
        record: dict[str, Any],
        record_sha256: str,
        fixture_count: int,
        fixture_set_sha256: str,
        valid_until: datetime,
        actor_id: UUID,
        request_id: str,
        now: datetime,
    ) -> None:
        onboarding_id = uuid7()
        async with self._engine.begin() as connection:
            await self._locked_source(connection, source_id)
            await connection.execute(
                text(
                    """
                    INSERT INTO source_onboarding_record (
                        id, source_id, source_policy_id, record, record_sha256,
                        fixture_count, fixture_set_sha256, valid_until, created_by, created_at
                    ) VALUES (
                        :id, :source_id, :policy_id, CAST(:record AS jsonb),
                        :record_sha256, :fixture_count, :fixture_set_sha256,
                        :valid_until, :actor_id, :now
                    )
                    """
                ),
                {
                    "id": onboarding_id,
                    "source_id": source_id,
                    "policy_id": policy_id,
                    "record": _json(record),
                    "record_sha256": record_sha256,
                    "fixture_count": fixture_count,
                    "fixture_set_sha256": fixture_set_sha256,
                    "valid_until": valid_until,
                    "actor_id": actor_id,
                    "now": now,
                },
            )
            await self._append_audit(
                connection,
                event_type="SOURCE_ONBOARDING_RECORDED",
                actor_id=actor_id,
                target_type="source_onboarding_record",
                target_id=onboarding_id,
                before_state=None,
                after_state={
                    "source_id": str(source_id),
                    "record_sha256": record_sha256,
                    "fixture_set_sha256": fixture_set_sha256,
                },
                reason="Source onboarding evidence recorded",
                request_id=request_id,
                now=now,
            )

    async def change_source(
        self,
        source_id: UUID,
        *,
        state: SourceState,
        enabled: bool,
        event_type: str,
        reason: str,
        actor_id: UUID,
        request_id: str,
        now: datetime,
    ) -> None:
        async with self._engine.begin() as connection:
            current = await self._locked_source(connection, source_id)
            before = {"state": str(current["state"]), "enabled": bool(current["enabled"])}
            after = {"state": state.value, "enabled": enabled}
            await connection.execute(
                text(
                    """
                    UPDATE source SET state = :state, enabled = :enabled, updated_at = :now
                    WHERE id = :source_id
                    """
                ),
                {"state": state.value, "enabled": enabled, "now": now, "source_id": source_id},
            )
            await self._append_audit(
                connection,
                event_type=event_type,
                actor_id=actor_id,
                target_type="source",
                target_id=source_id,
                before_state=before,
                after_state=after,
                reason=reason,
                request_id=request_id,
                now=now,
            )

    async def source_accepts_fixture(self, source_id: UUID, canonical_url: str) -> bool:
        try:
            source = await self.get_source(source_id)
        except SourceNotFound:
            return False
        if source.state not in {
            SourceState.FIXTURE_TEST,
            SourceState.APPROVED,
            SourceState.ACTIVE,
        }:
            return False
        policy = await self.latest_policy(source_id)
        if (
            policy is None
            or policy.status != "VALID"
            or policy.valid_until <= datetime.now(UTC)
        ):
            return False
        hostname = urlsplit(canonical_url).hostname
        domains = policy.document.get("access", {}).get("allowed_domains", [])
        return hostname is not None and any(
            hostname == domain or hostname.endswith(f".{domain}") for domain in domains
        )

    async def raw_object_exists(self, content_hash: str) -> bool:
        async with self._engine.connect() as connection:
            value = await connection.scalar(
                text("SELECT EXISTS(SELECT 1 FROM raw_object WHERE sha256 = :sha256)"),
                {"sha256": content_hash},
            )
            return bool(value)

    async def record_fixture(self, record: FixtureRecord) -> FixtureUploadResponse:
        version_created = False
        async with self._engine.begin() as connection:
            source = await self._locked_source(connection, record.source_id)
            if str(source["state"]) not in {
                SourceState.FIXTURE_TEST.value,
                SourceState.APPROVED.value,
                SourceState.ACTIVE.value,
            }:
                raise RepositoryConflict("source left fixture-test state")
            raw_id = uuid7()
            inserted_raw = (
                await connection.execute(
                    text(
                        """
                        INSERT INTO raw_object (
                            id, sha256, object_key, byte_size, declared_mime,
                            detected_mime, scan_status, storage_etag, created_at
                        ) VALUES (
                            :id, :sha256, :object_key, :byte_size, :detected_mime,
                            :detected_mime, 'CLEAN', :storage_etag, :created_at
                        )
                        ON CONFLICT (sha256) DO NOTHING RETURNING id
                        """
                    ),
                    {
                        "id": raw_id,
                        "sha256": record.content_hash,
                        "object_key": record.object_key,
                        "byte_size": record.byte_size,
                        "detected_mime": record.detected_mime,
                        "storage_etag": record.storage_etag,
                        "created_at": record.acquired_at,
                    },
                )
            ).scalar_one_or_none()
            raw_deduplicated = inserted_raw is None
            if raw_deduplicated:
                raw_id = await connection.scalar(
                    text("SELECT id FROM raw_object WHERE sha256 = :sha256"),
                    {"sha256": record.content_hash},
                )
                if not isinstance(raw_id, UUID):
                    raise RepositoryConflict("raw object deduplication failed")

            document_id = uuid7()
            inserted_document = (
                await connection.execute(
                    text(
                        """
                        INSERT INTO document (
                            id, source_id, canonical_url, document_kind,
                            first_discovered_at, current_version_id
                        ) VALUES (:id, :source_id, :url, :kind, :acquired_at, NULL)
                        ON CONFLICT (source_id, canonical_url) DO NOTHING RETURNING id
                        """
                    ),
                    {
                        "id": document_id,
                        "source_id": record.source_id,
                        "url": record.canonical_url,
                        "kind": record.document_kind,
                        "acquired_at": record.acquired_at,
                    },
                )
            ).scalar_one_or_none()
            if inserted_document is None:
                document_id = await connection.scalar(
                    text(
                        """
                        SELECT id FROM document
                        WHERE source_id = :source_id AND canonical_url = :url
                        FOR UPDATE
                        """
                    ),
                    {"source_id": record.source_id, "url": record.canonical_url},
                )
                if not isinstance(document_id, UUID):
                    raise RepositoryConflict("document upsert failed")

            existing_version = await connection.scalar(
                text(
                    """
                    SELECT id FROM document_version
                    WHERE document_id = :document_id AND content_hash = :content_hash
                    """
                ),
                {"document_id": document_id, "content_hash": record.content_hash},
            )
            if existing_version is None:
                next_number = int(
                    await connection.scalar(
                        text(
                            """
                            SELECT COALESCE(MAX(version_number), 0) + 1
                            FROM document_version WHERE document_id = :document_id
                            """
                        ),
                        {"document_id": document_id},
                    )
                )
                version_id = uuid7()
                await connection.execute(
                    text(
                        """
                        INSERT INTO document_version (
                            id, document_id, raw_object_id, version_number, content_hash,
                            original_filename, title, acquired_at
                        ) VALUES (
                            :id, :document_id, :raw_object_id, :version_number,
                            :content_hash, :filename, :title, :acquired_at
                        )
                        """
                    ),
                    {
                        "id": version_id,
                        "document_id": document_id,
                        "raw_object_id": raw_id,
                        "version_number": next_number,
                        "content_hash": record.content_hash,
                        "filename": record.filename,
                        "title": record.title,
                        "acquired_at": record.acquired_at,
                    },
                )
                await connection.execute(
                    text("UPDATE document SET current_version_id = :version_id WHERE id = :id"),
                    {"version_id": version_id, "id": document_id},
                )
                version_created = True
            await self._append_audit(
                connection,
                event_type="SOURCE_FIXTURE_UPLOADED",
                actor_id=record.actor_id,
                target_type="document",
                target_id=document_id,
                before_state=None,
                after_state={
                    "content_hash": record.content_hash,
                    "raw_object_deduplicated": raw_deduplicated,
                    "version_created": version_created,
                },
                reason="Manual source fixture uploaded",
                request_id=record.request_id,
                now=record.acquired_at,
            )
        document = await self.get_document(document_id)
        return FixtureUploadResponse(
            document=document,
            raw_object_deduplicated=raw_deduplicated,
            version_created=version_created,
        )

    async def get_document(self, document_id: UUID) -> DocumentDetail:
        async with self._engine.connect() as connection:
            row = (
                (
                    await connection.execute(
                        text(
                            """
                        SELECT d.id, d.source_id, s.name AS source_name, d.canonical_url,
                               d.document_kind, d.first_discovered_at,
                               v.id AS version_id, v.version_number, v.content_hash,
                               v.original_filename, v.title, v.acquired_at,
                               r.id AS raw_id, r.sha256, r.detected_mime,
                               r.byte_size, r.scan_status
                        FROM document d
                        JOIN source s ON s.id = d.source_id
                        JOIN document_version v ON v.id = d.current_version_id
                        JOIN raw_object r ON r.id = v.raw_object_id
                        WHERE d.id = :document_id
                        """
                        ),
                        {"document_id": document_id},
                    )
                )
                .mappings()
                .first()
            )
        if row is None:
            raise SourceNotFound("document does not exist")
        return DocumentDetail(
            id=row["id"],
            source_id=row["source_id"],
            source_name=row["source_name"],
            canonical_url=row["canonical_url"],
            document_kind=row["document_kind"],
            first_discovered_at=row["first_discovered_at"],
            current_version=DocumentVersionSummary(
                id=row["version_id"],
                version_number=row["version_number"],
                content_hash=row["content_hash"],
                original_filename=row["original_filename"],
                title=row["title"],
                acquired_at=row["acquired_at"],
            ),
            raw_object=RawObjectSummary(
                id=row["raw_id"],
                sha256=row["sha256"],
                detected_mime=row["detected_mime"],
                byte_size=row["byte_size"],
                scan_status=ScanStatus(row["scan_status"]),
            ),
        )

    async def _locked_source(self, connection: AsyncConnection, source_id: UUID) -> RowMapping:
        row = (
            (
                await connection.execute(
                    text("SELECT id, state, enabled FROM source WHERE id = :id FOR UPDATE"),
                    {"id": source_id},
                )
            )
            .mappings()
            .first()
        )
        if row is None:
            raise SourceNotFound("source does not exist")
        return row

    async def _append_audit(
        self,
        connection: AsyncConnection,
        *,
        event_type: str,
        actor_id: UUID,
        target_type: str,
        target_id: UUID,
        before_state: dict[str, Any] | None,
        after_state: dict[str, Any] | None,
        reason: str,
        request_id: str,
        now: datetime,
    ) -> None:
        await connection.execute(text("SELECT pg_advisory_xact_lock(hashtext('audit_log'))"))
        previous_hash = await connection.scalar(
            text("SELECT entry_hash FROM audit_log ORDER BY created_at DESC, id DESC LIMIT 1")
        )
        audit_id = uuid7()
        canonical = {
            "id": str(audit_id),
            "event_type": event_type,
            "actor_id": str(actor_id),
            "target_type": target_type,
            "target_id": str(target_id),
            "before_state": before_state,
            "after_state": after_state,
            "reason": reason,
            "request_id": request_id,
            "previous_hash": previous_hash,
            "created_at": now.isoformat(),
        }
        entry_hash = sha256(_json(canonical).encode()).hexdigest()
        await connection.execute(
            text(
                """
                INSERT INTO audit_log (
                    id, event_type, actor_id, target_type, target_id, before_state,
                    after_state, reason, request_id, previous_hash, entry_hash, created_at
                ) VALUES (
                    :id, :event_type, :actor_id, :target_type, :target_id,
                    CAST(:before_state AS jsonb), CAST(:after_state AS jsonb),
                    :reason, :request_id, :previous_hash, :entry_hash, :created_at
                )
                """
            ),
            {
                "id": audit_id,
                "event_type": event_type,
                "actor_id": actor_id,
                "target_type": target_type,
                "target_id": target_id,
                "before_state": None if before_state is None else _json(before_state),
                "after_state": None if after_state is None else _json(after_state),
                "reason": reason,
                "request_id": request_id,
                "previous_hash": previous_hash,
                "entry_hash": entry_hash,
                "created_at": now,
            },
        )


def _source_row(row: RowMapping) -> SourceRow:
    return SourceRow(
        id=row["id"],
        registry_code=row["registry_code"],
        name=row["name"],
        base_url=row["base_url"],
        channel=row["channel"],
        source_type=row["source_type"],
        authority_level=row["authority_level"],
        priority=row["priority"],
        collection_method=row["collection_method"],
        poll_interval_minutes=row["poll_interval_minutes"],
        owner=row["owner"],
        state=SourceState(row["state"]),
        enabled=row["enabled"],
        created_at=row["created_at"],
    )


def _policy_row(row: RowMapping) -> PolicyRow:
    return PolicyRow(
        id=row["id"],
        policy_version=row["policy_version"],
        status=row["status"],
        document=dict(row["document"]),
        document_sha256=row["document_sha256"],
        valid_until=row["valid_until"],
        created_at=row["created_at"],
    )


def _onboarding_row(row: RowMapping) -> OnboardingRow:
    return OnboardingRow(
        id=row["id"],
        source_policy_id=row["source_policy_id"],
        record=dict(row["record"]),
        record_sha256=row["record_sha256"],
        fixture_count=row["fixture_count"],
        fixture_set_sha256=row["fixture_set_sha256"],
        valid_until=row["valid_until"],
        created_at=row["created_at"],
    )


def canonical_json_hash(value: dict[str, Any]) -> str:
    return sha256(_json(value).encode()).hexdigest()


def fixture_set_hash(values: list[str]) -> str:
    return sha256("\n".join(sorted(set(values))).encode()).hexdigest()


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
