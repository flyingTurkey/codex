"""PostgreSQL adapter for source candidates, qualification facts and streams."""

# All composed SQL below uses module constants and bound parameters only.
# ruff: noqa: S608

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine
from srbg_contracts import (
    DiscoveryChannel,
    QualificationBundleView,
    QualificationCheckView,
    QualificationRunStatus,
    QualificationRunView,
    QualificationVerdict,
    SourceAttentionItem,
    SourceCandidateAction,
    SourceCandidateCreateRequest,
    SourceCandidateDetail,
    SourceCandidateStatus,
    SourceCandidateSummary,
    SourceContentDomain,
    SourceIndustry,
    SourceStreamAction,
    SourceStreamStatus,
    SourceStreamView,
)

from srbg_api.identifiers import uuid7


class SourceAutomationNotFound(LookupError):
    """An automation aggregate does not exist."""


class SourceAutomationConflict(RuntimeError):
    """An authoritative automation command rejected stale or conflicting state."""


@dataclass(frozen=True, slots=True)
class CandidateSlice:
    items: list[SourceCandidateSummary]
    status_counts: dict[SourceCandidateStatus, int]


@dataclass(frozen=True, slots=True)
class StreamSlice:
    items: list[SourceStreamView]


@dataclass(frozen=True, slots=True)
class AttentionSlice:
    items: list[SourceAttentionItem]


@dataclass(frozen=True, slots=True)
class ActivationRecord:
    decision_id: UUID
    source_id: UUID | None
    outbox_id: UUID | None
    candidate_status: SourceCandidateStatus
    idempotent_replay: bool


class PostgresSourceAutomationRepository:
    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def close(self) -> None:
        await self._engine.dispose()

    async def list_candidates(
        self,
        *,
        limit: int,
        after: tuple[datetime, UUID] | None,
        status: SourceCandidateStatus | None,
        verdict: QualificationVerdict | None,
        discovery_channel: DiscoveryChannel | None,
        industry: SourceIndustry | None,
        content_domain: SourceContentDomain | None,
        language_tag: str | None,
        query: str | None,
    ) -> CandidateSlice:
        after_at, after_id = after if after is not None else (None, None)
        parameters = {
            "limit": limit,
            "after_at": after_at,
            "after_id": after_id,
            "status": None if status is None else status.value,
            "verdict": None if verdict is None else verdict.value,
            "channel": None if discovery_channel is None else discovery_channel.value,
            "industry": None if industry is None else industry.value,
            "content_domain": None if content_domain is None else content_domain.value,
            "language_tag": language_tag,
            "query": None if query is None else f"%{query.casefold()}%",
        }
        async with self._engine.connect() as connection:
            rows = (
                await connection.execute(text(_CANDIDATE_LIST_SQL), parameters)
            ).mappings().all()
            count_rows = (
                await connection.execute(
                    text(
                        "SELECT status,count(*) AS count FROM source_candidate "
                        "GROUP BY status"
                    )
                )
            ).mappings().all()
        return CandidateSlice(
            items=[_candidate_summary(row) for row in rows],
            status_counts={
                SourceCandidateStatus(str(row["status"])): int(row["count"])
                for row in count_rows
            },
        )

    async def get_candidate(self, candidate_id: UUID) -> SourceCandidateDetail:
        async with self._engine.connect() as connection:
            row = (
                await connection.execute(
                    text(_CANDIDATE_BY_ID_SQL), {"candidate_id": candidate_id}
                )
            ).mappings().one_or_none()
            if row is None:
                raise SourceAutomationNotFound("source candidate was not found")
            reference_rows = (
                await connection.execute(
                    text(
                        "SELECT target_evidence_ref FROM source_candidate_occurrence "
                        "WHERE candidate_id=:candidate_id "
                        "ORDER BY discovered_at DESC,id DESC LIMIT 100"
                    ),
                    {"candidate_id": candidate_id},
                )
            ).mappings().all()
            history_rows = (
                await connection.execute(
                    text(_QUALIFICATION_HISTORY_SQL), {"candidate_id": candidate_id}
                )
            ).mappings().all()
            dismissed_reason = await connection.scalar(
                text(
                    "SELECT reason FROM source_candidate_decision "
                    "WHERE candidate_id=:candidate_id AND decision='DISMISS' "
                    "ORDER BY created_at DESC,id DESC LIMIT 1"
                ),
                {"candidate_id": candidate_id},
            )
        summary = _candidate_summary(row)
        return SourceCandidateDetail(
            **summary.model_dump(),
            discovery_references=[str(item["target_evidence_ref"]) for item in reference_rows],
            qualification_history=[
                bundle
                for item in history_rows
                if (bundle := _bundle_from_row(item, prefix="")) is not None
            ],
            enabled_source_id=row["source_id"],
            dismissed_reason=(
                str(dismissed_reason) if dismissed_reason is not None else None
            ),
        )

    async def register_manual_candidate(
        self,
        payload: SourceCandidateCreateRequest,
        *,
        canonical_url: str,
        canonical_url_sha256: str,
        authorization_boundary: str,
        material_fingerprint: str,
        actor_id: UUID,
        request_id: str,
        now: datetime,
    ) -> UUID:
        candidate_id, occurrence_id, audit_id = uuid7(), uuid7(), uuid7()
        try:
            async with self._engine.begin() as connection:
                result = await connection.scalar(
                    text(
                        """
                        SELECT register_discovered_source_candidate(
                          :candidate_id,:occurrence_id,:canonical_url,:url_sha256,
                          :boundary,:material_fingerprint,'MANUAL',:evidence_ref,
                          CAST(:industries AS text[]),CAST(:content_domains AS text[]),
                          CAST(:language_tags AS text[]),:actor_id,:reason,:request_id,
                          :audit_id,:now
                        )
                        """
                    ),
                    {
                        "candidate_id": candidate_id,
                        "occurrence_id": occurrence_id,
                        "canonical_url": canonical_url,
                        "url_sha256": canonical_url_sha256,
                        "boundary": authorization_boundary,
                        "material_fingerprint": material_fingerprint,
                        "evidence_ref": f"manual-submission:{request_id}",
                        "industries": [value.value for value in payload.industries],
                        "content_domains": [value.value for value in payload.content_domains],
                        "language_tags": payload.language_tags,
                        "actor_id": actor_id,
                        "reason": payload.reason,
                        "request_id": request_id,
                        "audit_id": audit_id,
                        "now": now,
                    },
                )
        except Exception as exc:
            raise SourceAutomationConflict("candidate registration was rejected") from exc
        if not isinstance(result, UUID):
            raise SourceAutomationConflict("candidate registration returned no identifier")
        return result

    async def request_qualification(
        self,
        candidate_id: UUID,
        *,
        rule_version: str,
        reason: str,
        actor_id: UUID,
        request_id: str,
        now: datetime,
    ) -> QualificationRunView:
        run_id, audit_id = uuid7(), uuid7()
        try:
            async with self._engine.begin() as connection:
                await connection.execute(
                    text(
                        "SELECT request_source_qualification("
                        ":run_id,:candidate_id,:rule_version,:actor_id,:reason,"
                        ":request_id,:audit_id,:now)"
                    ),
                    {
                        "run_id": run_id,
                        "candidate_id": candidate_id,
                        "rule_version": rule_version,
                        "actor_id": actor_id,
                        "reason": reason,
                        "request_id": request_id,
                        "audit_id": audit_id,
                        "now": now,
                    },
                )
        except Exception as exc:
            raise SourceAutomationConflict(
                "qualification request conflicts with current state"
            ) from exc
        return QualificationRunView(
            id=run_id,
            candidate_id=candidate_id,
            status=QualificationRunStatus.PENDING,
            rule_version=rule_version,
            requested_by=actor_id,
            created_at=now,
        )

    async def activate_candidate(
        self,
        candidate_id: UUID,
        *,
        decision: str,
        expected_bundle_sha256: str | None,
        request_sha256: str,
        idempotency_key: str,
        reason: str,
        waiver_reason: str | None,
        actor_id: UUID,
        now: datetime,
    ) -> ActivationRecord:
        identifiers = [uuid7() for _ in range(7)]
        candidate_decision_id = identifiers[0]
        parameters = {
            "candidate_id": candidate_id,
            "decision": decision,
            "bundle_sha256": expected_bundle_sha256,
            "request_sha256": request_sha256,
            "idempotency_key": idempotency_key,
            "reason": reason,
            "waiver_reason": waiver_reason,
            "actor_id": actor_id,
            "candidate_decision_id": candidate_decision_id,
            "governance_decision_id": identifiers[1],
            "lifecycle_event_id": identifiers[2],
            "stream_id": identifiers[3],
            "outbox_id": identifiers[4],
            "source_audit_id": identifiers[5],
            "candidate_audit_id": identifiers[6],
            "now": now,
        }
        try:
            async with self._engine.begin() as connection:
                row = (
                    await connection.execute(text(_ACTIVATE_CANDIDATE_SQL), parameters)
                ).mappings().one()
        except Exception as exc:
            raise SourceAutomationConflict(_bounded_conflict_code(exc)) from exc
        returned_decision_id = row["decision_id"]
        if not isinstance(returned_decision_id, UUID):
            raise SourceAutomationConflict("activation returned no decision identifier")
        return ActivationRecord(
            decision_id=returned_decision_id,
            source_id=row["source_id"],
            outbox_id=row["outbox_id"],
            candidate_status=SourceCandidateStatus(str(row["candidate_status"])),
            idempotent_replay=returned_decision_id != candidate_decision_id,
        )

    async def list_streams(
        self,
        *,
        limit: int,
        after: tuple[datetime, UUID] | None,
        query: str | None,
    ) -> StreamSlice:
        after_at, after_id = after if after is not None else (None, None)
        async with self._engine.connect() as connection:
            rows = (
                await connection.execute(
                    text(_STREAM_LIST_SQL),
                    {
                        "limit": limit,
                        "after_at": after_at,
                        "after_id": after_id,
                        "query": None if query is None else f"%{query.casefold()}%",
                    },
                )
            ).mappings().all()
        return StreamSlice(items=[_stream_view(row) for row in rows])

    async def list_attention(
        self,
        *,
        limit: int,
        after: tuple[datetime, UUID] | None,
    ) -> AttentionSlice:
        after_at, after_id = after if after is not None else (None, None)
        async with self._engine.connect() as connection:
            rows = (
                await connection.execute(
                    text(_ATTENTION_LIST_SQL),
                    {"limit": limit, "after_at": after_at, "after_id": after_id},
                )
            ).mappings().all()
        return AttentionSlice(
            items=[
                SourceAttentionItem(
                    stream=_stream_view(row),
                    reason_codes=list(row["reason_codes"]),
                    first_observed_at=row["first_observed_at"],
                    last_observed_at=row["last_observed_at"],
                )
                for row in rows
            ]
        )


def _bundle_from_row(row: Any, *, prefix: str = "bundle_") -> QualificationBundleView | None:
    bundle_id = row.get(f"{prefix}id")
    if bundle_id is None:
        return None
    checks_value = row.get(f"{prefix}checks") or []
    checks = [QualificationCheckView.model_validate(value) for value in checks_value]
    return QualificationBundleView(
        id=bundle_id,
        candidate_id=row[f"{prefix}candidate_id"],
        run_id=row[f"{prefix}run_id"],
        rule_version=row[f"{prefix}rule_version"],
        material_fingerprint=row[f"{prefix}material_fingerprint"],
        verdict=row[f"{prefix}verdict"],
        storage_policy=row[f"{prefix}storage_policy"],
        evidence_capture_policy=row[f"{prefix}evidence_capture_policy"],
        checks=checks,
        sampled_item_count=row[f"{prefix}sampled_item_count"],
        relevant_item_count=row[f"{prefix}relevant_item_count"],
        reason_codes=list(row[f"{prefix}reason_codes"] or []),
        bundle_sha256=row[f"{prefix}bundle_sha256"],
        created_at=row[f"{prefix}created_at"],
        expires_at=row[f"{prefix}valid_until"],
    )


def _candidate_summary(row: Any) -> SourceCandidateSummary:
    bundle = _bundle_from_row(row)
    status = SourceCandidateStatus(str(row["status"]))
    actions: list[SourceCandidateAction] = []
    if status in {
        SourceCandidateStatus.DISCOVERED,
        SourceCandidateStatus.BLOCKED,
        SourceCandidateStatus.STALE,
    }:
        actions.append(SourceCandidateAction.REQUEST_QUALIFICATION)
    if status in {
        SourceCandidateStatus.READY_FOR_DECISION,
        SourceCandidateStatus.BLOCKED,
    }:
        actions.append(SourceCandidateAction.DISMISS)
        if (
            status is SourceCandidateStatus.READY_FOR_DECISION
            and bundle is not None
            and bundle.verdict is not QualificationVerdict.BLOCKED
        ):
            actions.append(SourceCandidateAction.ENABLE)
    batch_eligible = bool(
        status is SourceCandidateStatus.READY_FOR_DECISION
        and bundle is not None
        and bundle.verdict is QualificationVerdict.QUALIFIED
        and bundle.expires_at > datetime.now(UTC)
    )
    return SourceCandidateSummary(
        id=row["id"],
        institution_name=row["institution_name"],
        canonical_url=row["canonical_url"],
        authorization_boundary=row["authorization_boundary"],
        discovery_channels=[DiscoveryChannel(value) for value in row["discovery_channels"]],
        status=status,
        industries=list(row["industries"] or []),
        content_domains=list(row["content_domains"] or []),
        language_tags=list(row["language_tags"] or []),
        occurrence_count=row["occurrence_count"],
        first_discovered_at=row["first_discovered_at"],
        last_discovered_at=row["last_discovered_at"],
        latest_qualification=bundle,
        available_actions=actions,
        batch_enable_eligible=batch_eligible,
    )


def _stream_view(row: Any) -> SourceStreamView:
    status = SourceStreamStatus(str(row["stream_status"]))
    if status is SourceStreamStatus.ACTIVE:
        actions = [
            SourceStreamAction.PAUSE,
            SourceStreamAction.REQUEST_REPAIR,
            SourceStreamAction.REVOKE,
        ]
    elif status is SourceStreamStatus.PAUSED:
        actions = [
            SourceStreamAction.RESUME,
            SourceStreamAction.REQUEST_REPAIR,
            SourceStreamAction.REVOKE,
        ]
    elif status is SourceStreamStatus.QUALIFIED:
        actions = [SourceStreamAction.REQUEST_REPAIR, SourceStreamAction.REVOKE]
    else:
        actions = []
    return SourceStreamView(
        id=row["stream_id"],
        source_id=row["source_id"],
        candidate_id=row["candidate_id"],
        institution_name=row["institution_name"],
        canonical_url=row["canonical_url"],
        authorization_boundary=row["authorization_boundary"],
        stream_key=row["stream_key"],
        status=status,
        rule_version=row["rule_version"],
        available_actions=actions,
        last_success_at=row["last_success_at"],
        last_failure_at=row["last_failure_at"],
        consecutive_failure_count=row["consecutive_failure_count"],
        next_fetch_at=row["next_fetch_at"],
        updated_at=row["updated_at"],
    )


def _bounded_conflict_code(exc: Exception) -> str:
    message = str(exc)
    for code in (
        "IDEMPOTENCY_CONFLICT",
        "STALE_QUALIFICATION_BUNDLE",
        "WARN_WAIVABLE requires waiver_reason",
        "candidate verdict cannot be enabled",
        "separation of duties",
    ):
        if code in message:
            return code
    return "SOURCE_AUTOMATION_CONFLICT"


_BUNDLE_COLUMNS = """
bundle.id AS bundle_id,bundle.candidate_id AS bundle_candidate_id,
bundle.run_id AS bundle_run_id,bundle.rule_version AS bundle_rule_version,
bundle.material_fingerprint AS bundle_material_fingerprint,
bundle.verdict AS bundle_verdict,bundle.storage_policy AS bundle_storage_policy,
bundle.evidence_capture_policy AS bundle_evidence_capture_policy,
bundle.checks AS bundle_checks,bundle.sampled_item_count AS bundle_sampled_item_count,
bundle.relevant_item_count AS bundle_relevant_item_count,
bundle.reason_codes AS bundle_reason_codes,bundle.bundle_sha256 AS bundle_bundle_sha256,
bundle.created_at AS bundle_created_at,bundle.valid_until AS bundle_valid_until
"""

_CANDIDATE_SELECT = f"""  # noqa: S608 - composed exclusively from static SQL constants
SELECT candidate.id,candidate.institution_name,candidate.canonical_url,
       candidate.authorization_boundary,candidate.status,candidate.industries,
       candidate.content_domains,candidate.language_tags,candidate.occurrence_count,
       candidate.first_discovered_at,candidate.last_discovered_at,candidate.source_id,
       ARRAY(
         SELECT DISTINCT occurrence.discovery_channel
           FROM source_candidate_occurrence occurrence
          WHERE occurrence.candidate_id=candidate.id
          ORDER BY occurrence.discovery_channel
       ) AS discovery_channels,
       {_BUNDLE_COLUMNS}
  FROM source_candidate candidate
  LEFT JOIN source_qualification_bundle bundle ON bundle.id=candidate.current_bundle_id
"""

_CANDIDATE_LIST_SQL = _CANDIDATE_SELECT + """  # noqa: S608 - static SQL
 WHERE (:status IS NULL OR candidate.status=:status)
   AND (:verdict IS NULL OR bundle.verdict=:verdict)
   AND (:channel IS NULL OR EXISTS(
     SELECT 1 FROM source_candidate_occurrence occurrence
      WHERE occurrence.candidate_id=candidate.id
        AND occurrence.discovery_channel=:channel
   ))
   AND (:industry IS NULL OR :industry=ANY(candidate.industries))
   AND (:content_domain IS NULL OR :content_domain=ANY(candidate.content_domains))
   AND (:language_tag IS NULL OR :language_tag=ANY(candidate.language_tags))
   AND (:query IS NULL OR lower(candidate.institution_name) LIKE :query
        OR lower(candidate.canonical_url) LIKE :query)
   AND (:after_at IS NULL OR (candidate.last_discovered_at,candidate.id)<(:after_at,:after_id))
 ORDER BY candidate.last_discovered_at DESC,candidate.id DESC
 LIMIT :limit
"""

_CANDIDATE_BY_ID_SQL = (
    _CANDIDATE_SELECT + " WHERE candidate.id=:candidate_id"
)

_QUALIFICATION_HISTORY_SQL = """
SELECT bundle.id,bundle.candidate_id,bundle.run_id,bundle.rule_version,
       bundle.material_fingerprint,bundle.verdict,bundle.storage_policy,
       bundle.evidence_capture_policy,bundle.checks,bundle.sampled_item_count,
       bundle.relevant_item_count,bundle.reason_codes,bundle.bundle_sha256,
       bundle.created_at,bundle.valid_until
  FROM source_qualification_bundle bundle
 WHERE bundle.candidate_id=:candidate_id
 ORDER BY bundle.created_at DESC,bundle.id DESC LIMIT 50
"""

_ACTIVATE_CANDIDATE_SQL = """
SELECT decision_id,source_id,outbox_id,candidate_status
  FROM activate_qualified_candidate(
    :candidate_id,:decision,:bundle_sha256,:request_sha256,:idempotency_key,
    :reason,:waiver_reason,:actor_id,:candidate_decision_id,
    :governance_decision_id,:lifecycle_event_id,:stream_id,:outbox_id,
    :source_audit_id,:candidate_audit_id,:now
  )
"""

_STREAM_SELECT = """
SELECT stream.id AS stream_id,stream.source_id,stream.candidate_id,
       source_row.name AS institution_name,stream.canonical_url,
       stream.authorization_boundary,stream.stream_key,stream.status AS stream_status,
       COALESCE(bundle.rule_version,'REQUALIFICATION_REQUIRED') AS rule_version,
       COALESCE(stream.last_success_at,last_success.completed_at) AS last_success_at,
       last_failure.completed_at AS last_failure_at,
       COALESCE(schedule.consecutive_failures,0) AS consecutive_failure_count,
       schedule.next_run_at AS next_fetch_at,stream.updated_at
  FROM source_stream stream
  JOIN source source_row ON source_row.id=stream.source_id
  LEFT JOIN source_candidate candidate ON candidate.id=stream.candidate_id
  LEFT JOIN source_qualification_bundle bundle ON bundle.id=candidate.current_bundle_id
  LEFT JOIN fetch_schedule schedule ON schedule.id=stream.schedule_id
  LEFT JOIN LATERAL(
    SELECT run.completed_at FROM fetch_run run
     WHERE run.source_id=stream.source_id AND run.status IN ('SUCCEEDED','NOT_MODIFIED')
     ORDER BY run.completed_at DESC NULLS LAST,run.id DESC LIMIT 1
  ) last_success ON true
  LEFT JOIN LATERAL(
    SELECT run.completed_at FROM fetch_run run
     WHERE run.source_id=stream.source_id AND run.status IN ('FAILED','PARTIAL')
     ORDER BY run.completed_at DESC NULLS LAST,run.id DESC LIMIT 1
  ) last_failure ON true
"""

_STREAM_LIST_SQL = _STREAM_SELECT + """  # noqa: S608 - static SQL
 WHERE (:query IS NULL OR lower(source_row.name) LIKE :query
        OR lower(stream.canonical_url) LIKE :query)
   AND (:after_at IS NULL OR (stream.updated_at,stream.id)<(:after_at,:after_id))
 ORDER BY stream.updated_at DESC,stream.id DESC LIMIT :limit
"""

_ATTENTION_LIST_SQL = _STREAM_SELECT + """  # noqa: S608 - static SQL
 JOIN LATERAL(
   SELECT array_agg(DISTINCT anomaly.code ORDER BY anomaly.code) AS reason_codes,
          min(anomaly.detected_at) AS first_observed_at,
          max(anomaly.detected_at) AS last_observed_at
     FROM source_anomaly anomaly
    WHERE anomaly.source_id=stream.source_id
      AND anomaly.status IN ('OPEN','ACKNOWLEDGED')
 ) attention ON attention.reason_codes IS NOT NULL
 WHERE (:after_at IS NULL OR (attention.last_observed_at,stream.id)<(:after_at,:after_id))
 ORDER BY attention.last_observed_at DESC,stream.id DESC LIMIT :limit
"""
