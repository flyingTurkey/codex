# ruff: noqa: E501
"""PostgreSQL persistence for personal sources and source profiles."""

import base64
import json
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from typing import Any, Literal
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import RowMapping
from sqlalchemy.ext.asyncio import AsyncEngine
from srbg_contracts import (
    DiscoveryDailyUsageView,
    DiscoveryTopicPatchRequest,
    DiscoveryTopicView,
    PersonalSourceCreateRequest,
    PersonalSourceInputKind,
    PersonalSourcePatchRequest,
    PersonalSourceProbeStatus,
    PersonalSourceReprobeRequest,
    PersonalSourceRuntimeState,
    PersonalSourceStreamStatus,
    PersonalSourceStreamType,
    PersonalStreamHealthReason,
    PersonalStreamHealthStatus,
    PersonalStreamRuntimeState,
    SourceAutoScoreDetailView,
    SourceAutoScoreSummaryView,
    SourceProfileOverrideRequest,
    SourceProfileSummaryView,
    SourceProfileView,
)

from srbg_api.identifiers import uuid7


class SourceNotFound(LookupError):
    pass


class RepositoryConflict(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class PersonalSourceRow:
    id: UUID
    display_name: str
    url: str
    desired_enabled: bool
    runtime_state: PersonalSourceRuntimeState
    manual_disabled_at: datetime | None
    normalized_origin: str | None = None
    streams: tuple["PersonalStreamRow", ...] = ()
    latest_probe_run: "ProbeRunRow | None" = None
    auto_score_summary: SourceAutoScoreSummaryView | None = None
    profile_summary: SourceProfileSummaryView | None = None


@dataclass(frozen=True, slots=True)
class AutomationSettingRow:
    automation_enabled: bool
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class PersonalStreamRow:
    id: UUID
    stream_type: PersonalSourceStreamType
    normalized_url: str
    allowed_hosts: tuple[str, ...]
    config_sha256: str | None
    discovery_method: str
    status: PersonalSourceStreamStatus
    failure_reason: str | None
    actual_running: bool = False
    runtime_state: PersonalStreamRuntimeState = PersonalStreamRuntimeState.STOPPED
    health_status: PersonalStreamHealthStatus = PersonalStreamHealthStatus.UNKNOWN
    health_reason: PersonalStreamHealthReason | None = None
    consecutive_failures: int = 0
    next_self_heal_at: datetime | None = None
    last_successful_fetch_at: datetime | None = None
    last_content_discovered_at: datetime | None = None
    health_observation_id: UUID | None = None
    health_observed_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class PersonalActivityRow:
    id: UUID
    kind: Literal[
        "OWNER_ENABLED",
        "OWNER_DISABLED",
        "AUTO_ENABLED",
        "DISPLAY_NAME_CHANGED",
        "URL_PROBE",
        "COLLECTION_RUN",
    ]
    occurred_at: datetime
    stream_id: UUID | None
    status: str
    reason_code: str | None
    discovered_count: int | None
    fetched_count: int | None
    failed_count: int | None


@dataclass(frozen=True, slots=True)
class PersonalRunSummaryRow:
    last_run_at: datetime | None
    last_run_status: str | None
    discovered_count: int
    fetched_count: int
    failed_count: int
    next_run_at: datetime | None


@dataclass(frozen=True, slots=True)
class PersonalActivityPageRow:
    items: tuple[PersonalActivityRow, ...]
    next_cursor: str | None
    run_summary: PersonalRunSummaryRow


@dataclass(frozen=True, slots=True)
class ProbeRunRow:
    id: UUID
    requested_url: str
    input_kind: PersonalSourceInputKind
    status: PersonalSourceProbeStatus
    duration_ms: int | None
    failure_code: str | None
    failure_reason: str | None


class SourceVaultRepository:
    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def close(self) -> None:
        await self._engine.dispose()

    async def list_personal_sources(self) -> list[PersonalSourceRow]:
        async with self._engine.connect() as connection:
            rows = (
                await connection.execute(
                    text(
                        "\n                        SELECT source.id,source.name,source.base_url,source.desired_enabled,\n                               source.runtime_state,source.manual_disabled_at,\n                               source.normalized_origin,score.id AS score_id,\n                               score.total_score,score.auto_enable_eligible,\n                               score.reason_codes AS score_reason_codes,\n                               score.rule_version AS score_rule_version,\n                               score.evaluated_at AS score_evaluated_at\n                          FROM source\n                          LEFT JOIN LATERAL (\n                            SELECT id,total_score,auto_enable_eligible,reason_codes,\n                                   rule_version,evaluated_at\n                              FROM source_auto_score_snapshot snapshot\n                             WHERE snapshot.source_id=source.id\n                             ORDER BY version DESC LIMIT 1\n                          ) score ON true\n                         WHERE source.state <> 'FIXTURE_TEST'\n                           AND source.trial_kind IS DISTINCT FROM 'FIXTURE_REPLAY'\n                         ORDER BY lower(source.name),source.id\n                        "
                    )
                )
            ).mappings()
            base_rows = [_personal_source_row(row) for row in rows]
        return [await self._personal_source_with_probe(row) for row in base_rows]

    async def get_personal_source(self, source_id: UUID) -> PersonalSourceRow:
        async with self._engine.connect() as connection:
            row = (
                (
                    await connection.execute(
                        text(
                            "\n                            SELECT source.id,source.name,source.base_url,\n                                   source.desired_enabled,source.runtime_state,\n                                   source.manual_disabled_at,source.normalized_origin,\n                                   score.id AS score_id,score.total_score,\n                                   score.auto_enable_eligible,\n                                   score.reason_codes AS score_reason_codes,\n                                   score.rule_version AS score_rule_version,\n                                   score.evaluated_at AS score_evaluated_at\n                              FROM source\n                              LEFT JOIN LATERAL (\n                                SELECT id,total_score,auto_enable_eligible,reason_codes,\n                                       rule_version,evaluated_at\n                                  FROM source_auto_score_snapshot snapshot\n                                 WHERE snapshot.source_id=source.id\n                                 ORDER BY version DESC LIMIT 1\n                              ) score ON true\n                             WHERE source.id=:source_id\n                               AND source.state <> 'FIXTURE_TEST'\n                               AND source.trial_kind IS DISTINCT FROM 'FIXTURE_REPLAY'\n                            "
                        ),
                        {"source_id": source_id},
                    )
                )
                .mappings()
                .first()
            )
        if row is None:
            raise SourceNotFound("source does not exist")
        return await self._personal_source_with_probe(_personal_source_row(row))

    async def get_personal_source_activity(
        self, source_id: UUID, *, cursor: str | None, limit: int
    ) -> PersonalActivityPageRow:
        cursor_at, cursor_id = _decode_personal_activity_cursor(cursor)
        async with self._engine.connect() as connection:
            exists = await connection.scalar(
                text("SELECT EXISTS(SELECT 1 FROM source WHERE id=:source_id)"),
                {"source_id": source_id},
            )
            if not exists:
                raise SourceNotFound("source does not exist")
            rows = list(
                (
                    await connection.execute(
                        text(
                            "\n                            WITH activity AS (\n                              SELECT event.id,\n                                CASE event.event_type\n                                  WHEN 'MANUAL_ENABLED' THEN 'OWNER_ENABLED'\n                                  WHEN 'MANUAL_DISABLED' THEN 'OWNER_DISABLED'\n                                  WHEN 'AUTO_ENABLED' THEN 'AUTO_ENABLED'\n                                  ELSE 'DISPLAY_NAME_CHANGED'\n                                END AS kind,\n                                event.created_at AS occurred_at,NULL::uuid AS stream_id,\n                                event.event_type AS status,NULL::text AS reason_code,\n                                NULL::integer AS discovered_count,NULL::integer AS fetched_count,\n                                NULL::integer AS failed_count\n                              FROM source_key_activity_event event WHERE event.source_id=:source_id\n                              UNION ALL\n                              SELECT probe.id,'URL_PROBE',probe.updated_at,probe.stream_id,\n                                probe.status,probe.failure_code,NULL,NULL,NULL\n                              FROM stream_probe_run probe WHERE probe.source_id=:source_id\n                              UNION ALL\n                                SELECT run.id,'COLLECTION_RUN',\n                                  COALESCE(run.completed_at,run.started_at),\n                                run.source_stream_id,run.status,run.error_code,\n                                run.discovered_count,run.fetched_count,run.failed_count\n                              FROM fetch_run run WHERE run.source_id=:source_id\n                            )\n                            SELECT * FROM activity\n                              WHERE (CAST(:cursor_at AS timestamptz) IS NULL OR\n                                (occurred_at,id)<(\n                                  CAST(:cursor_at AS timestamptz),CAST(:cursor_id AS uuid)\n                                ))\n                            ORDER BY occurred_at DESC,id DESC LIMIT :row_limit\n                            "
                        ),
                        {
                            "source_id": source_id,
                            "cursor_at": cursor_at,
                            "cursor_id": cursor_id,
                            "row_limit": limit + 1,
                        },
                    )
                ).mappings()
            )
            latest = (
                (
                    await connection.execute(
                        text(
                            "SELECT status,COALESCE(completed_at,started_at) AS run_at,\n                                      discovered_count,fetched_count,failed_count\n                                 FROM fetch_run WHERE source_id=:source_id\n                                 ORDER BY started_at DESC,id DESC LIMIT 1"
                        ),
                        {"source_id": source_id},
                    )
                )
                .mappings()
                .first()
            )
            next_run_at = await connection.scalar(
                text(
                    "SELECT MIN(next_run_at) FROM fetch_schedule WHERE source_id=:source_id AND authority_mode='PERSONAL_STREAM'"
                ),
                {"source_id": source_id},
            )
        has_more = len(rows) > limit
        visible_rows = rows[:limit]
        items = tuple(PersonalActivityRow(**dict(row)) for row in visible_rows)
        next_cursor = (
            _encode_personal_activity_cursor(items[-1].occurred_at, items[-1].id)
            if has_more and items
            else None
        )
        return PersonalActivityPageRow(
            items=items,
            next_cursor=next_cursor,
            run_summary=PersonalRunSummaryRow(
                last_run_at=None if latest is None else latest["run_at"],
                last_run_status=None if latest is None else latest["status"],
                discovered_count=0 if latest is None else int(latest["discovered_count"]),
                fetched_count=0 if latest is None else int(latest["fetched_count"]),
                failed_count=0 if latest is None else int(latest["failed_count"]),
                next_run_at=next_run_at,
            ),
        )

    async def get_discovery_setting(self) -> AutomationSettingRow:
        async with self._engine.connect() as connection:
            row = (
                (
                    await connection.execute(
                        text(
                            "SELECT automation_enabled,updated_at FROM personal_automation_setting WHERE singleton_slot=1"
                        )
                    )
                )
                .mappings()
                .one()
            )
        return AutomationSettingRow(row["automation_enabled"], row["updated_at"])

    async def patch_discovery_setting(
        self, enabled: bool, *, actor_id: UUID, request_id: str, now: datetime
    ) -> AutomationSettingRow:
        async with self._engine.begin() as connection:
            before = await connection.scalar(
                text(
                    "SELECT automation_enabled FROM personal_automation_setting WHERE singleton_slot=1 FOR UPDATE"
                )
            )
            if not isinstance(before, bool):
                raise RepositoryConflict("personal automation setting does not exist")
            await connection.execute(
                text(
                    "UPDATE personal_automation_setting SET automation_enabled=:enabled,updated_at=:now WHERE singleton_slot=1"
                ),
                {"enabled": enabled, "now": now},
            )
            if before != enabled:
                await connection.execute(
                    text(
                        "INSERT INTO personal_discovery_setting_event(id,actor_id,request_id,before_enabled,after_enabled,created_at) VALUES(:id,:actor_id,:request_id,:before,:after,:now)"
                    ),
                    {
                        "id": uuid7(),
                        "actor_id": actor_id,
                        "request_id": request_id,
                        "before": before,
                        "after": enabled,
                        "now": now,
                    },
                )
        return AutomationSettingRow(enabled, now)

    async def list_discovery_topics(self) -> list[DiscoveryTopicView]:
        async with self._engine.connect() as connection:
            rows = (
                await connection.execute(
                    text(
                        "SELECT id,code,name,keywords,excluded_terms,focus_regions,enabled,version,updated_at FROM discovery_topic ORDER BY code"
                    )
                )
            ).mappings()
            return [DiscoveryTopicView.model_validate(dict(row)) for row in rows]

    async def patch_discovery_topic(
        self,
        topic_id: UUID,
        payload: DiscoveryTopicPatchRequest,
        *,
        actor_id: UUID,
        request_id: str,
        now: datetime,
    ) -> DiscoveryTopicView:
        async with self._engine.begin() as connection:
            row = (
                (
                    await connection.execute(
                        text(
                            "SELECT id,code,name,keywords,excluded_terms,focus_regions,enabled,version,updated_at FROM discovery_topic WHERE id=:id FOR UPDATE"
                        ),
                        {"id": topic_id},
                    )
                )
                .mappings()
                .first()
            )
            if row is None:
                raise SourceNotFound("discovery topic does not exist")
            before = dict(row)
            keywords = (
                payload.keywords
                if "keywords" in payload.model_fields_set
                else list(row["keywords"])
            )
            excluded = (
                payload.excluded_terms
                if "excluded_terms" in payload.model_fields_set
                else list(row["excluded_terms"])
            )
            regions = (
                payload.focus_regions
                if "focus_regions" in payload.model_fields_set
                else list(row["focus_regions"])
            )
            enabled = payload.enabled if "enabled" in payload.model_fields_set else row["enabled"]
            updated = (
                (
                    await connection.execute(
                        text(
                            "UPDATE discovery_topic SET keywords=:keywords,excluded_terms=:excluded,focus_regions=:regions,enabled=:enabled,version=version+1,updated_at=:now WHERE id=:id RETURNING id,code,name,keywords,excluded_terms,focus_regions,enabled,version,updated_at"
                        ),
                        {
                            "id": topic_id,
                            "keywords": keywords,
                            "excluded": excluded,
                            "regions": regions,
                            "enabled": enabled,
                            "now": now,
                        },
                    )
                )
                .mappings()
                .one()
            )
            await connection.execute(
                text(
                    "INSERT INTO discovery_topic_event(id,topic_id,actor_id,request_id,before_state,after_state,created_at) VALUES(:id,:topic,:actor,:request,CAST(:before AS jsonb),CAST(:after AS jsonb),:now)"
                ),
                {
                    "id": uuid7(),
                    "topic": topic_id,
                    "actor": actor_id,
                    "request": request_id,
                    "before": json.dumps(before, default=str),
                    "after": json.dumps(dict(updated), default=str),
                    "now": now,
                },
            )
        return DiscoveryTopicView.model_validate(dict(updated))

    async def get_discovery_usage(self, *, now: datetime) -> DiscoveryDailyUsageView:
        async with self._engine.connect() as connection:
            row = (
                (
                    await connection.execute(
                        text(
                            "SELECT personal_discovery_local_date(:now) AS local_date,COALESCE((SELECT used_count FROM personal_probe_daily_ledger WHERE local_date=personal_discovery_local_date(:now)),0) AS probe_used,COALESCE((SELECT used_count FROM personal_auto_enable_daily_ledger WHERE local_date=personal_discovery_local_date(:now)),0) AS enable_used"
                        ),
                        {"now": now},
                    )
                )
                .mappings()
                .one()
            )
        return DiscoveryDailyUsageView(
            local_date=row["local_date"],
            probe_used=row["probe_used"],
            auto_enable_used=row["enable_used"],
        )

    async def get_auto_score(self, source_id: UUID) -> SourceAutoScoreDetailView:
        async with self._engine.connect() as connection:
            row = (
                (
                    await connection.execute(
                        text(
                            "SELECT id AS snapshot_id,source_id,total_score,auto_enable_eligible AS eligible,reason_codes,rule_version,evaluated_at,topic_relevance_score,connector_stability_score,sample_completeness_score,profile_evidence_score,content_validity_score,component_explanations,hard_gate_results,evidence_refs FROM source_auto_score_snapshot WHERE source_id=:source_id ORDER BY version DESC LIMIT 1"
                        ),
                        {"source_id": source_id},
                    )
                )
                .mappings()
                .first()
            )
        if row is None:
            raise SourceNotFound("source auto score does not exist")
        return SourceAutoScoreDetailView.model_validate(dict(row))

    async def get_source_profile(self, source_id: UUID) -> SourceProfileView:
        async with self._engine.connect() as connection:
            snapshot = (
                (
                    await connection.execute(
                        text(
                            "SELECT * FROM source_profile_snapshot WHERE source_id=:source_id ORDER BY version DESC LIMIT 1"
                        ),
                        {"source_id": source_id},
                    )
                )
                .mappings()
                .first()
            )
            override = (
                (
                    await connection.execute(
                        text(
                            "SELECT id,action,values FROM source_profile_override WHERE source_id=:source_id ORDER BY created_at DESC,id DESC LIMIT 1"
                        ),
                        {"source_id": source_id},
                    )
                )
                .mappings()
                .first()
            )
        if snapshot is None:
            raise SourceNotFound("source profile does not exist")
        return _source_profile_view(snapshot, override)

    async def patch_source_profile_override(
        self,
        source_id: UUID,
        payload: SourceProfileOverrideRequest,
        *,
        actor_id: UUID,
        request_id: str,
        now: datetime,
    ) -> SourceProfileView:
        async with self._engine.begin() as connection:
            exists = await connection.scalar(
                text("SELECT EXISTS(SELECT 1 FROM source WHERE id=:source_id)"),
                {"source_id": source_id},
            )
            if not exists:
                raise SourceNotFound("source does not exist")
            current = (
                (
                    await connection.execute(
                        text(
                            "SELECT id,action,values FROM source_profile_override WHERE source_id=:source_id ORDER BY created_at DESC,id DESC LIMIT 1 FOR UPDATE"
                        ),
                        {"source_id": source_id},
                    )
                )
                .mappings()
                .first()
            )
            values = (
                dict(current["values"])
                if current is not None and current["action"] == "APPLY"
                else {}
            )
            for field in payload.model_fields_set:
                value = getattr(payload, field)
                if value is None:
                    values.pop(field, None)
                else:
                    values[field] = (
                        [getattr(item, "value", item) for item in value]
                        if isinstance(value, list)
                        else getattr(value, "value", value)
                    )
            action = "APPLY" if values else "REVOKE"
            await connection.execute(
                text(
                    "INSERT INTO source_profile_override(id,source_id,action,values,supersedes_id,actor_id,request_id,created_at) VALUES(:id,:source_id,:action,CAST(:values AS jsonb),:supersedes_id,:actor_id,:request_id,:now)"
                ),
                {
                    "id": uuid7(),
                    "source_id": source_id,
                    "action": action,
                    "values": json.dumps(values, ensure_ascii=False, sort_keys=True),
                    "supersedes_id": None if current is None else current["id"],
                    "actor_id": actor_id,
                    "request_id": request_id,
                    "now": now,
                },
            )
        return await self.get_source_profile(source_id)

    async def revoke_source_profile_override(
        self, source_id: UUID, *, actor_id: UUID, request_id: str, now: datetime
    ) -> SourceProfileView:
        async with self._engine.begin() as connection:
            current = (
                (
                    await connection.execute(
                        text(
                            "SELECT id,action FROM source_profile_override WHERE source_id=:source_id ORDER BY created_at DESC,id DESC LIMIT 1 FOR UPDATE"
                        ),
                        {"source_id": source_id},
                    )
                )
                .mappings()
                .first()
            )
            if current is not None and current["action"] == "APPLY":
                await connection.execute(
                    text(
                        "INSERT INTO source_profile_override(id,source_id,action,values,supersedes_id,actor_id,request_id,created_at) VALUES(:id,:source_id,'REVOKE','{}'::jsonb,:supersedes_id,:actor_id,:request_id,:now)"
                    ),
                    {
                        "id": uuid7(),
                        "source_id": source_id,
                        "supersedes_id": current["id"],
                        "actor_id": actor_id,
                        "request_id": request_id,
                        "now": now,
                    },
                )
        return await self.get_source_profile(source_id)

    async def create_personal_source(
        self,
        payload: PersonalSourceCreateRequest,
        *,
        actor_id: UUID,
        request_id: str,
        now: datetime,
    ) -> PersonalSourceRow:
        from srbg_api.personal_source_probe import normalize_public_https_url

        normalized_url, origin, host = normalize_public_https_url(payload.url)
        async with self._engine.begin() as connection:
            await connection.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:origin,0))"),
                {"origin": origin},
            )
            source_id = await connection.scalar(
                text(
                    "SELECT id FROM source WHERE normalized_origin=:origin OR (normalized_origin IS NULL AND lower(split_part(base_url,'/',3))=:host AND lower(split_part(base_url,':',1))='https') ORDER BY normalized_origin NULLS LAST,registry_code NULLS LAST,id LIMIT 1 FOR UPDATE"
                ),
                {"origin": origin, "host": host},
            )
            if source_id is None:
                source_id = uuid7()
                await connection.execute(
                    text(
                        "SELECT register_source_candidate(:id,:name,:origin,'BOTH','personal_public','B2','P2','auto_probe',1440,'Local Personal Owner',NULL,ARRAY[]::text[],ARRAY[]::text[],ARRAY[]::text[],ARRAY[]::text[],ARRAY[]::text[],ARRAY[]::text[],:actor_id,:request_id,:audit_id,:now)"
                    ),
                    {
                        "id": source_id,
                        "name": host,
                        "origin": origin,
                        "actor_id": actor_id,
                        "request_id": request_id,
                        "audit_id": uuid7(),
                        "now": now,
                    },
                )
                await connection.execute(
                    text(
                        "UPDATE source SET normalized_origin=:origin,desired_enabled=true,runtime_state='PENDING_CONFIGURATION',updated_at=:now WHERE id=:source_id"
                    ),
                    {"origin": origin, "now": now, "source_id": source_id},
                )
            elif await connection.scalar(
                text("SELECT normalized_origin IS NULL FROM source WHERE id=:source_id"),
                {"source_id": source_id},
            ):
                await connection.execute(
                    text(
                        "UPDATE source SET normalized_origin=:origin,updated_at=:now WHERE id=:source_id"
                    ),
                    {"origin": origin, "now": now, "source_id": source_id},
                )
            stream_id = await connection.scalar(
                text(
                    "SELECT id FROM source_stream WHERE source_id=:source_id AND canonical_url=:url FOR UPDATE"
                ),
                {"source_id": source_id, "url": normalized_url},
            )
            if stream_id is None:
                stream_id = uuid7()
                await connection.execute(
                    text(
                        "INSERT INTO source_stream(id,source_id,stream_key,name,canonical_url,authorization_boundary,status,rule_version,automatically_managed,created_at,updated_at,stream_type,allowed_hosts,discovery_method) VALUES(:id,:source_id,:stream_key,:name,:url,CAST(:host AS varchar(253)),'PROBING','personal-source-probe-v1',false,:now,:now,'UNKNOWN',ARRAY[CAST(:host AS varchar(253))],'MANUAL_URL')"
                    ),
                    {
                        "id": stream_id,
                        "source_id": source_id,
                        "stream_key": "URL_" + sha256(normalized_url.encode()).hexdigest()[:24],
                        "name": normalized_url,
                        "url": normalized_url,
                        "host": host,
                        "now": now,
                    },
                )
            active = await connection.scalar(
                text(
                    "SELECT id FROM stream_probe_run WHERE source_id=:source_id AND normalized_url=:url AND status IN ('QUEUED','RUNNING') LIMIT 1"
                ),
                {"source_id": source_id, "url": normalized_url},
            )
            healthy = await connection.scalar(
                text("SELECT status='READY' FROM source_stream WHERE id=:stream_id"),
                {"stream_id": stream_id},
            )
            if active is None and (not healthy):
                await connection.execute(
                    text(
                        "INSERT INTO stream_probe_run(id,source_id,stream_id,requested_url,normalized_url,normalized_origin,input_kind,status,requested_by,request_id,created_at,updated_at) VALUES(:id,:source_id,:stream_id,:url,:url,:origin,'UNKNOWN','QUEUED',:actor_id,:request_id,:now,:now)"
                    ),
                    {
                        "id": uuid7(),
                        "source_id": source_id,
                        "stream_id": stream_id,
                        "url": normalized_url,
                        "origin": origin,
                        "actor_id": actor_id,
                        "request_id": request_id,
                        "now": now,
                    },
                )
        return await self.get_personal_source(source_id)

    async def reprobe_personal_source(
        self,
        source_id: UUID,
        payload: PersonalSourceReprobeRequest,
        *,
        actor_id: UUID,
        request_id: str,
        now: datetime,
    ) -> PersonalSourceRow:
        async with self._engine.begin() as connection:
            if payload.stream_id is not None:
                row = (
                    (
                        await connection.execute(
                            text(
                                "SELECT id,canonical_url FROM source_stream WHERE id=:stream_id AND source_id=:source_id FOR UPDATE"
                            ),
                            {"stream_id": payload.stream_id, "source_id": source_id},
                        )
                    )
                    .mappings()
                    .first()
                )
            else:
                row = (
                    (
                        await connection.execute(
                            text(
                                "SELECT stream_id AS id,normalized_url AS canonical_url FROM stream_probe_run WHERE source_id=:source_id ORDER BY created_at DESC LIMIT 1 FOR UPDATE"
                            ),
                            {"source_id": source_id},
                        )
                    )
                    .mappings()
                    .first()
                )
            if row is None:
                raise SourceNotFound("source stream does not exist")
            active = await connection.scalar(
                text(
                    "SELECT id FROM stream_probe_run WHERE source_id=:source_id AND normalized_url=:url AND status IN ('QUEUED','RUNNING') LIMIT 1"
                ),
                {"source_id": source_id, "url": row["canonical_url"]},
            )
            if active is None:
                origin = await connection.scalar(
                    text("SELECT normalized_origin FROM source WHERE id=:source_id"),
                    {"source_id": source_id},
                )
                if origin is None:
                    raise SourceNotFound("personal source origin does not exist")
                await connection.execute(
                    text(
                        "INSERT INTO stream_probe_run(id,source_id,stream_id,requested_url,normalized_url,normalized_origin,input_kind,status,requested_by,request_id,created_at,updated_at) VALUES(:id,:source_id,:stream_id,:url,:url,:origin,'UNKNOWN','QUEUED',:actor_id,:request_id,:now,:now)"
                    ),
                    {
                        "id": uuid7(),
                        "source_id": source_id,
                        "stream_id": row["id"],
                        "url": row["canonical_url"],
                        "origin": origin,
                        "actor_id": actor_id,
                        "request_id": request_id,
                        "now": now,
                    },
                )
                await connection.execute(
                    text(
                        "UPDATE source_stream SET status='PROBING',failure_reason=NULL,updated_at=:now WHERE id=:stream_id AND status NOT IN ('ACTIVE','QUALIFIED','READY')"
                    ),
                    {"now": now, "stream_id": row["id"]},
                )
        return await self.get_personal_source(source_id)

    async def _personal_source_with_probe(self, base: PersonalSourceRow) -> PersonalSourceRow:
        async with self._engine.connect() as connection:
            stream_rows = (
                (
                    await connection.execute(
                        text(
                            "SELECT stream.id,stream.stream_type,stream.canonical_url,\n                                      stream.allowed_hosts,stream.config_sha256,\n                                      stream.discovery_method,stream.status,stream.failure_reason,\n                                      schedule.status AS schedule_status,schedule.circuit_state,\n                                      schedule.circuit_open_until,schedule.access_state,\n                                      schedule.requests_used,schedule.daily_request_budget,\n                                      schedule.bytes_used,schedule.daily_byte_budget,\n                                      schedule.health_status,schedule.health_reason,\n                                      schedule.consecutive_failures,schedule.next_self_heal_at,\n                                      schedule.last_successful_fetch_at,\n                                      schedule.last_content_discovered_at\n                                      ,observation.id AS health_observation_id,\n                                      observation.observed_at AS health_observed_at\n                                 FROM source_stream stream\n                                 LEFT JOIN fetch_schedule schedule\n                                   ON schedule.source_stream_id=stream.id\n                                  AND schedule.authority_mode='PERSONAL_STREAM'\n                                LEFT JOIN LATERAL (\n                                  SELECT snapshot.id,snapshot.observed_at\n                                    FROM source_health_snapshot snapshot\n                                   WHERE snapshot.source_stream_id=stream.id\n                                   ORDER BY snapshot.observed_at DESC,snapshot.id DESC LIMIT 1\n                                ) observation ON true\n                                WHERE stream.source_id=:source_id\n                                  AND stream.status IN ('PROBING','READY','PROBE_FAILED')\n                                ORDER BY stream.created_at,stream.id"
                        ),
                        {"source_id": base.id},
                    )
                )
                .mappings()
                .all()
            )
            run = (
                (
                    await connection.execute(
                        text(
                            "SELECT id,requested_url,input_kind,status,duration_ms,failure_code,failure_reason FROM stream_probe_run WHERE source_id=:source_id ORDER BY created_at DESC,id DESC LIMIT 1"
                        ),
                        {"source_id": base.id},
                    )
                )
                .mappings()
                .first()
            )
            profile = (
                (
                    await connection.execute(
                        text(
                            "SELECT snapshot.status,snapshot.overall_confidence,\n                                        snapshot.generated_at,\n                                        COALESCE(override.values,'{}'::jsonb) AS override_values,\n                                        override.action AS override_action\n                                   FROM source_profile_snapshot snapshot\n                                   LEFT JOIN LATERAL (\n                                     SELECT action,values FROM source_profile_override item\n                                      WHERE item.source_id=snapshot.source_id\n                                      ORDER BY created_at DESC,id DESC LIMIT 1\n                                   ) override ON true\n                                  WHERE snapshot.source_id=:source_id\n                                  ORDER BY snapshot.version DESC LIMIT 1"
                        ),
                        {"source_id": base.id},
                    )
                )
                .mappings()
                .first()
            )
        streams = tuple(
            PersonalStreamRow(
                id=row["id"],
                stream_type=PersonalSourceStreamType(row["stream_type"]),
                normalized_url=row["canonical_url"],
                allowed_hosts=tuple(row["allowed_hosts"]),
                config_sha256=row["config_sha256"],
                discovery_method=row["discovery_method"],
                status=PersonalSourceStreamStatus(row["status"]),
                failure_reason=row["failure_reason"],
                actual_running=_personal_stream_actual_running(base, row),
                runtime_state=_personal_stream_runtime_state(base, row),
                health_status=PersonalStreamHealthStatus(row.get("health_status") or "UNKNOWN"),
                health_reason=_personal_health_reason(row.get("health_reason")),
                consecutive_failures=int(row.get("consecutive_failures") or 0),
                next_self_heal_at=row.get("next_self_heal_at"),
                last_successful_fetch_at=row.get("last_successful_fetch_at"),
                last_content_discovered_at=row.get("last_content_discovered_at"),
                health_observation_id=row.get("health_observation_id"),
                health_observed_at=row.get("health_observed_at"),
            )
            for row in stream_rows
        )
        latest = (
            None
            if run is None
            else ProbeRunRow(
                id=run["id"],
                requested_url=run["requested_url"],
                input_kind=PersonalSourceInputKind(run["input_kind"]),
                status=PersonalSourceProbeStatus(run["status"]),
                duration_ms=run["duration_ms"],
                failure_code=run["failure_code"],
                failure_reason=run["failure_reason"],
            )
        )
        projected_runtime = (
            PersonalSourceRuntimeState.RUNNING
            if any(stream.actual_running for stream in streams)
            else PersonalSourceRuntimeState.PENDING_CONFIGURATION
            if not any(stream.status is PersonalSourceStreamStatus.READY for stream in streams)
            else PersonalSourceRuntimeState.ERROR
            if base.desired_enabled
            and any(
                stream.health_status is PersonalStreamHealthStatus.UNHEALTHY for stream in streams
            )
            else PersonalSourceRuntimeState.STOPPED
        )
        return PersonalSourceRow(
            base.id,
            base.display_name,
            base.url,
            base.desired_enabled,
            projected_runtime,
            base.manual_disabled_at,
            base.normalized_origin,
            streams,
            latest,
            base.auto_score_summary,
            None
            if profile is None
            else SourceProfileSummaryView(
                status=profile["status"],
                overall_confidence=profile["overall_confidence"],
                overridden_fields=list(profile["override_values"])
                if profile["override_action"] == "APPLY"
                else [],
                generated_at=profile["generated_at"],
            ),
        )

    async def patch_personal_source(
        self,
        source_id: UUID,
        payload: PersonalSourcePatchRequest,
        *,
        actor_id: UUID,
        request_id: str,
        now: datetime,
    ) -> PersonalSourceRow:
        async with self._engine.begin() as connection:
            row = (
                (
                    await connection.execute(
                        text(
                            "\n                            SELECT id,name,base_url,desired_enabled,runtime_state,\n                                   manual_disabled_at,enabled\n                              FROM source WHERE id=:source_id FOR UPDATE\n                            "
                        ),
                        {"source_id": source_id},
                    )
                )
                .mappings()
                .first()
            )
            if row is None:
                raise SourceNotFound("source does not exist")
            display_name = row["name"]
            desired_enabled = row["desired_enabled"]
            manual_disabled_at = row["manual_disabled_at"]
            legacy_enabled = row["enabled"]
            event_types: list[str] = []
            if "display_name" in payload.model_fields_set:
                display_name_value = payload.display_name
                if display_name_value is None:
                    raise ValueError("display_name must not be null")
                if display_name_value != display_name:
                    display_name = display_name_value
                    event_types.append("DISPLAY_NAME_CHANGED")
            if "desired_enabled" in payload.model_fields_set:
                desired_enabled_value = payload.desired_enabled
                if desired_enabled_value is None:
                    raise ValueError("desired_enabled must not be null")
                if desired_enabled_value:
                    if not desired_enabled or manual_disabled_at is not None:
                        event_types.append("MANUAL_ENABLED")
                    desired_enabled = True
                    manual_disabled_at = None
                else:
                    if manual_disabled_at is None:
                        manual_disabled_at = now
                        event_types.append("MANUAL_DISABLED")
                    desired_enabled = False
                    legacy_enabled = False
            before_state = _personal_state(row)
            after_state = {
                "display_name": display_name,
                "desired_enabled": desired_enabled,
                "runtime_state": row["runtime_state"],
                "manual_disabled_at": _iso_or_none(manual_disabled_at),
            }
            if before_state != after_state or legacy_enabled != row["enabled"]:
                await connection.execute(
                    text(
                        "\n                        UPDATE source\n                           SET name=:display_name,desired_enabled=:desired_enabled,\n                               manual_disabled_at=:manual_disabled_at,enabled=:legacy_enabled,\n                               updated_at=:updated_at\n                         WHERE id=:source_id\n                        "
                    ),
                    {
                        "display_name": display_name,
                        "desired_enabled": desired_enabled,
                        "manual_disabled_at": manual_disabled_at,
                        "legacy_enabled": legacy_enabled,
                        "updated_at": now,
                        "source_id": source_id,
                    },
                )
                await connection.execute(
                    text(
                        "\n                        UPDATE fetch_schedule\n                           SET status=CASE\n                                 WHEN :runtime_allowed\n                                   THEN 'ACTIVE'\n                                 ELSE 'PAUSED'\n                               END,\n                               next_run_at=CASE\n                                 WHEN :runtime_allowed\n                                   THEN LEAST(next_run_at,:updated_at)\n                                 ELSE next_run_at\n                               END,\n                               updated_at=:updated_at\n                         WHERE source_id=:source_id\n                           AND authority_mode='PERSONAL_STREAM'\n                        "
                    ),
                    {
                        "runtime_allowed": desired_enabled and manual_disabled_at is None,
                        "updated_at": now,
                        "source_id": source_id,
                    },
                )
            for event_type in event_types:
                await connection.execute(
                    text(
                        "\n                        INSERT INTO source_key_activity_event(\n                            id,source_id,event_type,actor_id,request_id,\n                            before_state,after_state,created_at\n                        ) VALUES(\n                            :id,:source_id,:event_type,:actor_id,:request_id,\n                            CAST(:before_state AS jsonb),CAST(:after_state AS jsonb),:created_at\n                        )\n                        "
                    ),
                    {
                        "id": uuid7(),
                        "source_id": source_id,
                        "event_type": event_type,
                        "actor_id": actor_id,
                        "request_id": request_id,
                        "before_state": _json(before_state),
                        "after_state": _json(after_state),
                        "created_at": now,
                    },
                )
        return await self.get_personal_source(source_id)


def _personal_source_row(row: RowMapping) -> PersonalSourceRow:
    score = (
        None
        if row.get("score_id") is None
        else SourceAutoScoreSummaryView(
            snapshot_id=row["score_id"],
            total_score=row["total_score"],
            eligible=row["auto_enable_eligible"],
            reason_codes=list(row["score_reason_codes"]),
            rule_version=row["score_rule_version"],
            evaluated_at=row["score_evaluated_at"],
        )
    )
    return PersonalSourceRow(
        id=row["id"],
        display_name=row["name"],
        url=row["base_url"],
        desired_enabled=row["desired_enabled"],
        runtime_state=PersonalSourceRuntimeState(row["runtime_state"]),
        manual_disabled_at=row["manual_disabled_at"],
        normalized_origin=row.get("normalized_origin"),
        auto_score_summary=score,
    )


def _source_profile_view(snapshot: RowMapping, override: RowMapping | None) -> SourceProfileView:
    automatic = {
        "industries": list(snapshot["industries"]),
        "content_domains": list(snapshot["content_domains"]),
        "language_tags": list(snapshot["language_tags"]),
        "country_codes": list(snapshot["country_codes"]),
        "region_codes": list(snapshot["region_codes"]),
        "declared_roles": list(snapshot["declared_roles"]),
        "authority_level": snapshot["authority_level"],
        "independence_level": snapshot["independence_level"],
    }
    override_values = (
        dict(override["values"]) if override is not None and override["action"] == "APPLY" else {}
    )
    effective = {**automatic, **override_values}
    explanations = dict(snapshot["field_explanations"])
    for field in override_values:
        existing = dict(explanations.get(field, {}))
        explanations[field] = {**existing, "basis": "PERSONAL_OVERRIDE"}
    raw_facts = list(snapshot["technical_facts"])
    technical_facts = [
        str(item.get("code")) if isinstance(item, dict) else str(item) for item in raw_facts
    ]
    return SourceProfileView.model_validate(
        {
            "snapshot_id": snapshot["id"],
            "version": snapshot["version"],
            "status": snapshot["status"],
            "automatic": automatic,
            "effective": effective,
            "field_explanations": explanations,
            "overall_confidence": snapshot["overall_confidence"],
            "overridden_fields": sorted(override_values),
            "evidence": snapshot["evidence"],
            "technical_facts": technical_facts,
            "reason_codes": list(snapshot["reason_codes"]),
            "rule_version": snapshot["rule_version"],
            "prompt_version": snapshot["prompt_version"],
            "schema_version": snapshot["schema_version"],
            "model_version": snapshot["model_version"],
            "input_sha256": snapshot["input_sha256"],
            "generated_at": snapshot["generated_at"],
        }
    )


def _personal_stream_actual_running(base: PersonalSourceRow, row: RowMapping) -> bool:
    request_budget = int(row.get("daily_request_budget") or 0)
    byte_budget = int(row.get("daily_byte_budget") or 0)
    return bool(
        base.desired_enabled
        and base.manual_disabled_at is None
        and (row.get("status") == PersonalSourceStreamStatus.READY.value)
        and (row.get("schedule_status") == "ACTIVE")
        and (row.get("access_state") == "ACCESSIBLE")
        and (int(row.get("requests_used") or 0) < request_budget)
        and (int(row.get("bytes_used") or 0) < byte_budget)
        and (row.get("circuit_state") in {"CLOSED", "HALF_OPEN"})
    )


def _encode_personal_activity_cursor(occurred_at: datetime, item_id: UUID) -> str:
    value = json.dumps(
        {"at": occurred_at.isoformat(), "id": str(item_id)}, separators=(",", ":")
    ).encode()
    return base64.urlsafe_b64encode(value).decode().rstrip("=")


def _decode_personal_activity_cursor(value: str | None) -> tuple[datetime | None, UUID | None]:
    if value is None:
        return (None, None)
    try:
        decoded = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
        payload = json.loads(decoded)
        occurred_at = datetime.fromisoformat(payload["at"])
        if occurred_at.tzinfo is None:
            raise ValueError("cursor time must be timezone-aware")
        return (occurred_at, UUID(payload["id"]))
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise ValueError("invalid personal source activity cursor") from error


def _personal_stream_runtime_state(
    base: PersonalSourceRow, row: RowMapping
) -> PersonalStreamRuntimeState:
    if not base.desired_enabled or base.manual_disabled_at is not None:
        return PersonalStreamRuntimeState.STOPPED
    if row.get("access_state") == "INACCESSIBLE":
        return PersonalStreamRuntimeState.INACCESSIBLE
    if int(row.get("requests_used") or 0) >= int(row.get("daily_request_budget") or 0) or int(
        row.get("bytes_used") or 0
    ) >= int(row.get("daily_byte_budget") or 0):
        return PersonalStreamRuntimeState.BUDGET_EXHAUSTED
    if row.get("circuit_state") == "OPEN":
        return PersonalStreamRuntimeState.CIRCUIT_OPEN
    if row.get("circuit_state") == "HALF_OPEN":
        return PersonalStreamRuntimeState.HALF_OPEN
    if _personal_stream_actual_running(base, row):
        return PersonalStreamRuntimeState.SCHEDULED
    return PersonalStreamRuntimeState.STOPPED


def _personal_health_reason(value: object) -> PersonalStreamHealthReason | None:
    if not isinstance(value, str):
        return None
    try:
        return PersonalStreamHealthReason(value)
    except ValueError:
        return None


def _iso_or_none(value: datetime | None) -> str | None:
    return None if value is None else value.isoformat()


def _personal_state(row: RowMapping) -> dict[str, Any]:
    return {
        "display_name": row["name"],
        "desired_enabled": row["desired_enabled"],
        "runtime_state": row["runtime_state"],
        "manual_disabled_at": _iso_or_none(row["manual_disabled_at"]),
    }


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def canonical_json_hash(value: dict[str, Any]) -> str:
    return sha256(_json(value).encode()).hexdigest()
