import os

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import create_async_engine
from srbg_api.config import get_settings
from srbg_api.identifiers import uuid7
from srbg_api.internal_projection.audit_anchor import anchor_latest_audit_root
from srbg_api.internal_projection.backfill import backfill_internal_projection

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        os.environ.get("SRBG_RUN_ROUND13_INTEGRATION") != "1",
        reason="requires the disposable real projection-reader login",
    ),
]


@pytest_asyncio.fixture(scope="module", autouse=True)
async def build_shadow_generation() -> None:
    if os.environ.get("SRBG_RUN_ROUND13_INTEGRATION") != "1":
        return
    engine = create_async_engine(os.environ["SRBG_PUBLICATION_DATABASE_URL"])
    try:
        await backfill_internal_projection(engine)
    finally:
        await engine.dispose()


async def test_real_projection_reader_can_only_read_versioned_projection_views() -> None:
    url = os.environ["SRBG_PROJECTION_DATABASE_URL"]
    engine = create_async_engine(url)
    try:
        async with engine.connect() as connection:
            current_user = await connection.scalar(text("SELECT current_user"))
            assert current_user.startswith("srbg_it_reader_") or current_user == (
                "srbg_projection_reader_login"
            )
            assert await connection.scalar(
                text("SELECT has_schema_privilege(current_user, 'published_v1', 'USAGE')")
            )
            assert not await connection.scalar(
                text("SELECT has_schema_privilege(current_user, 'public', 'USAGE')")
            )
            rows = list(
                (
                    await connection.execute(
                        text(
                            "SELECT event_id, projection_level, summary_payload "
                            "FROM published_v1.current_event_summary ORDER BY event_id"
                        )
                    )
                ).mappings()
            )
            assert rows
            assert all(row["projection_level"] != "NONE" for row in rows)
            assert all(row["summary_payload"]["publication_risk_tier"] != "R4" for row in rows)
            for row in rows:
                if row["projection_level"] == "METADATA_ONLY":
                    assert row["summary_payload"].get("one_sentence_fact") is None
                    assert row["summary_payload"].get("type_summary") is None

            privilege_rows = list(
                (
                    await connection.execute(
                        text(
                            """
                            SELECT namespace.nspname || '.' || relation.relname object_name,
                                   has_table_privilege(
                                     current_user, relation.oid, 'SELECT'
                                   ) can_read
                              FROM pg_catalog.pg_class relation
                              JOIN pg_catalog.pg_namespace namespace
                                ON namespace.oid = relation.relnamespace
                             WHERE (namespace.nspname, relation.relname) IN (
                                ('public', 'intelligence_item'), ('public', 'raw_object'),
                                ('public', 'review_task'), ('public', 'audit_log'),
                                ('public', 'event'),
                                ('published_v1', 'event_projection_revision'),
                                ('published_v1', 'event_projection_field_source')
                             )
                            """
                        )
                    )
                ).mappings()
            )
            assert privilege_rows
            assert not any(row["can_read"] for row in privilege_rows)
    finally:
        await engine.dispose()


@pytest.mark.parametrize(
    "statement",
    [
        "SELECT * FROM public.intelligence_item LIMIT 1",
        "SELECT * FROM public.raw_object LIMIT 1",
        "SELECT * FROM public.review_task LIMIT 1",
        "SELECT * FROM public.audit_log LIMIT 1",
        "SELECT * FROM published_v1.event_projection_revision LIMIT 1",
        "INSERT INTO public.audit_log (id) VALUES (gen_random_uuid())",
    ],
)
async def test_real_projection_reader_is_denied_direct_business_and_audit_access(
    statement: str,
) -> None:
    engine = create_async_engine(os.environ["SRBG_PROJECTION_DATABASE_URL"])
    try:
        async with engine.connect() as connection:
            with pytest.raises(DBAPIError):
                await connection.execute(text(statement))
    finally:
        await engine.dispose()


async def test_metadata_only_is_excluded_from_distribution_detail_and_export() -> None:
    engine = create_async_engine(os.environ["SRBG_PROJECTION_DATABASE_URL"])
    try:
        async with engine.connect() as connection:
            metadata_ids = set(
                await connection.scalars(
                    text(
                        "SELECT event_id FROM published_v1.current_event_summary "
                        "WHERE projection_level = 'METADATA_ONLY'"
                    )
                )
            )
            distributed = set(
                await connection.scalars(
                    text("SELECT event_id FROM published_v1.distribution_candidates")
                )
            )
            detailed = set(
                await connection.scalars(
                    text("SELECT event_id FROM published_v1.current_event_detail")
                )
            )
            exported = set(
                await connection.scalars(text("SELECT event_id FROM published_v1.fulltext_export"))
            )
            assert metadata_ids.isdisjoint(distributed | detailed | exported)
    finally:
        await engine.dispose()


async def test_publication_writer_cannot_forge_audit_rows_but_can_use_chain_function() -> None:
    engine = create_async_engine(os.environ["SRBG_PUBLICATION_DATABASE_URL"])
    try:
        async with engine.connect() as connection:
            assert not await connection.scalar(
                text("SELECT has_table_privilege(current_user, 'public.audit_log', 'INSERT')")
            )
            with pytest.raises(DBAPIError):
                await connection.execute(
                    text("INSERT INTO audit_log (id) VALUES (:id)"), {"id": uuid7()}
                )
        async with engine.begin() as connection:
            audit_id = uuid7()
            created = await connection.scalar(
                text(
                    """
                    SELECT append_audit_event(
                        :id, 'ROUND13_BOUNDARY_TEST', :actor, 'EVENT', :target,
                        NULL, CAST(:after_state AS jsonb), 'boundary verification',
                        :request_id, now()
                    )
                    """
                ),
                {
                    "id": audit_id,
                    "actor": uuid7(),
                    "target": uuid7(),
                    "after_state": '{"controlled":true}',
                    "request_id": f"round13-audit-{audit_id}",
                },
            )
            assert created == audit_id
    finally:
        await engine.dispose()


async def test_latest_audit_root_is_anchored_to_independent_storage() -> None:
    get_settings.cache_clear()
    settings = get_settings()
    assert settings.backup_s3_endpoint_url != settings.s3_endpoint_url
    engine = create_async_engine(os.environ["SRBG_PUBLICATION_DATABASE_URL"])
    try:
        anchored = await anchor_latest_audit_root(engine, settings)
        assert anchored.entry_hash
        async with engine.connect() as connection:
            assert (
                await connection.scalar(
                    text(
                        "SELECT count(*) FROM audit_chain_anchor "
                        "WHERE audit_log_id = CAST(:id AS uuid) AND entry_hash = :hash"
                    ),
                    {"id": anchored.audit_log_id, "hash": anchored.entry_hash},
                )
                == 1
            )
    finally:
        await engine.dispose()
        get_settings.cache_clear()


async def test_backfill_is_idempotent_and_old_generation_cannot_remain_active() -> None:
    engine = create_async_engine(os.environ["SRBG_PUBLICATION_DATABASE_URL"])
    try:
        async with engine.connect() as connection:
            binding_count_before = await connection.scalar(
                text("SELECT count(*) FROM event_identity_binding")
            )
            previous_generation = await connection.scalar(
                text("SELECT max(generation) FROM published_v1.projection_build_run")
            )
        report = await backfill_internal_projection(engine)
        assert report.difference_count == 0
        assert report.generation == previous_generation + 1
        async with engine.connect() as connection:
            assert await connection.scalar(
                text("SELECT count(*) FROM event_identity_binding")
            ) == binding_count_before
            assert await connection.scalar(
                text(
                    "SELECT count(*) FROM published_v1.event_projection_revision "
                    "WHERE state = 'ACTIVE' AND generation < :generation"
                ),
                {"generation": report.generation},
            ) == 0
    finally:
        await engine.dispose()
