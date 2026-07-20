import os
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from srbg_api.identifiers import uuid7
from srbg_api.source_registry.controlled_stream import (
    AdmissionGates,
    PostgresControlledStreamRepository,
)

pytestmark = pytest.mark.asyncio
NOW = datetime(2026, 7, 20, 8, 0, tzinfo=UTC)


def _passing_gates() -> AdmissionGates:
    return AdmissionGates(**{name: True for name in AdmissionGates.__dataclass_fields__})


async def test_stream_admission_authorizes_only_current_owner_enabled_stream() -> None:
    engine = create_async_engine(os.environ["SRBG_TEST_ADMIN_DATABASE_URL"])
    repository = PostgresControlledStreamRepository(engine, now=lambda: NOW)
    try:
        async with engine.begin() as connection:
            source_id = await connection.scalar(text("SELECT id FROM source ORDER BY id LIMIT 1"))
            assert source_id is not None
            stream_ids = (uuid7(), uuid7())
            for index, stream_id in enumerate(stream_ids):
                await connection.execute(
                    text(
                        "INSERT INTO source_stream("
                        "id,source_id,stream_key,name,canonical_url,authorization_boundary,status,"
                        "rule_version,automatically_managed,created_at,updated_at,stream_type,"
                        "allowed_hosts,discovery_method) VALUES("
                        ":id,:source_id,:key,:name,:url,'fixture.example.gov.cn','READY',"
                        "'t07-test',false,:now,:now,'LIST_DETAIL',ARRAY['fixture.example.gov.cn'],"
                        "'T07_TEST')"
                    ),
                    {
                        "id": stream_id,
                        "source_id": source_id,
                        "key": f"t07-fixture-{index}",
                        "name": f"T07 fixture stream {index}",
                        "url": f"https://fixture.example.gov.cn/t07/{index}",
                        "now": NOW,
                    },
                )

        await repository.record_owner_intent(
            source_id=source_id,
            source_stream_id=stream_ids[0],
            desired_enabled=True,
            actor_id=uuid7(),
            request_id="t07-integration-enable",
        )
        assert await repository.record_admission_decision(
            source_id=source_id,
            source_stream_id=stream_ids[0],
            gates=_passing_gates(),
            evidence_sha256="a" * 64,
            actor_id=uuid7(),
            valid_for=timedelta(hours=1),
        ) == "ADMIT"

        authorization_id = await repository.authorize_shadow(
            source_id=source_id, source_stream_id=stream_ids[0]
        )
        assert authorization_id is not None
        assert await repository.authorize_shadow(
            source_id=source_id, source_stream_id=stream_ids[1]
        ) is None

        assert await repository.record_admission_decision(
            source_id=source_id,
            source_stream_id=stream_ids[0],
            gates=AdmissionGates(
                **(
                    {
                        name: True
                        for name in AdmissionGates.__dataclass_fields__
                    }
                    | {"robots_allowed": False}
                )
            ),
            evidence_sha256="b" * 64,
            actor_id=uuid7(),
            valid_for=timedelta(hours=1),
        ) == "PAUSE"
        assert await repository.authorize_shadow(
            source_id=source_id, source_stream_id=stream_ids[0]
        ) is None
        assert await repository.start_shadow(
            authorization_event_id=authorization_id, run_id=uuid7()
        ) is None

        assert await repository.record_admission_decision(
            source_id=source_id,
            source_stream_id=stream_ids[0],
            gates=_passing_gates(),
            evidence_sha256="c" * 64,
            actor_id=uuid7(),
            valid_for=timedelta(hours=1),
        ) == "ADMIT"
        authorization_id = await repository.authorize_shadow(
            source_id=source_id, source_stream_id=stream_ids[0]
        )
        assert authorization_id is not None

        await repository.record_owner_intent(
            source_id=source_id,
            source_stream_id=stream_ids[0],
            desired_enabled=False,
            actor_id=uuid7(),
            request_id="t07-integration-disable",
        )
        assert await repository.start_shadow(
            authorization_event_id=authorization_id, run_id=uuid7()
        ) is None

        async with engine.connect() as connection:
            counts = (
                await connection.execute(
                    text(
                        "SELECT count(DISTINCT source_id),count(*) FROM source_stream "
                        "WHERE id=ANY(:stream_ids)"
                    ),
                    {"stream_ids": list(stream_ids)},
                )
            ).one()
            assert tuple(counts) == (1, 2)
        async with engine.begin() as connection:
            with pytest.raises(Exception, match="T07_APPEND_ONLY_FACT"):
                await connection.execute(
                    text(
                        "UPDATE source_stream_admission_decision_v2 SET verdict='PAUSE' "
                        "WHERE source_stream_id=:stream_id"
                    ),
                    {"stream_id": stream_ids[0]},
                )
    finally:
        await engine.dispose()
