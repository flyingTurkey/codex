"""Transactional schedule claiming and idempotent run leasing."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from srbg_api.identifiers import uuid7
from srbg_api.observability import (
    FETCH_BACKLOG_AGE,
    FETCH_FAILURES,
    SCHEDULE_DISPATCH_DELAY,
    SOURCE_CIRCUIT_STATE,
    SOURCE_FRESHNESS,
    SOURCE_PARSE_QUALITY_BPS,
    SOURCE_SLO_VIOLATIONS,
)
from srbg_api.scheduling.domain import (
    AdaptiveScheduleInput,
    FetchFailure,
    HealthObservation,
    SchedulePolicy,
    calculate_adaptive_interval,
    classify_failure,
    evaluate_health,
    next_backoff,
)


@dataclass(frozen=True, slots=True)
class ClaimedFetchRun:
    source_id: UUID
    run_id: UUID


async def _round17_accounting_available(connection: AsyncConnection) -> bool:
    return bool(
        await connection.scalar(
            text(
                """SELECT count(*)=4
                     FROM information_schema.columns
                    WHERE table_schema='public'
                      AND (
                        (table_name='fetch_run' AND column_name IN
                          ('pilot_window_source_id','request_count','response_bytes'))
                        OR (table_name='source_health_snapshot'
                            AND column_name='discovery_body_bytes')
                      )"""
            )
        )
    )


class PostgresSchedulingService:
    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def close(self) -> None:
        await self._engine.dispose()

    async def claim_due(self, *, now: datetime | None = None) -> ClaimedFetchRun | None:
        observed_at = now or datetime.now(UTC)
        token = uuid7()
        async with self._engine.begin() as connection:
            await connection.execute(
                text(
                    """UPDATE fetch_schedule
                          SET requests_used=0,bytes_used=0,
                              budget_window_started_at=:now,updated_at=:now
                        WHERE budget_window_started_at <=
                              CAST(:now AS timestamptz) - interval '1 day'"""
                ),
                {"now": observed_at},
            )
            row = (
                (
                    await connection.execute(
                        text("SELECT * FROM claim_due_fetch_schedule(:now, :until, :token)"),
                        {
                            "now": observed_at,
                            "until": observed_at + timedelta(minutes=2),
                            "token": token,
                        },
                    )
                )
                .mappings()
                .one_or_none()
            )
            if row is None:
                return None
            existing = (
                (
                    await connection.execute(
                        text(
                            """SELECT id, source_id FROM fetch_run
                               WHERE schedule_id=:schedule_id
                                 AND status IN (
                                   'PENDING_DISPATCH','DISPATCHED','RUNNING','RETRY_WAIT'
                                 )
                               ORDER BY started_at DESC LIMIT 1 FOR UPDATE"""
                        ),
                        {"schedule_id": row["schedule_id"]},
                    )
                )
                .mappings()
                .one_or_none()
            )
            if existing is not None:
                return ClaimedFetchRun(source_id=existing["source_id"], run_id=existing["id"])
            refs = (
                (
                    await connection.execute(
                        text(
                            """SELECT fs.authority_mode,fs.source_stream_id,
                                      fs.stream_config_version_id,
                                      s.current_policy_version_id AS policy_id,
                                      s.current_connector_config_version_id AS config_id,
                                      (SELECT id FROM source_connector sc
                                        WHERE sc.source_id=s.id
                                        ORDER BY created_at DESC LIMIT 1) AS connector_id
                                 FROM source s
                                 JOIN fetch_schedule fs ON fs.id=:schedule_id
                                WHERE s.id=:source_id"""
                        ),
                        {"source_id": row["source_id"], "schedule_id": row["schedule_id"]},
                    )
                )
                .mappings()
                .one()
            )
            run_id = uuid7()
            await connection.execute(
                text(
                    """INSERT INTO fetch_run
                       (id, source_connector_id, trigger, status, started_at,
                        discovered_count, fetched_count, failed_count, request_id,
                        execution_domain, source_id, schedule_id, policy_version_id,
                        connector_config_version_id, idempotency_key, attempt_count,
                        source_stream_id,stream_config_version_id)
                       VALUES (:id, :connector, 'SCHEDULED', 'PENDING_DISPATCH', :now,
                               0, 0, 0, :request_id, 'PRODUCTION', :source, :schedule,
                               :policy, :config, :idempotency, 0,:stream,:stream_config)"""
                ),
                {
                    "id": run_id,
                    "connector": refs["connector_id"],
                    "now": observed_at,
                    "request_id": f"schedule:{run_id}",
                    "source": row["source_id"],
                    "schedule": row["schedule_id"],
                    "policy": refs["policy_id"],
                    "config": refs["config_id"],
                    "idempotency": f"source-fetch:{row['schedule_id']}:{run_id}",
                    "stream": refs["source_stream_id"],
                    "stream_config": refs["stream_config_version_id"],
                },
            )
            return ClaimedFetchRun(source_id=row["source_id"], run_id=run_id)

    async def mark_dispatched(self, run_id: UUID, *, now: datetime | None = None) -> None:
        observed_at = now or datetime.now(UTC)
        due_at: datetime | None = None
        async with self._engine.begin() as connection:
            due_at = await connection.scalar(
                text(
                    """SELECT fs.next_run_at FROM fetch_run r
                       JOIN fetch_schedule fs ON fs.id=r.schedule_id
                       WHERE r.id=:id"""
                ),
                {"id": run_id},
            )
            updated = await connection.execute(
                text(
                    """UPDATE fetch_run SET status='DISPATCHED', heartbeat_at=:now
                       WHERE id=:id AND status='PENDING_DISPATCH'"""
                ),
                {"id": run_id, "now": observed_at},
            )
        outcome = "DISPATCHED" if updated.rowcount else "ALREADY_DISPATCHED"
        delay = 0.0 if due_at is None else max(0.0, (observed_at - due_at).total_seconds())
        SCHEDULE_DISPATCH_DELAY.labels(outcome=outcome).observe(delay)

    async def acquire_execution(
        self, *, source_id: UUID, run_id: UUID, now: datetime | None = None
    ) -> bool:
        observed_at = now or datetime.now(UTC)
        token = uuid7()
        async with self._engine.begin() as connection:
            updated = await connection.execute(
                text(
                    """UPDATE fetch_run r SET status='RUNNING', execution_lease_token=:token,
                           execution_lease_until=:until, heartbeat_at=:now,
                           attempt_count=attempt_count+1
                       FROM source s, fetch_schedule fs
                       WHERE r.id=:run_id AND r.source_id=:source_id
                         AND s.id=r.source_id
                         AND fs.id=r.schedule_id AND fs.status='ACTIVE'
                         AND fs.requests_used < fs.daily_request_budget
                         AND fs.bytes_used < fs.daily_byte_budget
                         AND fs.circuit_state IN ('CLOSED','HALF_OPEN')
                         AND (
                           (fs.authority_mode='PERSONAL_STREAM'
                            AND s.desired_enabled=true AND s.manual_disabled_at IS NULL
                            AND fs.access_state='ACCESSIBLE'
                            AND r.source_stream_id=fs.source_stream_id
                            AND r.stream_config_version_id=fs.stream_config_version_id
                            AND EXISTS (
                              SELECT 1 FROM source_stream stream
                              JOIN stream_config_version config
                                ON config.id=r.stream_config_version_id
                               AND config.stream_id=stream.id
                               AND config.config_sha256=stream.config_sha256
                               WHERE stream.id=r.source_stream_id
                                 AND stream.source_id=s.id AND stream.status='READY'
                            ))
                           OR
                           (fs.authority_mode='LEGACY_GOVERNED'
                            AND s.lifecycle_state='ACTIVE'
                            AND EXISTS (
                              SELECT 1 FROM source_policy_version p
                              JOIN connector_config_version c
                                ON c.id=s.current_connector_config_version_id
                               AND c.id=r.connector_config_version_id
                               AND c.validation_status='VALID'
                               WHERE p.id=s.current_policy_version_id
                                 AND p.id=r.policy_version_id
                                 AND source_policy_compliance_current(s.id,p.id,:now)
                                 AND EXISTS (
                                   SELECT 1 FROM source_governance_decision d
                                    WHERE d.source_id=s.id
                                      AND d.decision_type='PRODUCTION_APPROVAL'
                                      AND d.outcome='APPROVED'
                                      AND (d.valid_until IS NULL OR d.valid_until>:now)
                                 )
                            ))
                         )
                         AND r.status IN ('PENDING_DISPATCH','DISPATCHED','RUNNING','RETRY_WAIT')
                         AND (r.execution_lease_until IS NULL OR r.execution_lease_until <= :now)
                    """
                ),
                {
                    "run_id": run_id,
                    "source_id": source_id,
                    "token": token,
                    "now": observed_at,
                    "until": observed_at + timedelta(minutes=10),
                },
            )
            return bool(updated.rowcount)

    async def reserve_request(
        self,
        *,
        source_id: UUID,
        run_id: UUID,
        now: datetime | None = None,
    ) -> bool:
        """Atomically reserve one physical HTTP request before transport I/O."""

        observed_at = now or datetime.now(UTC)
        async with self._engine.begin() as connection:
            if not await _round17_accounting_available(connection):
                updated = await connection.execute(
                    text(
                        """UPDATE fetch_schedule fs
                              SET requests_used=CASE
                                    WHEN fs.budget_window_started_at <=
                                         CAST(:now AS timestamptz) - interval '1 day'
                                    THEN 1 ELSE fs.requests_used+1
                                  END,
                                  bytes_used=CASE
                                    WHEN fs.budget_window_started_at <=
                                         CAST(:now AS timestamptz) - interval '1 day'
                                    THEN 0 ELSE fs.bytes_used
                                  END,
                                  budget_window_started_at=CASE
                                    WHEN fs.budget_window_started_at <=
                                         CAST(:now AS timestamptz) - interval '1 day'
                                    THEN :now ELSE fs.budget_window_started_at
                                  END,
                                  updated_at=:now
                             FROM fetch_run r
                            WHERE r.id=:run_id AND r.source_id=:source_id
                              AND r.schedule_id=fs.id AND r.status='RUNNING'
                              AND r.execution_lease_until>=:now
                              AND fs.status='ACTIVE'
                              AND fs.circuit_state IN ('CLOSED','HALF_OPEN')
                              AND (
                                fs.budget_window_started_at <=
                                  CAST(:now AS timestamptz) - interval '1 day'
                                OR (
                                  fs.requests_used < fs.daily_request_budget
                                  AND fs.bytes_used < fs.daily_byte_budget
                                )
                              )
                         RETURNING fs.id"""
                    ),
                    {"source_id": source_id, "run_id": run_id, "now": observed_at},
                )
                return bool(updated.rowcount)
            personal = await connection.scalar(
                text(
                    "SELECT fs.authority_mode='PERSONAL_STREAM' FROM fetch_run r "
                    "JOIN fetch_schedule fs ON fs.id=r.schedule_id "
                    "WHERE r.id=:run_id AND r.source_id=:source_id"
                ),
                {"run_id": run_id, "source_id": source_id},
            )
            if personal:
                updated = await connection.execute(
                    text(
                        """WITH reserved AS (
                             UPDATE fetch_schedule fs
                                SET requests_used=CASE
                                      WHEN fs.budget_window_started_at <=
                                           CAST(:now AS timestamptz)-interval '1 day'
                                      THEN 1 ELSE fs.requests_used+1 END,
                                    bytes_used=CASE
                                      WHEN fs.budget_window_started_at <=
                                           CAST(:now AS timestamptz)-interval '1 day'
                                      THEN 0 ELSE fs.bytes_used END,
                                    budget_window_started_at=CASE
                                      WHEN fs.budget_window_started_at <=
                                           CAST(:now AS timestamptz)-interval '1 day'
                                      THEN :now ELSE fs.budget_window_started_at END,
                                    updated_at=:now
                               FROM fetch_run r,source s,source_stream stream,
                                    stream_config_version config
                              WHERE r.id=:run_id AND r.source_id=:source_id
                                AND r.schedule_id=fs.id AND r.status='RUNNING'
                                AND r.execution_lease_until>=:now
                                AND s.id=r.source_id AND s.desired_enabled=true
                                AND s.manual_disabled_at IS NULL
                                AND fs.authority_mode='PERSONAL_STREAM'
                                AND fs.status='ACTIVE' AND fs.access_state='ACCESSIBLE'
                                AND fs.circuit_state IN ('CLOSED','HALF_OPEN')
                                AND stream.id=fs.source_stream_id
                                AND stream.id=r.source_stream_id
                                AND stream.source_id=s.id AND stream.status='READY'
                                AND config.id=fs.stream_config_version_id
                                AND config.id=r.stream_config_version_id
                                AND config.stream_id=stream.id
                                AND config.config_sha256=stream.config_sha256
                                AND (fs.budget_window_started_at <=
                                     CAST(:now AS timestamptz)-interval '1 day'
                                     OR (fs.requests_used<fs.daily_request_budget
                                         AND fs.bytes_used<fs.daily_byte_budget))
                              RETURNING fs.id
                           )
                           UPDATE fetch_run r SET request_count=r.request_count+1
                             FROM reserved
                            WHERE r.id=:run_id AND r.source_id=:source_id
                              AND r.schedule_id=reserved.id
                           RETURNING r.id"""
                    ),
                    {"source_id": source_id, "run_id": run_id, "now": observed_at},
                )
                return bool(updated.rowcount)
            updated = await connection.execute(
                text(
                    """WITH reserved AS (
                         UPDATE fetch_schedule fs
                          SET requests_used=CASE
                                WHEN fs.budget_window_started_at <=
                                     CAST(:now AS timestamptz) - interval '1 day'
                                THEN 1 ELSE fs.requests_used+1
                              END,
                              bytes_used=CASE
                                WHEN fs.budget_window_started_at <=
                                     CAST(:now AS timestamptz) - interval '1 day'
                                THEN 0 ELSE fs.bytes_used
                              END,
                              budget_window_started_at=CASE
                                WHEN fs.budget_window_started_at <=
                                     CAST(:now AS timestamptz) - interval '1 day'
                                THEN :now ELSE fs.budget_window_started_at
                              END,
                              updated_at=:now
                         FROM fetch_run r,source s,source_policy_version p,
                              connector_config_version c
                        WHERE r.id=:run_id AND r.source_id=:source_id
                          AND r.schedule_id=fs.id AND r.status='RUNNING'
                          AND r.execution_lease_until>=:now
                          AND s.id=r.source_id AND s.lifecycle_state='ACTIVE'
                          AND p.id=s.current_policy_version_id
                          AND p.id=r.policy_version_id
                          AND source_policy_compliance_current(s.id,p.id,:now)
                          AND source_private_evidence_capture_allowed(p.document)
                          AND c.id=s.current_connector_config_version_id
                          AND c.id=r.connector_config_version_id
                          AND c.validation_status='VALID'
                          AND fs.status='ACTIVE'
                          AND fs.interval_seconds=s.poll_interval_minutes*60
                          AND fs.freshness_slo_seconds=
                              (p.document #>> '{slo,target_minutes}')::int*60
                          AND fs.circuit_state IN ('CLOSED','HALF_OPEN')
                          AND EXISTS (
                            SELECT 1 FROM source_governance_decision decision
                             WHERE decision.source_id=s.id
                               AND decision.policy_version_id=p.id
                               AND decision.connector_config_version_id=c.id
                               AND decision.trial_run_id=s.current_trial_run_id
                               AND decision.decision_type='PRODUCTION_APPROVAL'
                               AND decision.outcome='APPROVED'
                               AND (decision.valid_until IS NULL
                                    OR decision.valid_until>:now)
                          )
                          AND (
                            (
                              r.pilot_window_source_id IS NULL
                              AND NOT EXISTS (
                                SELECT 1
                                  FROM round17_pilot_window_source cohort
                                  JOIN round17_pilot_window cohort_window
                                    ON cohort_window.id=cohort.window_id
                                 WHERE cohort.source_id=r.source_id
                                   AND cohort_window.state='RUNNING'
                              )
                            ) OR EXISTS (
                              SELECT 1
                                FROM round17_pilot_window_source segment
                                JOIN round17_pilot_window window_row
                                  ON window_row.id=segment.window_id
                               WHERE segment.id=r.pilot_window_source_id
                                 AND segment.source_id=r.source_id
                                 AND segment.schedule_id=r.schedule_id
                                 AND segment.policy_version_id=r.policy_version_id
                                 AND segment.connector_config_version_id=
                                     r.connector_config_version_id
                                 AND segment.status='RUNNING'
                                 AND window_row.state='RUNNING'
                                 AND :now>=segment.segment_started_at
                                 AND :now<segment.segment_ends_at
                                 AND :now>=window_row.started_at
                                 AND :now<window_row.ends_at
                                 AND fs.version=segment.schedule_version
                                 AND fs.interval_seconds=segment.interval_seconds
                                 AND fs.freshness_slo_seconds=
                                     segment.freshness_slo_seconds
                            )
                          )
                          AND (
                            fs.budget_window_started_at <=
                              CAST(:now AS timestamptz) - interval '1 day'
                            OR (
                              fs.requests_used < fs.daily_request_budget
                              AND fs.bytes_used < fs.daily_byte_budget
                            )
                          )
                        RETURNING fs.id
                    )
                    UPDATE fetch_run r
                       SET request_count=r.request_count+1
                      FROM reserved
                     WHERE r.id=:run_id AND r.source_id=:source_id
                       AND r.schedule_id=reserved.id
                    RETURNING r.id"""
                ),
                {"source_id": source_id, "run_id": run_id, "now": observed_at},
            )
        return bool(updated.rowcount)

    async def record_response_bytes(
        self,
        *,
        source_id: UUID,
        run_id: UUID,
        response_bytes: int,
    ) -> bool:
        """Persist each physical response immediately, before parsing or raw storage."""

        if response_bytes < 0:
            raise ValueError("response bytes cannot be negative")
        async with self._engine.begin() as connection:
            if not await _round17_accounting_available(connection):
                updated = await connection.execute(
                    text(
                        """UPDATE fetch_schedule fs
                              SET bytes_used=fs.bytes_used+:response_bytes,
                                  updated_at=:now
                             FROM fetch_run r
                            WHERE r.id=:run_id AND r.source_id=:source_id
                              AND r.schedule_id=fs.id
                              AND r.status IN ('RUNNING','CANCELLED')
                         RETURNING fs.id"""
                    ),
                    {
                        "source_id": source_id,
                        "run_id": run_id,
                        "response_bytes": response_bytes,
                        "now": datetime.now(UTC),
                    },
                )
                return bool(updated.rowcount)
            updated = await connection.execute(
                text(
                    """WITH counted AS (
                         UPDATE fetch_run r
                            SET response_bytes=r.response_bytes+:response_bytes
                          WHERE r.id=:run_id AND r.source_id=:source_id
                            AND r.request_count>0
                            AND r.status IN ('RUNNING','CANCELLED')
                         RETURNING r.schedule_id
                       )
                       UPDATE fetch_schedule fs
                          SET bytes_used=fs.bytes_used+:response_bytes,
                              updated_at=:now
                         FROM counted
                        WHERE fs.id=counted.schedule_id
                       RETURNING fs.id"""
                ),
                {
                    "source_id": source_id,
                    "run_id": run_id,
                    "response_bytes": response_bytes,
                    "now": datetime.now(UTC),
                },
            )
        return bool(updated.rowcount)

    async def pending_messages(self) -> list[ClaimedFetchRun]:
        async with self._engine.connect() as connection:
            rows = (
                await connection.execute(
                    text(
                        """SELECT id AS run_id, source_id FROM fetch_run
                           WHERE status IN ('PENDING_DISPATCH','DISPATCHED')
                           ORDER BY started_at, id LIMIT 500"""
                    )
                )
            ).mappings()
            return [ClaimedFetchRun(**row) for row in rows]

    async def cancel_ineligible(
        self, *, source_id: UUID, run_id: UUID, now: datetime | None = None
    ) -> bool:
        """Cancel only an unleased run whose current authority can no longer be proven."""

        observed_at = now or datetime.now(UTC)
        async with self._engine.begin() as connection:
            updated = await connection.execute(
                text(
                    """UPDATE fetch_run r SET status='CANCELLED',
                           completed_at=:now,failure_class='AUTHORIZATION_REVOKED',
                           execution_lease_token=NULL,execution_lease_until=NULL
                       WHERE r.id=:run_id AND r.source_id=:source_id
                         AND r.status IN ('PENDING_DISPATCH','DISPATCHED','RETRY_WAIT','RUNNING')
                         AND (r.execution_lease_until IS NULL OR r.execution_lease_until <= :now)
                         AND NOT EXISTS (
                           SELECT 1 FROM source s
                           JOIN fetch_schedule fs ON fs.id=r.schedule_id
                           LEFT JOIN source_stream stream ON stream.id=fs.source_stream_id
                           LEFT JOIN stream_config_version stream_config
                             ON stream_config.id=fs.stream_config_version_id
                           LEFT JOIN source_policy_version p
                             ON p.id=s.current_policy_version_id
                           LEFT JOIN connector_config_version c
                             ON c.id=s.current_connector_config_version_id
                           WHERE s.id=r.source_id AND fs.status='ACTIVE'
                             AND fs.requests_used < fs.daily_request_budget
                             AND fs.bytes_used < fs.daily_byte_budget
                             AND fs.circuit_state IN ('CLOSED','HALF_OPEN')
                             AND (
                               (
                                 fs.authority_mode='PERSONAL_STREAM'
                                 AND s.desired_enabled=true
                                 AND s.manual_disabled_at IS NULL
                                 AND stream.id=r.source_stream_id
                                 AND stream.source_id=s.id AND stream.status='READY'
                                 AND stream_config.id=r.stream_config_version_id
                                 AND stream_config.stream_id=stream.id
                                 AND stream.config_sha256=stream_config.config_sha256
                                 AND fs.access_state='ACCESSIBLE'
                               ) OR (
                                 fs.authority_mode='LEGACY_GOVERNED'
                                 AND s.lifecycle_state='ACTIVE'
                                 AND p.id=r.policy_version_id
                                 AND source_policy_compliance_current(s.id,p.id,:now)
                                 AND c.id=r.connector_config_version_id
                                 AND c.validation_status='VALID'
                                 AND EXISTS (
                                   SELECT 1 FROM source_governance_decision d
                                    WHERE d.source_id=s.id
                                      AND d.decision_type='PRODUCTION_APPROVAL'
                                      AND d.outcome='APPROVED'
                                      AND (d.valid_until IS NULL OR d.valid_until > :now)
                                 )
                               )
                             )
                         )"""
                ),
                {"run_id": run_id, "source_id": source_id, "now": observed_at},
            )
            return bool(updated.rowcount)

    async def record_outcome(
        self,
        *,
        source_id: UUID,
        run_id: UUID,
        observation: HealthObservation,
        discovered_count: int,
        parsed_count: int,
        request_count: int = 0,
        response_bytes: int = 0,
        failure: FetchFailure | None = None,
        now: datetime | None = None,
        random_fraction: Callable[[], float] = lambda: 0.5,
    ) -> str:
        if request_count < 0:
            raise ValueError("request count cannot be negative")
        if response_bytes < 0:
            raise ValueError("response bytes cannot be negative")
        observed_at = now or datetime.now(UTC)
        health = evaluate_health(observation, observed_at=observed_at)
        async with self._engine.begin() as connection:
            round17_accounting = await _round17_accounting_available(connection)
            run_query = (
                text(
                    """SELECT r.attempt_count,r.schedule_id,r.request_count,
                              r.response_bytes,fs.interval_seconds,
                              fs.backoff_base_seconds,fs.backoff_cap_seconds,
                              fs.max_attempts,fs.consecutive_failures,
                              fs.circuit_state,fs.authority_mode,fs.source_stream_id,
                              fs.zero_update_streak,fs.consecutive_zero_discovery
                       FROM fetch_run r JOIN fetch_schedule fs ON fs.id=r.schedule_id
                       WHERE r.id=:run_id AND r.source_id=:source_id FOR UPDATE OF r,fs"""
                )
                if round17_accounting
                else text(
                    """SELECT r.attempt_count,r.schedule_id,fs.interval_seconds,
                              fs.backoff_base_seconds,fs.backoff_cap_seconds,
                              fs.max_attempts,fs.consecutive_failures,
                              fs.circuit_state,fs.authority_mode,fs.source_stream_id,
                              fs.zero_update_streak,fs.consecutive_zero_discovery
                       FROM fetch_run r JOIN fetch_schedule fs ON fs.id=r.schedule_id
                       WHERE r.id=:run_id AND r.source_id=:source_id FOR UPDATE OF r,fs"""
                )
            )
            row = (
                (
                    await connection.execute(
                        run_query,
                        {"run_id": run_id, "source_id": source_id},
                    )
                )
                .mappings()
                .one()
            )
            if round17_accounting:
                if request_count > int(row["request_count"]):
                    raise ValueError("request count exceeds the authoritative run total")
                if response_bytes > int(row["response_bytes"]):
                    raise ValueError("response bytes exceed the authoritative run total")
            terminal = "SUCCEEDED"
            retry_at = None
            failure_code = None
            circuit_state = "CLOSED"
            circuit_until = None
            failures = 0
            if failure is not None:
                classified = classify_failure(failure)
                failure_code = classified.code
                if classified.code == "NOT_MODIFIED":
                    terminal = "NOT_MODIFIED"
                elif classified.retryable:
                    half_open_failed = row["circuit_state"] == "HALF_OPEN"
                    delay = next_backoff(
                        SchedulePolicy(
                            backoff_base_seconds=row["backoff_base_seconds"],
                            backoff_cap_seconds=row["backoff_cap_seconds"],
                            max_attempts=row["max_attempts"],
                        ),
                        attempt=row["attempt_count"],
                        random_fraction=random_fraction,
                        retry_after_seconds=failure.retry_after_seconds,
                    )
                    if delay is not None and not half_open_failed:
                        terminal, retry_at = "RETRY_WAIT", observed_at + delay
                    else:
                        terminal = "FAILED"
                else:
                    terminal = "FAILED"
                counts_for_circuit = classified.counts_for_circuit or (
                    row["authority_mode"] == "PERSONAL_STREAM"
                    and classified.code != "NOT_MODIFIED"
                )
                if counts_for_circuit and (
                    terminal == "FAILED" or row["authority_mode"] == "PERSONAL_STREAM"
                ):
                    failures = row["consecutive_failures"] + 1
                    if failures >= 5 or row["circuit_state"] == "HALF_OPEN":
                        circuit_state = "OPEN"
                        circuit_until = observed_at + timedelta(minutes=30)
                        terminal = "FAILED"
                        retry_at = None
            elif row["circuit_state"] == "HALF_OPEN":
                circuit_state = "CLOSED"

            personal_stream_id = row["source_stream_id"]
            zero_discovery = int(row["consecutive_zero_discovery"])
            next_interval = int(row["interval_seconds"])
            zero_update_streak = int(row["zero_update_streak"])
            if row["authority_mode"] == "PERSONAL_STREAM" and personal_stream_id is not None:
                if failure is None and discovered_count == 0:
                    zero_discovery += 1
                elif failure is None:
                    zero_discovery = 0
                update_times = tuple(
                    (
                        await connection.execute(
                            text(
                                """SELECT observed_at FROM source_health_snapshot
                                    WHERE source_stream_id=:stream
                                      AND new_content_count>0
                                    ORDER BY observed_at DESC,id DESC LIMIT 20"""
                            ),
                            {"stream": personal_stream_id},
                        )
                    ).scalars()
                )
                adaptive = calculate_adaptive_interval(
                    AdaptiveScheduleInput(
                        content_update_times=update_times,
                        current_interval_seconds=int(row["interval_seconds"]),
                        new_content_count=observation.new_content_count,
                        zero_update_streak=zero_update_streak,
                    ),
                    random_fraction=random_fraction,
                )
                next_interval = adaptive.interval_seconds
                zero_update_streak = adaptive.zero_update_streak
            snapshot_id = uuid7()
            snapshot_parameters = {
                "id": snapshot_id,
                "source": source_id,
                "run": run_id,
                "transport": health.transport_status,
                "discovery": health.discovery_status,
                "parse": health.parse_status,
                "quality": health.quality_status,
                "freshness": health.freshness_status,
                "latest": observation.latest_published_at,
                "discovered": discovered_count,
                "parsed": parsed_count,
                "fields": int(observation.required_field_ratio * 10_000),
                "duplicates": int(observation.duplicate_ratio * 10_000),
                "backlog": observation.oldest_queue_age_seconds,
                "body_bytes": observation.discovery_body_bytes,
                "structure_sha256": observation.structure_fingerprint_sha256,
                "stream": personal_stream_id,
                "reason": observation.reason_code or failure_code,
                "http_status": observation.http_status,
                "new_content": observation.new_content_count,
                "next_interval": next_interval,
                "circuit": circuit_state,
                "self_heal": (
                    "CIRCUIT_WAIT" if circuit_state == "OPEN" else "NONE"
                ),
                "now": observed_at,
            }
            snapshot_query = (
                text(
                    """INSERT INTO source_health_snapshot
                       (id,source_id,fetch_run_id,transport_status,discovery_status,
                        parse_status,quality_status,freshness_status,latest_published_at,
                        discovered_count,parsed_count,required_field_basis_points,
                        duplicate_basis_points,oldest_queue_age_seconds,
                        discovery_body_bytes,structure_fingerprint_sha256,
                        rule_version,observed_at,source_stream_id,reason_code,http_status,
                        new_content_count,next_interval_seconds,circuit_state,self_heal_state)
                       VALUES (:id,:source,:run,:transport,:discovery,:parse,:quality,:freshness,
                               :latest,:discovered,:parsed,:fields,:duplicates,:backlog,
                               :body_bytes,:structure_sha256,'pers03-health-v1',:now,:stream,
                               :reason,:http_status,:new_content,:next_interval,:circuit,:self_heal)
                       ON CONFLICT (fetch_run_id) DO UPDATE SET
                         transport_status=EXCLUDED.transport_status,
                         discovery_status=EXCLUDED.discovery_status,
                         parse_status=EXCLUDED.parse_status,
                         quality_status=EXCLUDED.quality_status,
                         freshness_status=EXCLUDED.freshness_status,
                         latest_published_at=EXCLUDED.latest_published_at,
                         discovered_count=EXCLUDED.discovered_count,
                         parsed_count=EXCLUDED.parsed_count,
                         required_field_basis_points=EXCLUDED.required_field_basis_points,
                         duplicate_basis_points=EXCLUDED.duplicate_basis_points,
                         oldest_queue_age_seconds=EXCLUDED.oldest_queue_age_seconds,
                         discovery_body_bytes=EXCLUDED.discovery_body_bytes,
                         structure_fingerprint_sha256=EXCLUDED.structure_fingerprint_sha256,
                         observed_at=EXCLUDED.observed_at,
                         reason_code=EXCLUDED.reason_code,http_status=EXCLUDED.http_status,
                         new_content_count=EXCLUDED.new_content_count,
                         next_interval_seconds=EXCLUDED.next_interval_seconds,
                         circuit_state=EXCLUDED.circuit_state,
                         self_heal_state=EXCLUDED.self_heal_state
                       RETURNING id"""
                )
                if round17_accounting
                else text(
                    """INSERT INTO source_health_snapshot
                       (id,source_id,fetch_run_id,transport_status,discovery_status,
                        parse_status,quality_status,freshness_status,latest_published_at,
                        discovered_count,parsed_count,required_field_basis_points,
                        duplicate_basis_points,oldest_queue_age_seconds,rule_version,observed_at)
                       VALUES (:id,:source,:run,:transport,:discovery,:parse,:quality,:freshness,
                               :latest,:discovered,:parsed,:fields,:duplicates,:backlog,
                               'round16-health-v1',:now)
                       RETURNING id"""
                )
            )
            persisted_snapshot_id = await connection.scalar(
                snapshot_query, snapshot_parameters
            )
            if not isinstance(persisted_snapshot_id, UUID):
                raise RuntimeError("health snapshot persistence returned no identifier")
            snapshot_id = persisted_snapshot_id
            for code in health.anomaly_codes:
                await connection.execute(
                    text(
                        """INSERT INTO source_anomaly
                           (id,source_id,health_snapshot_id,code,severity,status,
                            rule_version,detected_at)
                           VALUES (:id,:source,:snapshot,:code,:severity,'OPEN',
                                   'round16-health-v1',:now)"""
                    ),
                    {
                        "id": uuid7(),
                        "source": source_id,
                        "snapshot": snapshot_id,
                        "code": code,
                        "severity": "CRITICAL"
                        if code in {"QUEUE_BACKLOG_STALE", "LATEST_PUBLICATION_STALLED"}
                        else "WARNING",
                        "now": observed_at,
                    },
                )
            if personal_stream_id is not None and zero_discovery >= 3:
                anomaly_exists = await connection.scalar(
                    text(
                        """SELECT 1 FROM source_anomaly
                            WHERE source_stream_id=:stream
                              AND code='ZERO_DISCOVERY_STREAK'
                              AND status IN ('OPEN','ACKNOWLEDGED') LIMIT 1"""
                    ),
                    {"stream": personal_stream_id},
                )
                if anomaly_exists is None:
                    await connection.execute(
                        text(
                            """INSERT INTO source_anomaly(
                                 id,source_id,source_stream_id,health_snapshot_id,code,
                                 severity,status,rule_version,detected_at)
                               VALUES(:id,:source,:stream,:snapshot,'ZERO_DISCOVERY_STREAK',
                                      'WARNING','OPEN','pers03-health-v1',:now)"""
                        ),
                        {
                            "id": uuid7(),
                            "source": source_id,
                            "stream": personal_stream_id,
                            "snapshot": snapshot_id,
                            "now": observed_at,
                        },
                    )
                active_probe = await connection.scalar(
                    text(
                        "SELECT 1 FROM stream_probe_run WHERE stream_id=:stream "
                        "AND status IN ('QUEUED','RUNNING') LIMIT 1"
                    ),
                    {"stream": personal_stream_id},
                )
                if active_probe is None:
                    await connection.execute(
                        text(
                            """INSERT INTO stream_probe_run(
                                 id,source_id,stream_id,requested_url,normalized_url,
                                 normalized_origin,input_kind,status,requested_by,request_id,
                                 created_at,updated_at)
                               SELECT :id,stream.source_id,stream.id,stream.canonical_url,
                                      stream.canonical_url,source.normalized_origin,'UNKNOWN',
                                      'QUEUED',source.registered_by,:request_id,:now,:now
                                 FROM source_stream stream JOIN source ON source.id=stream.source_id
                                WHERE stream.id=:stream"""
                        ),
                        {
                            "id": uuid7(),
                            "stream": personal_stream_id,
                            "request_id": f"self-heal:{run_id}",
                            "now": observed_at,
                        },
                    )
            await connection.execute(
                text(
                    """UPDATE fetch_run SET status=CAST(:status AS varchar),
                           completed_at=CASE
                             WHEN CAST(:status AS varchar)='RETRY_WAIT'
                             THEN NULL ELSE CAST(:now AS timestamptz)
                           END,
                           next_retry_at=:retry,failure_class=:failure,transport_status=:transport,
                           discovery_status=:discovery,parse_status=:parse,quality_status=:quality,
                           discovered_count=:discovered,fetched_count=:parsed,
                           execution_lease_token=NULL,execution_lease_until=NULL
                       WHERE id=:run"""
                ),
                {
                    "status": terminal,
                    "now": observed_at,
                    "retry": retry_at,
                    "failure": failure_code,
                    "transport": health.transport_status,
                    "discovery": health.discovery_status,
                    "parse": health.parse_status,
                    "quality": health.quality_status,
                    "discovered": discovered_count,
                    "parsed": parsed_count,
                    "run": run_id,
                },
            )
            await connection.execute(
                text(
                    """UPDATE fetch_schedule SET next_run_at=:next_run,
                           leased_until=NULL,lease_token=NULL,
                           consecutive_failures=:failures,circuit_state=:circuit,
                           circuit_open_until=:circuit_until,updated_at=:now
                       WHERE id=:schedule"""
                ),
                {
                    "next_run": retry_at or observed_at + timedelta(seconds=next_interval),
                    "failures": failures,
                    "circuit": circuit_state,
                    "circuit_until": circuit_until,
                    "now": observed_at,
                    "schedule": row["schedule_id"],
                },
            )
            if personal_stream_id is not None:
                await connection.execute(
                    text(
                        """UPDATE fetch_schedule SET interval_seconds=:interval,
                               zero_update_streak=:zero_updates,
                               consecutive_zero_discovery=:zero_discovery,
                               self_heal_state=:self_heal,
                               next_self_heal_at=:next_heal,
                               last_successful_fetch_at=CASE WHEN :succeeded THEN :now
                                                            ELSE last_successful_fetch_at END,
                               last_content_discovered_at=CASE WHEN :new_content>0 THEN :now
                                                               ELSE last_content_discovered_at END,
                               health_status=:health_status,health_reason=:health_reason
                             WHERE id=:schedule"""
                    ),
                    {
                        "interval": next_interval,
                        "zero_updates": zero_update_streak,
                        "zero_discovery": zero_discovery,
                        "self_heal": (
                            "CIRCUIT_WAIT"
                            if circuit_state == "OPEN"
                            else "REPROBE_QUEUED"
                            if zero_discovery >= 3
                            else "NONE"
                        ),
                        "next_heal": circuit_until,
                        "succeeded": failure is None,
                        "new_content": observation.new_content_count,
                        "now": observed_at,
                        "health_status": (
                            "UNHEALTHY" if failure is not None else
                            "DEGRADED" if zero_discovery >= 3 else "HEALTHY"
                        ),
                        "health_reason": (
                            observation.reason_code or failure_code
                            if failure is not None
                            else "ZERO_DISCOVERY_STREAK" if zero_discovery >= 3 else None
                        ),
                        "schedule": row["schedule_id"],
                    },
                )
            circuit_rows = (
                await connection.execute(
                    text(
                        "SELECT circuit_state,count(*) AS total "
                        "FROM fetch_schedule GROUP BY circuit_state"
                    )
                )
            ).mappings()
            circuit_counts: dict[str, int] = {
                str(row["circuit_state"]): int(row["total"]) for row in circuit_rows
            }
        if failure_code is not None:
            FETCH_FAILURES.labels(kind=failure_code).inc()
        SOURCE_PARSE_QUALITY_BPS.labels(status=health.quality_status).set(
            int(observation.required_field_ratio * 10_000)
        )
        FETCH_BACKLOG_AGE.labels(state=terminal).set(max(0, observation.oldest_queue_age_seconds))
        freshness_seconds = (
            0
            if observation.latest_published_at is None
            else max(0, (observed_at - observation.latest_published_at).total_seconds())
        )
        SOURCE_FRESHNESS.labels(status=health.freshness_status).set(freshness_seconds)
        for state in ("CLOSED", "OPEN", "HALF_OPEN"):
            SOURCE_CIRCUIT_STATE.labels(state=state).set(circuit_counts.get(state, 0))
        for dimension in health.anomaly_codes:
            SOURCE_SLO_VIOLATIONS.labels(dimension=dimension).inc()
        return terminal
