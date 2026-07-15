"""PostgreSQL-backed operational control plane."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine
from srbg_contracts import (
    MetricSample,
    OperationsOverview,
    PilotMetrics,
    ReplayRequest,
    ReplayResult,
)

from srbg_api.identifiers import uuid7


class OperationsRejected(RuntimeError):
    pass


class PostgresOperationsService:
    def __init__(
        self,
        engine: AsyncEngine,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._engine = engine
        self._now = now or (lambda: datetime.now(UTC))

    async def close(self) -> None:
        await self._engine.dispose()

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

    async def record_feedback(self, *, item_id: UUID, value: str, actor_id: UUID) -> None:
        now = self._now()
        async with self._engine.begin() as connection:
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
                    """INSERT INTO item_feedback (id, actor_id, item_id, value, recorded_at)
                       VALUES (:id, :actor, :item, :value, :now)
                       ON CONFLICT (actor_id, item_id) DO UPDATE
                       SET value = EXCLUDED.value, recorded_at = EXCLUDED.recorded_at"""
                ),
                {"id": uuid7(), "actor": actor_id, "item": item_id, "value": value, "now": now},
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
