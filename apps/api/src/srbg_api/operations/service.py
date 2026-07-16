"""PostgreSQL-backed operational control plane."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import RowMapping
from sqlalchemy.ext.asyncio import AsyncEngine
from srbg_contracts import (
    CircuitState,
    FetchScheduleStatus,
    FetchScheduleUpdate,
    FetchScheduleView,
    MetricSample,
    OperationsOverview,
    PilotMetrics,
    ReplayRequest,
    ReplayResult,
    ReplayTaskView,
    SourceAnomalyView,
    SourceHealthView,
)

from srbg_api.identifiers import uuid7


class OperationsRejected(RuntimeError):
    pass


def _schedule_view(row: Mapping[str, Any] | RowMapping) -> FetchScheduleView:
    return FetchScheduleView(
        source_id=row["source_id"],
        authority_level=row["authority_level"],
        status=FetchScheduleStatus(row["status"]),
        interval_seconds=row["interval_seconds"],
        next_run_at=row["next_run_at"],
        circuit_state=CircuitState(row["circuit_state"]),
        circuit_open_until=row["circuit_open_until"],
        consecutive_failures=row["consecutive_failures"],
        freshness_slo_seconds=row["freshness_slo_seconds"],
        rate_limit_per_minute=row["rate_limit_per_minute"],
        daily_request_budget=row["daily_request_budget"],
        daily_byte_budget=row["daily_byte_budget"],
        requests_used=row["requests_used"],
        bytes_used=row["bytes_used"],
        version=row["version"],
        updated_at=row["updated_at"],
    )


class PostgresOperationsService:
    def __init__(
        self,
        engine: AsyncEngine,
        projection_engine: AsyncEngine | None = None,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._engine = engine
        self._projection_engine = projection_engine
        self._now = now or (lambda: datetime.now(UTC))

    async def close(self) -> None:
        await self._engine.dispose()
        if self._projection_engine is not None:
            await self._projection_engine.dispose()

    async def overview(self) -> OperationsOverview:
        async with self._engine.connect() as connection:
            row = (
                (
                    await connection.execute(
                        text(
                            """
                        SELECT
                          (SELECT count(*) FROM source_checkpoint
                             WHERE consecutive_failures > 0) AS unhealthy_sources,
                          (SELECT count(*) FROM source_checkpoint
                             WHERE circuit_open_until > now()) AS open_circuits,
                          (SELECT count(*) FROM review_task
                            WHERE status = 'PENDING') AS pending_reviews,
                          (SELECT count(*) FROM outbox_event
                            WHERE processed_at IS NULL) AS outbox_depth,
                          (SELECT count(*) FROM failed_task
                            WHERE resolved_at IS NULL) AS failed_tasks,
                          (SELECT count(*) FROM replay_request
                            WHERE status = 'QUEUED') AS queued_replays,
                          (SELECT COALESCE(EXTRACT(epoch FROM now() - min(started_at)), 0)
                             FROM fetch_run
                            WHERE status IN (
                              'PENDING_DISPATCH','DISPATCHED','RETRY_WAIT'
                            ))
                             AS fetch_backlog_age_seconds,
                          (SELECT count(*) FROM source_health_snapshot
                             WHERE freshness_status='VIOLATED' OR discovery_status='FALSE_SUCCESS')
                             AS source_slo_violations,
                          (SELECT count(*) FROM failed_task WHERE resolved_at IS NULL
                             AND reconstruction_status IN ('BLOCKED','NON_REPLAYABLE'))
                             AS blocked_replays,
                          (SELECT count(*) FROM retention_execution WHERE status='FAILED')
                             AS retention_failures,
                          (SELECT count(*) FROM ai_step_run
                            WHERE status = 'FAILED'
                              AND created_at >= now() - interval '24 hours') AS ai_failures,
                          (SELECT COALESCE(sum(cost_microusd), 0) FROM ai_step_run
                            WHERE created_at >= now() - interval '24 hours') AS ai_cost,
                          (SELECT COALESCE(percentile_cont(0.95) WITHIN GROUP
                              (ORDER BY latency_ms), 0) FROM ai_step_run
                            WHERE created_at >= now() - interval '24 hours') AS ai_p95_ms,
                          (SELECT COALESCE(sum(cost_microusd) /
                              NULLIF(count(DISTINCT pipeline_run_id), 0), 0)
                             FROM ai_step_run
                            WHERE created_at >= now() - interval '24 hours') AS ai_doc_cost
                        """
                        )
                    )
                )
                .mappings()
                .one()
            )
        metrics = [
            MetricSample(
                code="UNHEALTHY_SOURCES",
                value=row["unhealthy_sources"],
                unit="count",
                status="PASS" if row["unhealthy_sources"] == 0 else "FAIL",
            ),
            MetricSample(
                code="OPEN_SOURCE_CIRCUITS",
                value=row["open_circuits"],
                unit="count",
                status="PASS" if row["open_circuits"] == 0 else "FAIL",
            ),
            MetricSample(
                code="PENDING_REVIEWS", value=row["pending_reviews"], unit="count", status="UNKNOWN"
            ),
            MetricSample(
                code="PUBLISHER_OUTBOX_DEPTH",
                value=row["outbox_depth"],
                unit="count",
                status="PASS" if row["outbox_depth"] == 0 else "UNKNOWN",
            ),
            MetricSample(
                code="FAILED_TASKS",
                value=row["failed_tasks"],
                unit="count",
                status="PASS" if row["failed_tasks"] == 0 else "FAIL",
            ),
            MetricSample(
                code="QUEUED_REPLAYS", value=row["queued_replays"], unit="count", status="UNKNOWN"
            ),
            MetricSample(
                code="FETCH_BACKLOG_AGE_SECONDS",
                value=float(row["fetch_backlog_age_seconds"]),
                unit="seconds",
                status="PASS" if row["fetch_backlog_age_seconds"] <= 900 else "FAIL",
            ),
            MetricSample(
                code="SOURCE_SLO_VIOLATIONS",
                value=row["source_slo_violations"],
                unit="count",
                status="PASS" if row["source_slo_violations"] == 0 else "FAIL",
            ),
            MetricSample(
                code="BLOCKED_REPLAYS",
                value=row["blocked_replays"],
                unit="count",
                status="PASS" if row["blocked_replays"] == 0 else "FAIL",
            ),
            MetricSample(
                code="RETENTION_FAILURES",
                value=row["retention_failures"],
                unit="count",
                status="PASS" if row["retention_failures"] == 0 else "FAIL",
            ),
            MetricSample(
                code="AI_FAILURES_24H",
                value=row["ai_failures"],
                unit="count",
                status="PASS" if row["ai_failures"] == 0 else "FAIL",
            ),
            MetricSample(
                code="AI_COST_MICROUSD_24H",
                value=int(row["ai_cost"]),
                unit="microusd",
                status="UNKNOWN",
            ),
            MetricSample(
                code="AI_LATENCY_P95_MS_24H",
                value=float(row["ai_p95_ms"]),
                unit="ms",
                status="UNKNOWN",
            ),
            MetricSample(
                code="AI_COST_PER_DOCUMENT_MICROUSD_24H",
                value=int(row["ai_doc_cost"]),
                unit="microusd",
                status="UNKNOWN",
            ),
        ]
        return OperationsOverview(observed_at=self._now(), metrics=metrics)

    async def request_replay(
        self,
        payload: ReplayRequest,
        *,
        actor_id: UUID,
        idempotency_key: str,
    ) -> ReplayResult:
        now = self._now()
        async with self._engine.begin() as connection:
            existing = (
                (
                    await connection.execute(
                        text(
                            """SELECT r.id, r.failed_task_id, f.task_kind, r.priority, r.status
                           FROM replay_request r JOIN failed_task f ON f.id = r.failed_task_id
                          WHERE r.idempotency_key = :key"""
                        ),
                        {"key": idempotency_key},
                    )
                )
                .mappings()
                .one_or_none()
            )
            if existing is not None:
                return ReplayResult.model_validate(existing)
            failed = (
                (
                    await connection.execute(
                        text(
                            """SELECT id, task_kind FROM failed_task
                            WHERE id = :failed_task_id
                              AND replayable IS TRUE
                              AND resolved_at IS NULL
                              AND (reconstruction_status='REPLAYABLE'
                                   OR task_kind IN ('PUBLICATION_OUTBOX','PROJECTION'))
                            """
                        ),
                        {"failed_task_id": payload.failed_task_id},
                    )
                )
                .mappings()
                .one_or_none()
            )
            if failed is None:
                raise OperationsRejected("only an unresolved failed task may be replayed")
            replay_id = uuid7()
            await connection.execute(
                text(
                    """INSERT INTO replay_request
                       (id, failed_task_id, actor_id, reason, priority,
                        idempotency_key, status, requested_at)
                       VALUES (:id, :failed, :actor, :reason, :priority, :key, 'QUEUED', :now)"""
                ),
                {
                    "id": replay_id,
                    "failed": failed["id"],
                    "actor": actor_id,
                    "reason": payload.reason,
                    "priority": payload.priority,
                    "key": idempotency_key,
                    "now": now,
                },
            )
        return ReplayResult(
            id=replay_id,
            failed_task_id=payload.failed_task_id,
            task_kind=str(failed["task_kind"]),
            priority=payload.priority,
            status="QUEUED",
        )

    async def get_schedule(self, source_id: UUID) -> FetchScheduleView:
        async with self._engine.connect() as connection:
            row = (
                (
                    await connection.execute(
                        text("SELECT * FROM fetch_schedule WHERE source_id=:source_id"),
                        {"source_id": source_id},
                    )
                )
                .mappings()
                .one_or_none()
            )
        if row is None:
            raise OperationsRejected("source schedule does not exist")
        return _schedule_view(row)

    async def update_schedule(
        self,
        source_id: UUID,
        payload: FetchScheduleUpdate,
        *,
        actor_id: UUID,
        idempotency_key: str,
    ) -> FetchScheduleView:
        now = self._now()
        async with self._engine.begin() as connection:
            source = (
                (
                    await connection.execute(
                        text(
                            """SELECT s.authority_level, s.lifecycle_state,
                                  s.poll_interval_minutes,
                                  p.status AS policy_status, p.valid_from, p.valid_until,
                                  COALESCE(
                                    (p.document #>> '{fetch,rate_limit_per_minute}')::int,
                                    1
                                  ) AS policy_rate
                           FROM source s JOIN source_policy_version p
                             ON p.id=s.current_policy_version_id
                           WHERE s.id=:source_id FOR UPDATE"""
                        ),
                        {"source_id": source_id},
                    )
                )
                .mappings()
                .one_or_none()
            )
            if source is None:
                raise OperationsRejected("source or current policy does not exist")
            if (
                source["lifecycle_state"] != "ACTIVE"
                or source["policy_status"] != "APPROVED"
                or source["valid_from"] > now
                or source["valid_until"] <= now
            ):
                raise OperationsRejected(
                    "only an ACTIVE source with a valid policy may be scheduled"
                )
            if payload.interval_seconds < int(source["poll_interval_minutes"]) * 60:
                raise OperationsRejected(
                    "schedule is more frequent than the approved source interval"
                )
            if payload.rate_limit_per_minute > int(source["policy_rate"]):
                raise OperationsRejected("schedule rate exceeds the approved source policy")
            existing = (
                (
                    await connection.execute(
                        text("SELECT * FROM fetch_schedule WHERE source_id=:source_id FOR UPDATE"),
                        {"source_id": source_id},
                    )
                )
                .mappings()
                .one_or_none()
            )
            if existing is None and payload.expected_version != 0:
                raise OperationsRejected("schedule version conflict")
            if existing is not None and existing["last_idempotency_key"] == idempotency_key:
                return _schedule_view(existing)
            if existing is not None and existing["version"] != payload.expected_version:
                raise OperationsRejected("schedule version conflict")
            schedule_id = uuid7() if existing is None else existing["id"]
            next_run_at = now if existing is None else existing["next_run_at"]
            await connection.execute(
                text(
                    """INSERT INTO fetch_schedule
                       (id,source_id,authority_level,status,interval_seconds,next_run_at,
                        backoff_base_seconds,backoff_cap_seconds,max_attempts,consecutive_failures,
                        circuit_state,freshness_slo_seconds,rate_limit_per_minute,
                        daily_request_budget,daily_byte_budget,requests_used,bytes_used,
                        budget_window_started_at,version,last_idempotency_key,updated_at)
                       VALUES (:id,:source,:authority,:status,:interval,:next_run,30,21600,3,0,
                               'CLOSED',:slo,:rate,:request_budget,:byte_budget,0,0,:now,1,:key,:now)
                       ON CONFLICT (source_id) DO UPDATE SET
                         status=EXCLUDED.status, interval_seconds=EXCLUDED.interval_seconds,
                         freshness_slo_seconds=EXCLUDED.freshness_slo_seconds,
                         rate_limit_per_minute=EXCLUDED.rate_limit_per_minute,
                         daily_request_budget=EXCLUDED.daily_request_budget,
                         daily_byte_budget=EXCLUDED.daily_byte_budget,
                         last_idempotency_key=EXCLUDED.last_idempotency_key,
                         version=fetch_schedule.version+1, updated_at=EXCLUDED.updated_at"""
                ),
                {
                    "id": schedule_id,
                    "source": source_id,
                    "authority": source["authority_level"],
                    "status": payload.status.value,
                    "interval": payload.interval_seconds,
                    "next_run": next_run_at,
                    "slo": payload.freshness_slo_seconds,
                    "rate": payload.rate_limit_per_minute,
                    "request_budget": payload.daily_request_budget,
                    "byte_budget": payload.daily_byte_budget,
                    "key": idempotency_key,
                    "now": now,
                },
            )
            await connection.execute(
                text(
                    "SELECT append_audit_event("
                    ":id,'FETCH_SCHEDULE_UPDATED',:actor,'fetch_schedule',:target,NULL,"
                    "jsonb_build_object('source_id',:source,'status',:status,"
                    "'idempotency_key',:key),"
                    ":reason,:key,:now)"
                ),
                {
                    "id": uuid7(),
                    "actor": actor_id,
                    "target": schedule_id,
                    "source": str(source_id),
                    "status": payload.status.value,
                    "key": idempotency_key,
                    "reason": payload.reason,
                    "now": now,
                },
            )
            row = (
                (
                    await connection.execute(
                        text("SELECT * FROM fetch_schedule WHERE id=:id"), {"id": schedule_id}
                    )
                )
                .mappings()
                .one()
            )
        return _schedule_view(row)

    async def source_health(self) -> list[SourceHealthView]:
        async with self._engine.connect() as connection:
            snapshots = (
                (
                    await connection.execute(
                        text(
                            """SELECT DISTINCT ON (source_id) * FROM source_health_snapshot
                           ORDER BY source_id, observed_at DESC"""
                        )
                    )
                )
                .mappings()
                .all()
            )
            anomalies = (
                (
                    await connection.execute(
                        text(
                            "SELECT id,source_id,code,severity,status,detected_at "
                            "FROM source_anomaly WHERE status <> 'RESOLVED' "
                            "ORDER BY detected_at DESC"
                        )
                    )
                )
                .mappings()
                .all()
            )
        by_source: dict[UUID, list[SourceAnomalyView]] = {}
        for anomaly in anomalies:
            by_source.setdefault(anomaly["source_id"], []).append(
                SourceAnomalyView.model_validate(anomaly)
            )
        return [
            SourceHealthView(
                source_id=row["source_id"],
                fetch_run_id=row["fetch_run_id"],
                transport_status=row["transport_status"],
                discovery_status=row["discovery_status"],
                parse_status=row["parse_status"],
                quality_status=row["quality_status"],
                freshness_status=row["freshness_status"],
                rule_version=row["rule_version"],
                observed_at=row["observed_at"],
                anomalies=by_source.get(row["source_id"], []),
            )
            for row in snapshots
        ]

    async def list_replays(self) -> list[ReplayTaskView]:
        async with self._engine.connect() as connection:
            rows = (
                (
                    await connection.execute(
                        text(
                            """SELECT f.id,f.task_kind,f.error_code,f.priority,
                                  f.reconstruction_status,f.blocked_reason,f.source_id,f.run_id,
                                  f.document_version_id,f.event_id,f.failed_at,
                                  r.status AS replay_status
                           FROM failed_task f LEFT JOIN LATERAL (
                             SELECT status FROM replay_request rr WHERE rr.failed_task_id=f.id
                             ORDER BY requested_at DESC LIMIT 1
                           ) r ON TRUE WHERE f.resolved_at IS NULL
                           ORDER BY f.priority DESC,f.failed_at"""
                        )
                    )
                )
                .mappings()
                .all()
            )
        return [ReplayTaskView.model_validate(row) for row in rows]

    async def record_feedback(
        self,
        *,
        item_id: UUID | None,
        event_id: UUID | None = None,
        value: str,
        actor_id: UUID,
    ) -> None:
        now = self._now()
        if event_id is not None:
            if self._projection_engine is None:
                raise OperationsRejected("published Event projection is unavailable")
            async with self._projection_engine.connect() as projection_connection:
                visible = await projection_connection.scalar(
                    text(
                        "SELECT 1 FROM published_v1.current_event_summary WHERE event_id=:event_id"
                    ),
                    {"event_id": event_id},
                )
            if visible is None:
                raise OperationsRejected("feedback target is not visible")
        async with self._engine.begin() as connection:
            if event_id is not None:
                switch = await connection.scalar(
                    text("SELECT status FROM event_consumer_switch WHERE singleton")
                )
                if switch != "EVENT":
                    raise OperationsRejected("event consumer writes are read-only")
            elif item_id is None:
                raise OperationsRejected("feedback target is not visible")
            else:
                visible = (
                    await connection.execute(
                        text(
                            """SELECT 1 FROM publication
                                WHERE item_id = :item_id AND status = 'PUBLISHED'"""
                        ),
                        {"item_id": item_id},
                    )
                ).scalar_one_or_none()
                if visible is None:
                    raise OperationsRejected("feedback target is not visible")
            await connection.execute(
                text(
                    """INSERT INTO item_feedback
                         (id, actor_id, item_id, event_id, value, recorded_at)
                       VALUES (:id, :actor, :item, :event, :value, :now)
                       ON CONFLICT (actor_id, event_id) DO UPDATE
                       SET value = EXCLUDED.value, recorded_at = EXCLUDED.recorded_at"""
                ),
                {
                    "id": uuid7(),
                    "actor": actor_id,
                    "item": None if event_id is not None else item_id,
                    "event": event_id,
                    "value": value,
                    "now": now,
                },
            )

    async def record_usage(
        self,
        *,
        event_type: str,
    ) -> None:
        allowed = {"SEARCH", "VIEW_EVIDENCE", "SAVE_ITEM", "EXPORT", "READ_DAILY"}
        if event_type not in allowed:
            raise OperationsRejected("usage event type is not permitted")
        bucket_started_at = self._now().replace(minute=0, second=0, microsecond=0)
        async with self._engine.begin() as connection:
            await connection.execute(
                text(
                    """INSERT INTO usage_metric_bucket
                       (id, event_type, bucket_started_at, event_count)
                       VALUES (:id, :event_type, :bucket_started_at, 1)
                       ON CONFLICT (event_type, bucket_started_at) DO UPDATE
                       SET event_count = usage_metric_bucket.event_count + 1"""
                ),
                {
                    "id": uuid7(),
                    "event_type": event_type,
                    "bucket_started_at": bucket_started_at,
                },
            )

    async def pilot_metrics(self) -> PilotMetrics:
        now = self._now()
        async with self._engine.connect() as connection:
            row = (
                (
                    await connection.execute(
                        text(
                            """SELECT
                          COALESCE(min(bucket_started_at), :now) AS started_at,
                          COALESCE(max(bucket_started_at), :now) AS ended_at,
                          COALESCE(sum(event_count), 0) AS aggregate_actions
                          FROM usage_metric_bucket"""
                        ),
                        {"now": now},
                    )
                )
                .mappings()
                .one()
            )
            votes = (
                (
                    await connection.execute(
                        text(
                            """SELECT count(*) FILTER (WHERE value='USEFUL') AS useful,
                                  count(*) AS total,
                                  count(DISTINCT actor_id) AS feedback_users
                                  FROM item_feedback"""
                        ),
                    )
                )
                .mappings()
                .one()
            )
        return PilotMetrics(
            started_at=row["started_at"],
            ended_at=row["ended_at"],
            aggregate_effective_actions=row["aggregate_actions"],
            distinct_feedback_users=votes["feedback_users"],
            useful_votes=votes["useful"],
            total_votes=votes["total"],
            identity_metrics_available=False,
            sufficient_window=False,
        )
