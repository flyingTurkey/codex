"""PostgreSQL persistence for source admission and immutable document versions."""

import base64
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from typing import Any, Literal
from urllib.parse import urlsplit
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import RowMapping
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine
from srbg_contracts import (
    ConnectorConfigVersionView,
    ConnectorDefinitionView,
    ConnectorType,
    CreateSourceRequest,
    DiscoveryDailyUsageView,
    DiscoveryTopicPatchRequest,
    DiscoveryTopicView,
    DocumentDetail,
    DocumentVersionSummary,
    FixtureUploadResponse,
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
    RawObjectSummary,
    ScanStatus,
    SourceAssessmentSubmission,
    SourceAuthorityAssessment,
    SourceAutoScoreDetailView,
    SourceAutoScoreSummaryView,
    SourceContentDomain,
    SourceCoverageCell,
    SourceCoverageMatrix,
    SourceGovernanceMetadataUpdate,
    SourceIndependenceAssessment,
    SourceIndustry,
    SourceLifecycleEventView,
    SourceLifecycleState,
    SourcePolicyDecisionOutcome,
    SourcePolicyV2Submission,
    SourcePolicyVersionView,
    SourceProfileOverrideRequest,
    SourceProfileSummaryView,
    SourceProfileView,
    SourceState,
    SourceTrialKind,
    SourceTrialQualitySummary,
    SourceTrialRunRequest,
    SourceTrialRunStatus,
    SourceTrialRunView,
    SourceType,
)

from srbg_api.document_vault.service import (
    AttachmentAttemptRecord,
    AttachmentRecord,
    FixtureRecord,
    RejectedRawRecord,
)
from srbg_api.identifiers import uuid7

ROUND17_TWO_PERSON_GOVERNANCE_SCHEME = "R17_TWO_PERSON_MAKER_CHECKER_V1"
LEGACY_GOVERNANCE_SCHEME = "FOUR_PERSON_SEPARATION_V1"


class SourceNotFound(LookupError):
    pass


class RepositoryConflict(RuntimeError):
    pass


def _governance_separation_actor_ids(
    *,
    scheme: str,
    maker_actor_ids: frozenset[UUID],
    prior_approver_actor_ids: frozenset[UUID],
) -> frozenset[UUID]:
    """Return actors forbidden from the next approval.

    The bounded R17 cohort permits one independent checker to perform separate
    approval actions.  It never permits a maker to approve.  Unknown schemes
    deliberately inherit the stricter legacy rule.
    """

    if scheme == ROUND17_TWO_PERSON_GOVERNANCE_SCHEME:
        return maker_actor_ids
    return maker_actor_ids | prior_approver_actor_ids


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
    lifecycle_state: SourceLifecycleState
    trial_kind: SourceTrialKind | None
    registered_by: UUID | None
    governance_owner_id: UUID | None
    country_codes: tuple[str, ...]
    region_codes: tuple[str, ...]
    language_tags: tuple[str, ...]
    industries: tuple[str, ...]
    content_domains: tuple[str, ...]
    declared_roles: tuple[str, ...]
    current_policy_version_id: UUID | None
    current_connector_config_version_id: UUID | None
    current_trial_run_id: UUID | None
    created_at: datetime


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


@dataclass(frozen=True, slots=True)
class LifecycleFacts:
    policy_valid: bool
    policy_valid_until: datetime | None
    robots_allowed: bool
    terms_allowed: bool
    copyright_allowed: bool
    governance_owner_present: bool
    compliance_approved: bool
    connector_config_current: bool
    trial_kind: SourceTrialKind | None
    live_trial_succeeded: bool
    production_approval_current: bool
    separation_actor_ids: frozenset[UUID]
    current_trial_pending: bool = False


@dataclass(frozen=True, slots=True)
class FixtureReplayCapture:
    id: UUID
    raw_object_id: UUID
    object_key: str
    content_sha256: str
    byte_size: int
    declared_mime: str
    detected_mime: str
    requested_url: str
    final_url: str
    http_status: int
    etag: str | None
    last_modified: str | None
    filename: str
    title: str | None
    captured_at: datetime


@dataclass(frozen=True, slots=True)
class FixtureReplayBundle:
    source_id: UUID
    trial_run_id: UUID
    connector_config_version_id: UUID
    connector_type: str
    config_document: dict[str, Any]
    allowed_hosts: tuple[str, ...]
    replay_status: str | None
    captures: tuple[FixtureReplayCapture, ...]


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
                        """
                        SELECT source.id,source.name,source.base_url,source.desired_enabled,
                               source.runtime_state,source.manual_disabled_at,
                               source.normalized_origin,score.id AS score_id,
                               score.total_score,score.auto_enable_eligible,
                               score.reason_codes AS score_reason_codes,
                               score.rule_version AS score_rule_version,
                               score.evaluated_at AS score_evaluated_at
                          FROM source
                          LEFT JOIN LATERAL (
                            SELECT id,total_score,auto_enable_eligible,reason_codes,
                                   rule_version,evaluated_at
                              FROM source_auto_score_snapshot snapshot
                             WHERE snapshot.source_id=source.id
                             ORDER BY version DESC LIMIT 1
                          ) score ON true
                         ORDER BY lower(source.name),source.id
                        """
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
                            """
                            SELECT source.id,source.name,source.base_url,
                                   source.desired_enabled,source.runtime_state,
                                   source.manual_disabled_at,source.normalized_origin,
                                   score.id AS score_id,score.total_score,
                                   score.auto_enable_eligible,
                                   score.reason_codes AS score_reason_codes,
                                   score.rule_version AS score_rule_version,
                                   score.evaluated_at AS score_evaluated_at
                              FROM source
                              LEFT JOIN LATERAL (
                                SELECT id,total_score,auto_enable_eligible,reason_codes,
                                       rule_version,evaluated_at
                                  FROM source_auto_score_snapshot snapshot
                                 WHERE snapshot.source_id=source.id
                                 ORDER BY version DESC LIMIT 1
                              ) score ON true
                             WHERE source.id=:source_id
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
                            """
                            WITH activity AS (
                              SELECT event.id,
                                CASE event.event_type
                                  WHEN 'MANUAL_ENABLED' THEN 'OWNER_ENABLED'
                                  WHEN 'MANUAL_DISABLED' THEN 'OWNER_DISABLED'
                                  WHEN 'AUTO_ENABLED' THEN 'AUTO_ENABLED'
                                  ELSE 'DISPLAY_NAME_CHANGED'
                                END AS kind,
                                event.created_at AS occurred_at,NULL::uuid AS stream_id,
                                event.event_type AS status,NULL::text AS reason_code,
                                NULL::integer AS discovered_count,NULL::integer AS fetched_count,
                                NULL::integer AS failed_count
                              FROM source_key_activity_event event WHERE event.source_id=:source_id
                              UNION ALL
                              SELECT probe.id,'URL_PROBE',probe.updated_at,probe.stream_id,
                                probe.status,probe.failure_code,NULL,NULL,NULL
                              FROM stream_probe_run probe WHERE probe.source_id=:source_id
                              UNION ALL
                                SELECT run.id,'COLLECTION_RUN',
                                  COALESCE(run.completed_at,run.started_at),
                                run.source_stream_id,run.status,run.error_code,
                                run.discovered_count,run.fetched_count,run.failed_count
                              FROM fetch_run run WHERE run.source_id=:source_id
                            )
                            SELECT * FROM activity
                              WHERE (CAST(:cursor_at AS timestamptz) IS NULL OR
                                (occurred_at,id)<(
                                  CAST(:cursor_at AS timestamptz),CAST(:cursor_id AS uuid)
                                ))
                            ORDER BY occurred_at DESC,id DESC LIMIT :row_limit
                            """
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
                            """SELECT status,COALESCE(completed_at,started_at) AS run_at,
                                      discovered_count,fetched_count,failed_count
                                 FROM fetch_run WHERE source_id=:source_id
                                 ORDER BY started_at DESC,id DESC LIMIT 1"""
                        ),
                        {"source_id": source_id},
                    )
                )
                .mappings()
                .first()
            )
            next_run_at = await connection.scalar(
                text(
                    "SELECT MIN(next_run_at) FROM fetch_schedule "
                    "WHERE source_id=:source_id AND authority_mode='PERSONAL_STREAM'"
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
                            "SELECT automation_enabled,updated_at FROM personal_automation_setting "
                            "WHERE singleton_slot=1"
                        )
                    )
                )
                .mappings()
                .one()
            )
        return AutomationSettingRow(row["automation_enabled"], row["updated_at"])

    async def patch_discovery_setting(
        self,
        enabled: bool,
        *,
        actor_id: UUID,
        request_id: str,
        now: datetime,
    ) -> AutomationSettingRow:
        async with self._engine.begin() as connection:
            before = await connection.scalar(
                text(
                    "SELECT automation_enabled FROM personal_automation_setting "
                    "WHERE singleton_slot=1 FOR UPDATE"
                )
            )
            if not isinstance(before, bool):
                raise RepositoryConflict("personal automation setting does not exist")
            await connection.execute(
                text(
                    "UPDATE personal_automation_setting SET automation_enabled=:enabled,"
                    "updated_at=:now WHERE singleton_slot=1"
                ),
                {"enabled": enabled, "now": now},
            )
            if before != enabled:
                await connection.execute(
                    text(
                        "INSERT INTO personal_discovery_setting_event(id,actor_id,request_id,"
                        "before_enabled,after_enabled,created_at) "
                        "VALUES(:id,:actor_id,:request_id,:before,:after,:now)"
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
                        "SELECT id,code,name,keywords,excluded_terms,focus_regions,enabled,"
                        "version,updated_at FROM discovery_topic ORDER BY code"
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
                            "SELECT id,code,name,keywords,excluded_terms,focus_regions,enabled,"
                            "version,updated_at FROM discovery_topic WHERE id=:id FOR UPDATE"
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
                            "UPDATE discovery_topic SET keywords=:keywords,"
                            "excluded_terms=:excluded,focus_regions=:regions,"
                            "enabled=:enabled,version=version+1,updated_at=:now "
                            "WHERE id=:id RETURNING id,code,name,keywords,"
                            "excluded_terms,focus_regions,"
                            "enabled,version,updated_at"
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
                    "INSERT INTO discovery_topic_event(id,topic_id,actor_id,request_id,"
                    "before_state,after_state,created_at) VALUES(:id,:topic,:actor,:request,"
                    "CAST(:before AS jsonb),CAST(:after AS jsonb),:now)"
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
                            "SELECT personal_discovery_local_date(:now) AS local_date,"
                            "COALESCE((SELECT used_count FROM "
                            "personal_probe_daily_ledger "
                            "WHERE local_date=personal_discovery_local_date(:now)),0) "
                            "AS probe_used,"
                            "COALESCE((SELECT used_count FROM "
                            "personal_auto_enable_daily_ledger WHERE "
                            "local_date=personal_discovery_local_date(:now)),0) "
                            "AS enable_used"
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
                            "SELECT id AS snapshot_id,source_id,total_score,auto_enable_eligible "
                            "AS eligible,reason_codes,rule_version,evaluated_at,"
                            "topic_relevance_score,connector_stability_score,"
                            "sample_completeness_score,profile_evidence_score,"
                            "content_validity_score,component_explanations,hard_gate_results,"
                            "evidence_refs FROM source_auto_score_snapshot "
                            "WHERE source_id=:source_id ORDER BY version DESC LIMIT 1"
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
                            "SELECT * FROM source_profile_snapshot WHERE source_id=:source_id "
                            "ORDER BY version DESC LIMIT 1"
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
                            "SELECT id,action,values FROM source_profile_override "
                            "WHERE source_id=:source_id ORDER BY created_at DESC,id DESC LIMIT 1"
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
                            "SELECT id,action,values FROM source_profile_override "
                            "WHERE source_id=:source_id ORDER BY created_at DESC,id DESC "
                            "LIMIT 1 FOR UPDATE"
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
                    "INSERT INTO source_profile_override(id,source_id,action,values,supersedes_id,"
                    "actor_id,request_id,created_at) VALUES(:id,:source_id,:action,"
                    "CAST(:values AS jsonb),:supersedes_id,:actor_id,:request_id,:now)"
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
        self,
        source_id: UUID,
        *,
        actor_id: UUID,
        request_id: str,
        now: datetime,
    ) -> SourceProfileView:
        async with self._engine.begin() as connection:
            current = (
                (
                    await connection.execute(
                        text(
                            "SELECT id,action FROM source_profile_override "
                            "WHERE source_id=:source_id "
                            "ORDER BY created_at DESC,id DESC LIMIT 1 FOR UPDATE"
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
                        "INSERT INTO source_profile_override(id,source_id,action,values,"
                        "supersedes_id,actor_id,request_id,created_at) VALUES(:id,:source_id,"
                        "'REVOKE','{}'::jsonb,:supersedes_id,:actor_id,:request_id,:now)"
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
                    "SELECT id FROM source WHERE normalized_origin=:origin OR "
                    "(normalized_origin IS NULL AND lower(split_part(base_url,'/',3))=:host "
                    "AND lower(split_part(base_url,':',1))='https') "
                    "ORDER BY normalized_origin NULLS LAST,registry_code NULLS LAST,id "
                    "LIMIT 1 FOR UPDATE"
                ),
                {"origin": origin, "host": host},
            )
            if source_id is None:
                source_id = uuid7()
                await connection.execute(
                    text(
                        "SELECT register_source_candidate(:id,:name,:origin,'BOTH',"
                        "'personal_public','B2','P2','auto_probe',1440,"
                        "'Local Personal Owner',NULL,ARRAY[]::text[],ARRAY[]::text[],"
                        "ARRAY[]::text[],ARRAY[]::text[],ARRAY[]::text[],ARRAY[]::text[],"
                        ":actor_id,:request_id,:audit_id,:now)"
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
                        "UPDATE source SET normalized_origin=:origin,desired_enabled=true,"
                        "runtime_state='PENDING_CONFIGURATION',updated_at=:now WHERE id=:source_id"
                    ),
                    {"origin": origin, "now": now, "source_id": source_id},
                )
            elif await connection.scalar(
                text("SELECT normalized_origin IS NULL FROM source WHERE id=:source_id"),
                {"source_id": source_id},
            ):
                await connection.execute(
                    text(
                        "UPDATE source SET normalized_origin=:origin,updated_at=:now "
                        "WHERE id=:source_id"
                    ),
                    {"origin": origin, "now": now, "source_id": source_id},
                )
            stream_id = await connection.scalar(
                text(
                    "SELECT id FROM source_stream WHERE source_id=:source_id "
                    "AND canonical_url=:url FOR UPDATE"
                ),
                {"source_id": source_id, "url": normalized_url},
            )
            if stream_id is None:
                stream_id = uuid7()
                await connection.execute(
                    text(
                        "INSERT INTO source_stream(id,source_id,stream_key,name,canonical_url,"
                        "authorization_boundary,status,rule_version,automatically_managed,"
                        "created_at,updated_at,stream_type,allowed_hosts,discovery_method) "
                        "VALUES(:id,:source_id,:stream_key,:name,:url,"
                        "CAST(:host AS varchar(253)),'PROBING',"
                        "'personal-source-probe-v1',false,:now,:now,'UNKNOWN',"
                        "ARRAY[CAST(:host AS varchar(253))],'MANUAL_URL')"
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
                    "SELECT id FROM stream_probe_run WHERE source_id=:source_id "
                    "AND normalized_url=:url "
                    "AND status IN ('QUEUED','RUNNING') LIMIT 1"
                ),
                {"source_id": source_id, "url": normalized_url},
            )
            healthy = await connection.scalar(
                text("SELECT status='READY' FROM source_stream WHERE id=:stream_id"),
                {"stream_id": stream_id},
            )
            if active is None and not healthy:
                await connection.execute(
                    text(
                        "INSERT INTO stream_probe_run(id,source_id,stream_id,requested_url,"
                        "normalized_url,normalized_origin,input_kind,status,requested_by,"
                        "request_id,created_at,updated_at) VALUES(:id,:source_id,:stream_id,"
                        ":url,:url,:origin,'UNKNOWN','QUEUED',:actor_id,:request_id,:now,:now)"
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
                                "SELECT id,canonical_url FROM source_stream "
                                "WHERE id=:stream_id AND source_id=:source_id FOR UPDATE"
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
                                "SELECT stream_id AS id,normalized_url AS canonical_url "
                                "FROM stream_probe_run WHERE source_id=:source_id "
                                "ORDER BY created_at DESC LIMIT 1 FOR UPDATE"
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
                    "SELECT id FROM stream_probe_run WHERE source_id=:source_id "
                    "AND normalized_url=:url AND status IN ('QUEUED','RUNNING') LIMIT 1"
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
                        "INSERT INTO stream_probe_run(id,source_id,stream_id,requested_url,"
                        "normalized_url,normalized_origin,input_kind,status,requested_by,"
                        "request_id,created_at,updated_at) VALUES(:id,:source_id,:stream_id,"
                        ":url,:url,:origin,'UNKNOWN','QUEUED',:actor_id,:request_id,:now,:now)"
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
                        "UPDATE source_stream SET status='PROBING',failure_reason=NULL,"
                        "updated_at=:now WHERE id=:stream_id "
                        "AND status NOT IN ('ACTIVE','QUALIFIED','READY')"
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
                            """SELECT stream.id,stream.stream_type,stream.canonical_url,
                                      stream.allowed_hosts,stream.config_sha256,
                                      stream.discovery_method,stream.status,stream.failure_reason,
                                      schedule.status AS schedule_status,schedule.circuit_state,
                                      schedule.circuit_open_until,schedule.access_state,
                                      schedule.requests_used,schedule.daily_request_budget,
                                      schedule.bytes_used,schedule.daily_byte_budget,
                                      schedule.health_status,schedule.health_reason,
                                      schedule.consecutive_failures,schedule.next_self_heal_at,
                                      schedule.last_successful_fetch_at,
                                      schedule.last_content_discovered_at
                                      ,observation.id AS health_observation_id,
                                      observation.observed_at AS health_observed_at
                                 FROM source_stream stream
                                 LEFT JOIN fetch_schedule schedule
                                   ON schedule.source_stream_id=stream.id
                                  AND schedule.authority_mode='PERSONAL_STREAM'
                                LEFT JOIN LATERAL (
                                  SELECT snapshot.id,snapshot.observed_at
                                    FROM source_health_snapshot snapshot
                                   WHERE snapshot.source_stream_id=stream.id
                                   ORDER BY snapshot.observed_at DESC,snapshot.id DESC LIMIT 1
                                ) observation ON true
                                WHERE stream.source_id=:source_id
                                  AND stream.status IN ('PROBING','READY','PROBE_FAILED')
                                ORDER BY stream.created_at,stream.id"""
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
                            "SELECT id,requested_url,input_kind,status,duration_ms,failure_code,"
                            "failure_reason FROM stream_probe_run WHERE source_id=:source_id "
                            "ORDER BY created_at DESC,id DESC LIMIT 1"
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
                            """SELECT snapshot.status,snapshot.overall_confidence,
                                        snapshot.generated_at,
                                        COALESCE(override.values,'{}'::jsonb) AS override_values,
                                        override.action AS override_action
                                   FROM source_profile_snapshot snapshot
                                   LEFT JOIN LATERAL (
                                     SELECT action,values FROM source_profile_override item
                                      WHERE item.source_id=snapshot.source_id
                                      ORDER BY created_at DESC,id DESC LIMIT 1
                                   ) override ON true
                                  WHERE snapshot.source_id=:source_id
                                  ORDER BY snapshot.version DESC LIMIT 1"""
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
                            """
                            SELECT id,name,base_url,desired_enabled,runtime_state,
                                   manual_disabled_at,enabled
                              FROM source WHERE id=:source_id FOR UPDATE
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
                        """
                        UPDATE source
                           SET name=:display_name,desired_enabled=:desired_enabled,
                               manual_disabled_at=:manual_disabled_at,enabled=:legacy_enabled,
                               updated_at=:updated_at
                         WHERE id=:source_id
                        """
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
                        """
                        UPDATE fetch_schedule
                           SET status=CASE
                                 WHEN :desired_enabled AND :manual_disabled_at IS NULL
                                   THEN 'ACTIVE'
                                 ELSE 'PAUSED'
                               END,
                               next_run_at=CASE
                                 WHEN :desired_enabled AND :manual_disabled_at IS NULL
                                   THEN LEAST(next_run_at,:updated_at)
                                 ELSE next_run_at
                               END,
                               updated_at=:updated_at
                         WHERE source_id=:source_id
                           AND authority_mode='PERSONAL_STREAM'
                        """
                    ),
                    {
                        "desired_enabled": desired_enabled,
                        "manual_disabled_at": manual_disabled_at,
                        "updated_at": now,
                        "source_id": source_id,
                    },
                )
            for event_type in event_types:
                await connection.execute(
                    text(
                        """
                        INSERT INTO source_key_activity_event(
                            id,source_id,event_type,actor_id,request_id,
                            before_state,after_state,created_at
                        ) VALUES(
                            :id,:source_id,:event_type,:actor_id,:request_id,
                            CAST(:before_state AS jsonb),CAST(:after_state AS jsonb),:created_at
                        )
                        """
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

    async def list_sources(self) -> list[SourceRow]:
        async with self._engine.connect() as connection:
            rows = (
                await connection.execute(
                    text(
                        """
                        SELECT id, registry_code, name, base_url, channel, source_type,
                               authority_level, priority, collection_method,
                               poll_interval_minutes, owner, state, enabled,
                               lifecycle_state, trial_kind, registered_by,
                               governance_owner_id, country_codes, region_codes,
                               language_tags, industries, content_domains, declared_roles,
                               current_policy_version_id, current_connector_config_version_id,
                               current_trial_run_id, created_at
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
                               poll_interval_minutes, owner, state, enabled,
                               lifecycle_state, trial_kind, registered_by,
                               governance_owner_id, country_codes, region_codes,
                               language_tags, industries, content_domains, declared_roles,
                               current_policy_version_id, current_connector_config_version_id,
                               current_trial_run_id, created_at
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
        audit_id = uuid7()
        values = payload.model_dump(mode="python") | {
            "id": source_id,
            "actor_id": actor_id,
            "request_id": request_id,
            "audit_id": audit_id,
            "now": now,
        }
        async with self._engine.begin() as connection:
            await connection.execute(
                text(
                    """
                    SELECT register_source_candidate(
                        :id, :name, :base_url, :channel, :source_type,
                        :authority_level, :priority, :collection_method,
                        :poll_interval_minutes, :owner, :governance_owner_id,
                        :country_codes, :region_codes, :language_tags,
                        :industries, :content_domains, :declared_roles,
                        :actor_id, :request_id, :audit_id, :now
                    )
                    """
                ),
                values,
            )
        return await self.get_source(source_id)

    async def lifecycle_facts(self, source_id: UUID, *, now: datetime) -> LifecycleFacts:
        async with self._engine.connect() as connection:
            row = (
                (
                    await connection.execute(
                        text(
                            """
                            SELECT
                              p.valid_until,
                              COALESCE(
                                p.valid_from <= :now AND p.valid_until > :now, false
                              ) AS policy_valid,
                              COALESCE(p.document #>> '{robots_review,result}' = 'ALLOWED', false)
                                AS robots_allowed,
                              COALESCE(p.document #>> '{terms_review,result}' = 'ALLOWED', false)
                                AS terms_allowed,
                              COALESCE(
                                p.document #>> '{copyright_review,result}' = 'ALLOWED', false
                              )
                                AS copyright_allowed,
                              s.governance_owner_id IS NOT NULL AS governance_owner_present,
                              COALESCE(source_v2_policy_compliance_approved(
                                s.id,s.current_policy_version_id,:now
                              ),false) AS compliance_approved,
                              COALESCE(c.validation_status = 'VALID', false)
                                AS connector_config_current,
                              r.kind AS trial_kind,
                              COALESCE(rr.status = 'SUCCEEDED' AND r.kind = 'LIVE_TRIAL', false)
                                AS live_trial_succeeded,
                              COALESCE(r.id IS NOT NULL AND rr.trial_run_id IS NULL, false)
                                AS current_trial_pending,
                              EXISTS (
                                SELECT 1 FROM source_governance_decision d
                                 WHERE d.source_id = s.id
                                   AND d.policy_version_id = s.current_policy_version_id
                                   AND d.connector_config_version_id =
                                       s.current_connector_config_version_id
                                   AND d.trial_run_id = s.current_trial_run_id
                                   AND d.decision_type = 'PRODUCTION_APPROVAL'
                                   AND d.outcome = 'APPROVED'
                                   AND (d.valid_until IS NULL OR d.valid_until > :now)
                              ) AS production_approval_current,
                              s.registered_by, p.submitted_by AS policy_submitter,
                              c.created_by AS config_submitter,
                              r.requested_by AS trial_requester,
                              COALESCE(
                                assignment.scheme, :legacy_governance_scheme
                              ) AS governance_scheme,
                              (
                                SELECT d.decided_by
                                  FROM source_governance_decision d
                                 WHERE d.source_id=s.id
                                   AND d.policy_version_id=s.current_policy_version_id
                                   AND d.decision_type='COMPLIANCE'
                                 ORDER BY d.created_at DESC,d.id DESC LIMIT 1
                              ) AS compliance_approver,
                              (
                                SELECT d.decided_by
                                  FROM source_governance_decision d
                                 WHERE d.id=r.authorization_decision_id
                                   AND d.source_id=s.id
                                   AND d.decision_type='LIVE_TRIAL_AUTHORIZATION'
                              ) AS trial_authorizer,
                              ARRAY(
                                SELECT DISTINCT audit.actor_id
                                  FROM fetch_schedule schedule
                                  JOIN audit_log audit
                                    ON audit.target_type='fetch_schedule'
                                   AND audit.target_id=schedule.id
                                   AND audit.event_type='FETCH_SCHEDULE_UPDATED'
                                 WHERE schedule.source_id=s.id
                              ) AS schedule_maker_ids
                            FROM source s
                            LEFT JOIN source_governance_scheme_assignment assignment
                              ON assignment.source_id=s.id
                            LEFT JOIN source_policy_version p
                              ON p.id = s.current_policy_version_id AND p.source_id = s.id
                            LEFT JOIN connector_config_version c
                              ON c.id = s.current_connector_config_version_id
                             AND c.source_id = s.id AND c.policy_version_id=p.id
                            LEFT JOIN source_trial_run r
                              ON r.id = s.current_trial_run_id AND r.source_id = s.id
                             AND r.policy_version_id=p.id
                             AND r.connector_config_version_id=c.id
                            LEFT JOIN source_trial_run_result rr ON rr.trial_run_id = r.id
                            WHERE s.id = :source_id
                            """
                        ),
                        {
                            "source_id": source_id,
                            "now": now,
                            "legacy_governance_scheme": LEGACY_GOVERNANCE_SCHEME,
                        },
                    )
                )
                .mappings()
                .first()
            )
        if row is None:
            raise SourceNotFound("source does not exist")
        schedule_makers = row["schedule_maker_ids"]
        maker_actors = frozenset(
            value
            for value in (
                row["registered_by"],
                row["policy_submitter"],
                row["config_submitter"],
                row["trial_requester"],
                *(schedule_makers if isinstance(schedule_makers, list | tuple) else ()),
            )
            if isinstance(value, UUID)
        )
        prior_approvers = frozenset(
            value
            for value in (
                row["compliance_approver"],
                row["trial_authorizer"],
            )
            if isinstance(value, UUID)
        )
        actors = _governance_separation_actor_ids(
            scheme=str(row["governance_scheme"]),
            maker_actor_ids=maker_actors,
            prior_approver_actor_ids=prior_approvers,
        )
        return LifecycleFacts(
            policy_valid=bool(row["policy_valid"]),
            policy_valid_until=row["valid_until"],
            robots_allowed=bool(row["robots_allowed"]),
            terms_allowed=bool(row["terms_allowed"]),
            copyright_allowed=bool(row["copyright_allowed"]),
            governance_owner_present=bool(row["governance_owner_present"]),
            compliance_approved=bool(row["compliance_approved"]),
            connector_config_current=bool(row["connector_config_current"]),
            trial_kind=(None if row["trial_kind"] is None else SourceTrialKind(row["trial_kind"])),
            live_trial_succeeded=bool(row["live_trial_succeeded"]),
            production_approval_current=bool(row["production_approval_current"]),
            separation_actor_ids=actors,
            current_trial_pending=bool(row["current_trial_pending"]),
        )

    async def assign_round17_governance_scheme(
        self,
        source_id: UUID,
        *,
        cohort_key: str,
        actor_id: UUID,
        reason: str,
        request_id: str,
        now: datetime,
    ) -> None:
        assignment_id, audit_id = uuid7(), uuid7()
        async with self._engine.begin() as connection:
            await connection.execute(
                text(
                    """
                    SELECT assign_round17_two_person_governance(
                      :assignment_id,:source_id,:cohort_key,:actor_id,
                      :reason,:request_id,:audit_id,:now
                    )
                    """
                ),
                {
                    "assignment_id": assignment_id,
                    "source_id": source_id,
                    "cohort_key": cohort_key,
                    "actor_id": actor_id,
                    "reason": reason,
                    "request_id": request_id,
                    "audit_id": audit_id,
                    "now": now,
                },
            )

    async def round17_source_approver_binding_matches(
        self,
        *,
        actor_id: UUID,
        display_name: str,
        authority_mode: str = "OIDC",
        oidc_issuer_sha256: str | None = None,
        oidc_subject_sha256: str | None = None,
    ) -> bool:
        async with self._engine.connect() as connection:
            matched = (
                await connection.execute(
                    text(
                        """
                        SELECT EXISTS (
                          SELECT 1
                            FROM round17_staff_binding
                           WHERE actor_id=:actor_id
                             AND display_name=:display_name
                             AND responsibility='SOURCE_APPROVER'
                             AND authority_mode=:authority_mode
                             AND (
                               (:authority_mode='OIDC' AND local_identity=false
                                AND oidc_issuer_sha256=:oidc_issuer_sha256
                                AND oidc_subject_sha256=:oidc_subject_sha256)
                               OR
                               (:authority_mode='SIGNED_LOCAL_PILOT'
                                AND local_identity=true
                                AND oidc_issuer_sha256 IS NULL
                                AND oidc_subject_sha256 IS NULL)
                             )
                        )
                        """
                    ),
                    {
                        "actor_id": actor_id,
                        "display_name": display_name,
                        "authority_mode": authority_mode,
                        "oidc_issuer_sha256": oidc_issuer_sha256,
                        "oidc_subject_sha256": oidc_subject_sha256,
                    },
                )
            ).scalar_one()
        return bool(matched)

    async def submit_policy_version(
        self,
        source_id: UUID,
        payload: SourcePolicyV2Submission,
        *,
        actor_id: UUID,
        request_id: str,
        now: datetime,
    ) -> UUID:
        policy_id, audit_id = uuid7(), uuid7()
        document = payload.model_dump(mode="json")
        async with self._engine.begin() as connection:
            await connection.execute(
                text(
                    """
                    SELECT submit_source_policy_version(
                      :source_id, :policy_id, :schema_version, :policy_version,
                      CAST(:document AS jsonb), :valid_from, :valid_until,
                      :actor_id, :reason, :request_id, :audit_id, :now
                    )
                    """
                ),
                {
                    "source_id": source_id,
                    "policy_id": policy_id,
                    "schema_version": payload.schema_version,
                    "policy_version": payload.policy_version,
                    "document": _json(document),
                    "valid_from": payload.valid_from.astimezone(UTC),
                    "valid_until": payload.valid_until.astimezone(UTC),
                    "actor_id": actor_id,
                    "reason": payload.reason,
                    "request_id": request_id,
                    "audit_id": audit_id,
                    "now": now,
                },
            )
        return policy_id

    async def decide_policy_version(
        self,
        source_id: UUID,
        policy_id: UUID,
        outcome: SourcePolicyDecisionOutcome,
        reason: str,
        *,
        actor_id: UUID,
        request_id: str,
        now: datetime,
    ) -> UUID:
        decision_id, audit_id = uuid7(), uuid7()
        async with self._engine.begin() as connection:
            await connection.execute(
                text(
                    """
                    SELECT decide_source_policy_version(
                      :source_id, :policy_id, :decision_id, :outcome, :actor_id,
                      :reason, :request_id, :audit_id, :now
                    )
                    """
                ),
                {
                    "source_id": source_id,
                    "policy_id": policy_id,
                    "decision_id": decision_id,
                    "outcome": outcome.value,
                    "actor_id": actor_id,
                    "reason": reason,
                    "request_id": request_id,
                    "audit_id": audit_id,
                    "now": now,
                },
            )
        return decision_id

    async def list_policy_versions(self, source_id: UUID) -> list[SourcePolicyVersionView]:
        async with self._engine.connect() as connection:
            rows = (
                await connection.execute(
                    text(
                        """
                        SELECT p.id, p.source_id, p.schema_version, p.policy_version,
                               CASE WHEN p.valid_until <= now() THEN 'EXPIRED'
                                    ELSE COALESCE(decision.outcome, 'PENDING_REVIEW') END status,
                               p.valid_from, p.valid_until, p.document_sha256, p.document,
                               p.submitted_by, decision.decided_by, p.created_at
                          FROM source_policy_version p
                          LEFT JOIN LATERAL (
                            SELECT d.outcome, d.decided_by
                              FROM source_governance_decision d
                             WHERE d.policy_version_id = p.id
                               AND d.decision_type = 'COMPLIANCE'
                             ORDER BY d.created_at DESC, d.id DESC LIMIT 1
                          ) decision ON true
                         WHERE p.source_id = :source_id
                         ORDER BY p.created_at DESC, p.id DESC
                        """
                    ),
                    {"source_id": source_id},
                )
            ).mappings()
        return [SourcePolicyVersionView.model_validate(dict(row)) for row in rows]

    async def current_policy_allowed_hosts(
        self, source_id: UUID, *, now: datetime
    ) -> tuple[str, ...]:
        async with self._engine.connect() as connection:
            value = await connection.scalar(
                text(
                    """
                    SELECT p.document #> '{fetch,allowed_domains}'
                      FROM source s
                      JOIN source_policy_version p ON p.id=s.current_policy_version_id
                     WHERE s.id=:source_id AND p.source_id=s.id
                       AND p.valid_from <= :now AND p.valid_until > :now
                       AND source_v2_policy_compliance_approved(
                             s.id,p.id,:now
                           ) IS TRUE
                    """
                ),
                {"source_id": source_id, "now": now},
            )
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            raise RepositoryConflict("a current approved source policy is required")
        return tuple(value)

    async def list_connector_definitions(self) -> list[ConnectorDefinitionView]:
        async with self._engine.connect() as connection:
            rows = (
                await connection.execute(
                    text(
                        """
                        SELECT id, connector_type, definition_version, schema_version,
                               schema_document, schema_sha256, executor_key, capabilities
                          FROM connector_definition
                         ORDER BY connector_type, definition_version
                        """
                    )
                )
            ).mappings()
        return [ConnectorDefinitionView.model_validate(dict(row)) for row in rows]

    async def connector_definition(
        self, connector_type: ConnectorType, definition_version: str
    ) -> ConnectorDefinitionView:
        async with self._engine.connect() as connection:
            row = (
                (
                    await connection.execute(
                        text(
                            """
                            SELECT id, connector_type, definition_version, schema_version,
                                   schema_document, schema_sha256, executor_key, capabilities
                              FROM connector_definition
                             WHERE connector_type=:connector_type
                               AND definition_version=:definition_version
                            """
                        ),
                        {
                            "connector_type": connector_type.value,
                            "definition_version": definition_version,
                        },
                    )
                )
                .mappings()
                .first()
            )
        if row is None:
            raise RepositoryConflict("connector definition does not exist")
        return ConnectorDefinitionView.model_validate(dict(row))

    async def save_connector_config(
        self,
        source_id: UUID,
        *,
        definition_id: UUID,
        config_document: dict[str, object],
        credential_ref: str | None,
        actor_id: UUID,
        reason: str,
        request_id: str,
        now: datetime,
    ) -> UUID:
        config_id, audit_id = uuid7(), uuid7()
        async with self._engine.begin() as connection:
            version_row = (
                (
                    await connection.execute(
                        text(
                            """
                            SELECT COALESCE(max(version_number),0)+1 next_version,
                                   (array_agg(id ORDER BY version_number DESC))[1] latest_id
                              FROM connector_config_version
                             WHERE source_id=:source_id
                            """
                        ),
                        {"source_id": source_id},
                    )
                )
                .mappings()
                .one()
            )
            await connection.execute(
                text(
                    """
                    SELECT save_source_connector_config(
                      :source_id, :config_id, :definition_id, :version_number,
                      CAST(:config_document AS jsonb), :credential_ref,
                      :supersedes_id, :actor_id, :reason, :request_id, :audit_id, :now
                    )
                    """
                ),
                {
                    "source_id": source_id,
                    "config_id": config_id,
                    "definition_id": definition_id,
                    "version_number": version_row["next_version"],
                    "config_document": _json(config_document),
                    "credential_ref": credential_ref,
                    "supersedes_id": version_row["latest_id"],
                    "actor_id": actor_id,
                    "reason": reason,
                    "request_id": request_id,
                    "audit_id": audit_id,
                    "now": now,
                },
            )
        return config_id

    async def list_connector_configs(self, source_id: UUID) -> list[ConnectorConfigVersionView]:
        async with self._engine.connect() as connection:
            rows = (
                await connection.execute(
                    text(
                        """
                        SELECT c.id, c.source_id, c.policy_version_id, d.connector_type,
                               d.definition_version, c.version_number, c.config_sha256,
                               c.config_document AS config, c.allowed_hosts,
                               c.credential_ref IS NOT NULL
                                 AS credential_configured,
                               c.validation_status, c.created_by, c.created_at
                          FROM connector_config_version c
                          JOIN connector_definition d ON d.id=c.connector_definition_id
                         WHERE c.source_id=:source_id
                         ORDER BY c.version_number DESC
                        """
                    ),
                    {"source_id": source_id},
                )
            ).mappings()
        return [ConnectorConfigVersionView.model_validate(dict(row)) for row in rows]

    async def update_governance_metadata(
        self,
        source_id: UUID,
        payload: SourceGovernanceMetadataUpdate,
        *,
        actor_id: UUID,
        request_id: str,
        now: datetime,
    ) -> None:
        async with self._engine.begin() as connection:
            await connection.execute(
                text(
                    """
                    SELECT update_source_governance_metadata(
                      :source_id, :governance_owner_id, :country_codes,
                      :region_codes, :language_tags, :industries, :content_domains,
                      :declared_roles, :actor_id, :reason, :request_id, :audit_id, :now
                    )
                    """
                ),
                {
                    "source_id": source_id,
                    "governance_owner_id": payload.governance_owner_id,
                    "country_codes": payload.country_codes,
                    "region_codes": payload.region_codes,
                    "language_tags": payload.language_tags,
                    "industries": [value.value for value in payload.industries],
                    "content_domains": [value.value for value in payload.content_domains],
                    "declared_roles": [value.value for value in payload.declared_roles],
                    "actor_id": actor_id,
                    "reason": payload.reason,
                    "request_id": request_id,
                    "audit_id": uuid7(),
                    "now": now,
                },
            )

    async def append_assessments(
        self,
        source_id: UUID,
        payload: SourceAssessmentSubmission,
        *,
        actor_id: UUID,
        request_id: str,
        now: datetime,
    ) -> None:
        authority, independence = payload.authority, payload.independence
        async with self._engine.begin() as connection:
            await connection.execute(
                text(
                    """
                    SELECT append_source_assessments(
                      :source_id, :authority_id, :authority_level,
                      :authority_rule_version, :authority_reason_codes,
                      :authority_evidence_refs, :authority_assessed_at,
                      :independence_id, :independence_level,
                      :independence_rule_version, :independence_reason_codes,
                      :independence_evidence_refs, :independence_assessed_at,
                      :actor_id, :reason, :request_id, :audit_id, :now
                    )
                    """
                ),
                {
                    "source_id": source_id,
                    "authority_id": uuid7(),
                    "authority_level": authority.level.value,
                    "authority_rule_version": authority.rule_version,
                    "authority_reason_codes": authority.reason_codes,
                    "authority_evidence_refs": authority.evidence_refs,
                    "authority_assessed_at": authority.assessed_at,
                    "independence_id": uuid7(),
                    "independence_level": independence.level.value,
                    "independence_rule_version": independence.rule_version,
                    "independence_reason_codes": independence.reason_codes,
                    "independence_evidence_refs": independence.evidence_refs,
                    "independence_assessed_at": independence.assessed_at,
                    "actor_id": actor_id,
                    "reason": payload.reason,
                    "request_id": request_id,
                    "audit_id": uuid7(),
                    "now": now,
                },
            )

    async def latest_assessments(
        self, source_id: UUID
    ) -> tuple[SourceAuthorityAssessment | None, SourceIndependenceAssessment | None]:
        async with self._engine.connect() as connection:
            authority = (
                (
                    await connection.execute(
                        text(
                            """
                            SELECT authority_level AS level, rule_version, reason_codes,
                                   evidence_refs, assessed_at
                              FROM source_authority_assessment
                             WHERE source_id=:source_id
                             ORDER BY assessed_at DESC, id DESC LIMIT 1
                            """
                        ),
                        {"source_id": source_id},
                    )
                )
                .mappings()
                .first()
            )
            independence = (
                (
                    await connection.execute(
                        text(
                            """
                            SELECT independence_level AS level, rule_version, reason_codes,
                                   evidence_refs, assessed_at
                              FROM source_independence_assessment
                             WHERE source_id=:source_id
                             ORDER BY assessed_at DESC, id DESC LIMIT 1
                            """
                        ),
                        {"source_id": source_id},
                    )
                )
                .mappings()
                .first()
            )
        return (
            None
            if authority is None
            else SourceAuthorityAssessment.model_validate(dict(authority)),
            None
            if independence is None
            else SourceIndependenceAssessment.model_validate(dict(independence)),
        )

    async def start_trial_run(
        self,
        source_id: UUID,
        payload: SourceTrialRunRequest,
        *,
        actor_id: UUID,
        request_id: str,
        now: datetime,
    ) -> UUID:
        trial_id, decision_id, event_id, audit_id = (
            uuid7(),
            uuid7(),
            uuid7(),
            uuid7(),
        )
        async with self._engine.begin() as connection:
            await connection.execute(
                text(
                    """
                    SELECT start_source_trial_run(
                      :source_id, :trial_id, :kind, :policy_id, :config_id,
                      :decision_id, :actor_id, :reason, :request_id,
                      :event_id, :audit_id, :now
                    )
                    """
                ),
                {
                    "source_id": source_id,
                    "trial_id": trial_id,
                    "kind": payload.kind.value,
                    "policy_id": payload.policy_version_id,
                    "config_id": payload.connector_config_version_id,
                    "decision_id": decision_id,
                    "actor_id": actor_id,
                    "reason": payload.reason,
                    "request_id": request_id,
                    "event_id": event_id,
                    "audit_id": audit_id,
                    "now": now,
                },
            )
        return trial_id

    async def complete_trial_run(
        self,
        trial_id: UUID,
        status: SourceTrialRunStatus,
        quality_summary: SourceTrialQualitySummary,
        *,
        raw_namespace: str,
        actor_id: UUID,
        reason: str,
        request_id: str,
        now: datetime,
    ) -> tuple[UUID, SourceTrialKind]:
        if status not in {
            SourceTrialRunStatus.SUCCEEDED,
            SourceTrialRunStatus.FAILED,
            SourceTrialRunStatus.CANCELLED,
        }:
            raise RepositoryConflict("source trial completion status is not terminal")
        async with self._engine.begin() as connection:
            row = (
                (
                    await connection.execute(
                        text("SELECT source_id,kind FROM source_trial_run WHERE id=:trial_id"),
                        {"trial_id": trial_id},
                    )
                )
                .mappings()
                .first()
            )
            if row is None:
                raise SourceNotFound("source trial does not exist")
            await connection.execute(
                text(
                    """
                    SELECT complete_source_trial_run_with_audit(
                      :trial_id,:status,CAST(:quality_summary AS jsonb),
                      :raw_namespace,:actor_id,:reason,:request_id,:audit_id,:now
                    )
                    """
                ),
                {
                    "trial_id": trial_id,
                    "status": status.value,
                    "quality_summary": _json(quality_summary.model_dump(mode="json")),
                    "raw_namespace": raw_namespace,
                    "actor_id": actor_id,
                    "reason": reason,
                    "request_id": request_id,
                    "audit_id": uuid7(),
                    "now": now,
                },
            )
        return row["source_id"], SourceTrialKind(row["kind"])

    async def fixture_trial_quality(
        self, source_id: UUID, trial_id: UUID
    ) -> SourceTrialQualitySummary:
        async with self._engine.connect() as connection:
            row = (
                (
                    await connection.execute(
                        text(
                            """
                            SELECT source_trial_quality_summary(r.id) AS quality_summary
                              FROM source_trial_run r
                              JOIN source s ON s.id=r.source_id
                              LEFT JOIN source_trial_run_result result
                                ON result.trial_run_id=r.id
                             WHERE r.id=:trial_id AND r.source_id=:source_id
                               AND r.kind='FIXTURE_REPLAY'
                               AND r.execution_domain='FIXTURE'
                               AND s.lifecycle_state='TRIAL'
                               AND s.current_trial_run_id=r.id
                               AND result.trial_run_id IS NULL
                            """
                        ),
                        {"trial_id": trial_id, "source_id": source_id},
                    )
                )
                .mappings()
                .first()
            )
        if row is None:
            raise RepositoryConflict("fixture trial is not the current pending replay")
        return SourceTrialQualitySummary.model_validate(row["quality_summary"])

    async def fixture_replay_bundle(self, source_id: UUID, trial_id: UUID) -> FixtureReplayBundle:
        async with self._engine.connect() as connection:
            header = (
                (
                    await connection.execute(
                        text(
                            """
                            SELECT r.id AS trial_run_id, r.source_id,
                                   r.connector_config_version_id,
                                   definition.connector_type,
                                   config.config_document, config.allowed_hosts,
                                   replay.status AS replay_status
                              FROM source_trial_run r
                              JOIN source s
                                ON s.id=r.source_id
                               AND s.lifecycle_state='TRIAL'
                               AND s.trial_kind='FIXTURE_REPLAY'
                               AND s.current_trial_run_id=r.id
                              JOIN connector_config_version config
                                ON config.id=r.connector_config_version_id
                               AND config.source_id=r.source_id
                               AND config.validation_status='VALID'
                              JOIN connector_definition definition
                                ON definition.id=config.connector_definition_id
                              LEFT JOIN source_fixture_replay_result replay
                                ON replay.trial_run_id=r.id
                             WHERE r.id=:trial_id AND r.source_id=:source_id
                               AND r.kind='FIXTURE_REPLAY'
                               AND r.execution_domain='FIXTURE'
                               AND NOT EXISTS (
                                 SELECT 1 FROM source_trial_run_result result
                                  WHERE result.trial_run_id=r.id
                               )
                            """
                        ),
                        {"trial_id": trial_id, "source_id": source_id},
                    )
                )
                .mappings()
                .first()
            )
            if header is None:
                raise RepositoryConflict("fixture trial is not the current pending replay")
            capture_rows = (
                (
                    await connection.execute(
                        text(
                            """
                        SELECT capture.id, capture.raw_object_id, raw.object_key,
                               raw.sha256 AS content_sha256, raw.byte_size,
                               raw.declared_mime, raw.detected_mime,
                               capture.requested_url, capture.final_url,
                               capture.http_status, capture.etag,
                               capture.last_modified, capture.captured_at,
                               COALESCE(version.original_filename, 'fixture.bin') filename,
                               version.title
                          FROM raw_object_capture capture
                          JOIN raw_object raw ON raw.id=capture.raw_object_id
                          LEFT JOIN LATERAL (
                            SELECT candidate.original_filename,candidate.title
                              FROM document_version candidate
                              JOIN document linked_document
                                ON linked_document.id=candidate.document_id
                               AND linked_document.source_id=capture.source_id
                             WHERE candidate.raw_object_id=capture.raw_object_id
                               AND candidate.execution_domain='FIXTURE'
                             ORDER BY candidate.acquired_at DESC,candidate.id DESC
                             LIMIT 1
                          ) version ON true
                         WHERE capture.trial_run_id=:trial_id
                           AND capture.source_id=:source_id
                           AND capture.execution_domain='FIXTURE'
                           AND capture.arrived_after_close=false
                         ORDER BY capture.captured_at,capture.id
                        """
                        ),
                        {"trial_id": trial_id, "source_id": source_id},
                    )
                )
                .mappings()
                .all()
            )
        config_document = header["config_document"]
        allowed_hosts = header["allowed_hosts"]
        if not isinstance(config_document, dict) or not isinstance(allowed_hosts, list):
            raise RepositoryConflict("fixture connector configuration is malformed")
        return FixtureReplayBundle(
            source_id=header["source_id"],
            trial_run_id=header["trial_run_id"],
            connector_config_version_id=header["connector_config_version_id"],
            connector_type=str(header["connector_type"]),
            config_document=dict(config_document),
            allowed_hosts=tuple(str(host) for host in allowed_hosts),
            replay_status=(
                None if header["replay_status"] is None else str(header["replay_status"])
            ),
            captures=tuple(
                FixtureReplayCapture(
                    id=row["id"],
                    raw_object_id=row["raw_object_id"],
                    object_key=str(row["object_key"]),
                    content_sha256=str(row["content_sha256"]),
                    byte_size=int(row["byte_size"]),
                    declared_mime=str(row["declared_mime"]),
                    detected_mime=str(row["detected_mime"]),
                    requested_url=str(row["requested_url"]),
                    final_url=str(row["final_url"]),
                    http_status=int(row["http_status"]),
                    etag=None if row["etag"] is None else str(row["etag"]),
                    last_modified=(
                        None if row["last_modified"] is None else str(row["last_modified"])
                    ),
                    filename=str(row["filename"]),
                    title=None if row["title"] is None else str(row["title"]),
                    captured_at=row["captured_at"],
                )
                for row in capture_rows
            ),
        )

    async def record_fixture_replay_result(
        self,
        bundle: FixtureReplayBundle,
        *,
        status: str,
        reason_code: str,
        document_count: int,
        transport_call_count: int,
        actor_id: UUID,
        now: datetime,
    ) -> None:
        async with self._engine.begin() as connection:
            await connection.execute(
                text(
                    """
                    SELECT record_source_fixture_replay_result(
                      :trial_id,:source_id,:config_id,:status,
                      :reason_code,:raw_capture_count,:document_count,
                      :transport_call_count,:actor_id,:now
                    )
                    """
                ),
                {
                    "trial_id": bundle.trial_run_id,
                    "source_id": bundle.source_id,
                    "config_id": bundle.connector_config_version_id,
                    "status": status,
                    "reason_code": reason_code,
                    "raw_capture_count": len(bundle.captures),
                    "document_count": document_count,
                    "transport_call_count": transport_call_count,
                    "actor_id": actor_id,
                    "now": now,
                },
            )

    async def list_trial_runs(self, source_id: UUID) -> list[SourceTrialRunView]:
        async with self._engine.connect() as connection:
            rows = (
                await connection.execute(
                    text(
                        """
                        SELECT r.id, r.source_id, r.kind,
                               COALESCE(result.status, 'PENDING') status,
                               r.policy_version_id, r.connector_config_version_id,
                               r.requested_by, r.created_at AS started_at,
                               result.completed_at, result.quality_summary, r.created_at
                          FROM source_trial_run r
                          LEFT JOIN source_trial_run_result result
                            ON result.trial_run_id = r.id
                         WHERE r.source_id = :source_id
                         ORDER BY r.created_at DESC, r.id DESC
                        """
                    ),
                    {"source_id": source_id},
                )
            ).mappings()
        return [
            SourceTrialRunView(
                id=row["id"],
                source_id=row["source_id"],
                kind=SourceTrialKind(row["kind"]),
                status=SourceTrialRunStatus(row["status"]),
                policy_version_id=row["policy_version_id"],
                connector_config_version_id=row["connector_config_version_id"],
                requested_by=row["requested_by"],
                started_at=row["started_at"],
                completed_at=row["completed_at"],
                quality_summary=(
                    None
                    if row["quality_summary"] is None
                    else SourceTrialQualitySummary.model_validate(row["quality_summary"])
                ),
                created_at=row["created_at"],
            )
            for row in rows
        ]

    async def approve_production(
        self,
        source_id: UUID,
        *,
        policy_version_id: UUID,
        connector_config_version_id: UUID,
        trial_run_id: UUID,
        reason: str,
        actor_id: UUID,
        request_id: str,
        now: datetime,
    ) -> UUID:
        decision_id, event_id, audit_id = uuid7(), uuid7(), uuid7()
        async with self._engine.begin() as connection:
            await connection.execute(
                text(
                    """
                    SELECT approve_source_production(
                      :source_id, :policy_id, :config_id, :trial_id, :decision_id,
                      :actor_id, :reason, :request_id, :event_id, :audit_id, :now
                    )
                    """
                ),
                {
                    "source_id": source_id,
                    "policy_id": policy_version_id,
                    "config_id": connector_config_version_id,
                    "trial_id": trial_run_id,
                    "decision_id": decision_id,
                    "actor_id": actor_id,
                    "reason": reason,
                    "request_id": request_id,
                    "event_id": event_id,
                    "audit_id": audit_id,
                    "now": now,
                },
            )
        return decision_id

    async def apply_lifecycle_action(
        self,
        source_id: UUID,
        action: str,
        reason: str,
        *,
        actor_id: UUID,
        request_id: str,
        now: datetime,
    ) -> None:
        event_id = uuid7()
        async with self._engine.begin() as connection:
            await connection.execute(
                text(
                    """
                    SELECT apply_source_lifecycle_command(
                      :source_id, :action, :actor_id, :reason, :request_id,
                      :event_id, :now
                    )
                    """
                ),
                {
                    "source_id": source_id,
                    "action": action,
                    "actor_id": actor_id,
                    "reason": reason,
                    "request_id": request_id,
                    "event_id": event_id,
                    "now": now,
                },
            )

    async def list_lifecycle_events(self, source_id: UUID) -> list[SourceLifecycleEventView]:
        async with self._engine.connect() as connection:
            rows = (
                await connection.execute(
                    text(
                        """
                        SELECT id, source_id, from_state, to_state, action, reason_code,
                               reason, actor_id, policy_version_id,
                               governance_decision_id, migration_rule_version, created_at
                          FROM source_lifecycle_event
                         WHERE source_id = :source_id
                         ORDER BY created_at DESC, id DESC
                        """
                    ),
                    {"source_id": source_id},
                )
            ).mappings()
        return [SourceLifecycleEventView.model_validate(dict(row)) for row in rows]

    async def list_audit_events(self, source_id: UUID) -> list[dict[str, Any]]:
        async with self._engine.connect() as connection:
            rows = (
                await connection.execute(
                    text(
                        """
                        SELECT id, event_type, actor_id, reason, request_id, created_at
                          FROM audit_log
                         WHERE (target_type = 'SOURCE' AND target_id = :source_id)
                            OR target_id IN (
                              SELECT id FROM source_policy_version
                               WHERE source_id = :source_id
                              UNION ALL
                              SELECT id FROM connector_config_version
                               WHERE source_id = :source_id
                              UNION ALL
                              SELECT id FROM source_trial_run
                               WHERE source_id = :source_id
                              UNION ALL
                              SELECT id FROM source_trial_rejected_raw_attempt
                               WHERE source_id = :source_id
                              UNION ALL
                              SELECT id FROM document
                               WHERE source_id = :source_id
                            )
                         ORDER BY created_at DESC, id DESC
                        """
                    ),
                    {"source_id": source_id},
                )
            ).mappings()
        return [dict(row) for row in rows]

    async def source_coverage(self, *, now: datetime) -> SourceCoverageMatrix:
        industries = [item.value for item in SourceIndustry]
        domains = [item.value for item in SourceContentDomain]
        source_types = [item.value for item in SourceType]
        async with self._engine.connect() as connection:
            rows = (
                await connection.execute(
                    text(
                        """
                        WITH normalized AS (
                          SELECT s.id, s.lifecycle_state, s.source_type,
                                 industry, content_domain, region, language,
                                 (
                                   s.lifecycle_state = 'ACTIVE'
                                   AND p.valid_from <= :now AND p.valid_until > :now
                                   AND c.validation_status = 'VALID'
                                   AND r.kind = 'LIVE_TRIAL' AND result.status = 'SUCCEEDED'
                                   AND source_v2_policy_compliance_approved(
                                         s.id,p.id,:now
                                       ) IS TRUE
                                   AND EXISTS (
                                     SELECT 1 FROM source_governance_decision d
                                      WHERE d.source_id = s.id
                                        AND d.policy_version_id = p.id
                                        AND d.connector_config_version_id = c.id
                                        AND d.trial_run_id = r.id
                                        AND d.decision_type = 'PRODUCTION_APPROVAL'
                                        AND d.outcome = 'APPROVED'
                                        AND (d.valid_until IS NULL OR d.valid_until > :now)
                                   )
                                 ) effective_active
                            FROM source s
                            CROSS JOIN LATERAL unnest(
                              CASE WHEN cardinality(s.industries)=0
                                   THEN ARRAY['UNKNOWN']::text[] ELSE s.industries END
                            ) industry
                            CROSS JOIN LATERAL unnest(
                              CASE WHEN cardinality(s.content_domains)=0
                                   THEN ARRAY['UNKNOWN']::text[] ELSE s.content_domains END
                            ) content_domain
                            CROSS JOIN LATERAL unnest(
                              CASE WHEN cardinality(s.region_codes)>0 THEN s.region_codes
                                   WHEN cardinality(s.country_codes)>0 THEN s.country_codes
                                   ELSE ARRAY['UNKNOWN']::text[] END
                            ) region
                            CROSS JOIN LATERAL unnest(
                              CASE WHEN cardinality(s.language_tags)=0
                                   THEN ARRAY['UNKNOWN']::text[] ELSE s.language_tags END
                            ) language
                            LEFT JOIN source_policy_version p
                              ON p.id=s.current_policy_version_id AND p.source_id=s.id
                            LEFT JOIN connector_config_version c
                              ON c.id=s.current_connector_config_version_id
                             AND c.source_id=s.id AND c.policy_version_id=p.id
                            LEFT JOIN source_trial_run r
                              ON r.id=s.current_trial_run_id AND r.source_id=s.id
                             AND r.policy_version_id=p.id
                             AND r.connector_config_version_id=c.id
                            LEFT JOIN source_trial_run_result result ON result.trial_run_id=r.id
                        ), observed_geo AS (
                          SELECT DISTINCT region, language FROM normalized
                          UNION SELECT 'UNKNOWN','UNKNOWN'
                        ), grid AS (
                          SELECT industry, content_domain, source_type, region, language
                            FROM unnest(CAST(:industries AS text[])) industry
                            CROSS JOIN unnest(CAST(:domains AS text[])) content_domain
                            CROSS JOIN unnest(CAST(:source_types AS text[])) source_type
                            CROSS JOIN observed_geo
                        )
                        SELECT grid.industry, grid.content_domain, grid.source_type,
                               grid.region, grid.language,
                               count(normalized.id) FILTER (
                                 WHERE normalized.lifecycle_state IN
                                   ('CANDIDATE','COMPLIANCE_REVIEW')
                               ) candidate_count,
                               count(normalized.id) FILTER (
                                 WHERE normalized.lifecycle_state='TRIAL'
                               ) trial_count,
                               count(normalized.id) FILTER (
                                 WHERE normalized.effective_active
                               ) active_count
                          FROM grid
                          LEFT JOIN normalized USING (
                            industry,content_domain,source_type,region,language
                          )
                         GROUP BY grid.industry, grid.content_domain, grid.source_type,
                                  grid.region, grid.language
                         ORDER BY grid.industry, grid.content_domain, grid.source_type,
                                  grid.region, grid.language
                        """
                    ),
                    {
                        "now": now,
                        "industries": industries,
                        "domains": domains,
                        "source_types": source_types,
                    },
                )
            ).mappings()
        cells = [
            SourceCoverageCell(
                industry=SourceIndustry(row["industry"]),
                content_domain=SourceContentDomain(row["content_domain"]),
                source_type=SourceType(row["source_type"]),
                region=row["region"],
                language=row["language"],
                candidate_count=row["candidate_count"],
                trial_count=row["trial_count"],
                active_count=row["active_count"],
                gap=row["active_count"] == 0,
            )
            for row in rows
        ]
        return SourceCoverageMatrix(
            generated_at=now,
            cells=cells,
            gap_cell_count=sum(cell.gap for cell in cells),
        )

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
                      AND document.admission_fixture = true
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

    async def source_accepts_fixture(self, source_id: UUID, canonical_url: str) -> UUID | None:
        now = datetime.now(UTC)
        async with self._engine.connect() as connection:
            row = (
                (
                    await connection.execute(
                        text(
                            """
                            SELECT r.id AS trial_run_id,
                                   p.document #> '{fetch,allowed_domains}' allowed_domains,
                                   c.allowed_hosts
                              FROM source s
                              JOIN source_policy_version p
                                ON p.id=s.current_policy_version_id AND p.source_id=s.id
                              JOIN connector_config_version c
                                ON c.id=s.current_connector_config_version_id
                               AND c.source_id=s.id AND c.policy_version_id=p.id
                              JOIN source_trial_run r
                                ON r.id=s.current_trial_run_id AND r.source_id=s.id
                               AND r.policy_version_id=p.id
                               AND r.connector_config_version_id=c.id
                             WHERE s.id=:source_id AND s.lifecycle_state='TRIAL'
                               AND s.trial_kind='FIXTURE_REPLAY'
                               AND r.kind='FIXTURE_REPLAY' AND r.execution_domain='FIXTURE'
                               AND NOT EXISTS (
                                 SELECT 1 FROM source_trial_run_result result
                                  WHERE result.trial_run_id=r.id
                               )
                               AND c.validation_status='VALID'
                               AND p.valid_from <= :now AND p.valid_until > :now
                               AND source_v2_policy_compliance_approved(
                                     s.id,p.id,:now
                                   ) IS TRUE
                            """
                        ),
                        {"source_id": source_id, "now": now},
                    )
                )
                .mappings()
                .first()
            )
        if row is None:
            return None
        hostname = urlsplit(canonical_url).hostname
        domains = row["allowed_domains"]
        allowed_hosts = row["allowed_hosts"]
        if hostname is None or not isinstance(domains, list) or not isinstance(allowed_hosts, list):
            return None
        normalized_host = hostname.rstrip(".").lower()
        return (
            row["trial_run_id"]
            if normalized_host in set(domains) and normalized_host in set(allowed_hosts)
            else None
        )

    async def raw_object_exists(self, content_hash: str) -> bool:
        async with self._engine.connect() as connection:
            value = await connection.scalar(
                text("SELECT EXISTS(SELECT 1 FROM raw_object WHERE sha256 = :sha256)"),
                {"sha256": content_hash},
            )
        return bool(value)

    async def raw_object_security_blocked(self, content_hash: str) -> bool:
        async with self._engine.connect() as connection:
            value = await connection.scalar(
                text(
                    """
                    SELECT EXISTS(
                      SELECT 1
                        FROM raw_object raw
                       WHERE raw.sha256=:sha256
                         AND (
                           raw.scan_status='REJECTED'
                           OR EXISTS (
                             SELECT 1 FROM raw_object_security_fact security
                              WHERE security.raw_object_id=raw.id
                                AND security.status IN ('REJECTED','QUARANTINED')
                           )
                         )
                    )
                    """
                ),
                {"sha256": content_hash},
            )
        return bool(value)

    async def record_fixture(self, record: FixtureRecord) -> FixtureUploadResponse:
        version_created = False
        async with self._engine.begin() as connection:
            await self._locked_source(connection, record.source_id)
            if record.trial_run_id is None:
                raise RepositoryConflict("fixture upload has no trial authorization")
            raw_id = uuid7()
            inserted_raw = (
                await connection.execute(
                    text(
                        """
                        INSERT INTO raw_object (
                            id, sha256, object_key, byte_size, declared_mime,
                            detected_mime, scan_status, storage_etag, created_at
                        ) VALUES (
                            :id, :sha256, :object_key, :byte_size, :declared_mime,
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
                        "declared_mime": record.declared_mime,
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
            await connection.execute(
                text(
                    """
                    INSERT INTO raw_object_security_fact (
                        id, raw_object_id, status, detected_mime,
                        rule_version, reason_code, created_at
                    ) VALUES (
                        :id, :raw_id, 'CLEAN', :detected_mime,
                        'source-vault-2.0.0', NULL, :created_at
                    )
                    ON CONFLICT (raw_object_id, rule_version) DO NOTHING
                    """
                ),
                {
                    "id": uuid7(),
                    "raw_id": raw_id,
                    "detected_mime": record.detected_mime,
                    "created_at": record.acquired_at,
                },
            )
            capture_id = uuid7()
            await connection.execute(
                text(
                    """
                    SELECT append_source_trial_raw_capture(
                      :id,:raw_object_id,:source_id,:trial_run_id,'FIXTURE',
                      :url,:url,CAST('[]' AS jsonb),200,NULL,NULL,
                      :response_sha256,:captured_at
                    )
                    """
                ),
                {
                    "id": capture_id,
                    "raw_object_id": raw_id,
                    "source_id": record.source_id,
                    "trial_run_id": record.trial_run_id,
                    "url": record.canonical_url,
                    "response_sha256": record.response_sha256,
                    "captured_at": record.acquired_at,
                },
            )
            arrived_after_close = bool(
                await connection.scalar(
                    text("SELECT arrived_after_close FROM raw_object_capture WHERE id=:id"),
                    {"id": capture_id},
                )
            )

            document_id = uuid7()
            inserted_document = (
                await connection.execute(
                    text(
                        """
                        INSERT INTO document (
                            id, source_id, canonical_url, document_kind,
                            first_discovered_at, current_version_id, admission_fixture
                        ) VALUES (
                            :id, :source_id, :url, :kind, :acquired_at, NULL,
                            :admission_fixture
                        )
                        ON CONFLICT (source_id, canonical_url) DO NOTHING RETURNING id
                        """
                    ),
                    {
                        "id": document_id,
                        "source_id": record.source_id,
                        "url": record.canonical_url,
                        "kind": record.document_kind,
                        "acquired_at": record.acquired_at,
                        "admission_fixture": record.admission_fixture,
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
                            original_filename, title, acquired_at, execution_domain,
                            raw_object_capture_id
                        ) VALUES (
                            :id, :document_id, :raw_object_id, :version_number,
                            :content_hash, :filename, :title, :acquired_at, 'FIXTURE',
                            :raw_object_capture_id
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
                        "raw_object_capture_id": capture_id,
                    },
                )
                # Manual fixtures complete bounded parsing before this transaction.
                # Pipeline acquisitions remain non-terminal until their dedicated
                # parser/attachment workflow appends READY or a failure state.
                states = ["RECEIVED", "SECURITY_PASSED"]
                if record.admission_fixture and not arrived_after_close:
                    states.append("READY")
                elif arrived_after_close:
                    states.append("FAILED")
                for state_index, state in enumerate(states):
                    await connection.execute(
                        text(
                            """
                            INSERT INTO document_version_state_event (
                                id, document_version_id, state, reason_code,
                                actor_type, created_at
                            ) VALUES (
                                :id, :version_id, :state, :reason_code,
                                'SYSTEM', :created_at
                            )
                            """
                        ),
                        {
                            "id": uuid7(),
                            "version_id": version_id,
                            "state": state,
                            "reason_code": (
                                "TRIAL_CLOSED_DURING_UPLOAD"
                                if state == "FAILED" and arrived_after_close
                                else None
                            ),
                            "created_at": record.acquired_at + timedelta(microseconds=state_index),
                        },
                    )
                if record.admission_fixture and not arrived_after_close:
                    await connection.execute(
                        text("UPDATE document SET current_version_id = :version_id WHERE id = :id"),
                        {"version_id": version_id, "id": document_id},
                    )
                version_created = True
            else:
                if not isinstance(existing_version, UUID):
                    raise RepositoryConflict("document version lookup failed")
                version_id = existing_version
            await self._append_audit(
                connection,
                event_type=(
                    "SOURCE_FIXTURE_UPLOAD_TERMINATED"
                    if arrived_after_close
                    else "SOURCE_FIXTURE_UPLOADED"
                ),
                actor_id=record.actor_id,
                target_type="document",
                target_id=document_id,
                before_state=None,
                after_state={
                    "content_hash": record.content_hash,
                    "raw_object_deduplicated": raw_deduplicated,
                    "version_created": version_created,
                    "arrived_after_close": arrived_after_close,
                },
                reason=(
                    "Authorized fixture upload arrived after trial closure"
                    if arrived_after_close
                    else "Manual source fixture uploaded"
                ),
                request_id=record.request_id,
                now=record.acquired_at,
            )
        document = await self._get_document_version(document_id, version_id)
        return FixtureUploadResponse(
            document=document,
            raw_object_deduplicated=raw_deduplicated,
            version_created=version_created,
        )

    async def record_attachment(self, record: AttachmentRecord) -> UUID:
        async with self._engine.begin() as connection:
            raw_object_id = (
                await connection.execute(
                    text(
                        """
                        INSERT INTO raw_object (
                            id, sha256, object_key, byte_size, declared_mime,
                            detected_mime, scan_status, storage_etag, created_at
                        ) VALUES (
                            :id, :sha256, :object_key, :byte_size, :declared_mime,
                            :detected_mime, :scan_status, :storage_etag, :created_at
                        )
                        ON CONFLICT (sha256) DO NOTHING RETURNING id
                        """
                    ),
                    {
                        "id": record.raw_object_id,
                        "sha256": record.content_hash,
                        "object_key": record.object_key,
                        "byte_size": record.byte_size,
                        "declared_mime": record.declared_mime,
                        "detected_mime": record.detected_mime,
                        "scan_status": ("REJECTED" if record.globally_quarantined else "CLEAN"),
                        "storage_etag": record.storage_etag,
                        "created_at": record.acquired_at,
                    },
                )
            ).scalar_one_or_none()
            if not isinstance(raw_object_id, UUID):
                raw_object_id = await connection.scalar(
                    text("SELECT id FROM raw_object WHERE sha256 = :sha256"),
                    {"sha256": record.content_hash},
                )
            if not isinstance(raw_object_id, UUID):
                raise RepositoryConflict("attachment raw object upsert failed")
            if record.security_status == "CLEAN":
                blocked = await connection.scalar(
                    text(
                        """
                        SELECT raw.scan_status <> 'CLEAN'
                               OR EXISTS (
                                 SELECT 1 FROM raw_object_security_fact security
                                  WHERE security.raw_object_id=raw.id
                                    AND security.status IN ('REJECTED','QUARANTINED')
                               )
                          FROM raw_object raw WHERE raw.id=:raw_object_id
                        """
                    ),
                    {"raw_object_id": raw_object_id},
                )
                if blocked is not False:
                    raise RepositoryConflict("attachment raw object has rejected security history")
            if record.security_status == "CLEAN" or record.globally_quarantined:
                await connection.execute(
                    text(
                        """
                        INSERT INTO raw_object_security_fact (
                            id, raw_object_id, status, detected_mime,
                            rule_version, reason_code, created_at
                        ) VALUES (
                            :id, :raw_object_id, :status, :detected_mime,
                            :rule_version, :reason_code, :created_at
                        )
                        ON CONFLICT (raw_object_id, rule_version) DO NOTHING
                        """
                    ),
                    {
                        "id": uuid7(),
                        "raw_object_id": raw_object_id,
                        "status": record.security_status,
                        "rule_version": (
                            "attachment-security-3.0.0-clean"
                            if record.security_status == "CLEAN"
                            else "attachment-security-3.0.0-negative"
                        ),
                        "detected_mime": record.detected_mime,
                        "reason_code": record.reason_code,
                        "created_at": record.acquired_at,
                    },
                )
            existing_id = await connection.scalar(
                text(
                    """
                    SELECT id
                    FROM document_attachment
                    WHERE document_version_id = :document_version_id
                      AND parent_attachment_id IS NOT DISTINCT FROM :parent_attachment_id
                      AND normalized_path = :normalized_path
                      AND raw_object_id = :raw_object_id
                    LIMIT 1
                    """
                ),
                {
                    "document_version_id": record.document_version_id,
                    "parent_attachment_id": record.parent_attachment_id,
                    "normalized_path": record.normalized_path,
                    "raw_object_id": raw_object_id,
                },
            )
            if isinstance(existing_id, UUID):
                return existing_id
            await connection.execute(
                text(
                    """
                    INSERT INTO document_attachment (
                        id, document_version_id, raw_object_id, filename, role,
                        parent_attachment_id, normalized_path, depth, detected_mime,
                        byte_size, security_status, created_at
                    ) VALUES (
                        :id, :document_version_id, :raw_object_id, :filename, :role,
                        :parent_attachment_id, :normalized_path, :depth, :detected_mime,
                        :byte_size, :security_status, :created_at
                    )
                    """
                ),
                {
                    "id": record.attachment_id,
                    "document_version_id": record.document_version_id,
                    "raw_object_id": raw_object_id,
                    "filename": record.filename,
                    "role": record.role,
                    "parent_attachment_id": record.parent_attachment_id,
                    "normalized_path": record.normalized_path,
                    "depth": record.depth,
                    "detected_mime": record.detected_mime,
                    "byte_size": record.byte_size,
                    "security_status": record.security_status,
                    "created_at": record.acquired_at,
                },
            )
        return record.attachment_id

    async def record_attachment_attempt(self, record: AttachmentAttemptRecord) -> UUID:
        async with self._engine.begin() as connection:
            attempt_id = await connection.scalar(
                text(
                    """
                    SELECT append_document_attachment_attempt(
                      :attempt_id,:document_version_id,:content_sha256,
                      :object_key,:storage_etag,:byte_size,:declared_mime,
                      :detected_mime,:filename_sha256,:normalized_path_sha256,
                      :canonical_url_sha256,:outcome,:reason_code,:occurred_at
                    )
                    """
                ),
                {
                    "attempt_id": record.attempt_id,
                    "document_version_id": record.document_version_id,
                    "content_sha256": record.content_hash,
                    "object_key": record.object_key,
                    "storage_etag": record.storage_etag,
                    "byte_size": record.byte_size,
                    "declared_mime": record.declared_mime,
                    "detected_mime": record.detected_mime,
                    "filename_sha256": record.filename_sha256,
                    "normalized_path_sha256": record.normalized_path_sha256,
                    "canonical_url_sha256": record.canonical_url_sha256,
                    "outcome": record.outcome,
                    "reason_code": record.reason_code,
                    "occurred_at": record.acquired_at,
                },
            )
        if not isinstance(attempt_id, UUID):
            raise RepositoryConflict("attachment attempt evidence was not appended")
        return attempt_id

    async def record_rejected_raw(self, record: RejectedRawRecord) -> UUID | None:
        async with self._engine.begin() as connection:
            if record.trial_run_id is None:
                raise RepositoryConflict("rejected fixture attempt has no trial context")
            if not record.globally_quarantined:
                contextual_raw_id = await connection.scalar(
                    text("SELECT id FROM raw_object WHERE sha256=:sha256"),
                    {"sha256": record.content_hash},
                )
                raw_id = contextual_raw_id if isinstance(contextual_raw_id, UUID) else None
                await self._append_rejected_trial_attempt(connection, record, raw_id)
                return raw_id
            raw_object_id = (
                await connection.execute(
                    text(
                        """
                        INSERT INTO raw_object (
                            id, sha256, object_key, byte_size, declared_mime,
                            detected_mime, scan_status, storage_etag, created_at
                        ) VALUES (
                            :id, :sha256, :object_key, :byte_size, :declared_mime,
                            :detected_mime, 'REJECTED', :storage_etag, :created_at
                        )
                        ON CONFLICT (sha256) DO NOTHING RETURNING id
                        """
                    ),
                    {
                        "id": record.raw_object_id,
                        "sha256": record.content_hash,
                        "object_key": record.object_key,
                        "byte_size": record.byte_size,
                        "declared_mime": record.declared_mime,
                        "detected_mime": record.detected_mime,
                        "storage_etag": record.storage_etag,
                        "created_at": record.acquired_at,
                    },
                )
            ).scalar_one_or_none()
            if not isinstance(raw_object_id, UUID):
                raw_object_id = await connection.scalar(
                    text("SELECT id FROM raw_object WHERE sha256 = :sha256"),
                    {"sha256": record.content_hash},
                )
            if not isinstance(raw_object_id, UUID):
                raise RepositoryConflict("rejected raw object upsert failed")
            affected_version_ids = list(
                await connection.scalars(
                    text(
                        """
                        SELECT version.id FROM document_version version
                         WHERE version.raw_object_id=:raw_object_id
                           AND NOT EXISTS (
                             SELECT 1 FROM document_version_state_event terminal
                              WHERE terminal.document_version_id=version.id
                                AND terminal.state IN ('QUARANTINED','FAILED')
                           )
                        """
                    ),
                    {"raw_object_id": raw_object_id},
                )
            )
            for version_id in affected_version_ids:
                await connection.execute(
                    text(
                        """
                        INSERT INTO document_version_state_event(
                          id,document_version_id,state,reason_code,actor_type,created_at
                        ) VALUES (
                          :id,:version_id,'QUARANTINED',:reason_code,'SYSTEM',
                          GREATEST(
                            CAST(:created_at AS timestamptz),
                            COALESCE((
                              SELECT max(existing.created_at) + interval '1 microsecond'
                                FROM document_version_state_event existing
                               WHERE existing.document_version_id=:version_id
                            ),CAST(:created_at AS timestamptz))
                          )
                        )
                        """
                    ),
                    {
                        "id": uuid7(),
                        "version_id": version_id,
                        "reason_code": record.reason_code,
                        "created_at": record.acquired_at,
                    },
                )
            await connection.execute(
                text(
                    """
                    UPDATE document document_row
                       SET current_version_id=(
                         SELECT candidate.id
                           FROM document_version candidate
                           JOIN raw_object candidate_raw
                             ON candidate_raw.id=candidate.raw_object_id
                          WHERE candidate.document_id=document_row.id
                            AND candidate.raw_object_id<>:raw_object_id
                            AND candidate_raw.scan_status='CLEAN'
                            AND NOT EXISTS (
                              SELECT 1 FROM raw_object_security_fact negative
                               WHERE negative.raw_object_id=candidate_raw.id
                                 AND negative.status IN ('REJECTED','QUARANTINED')
                            )
                            AND (
                              SELECT state.state
                                FROM document_version_state_event state
                               WHERE state.document_version_id=candidate.id
                               ORDER BY state.created_at DESC,state.id DESC LIMIT 1
                            )='READY'
                          ORDER BY candidate.version_number DESC,candidate.id DESC
                          LIMIT 1
                       )
                     WHERE document_row.current_version_id IN (
                       SELECT blocked.id FROM document_version blocked
                        WHERE blocked.raw_object_id=:raw_object_id
                     )
                    """
                ),
                {"raw_object_id": raw_object_id},
            )
            await connection.execute(
                text(
                    """
                    INSERT INTO raw_object_security_fact (
                        id, raw_object_id, status, detected_mime,
                        rule_version, reason_code, created_at
                    ) VALUES (
                        :id, :raw_object_id, 'QUARANTINED', :detected_mime,
                        'source-vault-3.0.0', :reason_code, :created_at
                    )
                    ON CONFLICT (raw_object_id, rule_version) DO NOTHING
                    """
                ),
                {
                    "id": uuid7(),
                    "raw_object_id": raw_object_id,
                    "detected_mime": record.detected_mime,
                    "reason_code": record.reason_code,
                    "created_at": record.acquired_at,
                },
            )
            await self._append_rejected_trial_attempt(connection, record, raw_object_id)
        return raw_object_id

    async def _append_rejected_trial_attempt(
        self,
        connection: AsyncConnection,
        record: RejectedRawRecord,
        raw_object_id: UUID | None,
    ) -> None:
        if record.trial_run_id is None:
            raise RepositoryConflict("rejected fixture attempt has no trial context")
        attempt_id = uuid7()
        await connection.execute(
            text(
                """
                SELECT append_source_trial_rejected_raw_attempt(
                  :id,:source_id,:trial_run_id,:raw_object_id,:content_sha256,
                  :object_key,:canonical_url,:reason_code,:actor_id,:request_id,
                  :occurred_at
                )
                """
            ),
            {
                "id": attempt_id,
                "source_id": record.source_id,
                "trial_run_id": record.trial_run_id,
                "raw_object_id": raw_object_id,
                "content_sha256": record.content_hash,
                "object_key": record.object_key,
                "canonical_url": record.canonical_url,
                "reason_code": record.reason_code,
                "actor_id": record.actor_id,
                "request_id": record.request_id,
                "occurred_at": record.acquired_at,
            },
        )

    async def get_document(self, document_id: UUID) -> DocumentDetail:
        return await self._get_document_version(document_id, None)

    async def _get_document_version(
        self,
        document_id: UUID,
        version_id: UUID | None,
    ) -> DocumentDetail:
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
                        JOIN document_version v
                          ON v.id = COALESCE(CAST(:version_id AS uuid), d.current_version_id)
                        JOIN raw_object r ON r.id = v.raw_object_id
                        WHERE d.id = :document_id
                        """
                        ),
                        {"document_id": document_id, "version_id": version_id},
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
                    text(
                        """
                        SELECT id,state,enabled,lifecycle_state,trial_kind,
                               current_trial_run_id
                          FROM source WHERE id=:id
                        """
                    ),
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
        await connection.execute(
            text(
                """
                SELECT append_audit_event(
                    :id, :event_type, :actor_id, :target_type, :target_id,
                    CAST(:before_state AS jsonb), CAST(:after_state AS jsonb),
                    :reason, :request_id, :created_at
                )
                """
            ),
            {
                "id": uuid7(),
                "event_type": event_type,
                "actor_id": actor_id,
                "target_type": target_type,
                "target_id": target_id,
                "before_state": None if before_state is None else _json(before_state),
                "after_state": None if after_state is None else _json(after_state),
                "reason": reason,
                "request_id": request_id,
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
        lifecycle_state=SourceLifecycleState(row["lifecycle_state"]),
        trial_kind=None if row["trial_kind"] is None else SourceTrialKind(row["trial_kind"]),
        registered_by=row["registered_by"],
        governance_owner_id=row["governance_owner_id"],
        country_codes=tuple(row["country_codes"]),
        region_codes=tuple(row["region_codes"]),
        language_tags=tuple(row["language_tags"]),
        industries=tuple(row["industries"]),
        content_domains=tuple(row["content_domains"]),
        declared_roles=tuple(row["declared_roles"]),
        current_policy_version_id=row["current_policy_version_id"],
        current_connector_config_version_id=row["current_connector_config_version_id"],
        current_trial_run_id=row["current_trial_run_id"],
        created_at=row["created_at"],
    )


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
        and row.get("status") == PersonalSourceStreamStatus.READY.value
        and row.get("schedule_status") == "ACTIVE"
        and row.get("access_state") == "ACCESSIBLE"
        and int(row.get("requests_used") or 0) < request_budget
        and int(row.get("bytes_used") or 0) < byte_budget
        and row.get("circuit_state") in {"CLOSED", "HALF_OPEN"}
    )


def _encode_personal_activity_cursor(occurred_at: datetime, item_id: UUID) -> str:
    value = json.dumps(
        {"at": occurred_at.isoformat(), "id": str(item_id)},
        separators=(",", ":"),
    ).encode()
    return base64.urlsafe_b64encode(value).decode().rstrip("=")


def _decode_personal_activity_cursor(value: str | None) -> tuple[datetime | None, UUID | None]:
    if value is None:
        return None, None
    try:
        decoded = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
        payload = json.loads(decoded)
        occurred_at = datetime.fromisoformat(payload["at"])
        if occurred_at.tzinfo is None:
            raise ValueError("cursor time must be timezone-aware")
        return occurred_at, UUID(payload["id"])
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
