"""Replay and inspect the complete Round 17 migration chain on a disposable database."""

from __future__ import annotations

import asyncio
import ipaddress
import json
import os
import re
from base64 import b64encode
from hashlib import sha256
from pathlib import Path
from urllib.parse import urlsplit

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine

BASE_REVISION = "0016_scheduling_health_replay"
HEAD_REVISION = "0017c_round17_flat_pilot"
_DISPOSABLE_DATABASE = re.compile(r"srbg_it_[0-9a-f]{24}\Z")
_GUARD_WINDOW_ID = "019b1700-0000-7000-8000-00000000d017"

EXPECTED_TABLES = (
    "source_governance_scheme_assignment",
    "round17_staff_binding",
    "round17_eventization_readiness",
    "round17_pilot_window",
    "round17_pilot_window_source",
    "round17_gold_task",
    "round17_gold_assignment",
    "round17_gold_annotation",
    "round17_gold_arbitration",
    "round17_gold_release",
    "round17_operator_task",
    "round17_operator_work_session",
    "round17_operator_work_correction",
    "round17_metric_snapshot",
    "round17_signed_approval",
    "round17_reference_annotation",
)
EXPECTED_CONSTRAINTS = (
    "ck_source_governance_scheme_round17",
    "ck_round17_staff_responsibility",
    "ck_round17_staff_authority_mode",
    "ck_round17_staff_identity_assurance",
    "ck_round17_staff_identity_hashes",
    "ck_round17_window_environment",
    "ck_round17_window_duration",
    "ck_round17_window_state",
    "ck_round17_window_exact_period",
    "ck_round17_source_exact_period",
    "ck_round17_source_schedule_pins",
    "ck_round17_source_pause_fact",
    "ck_round17_source_resume_fact",
    "uq_round17_window_source_segment",
    "uq_round17_window_source_code_segment",
    "ck_fetch_run_origin",
    "ck_round17_gold_task_hashes",
    "ck_round17_gold_task_roster_version",
    "ck_round17_gold_task_definition_version",
    "ck_round17_annotation_status",
    "ck_round17_gold_release_roster_version",
    "ck_round17_gold_release_definition_version",
    "ck_round17_gold_release_source_codes",
    "ck_round17_gold_release_status",
    "ck_round17_operator_task_category",
    "ck_round17_operator_task_status",
    "ck_round17_operator_task_version",
    "ck_round17_operator_task_separation",
    "ck_round17_work_seconds",
    "uq_round17_work_session_task",
    "ck_round17_work_correction_separation",
    "ck_round17_eventization_status",
    "ck_round17_eventization_profile_hashes",
    "ck_round17_eventization_manifest_ref",
    "ck_round17_metric_hash",
    "fk_fetch_run_round17_window_source",
    "ck_round17_signed_approval_type",
    "ck_round17_signed_approval_authority",
    "ck_round17_signed_approval_crypto",
    "ck_round17_signed_approval_document",
    "ck_round17_signed_approval_validity",
    "ck_round17_reference_annotation_model",
    "ck_round17_reference_kind",
    "ck_round17_reference_hashes",
)
EXPECTED_INDEXES = ("uq_round17_single_running_window",)
EXPECTED_TRIGGERS = (
    "trg_source_governance_scheme_assignment_immutable",
    "trg_round17_staff_binding_immutable",
    "trg_round17_eventization_readiness_immutable",
    "trg_round17_gold_annotation_immutable",
    "trg_round17_gold_arbitration_immutable",
    "trg_round17_gold_release_immutable",
    "trg_round17_metric_snapshot_immutable",
    "trg_round17_signed_approval_immutable",
    "trg_round17_reference_annotation_immutable",
    "trg_round17_window_pins",
    "trg_round17_source_segment_pins",
    "trg_fetch_run_origin_immutable",
    "trg_fetch_run_bind_round17",
    "trg_round17_source_authority_change",
    "trg_round17_schedule_change",
    "trg_round17_source_anomaly",
    "trg_round17_work_correction_guard",
    "trg_round17_operator_task_guard",
    "trg_round17_work_session_guard",
)
EXPECTED_FUNCTION_SIGNATURES = (
    "assign_round17_two_person_governance(uuid,uuid,text,uuid,text,text,uuid,timestamptz)",
    "source_v2_governance_scheme(uuid)",
    "round17_source_actor_is_maker(uuid,uuid,uuid,uuid,uuid)",
    "decide_source_policy_version(uuid,uuid,uuid,text,uuid,text,text,uuid,timestamptz)",
    "start_source_trial_run(uuid,uuid,text,uuid,uuid,uuid,uuid,text,text,uuid,uuid,timestamptz)",
    "approve_source_production(uuid,uuid,uuid,uuid,uuid,uuid,text,text,uuid,uuid,timestamptz)",
    "protect_round17_window_pins()",
    "protect_round17_source_segment_pins()",
    "protect_fetch_run_origin()",
    "bind_round17_fetch_run()",
    "pause_round17_segments_on_source_change()",
    "pause_round17_segments_on_schedule_change()",
    "pause_round17_segments_on_anomaly()",
    "validate_round17_operator_task()",
    "validate_round17_work_session()",
    "validate_round17_work_correction()",
    "start_round17_operator_task(uuid,uuid,uuid,timestamptz)",
    "complete_round17_operator_task(uuid,integer,uuid,timestamptz)",
    "record_scheduled_source_raw(uuid,uuid,uuid,uuid,text,text,text,text,bigint,text,text,text,text,text,text,jsonb,integer,text,text,timestamptz)",
    "record_scheduled_source_document(uuid,uuid,uuid,uuid,uuid,uuid,uuid,uuid,uuid,text,text,text,text,text,timestamptz)",
)

_RAW_FUNCTION = EXPECTED_FUNCTION_SIGNATURES[-2]
_DOCUMENT_FUNCTION = EXPECTED_FUNCTION_SIGNATURES[-1]
_ASSIGNMENT_FUNCTION = EXPECTED_FUNCTION_SIGNATURES[0]
_POLICY_FUNCTION = EXPECTED_FUNCTION_SIGNATURES[3]
_START_OPERATOR_TASK_FUNCTION = "start_round17_operator_task(uuid,uuid,uuid,timestamptz)"
_COMPLETE_OPERATOR_TASK_FUNCTION = (
    "complete_round17_operator_task(uuid,integer,uuid,timestamptz)"
)
_COMPATIBILITY_WRAPPERS = EXPECTED_FUNCTION_SIGNATURES[3:6]
_ROUND17_ONLY_FUNCTIONS = (
    *EXPECTED_FUNCTION_SIGNATURES[:3],
    *EXPECTED_FUNCTION_SIGNATURES[6:],
)
_REVOKED_TRIGGER_FUNCTIONS = (
    "protect_round17_source_segment_pins()",
    "pause_round17_segments_on_source_change()",
    "pause_round17_segments_on_schedule_change()",
    "pause_round17_segments_on_anomaly()",
    "validate_round17_operator_task()",
    "validate_round17_work_session()",
    "validate_round17_work_correction()",
)


def validate_disposable_database_url(database_url: str) -> str:
    """Return the database name only for an isolated loopback integration database."""

    parsed = urlsplit(database_url.replace("postgresql+asyncpg", "postgresql", 1))
    database_name = parsed.path.removeprefix("/")
    try:
        loopback = parsed.hostname == "localhost" or (
            parsed.hostname is not None and ipaddress.ip_address(parsed.hostname).is_loopback
        )
    except ValueError:
        loopback = False
    if (
        parsed.scheme != "postgresql"
        or not loopback
        or _DISPOSABLE_DATABASE.fullmatch(database_name) is None
    ):
        raise RuntimeError("Round17 migration replay requires an isolated loopback database")
    return database_name


async def _current_revisions(connection: AsyncConnection) -> tuple[str, ...]:
    result = await connection.execute(text("SELECT version_num FROM alembic_version ORDER BY 1"))
    return tuple(result.scalars())


async def _assert_database_revision(database_url: str, expected: str) -> None:
    engine = create_async_engine(database_url)
    try:
        async with engine.connect() as connection:
            revisions = await _current_revisions(connection)
            if revisions != (expected,):
                raise RuntimeError(
                    f"isolated database revision mismatch: expected {expected}, got {revisions}"
                )
    finally:
        await engine.dispose()


async def _has_table_privilege(
    connection: AsyncConnection,
    role: str,
    table: str,
    privilege: str,
) -> bool:
    if role == "PUBLIC":
        value = await connection.scalar(
            text(
                """
                SELECT COALESCE(bool_or(acl.grantee=0 AND acl.privilege_type=:privilege),false)
                  FROM pg_class relation
                  CROSS JOIN LATERAL aclexplode(
                    COALESCE(relation.relacl,acldefault('r',relation.relowner))
                  ) acl
                 WHERE relation.oid=to_regclass(:table)
                """
            ),
            {"table": f"public.{table}", "privilege": privilege},
        )
        return value is True
    value = await connection.scalar(
        text("SELECT has_table_privilege(:role,:table,:privilege)"),
        {"role": role, "table": table, "privilege": privilege},
    )
    return value is True


async def _has_column_privilege(
    connection: AsyncConnection,
    role: str,
    table: str,
    column: str,
    privilege: str,
) -> bool:
    value = await connection.scalar(
        text("SELECT has_column_privilege(:role,:table,:column,:privilege)"),
        {"role": role, "table": table, "column": column, "privilege": privilege},
    )
    return value is True


async def _has_function_privilege(
    connection: AsyncConnection,
    role: str,
    signature: str,
) -> bool:
    if role == "PUBLIC":
        value = await connection.scalar(
            text(
                """
                SELECT COALESCE(bool_or(acl.grantee=0 AND acl.privilege_type='EXECUTE'),false)
                  FROM pg_proc function_row
                  CROSS JOIN LATERAL aclexplode(
                    COALESCE(function_row.proacl,acldefault('f',function_row.proowner))
                  ) acl
                 WHERE function_row.oid=to_regprocedure(:signature)
                """
            ),
            {"signature": f"public.{signature}"},
        )
        return value is True
    value = await connection.scalar(
        text("SELECT has_function_privilege(:role,to_regprocedure(:signature),'EXECUTE')"),
        {"role": role, "signature": f"public.{signature}"},
    )
    return value is True


async def _verify_objects(connection: AsyncConnection) -> None:
    for table in EXPECTED_TABLES:
        relation = await connection.scalar(
            text("SELECT to_regclass(:name)"), {"name": f"public.{table}"}
        )
        if relation is None:
            raise RuntimeError(f"Round17 migration table is missing: {table}")

    constraint_rows = await connection.execute(text("SELECT conname FROM pg_constraint"))
    constraints = set(constraint_rows.scalars())
    missing_constraints = set(EXPECTED_CONSTRAINTS) - constraints
    if missing_constraints:
        raise RuntimeError(f"Round17 constraints are missing: {sorted(missing_constraints)}")

    index_rows = await connection.execute(
        text("SELECT indexname FROM pg_indexes WHERE schemaname='public'")
    )
    indexes = set(index_rows.scalars())
    missing_indexes = set(EXPECTED_INDEXES) - indexes
    if missing_indexes:
        raise RuntimeError(f"Round17 indexes are missing: {sorted(missing_indexes)}")

    trigger_rows = await connection.execute(
        text("SELECT tgname FROM pg_trigger WHERE NOT tgisinternal")
    )
    triggers = set(trigger_rows.scalars())
    missing_triggers = set(EXPECTED_TRIGGERS) - triggers
    if missing_triggers:
        raise RuntimeError(f"Round17 immutable triggers are missing: {sorted(missing_triggers)}")

    for signature in EXPECTED_FUNCTION_SIGNATURES:
        function = await connection.scalar(
            text("SELECT to_regprocedure(:signature)"),
            {"signature": f"public.{signature}"},
        )
        if function is None:
            raise RuntimeError(f"Round17 function signature is missing: {signature}")

    columns_result = await connection.execute(
        text(
            """
            SELECT column_name FROM information_schema.columns
             WHERE table_schema='public' AND table_name='fetch_run'
               AND column_name IN ('run_origin','replayed_from_run_id','pilot_window_source_id')
            """
        )
    )
    if set(columns_result.scalars()) != {
        "run_origin",
        "replayed_from_run_id",
        "pilot_window_source_id",
    }:
        raise RuntimeError("Round17 fetch-run provenance columns are incomplete")


async def _verify_role_boundaries(connection: AsyncConnection) -> None:
    api_expected = (
        ("round17_gold_annotation", "SELECT", True),
        ("round17_gold_annotation", "INSERT", True),
        ("round17_gold_annotation", "UPDATE", False),
        ("round17_gold_annotation", "DELETE", False),
        ("round17_pilot_window", "SELECT", True),
        ("round17_pilot_window", "INSERT", True),
        ("round17_pilot_window", "UPDATE", False),
        ("round17_pilot_window", "DELETE", False),
        ("round17_eventization_readiness", "SELECT", True),
        ("round17_eventization_readiness", "INSERT", False),
        ("round17_staff_binding", "SELECT", True),
        ("round17_staff_binding", "INSERT", False),
        ("round17_operator_task", "SELECT", True),
        ("round17_operator_task", "INSERT", True),
        ("round17_operator_task", "UPDATE", False),
        ("round17_operator_task", "DELETE", False),
        ("round17_operator_work_session", "INSERT", False),
        ("round17_signed_approval", "SELECT", True),
        ("round17_signed_approval", "INSERT", False),
        ("round17_reference_annotation", "SELECT", True),
        ("round17_reference_annotation", "INSERT", False),
    )
    for table, privilege, expected in api_expected:
        actual = await _has_table_privilege(connection, "srbg_api_role", table, privilege)
        if actual is not expected:
            raise RuntimeError(f"srbg_api_role {table} {privilege} boundary differs")

    api_columns = (
        ("round17_pilot_window", "state", True),
        ("round17_pilot_window", "roster_version", False),
        ("round17_pilot_window_source", "status", True),
        ("round17_pilot_window_source", "source_id", False),
        ("round17_pilot_window_source", "schedule_version", False),
        ("round17_gold_task", "status", True),
        ("round17_gold_task", "sample_ref", False),
        ("round17_operator_work_session", "active_seconds", True),
        ("round17_operator_work_session", "accrued_seconds", True),
        ("round17_operator_work_session", "last_activity_at", True),
        ("round17_operator_work_session", "task_id", False),
        ("round17_operator_work_session", "window_id", False),
        ("round17_operator_work_session", "started_at", False),
        ("round17_operator_task", "status", False),
    )
    for table, column, expected in api_columns:
        actual = await _has_column_privilege(connection, "srbg_api_role", table, column, "UPDATE")
        if actual is not expected:
            raise RuntimeError(f"srbg_api_role {table}.{column} UPDATE boundary differs")

    worker_expected = (
        ("round17_pilot_window", "SELECT", True),
        ("round17_pilot_window_source", "SELECT", True),
        ("round17_gold_annotation", "SELECT", False),
        ("round17_pilot_window", "INSERT", False),
        ("round17_pilot_window_source", "UPDATE", False),
    )
    for table, privilege, expected in worker_expected:
        actual = await _has_table_privilege(connection, "srbg_worker_role", table, privilege)
        if actual is not expected:
            raise RuntimeError(f"srbg_worker_role {table} {privilege} boundary differs")

    for table in EXPECTED_TABLES:
        for role in ("srbg_projection_reader", "PUBLIC"):
            if await _has_table_privilege(connection, role, table, "SELECT"):
                raise RuntimeError(f"{role} can read protected Round17 table {table}")
            if await _has_table_privilege(connection, role, table, "INSERT"):
                raise RuntimeError(f"{role} can write protected Round17 table {table}")

    function_matrix = (
        ("srbg_worker_role", _RAW_FUNCTION, True),
        ("srbg_worker_role", _DOCUMENT_FUNCTION, True),
        ("srbg_api_role", _RAW_FUNCTION, False),
        ("srbg_api_role", _DOCUMENT_FUNCTION, False),
        ("srbg_projection_reader", _RAW_FUNCTION, False),
        ("PUBLIC", _RAW_FUNCTION, False),
        ("srbg_api_role", _ASSIGNMENT_FUNCTION, True),
        ("srbg_api_role", _POLICY_FUNCTION, True),
        ("srbg_worker_role", _ASSIGNMENT_FUNCTION, False),
        ("srbg_projection_reader", _ASSIGNMENT_FUNCTION, False),
        ("PUBLIC", _ASSIGNMENT_FUNCTION, False),
        ("srbg_api_role", _START_OPERATOR_TASK_FUNCTION, True),
        ("srbg_api_role", _COMPLETE_OPERATOR_TASK_FUNCTION, True),
        ("srbg_worker_role", _START_OPERATOR_TASK_FUNCTION, False),
        ("srbg_projection_reader", _START_OPERATOR_TASK_FUNCTION, False),
        ("PUBLIC", _START_OPERATOR_TASK_FUNCTION, False),
    )
    for role, signature, expected in function_matrix:
        actual = await _has_function_privilege(connection, role, signature)
        if actual is not expected:
            raise RuntimeError(f"{role} EXECUTE boundary differs for {signature}")
    for signature in _REVOKED_TRIGGER_FUNCTIONS:
        for role in ("srbg_api_role", "srbg_worker_role", "srbg_projection_reader", "PUBLIC"):
            if await _has_function_privilege(connection, role, signature):
                raise RuntimeError(f"{role} can execute protected trigger function {signature}")


async def _expect_database_rejection(
    connection: AsyncConnection, statement: str, message: str
) -> None:
    savepoint = await connection.begin_nested()
    try:
        await connection.execute(text(statement))
    except DBAPIError:
        await savepoint.rollback()
    else:
        await savepoint.rollback()
        raise RuntimeError(message)


async def _verify_window_state_guards(connection: AsyncConnection) -> None:
    for suffix in ("e001", "e002"):
        await connection.execute(
            text(
                """INSERT INTO round17_pilot_window(
                      id,roster_version,metric_definition_version,gold_definition_version,
                      baseline_commit,config_version,database_revision,environment,
                      duration_hours,state,version,blocker_codes,prepared_by,prepared_at,
                      idempotency_key
                    ) VALUES (
                      CAST(:id AS uuid),'r17-sources-v0.1',
                      'phase2-round17-metrics-v1.0.0',
                      'phase2-round17-gold-v1.0.0',
                      'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa','r17-config-v0.1',
                      '0017c_round17_flat_pilot','PREPRODUCTION',168,'PREPARING',1,
                      '{}'::text[],'019b1700-0000-7000-8000-00000000e000',
                      statement_timestamp(),:key
                    )"""
            ),
            {
                "id": f"019b1700-0000-7000-8000-00000000{suffix}",
                "key": f"round17-window-guard-{suffix}",
            },
        )
    await connection.execute(
        text(
            "UPDATE round17_pilot_window SET state='READY',version=2 "
            "WHERE id IN ('019b1700-0000-7000-8000-00000000e001',"
            "'019b1700-0000-7000-8000-00000000e002')"
        )
    )
    await connection.execute(
        text(
            """UPDATE round17_pilot_window
                  SET state='RUNNING',version=3,
                      started_by='019b1700-0000-7000-8000-00000000e000',
                      started_at=statement_timestamp(),
                      ends_at=statement_timestamp()+interval '168 hours'
                WHERE id='019b1700-0000-7000-8000-00000000e001'"""
        )
    )
    await _expect_database_rejection(
        connection,
        """UPDATE round17_pilot_window
              SET state='COMPLETED',version=4
            WHERE id='019b1700-0000-7000-8000-00000000e001'""",
        "window completed before its immutable ends_at",
    )
    await _expect_database_rejection(
        connection,
        """UPDATE round17_pilot_window
              SET state='RUNNING',version=3,
                  started_by='019b1700-0000-7000-8000-00000000e000',
                  started_at=statement_timestamp(),
                  ends_at=statement_timestamp()+interval '168 hours'
            WHERE id='019b1700-0000-7000-8000-00000000e002'""",
        "Round17 accepted two concurrent RUNNING windows",
    )
    await _expect_database_rejection(
        connection,
        """UPDATE round17_pilot_window
              SET version=4,started_at=started_at+interval '1 second'
            WHERE id='019b1700-0000-7000-8000-00000000e001'""",
        "Round17 accepted mutation of an immutable window start fact",
    )
    await _expect_database_rejection(
        connection,
        """INSERT INTO round17_pilot_window(
              id,roster_version,metric_definition_version,gold_definition_version,
              baseline_commit,config_version,database_revision,environment,
              duration_hours,state,version,blocker_codes,prepared_by,prepared_at,
              started_by,started_at,ends_at,idempotency_key
            ) VALUES (
              '019b1700-0000-7000-8000-00000000e003',
              'r17-sources-v0.1','phase2-round17-metrics-v1.0.0',
              'phase2-round17-gold-v1.0.0','aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
              'r17-config-v0.1','0017c_round17_flat_pilot','PREPRODUCTION',168,
              'RUNNING',1,'{}'::text[],
              '019b1700-0000-7000-8000-00000000e000',statement_timestamp(),
              '019b1700-0000-7000-8000-00000000e000',statement_timestamp(),
              statement_timestamp()+interval '168 hours','round17-window-guard-e003'
            )""",
        "Round17 accepted a window that bypassed PREPARING state",
    )


async def _verify_head(database_url: str) -> None:
    engine = create_async_engine(database_url)
    try:
        async with engine.connect() as connection:
            if await _current_revisions(connection) != (HEAD_REVISION,):
                raise RuntimeError("Round17 database does not have exactly one current head")
            await _verify_objects(connection)
            await _verify_role_boundaries(connection)
            await _verify_window_state_guards(connection)
    finally:
        await engine.dispose()


async def _expect_runtime_rejection(
    connection: AsyncConnection,
    statement: str,
    message: str = "Round17 scheduled runtime accepted forbidden evidence",
) -> None:
    savepoint = await connection.begin_nested()
    try:
        await connection.execute(text(statement))
    except DBAPIError:
        await savepoint.rollback()
    else:
        await savepoint.rollback()
        raise RuntimeError(message)


async def _verify_scheduled_runtime_functions(database_url: str) -> None:
    """Execute the Worker ABI through its real role, then roll all facts back."""

    engine = create_async_engine(database_url)
    manifest = {
        "schema_version": "round17-eventization-manifest-v1",
        "source_code": "R17-DYNAMIC-001",
        "source_id": "019b1700-0000-7000-8000-00000000d101",
        "policy_version_id": "019b1700-0000-7000-8000-00000000d102",
        "connector_config_version_id": "019b1700-0000-7000-8000-00000000d103",
        "trial_run_id": "019b1700-0000-7000-8000-00000000d104",
        "production_decision_id": "019b1700-0000-7000-8000-00000000d106",
        "business_parser_profile": {"version": "fixture-business-parser-v1", "sha256": "5" * 64},
        "claim_evidence_profile": {"version": "fixture-claim-evidence-v1", "sha256": "6" * 64},
        "event_identity_profile": {"version": "fixture-event-identity-v1", "sha256": "7" * 64},
        "publication_projection_profile": {
            "version": "fixture-publication-projection-v1",
            "sha256": "8" * 64,
        },
        "verification_manifest_ref": (
            "urn:srbg:round17-eventization-manifest:"
            "019b1700-0000-7000-8000-00000000d150"
        ),
        "outcome": "PASSED",
    }
    manifest_bytes = json.dumps(
        manifest, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode()
    private_key = Ed25519PrivateKey.from_private_bytes(bytes(range(1, 33)))
    public_key = private_key.public_key().public_bytes_raw()
    manifest_json = manifest_bytes.decode()
    manifest_sha256 = sha256(manifest_bytes).hexdigest()
    manifest_signature = b64encode(private_key.sign(manifest_bytes)).decode()
    signer_sha256 = sha256(public_key).hexdigest()
    policy_json = json.dumps(
        {
            "storage_policy": "RAW_EVIDENCE_ALLOWED",
            "fetch": {
                "allowed_domains": ["source.example.test"],
                "minimum_interval_seconds": 1,
            },
            "slo": {"applicability": "APPLICABLE", "target_minutes": 480},
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    try:
        async with engine.connect() as connection:
            transaction = await connection.begin()
            try:
                seed_sql = """
                        INSERT INTO source(
                          id,registry_code,name,base_url,channel,source_type,
                          authority_level,priority,collection_method,
                          poll_interval_minutes,owner,state,enabled,created_at,updated_at,
                          lifecycle_state,registered_by,governance_owner_id
                        ) VALUES (
                          '019b1700-0000-7000-8000-00000000d101',
                          'R17-DYNAMIC-001','Round17 dynamic runtime source',
                          'https://source.example.test/','BOTH','government',
                          'A1','P0','rss',60,'source_ops','CANDIDATE',false,now(),now(),
                          'CANDIDATE','019b1700-0000-7000-8000-00000000da01',
                          '019b1700-0000-7000-8000-00000000da02'
                        );
                        INSERT INTO round17_staff_binding(
                          id,actor_id,display_name,responsibility,oidc_issuer_sha256,
                          oidc_subject_sha256,local_identity,bound_by,bound_at
                        ) VALUES
                        (
                          '019b1700-0000-7000-8000-00000000d151',
                          '019b1700-0000-7000-8000-00000000da07','LEO',
                          'SOURCE_APPROVER',repeat('1',64),repeat('2',64),false,
                          '019b1700-0000-7000-8000-00000000da09',now()
                        ),
                        (
                          '019b1700-0000-7000-8000-00000000d152',
                          '019b1700-0000-7000-8000-00000000da08','yinzi',
                          'SOURCE_OPERATOR',repeat('3',64),repeat('4',64),false,
                          '019b1700-0000-7000-8000-00000000da09',now()
                        );
                        INSERT INTO source_governance_scheme_assignment(
                          id,source_id,scheme,cohort_key,assigned_by,reason,request_id,
                          created_at
                        ) VALUES (
                          '019b1700-0000-7000-8000-00000000d153',
                          '019b1700-0000-7000-8000-00000000d101',
                          'R17_TWO_PERSON_MAKER_CHECKER_V1','r17-sources-v0.1',
                          '019b1700-0000-7000-8000-00000000da07',
                          'isolated migration verifier assignment',
                          'r17-dynamic-governance-assignment',now()
                        );
                        INSERT INTO source_policy_version(
                          id,source_id,schema_version,policy_version,status,document,
                          document_sha256,valid_from,valid_until,submitted_by,created_at
                        ) VALUES (
                          '019b1700-0000-7000-8000-00000000d102',
                          '019b1700-0000-7000-8000-00000000d101','2.0.0','r17-dynamic-v1',
                          'APPROVED',
                          CAST(:policy_json AS jsonb),
                          repeat('a',64),now()-interval '1 hour',now()+interval '8 days',
                          '019b1700-0000-7000-8000-00000000da03',now()
                        );
                        INSERT INTO connector_config_version(
                          id,source_id,connector_definition_id,policy_version_id,
                          version_number,config_document,config_sha256,allowed_hosts,
                          validation_status,validation_reason_codes,created_by,created_at
                        ) SELECT
                          '019b1700-0000-7000-8000-00000000d103',
                          '019b1700-0000-7000-8000-00000000d101',definition.id,
                          '019b1700-0000-7000-8000-00000000d102',1,
                          '{"allowed_hosts":["source.example.test"],"feed_url":"https://source.example.test/feed.xml"}'::jsonb,
                          repeat('b',64),ARRAY['source.example.test'],'VALID',ARRAY[]::text[],
                          '019b1700-0000-7000-8000-00000000da04',now()
                          FROM connector_definition definition
                         WHERE definition.connector_type='RSS_ATOM'
                           AND definition.definition_version='1.0.0';
                        INSERT INTO source_governance_decision(
                          id,source_id,decision_type,outcome,policy_version_id,
                          connector_config_version_id,trial_run_id,submitted_by,decided_by,
                          reason,valid_until,created_at
                        ) VALUES (
                          '019b1700-0000-7000-8000-00000000d154',
                          '019b1700-0000-7000-8000-00000000d101',
                          'COMPLIANCE','APPROVED',
                          '019b1700-0000-7000-8000-00000000d102',
                          '019b1700-0000-7000-8000-00000000d103',NULL,
                          '019b1700-0000-7000-8000-00000000da03',
                          '019b1700-0000-7000-8000-00000000da07',
                          'isolated verifier compliance approval',
                          now()+interval '8 days',now()
                        );
                        INSERT INTO source_governance_decision(
                          id,source_id,decision_type,outcome,policy_version_id,
                          connector_config_version_id,trial_run_id,submitted_by,decided_by,
                          reason,valid_until,created_at
                        ) VALUES (
                          '019b1700-0000-7000-8000-00000000d105',
                          '019b1700-0000-7000-8000-00000000d101',
                          'LIVE_TRIAL_AUTHORIZATION','APPROVED',
                          '019b1700-0000-7000-8000-00000000d102',
                          '019b1700-0000-7000-8000-00000000d103',NULL,
                          '019b1700-0000-7000-8000-00000000da04',
                          '019b1700-0000-7000-8000-00000000da05',
                          'dynamic live trial authorization',now()+interval '8 days',now()
                        );
                        INSERT INTO source_trial_run(
                          id,source_id,kind,execution_domain,policy_version_id,
                          connector_config_version_id,authorization_decision_id,
                          requested_by,request_reason,created_at
                        ) VALUES (
                          '019b1700-0000-7000-8000-00000000d104',
                          '019b1700-0000-7000-8000-00000000d101','LIVE_TRIAL','TRIAL',
                          '019b1700-0000-7000-8000-00000000d102',
                          '019b1700-0000-7000-8000-00000000d103',
                          '019b1700-0000-7000-8000-00000000d105',
                          '019b1700-0000-7000-8000-00000000da04',
                          'dynamic live trial',now()
                        );
                        INSERT INTO source_trial_run_result(
                          trial_run_id,status,quality_summary,raw_namespace,
                          completed_by,completed_at
                        ) VALUES (
                          '019b1700-0000-7000-8000-00000000d104','SUCCEEDED','{}'::jsonb,
                          'trial/r17-dynamic-runtime',
                          '019b1700-0000-7000-8000-00000000da06',now()
                        );
                        INSERT INTO source_governance_decision(
                          id,source_id,decision_type,outcome,policy_version_id,
                          connector_config_version_id,trial_run_id,submitted_by,decided_by,
                          reason,valid_until,created_at
                        ) VALUES (
                          '019b1700-0000-7000-8000-00000000d106',
                          '019b1700-0000-7000-8000-00000000d101',
                          'PRODUCTION_APPROVAL','APPROVED',
                          '019b1700-0000-7000-8000-00000000d102',
                          '019b1700-0000-7000-8000-00000000d103',
                          '019b1700-0000-7000-8000-00000000d104',
                          '019b1700-0000-7000-8000-00000000da04',
                          '019b1700-0000-7000-8000-00000000da07',
                          'dynamic production approval',now()+interval '8 days',now()
                        );
                        INSERT INTO round17_eventization_readiness(
                          id,source_id,policy_version_id,connector_config_version_id,
                          trial_run_id,production_decision_id,
                          business_parser_profile_version,business_parser_profile_sha256,
                          claim_evidence_profile_version,claim_evidence_profile_sha256,
                          event_identity_profile_version,event_identity_profile_sha256,
                          publication_projection_profile_version,
                          publication_projection_profile_sha256,
                          verification_manifest_ref,verification_manifest,
                          verification_manifest_sha256,verification_signature,
                          signer_public_key_sha256,
                          status,verified_by,verified_at
                        ) VALUES (
                          '019b1700-0000-7000-8000-00000000d150',
                          '019b1700-0000-7000-8000-00000000d101',
                          '019b1700-0000-7000-8000-00000000d102',
                          '019b1700-0000-7000-8000-00000000d103',
                          '019b1700-0000-7000-8000-00000000d104',
                          '019b1700-0000-7000-8000-00000000d106',
                          'fixture-business-parser-v1',repeat('5',64),
                          'fixture-claim-evidence-v1',repeat('6',64),
                          'fixture-event-identity-v1',repeat('7',64),
                          'fixture-publication-projection-v1',repeat('8',64),
                          'urn:srbg:round17-eventization-manifest:'
                            ||'019b1700-0000-7000-8000-00000000d150',
                          CAST(:manifest_json AS jsonb),:manifest_sha256,
                          :manifest_signature,:signer_sha256,'PASSED',
                          '019b1700-0000-7000-8000-00000000da07',now()
                        );
                        UPDATE source SET
                          lifecycle_state='ACTIVE',trial_kind=NULL,
                          current_policy_version_id='019b1700-0000-7000-8000-00000000d102',
                          current_connector_config_version_id='019b1700-0000-7000-8000-00000000d103',
                          current_trial_run_id='019b1700-0000-7000-8000-00000000d104',
                          updated_at=now()
                         WHERE id='019b1700-0000-7000-8000-00000000d101';
                        INSERT INTO fetch_schedule(
                          id,source_id,authority_level,status,interval_seconds,next_run_at,
                          freshness_slo_seconds,rate_limit_per_minute,daily_request_budget,
                          daily_byte_budget,budget_window_started_at,updated_at
                        ) VALUES (
                          '019b1700-0000-7000-8000-00000000d107',
                          '019b1700-0000-7000-8000-00000000d101','A1','ACTIVE',3600,now(),
                          28800,1,100,104857600,now(),now()
                        );
                        INSERT INTO round17_pilot_window(
                          id,roster_version,metric_definition_version,gold_definition_version,
                          baseline_commit,config_version,database_revision,environment,
                          duration_hours,state,version,blocker_codes,prepared_by,prepared_at,
                          idempotency_key
                        ) VALUES (
                          '019b1700-0000-7000-8000-00000000d140','r17-sources-v0.1',
                          'phase2-round17-metrics-v1.0.0','phase2-round17-gold-v1.0.0',
                          'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa','r17-dynamic-v1',
                          '0017c_round17_flat_pilot','PREPRODUCTION',168,'PREPARING',1,
                          '{}'::text[],'019b1700-0000-7000-8000-00000000da07',now(),
                          'r17-dynamic-runtime-window'
                        );
                        UPDATE round17_pilot_window
                           SET state='READY',version=2
                         WHERE id='019b1700-0000-7000-8000-00000000d140';
                        UPDATE round17_pilot_window
                           SET state='RUNNING',version=3,
                               started_by='019b1700-0000-7000-8000-00000000da07',
                               started_at=now()-interval '2 hours',
                               ends_at=now()-interval '2 hours'+interval '168 hours'
                         WHERE id='019b1700-0000-7000-8000-00000000d140';
                        INSERT INTO round17_pilot_window_source(
                          id,window_id,source_id,source_code,policy_version_id,
                          connector_config_version_id,schedule_id,schedule_version,
                          interval_seconds,freshness_slo_seconds,trial_run_id,
                          production_decision_id,eventization_readiness_id,
                          segment_number,status,created_at
                        ) VALUES (
                          '019b1700-0000-7000-8000-00000000d141',
                          '019b1700-0000-7000-8000-00000000d140',
                          '019b1700-0000-7000-8000-00000000d101','R17-DYNAMIC-001',
                          '019b1700-0000-7000-8000-00000000d102',
                          '019b1700-0000-7000-8000-00000000d103',
                          '019b1700-0000-7000-8000-00000000d107',1,3600,28800,
                          '019b1700-0000-7000-8000-00000000d104',
                          '019b1700-0000-7000-8000-00000000d106',
                          '019b1700-0000-7000-8000-00000000d150',
                          1,'PREPARING',now()
                        );
                        UPDATE round17_pilot_window_source
                           SET status='RUNNING',segment_started_at=now()-interval '2 hours',
                               segment_ends_at=now()-interval '2 hours'+interval '168 hours'
                         WHERE id='019b1700-0000-7000-8000-00000000d141';
                        INSERT INTO fetch_run(
                          id,trigger,status,started_at,request_id,source_id,schedule_id,
                          policy_version_id,connector_config_version_id,idempotency_key,
                          execution_domain,run_origin,execution_lease_token,
                          execution_lease_until,heartbeat_at
                        ) VALUES (
                          '019b1700-0000-7000-8000-00000000d108','SCHEDULED','RUNNING',
                          now()-interval '1 hour','r17-dynamic-runtime',
                          '019b1700-0000-7000-8000-00000000d101',
                          '019b1700-0000-7000-8000-00000000d107',
                          '019b1700-0000-7000-8000-00000000d102',
                          '019b1700-0000-7000-8000-00000000d103',
                          'r17-dynamic-runtime','PRODUCTION','SCHEDULED',
                          '019b1700-0000-7000-8000-00000000d109',
                          now()+interval '30 minutes',now()
                        )
                        """
                for seed_statement in seed_sql.split(";"):
                    if seed_statement.strip():
                        parameters: dict[str, str] = {}
                        if ":policy_json" in seed_statement:
                            parameters["policy_json"] = policy_json
                        if ":manifest_json" in seed_statement:
                            parameters.update(
                                {
                                    "manifest_json": manifest_json,
                                    "manifest_sha256": manifest_sha256,
                                    "manifest_signature": manifest_signature,
                                    "signer_sha256": signer_sha256,
                                }
                            )
                        await connection.execute(text(seed_statement), parameters)
                await _expect_runtime_rejection(
                    connection,
                    """
                    INSERT INTO round17_pilot_window_source(
                      id,window_id,source_id,source_code,policy_version_id,
                      connector_config_version_id,schedule_id,schedule_version,
                      interval_seconds,freshness_slo_seconds,trial_run_id,
                      production_decision_id,eventization_readiness_id,
                      segment_number,status,segment_started_at,segment_ends_at,
                      resumed_by,resume_reason,resume_request_id,created_at
                    ) VALUES (
                      '019b1700-0000-7000-8000-00000000d160',
                      '019b1700-0000-7000-8000-00000000d140',
                      '019b1700-0000-7000-8000-00000000d101','R17-DYNAMIC-001',
                      '019b1700-0000-7000-8000-00000000d102',
                      '019b1700-0000-7000-8000-00000000d103',
                      '019b1700-0000-7000-8000-00000000d107',1,3600,28800,
                      '019b1700-0000-7000-8000-00000000d104',
                      '019b1700-0000-7000-8000-00000000d106',
                      '019b1700-0000-7000-8000-00000000d150',2,'RUNNING',now(),
                      (SELECT ends_at FROM round17_pilot_window
                        WHERE id='019b1700-0000-7000-8000-00000000d140'),
                      '019b1700-0000-7000-8000-00000000da07',
                      'attempt resume without a paused predecessor',
                      'r17-invalid-resume-without-pause',now()
                    )
                    """,
                    "resumed segment accepted without a paused predecessor",
                )
                await connection.execute(
                    text(
                        """INSERT INTO round17_operator_task(
                              id,window_id,source_id,category,assigned_to,status,
                              created_by,created_at,version
                            ) VALUES (
                              '019b1700-0000-7000-8000-00000000d160',
                              '019b1700-0000-7000-8000-00000000d140',
                              '019b1700-0000-7000-8000-00000000d101',
                              'SOURCE_MAINTENANCE',
                              '019b1700-0000-7000-8000-00000000da08','PENDING',
                              '019b1700-0000-7000-8000-00000000da07',
                              now()-interval '10 minutes',1
                            )"""
                    )
                )
                await connection.execute(
                    text(
                        """SELECT start_round17_operator_task(
                              '019b1700-0000-7000-8000-00000000d160',
                              '019b1700-0000-7000-8000-00000000d161',
                              '019b1700-0000-7000-8000-00000000da08',
                              now()-interval '10 minutes'
                            )"""
                    )
                )
                await connection.execute(
                    text(
                        """UPDATE round17_operator_work_session
                               SET last_activity_at=now()-interval '5 minutes',
                                   stopped_at=now(),accrued_seconds=300,
                                   active_seconds=300,version=2
                             WHERE id='019b1700-0000-7000-8000-00000000d161'"""
                    )
                )
                await _expect_runtime_rejection(
                    connection,
                    """INSERT INTO round17_operator_work_correction(
                          id,session_id,actor_id,corrected_by,previous_seconds,
                          corrected_seconds,reason_code,corrected_at
                        ) VALUES (
                          '019b1700-0000-7000-8000-00000000d162',
                          '019b1700-0000-7000-8000-00000000d161',
                          '019b1700-0000-7000-8000-00000000da08',
                          '019b1700-0000-7000-8000-00000000da08',300,240,
                          'TIMER_INTERRUPTED',now()
                        )""",
                    "self-correction of yinzi operator evidence was accepted",
                )
                await connection.execute(
                    text(
                        """INSERT INTO round17_operator_work_correction(
                              id,session_id,actor_id,corrected_by,previous_seconds,
                              corrected_seconds,reason_code,corrected_at
                            ) VALUES (
                              '019b1700-0000-7000-8000-00000000d163',
                              '019b1700-0000-7000-8000-00000000d161',
                              '019b1700-0000-7000-8000-00000000da08',
                              '019b1700-0000-7000-8000-00000000da07',300,240,
                              'TIMER_INTERRUPTED',now()
                            )"""
                    )
                )
                completed_task = await connection.scalar(
                    text(
                        """SELECT complete_round17_operator_task(
                              '019b1700-0000-7000-8000-00000000d160',2,
                              '019b1700-0000-7000-8000-00000000da07',now()
                            )"""
                    )
                )
                if str(completed_task) != "019b1700-0000-7000-8000-00000000d160":
                    raise RuntimeError("Round17 operator task lifecycle is incomplete")
                await connection.execute(text("SET LOCAL ROLE srbg_worker_role"))
                raw = (
                    await connection.execute(
                        text(
                            """
                            SELECT raw_object_id,capture_id
                              FROM record_scheduled_source_raw(
                                '019b1700-0000-7000-8000-00000000d110',
                                '019b1700-0000-7000-8000-00000000d111',
                                '019b1700-0000-7000-8000-00000000d101',
                                '019b1700-0000-7000-8000-00000000d108',
                                repeat('1',64),repeat('2',64),
                                'sha256/11/'||repeat('1',64),'dynamic-etag',32,
                                'text/html','text/html','CLEAN',NULL,
                                'https://source.example.test/document.html',
                                'https://source.example.test/document.html','[]'::jsonb,
                                200,NULL,NULL,now()
                              )
                            """
                        )
                    )
                ).one()
                if str(raw.raw_object_id) != "019b1700-0000-7000-8000-00000000d110":
                    raise RuntimeError("Round17 raw function returned the wrong object")
                if str(raw.capture_id) != "019b1700-0000-7000-8000-00000000d111":
                    raise RuntimeError("Round17 raw function returned the wrong capture")

                version_id = await connection.scalar(
                    text(
                        """
                        SELECT record_scheduled_source_document(
                          '019b1700-0000-7000-8000-00000000d112',
                          '019b1700-0000-7000-8000-00000000d113',
                          '019b1700-0000-7000-8000-00000000d114',
                          '019b1700-0000-7000-8000-00000000d115',
                          '019b1700-0000-7000-8000-00000000d116',
                          '019b1700-0000-7000-8000-00000000d101',
                          '019b1700-0000-7000-8000-00000000d108',
                          '019b1700-0000-7000-8000-00000000d110',
                          '019b1700-0000-7000-8000-00000000d111',
                          'https://source.example.test/document.html','HTML',repeat('1',64),
                          'dynamic.html','Dynamic document',now()
                        )
                        """
                    )
                )
                if str(version_id) != "019b1700-0000-7000-8000-00000000d113":
                    raise RuntimeError("Round17 document function returned the wrong version")
                evidence = (
                    await connection.execute(
                        text(
                            """
                            SELECT capture.response_sha256,raw.sha256,document.current_version_id,
                                   count(state.id) AS state_count,
                                   bool_or(state.state='READY') AS ready
                              FROM raw_object_capture capture
                              JOIN raw_object raw ON raw.id=capture.raw_object_id
                              JOIN document_version version
                                ON version.raw_object_capture_id=capture.id
                              JOIN document ON document.id=version.document_id
                              JOIN document_version_state_event state
                                ON state.document_version_id=version.id
                             WHERE capture.id='019b1700-0000-7000-8000-00000000d111'
                             GROUP BY capture.response_sha256,raw.sha256,
                                      document.current_version_id
                            """
                        )
                    )
                ).one()
                if (
                    evidence.response_sha256 != "2" * 64
                    or evidence.sha256 != "1" * 64
                    or str(evidence.current_version_id)
                    != "019b1700-0000-7000-8000-00000000d113"
                    or evidence.state_count != 3
                    or evidence.ready is not True
                ):
                    raise RuntimeError("Round17 runtime evidence chain is incomplete")

                await _expect_runtime_rejection(
                    connection,
                    """
                    SELECT * FROM record_scheduled_source_raw(
                      '019b1700-0000-7000-8000-00000000d120',
                      '019b1700-0000-7000-8000-00000000d121',
                      '019b1700-0000-7000-8000-00000000d101',
                      '019b1700-0000-7000-8000-00000000d108',
                      repeat('3',64),repeat('4',64),'sha256/33/'||repeat('3',64),
                      'dynamic-etag',32,'text/html','text/html','CLEAN',NULL,
                      'https://source.example.test/document.html',
                      'https://other.example.test/document.html','[]'::jsonb,
                      200,NULL,NULL,now())
                    """,
                )
                await _expect_runtime_rejection(
                    connection,
                    """
                    SELECT * FROM record_scheduled_source_raw(
                      '019b1700-0000-7000-8000-00000000d122',
                      '019b1700-0000-7000-8000-00000000d123',
                      '019b1700-0000-7000-8000-00000000d101',
                      '019b1700-0000-7000-8000-00000000d108',
                      repeat('5',64),repeat('6',64),'sha256/55/'||repeat('5',64),
                      'dynamic-etag',32,'text/html','text/html','CLEAN',NULL,
                      'https://source.example.test/document.html',
                      'https://source.example.test/document.html','[]'::jsonb,
                      200,NULL,NULL,now()+interval '2 hours')
                    """,
                )

                rejected = (
                    await connection.execute(
                        text(
                            """
                            SELECT * FROM record_scheduled_source_raw(
                              '019b1700-0000-7000-8000-00000000d124',
                              '019b1700-0000-7000-8000-00000000d125',
                              '019b1700-0000-7000-8000-00000000d101',
                              '019b1700-0000-7000-8000-00000000d108',
                              repeat('7',64),repeat('8',64),
                              'sha256/77/'||repeat('7',64),'dynamic-etag',32,
                              'text/html','text/html','REJECTED','MALWARE_DETECTED',
                              'https://source.example.test/rejected.html',
                              'https://source.example.test/rejected.html','[]'::jsonb,
                              200,NULL,NULL,now())
                            """
                        )
                    )
                ).one()
                await _expect_runtime_rejection(
                    connection,
                    f"""
                    SELECT record_scheduled_source_document(
                      '019b1700-0000-7000-8000-00000000d126',
                      '019b1700-0000-7000-8000-00000000d127',
                      '019b1700-0000-7000-8000-00000000d128',
                      '019b1700-0000-7000-8000-00000000d129',
                      '019b1700-0000-7000-8000-00000000d130',
                      '019b1700-0000-7000-8000-00000000d101',
                      '019b1700-0000-7000-8000-00000000d108',
                      '{rejected.raw_object_id}','{rejected.capture_id}',
                      'https://source.example.test/rejected.html','HTML',repeat('7',64),
                      'rejected.html','Rejected document',now())
                    """,
                )
                await connection.execute(text("RESET ROLE"))
                await connection.execute(
                    text(
                        """UPDATE fetch_run
                              SET execution_lease_until=now()-interval '15 minutes'
                            WHERE id='019b1700-0000-7000-8000-00000000d108'"""
                    )
                )
                await connection.execute(text("SET LOCAL ROLE srbg_worker_role"))
                await _expect_runtime_rejection(
                    connection,
                    """
                    SELECT * FROM record_scheduled_source_raw(
                      '019b1700-0000-7000-8000-00000000d131',
                      '019b1700-0000-7000-8000-00000000d132',
                      '019b1700-0000-7000-8000-00000000d101',
                      '019b1700-0000-7000-8000-00000000d108',
                      repeat('9',64),repeat('a',64),'sha256/99/'||repeat('9',64),
                      'dynamic-etag',32,'text/html','text/html','CLEAN',NULL,
                      'https://source.example.test/expired.html',
                      'https://source.example.test/expired.html','[]'::jsonb,
                      200,NULL,NULL,now()-interval '30 minutes')
                    """,
                    "expired lease accepted a backdated raw capture",
                )
                await _expect_runtime_rejection(
                    connection,
                    """
                    SELECT record_scheduled_source_document(
                      '019b1700-0000-7000-8000-00000000d133',
                      '019b1700-0000-7000-8000-00000000d134',
                      '019b1700-0000-7000-8000-00000000d135',
                      '019b1700-0000-7000-8000-00000000d136',
                      '019b1700-0000-7000-8000-00000000d137',
                      '019b1700-0000-7000-8000-00000000d101',
                      '019b1700-0000-7000-8000-00000000d108',
                      '019b1700-0000-7000-8000-00000000d110',
                      '019b1700-0000-7000-8000-00000000d111',
                      'https://source.example.test/document.html','HTML',repeat('1',64),
                      'expired.html','Expired lease document',now())
                    """,
                    "expired lease accepted document materialization",
                )
                await connection.execute(text("RESET ROLE"))
                await connection.execute(
                    text(
                        """UPDATE fetch_run
                              SET execution_lease_until=now()+interval '30 minutes'
                            WHERE id='019b1700-0000-7000-8000-00000000d108'"""
                    )
                )
                await connection.execute(
                    text(
                        """UPDATE fetch_schedule
                              SET version=2,updated_at=statement_timestamp()
                            WHERE id='019b1700-0000-7000-8000-00000000d107'"""
                    )
                )
                paused_status = await connection.scalar(
                    text(
                        "SELECT status FROM round17_pilot_window_source "
                        "WHERE id='019b1700-0000-7000-8000-00000000d141'"
                    )
                )
                if paused_status != "PAUSED":
                    raise RuntimeError("schedule change did not pause the active source segment")
                await connection.execute(
                    text(
                        """INSERT INTO round17_pilot_window_source(
                              id,window_id,source_id,source_code,policy_version_id,
                              connector_config_version_id,schedule_id,schedule_version,
                              interval_seconds,freshness_slo_seconds,trial_run_id,
                              production_decision_id,eventization_readiness_id,
                              segment_number,status,segment_started_at,segment_ends_at,
                              resumed_by,resume_reason,resume_request_id,created_at
                            ) VALUES (
                              '019b1700-0000-7000-8000-00000000d164',
                              '019b1700-0000-7000-8000-00000000d140',
                              '019b1700-0000-7000-8000-00000000d101',
                              'R17-DYNAMIC-001',
                              '019b1700-0000-7000-8000-00000000d102',
                              '019b1700-0000-7000-8000-00000000d103',
                              '019b1700-0000-7000-8000-00000000d107',2,3600,28800,
                              '019b1700-0000-7000-8000-00000000d104',
                              '019b1700-0000-7000-8000-00000000d106',
                              '019b1700-0000-7000-8000-00000000d150',2,'RUNNING',now(),
                              (SELECT ends_at FROM round17_pilot_window
                                WHERE id='019b1700-0000-7000-8000-00000000d140'),
                              '019b1700-0000-7000-8000-00000000da07',
                              'resume after isolated schedule authority repair',
                              'r17-valid-resume-after-schedule-change',now()
                            )"""
                    )
                )
                await connection.execute(text("SET LOCAL ROLE srbg_worker_role"))
                await _expect_runtime_rejection(
                    connection,
                    """
                    SELECT * FROM record_scheduled_source_raw(
                      '019b1700-0000-7000-8000-00000000d138',
                      '019b1700-0000-7000-8000-00000000d139',
                      '019b1700-0000-7000-8000-00000000d101',
                      '019b1700-0000-7000-8000-00000000d108',
                      repeat('c',64),repeat('d',64),'sha256/cc/'||repeat('c',64),
                      'dynamic-etag',32,'text/html','text/html','CLEAN',NULL,
                      'https://source.example.test/paused.html',
                      'https://source.example.test/paused.html','[]'::jsonb,
                      200,NULL,NULL,now())
                    """,
                    "paused source segment accepted raw capture",
                )
                await _expect_runtime_rejection(
                    connection,
                    """
                    SELECT record_scheduled_source_document(
                      '019b1700-0000-7000-8000-00000000d142',
                      '019b1700-0000-7000-8000-00000000d143',
                      '019b1700-0000-7000-8000-00000000d144',
                      '019b1700-0000-7000-8000-00000000d145',
                      '019b1700-0000-7000-8000-00000000d146',
                      '019b1700-0000-7000-8000-00000000d101',
                      '019b1700-0000-7000-8000-00000000d108',
                      '019b1700-0000-7000-8000-00000000d110',
                      '019b1700-0000-7000-8000-00000000d111',
                      'https://source.example.test/document.html','HTML',repeat('1',64),
                      'paused.html','Paused segment document',now())
                    """,
                    "paused source segment accepted document materialization",
                )
            finally:
                await transaction.rollback()
    finally:
        await engine.dispose()


async def _verify_round17_absent(database_url: str) -> None:
    engine = create_async_engine(database_url)
    try:
        async with engine.connect() as connection:
            if await _current_revisions(connection) != (BASE_REVISION,):
                raise RuntimeError("Round17 downgrade did not return to Round16")
            for table in EXPECTED_TABLES:
                relation = await connection.scalar(
                    text("SELECT to_regclass(:name)"), {"name": f"public.{table}"}
                )
                if relation is not None:
                    raise RuntimeError(f"Round17 table survived empty downgrade: {table}")
            for signature in _ROUND17_ONLY_FUNCTIONS:
                function = await connection.scalar(
                    text("SELECT to_regprocedure(:signature)"),
                    {"signature": f"public.{signature}"},
                )
                if function is not None:
                    raise RuntimeError(f"Round17 function survived empty downgrade: {signature}")
            for signature in _COMPATIBILITY_WRAPPERS:
                function = await connection.scalar(
                    text("SELECT to_regprocedure(:signature)"),
                    {"signature": f"public.{signature}"},
                )
                if function is None:
                    raise RuntimeError(
                        f"Round16 compatibility function was not restored: {signature}"
                    )
            column_count = await connection.scalar(
                text(
                    """
                    SELECT count(*) FROM information_schema.columns
                     WHERE table_schema='public' AND table_name='fetch_run'
                       AND column_name IN (
                         'run_origin','replayed_from_run_id','pilot_window_source_id'
                       )
                    """
                )
            )
            if column_count != 0:
                raise RuntimeError("Round17 fetch-run columns survived empty downgrade")
    finally:
        await engine.dispose()


async def _seed_guard_fact(database_url: str) -> None:
    engine = create_async_engine(database_url)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    """
                    INSERT INTO round17_pilot_window(
                      id,roster_version,metric_definition_version,gold_definition_version,
                      baseline_commit,config_version,database_revision,environment,
                      duration_hours,state,version,blocker_codes,prepared_by,prepared_at,
                      idempotency_key
                    ) VALUES (
                      CAST(:id AS uuid),'r17-migration-guard','round17-migration-guard',
                      'round17-migration-guard','b08513965e931f363283384037fc1c1f068a1b1c',
                      'r17-migration-guard','0017c_round17_flat_pilot','PREPRODUCTION',168,
                      'PREPARING',1,ARRAY['ISOLATED_MIGRATION_GUARD']::text[],
                      '019b1700-0000-7000-8000-00000000a017',now(),
                      'round17-isolated-migration-guard'
                    )
                    """
                ),
                {"id": _GUARD_WINDOW_ID},
            )
    finally:
        await engine.dispose()


async def _delete_guard_fact(database_url: str) -> None:
    engine = create_async_engine(database_url)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text("DELETE FROM round17_pilot_window WHERE id=CAST(:id AS uuid)"),
                {"id": _GUARD_WINDOW_ID},
            )
    finally:
        await engine.dispose()


async def _seed_projection_contract_fixture(database_url: str) -> None:
    """Seed only the disposable DB used by deterministic projection boundary tests."""

    engine = create_async_engine(database_url)
    fixture_sql = """
    INSERT INTO source(
      id,registry_code,name,base_url,channel,source_type,authority_level,priority,
      collection_method,poll_interval_minutes,owner,state,enabled,created_at,updated_at,
      lifecycle_state
    ) VALUES (
      '019b1700-0000-7000-8000-00000000f101','R17-PROJECTION-FIXTURE',
      'Round17 isolated projection fixture','https://fixture.example.test/','SAFETY',
      'government','A1','P2','fixture',1440,'ci','CANDIDATE',false,now(),now(),'CANDIDATE'
    );
    INSERT INTO source_policy(
      id,source_id,policy_version,status,document,document_sha256,valid_until,
      created_by,created_at
    ) VALUES (
      '019b1700-0000-7000-8000-00000000f102',
      '019b1700-0000-7000-8000-00000000f101','round17-projection-fixture-v1','VALID',
      '{"fixture_scope":"isolated_contract_test"}'::jsonb,
      encode(sha256(convert_to('{"fixture_scope":"isolated_contract_test"}','UTF8')),'hex'),
      now()+interval '1 day','019b1700-0000-7000-8000-00000000fa01',now()
    );
    INSERT INTO raw_object(
      id,sha256,object_key,byte_size,declared_mime,detected_mime,scan_status,storage_etag,
      created_at
    ) VALUES
    (
      '019b1700-0000-7000-8000-00000000f110',
      encode(sha256(convert_to('round17 projection metadata','UTF8')),'hex'),
      'fixture/round17/projection-metadata',27,'application/pdf','application/pdf','CLEAN',
      'fixture-metadata',now()
    ),
    (
      '019b1700-0000-7000-8000-00000000f120',
      encode(sha256(convert_to('round17 projection full','UTF8')),'hex'),
      'fixture/round17/projection-full',23,'application/pdf','application/pdf','CLEAN',
      'fixture-full',now()
    );
    INSERT INTO document(
      id,source_id,canonical_url,document_kind,first_discovered_at,admission_fixture
    ) VALUES
    (
      '019b1700-0000-7000-8000-00000000f111',
      '019b1700-0000-7000-8000-00000000f101',
      'https://fixture.example.test/metadata.pdf','PDF',now(),true
    ),
    (
      '019b1700-0000-7000-8000-00000000f121',
      '019b1700-0000-7000-8000-00000000f101',
      'https://fixture.example.test/full.pdf','PDF',now(),true
    );
    INSERT INTO document_version(
      id,document_id,raw_object_id,version_number,content_hash,original_filename,title,
      acquired_at,execution_domain
    ) VALUES
    (
      '019b1700-0000-7000-8000-00000000f112',
      '019b1700-0000-7000-8000-00000000f111',
      '019b1700-0000-7000-8000-00000000f110',1,
      encode(sha256(convert_to('round17 projection metadata','UTF8')),'hex'),
      'metadata.pdf','待审核元数据投影夹具',now(),'LEGACY'
    ),
    (
      '019b1700-0000-7000-8000-00000000f122',
      '019b1700-0000-7000-8000-00000000f121',
      '019b1700-0000-7000-8000-00000000f120',1,
      encode(sha256(convert_to('round17 projection full','UTF8')),'hex'),
      'full.pdf','已发布完整投影夹具',now(),'LEGACY'
    );
    UPDATE document SET current_version_id='019b1700-0000-7000-8000-00000000f112'
     WHERE id='019b1700-0000-7000-8000-00000000f111';
    UPDATE document SET current_version_id='019b1700-0000-7000-8000-00000000f122'
     WHERE id='019b1700-0000-7000-8000-00000000f121';
    INSERT INTO document_page(
      id,document_version_id,page_number,width_mpt,height_mpt,rotation,text_source,
      normalized_text_sha256,preview_object_key,preview_sha256,preview_mime,created_at
    ) VALUES (
      '019b1700-0000-7000-8000-00000000f123',
      '019b1700-0000-7000-8000-00000000f122',1,595000,842000,0,'NATIVE',
      encode(sha256(convert_to('verified fact','UTF8')),'hex'),
      'fixture/round17/preview.png',
      encode(sha256(convert_to('round17 preview','UTF8')),'hex'),'image/png',now()
    );
    INSERT INTO document_text_block(
      id,document_page_id,block_index,block_kind,text_source,text,normalized_text,text_sha256,
      x0_mpt,y0_mpt,x1_mpt,y1_mpt,confidence_bps,created_at
    ) VALUES (
      '019b1700-0000-7000-8000-00000000f124',
      '019b1700-0000-7000-8000-00000000f123',0,'BODY','NATIVE','verified fact',
      'verified fact',encode(sha256(convert_to('verified fact','UTF8')),'hex'),
      0,0,595000,842000,10000,now()
    );
    INSERT INTO intelligence_item(
      id,source_id,primary_document_id,current_document_version_id,item_type,channel,
      risk_level,title,original_url,source_published_at,first_discovered_at,activity_at,
      processing_status,review_status,submitted_by,is_demo,publishable,created_at,updated_at,
      publication_risk_tier,content_severity,projection_level
    ) VALUES
    (
      '019b1700-0000-7000-8000-00000000f113',
      '019b1700-0000-7000-8000-00000000f101',
      '019b1700-0000-7000-8000-00000000f111',
      '019b1700-0000-7000-8000-00000000f112','SAFETY_REGULATION','SAFETY','R3',
      '待审核元数据投影夹具','https://fixture.example.test/metadata.pdf',now(),now(),now(),
      'READY_FOR_REVIEW','PENDING','019b1700-0000-7000-8000-00000000fa01',true,true,
      now(),now(),'R3','MODERATE','NONE'
    ),
    (
      '019b1700-0000-7000-8000-00000000f125',
      '019b1700-0000-7000-8000-00000000f101',
      '019b1700-0000-7000-8000-00000000f121',
      '019b1700-0000-7000-8000-00000000f122','SAFETY_REGULATION','SAFETY','R2',
      '已发布完整投影夹具','https://fixture.example.test/full.pdf',now(),now(),now(),
      'READY_FOR_REVIEW','APPROVED','019b1700-0000-7000-8000-00000000fa01',true,true,
      now(),now(),'R2','LOW','NONE'
    );
    INSERT INTO review_task(
      id,item_id,document_version_id,source_policy_id,risk_level,status,submitted_by,
      submitted_at,assigned_to,decided_by,decided_at,decision_reason,created_at,task_type
    ) VALUES (
      '019b1700-0000-7000-8000-00000000f126',
      '019b1700-0000-7000-8000-00000000f125',
      '019b1700-0000-7000-8000-00000000f122',
      '019b1700-0000-7000-8000-00000000f102','R2','APPROVED',
      '019b1700-0000-7000-8000-00000000fa01',now(),
      '019b1700-0000-7000-8000-00000000fa02',
      '019b1700-0000-7000-8000-00000000fa02',now(),
      'isolated projection contract fixture',now(),'CONTENT_REVIEW'
    );
    INSERT INTO claim(
      id,item_id,document_version_id,claim_type,subject,predicate,literal_value,
      verification_status,critical,created_at
    ) VALUES (
      '019b1700-0000-7000-8000-00000000f129',
      '019b1700-0000-7000-8000-00000000f125',
      '019b1700-0000-7000-8000-00000000f122','one_sentence_fact','fixture','states',
      to_jsonb('verified fact'::text),'ACCEPTED',true,now()
    );
    INSERT INTO claim_evidence(
      id,claim_id,document_version_id,evidence_role,paragraph_id,char_start,char_end,excerpt,
      excerpt_sha256,original_url,created_at,locator_type,page_number,
      document_text_block_id,confidence_bps
    ) VALUES (
      '019b1700-0000-7000-8000-00000000f130',
      '019b1700-0000-7000-8000-00000000f129',
      '019b1700-0000-7000-8000-00000000f122','PRIMARY_OFFICIAL',NULL,NULL,NULL,
      'verified fact',encode(sha256(convert_to('verified fact','UTF8')),'hex'),
      'https://fixture.example.test/full.pdf',now(),'PDF_TEXT',1,
      '019b1700-0000-7000-8000-00000000f124',10000
    );
    INSERT INTO publication(id,item_id,status,published_at,updated_at) VALUES (
      '019b1700-0000-7000-8000-00000000f127',
      '019b1700-0000-7000-8000-00000000f125','PUBLISHED',now(),now()
    );
    INSERT INTO publication_revision(
      id,publication_id,revision_number,document_version_id,source_policy_id,
      source_policy_sha256,review_task_id,snapshot,evaluation,evaluation_sha256,action,
      valid,created_by,created_at
    ) VALUES (
      '019b1700-0000-7000-8000-00000000f128',
      '019b1700-0000-7000-8000-00000000f127',1,
      '019b1700-0000-7000-8000-00000000f122',
      '019b1700-0000-7000-8000-00000000f102',
      encode(sha256(convert_to('{"fixture_scope":"isolated_contract_test"}','UTF8')),'hex'),
      '019b1700-0000-7000-8000-00000000f126',
      '{"one_sentence_fact":"verified fact",
        "type_summary":{"kind":"SAFETY_REGULATION",
        "document_number":"R17-FIXTURE",
        "issuing_authority":"Fixture Authority",
        "regulation_status":"EFFECTIVE",
        "classification":"STANDARD_OR_GUIDE"}}'::jsonb,
      '{}'::jsonb,encode(sha256(convert_to('{}','UTF8')),'hex'),'PUBLISH',true,
      '019b1700-0000-7000-8000-00000000fa02',now()
    );
    UPDATE publication SET current_revision_id='019b1700-0000-7000-8000-00000000f128'
     WHERE id='019b1700-0000-7000-8000-00000000f127';
    """
    try:
        async with engine.begin() as connection:
            for statement in fixture_sql.split(";"):
                if statement.strip():
                    await connection.execute(text(statement))
    finally:
        await engine.dispose()


def _verify_repository_has_single_head(config: Config) -> None:
    heads = tuple(ScriptDirectory.from_config(config).get_heads())
    if heads != (HEAD_REVISION,):
        raise RuntimeError(f"migration repository must have one Round17 head, got {heads}")


def main() -> None:
    database_url = os.environ["SRBG_DATABASE_URL"]
    validate_disposable_database_url(database_url)
    config_path = Path("apps/api/alembic.ini")
    config = Config(str(config_path))
    _verify_repository_has_single_head(config)

    command.upgrade(config, BASE_REVISION)
    asyncio.run(_assert_database_revision(database_url, BASE_REVISION))
    command.upgrade(config, HEAD_REVISION)
    asyncio.run(_verify_head(database_url))
    asyncio.run(_verify_scheduled_runtime_functions(database_url))

    command.downgrade(config, BASE_REVISION)
    asyncio.run(_verify_round17_absent(database_url))
    command.upgrade(config, HEAD_REVISION)
    asyncio.run(_verify_head(database_url))

    asyncio.run(_seed_guard_fact(database_url))
    try:
        command.downgrade(config, BASE_REVISION)
    except RuntimeError as exc:
        if "0017B_DOWNGRADE_BLOCKED" not in str(exc):
            raise
    else:
        raise RuntimeError("Round17 downgrade did not protect an authoritative pilot fact")
    asyncio.run(_assert_database_revision(database_url, HEAD_REVISION))
    asyncio.run(_delete_guard_fact(database_url))
    asyncio.run(_verify_head(database_url))
    asyncio.run(_seed_projection_contract_fixture(database_url))

    print(
        "Round17 migration replay passed: 0016 -> 0017c -> 0016 -> 0017c; "
        "single head, role boundaries, signatures, constraints, scheduled raw/document "
        "runtime chain, adversarial denials, guarded downgrade, and isolated projection "
        "contract fixture verified"
    )


if __name__ == "__main__":
    main()
