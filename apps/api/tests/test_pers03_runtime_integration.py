import os
from datetime import UTC, datetime
from hashlib import sha256
from urllib.parse import urlsplit
from uuid import UUID

import pytest
from sqlalchemy import text
from srbg_api.config import Settings
from srbg_api.database import create_database_engine
from srbg_api.identifiers import uuid7
from srbg_api.scheduling.domain import FetchFailure, HealthObservation
from srbg_api.scheduling.service import PostgresSchedulingService
from srbg_api.source_registry.repository import SourceVaultRepository
from srbg_contracts import PersonalSourceCreateRequest

pytestmark = pytest.mark.skipif(
    urlsplit(os.environ.get("SRBG_WORKER_DATABASE_URL", "")).hostname
    not in {"127.0.0.1", "localhost"},
    reason="requires the isolated PostgreSQL runner",
)


async def _ready_personal_stream() -> tuple[PostgresSchedulingService, UUID, UUID, UUID]:
    admin_engine = create_database_engine(
        Settings(database_url=os.environ["SRBG_TEST_ADMIN_DATABASE_URL"])
    )
    repository = SourceVaultRepository(admin_engine)
    owner_id = UUID("019d3000-0000-7000-8000-000000000001")
    host = f"pers03-{uuid7().hex[:12]}.example.test"
    source = await repository.create_personal_source(
        PersonalSourceCreateRequest(url=f"https://{host}/feed.xml"),
        actor_id=owner_id,
        request_id=f"pers03-{uuid7()}",
        now=datetime.now(UTC),
    )
    stream_id = source.streams[0].id
    config_id = uuid7()
    schedule_id = uuid7()
    config = f'{{"allowed_hosts":["{host}"],"feed_url":"https://{host}/feed.xml"}}'
    config_hash = sha256(config.encode()).hexdigest()
    async with admin_engine.begin() as connection:
        await connection.execute(
            text(
                "INSERT INTO stream_config_version(id,stream_id,probe_run_id,connector_type,"
                "definition_version,schema_version,config,config_sha256,"
                "discovery_method,created_at) "
                "SELECT :config,:stream,probe.id,'RSS_ATOM','1.0.0','2020-12',"
                "CAST(:document AS jsonb),:hash,'DIRECT',now() FROM stream_probe_run probe "
                "WHERE probe.stream_id=:stream ORDER BY probe.created_at DESC LIMIT 1"
            ),
            {
                "config": config_id,
                "stream": stream_id,
                "document": config,
                "hash": config_hash,
            },
        )
        await connection.execute(
            text(
                "UPDATE source_stream SET status='READY',stream_type='RSS_ATOM',"
                "allowed_hosts=ARRAY[CAST(:host AS varchar(253))],config_sha256=:hash,"
                "discovery_method='DIRECT',failure_reason=NULL WHERE id=:stream"
            ),
            {"stream": stream_id, "hash": config_hash, "host": host},
        )
        await connection.execute(
            text(
                "INSERT INTO fetch_schedule(id,source_id,source_stream_id,stream_config_version_id,"
                "authority_mode,authority_level,status,interval_seconds,next_run_at,"
                "backoff_base_seconds,backoff_cap_seconds,max_attempts,consecutive_failures,"
                "circuit_state,freshness_slo_seconds,rate_limit_per_minute,daily_request_budget,"
                "daily_byte_budget,requests_used,bytes_used,budget_window_started_at,"
                "version,updated_at) "
                "VALUES(:schedule,:source,:stream,:config,'PERSONAL_STREAM','PERSONAL','ACTIVE',"
                "3600,now(),1,60,3,0,'CLOSED',86400,6,20,1048576,0,0,now(),1,now())"
            ),
            {
                "schedule": schedule_id,
                "source": source.id,
                "stream": stream_id,
                "config": config_id,
            },
        )
        await connection.execute(
            text("UPDATE source_stream SET schedule_id=:schedule WHERE id=:stream"),
            {"schedule": schedule_id, "stream": stream_id},
        )
    return PostgresSchedulingService(admin_engine), source.id, stream_id, schedule_id


async def _claim_running(
    service: PostgresSchedulingService, source_id: UUID, now: datetime
) -> UUID:
    async with service._engine.begin() as connection:
        await connection.execute(
            text(
                "UPDATE fetch_schedule SET next_run_at=:now,leased_until=NULL,lease_token=NULL "
                "WHERE source_id=:source"
            ),
            {"now": now, "source": source_id},
        )
    claimed = await service.claim_due(now=now)
    assert claimed is not None and claimed.source_id == source_id
    async with service._engine.begin() as connection:
        await connection.execute(
            text("UPDATE fetch_run SET status='RUNNING' WHERE id=:run"),
            {"run": claimed.run_id},
        )
    return claimed.run_id


@pytest.mark.asyncio
async def test_personal_stream_runs_without_legacy_approvals_and_disable_revokes_network() -> None:
    service, source_id, _stream_id, _schedule_id = await _ready_personal_stream()
    try:
        async with service._engine.connect() as connection:
            assert await connection.scalar(
                text("SELECT count(*) FROM source_governance_decision WHERE source_id=:source"),
                {"source": source_id},
            ) == 0
        claimed = await service.claim_due(now=datetime.now(UTC))
        assert claimed is not None and claimed.source_id == source_id
        async with service._engine.begin() as connection:
            await connection.execute(
                text(
                    "UPDATE source SET desired_enabled=false,manual_disabled_at=now() "
                    "WHERE id=:source"
                ),
                {"source": source_id},
            )
        assert not await service.acquire_execution(
            source_id=source_id, run_id=claimed.run_id, now=datetime.now(UTC)
        )
    finally:
        await service.close()


@pytest.mark.asyncio
async def test_five_failures_half_open_and_zero_discovery_are_isolated_per_stream() -> None:
    service, source_id, stream_id, schedule_id = await _ready_personal_stream()
    now = datetime.now(UTC)
    try:
        for _ in range(5):
            run_id = await _claim_running(service, source_id, now)
            await service.record_outcome(
                source_id=source_id,
                run_id=run_id,
                observation=HealthObservation(transport_succeeded=False),
                discovered_count=0,
                parsed_count=0,
                failure=FetchFailure(kind="TIMEOUT"),
                now=now,
                random_fraction=lambda: 0.0,
            )
        async with service._engine.connect() as connection:
            state = (
                await connection.execute(
                    text(
                        "SELECT circuit_state,consecutive_failures,"
                        "circuit_open_until=next_self_heal_at FROM fetch_schedule WHERE id=:id"
                    ),
                    {"id": schedule_id},
                )
            ).one()
        assert tuple(state) == ("OPEN", 5, True)

        async with service._engine.begin() as connection:
            await connection.execute(
                text(
                    "UPDATE fetch_schedule SET circuit_state='OPEN',status='ACTIVE',"
                    "circuit_open_until=:expired WHERE id=:id"
                ),
                {"id": schedule_id, "expired": now},
            )
        half_open_success_run = await _claim_running(service, source_id, now)
        await service.record_outcome(
            source_id=source_id,
            run_id=half_open_success_run,
            observation=HealthObservation(transport_succeeded=True, new_content_count=1),
            discovered_count=1,
            parsed_count=1,
            now=now,
        )
        async with service._engine.connect() as connection:
            assert await connection.scalar(
                text("SELECT circuit_state FROM fetch_schedule WHERE id=:id"),
                {"id": schedule_id},
            ) == "CLOSED"

        async with service._engine.begin() as connection:
            await connection.execute(
                text(
                    "UPDATE fetch_schedule SET circuit_state='OPEN',"
                    "circuit_open_until=:expired WHERE id=:id"
                ),
                {"id": schedule_id, "expired": now},
            )
        half_open_failure_run = await _claim_running(service, source_id, now)
        await service.record_outcome(
            source_id=source_id,
            run_id=half_open_failure_run,
            observation=HealthObservation(transport_succeeded=False),
            discovered_count=0,
            parsed_count=0,
            failure=FetchFailure(kind="DNS"),
            now=now,
        )
        async with service._engine.begin() as connection:
            assert await connection.scalar(
                text("SELECT circuit_state FROM fetch_schedule WHERE id=:id"),
                {"id": schedule_id},
            ) == "OPEN"
            await connection.execute(
                text(
                    "UPDATE fetch_schedule SET circuit_state='CLOSED',"
                    "consecutive_failures=0 WHERE id=:id"
                ),
                {"id": schedule_id},
            )

        for _ in range(3):
            zero_run_id = await _claim_running(service, source_id, now)
            await service.record_outcome(
                source_id=source_id,
                run_id=zero_run_id,
                observation=HealthObservation(transport_succeeded=True),
                discovered_count=0,
                parsed_count=0,
                now=now,
            )
        async with service._engine.connect() as connection:
            assert await connection.scalar(
                text(
                    "SELECT count(*) FROM source_anomaly WHERE source_stream_id=:stream "
                    "AND code='ZERO_DISCOVERY_STREAK'"
                ),
                {"stream": stream_id},
            ) == 1
            assert await connection.scalar(
                text(
                    "SELECT count(*) FROM stream_probe_run WHERE stream_id=:stream "
                    "AND status='QUEUED'"
                ),
                {"stream": stream_id},
            ) == 1
    finally:
        await service.close()
