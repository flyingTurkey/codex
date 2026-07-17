import asyncio
import inspect
import os
import runpy
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import urlsplit
from uuid import UUID

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import create_async_engine
from srbg_api.config import get_settings

MIGRATION = Path("apps/api/migrations/versions/0018_source_automation.py")


def test_round18_is_the_single_head_and_creates_isolated_automation_facts() -> None:
    script = ScriptDirectory.from_config(Config("apps/api/alembic.ini"))
    assert script.get_current_head() == "0019_source_content_bridge"
    revision = script.get_revision("0018_source_automation")
    assert revision.down_revision == "0017c_round17_flat_pilot"

    module = runpy.run_path(str(MIGRATION))
    assert set(module["SOURCE_AUTOMATION_TABLES"]) >= {
        "source_candidate",
        "source_candidate_occurrence",
        "source_qualification_run",
        "source_qualification_capture",
        "source_qualification_bundle",
        "source_candidate_decision",
        "source_stream",
        "source_activation_outbox",
        "source_provider_usage",
    }


def test_qualification_evidence_is_isolated_and_search_provider_payload_cannot_persist() -> None:
    source = MIGRATION.read_text(encoding="utf-8")

    assert "execution_domain IN ('QUALIFICATION')" in source
    assert "qualification/sha256/" in source
    assert "source_qualification_capture" in source
    assert "raw_response" not in source
    assert "provider_payload" not in source
    assert "search_snippet" not in source
    assert "search_result_title" not in source
    assert "source_provider_usage" in source
    assert "cost_micrormb" in source


def test_activation_is_atomic_stale_safe_idempotent_and_audited() -> None:
    source = MIGRATION.read_text(encoding="utf-8")

    for required in (
        "register_discovered_source_candidate",
        "request_source_qualification",
        "activate_qualified_candidate",
        "FOR UPDATE",
        "p_expected_bundle_sha256",
        "material_fingerprint",
        "valid_until",
        "WARN_WAIVABLE",
        "waiver_reason",
        "PRODUCTION_REFETCH",
        "append_audit_event",
        "source_candidate_decision",
        "source_activation_outbox",
        "request_sha256",
        "idempotency_key",
    ):
        assert required in source
    assert "verdict='BLOCKED'" in source or "verdict = 'BLOCKED'" in source
    assert "GRANT EXECUTE ON FUNCTION activate_qualified_candidate" in source
    assert "REVOKE ALL ON" in source


def test_source_stream_expand_backfills_without_grandfathering_activation() -> None:
    module = runpy.run_path(str(MIGRATION))
    source = inspect.getsource(module["_backfill_default_streams"])

    assert "DEFAULT" in source
    assert "INSERT INTO source_stream" in source
    assert "FROM source" in source
    assert "lifecycle_state='ACTIVE'" not in source
    assert "runtime_authorization" not in source
    assert "authorization_boundary" in source
    assert "stream_key" in source
    assert "ON CONFLICT (source_id,stream_key) DO NOTHING" in source


def test_round18_has_append_only_guards_and_refuses_destructive_downgrade() -> None:
    source = MIGRATION.read_text(encoding="utf-8")

    assert "prevent_source_automation_fact_mutation" in source
    assert "ROUND18_DOWNGRADE_BLOCKED" in source
    assert "IF EXISTS (SELECT 1 FROM source_candidate_decision" in source
    assert "IF EXISTS (SELECT 1 FROM source_qualification_bundle" in source


def test_round18_repairs_policy_approval_and_non_pilot_runtime_authority() -> None:
    module = runpy.run_path(str(MIGRATION))
    source = inspect.getsource(module["_repair_scheduled_runtime_authority"])
    policy_source = inspect.getsource(module["_create_policy_authority_projection"])

    assert "source_policy_compliance_current" in policy_source
    assert "decision_type='COMPLIANCE'" in policy_source
    assert "record_scheduled_source_raw" in source
    assert "record_scheduled_source_document" in source
    assert "round17_pilot_window_source" in source
    assert "NOT EXISTS" in source
    assert "RAW_EVIDENCE_ALLOWED" not in source
    assert "source_private_evidence_capture_allowed" in source


def test_stream_activation_and_downgrade_restore_runtime_dependencies() -> None:
    module = runpy.run_path(str(MIGRATION))
    stream_source = inspect.getsource(module["_create_stream_and_decision_tables"])
    backfill_source = inspect.getsource(module["_backfill_default_streams"])
    activation_source = inspect.getsource(module["_create_candidate_commands"])
    downgrade_source = inspect.getsource(module["downgrade"])

    assert 'sa.Column("rule_version"' in stream_source
    assert "REQUALIFICATION_REQUIRED" in backfill_source
    assert "schedule_id" in backfill_source
    assert "rule_version" in activation_source
    assert "schedule_id" in activation_source
    assert "_restore_round17_runtime_authority" in downgrade_source


def test_net_new_candidates_are_prepared_without_promoting_qualification_raw() -> None:
    module = runpy.run_path(str(MIGRATION))
    command_source = inspect.getsource(module["_create_candidate_commands"])
    policy_source = inspect.getsource(module["_create_policy_authority_projection"])

    assert "prepare_source_candidate_for_qualification" in command_source
    assert "INSERT INTO source_policy_version" in command_source
    assert "INSERT INTO connector_config_version" in command_source
    assert "INSERT INTO source_trial_run" in command_source
    assert "INSERT INTO source_connector" in command_source
    assert "INSERT INTO fetch_schedule" in command_source
    assert "prepared_source_id" in command_source
    assert "source_candidate_decision" in policy_source
    assert "qualification_bundle_id" in policy_source
    assert "source_trial_run_result" in command_source
    assert "source-automation-qualification-v1" in command_source
    assert "INSERT INTO source_qualification_capture" not in command_source
    assert "raw_object" not in command_source
    assert "pg_advisory_xact_lock" in command_source
    assert "target_evidence_ref=p_target_evidence_ref" in command_source
    assert "RETURN NULL" in command_source
    assert "v_status NOT IN ('DISCOVERED','STALE','BLOCKED')" in command_source
    assert "GENERAL_TRANSPORT" in command_source
    assert "DIGITAL_TRANSFORMATION_CASE" in command_source
    assert "ACCIDENT_INVESTIGATION" in command_source
    assert "RECTIFICATION" in command_source
    assert "TENDER" not in command_source
    assert "'evidence_capture_policy','PRIVATE_RAW_ALLOWED'" in command_source
    assert "'isolation_namespace','qualification/sha256/'" in command_source
    assert "'retention_days',30" in command_source
    assert "'promotion_allowed',false" in command_source


def test_enabled_material_change_fails_closed_before_requalification() -> None:
    module = runpy.run_path(str(MIGRATION))
    command_source = inspect.getsource(module["_create_candidate_commands"])

    assert "v_before_status='ENABLED'" in command_source
    assert "UPDATE source_stream SET status='PAUSED'" in command_source
    assert "UPDATE fetch_schedule SET status='PAUSED'" in command_source
    assert "lifecycle_state='PAUSED'" in command_source
    assert "SOURCE_MATERIAL_CHANGED" in command_source
    assert "source_row.lifecycle_state IN ('CANDIDATE','PAUSED')" in command_source
    assert "v_scope_changed" in command_source
    assert "current_bundle_id=CASE WHEN v_requalification_required THEN NULL" in command_source
    assert "v_scope_changed AND v_before_status<>'ENABLED'" in command_source
    assert "v_before_status='ENABLED' AND v_scope_changed" in command_source
    assert "SET status='CANCELLED'" in command_source


def test_blocked_current_bundle_can_be_dismissed_but_never_enabled() -> None:
    module = runpy.run_path(str(MIGRATION))
    command_source = inspect.getsource(module["_create_candidate_commands"])

    assert "v_candidate.status NOT IN ('READY_FOR_DECISION','BLOCKED')" in command_source
    assert "v_candidate.status<>'READY_FOR_DECISION'" in command_source
    assert "v_bundle.verdict = 'BLOCKED'" in command_source
    assert "TO srbg_api_role,srbg_worker_role" in command_source


def test_worker_role_only_executes_narrow_database_commands() -> None:
    module = runpy.run_path(str(MIGRATION))
    role_source = inspect.getsource(module["_configure_roles"])
    boundary_source = inspect.getsource(module["_create_worker_command_boundary"])

    assert "REVOKE ALL ON" in role_source
    assert "srbg_api_role,srbg_worker_role" in role_source
    assert "GRANT SELECT ON" in role_source
    assert "TO srbg_api_role" in role_source
    assert "GRANT UPDATE" not in role_source
    assert "GRANT INSERT" not in role_source
    for command_name in (
        "acquire_source_qualification",
        "record_source_qualification_capture",
        "complete_source_qualification",
        "fail_source_qualification",
        "prepare_source_activation",
        "complete_source_activation",
        "reserve_source_provider_usage",
    ):
        assert f"CREATE FUNCTION {command_name}" in boundary_source
    assert "SECURITY DEFINER" in boundary_source
    assert "source_provider_budget_policy" in boundary_source


@pytest.mark.skipif(
    not os.environ.get("SRBG_ROUND18_MIGRATION_DATABASE_URL"),
    reason="requires a dedicated disposable PostgreSQL database",
)
def test_round18_upgrade_and_downgrade_execute_on_disposable_postgres(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_url = os.environ["SRBG_ROUND18_MIGRATION_DATABASE_URL"]
    parsed = urlsplit(database_url.replace("postgresql+asyncpg", "postgresql", 1))
    database_name = parsed.path.removeprefix("/")
    if parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError("Round18 migration replay is restricted to loopback PostgreSQL")
    if not database_name.startswith("srbg_it_"):
        raise ValueError("Round18 migration replay requires an explicitly disposable database")

    config = Config("apps/api/alembic.ini")
    monkeypatch.setenv("SRBG_DATABASE_URL", database_url)
    get_settings.cache_clear()
    try:
        command.upgrade(config, "0017c_round17_flat_pilot")
        asyncio.run(_seed_round17_source_with_schedule(database_url))
        command.upgrade(config, "0018_source_automation")
        asyncio.run(_assert_round18_runtime_shape(database_url))
        command.downgrade(config, "0017c_round17_flat_pilot")
        asyncio.run(_assert_round17_runtime_restored(database_url))
        command.upgrade(config, "0018_source_automation")
        asyncio.run(_assert_worker_discovery_gateway(database_url))
        asyncio.run(_seed_round18_activation_fixture(database_url))
        asyncio.run(_assert_qualified_candidate_activation(database_url))
        with pytest.raises(RuntimeError, match="ROUND18_DOWNGRADE_BLOCKED"):
            command.downgrade(config, "0017c_round17_flat_pilot")
        command.upgrade(config, "0019_source_content_bridge")
        asyncio.run(_assert_round19_source_content_bridge(database_url))
        asyncio.run(_assert_round18_runtime_shape(database_url))
        asyncio.run(_assert_blocked_candidate_dismissal(database_url))
        asyncio.run(_assert_failed_candidate_dismissal(database_url))
        with pytest.raises(RuntimeError, match="ROUND19_DOWNGRADE_BLOCKED"):
            command.downgrade(config, "0018_source_automation")
    finally:
        get_settings.cache_clear()


async def _assert_round19_source_content_bridge(database_url: str) -> None:
    engine = create_async_engine(database_url)
    try:
        async with engine.begin() as connection:
            await connection.execute(text("SET LOCAL ROLE srbg_worker_role"))
            dispatch = (
                await connection.execute(
                    text(
                        """
                        SELECT * FROM prepare_source_activation(
                          '019b1800-0000-7000-8000-00000000e134',
                          '019b1900-0000-7000-8000-000000000001',
                          now(),now()+interval '5 minutes'
                        )
                        """
                    )
                )
            ).one()
            assert dispatch.needs_dispatch
            completed = await connection.scalar(
                text(
                    """
                    SELECT complete_source_activation(
                      '019b1800-0000-7000-8000-00000000e134',
                      '019b1900-0000-7000-8000-000000000001',
                      :source_id,now()
                    )
                    """
                ),
                {"source_id": dispatch.source_id},
            )
            assert str(completed) == "019b1800-0000-7000-8000-00000000e134"
            await connection.execute(text("RESET ROLE"))
            await connection.execute(
                text(
                    """
                    UPDATE fetch_run
                       SET status='RUNNING',started_at=now()-interval '1 second',
                           execution_lease_token=
                             '019b1900-0000-7000-8000-000000000002',
                           execution_lease_until=now()+interval '5 minutes'
                     WHERE id='019b1900-0000-7000-8000-000000000001'
                    """
                )
            )
            await connection.execute(text("SET LOCAL ROLE srbg_worker_role"))
            raw = (
                await connection.execute(
                    text(
                        """
                        SELECT * FROM record_scheduled_source_raw(
                          '019b1900-0000-7000-8000-000000000003',
                          '019b1900-0000-7000-8000-000000000004',
                          :source_id,'019b1900-0000-7000-8000-000000000001',
                          repeat('a',64),repeat('b',64),
                          'sha256/aa/' || repeat('a',64),'round19-etag',128,
                          'text/html','text/html','CLEAN',NULL,
                          'https://new-source.example.test/content',
                          'https://new-source.example.test/content','[]'::jsonb,
                          200,NULL,NULL,now()
                        )
                        """
                    ),
                    {"source_id": dispatch.source_id},
                )
            ).one()
            assert str(raw.raw_object_id) == "019b1900-0000-7000-8000-000000000003"
            version_id = await connection.scalar(
                text(
                    """
                    SELECT record_scheduled_source_document(
                      '019b1900-0000-7000-8000-000000000005',
                      '019b1900-0000-7000-8000-000000000006',
                      '019b1900-0000-7000-8000-000000000007',
                      '019b1900-0000-7000-8000-000000000008',
                      '019b1900-0000-7000-8000-000000000009',
                      :source_id,'019b1900-0000-7000-8000-000000000001',
                      '019b1900-0000-7000-8000-000000000003',
                      '019b1900-0000-7000-8000-000000000004',
                      'https://new-source.example.test/content','HTML',
                      repeat('a',64),'round19.html','Round 19 bridge fixture',now()
                    )
                    """
                ),
                {"source_id": dispatch.source_id},
            )
            assert str(version_id) == "019b1900-0000-7000-8000-000000000006"

        async with engine.connect() as connection:
            outbox = (
                await connection.execute(
                    text(
                        """
                        SELECT id,status,document_version_id
                          FROM source_content_outbox
                         WHERE document_version_id=
                           '019b1900-0000-7000-8000-000000000006'
                        """
                    )
                )
            ).one()
            assert outbox.status == "PENDING"
            before = (
                await connection.execute(
                    text(
                        """
                        SELECT
                          (SELECT count(*) FROM claim) AS claims,
                          (SELECT count(*) FROM claim_evidence) AS evidence,
                          (SELECT count(*) FROM review_task) AS reviews,
                          (SELECT count(*) FROM publication_revision) AS publications
                        """
                    )
                )
            ).one()

        async with engine.connect() as connection:
            transaction = await connection.begin()
            try:
                await connection.execute(text("SET LOCAL ROLE srbg_worker_role"))
                with pytest.raises(DBAPIError):
                    await connection.execute(text("SELECT * FROM source_content_outbox"))
            finally:
                await transaction.rollback()

        async with engine.begin() as connection:
            await connection.execute(text("SET LOCAL ROLE srbg_worker_role"))
            pending = (
                await connection.execute(
                    text("SELECT outbox_id FROM list_pending_source_content_ids(now(),100)")
                )
            ).scalars().all()
            assert outbox.id in pending
            first = (
                await connection.execute(
                    text(
                        """
                        SELECT * FROM handoff_source_content_to_ai(
                          :outbox_id,'019b1900-0000-7000-8000-000000000010',now()
                        )
                        """
                    ),
                    {"outbox_id": outbox.id},
                )
            ).one()
            duplicate = (
                await connection.execute(
                    text(
                        """
                        SELECT * FROM handoff_source_content_to_ai(
                          :outbox_id,'019b1900-0000-7000-8000-000000000011',now()
                        )
                        """
                    ),
                    {"outbox_id": outbox.id},
                )
            ).one()
            assert first.status == "WAITING_AI"
            assert first.queued
            assert str(first.pipeline_run_id) == "019b1900-0000-7000-8000-000000000010"
            assert duplicate.status == "WAITING_AI"
            assert not duplicate.queued
            assert duplicate.pipeline_run_id == first.pipeline_run_id

        async with engine.connect() as connection:
            bridge = (
                await connection.execute(
                    text(
                        """
                        SELECT content.status,content.attempt_count,
                               pipeline.mode,pipeline.status AS pipeline_status,
                               count(*) OVER () AS pipeline_count
                          FROM source_content_outbox content
                          JOIN ai_pipeline_run pipeline
                            ON pipeline.id=content.pipeline_run_id
                         WHERE content.id=:outbox_id
                        """
                    ),
                    {"outbox_id": outbox.id},
                )
            ).one()
            after = (
                await connection.execute(
                    text(
                        """
                        SELECT
                          (SELECT count(*) FROM claim) AS claims,
                          (SELECT count(*) FROM claim_evidence) AS evidence,
                          (SELECT count(*) FROM review_task) AS reviews,
                          (SELECT count(*) FROM publication_revision) AS publications
                        """
                    )
                )
            ).one()
            assert bridge.status == "WAITING_AI"
            assert bridge.attempt_count == 1
            assert bridge.mode == "LIVE"
            assert bridge.pipeline_status == "QUEUED"
            assert bridge.pipeline_count == 1
            assert after == before
    finally:
        await engine.dispose()


async def _seed_round17_source_with_schedule(database_url: str) -> None:
    engine = create_async_engine(database_url)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    """
                    INSERT INTO source(
                      id,registry_code,name,base_url,channel,source_type,
                      authority_level,priority,collection_method,
                      poll_interval_minutes,owner,state,enabled,created_at,updated_at,
                      lifecycle_state
                    ) VALUES (
                      '019b1800-0000-7000-8000-00000000e101','R18-REPLAY-001',
                      'Round18 migration replay source','https://source.example.test/',
                      'BOTH','government','A1','P2','rss',60,'migration-test',
                      'CANDIDATE',false,now(),now(),'CANDIDATE'
                    )
                    """
                )
            )
            await connection.execute(
                text(
                    """
                    INSERT INTO fetch_schedule(
                      id,source_id,authority_level,status,interval_seconds,next_run_at,
                      freshness_slo_seconds,rate_limit_per_minute,daily_request_budget,
                      daily_byte_budget,budget_window_started_at,updated_at
                    ) VALUES (
                      '019b1800-0000-7000-8000-00000000e102',
                      '019b1800-0000-7000-8000-00000000e101','A1','ACTIVE',3600,now(),
                      28800,1,100,104857600,now(),now()
                    )
                    """
                )
            )
    finally:
        await engine.dispose()


async def _assert_round18_runtime_shape(database_url: str) -> None:
    engine = create_async_engine(database_url)
    try:
        async with engine.connect() as connection:
            stream = (
                await connection.execute(
                    text(
                        """
                        SELECT schedule_id,rule_version,status
                          FROM source_stream
                         WHERE source_id='019b1800-0000-7000-8000-00000000e101'::uuid
                        """
                    )
                )
            ).one()
            assert str(stream.schedule_id) == "019b1800-0000-7000-8000-00000000e102"
            assert stream.rule_version == "REQUALIFICATION_REQUIRED"
            assert stream.status == "QUALIFIED"
            assert await connection.scalar(
                text(
                    """
                    SELECT has_function_privilege(
                      'srbg_worker_role',
                      'claim_due_fetch_schedule(timestamptz,timestamptz,uuid)',
                      'EXECUTE'
                    )
                    """
                )
            )
            assert await connection.scalar(
                text(
                    """
                    SELECT has_function_privilege(
                      'srbg_worker_role',
                      'request_automated_source_qualification(uuid,uuid,text,uuid,text,text,uuid,timestamptz)',
                      'EXECUTE'
                    )
                    """
                )
            )
            assert not await connection.scalar(
                text(
                    """
                    SELECT EXISTS(
                      SELECT 1
                        FROM pg_proc function_row
                        CROSS JOIN LATERAL aclexplode(
                          coalesce(
                            function_row.proacl,
                            acldefault('f',function_row.proowner)
                          )
                        ) privilege
                       WHERE function_row.oid='activate_qualified_candidate(
                         uuid,text,text,text,text,text,text,uuid,uuid,uuid,uuid,uuid,
                         uuid,uuid,uuid,timestamptz
                       )'::regprocedure
                         AND privilege.grantee=0
                         AND privilege.privilege_type='EXECUTE'
                    )
                    """
                )
            )
            assert not await connection.scalar(
                text(
                    """
                    SELECT has_function_privilege(
                      'srbg_worker_role',
                      'request_source_qualification(uuid,uuid,text,uuid,text,text,uuid,timestamptz)',
                      'EXECUTE'
                    )
                    """
                )
            )
            assert not await connection.scalar(
                text(
                    """
                    SELECT has_function_privilege(
                      'srbg_worker_role',
                      'prepare_source_candidate_for_qualification(uuid,uuid,uuid,timestamptz)',
                      'EXECUTE'
                    )
                    """
                )
            )
            permissions = (
                await connection.execute(
                    text(
                        """
                        SELECT
                          has_table_privilege(
                            'srbg_worker_role','source_candidate_occurrence','INSERT'
                          ) AS occurrence_insert,
                          has_table_privilege(
                            'srbg_worker_role','source_candidate','INSERT'
                          ) AS candidate_insert,
                          has_table_privilege(
                            'srbg_worker_role','source_candidate','UPDATE'
                          ) AS candidate_table_update,
                          has_column_privilege(
                            'srbg_worker_role','source_candidate','status','UPDATE'
                          ) AS candidate_status_update,
                          has_column_privilege(
                            'srbg_worker_role','source_candidate','industries','UPDATE'
                          ) AS candidate_industries_update,
                          has_table_privilege(
                            'srbg_worker_role','source_qualification_run','INSERT'
                          ) AS qualification_run_insert,
                          has_table_privilege(
                            'srbg_worker_role','source_qualification_run','UPDATE'
                          ) AS qualification_run_table_update,
                          has_column_privilege(
                            'srbg_worker_role','source_qualification_run','status','UPDATE'
                          ) AS qualification_run_status_update,
                          has_table_privilege(
                            'srbg_worker_role','source_qualification_bundle','INSERT'
                          ) AS qualification_bundle_insert,
                          has_table_privilege(
                            'srbg_worker_role','source_qualification_bundle','UPDATE'
                          ) AS qualification_bundle_update,
                          has_table_privilege(
                            'srbg_worker_role','source_provider_usage','UPDATE'
                          ) AS provider_usage_update,
                          has_table_privilege(
                            'srbg_worker_role','source_provider_budget_policy','SELECT'
                          ) AS provider_policy_select
                        """
                    )
                )
            ).one()
            assert not permissions.occurrence_insert
            assert not permissions.candidate_insert
            assert not permissions.candidate_table_update
            assert not permissions.candidate_status_update
            assert not permissions.candidate_industries_update
            assert not permissions.qualification_run_insert
            assert not permissions.qualification_run_table_update
            assert not permissions.qualification_run_status_update
            assert not permissions.qualification_bundle_insert
            assert not permissions.qualification_bundle_update
            assert not permissions.provider_usage_update
            assert not permissions.provider_policy_select
            for signature in runpy.run_path(str(MIGRATION))["WORKER_COMMAND_SIGNATURES"]:
                assert await connection.scalar(
                    text(
                        "SELECT has_function_privilege("
                        "'srbg_worker_role',CAST(:signature AS text),'EXECUTE')"
                    ),
                    {"signature": signature},
                )

            activation_candidate_exists = await connection.scalar(
                text(
                    "SELECT EXISTS(SELECT 1 FROM source_candidate "
                    "WHERE id='019b1800-0000-7000-8000-00000000e120'::uuid "
                    "AND status='ENABLED')"
                )
            )
        if not activation_candidate_exists:
            return

        async with engine.begin() as connection:
            governance_fingerprint = await connection.scalar(
                text(
                    "SELECT material_fingerprint FROM source_candidate "
                    "WHERE id='019b1800-0000-7000-8000-00000000e120'::uuid"
                )
            )
            await connection.execute(text("SET LOCAL ROLE srbg_worker_role"))
            same_candidate = await connection.scalar(
                text(
                    """
                    SELECT register_discovered_source_candidate(
                      '019b1800-0000-7000-8000-00000000e140',
                      '019b1800-0000-7000-8000-00000000e141',
                      'https://new-source.example.test/',
                      encode(digest(convert_to(
                        'https://new-source.example.test/','UTF8'
                      ),'sha256'),'hex'),
                      'new-source.example.test',repeat('c',64),'MANUAL',
                      'manual-submission:round18-same-material',ARRAY[]::text[],
                      ARRAY[]::text[],ARRAY['zh-CN'],
                      '019b1800-0000-7000-8000-00000000e901',
                      'rediscover unchanged enabled source',
                      'round18-same-material',
                      '019b1800-0000-7000-8000-00000000e142',now()
                    )
                    """
                )
            )
            assert str(same_candidate) == "019b1800-0000-7000-8000-00000000e120"
            assert (
                await connection.scalar(
                    text(
                        """
                    SELECT request_automated_source_qualification(
                      '019b1800-0000-7000-8000-00000000e143',
                      '019b1800-0000-7000-8000-00000000e120',
                      'source-qualification-v1',
                      '019b1800-0000-7000-8000-00000000e901',
                      'do not requalify unchanged enabled source',
                      'round18-same-material-qualification',
                      '019b1800-0000-7000-8000-00000000e144',now()
                    )
                    """
                    )
                )
                is None
            )
            scope_changed_candidate = await connection.scalar(
                text(
                    """
                    SELECT register_discovered_source_candidate(
                      '019b1800-0000-7000-8000-00000000e150',
                      '019b1800-0000-7000-8000-00000000e151',
                      'https://new-source.example.test/',
                      encode(digest(convert_to(
                        'https://new-source.example.test/','UTF8'
                      ),'sha256'),'hex'),
                      'new-source.example.test',repeat('c',64),'MANUAL',
                      'manual-submission:round18-scope-change',ARRAY['BRIDGE']::text[],
                      ARRAY['STANDARD_GUIDANCE']::text[],ARRAY['zh-CN','en'],
                      '019b1800-0000-7000-8000-00000000e901',
                      'expand classification scope of enabled source',
                      'round18-scope-change',
                      '019b1800-0000-7000-8000-00000000e152',now()
                    )
                    """
                )
            )
            assert scope_changed_candidate == same_candidate
            await connection.execute(text("RESET ROLE"))
            scope_state = (
                await connection.execute(
                    text(
                        """
                        SELECT candidate.status,candidate.current_bundle_id,
                               source_row.lifecycle_state,source_row.state,
                               source_row.enabled,source_row.industries,
                               source_row.content_domains,source_row.language_tags,
                               stream.status AS stream_status,stream.paused_reason,
                               schedule.status AS schedule_status,
                               connector.enabled AS connector_enabled
                          FROM source_candidate candidate
                          JOIN source source_row ON source_row.id=candidate.source_id
                          JOIN source_stream stream ON stream.source_id=source_row.id
                          JOIN fetch_schedule schedule ON schedule.source_id=source_row.id
                          JOIN source_connector connector ON connector.source_id=source_row.id
                         WHERE candidate.id='019b1800-0000-7000-8000-00000000e120'
                        """
                    )
                )
            ).one()
            assert scope_state.status == "ENABLED"
            assert scope_state.current_bundle_id is not None
            assert scope_state.lifecycle_state == "ACTIVE"
            assert scope_state.state == "ACTIVE"
            assert scope_state.enabled
            assert scope_state.stream_status == "ACTIVE"
            assert scope_state.paused_reason is None
            assert scope_state.schedule_status == "ACTIVE"
            assert scope_state.connector_enabled
            assert set(scope_state.industries) == {"BRIDGE"}
            assert set(scope_state.content_domains) == {"STANDARD_GUIDANCE"}
            assert set(scope_state.language_tags) == {"zh-CN", "en"}

            # Simulate an administrator changing the authorization boundary; the
            # next authoritative discovery must fail closed, unlike label union.
            await connection.execute(
                text(
                    """
                    UPDATE source_candidate
                       SET authorization_boundary='obsolete.example.test',
                           material_fingerprint=encode(digest(convert_to(
                             canonical_url || chr(10) || 'obsolete.example.test','UTF8'
                           ),'sha256'),'hex')
                     WHERE id='019b1800-0000-7000-8000-00000000e120'
                    """
                )
            )
            await connection.execute(text("SET LOCAL ROLE srbg_worker_role"))
            assert (
                await connection.scalar(
                    text(
                        """
                    SELECT register_discovered_source_candidate(
                      '019b1800-0000-7000-8000-00000000e160',
                      '019b1800-0000-7000-8000-00000000e161',
                      'https://new-source.example.test/',
                      encode(digest(convert_to(
                        'https://new-source.example.test/','UTF8'
                      ),'sha256'),'hex'),
                      'new-source.example.test',repeat('c',64),'MANUAL',
                      'manual-submission:round18-governance-change',
                      ARRAY['BRIDGE']::text[],ARRAY['STANDARD_GUIDANCE']::text[],
                      ARRAY['zh-CN','en'],
                      '019b1800-0000-7000-8000-00000000e901',
                      'restore changed governance boundary and fail closed',
                      'round18-governance-change',
                      '019b1800-0000-7000-8000-00000000e162',now()
                    )
                    """
                    )
                )
                == same_candidate
            )
            await connection.execute(text("RESET ROLE"))
            paused = (
                await connection.execute(
                    text(
                        """
                        SELECT candidate.status,candidate.occurrence_count,
                               candidate.material_fingerprint,candidate.current_bundle_id,
                               candidate.industries,candidate.content_domains,
                               candidate.language_tags,
                               source_row.lifecycle_state,source_row.current_policy_version_id,
                               stream.status AS stream_status,stream.paused_reason,
                               schedule.status AS schedule_status,
                               connector.enabled AS connector_enabled,
                               source_policy_compliance_current(
                                 source_row.id,source_row.current_policy_version_id,now()
                               ) AS policy_current,
                               (SELECT count(*) FROM source_qualification_run run
                                 WHERE run.candidate_id=candidate.id) AS qualification_runs
                          FROM source_candidate candidate
                          JOIN source source_row ON source_row.id=candidate.source_id
                          JOIN source_stream stream ON stream.source_id=source_row.id
                          JOIN fetch_schedule schedule ON schedule.source_id=source_row.id
                          JOIN source_connector connector ON connector.source_id=source_row.id
                         WHERE candidate.id='019b1800-0000-7000-8000-00000000e120'
                        """
                    )
                )
            ).one()
            production_policy_id = paused.current_policy_version_id
            assert paused.status == "STALE"
            assert paused.occurrence_count == 4
            assert paused.material_fingerprint == governance_fingerprint
            assert paused.current_bundle_id is None
            assert set(paused.industries) == {"BRIDGE"}
            assert set(paused.content_domains) == {"STANDARD_GUIDANCE"}
            assert set(paused.language_tags) == {"zh-CN", "en"}
            assert paused.lifecycle_state == "PAUSED"
            assert paused.stream_status == "PAUSED"
            assert paused.paused_reason == "SOURCE_MATERIAL_CHANGED"
            assert paused.schedule_status == "PAUSED"
            assert not paused.connector_enabled
            assert not paused.policy_current
            assert paused.qualification_runs == 1
            assert await connection.scalar(
                text(
                    """
                    SELECT count(*)=1 FROM source_lifecycle_event event
                    JOIN source_candidate candidate ON candidate.source_id=event.source_id
                     WHERE candidate.id='019b1800-0000-7000-8000-00000000e120'
                       AND event.reason_code='SOURCE_MATERIAL_CHANGED'
                       AND event.to_state='PAUSED'
                    """
                )
            )

            await connection.execute(text("SET LOCAL ROLE srbg_worker_role"))
            requalification_id = await connection.scalar(
                text(
                    """
                    SELECT request_automated_source_qualification(
                      '019b1800-0000-7000-8000-00000000e153',
                      '019b1800-0000-7000-8000-00000000e120',
                      'source-qualification-v1',
                      '019b1800-0000-7000-8000-00000000e901',
                      'requalify source after governance boundary change',
                      'round18-governance-change-qualification',
                      '019b1800-0000-7000-8000-00000000e154',now()
                    )
                    """
                )
            )
            assert str(requalification_id) == "019b1800-0000-7000-8000-00000000e153"
            await connection.execute(text("RESET ROLE"))
            requalifying = (
                await connection.execute(
                    text(
                        """
                        SELECT candidate.status,source_row.lifecycle_state,
                               source_row.current_policy_version_id,policy.status AS policy_status,
                               schedule.status AS schedule_status,source_row.industries,
                               source_row.content_domains,source_row.language_tags
                          FROM source_candidate candidate
                          JOIN source source_row ON source_row.id=candidate.source_id
                          JOIN source_policy_version policy
                            ON policy.id=source_row.current_policy_version_id
                          JOIN fetch_schedule schedule ON schedule.source_id=source_row.id
                         WHERE candidate.id='019b1800-0000-7000-8000-00000000e120'
                        """
                    )
                )
            ).one()
            assert requalifying.status == "QUALIFYING"
            assert requalifying.lifecycle_state == "PAUSED"
            assert requalifying.current_policy_version_id != production_policy_id
            assert requalifying.policy_status == "PENDING_REVIEW"
            assert requalifying.schedule_status == "PAUSED"
            assert set(requalifying.industries) == {"BRIDGE"}
            assert set(requalifying.content_domains) == {"STANDARD_GUIDANCE"}
            assert set(requalifying.language_tags) == {"zh-CN", "en"}
    finally:
        await engine.dispose()


async def _assert_round17_runtime_restored(database_url: str) -> None:
    engine = create_async_engine(database_url)
    try:
        async with engine.connect() as connection:
            assert await connection.scalar(
                text("SELECT to_regclass('public.source_candidate') IS NULL")
            )
            assert await connection.scalar(
                text(
                    """
                    SELECT position(
                      'source_policy_compliance_current' IN
                      pg_get_functiondef(
                        'claim_due_fetch_schedule(timestamptz,timestamptz,uuid)'::regprocedure
                      )
                    )=0
                    """
                )
            )
            assert await connection.scalar(
                text(
                    """
                    SELECT to_regprocedure(
                      'record_scheduled_source_raw_round17(
                        uuid,uuid,uuid,uuid,text,text,text,text,bigint,text,text,text,
                        text,text,text,jsonb,integer,text,text,timestamptz
                      )'
                    ) IS NULL
                    """
                )
            )
    finally:
        await engine.dispose()


async def _assert_worker_discovery_gateway(database_url: str) -> None:
    from srbg_worker.source_discovery import (
        PostgresDiscoveryGateway,
        VerifiedDiscoveryTarget,
        _target_evidence_ref,
    )

    role_engine = create_async_engine(
        database_url,
        connect_args={"server_settings": {"role": "srbg_worker_role"}},
    )
    target = VerifiedDiscoveryTarget(
        canonical_url="https://gateway-source.example.test/",
        authorization_boundary="gateway-source.example.test",
        response_sha256="a" * 64,
        material_fingerprint="b" * 64,
    )
    industries = ("HIGHWAY",)
    content_domains = ("SAFETY_REGULATION",)
    evidence_ref = _target_evidence_ref(
        target,
        industries=industries,
        content_domains=content_domains,
    )
    expanded_industries = ("HIGHWAY", "BRIDGE")
    expanded_evidence_ref = _target_evidence_ref(
        target,
        industries=expanded_industries,
        content_domains=content_domains,
    )
    gateway = PostgresDiscoveryGateway(role_engine)
    now = datetime.now(UTC)
    try:
        first = await gateway.register_and_request(
            target,
            discovery_channel="DIRECTORY",
            industries=industries,
            content_domains=content_domains,
            evidence_ref=evidence_ref,
            discovery_run_id=UUID("019b1800-0000-7000-8000-00000000ea01"),
            now=now,
        )
        duplicate = await gateway.register_and_request(
            target,
            discovery_channel="DIRECTORY",
            industries=industries,
            content_domains=content_domains,
            evidence_ref=evidence_ref,
            discovery_run_id=UUID("019b1800-0000-7000-8000-00000000ea02"),
            now=now,
        )
        expanded = await gateway.register_and_request(
            target,
            discovery_channel="DIRECTORY",
            industries=expanded_industries,
            content_domains=content_domains,
            evidence_ref=expanded_evidence_ref,
            discovery_run_id=UUID("019b1800-0000-7000-8000-00000000ea03"),
            now=now,
        )
    finally:
        await gateway.close()

    assert first.created
    assert first.qualification_run_id is not None
    assert duplicate.candidate_id == first.candidate_id
    assert duplicate.qualification_run_id is None
    assert not duplicate.created
    assert expanded.candidate_id == first.candidate_id
    assert expanded.qualification_run_id is not None
    assert expanded.qualification_run_id != first.qualification_run_id
    assert not expanded.created

    engine = create_async_engine(database_url)
    try:
        with pytest.raises(DBAPIError, match="source candidate discovery input is invalid"):
            async with engine.begin() as connection:
                await connection.execute(text("SET LOCAL ROLE srbg_worker_role"))
                await connection.execute(
                    text(
                        """
                        SELECT register_discovered_source_candidate(
                          '019b1800-0000-7000-8000-00000000eb01',
                          '019b1800-0000-7000-8000-00000000eb02',
                          'https://out-of-scope.example.test/',
                          encode(digest(convert_to(
                            'https://out-of-scope.example.test/','UTF8'
                          ),'sha256'),'hex'),
                          'out-of-scope.example.test',repeat('e',64),'DIRECTORY',
                          'target-fetch:out-of-scope',ARRAY['TENDER'],
                          ARRAY['SAFETY_REGULATION'],ARRAY['zh-CN'],
                          '019b1800-0000-7000-8000-00000000e901',
                          'reject out of scope discovery classification',
                          'round18-out-of-scope',
                          '019b1800-0000-7000-8000-00000000eb03',now()
                        )
                        """
                    )
                )
        async with engine.begin() as connection:
            await connection.execute(text("SET LOCAL ROLE srbg_worker_role"))
            pending_ids = (
                (
                    await connection.execute(
                        text(
                            "SELECT qualification_run_id FROM "
                            "list_pending_source_qualification_ids(now(),100)"
                        )
                    )
                )
                .scalars()
                .all()
            )
            assert expanded.qualification_run_id in pending_ids
            binding = (
                await connection.execute(
                    text(
                        """
                        SELECT * FROM acquire_source_qualification(
                          :run_id,'019b1800-0000-7000-8000-00000000ec01',
                          now(),now()+interval '5 minutes'
                        )
                        """
                    ),
                    {"run_id": expanded.qualification_run_id},
                )
            ).one()
            assert binding.candidate_id == first.candidate_id
            capture_id = await connection.scalar(
                text(
                    """
                    SELECT record_source_qualification_capture(
                      '019b1800-0000-7000-8000-00000000ec02',:run_id,:candidate_id,
                      '019b1800-0000-7000-8000-00000000ec01','TARGET_PAGE',
                      'https://gateway-source.example.test/',
                      'https://gateway-source.example.test/',
                      'qualification/sha256/11/' || repeat('1',64),repeat('1',64),
                      repeat('2',64),128,200,'text/html',now()
                    )
                    """
                ),
                {
                    "run_id": expanded.qualification_run_id,
                    "candidate_id": first.candidate_id,
                },
            )
            assert str(capture_id) == "019b1800-0000-7000-8000-00000000ec02"
            bundle_id = await connection.scalar(
                text(
                    """
                    SELECT complete_source_qualification(
                      '019b1800-0000-7000-8000-00000000ec03',
                      CAST(:run_id AS uuid),CAST(:candidate_id AS uuid),
                      '019b1800-0000-7000-8000-00000000ec01',
                      'source-qualification-v1',:expected_fingerprint,
                      encode(digest(convert_to(
                        'https://gateway-source.example.test/' || chr(10) ||
                        'gateway-source.example.test' || chr(10) || repeat('2',64),
                        'UTF8'
                      ),'sha256'),'hex'),
                      'QUALIFIED','RAW_EVIDENCE_ALLOWED','PRIVATE_RAW_ALLOWED',
                      jsonb_build_array(jsonb_build_object(
                        'code','SHARED_POLICY_EVALUATION','level','PASS',
                        'message','Shared source qualification policy evaluated ' ||
                                  'direct target evidence.',
                        'evidence_refs',jsonb_build_array(
                          'qualification-run:' || CAST(:run_id AS text)
                        ),'observed_at',now()
                      )),ARRAY[]::text[],1,1,
                      now(),now()+interval '7 days'
                    )
                    """
                ),
                {
                    "run_id": expanded.qualification_run_id,
                    "candidate_id": first.candidate_id,
                    "expected_fingerprint": binding.material_fingerprint,
                },
            )
            assert str(bundle_id) == "019b1800-0000-7000-8000-00000000ec03"
            budget = (
                await connection.execute(
                    text(
                        """
                        SELECT * FROM reserve_source_provider_usage(
                          'BAIDU_SEARCH',to_char(now() AT TIME ZONE 'UTC','YYYY-MM'),now()
                        )
                        """
                    )
                )
            ).one()
            assert budget.request_count == 1
            assert budget.cost_micrormb == 0
            assert not budget.alert_required
        async with engine.connect() as connection:
            counts = (
                await connection.execute(
                    text(
                        """
                        SELECT candidate.occurrence_count,candidate.status,
                               candidate.current_bundle_id,candidate.material_fingerprint,
                               candidate.industries,
                               count(DISTINCT occurrence.id) AS occurrence_rows,
                               count(DISTINCT run.id) AS qualification_runs,
                               count(DISTINCT run.id) FILTER (
                                 WHERE run.status='CANCELLED'
                               ) AS cancelled_runs,
                               count(DISTINCT run.id) FILTER (
                                 WHERE run.status='PENDING'
                               ) AS pending_runs
                          FROM source_candidate candidate
                          JOIN source_candidate_occurrence occurrence
                            ON occurrence.candidate_id=candidate.id
                          JOIN source_qualification_run run
                            ON run.candidate_id=candidate.id
                         WHERE candidate.id=:candidate_id
                         GROUP BY candidate.occurrence_count,candidate.status,
                                  candidate.current_bundle_id,
                                  candidate.material_fingerprint,candidate.industries
                        """
                    ),
                    {"candidate_id": first.candidate_id},
                )
            ).one()
            assert counts.occurrence_count == 2
            assert counts.status == "READY_FOR_DECISION"
            assert str(counts.current_bundle_id) == ("019b1800-0000-7000-8000-00000000ec03")
            assert counts.material_fingerprint == await connection.scalar(
                text(
                    """
                    SELECT encode(digest(convert_to(
                      canonical_url || chr(10) || authorization_boundary,'UTF8'
                    ),'sha256'),'hex')
                      FROM source_candidate WHERE id=:candidate_id
                    """
                ),
                {"candidate_id": first.candidate_id},
            )
            assert set(counts.industries) == {"HIGHWAY", "BRIDGE"}
            assert counts.occurrence_rows == 2
            assert counts.qualification_runs == 2
            assert counts.cancelled_runs == 1
            assert counts.pending_runs == 0
            assert await connection.scalar(
                text(
                    """
                    SELECT bundle.material_fingerprint=candidate.material_fingerprint
                      FROM source_candidate candidate
                      JOIN source_qualification_bundle bundle
                        ON bundle.id=candidate.current_bundle_id
                     WHERE candidate.id=:candidate_id
                    """
                ),
                {"candidate_id": first.candidate_id},
            )
            assert not await connection.scalar(
                text(
                    "SELECT EXISTS(SELECT 1 FROM source_candidate "
                    "WHERE canonical_url='https://out-of-scope.example.test/')"
                )
            )
    finally:
        await engine.dispose()


async def _seed_round18_activation_fixture(database_url: str) -> None:
    statements = (
        "SET LOCAL ROLE srbg_worker_role",
        """
        SELECT register_discovered_source_candidate(
          '019b1800-0000-7000-8000-00000000e120'::uuid,
          '019b1800-0000-7000-8000-00000000e123'::uuid,
          'https://new-source.example.test/',
          encode(digest(convert_to('https://new-source.example.test/','UTF8'),'sha256'),'hex'),
          'new-source.example.test',repeat('c',64),'MANUAL',
          'manual-submission:round18-replay',ARRAY[]::text[],ARRAY[]::text[],
          ARRAY['zh-CN'],
          '019b1800-0000-7000-8000-00000000e901'::uuid,
          'register source in disposable migration replay','round18-replay-register',
          '019b1800-0000-7000-8000-00000000e137'::uuid,now()
        )
        """,
        """
        SELECT request_automated_source_qualification(
          '019b1800-0000-7000-8000-00000000e121'::uuid,
          '019b1800-0000-7000-8000-00000000e120'::uuid,
          'source-qualification-v1','019b1800-0000-7000-8000-00000000e901'::uuid,
          'qualify source in disposable migration replay','round18-replay-qualification',
          '019b1800-0000-7000-8000-00000000e138'::uuid,now()
        )
        """,
        "RESET ROLE",
        """
        UPDATE source_qualification_run
           SET status='SUCCEEDED',started_at=created_at,completed_at=now()
         WHERE id='019b1800-0000-7000-8000-00000000e121'
        """,
        """
        INSERT INTO source_qualification_bundle(
          id,candidate_id,run_id,rule_version,material_fingerprint,verdict,
          storage_policy,evidence_capture_policy,checks,reason_codes,
          sampled_item_count,relevant_item_count,bundle_sha256,evaluated_by,
          prepared_source_id,prepared_policy_version_id,
          prepared_connector_config_version_id,prepared_trial_run_id,created_at,valid_until
        ) SELECT
          '019b1800-0000-7000-8000-00000000e122',
          '019b1800-0000-7000-8000-00000000e120',
          '019b1800-0000-7000-8000-00000000e121','source-qualification-v1',
          candidate.material_fingerprint,'QUALIFIED',
          'RAW_EVIDENCE_ALLOWED','PRIVATE_RAW_ALLOWED',
          '[]'::jsonb,ARRAY[]::text[],5,5,repeat('d',64),
          '019b1800-0000-7000-8000-00000000e901',candidate.source_id,
          source_row.current_policy_version_id,
          source_row.current_connector_config_version_id,
          source_row.current_trial_run_id,now(),now()+interval '7 days'
          FROM source_candidate candidate
          JOIN source source_row ON source_row.id=candidate.source_id
         WHERE candidate.id='019b1800-0000-7000-8000-00000000e120'
        """,
        """
        UPDATE source_candidate
           SET status='READY_FOR_DECISION',
               current_bundle_id='019b1800-0000-7000-8000-00000000e122',
               updated_at=now()
         WHERE id='019b1800-0000-7000-8000-00000000e120'
        """,
    )
    engine = create_async_engine(database_url)
    try:
        async with engine.begin() as connection:
            for statement in statements:
                await connection.execute(text(statement))
            prepared = (
                await connection.execute(
                    text(
                        """
                        SELECT candidate.source_id,source_row.current_policy_version_id,
                               source_row.current_connector_config_version_id,
                               source_row.current_trial_run_id,source_row.lifecycle_state,
                               policy.status AS policy_status,policy.document AS policy_document,
                               schedule.status AS schedule_status,
                               occurrence.campaign_id,connector.enabled AS connector_enabled
                          FROM source_candidate candidate
                          JOIN source source_row ON source_row.id=candidate.source_id
                          JOIN source_policy_version policy
                            ON policy.id=source_row.current_policy_version_id
                          JOIN fetch_schedule schedule ON schedule.source_id=source_row.id
                          JOIN source_connector connector ON connector.source_id=source_row.id
                          JOIN source_candidate_occurrence occurrence
                            ON occurrence.candidate_id=candidate.id
                         WHERE candidate.id='019b1800-0000-7000-8000-00000000e120'
                        """
                    )
                )
            ).one()
            assert prepared.source_id is not None
            assert prepared.current_policy_version_id is not None
            assert prepared.current_connector_config_version_id is not None
            assert prepared.current_trial_run_id is not None
            assert prepared.lifecycle_state == "CANDIDATE"
            assert prepared.policy_status == "PENDING_REVIEW"
            assert prepared.policy_document["storage_policy"] == "LINK_ONLY"
            assert prepared.policy_document["evidence_capture_policy"] == "PRIVATE_RAW_ALLOWED"
            assert prepared.policy_document["qualification_evidence"] == {
                "isolation_namespace": "qualification/sha256/",
                "purpose": "qualification_only",
                "retention_days": 30,
                "promotion_allowed": False,
            }
            assert not prepared.policy_document["automatic_publication"]
            assert prepared.schedule_status == "PAUSED"
            assert prepared.campaign_id is None
            assert not prepared.connector_enabled
            assert not await connection.scalar(
                text(
                    """
                    SELECT EXISTS(
                      SELECT 1 FROM source_trial_run_result result
                      JOIN source source_row ON source_row.current_trial_run_id=result.trial_run_id
                      JOIN source_candidate candidate ON candidate.source_id=source_row.id
                     WHERE candidate.id='019b1800-0000-7000-8000-00000000e120'
                    )
                    """
                )
            )
    finally:
        await engine.dispose()


async def _assert_qualified_candidate_activation(database_url: str) -> None:
    engine = create_async_engine(database_url)
    try:
        async with engine.begin() as connection:
            await connection.execute(text("SET LOCAL ROLE srbg_api_role"))
            activation = (
                await connection.execute(
                    text(
                        """
                        SELECT * FROM activate_qualified_candidate(
                          '019b1800-0000-7000-8000-00000000e120'::uuid,
                          'ENABLE',repeat('d',64),repeat('e',64),'round18-replay-enable',
                          'enable qualified source in disposable migration replay',NULL,
                          '019b1800-0000-7000-8000-00000000e900'::uuid,
                          '019b1800-0000-7000-8000-00000000e130'::uuid,
                          '019b1800-0000-7000-8000-00000000e131'::uuid,
                          '019b1800-0000-7000-8000-00000000e132'::uuid,
                          '019b1800-0000-7000-8000-00000000e133'::uuid,
                          '019b1800-0000-7000-8000-00000000e134'::uuid,
                          '019b1800-0000-7000-8000-00000000e135'::uuid,
                          '019b1800-0000-7000-8000-00000000e136'::uuid,now()
                        )
                        """
                    )
                )
            ).one()
            assert str(activation.decision_id) == "019b1800-0000-7000-8000-00000000e130"
            assert activation.source_id == await connection.scalar(
                text(
                    "SELECT source_id FROM source_candidate "
                    "WHERE id='019b1800-0000-7000-8000-00000000e120'::uuid"
                )
            )
            assert str(activation.outbox_id) == "019b1800-0000-7000-8000-00000000e134"
            assert activation.candidate_status == "ENABLED"

        async with engine.connect() as connection:
            stream = (
                await connection.execute(
                    text(
                        """
                        SELECT stream.candidate_id,stream.schedule_id,stream.rule_version,
                               stream.status,schedule.id AS runtime_schedule_id,
                                   schedule.status AS schedule_status,
                                   source_row.id AS source_id,
                                   source_row.lifecycle_state,source_row.state,
                                   source_row.enabled,source_row.governance_owner_id,
                                   source_row.current_trial_run_id,
                               source_row.current_policy_version_id,
                               source_row.current_connector_config_version_id,
                               bundle.prepared_policy_version_id,
                               policy.document AS policy_document,
                               policy.valid_until AS policy_valid_until,
                               connector.enabled AS connector_enabled,
                                   source_policy_compliance_current(
                                     source_row.id,policy.id,now()
                                   ) AS policy_current,
                                   source_v2_policy_compliance_approved(
                                     source_row.id,policy.id,now()
                                   ) AS legacy_compliance_current,
                                   policy.document#>>'{robots_review,result}' AS robots_result,
                                   policy.document#>>'{terms_review,result}' AS terms_result,
                                   policy.document#>>'{copyright_review,result}' AS copyright_result
                          FROM source_candidate candidate
                          JOIN source source_row ON source_row.id=candidate.source_id
                          JOIN source_stream stream
                            ON stream.source_id=source_row.id
                           AND stream.candidate_id=candidate.id
                          JOIN fetch_schedule schedule ON schedule.source_id=source_row.id
                          JOIN source_policy_version policy
                            ON policy.id=source_row.current_policy_version_id
                          JOIN source_connector connector ON connector.source_id=source_row.id
                          JOIN source_qualification_bundle bundle
                            ON bundle.id=candidate.current_bundle_id
                         WHERE candidate.id='019b1800-0000-7000-8000-00000000e120'::uuid
                        """
                    )
                )
            ).one()
            assert str(stream.candidate_id) == "019b1800-0000-7000-8000-00000000e120"
            assert stream.schedule_id == stream.runtime_schedule_id
            assert stream.rule_version == "source-qualification-v1"
            assert stream.status == "ACTIVE"
            assert stream.schedule_status == "ACTIVE"
            assert stream.lifecycle_state == "ACTIVE"
            assert stream.state == "ACTIVE"
            assert stream.enabled
            assert stream.governance_owner_id is not None
            assert stream.connector_enabled
            assert stream.policy_current
            assert stream.legacy_compliance_current
            assert stream.robots_result == "ALLOWED"
            assert stream.terms_result == "ALLOWED"
            assert stream.copyright_result == "ALLOWED"
            assert stream.current_policy_version_id != stream.prepared_policy_version_id
            assert (
                stream.policy_document["qualification_bundle_id"]
                == "019b1800-0000-7000-8000-00000000e122"
            )
            assert stream.policy_document["storage_policy"] == "RAW_EVIDENCE_ALLOWED"
            assert stream.policy_document["evidence_capture_policy"] == "PRIVATE_RAW_ALLOWED"
            assert stream.policy_valid_until > datetime.now(UTC).replace(microsecond=0) + timedelta(
                days=364
            )
            assert await connection.scalar(
                text(
                    """
                    SELECT EXISTS(
                      SELECT 1 FROM source_trial_run_result
                       WHERE trial_run_id=:trial_run_id
                    )
                    """
                ),
                {"trial_run_id": stream.current_trial_run_id},
            )

        async with engine.begin() as connection:
            await connection.execute(text("SET LOCAL ROLE srbg_api_role"))
            paused_state = await connection.scalar(
                text(
                    """
                    SELECT apply_source_lifecycle_command(
                      :source_id,'PAUSE',
                      '019b1800-0000-7000-8000-00000000e900',
                      'pause automated source in lifecycle projection replay',
                      'round18-lifecycle-pause',
                      '019b1800-0000-7000-8000-00000000ee01',now()
                    )
                    """
                ),
                {"source_id": stream.source_id},
            )
            assert paused_state == "PAUSED"
            paused_projection = (
                await connection.execute(
                    text(
                        """
                        SELECT lifecycle_state,state,enabled
                          FROM source WHERE id=:source_id
                        """
                    ),
                    {"source_id": stream.source_id},
                )
            ).one()
            assert paused_projection.lifecycle_state == "PAUSED"
            assert paused_projection.state == "CANDIDATE"
            assert not paused_projection.enabled
            resumed_state = await connection.scalar(
                text(
                    """
                    SELECT apply_source_lifecycle_command(
                      :source_id,'RESUME',
                      '019b1800-0000-7000-8000-00000000e900',
                      'resume automated source with current authority replay',
                      'round18-lifecycle-resume',
                      '019b1800-0000-7000-8000-00000000ee02',now()
                    )
                    """
                ),
                {"source_id": stream.source_id},
            )
            assert resumed_state == "ACTIVE"
            resumed_projection = (
                await connection.execute(
                    text("SELECT lifecycle_state,state,enabled FROM source WHERE id=:source_id"),
                    {"source_id": stream.source_id},
                )
            ).one()
            assert resumed_projection.lifecycle_state == "ACTIVE"
            assert resumed_projection.state == "ACTIVE"
            assert resumed_projection.enabled

        async with engine.connect() as connection:
            transaction = await connection.begin()
            try:
                await connection.execute(text("SET LOCAL ROLE srbg_api_role"))
                await connection.execute(
                    text(
                        """
                        SELECT apply_source_lifecycle_command(
                          :source_id,'PAUSE',
                          '019b1800-0000-7000-8000-00000000e900',
                          'pause before stale governance resume replay',
                          'round18-lifecycle-stale-pause',
                          '019b1800-0000-7000-8000-00000000ee03',now()
                        )
                        """
                    ),
                    {"source_id": stream.source_id},
                )
                await connection.execute(text("RESET ROLE"))
                await connection.execute(
                    text("UPDATE source_candidate SET status='STALE' WHERE source_id=:source_id"),
                    {"source_id": stream.source_id},
                )
                await connection.execute(text("SET LOCAL ROLE srbg_api_role"))
                with pytest.raises(DBAPIError):
                    await connection.execute(
                        text(
                            """
                            SELECT apply_source_lifecycle_command(
                              :source_id,'RESUME',
                              '019b1800-0000-7000-8000-00000000e900',
                              'stale governance must not resume replay',
                              'round18-lifecycle-stale-resume',
                              '019b1800-0000-7000-8000-00000000ee04',now()
                            )
                            """
                        ),
                        {"source_id": stream.source_id},
                    )
            finally:
                await transaction.rollback()
            assert await connection.scalar(
                text(
                    """
                    SELECT count(*)=1 FROM source_activation_outbox
                     WHERE id='019b1800-0000-7000-8000-00000000e134'::uuid
                       AND status='PENDING' AND event_type='PRODUCTION_REFETCH'
                    """
                )
            )
            assert await connection.scalar(
                text(
                    """
                    SELECT EXISTS(
                      SELECT 1
                        FROM source_activation_outbox activation
                        JOIN source source_row ON source_row.id=activation.source_id
                        JOIN source_stream stream ON stream.id=activation.stream_id
                        JOIN fetch_schedule schedule ON schedule.source_id=source_row.id
                        JOIN source_policy_version policy
                          ON policy.id=source_row.current_policy_version_id
                        JOIN connector_config_version config
                          ON config.id=source_row.current_connector_config_version_id
                        JOIN source_connector connector ON connector.source_id=source_row.id
                       WHERE activation.id='019b1800-0000-7000-8000-00000000e134'::uuid
                         AND source_row.lifecycle_state='ACTIVE'
                         AND stream.status='ACTIVE' AND schedule.status='ACTIVE'
                         AND connector.enabled AND config.validation_status='VALID'
                         AND source_policy_compliance_current(source_row.id,policy.id,now())
                         AND EXISTS(
                           SELECT 1 FROM source_governance_decision decision
                            WHERE decision.source_id=source_row.id
                              AND decision.policy_version_id=policy.id
                              AND decision.connector_config_version_id=config.id
                              AND decision.trial_run_id=source_row.current_trial_run_id
                              AND decision.decision_type='PRODUCTION_APPROVAL'
                              AND decision.outcome='APPROVED'
                         )
                    )
                    """
                )
            )

        async with engine.connect() as connection:
            transaction = await connection.begin()
            try:
                await connection.execute(text("SET LOCAL ROLE srbg_worker_role"))
                assert (
                    UUID("019b1800-0000-7000-8000-00000000e134")
                    in (
                        await connection.execute(
                            text(
                                "SELECT outbox_id FROM "
                                "list_pending_source_activation_ids(now(),100)"
                            )
                        )
                    )
                    .scalars()
                    .all()
                )
                dispatch = (
                    await connection.execute(
                        text(
                            """
                            SELECT * FROM prepare_source_activation(
                              '019b1800-0000-7000-8000-00000000e134',
                              '019b1800-0000-7000-8000-00000000ed01',
                              now(),now()+interval '5 minutes'
                            )
                            """
                        )
                    )
                ).one()
                assert dispatch.needs_dispatch
                assert str(dispatch.fetch_run_id) == ("019b1800-0000-7000-8000-00000000ed01")
                completed_outbox = await connection.scalar(
                    text(
                        """
                        SELECT complete_source_activation(
                          '019b1800-0000-7000-8000-00000000e134',
                          '019b1800-0000-7000-8000-00000000ed01',
                          :source_id,now()
                        )
                        """
                    ),
                    {"source_id": dispatch.source_id},
                )
                assert str(completed_outbox) == ("019b1800-0000-7000-8000-00000000e134")
            finally:
                await transaction.rollback()

        async with engine.connect() as connection:
            transaction = await connection.begin()
            try:
                production = (
                    await connection.execute(
                        text(
                            """
                            SELECT candidate.current_bundle_id,
                                   source_row.current_policy_version_id,
                                   source_row.current_connector_config_version_id,
                                   source_row.current_trial_run_id
                              FROM source_candidate candidate
                              JOIN source source_row ON source_row.id=candidate.source_id
                             WHERE candidate.id=
                               '019b1800-0000-7000-8000-00000000e120'
                            """
                        )
                    )
                ).one()
                # Fixture-only clock compression: the production policy table is
                # immutable in normal operation, so disable its owner trigger only
                # inside this rollback-only transaction.
                await connection.execute(
                    text("ALTER TABLE source_policy_version DISABLE TRIGGER USER")
                )
                await connection.execute(
                    text(
                        """
                        UPDATE source_policy_version policy
                           SET valid_until=now()+interval '29 days'
                          FROM source source_row
                          JOIN source_candidate candidate
                            ON candidate.source_id=source_row.id
                         WHERE policy.id=source_row.current_policy_version_id
                           AND candidate.id='019b1800-0000-7000-8000-00000000e120'
                        """
                    )
                )
                await connection.execute(
                    text("ALTER TABLE source_policy_version ENABLE TRIGGER USER")
                )
                await connection.execute(text("SET LOCAL ROLE srbg_worker_role"))
                annual_runs = (
                    (
                        await connection.execute(
                            text(
                                "SELECT qualification_run_id FROM "
                                "list_pending_source_qualification_ids(now(),100)"
                            )
                        )
                    )
                    .scalars()
                    .all()
                )
                assert len(annual_runs) == 1
                await connection.execute(text("RESET ROLE"))
                annual_state = (
                    await connection.execute(
                        text(
                            """
                            SELECT candidate.status,candidate.current_bundle_id,
                                   source_row.lifecycle_state,source_row.state,
                                   source_row.enabled,
                                   source_row.current_policy_version_id,
                                   source_row.current_connector_config_version_id,
                                   source_row.current_trial_run_id,
                                   stream.status AS stream_status,stream.paused_reason,
                                   schedule.status AS schedule_status,
                                   connector.enabled AS connector_enabled,
                                   run.qualification_mode,
                                   run.renewal_of_policy_version_id,
                                   run.prepared_policy_version_id,
                                   run.prepared_connector_config_version_id,
                                   run.prepared_trial_run_id,
                                   prepared_policy.status AS prepared_policy_status
                              FROM source_candidate candidate
                              JOIN source source_row ON source_row.id=candidate.source_id
                              JOIN source_stream stream ON stream.source_id=source_row.id
                              JOIN fetch_schedule schedule ON schedule.source_id=source_row.id
                              JOIN source_connector connector
                                ON connector.source_id=source_row.id
                              JOIN source_qualification_run run
                                ON run.candidate_id=candidate.id
                               AND run.qualification_mode='SHADOW_RENEWAL'
                              JOIN source_policy_version prepared_policy
                                ON prepared_policy.id=run.prepared_policy_version_id
                             WHERE candidate.id=
                               '019b1800-0000-7000-8000-00000000e120'
                            """
                        )
                    )
                ).one()
                assert annual_state.status == "ENABLED"
                assert annual_state.current_bundle_id == production.current_bundle_id
                assert annual_state.lifecycle_state == "ACTIVE"
                assert annual_state.state == "ACTIVE"
                assert annual_state.enabled
                assert annual_state.stream_status == "ACTIVE"
                assert annual_state.paused_reason is None
                assert annual_state.schedule_status == "ACTIVE"
                assert annual_state.connector_enabled
                assert annual_state.qualification_mode == "SHADOW_RENEWAL"
                assert (
                    annual_state.renewal_of_policy_version_id
                    == production.current_policy_version_id
                )
                assert (
                    annual_state.current_policy_version_id == production.current_policy_version_id
                )
                assert (
                    annual_state.current_connector_config_version_id
                    == production.current_connector_config_version_id
                )
                assert annual_state.current_trial_run_id == production.current_trial_run_id
                assert (
                    annual_state.prepared_policy_version_id != production.current_policy_version_id
                )
                assert (
                    annual_state.prepared_connector_config_version_id
                    != production.current_connector_config_version_id
                )
                assert annual_state.prepared_trial_run_id != production.current_trial_run_id
                assert annual_state.prepared_policy_status == "PENDING_REVIEW"
                await connection.execute(text("SET LOCAL ROLE srbg_worker_role"))
                shadow_binding = (
                    await connection.execute(
                        text(
                            """
                            SELECT * FROM acquire_source_qualification(
                              CAST(:run_id AS uuid),
                              '019b1800-0000-7000-8000-00000000e291',
                              now(),now()+interval '5 minutes'
                            )
                            """
                        ),
                        {"run_id": annual_runs[0]},
                    )
                ).one()
                assert (
                    shadow_binding.prepared_policy_version_id
                    == annual_state.prepared_policy_version_id
                )
                await connection.execute(
                    text(
                        """
                        SELECT record_source_qualification_capture(
                          '019b1800-0000-7000-8000-00000000e292',
                          CAST(:run_id AS uuid),
                          '019b1800-0000-7000-8000-00000000e120',
                          '019b1800-0000-7000-8000-00000000e291','TARGET_PAGE',
                          'https://new-source.example.test/',
                          'https://new-source.example.test/',
                          'qualification/sha256/33/' || repeat('3',64),
                          repeat('3',64),repeat('4',64),256,200,'text/html',now()
                        )
                        """
                    ),
                    {"run_id": annual_runs[0]},
                )
                shadow_bundle_id = await connection.scalar(
                    text(
                        """
                        SELECT complete_source_qualification(
                          '019b1800-0000-7000-8000-00000000e293',
                          CAST(:run_id AS uuid),
                          '019b1800-0000-7000-8000-00000000e120',
                          '019b1800-0000-7000-8000-00000000e291',
                          'source-qualification-v1',:expected_fingerprint,
                          encode(digest(convert_to(
                            'https://new-source.example.test/' || chr(10) ||
                            'new-source.example.test' || chr(10) || repeat('4',64),
                            'UTF8'
                          ),'sha256'),'hex'),
                          'QUALIFIED','RAW_EVIDENCE_ALLOWED','PRIVATE_RAW_ALLOWED',
                          jsonb_build_array(jsonb_build_object(
                            'code','SHADOW_POLICY_EVALUATION','level','PASS',
                            'message','Shadow qualification completed without ' ||
                                      'changing production authority.',
                            'evidence_refs',jsonb_build_array(
                              'qualification-run:' || CAST(:run_id AS text)
                            ),'observed_at',now()
                          )),ARRAY[]::text[],1,1,now(),now()+interval '7 days'
                        )
                        """
                    ),
                    {
                        "run_id": annual_runs[0],
                        "expected_fingerprint": shadow_binding.material_fingerprint,
                    },
                )
                assert str(shadow_bundle_id) == ("019b1800-0000-7000-8000-00000000e293")
                await connection.execute(text("RESET ROLE"))
                shadow_completed = (
                    await connection.execute(
                        text(
                            """
                            SELECT candidate.status,candidate.current_bundle_id,
                                   source_row.lifecycle_state,
                                   source_row.current_policy_version_id,
                                   source_row.current_connector_config_version_id,
                                   source_row.current_trial_run_id,
                                   stream.status AS stream_status,
                                   schedule.status AS schedule_status,
                                   connector.enabled AS connector_enabled,
                                   run.status AS run_status
                              FROM source_candidate candidate
                              JOIN source source_row ON source_row.id=candidate.source_id
                              JOIN source_stream stream ON stream.source_id=source_row.id
                              JOIN fetch_schedule schedule ON schedule.source_id=source_row.id
                              JOIN source_connector connector ON connector.source_id=source_row.id
                              JOIN source_qualification_run run
                                ON run.id=CAST(:run_id AS uuid)
                             WHERE candidate.id=
                               '019b1800-0000-7000-8000-00000000e120'
                            """
                        ),
                        {"run_id": annual_runs[0]},
                    )
                ).one()
                assert shadow_completed.status == "ENABLED"
                assert shadow_completed.current_bundle_id == production.current_bundle_id
                assert shadow_completed.lifecycle_state == "ACTIVE"
                assert (
                    shadow_completed.current_policy_version_id
                    == production.current_policy_version_id
                )
                assert (
                    shadow_completed.current_connector_config_version_id
                    == production.current_connector_config_version_id
                )
                assert shadow_completed.current_trial_run_id == production.current_trial_run_id
                assert shadow_completed.stream_status == "ACTIVE"
                assert shadow_completed.schedule_status == "ACTIVE"
                assert shadow_completed.connector_enabled
                assert shadow_completed.run_status == "SUCCEEDED"
            finally:
                await transaction.rollback()
    finally:
        await engine.dispose()


async def _assert_blocked_candidate_dismissal(database_url: str) -> None:
    engine = create_async_engine(database_url)
    try:
        async with engine.begin() as connection:
            await connection.execute(text("SET LOCAL ROLE srbg_worker_role"))
            await connection.execute(
                text(
                    """
                    SELECT register_discovered_source_candidate(
                      '019b1800-0000-7000-8000-00000000e220'::uuid,
                      '019b1800-0000-7000-8000-00000000e223'::uuid,
                      'https://blocked-source.example.test/',
                      encode(digest(convert_to(
                        'https://blocked-source.example.test/','UTF8'
                      ),'sha256'),'hex'),
                      'blocked-source.example.test',repeat('8',64),'MANUAL',
                      'manual-submission:round18-blocked',ARRAY[]::text[],
                      ARRAY[]::text[],ARRAY['zh-CN'],
                      '019b1800-0000-7000-8000-00000000e901'::uuid,
                      'register blocked source in migration replay',
                      'round18-blocked-register',
                      '019b1800-0000-7000-8000-00000000e237'::uuid,now()
                    )
                    """
                )
            )
            await connection.execute(
                text(
                    """
                    SELECT request_automated_source_qualification(
                      '019b1800-0000-7000-8000-00000000e221'::uuid,
                      '019b1800-0000-7000-8000-00000000e220'::uuid,
                      'source-qualification-v1',
                      '019b1800-0000-7000-8000-00000000e901'::uuid,
                      'qualify blocked source in migration replay',
                      'round18-blocked-qualification',
                      '019b1800-0000-7000-8000-00000000e238'::uuid,now()
                    )
                    """
                )
            )
            blocked_binding = (
                await connection.execute(
                    text(
                        """
                        SELECT * FROM acquire_source_qualification(
                          '019b1800-0000-7000-8000-00000000e221',
                          '019b1800-0000-7000-8000-00000000e224',
                          now(),now()+interval '5 minutes'
                        )
                        """
                    )
                )
            ).one()
            assert blocked_binding.candidate_id == UUID("019b1800-0000-7000-8000-00000000e220")
            blocked_bundle_id = await connection.scalar(
                text(
                    """
                    SELECT complete_source_qualification(
                      '019b1800-0000-7000-8000-00000000e222',
                      '019b1800-0000-7000-8000-00000000e221',
                      '019b1800-0000-7000-8000-00000000e220',
                      '019b1800-0000-7000-8000-00000000e224',
                      'source-qualification-v1',:expected_fingerprint,
                      repeat('8',64),'BLOCKED','LINK_ONLY','TRANSIENT_METADATA_ONLY',
                      jsonb_build_array(jsonb_build_object(
                        'code','ROBOTS_BLOCKED','level','BLOCK',
                        'message','Robots policy blocks automated qualification.',
                        'evidence_refs',jsonb_build_array(
                          'qualification-run:019b1800-0000-7000-8000-00000000e221'
                        ),'observed_at',now()
                      )),ARRAY['ROBOTS_BLOCKED'],1,0,
                      now(),now()+interval '7 days'
                    )
                    """
                ),
                {"expected_fingerprint": blocked_binding.material_fingerprint},
            )
            assert str(blocked_bundle_id) == "019b1800-0000-7000-8000-00000000e222"
            await connection.execute(text("RESET ROLE"))
            blocked_bundle_sha256 = await connection.scalar(
                text(
                    "SELECT bundle_sha256 FROM source_qualification_bundle "
                    "WHERE id='019b1800-0000-7000-8000-00000000e222'"
                )
            )
            await connection.execute(text("SET LOCAL ROLE srbg_worker_role"))
            assert (
                await connection.scalar(
                    text(
                        """
                    SELECT request_automated_source_qualification(
                      '019b1800-0000-7000-8000-00000000e227',
                      '019b1800-0000-7000-8000-00000000e220',
                      'source-qualification-v1',
                      '019b1800-0000-7000-8000-00000000e901',
                      'automatic discovery must not retry unchanged blocked candidate',
                      'round18-blocked-automatic-cooldown',
                      '019b1800-0000-7000-8000-00000000e228',now()
                    )
                    """
                    )
                )
                is None
            )
            await connection.execute(text("RESET ROLE"))
            assert await connection.scalar(
                text(
                    "SELECT count(*)=1 FROM source_qualification_run "
                    "WHERE candidate_id='019b1800-0000-7000-8000-00000000e220'"
                )
            )

        async with engine.connect() as connection:
            transaction = await connection.begin()
            try:
                await connection.execute(text("SET LOCAL ROLE srbg_api_role"))
                requalification_id = await connection.scalar(
                    text(
                        """
                        SELECT request_source_qualification(
                          '019b1800-0000-7000-8000-00000000e225',
                          '019b1800-0000-7000-8000-00000000e220',
                          'source-qualification-v1',
                          '019b1800-0000-7000-8000-00000000e901',
                          'requalify a blocked source candidate',
                          'round18-blocked-requalification',
                          '019b1800-0000-7000-8000-00000000e226',now()
                        )
                        """
                    )
                )
                assert str(requalification_id) == ("019b1800-0000-7000-8000-00000000e225")
                await connection.execute(text("RESET ROLE"))
                assert await connection.scalar(
                    text(
                        "SELECT status='QUALIFYING' FROM source_candidate "
                        "WHERE id='019b1800-0000-7000-8000-00000000e220'"
                    )
                )
            finally:
                await transaction.rollback()

        with pytest.raises(DBAPIError, match="candidate verdict cannot be enabled"):
            async with engine.begin() as connection:
                await connection.execute(text("SET LOCAL ROLE srbg_api_role"))
                await connection.execute(
                    text(
                        """
                        SELECT * FROM activate_qualified_candidate(
                          '019b1800-0000-7000-8000-00000000e220','ENABLE',
                          :bundle_sha256,repeat('a',64),'round18-blocked-enable',
                          'blocked candidates cannot be enabled',NULL,
                          '019b1800-0000-7000-8000-00000000e900',
                          '019b1800-0000-7000-8000-00000000e230',
                          '019b1800-0000-7000-8000-00000000e231',
                          '019b1800-0000-7000-8000-00000000e232',
                          '019b1800-0000-7000-8000-00000000e233',
                          '019b1800-0000-7000-8000-00000000e234',
                          '019b1800-0000-7000-8000-00000000e235',
                          '019b1800-0000-7000-8000-00000000e236',now()
                        )
                        """
                    ),
                    {"bundle_sha256": blocked_bundle_sha256},
                )

        async with engine.begin() as connection:
            await connection.execute(text("SET LOCAL ROLE srbg_api_role"))
            dismissed = (
                await connection.execute(
                    text(
                        """
                        SELECT * FROM activate_qualified_candidate(
                          '019b1800-0000-7000-8000-00000000e220','DISMISS',
                          repeat('0',64),repeat('b',64),'round18-blocked-dismiss',
                          'dismiss blocked source in migration replay',NULL,
                          '019b1800-0000-7000-8000-00000000e900',
                          '019b1800-0000-7000-8000-00000000e240',
                          '019b1800-0000-7000-8000-00000000e241',
                          '019b1800-0000-7000-8000-00000000e242',
                          '019b1800-0000-7000-8000-00000000e243',
                          '019b1800-0000-7000-8000-00000000e244',
                          '019b1800-0000-7000-8000-00000000e245',
                          '019b1800-0000-7000-8000-00000000e246',now()
                        )
                        """
                    )
                )
            ).one()
            assert dismissed.source_id is None
            assert dismissed.outbox_id is None
            assert dismissed.candidate_status == "DISMISSED"

        async with engine.connect() as connection:
            state = (
                await connection.execute(
                    text(
                        """
                        SELECT candidate.status,source_row.lifecycle_state,
                               schedule.status AS schedule_status,
                               count(activation.id) AS activation_count
                          FROM source_candidate candidate
                          JOIN source source_row ON source_row.id=candidate.source_id
                          JOIN fetch_schedule schedule ON schedule.source_id=source_row.id
                          LEFT JOIN source_activation_outbox activation
                            ON activation.source_id=source_row.id
                         WHERE candidate.id='019b1800-0000-7000-8000-00000000e220'
                         GROUP BY candidate.status,source_row.lifecycle_state,schedule.status
                        """
                    )
                )
            ).one()
            assert state.status == "DISMISSED"
            assert state.lifecycle_state == "CANDIDATE"
            assert state.schedule_status == "PAUSED"
            assert state.activation_count == 0
    finally:
        await engine.dispose()


async def _assert_failed_candidate_dismissal(database_url: str) -> None:
    engine = create_async_engine(database_url)
    try:
        async with engine.begin() as connection:
            await connection.execute(text("SET LOCAL ROLE srbg_worker_role"))
            await connection.execute(
                text(
                    """
                    SELECT register_discovered_source_candidate(
                      '019b1800-0000-7000-8000-00000000e250',
                      '019b1800-0000-7000-8000-00000000e251',
                      'https://failed-source.example.test/',
                      encode(digest(convert_to(
                        'https://failed-source.example.test/','UTF8'
                      ),'sha256'),'hex'),
                      'failed-source.example.test',repeat('9',64),'MANUAL',
                      'manual-submission:round18-failed',ARRAY[]::text[],
                      ARRAY[]::text[],ARRAY['zh-CN'],
                      '019b1800-0000-7000-8000-00000000e901',
                      'register source for controlled qualification failure replay',
                      'round18-failed-register',
                      '019b1800-0000-7000-8000-00000000e252',now()
                    )
                    """
                )
            )
            await connection.execute(
                text(
                    """
                    SELECT request_automated_source_qualification(
                      '019b1800-0000-7000-8000-00000000e253',
                      '019b1800-0000-7000-8000-00000000e250',
                      'source-qualification-v1',
                      '019b1800-0000-7000-8000-00000000e901',
                      'start controlled qualification failure replay',
                      'round18-failed-qualification',
                      '019b1800-0000-7000-8000-00000000e254',now()
                    )
                    """
                )
            )
            await connection.execute(
                text(
                    """
                    SELECT * FROM acquire_source_qualification(
                      '019b1800-0000-7000-8000-00000000e253',
                      '019b1800-0000-7000-8000-00000000e255',
                      now(),now()+interval '5 minutes'
                    )
                    """
                )
            )
            failed_id = await connection.scalar(
                text(
                    """
                    SELECT fail_source_qualification(
                      '019b1800-0000-7000-8000-00000000e253',
                      '019b1800-0000-7000-8000-00000000e250',
                      '019b1800-0000-7000-8000-00000000e255',
                      'TARGET_FETCH_FAILED',now()
                    )
                    """
                )
            )
            assert str(failed_id) == "019b1800-0000-7000-8000-00000000e250"
            await connection.execute(text("RESET ROLE"))
            failed = (
                await connection.execute(
                    text(
                        """
                        SELECT candidate.status,candidate.current_bundle_id,
                               run.status AS run_status,run.failure_reason_code
                          FROM source_candidate candidate
                          JOIN source_qualification_run run
                            ON run.candidate_id=candidate.id
                         WHERE candidate.id='019b1800-0000-7000-8000-00000000e250'
                        """
                    )
                )
            ).one()
            assert failed.status == "BLOCKED"
            assert failed.current_bundle_id is None
            assert failed.run_status == "FAILED"
            assert failed.failure_reason_code == "TARGET_FETCH_FAILED"

        with pytest.raises(DBAPIError, match="STALE_QUALIFICATION_BUNDLE"):
            async with engine.begin() as connection:
                await connection.execute(text("SET LOCAL ROLE srbg_api_role"))
                await connection.execute(
                    text(
                        """
                        SELECT * FROM activate_qualified_candidate(
                          '019b1800-0000-7000-8000-00000000e250','ENABLE',NULL,
                          repeat('1',64),'round18-failed-enable',
                          'failed qualification cannot be enabled',NULL,
                          '019b1800-0000-7000-8000-00000000e900',
                          '019b1800-0000-7000-8000-00000000e260',
                          '019b1800-0000-7000-8000-00000000e261',
                          '019b1800-0000-7000-8000-00000000e262',
                          '019b1800-0000-7000-8000-00000000e263',
                          '019b1800-0000-7000-8000-00000000e264',
                          '019b1800-0000-7000-8000-00000000e265',
                          '019b1800-0000-7000-8000-00000000e266',now()
                        )
                        """
                    )
                )

        async with engine.begin() as connection:
            await connection.execute(text("SET LOCAL ROLE srbg_api_role"))
            dismissed = (
                await connection.execute(
                    text(
                        """
                        SELECT * FROM activate_qualified_candidate(
                          '019b1800-0000-7000-8000-00000000e250','DISMISS',NULL,
                          repeat('2',64),'round18-failed-dismiss',
                          'dismiss failed source candidate after reviewing failure',NULL,
                          '019b1800-0000-7000-8000-00000000e900',
                          '019b1800-0000-7000-8000-00000000e270',
                          '019b1800-0000-7000-8000-00000000e271',
                          '019b1800-0000-7000-8000-00000000e272',
                          '019b1800-0000-7000-8000-00000000e273',
                          '019b1800-0000-7000-8000-00000000e274',
                          '019b1800-0000-7000-8000-00000000e275',
                          '019b1800-0000-7000-8000-00000000e276',now()
                        )
                        """
                    )
                )
            ).one()
            assert dismissed.candidate_status == "DISMISSED"

        async with engine.connect() as connection:
            evidence = (
                await connection.execute(
                    text(
                        """
                        SELECT candidate.status,decision.bundle_id,
                               audit.before_state->>'failure_reason_code' AS failure_reason_code
                          FROM source_candidate candidate
                          JOIN source_candidate_decision decision
                            ON decision.candidate_id=candidate.id
                          JOIN audit_log audit
                            ON audit.id='019b1800-0000-7000-8000-00000000e276'
                         WHERE candidate.id='019b1800-0000-7000-8000-00000000e250'
                           AND decision.id='019b1800-0000-7000-8000-00000000e270'
                        """
                    )
                )
            ).one()
            assert evidence.status == "DISMISSED"
            assert evidence.bundle_id is None
            assert evidence.failure_reason_code == "TARGET_FETCH_FAILED"
    finally:
        await engine.dispose()
