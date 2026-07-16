"""Transactional schedule claiming and idempotent run leasing."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

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
    FetchFailure,
    HealthObservation,
    SchedulePolicy,
    classify_failure,
    evaluate_health,
    next_backoff,
)


@dataclass(frozen=True, slots=True)
class ClaimedFetchRun:
    source_id: UUID
    run_id: UUID


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
                            """SELECT s.current_policy_version_id AS policy_id,
                                      s.current_connector_config_version_id AS config_id,
                                      (SELECT id FROM source_connector sc
                                        WHERE sc.source_id=s.id
                                        ORDER BY created_at DESC LIMIT 1) AS connector_id
                                 FROM source s WHERE s.id=:source_id"""
                        ),
                        {"source_id": row["source_id"]},
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
                        connector_config_version_id, idempotency_key, attempt_count)
                       VALUES (:id, :connector, 'SCHEDULED', 'PENDING_DISPATCH', :now,
                               0, 0, 0, :request_id, 'PRODUCTION', :source, :schedule,
                               :policy, :config, :idempotency, 0)"""
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
                       FROM source s, source_policy_version p, connector_config_version c,
                            fetch_schedule fs
                       WHERE r.id=:run_id AND r.source_id=:source_id
                         AND s.id=r.source_id AND s.lifecycle_state='ACTIVE'
                         AND fs.id=r.schedule_id AND fs.status='ACTIVE'
                         AND fs.requests_used < fs.daily_request_budget
                         AND fs.bytes_used < fs.daily_byte_budget
                         AND fs.circuit_state IN ('CLOSED','HALF_OPEN')
                         AND p.id=s.current_policy_version_id AND p.id=r.policy_version_id
                         AND p.status='APPROVED' AND p.valid_from <= :now AND p.valid_until > :now
                         AND c.id=s.current_connector_config_version_id
                         AND c.id=r.connector_config_version_id AND c.validation_status='VALID'
                         AND EXISTS (
                           SELECT 1 FROM source_governance_decision d
                            WHERE d.source_id=s.id
                              AND d.decision_type='PRODUCTION_APPROVAL'
                              AND d.outcome='APPROVED'
                              AND (d.valid_until IS NULL OR d.valid_until > :now)
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
                           JOIN source_policy_version p
                             ON p.id=s.current_policy_version_id
                           JOIN connector_config_version c
                             ON c.id=s.current_connector_config_version_id
                           JOIN fetch_schedule fs ON fs.id=r.schedule_id
                           WHERE s.id=r.source_id AND s.lifecycle_state='ACTIVE'
                             AND fs.status='ACTIVE'
                             AND fs.requests_used < fs.daily_request_budget
                             AND fs.bytes_used < fs.daily_byte_budget
                             AND fs.circuit_state IN ('CLOSED','HALF_OPEN')
                             AND p.id=r.policy_version_id AND p.status='APPROVED'
                             AND p.valid_from <= :now AND p.valid_until > :now
                             AND c.id=r.connector_config_version_id
                             AND c.validation_status='VALID'
                             AND EXISTS (
                               SELECT 1 FROM source_governance_decision d
                                WHERE d.source_id=s.id
                                  AND d.decision_type='PRODUCTION_APPROVAL'
                                  AND d.outcome='APPROVED'
                                  AND (d.valid_until IS NULL OR d.valid_until > :now)
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
        response_bytes: int = 0,
        failure: FetchFailure | None = None,
        now: datetime | None = None,
        random_fraction: Callable[[], float] = lambda: 0.5,
    ) -> str:
        observed_at = now or datetime.now(UTC)
        health = evaluate_health(observation, observed_at=observed_at)
        async with self._engine.begin() as connection:
            row = (
                (
                    await connection.execute(
                        text(
                            """SELECT r.attempt_count,r.schedule_id,fs.interval_seconds,
                                  fs.backoff_base_seconds,fs.backoff_cap_seconds,
                                  fs.max_attempts,fs.consecutive_failures,
                                  fs.circuit_state
                           FROM fetch_run r JOIN fetch_schedule fs ON fs.id=r.schedule_id
                           WHERE r.id=:run_id AND r.source_id=:source_id FOR UPDATE OF r,fs"""
                        ),
                        {"run_id": run_id, "source_id": source_id},
                    )
                )
                .mappings()
                .one()
            )
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
                if classified.counts_for_circuit and terminal == "FAILED":
                    failures = row["consecutive_failures"] + 1
                    if failures >= 5 or row["circuit_state"] == "HALF_OPEN":
                        circuit_state = "OPEN"
                        circuit_until = observed_at + timedelta(minutes=30)
            snapshot_id = uuid7()
            await connection.execute(
                text(
                    """INSERT INTO source_health_snapshot
                       (id,source_id,fetch_run_id,transport_status,discovery_status,
                        parse_status,quality_status,freshness_status,latest_published_at,
                        discovered_count,parsed_count,required_field_basis_points,
                        duplicate_basis_points,oldest_queue_age_seconds,rule_version,observed_at)
                       VALUES (:id,:source,:run,:transport,:discovery,:parse,:quality,:freshness,
                               :latest,:discovered,:parsed,:fields,:duplicates,:backlog,
                               'round16-health-v1',:now)"""
                ),
                {
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
                    "now": observed_at,
                },
            )
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
            await connection.execute(
                text(
                    """UPDATE fetch_run SET status=:status,
                           completed_at=CASE
                             WHEN :status='RETRY_WAIT' THEN NULL ELSE :now
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
                           circuit_open_until=:circuit_until,updated_at=:now,
                           requests_used=requests_used+1,
                           bytes_used=bytes_used+:response_bytes
                       WHERE id=:schedule"""
                ),
                {
                    "next_run": retry_at
                    or observed_at + timedelta(seconds=row["interval_seconds"]),
                    "failures": failures,
                    "circuit": circuit_state,
                    "circuit_until": circuit_until,
                    "now": observed_at,
                    "schedule": row["schedule_id"],
                    "response_bytes": max(0, response_bytes),
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
