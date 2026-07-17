"""PERS-03 personal stream runtime authority and self-healing health.

Revision ID: 0023_personal_source_runtime
Revises: 0022_personal_source_streams
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql
from srbg_api.identifiers import uuid7

revision = "0023_personal_source_runtime"
down_revision = "0022_personal_source_streams"
branch_labels = None
depends_on = None


def _uuid() -> postgresql.UUID:
    return postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.execute("ALTER TABLE fetch_schedule DROP CONSTRAINT IF EXISTS fetch_schedule_source_id_key")
    op.add_column("fetch_schedule", sa.Column("source_stream_id", _uuid()))
    op.add_column("fetch_schedule", sa.Column("stream_config_version_id", _uuid()))
    op.add_column(
        "fetch_schedule",
        sa.Column(
            "authority_mode",
            sa.String(30),
            nullable=False,
            server_default="LEGACY_GOVERNED",
        ),
    )
    op.add_column(
        "fetch_schedule",
        sa.Column("access_state", sa.String(20), nullable=False, server_default="ACCESSIBLE"),
    )
    op.add_column(
        "fetch_schedule",
        sa.Column("self_heal_state", sa.String(30), nullable=False, server_default="NONE"),
    )
    op.add_column("fetch_schedule", sa.Column("next_self_heal_at", sa.DateTime(timezone=True)))
    op.add_column(
        "fetch_schedule",
        sa.Column("consecutive_zero_discovery", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "fetch_schedule",
        sa.Column("zero_update_streak", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "fetch_schedule", sa.Column("last_successful_fetch_at", sa.DateTime(timezone=True))
    )
    op.add_column(
        "fetch_schedule", sa.Column("last_content_discovered_at", sa.DateTime(timezone=True))
    )
    op.add_column(
        "fetch_schedule",
        sa.Column("health_status", sa.String(20), nullable=False, server_default="UNKNOWN"),
    )
    op.add_column("fetch_schedule", sa.Column("health_reason", sa.String(60)))
    op.create_foreign_key(
        "fk_fetch_schedule_source_stream",
        "fetch_schedule",
        "source_stream",
        ["source_stream_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_fetch_schedule_stream_config",
        "fetch_schedule",
        "stream_config_version",
        ["stream_config_version_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        "uq_fetch_schedule_legacy_source",
        "fetch_schedule",
        ["source_id"],
        unique=True,
        postgresql_where=sa.text("source_stream_id IS NULL"),
    )
    op.create_index(
        "uq_fetch_schedule_personal_stream",
        "fetch_schedule",
        ["source_stream_id"],
        unique=True,
        postgresql_where=sa.text("source_stream_id IS NOT NULL"),
    )
    op.create_check_constraint(
        "ck_fetch_schedule_authority_mode",
        "fetch_schedule",
        "authority_mode IN ('LEGACY_GOVERNED','PERSONAL_STREAM')",
    )
    op.create_check_constraint(
        "ck_fetch_schedule_access_state",
        "fetch_schedule",
        "access_state IN ('ACCESSIBLE','INACCESSIBLE')",
    )
    op.create_check_constraint(
        "ck_fetch_schedule_self_heal_state",
        "fetch_schedule",
        "self_heal_state IN ('NONE','CIRCUIT_WAIT','HALF_OPEN_PROBE','REPROBE_QUEUED','REPROBING')",
    )
    op.create_check_constraint(
        "ck_fetch_schedule_personal_binding",
        "fetch_schedule",
        "(authority_mode='LEGACY_GOVERNED' AND source_stream_id IS NULL "
        "AND stream_config_version_id IS NULL) OR "
        "(authority_mode='PERSONAL_STREAM' AND source_stream_id IS NOT NULL "
        "AND stream_config_version_id IS NOT NULL)",
    )

    for table in ("fetch_run", "source_health_snapshot", "source_anomaly"):
        op.add_column(table, sa.Column("source_stream_id", _uuid()))
        op.create_foreign_key(
            f"fk_{table}_personal_stream",
            table,
            "source_stream",
            ["source_stream_id"],
            ["id"],
            ondelete="RESTRICT",
        )
    op.add_column("fetch_run", sa.Column("stream_config_version_id", _uuid()))
    op.create_foreign_key(
        "fk_fetch_run_stream_config",
        "fetch_run",
        "stream_config_version",
        ["stream_config_version_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.add_column("source_health_snapshot", sa.Column("reason_code", sa.String(60)))
    op.add_column("source_health_snapshot", sa.Column("http_status", sa.Integer()))
    op.add_column(
        "source_health_snapshot",
        sa.Column("new_content_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column("source_health_snapshot", sa.Column("next_interval_seconds", sa.Integer()))
    op.add_column("source_health_snapshot", sa.Column("circuit_state", sa.String(20)))
    op.add_column("source_health_snapshot", sa.Column("self_heal_state", sa.String(30)))
    op.create_index(
        "ix_source_health_stream_observed",
        "source_health_snapshot",
        ["source_stream_id", "observed_at"],
    )

    _backfill_personal_schedules()
    _replace_claim_function()
    _replace_runtime_persistence_functions()
    op.execute(
        "GRANT SELECT,INSERT,UPDATE ON fetch_schedule,source_health_snapshot,source_anomaly "
        "TO srbg_worker_role"
    )


def _backfill_personal_schedules() -> None:
    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            """
            SELECT stream.id AS stream_id,stream.source_id,config.id AS config_id,
                   source.desired_enabled,source.manual_disabled_at
              FROM source_stream stream
              JOIN source ON source.id=stream.source_id
              JOIN stream_config_version config
                ON config.stream_id=stream.id AND config.config_sha256=stream.config_sha256
             WHERE stream.status='READY' AND source.normalized_origin IS NOT NULL
               AND NOT EXISTS (
                 SELECT 1 FROM fetch_schedule schedule
                  WHERE schedule.source_stream_id=stream.id
               )
             ORDER BY stream.id,config.created_at DESC
            """
        )
    ).mappings()
    seen: set[object] = set()
    for row in rows:
        if row["stream_id"] in seen:
            continue
        seen.add(row["stream_id"])
        schedule_id = uuid7()
        bind.execute(
            sa.text(
                """
                INSERT INTO fetch_schedule(
                  id,source_id,source_stream_id,stream_config_version_id,authority_mode,
                  authority_level,status,interval_seconds,next_run_at,
                  backoff_base_seconds,backoff_cap_seconds,max_attempts,
                  consecutive_failures,circuit_state,freshness_slo_seconds,
                  rate_limit_per_minute,daily_request_budget,daily_byte_budget,
                  requests_used,bytes_used,budget_window_started_at,version,updated_at
                ) VALUES(
                  :id,:source_id,:stream_id,:config_id,'PERSONAL_STREAM','PERSONAL',
                  :status,3600,now(),30,21600,3,0,'CLOSED',86400,6,500,536870912,
                  0,0,now(),1,now()
                )
                """
            ),
            {
                "id": schedule_id,
                "source_id": row["source_id"],
                "stream_id": row["stream_id"],
                "config_id": row["config_id"],
                "status": (
                    "ACTIVE"
                    if row["desired_enabled"] and row["manual_disabled_at"] is None
                    else "PAUSED"
                ),
            },
        )
        bind.execute(
            sa.text("UPDATE source_stream SET schedule_id=:schedule WHERE id=:stream"),
            {"schedule": schedule_id, "stream": row["stream_id"]},
        )


def _replace_claim_function() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION claim_due_fetch_schedule(
          p_now timestamptz,p_lease_until timestamptz,p_token uuid
        ) RETURNS TABLE(schedule_id uuid,source_id uuid)
        LANGUAGE sql SECURITY DEFINER
        SET search_path=pg_catalog,public AS $$
          WITH due AS (
            SELECT schedule.id,schedule.source_id
              FROM fetch_schedule schedule
              JOIN source source_row ON source_row.id=schedule.source_id
              LEFT JOIN source_stream stream ON stream.id=schedule.source_stream_id
              LEFT JOIN stream_config_version stream_config
                ON stream_config.id=schedule.stream_config_version_id
              LEFT JOIN source_policy_version policy
                ON policy.id=source_row.current_policy_version_id
              LEFT JOIN connector_config_version config
                ON config.id=source_row.current_connector_config_version_id
             WHERE schedule.status='ACTIVE'
               AND schedule.next_run_at<=p_now
               AND schedule.requests_used<schedule.daily_request_budget
               AND schedule.bytes_used<schedule.daily_byte_budget
               AND (schedule.leased_until IS NULL OR schedule.leased_until<=p_now)
               AND (
                 schedule.circuit_state='CLOSED'
                 OR (schedule.circuit_state='OPEN' AND schedule.circuit_open_until<=p_now)
               )
               AND (
                 (
                   schedule.authority_mode='PERSONAL_STREAM'
                   AND source_row.desired_enabled=true
                   AND source_row.manual_disabled_at IS NULL
                   AND stream.source_id=source_row.id AND stream.status='READY'
                   AND stream.config_sha256=stream_config.config_sha256
                   AND stream_config.stream_id=stream.id
                   AND schedule.access_state='ACCESSIBLE'
                 ) OR (
                   schedule.authority_mode='LEGACY_GOVERNED'
                   AND source_row.lifecycle_state='ACTIVE'
                   AND source_policy_compliance_current(source_row.id,policy.id,p_now)
                   AND source_private_evidence_capture_allowed(policy.document)
                   AND config.validation_status='VALID'
                   AND EXISTS (
                     SELECT 1 FROM source_governance_decision decision
                      WHERE decision.source_id=source_row.id
                        AND decision.policy_version_id=policy.id
                        AND decision.connector_config_version_id=config.id
                        AND decision.trial_run_id=source_row.current_trial_run_id
                        AND decision.decision_type='PRODUCTION_APPROVAL'
                        AND decision.outcome='APPROVED'
                        AND (decision.valid_until IS NULL OR decision.valid_until>p_now)
                   )
                 )
               )
             ORDER BY schedule.next_run_at,schedule.id
             LIMIT 1 FOR UPDATE OF schedule SKIP LOCKED
          )
          UPDATE fetch_schedule schedule
             SET lease_token=p_token,leased_until=p_lease_until,
                 circuit_state=CASE WHEN schedule.circuit_state='OPEN'
                                    THEN 'HALF_OPEN' ELSE schedule.circuit_state END,
                 self_heal_state=CASE WHEN schedule.circuit_state='OPEN'
                                      THEN 'HALF_OPEN_PROBE' ELSE schedule.self_heal_state END
            FROM due WHERE schedule.id=due.id
          RETURNING schedule.id,schedule.source_id
        $$
        """
    )


def _replace_runtime_persistence_functions() -> None:
    raw_args = (
        "uuid,uuid,uuid,uuid,text,text,text,text,bigint,text,text,text,text,text,text,"
        "jsonb,integer,text,text,timestamptz"
    )
    document_args = (
        "uuid,uuid,uuid,uuid,uuid,uuid,uuid,uuid,uuid,text,text,text,text,text,timestamptz"
    )
    op.execute(
        f"ALTER FUNCTION record_scheduled_source_raw({raw_args}) "
        "RENAME TO record_scheduled_source_raw_pers02"
    )
    op.execute(
        f"ALTER FUNCTION record_scheduled_source_document({document_args}) "
        "RENAME TO record_scheduled_source_document_pers02"
    )
    op.execute(
        r"""
        CREATE FUNCTION record_scheduled_source_raw(
          p_raw_object_id uuid,p_capture_id uuid,p_source_id uuid,p_fetch_run_id uuid,
          p_content_sha256 text,p_response_sha256 text,p_object_key text,
          p_storage_etag text,p_byte_size bigint,p_declared_mime text,
          p_detected_mime text,p_security_status text,p_security_reason text,
          p_requested_url text,p_final_url text,p_redirect_chain jsonb,
          p_http_status integer,p_etag text,p_last_modified text,p_captured_at timestamptz
        ) RETURNS TABLE(raw_object_id uuid,capture_id uuid)
        LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,public AS $$
        DECLARE
          v_mode text;v_hosts text[];v_raw_id uuid;v_status text;
          v_now timestamptz:=statement_timestamp();
        BEGIN
          SELECT schedule.authority_mode INTO v_mode
            FROM fetch_run run JOIN fetch_schedule schedule ON schedule.id=run.schedule_id
           WHERE run.id=p_fetch_run_id AND run.source_id=p_source_id;
          IF v_mode IS DISTINCT FROM 'PERSONAL_STREAM' THEN
            RETURN QUERY SELECT * FROM record_scheduled_source_raw_pers02(
              p_raw_object_id,p_capture_id,p_source_id,p_fetch_run_id,p_content_sha256,
              p_response_sha256,p_object_key,p_storage_etag,p_byte_size,p_declared_mime,
              p_detected_mime,p_security_status,p_security_reason,p_requested_url,p_final_url,
              p_redirect_chain,p_http_status,p_etag,p_last_modified,p_captured_at);
            RETURN;
          END IF;
          SELECT stream.allowed_hosts INTO v_hosts
            FROM fetch_run run
            JOIN fetch_schedule schedule ON schedule.id=run.schedule_id
            JOIN source source_row ON source_row.id=run.source_id
            JOIN source_stream stream ON stream.id=run.source_stream_id
            JOIN stream_config_version config ON config.id=run.stream_config_version_id
           WHERE run.id=p_fetch_run_id AND run.source_id=p_source_id
             AND run.run_origin='SCHEDULED' AND run.execution_domain='PRODUCTION'
             AND run.status='RUNNING' AND run.execution_lease_token IS NOT NULL
             AND run.execution_lease_until>v_now AND run.execution_lease_until>=p_captured_at
             AND schedule.authority_mode='PERSONAL_STREAM' AND schedule.status='ACTIVE'
             AND schedule.source_stream_id=stream.id
             AND schedule.stream_config_version_id=config.id
             AND schedule.access_state='ACCESSIBLE'
             AND schedule.requests_used<=schedule.daily_request_budget
             AND schedule.bytes_used<=schedule.daily_byte_budget
             AND schedule.circuit_state IN ('CLOSED','HALF_OPEN')
             AND source_row.desired_enabled=true AND source_row.manual_disabled_at IS NULL
             AND stream.source_id=source_row.id AND stream.status='READY'
             AND config.stream_id=stream.id AND config.config_sha256=stream.config_sha256
             AND run.started_at<=p_captured_at AND p_captured_at<=v_now
           FOR UPDATE OF run,source_row,schedule,stream;
          IF NOT FOUND OR p_content_sha256 !~ '^[0-9a-f]{64}$'
             OR p_response_sha256 !~ '^[0-9a-f]{64}$'
             OR p_byte_size NOT BETWEEN 0 AND 52428800
             OR p_object_key<>'sha256/'||substring(p_content_sha256,1,2)||'/'||p_content_sha256
             OR length(p_storage_etag) NOT BETWEEN 1 AND 200
             OR p_security_status NOT IN ('CLEAN','REJECTED')
             OR p_http_status NOT BETWEEN 100 AND 599
             OR jsonb_typeof(p_redirect_chain) IS DISTINCT FROM 'array'
             OR jsonb_array_length(p_redirect_chain)>10
             OR source_v2_safe_http_url(p_requested_url,v_hosts) IS DISTINCT FROM true
             OR source_v2_safe_http_url(p_final_url,v_hosts) IS DISTINCT FROM true
             OR EXISTS (SELECT 1 FROM jsonb_array_elements(p_redirect_chain) entry
                         WHERE jsonb_typeof(entry)<>'string'
                            OR source_v2_safe_http_url(
                                 entry #>> '{}',v_hosts
                               ) IS DISTINCT FROM true)
          THEN RAISE EXCEPTION 'personal stream raw capture is not authorized';END IF;
          INSERT INTO raw_object(id,sha256,object_key,byte_size,declared_mime,detected_mime,
                                 scan_status,storage_etag,created_at)
          VALUES(p_raw_object_id,p_content_sha256,p_object_key,p_byte_size,p_declared_mime,
                 p_detected_mime,p_security_status,p_storage_etag,p_captured_at)
          ON CONFLICT(sha256) DO NOTHING;
          SELECT id INTO v_raw_id FROM raw_object
           WHERE sha256=p_content_sha256 AND object_key=p_object_key
             AND byte_size=p_byte_size AND detected_mime=p_detected_mime;
          IF v_raw_id IS NULL THEN RAISE EXCEPTION 'personal raw identity mismatch';END IF;
          INSERT INTO raw_object_security_fact(id,raw_object_id,status,detected_mime,
                                               rule_version,reason_code,created_at)
          VALUES(p_raw_object_id,v_raw_id,p_security_status,p_detected_mime,'pers03-runtime-v1',
                 COALESCE(p_security_reason,'SCHEDULED_CAPTURE_CLEAN'),p_captured_at)
          ON CONFLICT ON CONSTRAINT uq_raw_security_object_rule DO NOTHING;
          SELECT fact.status INTO v_status FROM raw_object_security_fact fact
           WHERE fact.raw_object_id=v_raw_id ORDER BY fact.created_at DESC,fact.id DESC LIMIT 1;
          IF v_status IS DISTINCT FROM p_security_status THEN
            RAISE EXCEPTION 'personal raw security mismatch';END IF;
          INSERT INTO raw_object_capture(id,raw_object_id,source_id,fetch_run_id,trial_run_id,
            execution_domain,requested_url,final_url,redirect_chain,http_status,etag,last_modified,
            response_sha256,arrived_after_close,captured_at)
          VALUES(p_capture_id,v_raw_id,p_source_id,p_fetch_run_id,NULL,'PRODUCTION',p_requested_url,
            p_final_url,p_redirect_chain,p_http_status,p_etag,p_last_modified,p_response_sha256,
            false,p_captured_at);
          raw_object_id:=v_raw_id;capture_id:=p_capture_id;RETURN NEXT;
        END $$
        """
    )
    op.execute(
        r"""
        CREATE FUNCTION record_scheduled_source_document(
          p_document_id uuid,p_version_id uuid,p_received_event_id uuid,
          p_security_event_id uuid,p_ready_event_id uuid,p_source_id uuid,
          p_fetch_run_id uuid,p_raw_object_id uuid,p_capture_id uuid,
          p_canonical_url text,p_document_kind text,p_content_hash text,
          p_original_filename text,p_title text,p_acquired_at timestamptz
        ) RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,public AS $$
        DECLARE
          v_mode text;v_document_id uuid;v_raw_id uuid;v_hash text;v_existing uuid;
          v_version integer;v_hosts text[];v_captured_at timestamptz;v_mime text;
          v_now timestamptz:=statement_timestamp();
        BEGIN
          SELECT schedule.authority_mode INTO v_mode FROM fetch_run run
          JOIN fetch_schedule schedule ON schedule.id=run.schedule_id
          WHERE run.id=p_fetch_run_id AND run.source_id=p_source_id;
          IF v_mode IS DISTINCT FROM 'PERSONAL_STREAM' THEN
            RETURN record_scheduled_source_document_pers02(
              p_document_id,p_version_id,p_received_event_id,p_security_event_id,p_ready_event_id,
              p_source_id,p_fetch_run_id,p_raw_object_id,p_capture_id,p_canonical_url,
              p_document_kind,p_content_hash,p_original_filename,p_title,p_acquired_at);
          END IF;
          SELECT capture.raw_object_id,raw.sha256,stream.allowed_hosts,capture.captured_at,
                 raw.detected_mime INTO v_raw_id,v_hash,v_hosts,v_captured_at,v_mime
            FROM raw_object_capture capture JOIN raw_object raw ON raw.id=capture.raw_object_id
            JOIN fetch_run run ON run.id=capture.fetch_run_id
            JOIN fetch_schedule schedule ON schedule.id=run.schedule_id
            JOIN source source_row ON source_row.id=run.source_id
            JOIN source_stream stream ON stream.id=run.source_stream_id
            JOIN stream_config_version config ON config.id=run.stream_config_version_id
           WHERE capture.id=p_capture_id AND capture.source_id=p_source_id
             AND capture.fetch_run_id=p_fetch_run_id AND capture.raw_object_id=p_raw_object_id
             AND run.status='RUNNING' AND run.execution_lease_token IS NOT NULL
             AND run.execution_lease_until>v_now AND run.execution_domain='PRODUCTION'
             AND schedule.authority_mode='PERSONAL_STREAM' AND schedule.status='ACTIVE'
             AND schedule.source_stream_id=stream.id AND schedule.stream_config_version_id=config.id
             AND schedule.access_state='ACCESSIBLE'
             AND source_row.desired_enabled=true AND source_row.manual_disabled_at IS NULL
             AND stream.source_id=source_row.id AND stream.status='READY'
             AND config.stream_id=stream.id AND config.config_sha256=stream.config_sha256
             AND EXISTS(SELECT 1 FROM raw_object_security_fact fact
                         WHERE fact.raw_object_id=raw.id AND fact.status='CLEAN')
             AND NOT EXISTS(SELECT 1 FROM raw_object_security_fact fact
                             WHERE fact.raw_object_id=raw.id
                               AND fact.status IN ('REJECTED','QUARANTINED'))
           FOR UPDATE OF run,source_row,schedule,stream;
          IF NOT FOUND OR p_content_hash IS DISTINCT FROM v_hash
             OR p_document_kind NOT IN ('HTML','PDF','DISCOVERY_XML','DISCOVERY_JSON')
             OR source_v2_safe_http_url(p_canonical_url,v_hosts) IS DISTINCT FROM true
             OR p_acquired_at<v_captured_at OR p_acquired_at>v_now
             OR (p_document_kind='HTML' AND v_mime<>'text/html')
             OR (p_document_kind='PDF' AND v_mime<>'application/pdf')
             OR (p_document_kind='DISCOVERY_XML' AND v_mime<>'application/xml')
             OR (p_document_kind='DISCOVERY_JSON' AND v_mime<>'application/json')
          THEN RAISE EXCEPTION 'personal stream document is not authorized';END IF;
          INSERT INTO document(id,source_id,canonical_url,document_kind,first_discovered_at,
                               current_version_id,admission_fixture)
          VALUES(p_document_id,p_source_id,p_canonical_url,p_document_kind,p_acquired_at,NULL,false)
          ON CONFLICT(source_id,canonical_url) DO NOTHING;
          SELECT id INTO v_document_id FROM document WHERE source_id=p_source_id
           AND canonical_url=p_canonical_url FOR UPDATE;
          SELECT id INTO v_existing FROM document_version WHERE document_id=v_document_id
           AND content_hash=v_hash;
          IF v_existing IS NOT NULL THEN RETURN v_existing;END IF;
          SELECT COALESCE(max(version_number),0)+1 INTO v_version FROM document_version
           WHERE document_id=v_document_id;
          INSERT INTO document_version(id,document_id,raw_object_id,version_number,content_hash,
            original_filename,title,acquired_at,execution_domain,raw_object_capture_id)
          VALUES(p_version_id,v_document_id,v_raw_id,v_version,v_hash,p_original_filename,p_title,
                 p_acquired_at,'PRODUCTION',p_capture_id);
          INSERT INTO document_version_state_event(id,document_version_id,state,reason_code,
            actor_type,created_at) VALUES
            (p_received_event_id,p_version_id,'RECEIVED','SCHEDULED_CAPTURE','WORKER',p_acquired_at),
            (p_security_event_id,p_version_id,'SECURITY_PASSED','RAW_SECURITY_CLEAN','WORKER',p_acquired_at),
            (p_ready_event_id,p_version_id,'READY','DETERMINISTIC_PARSE_READY','WORKER',p_acquired_at);
          UPDATE document SET current_version_id=p_version_id WHERE id=v_document_id;
          RETURN p_version_id;
        END $$
        """
    )
    for signature in (
        f"record_scheduled_source_raw({raw_args})",
        f"record_scheduled_source_document({document_args})",
    ):
        op.execute(f"REVOKE ALL ON FUNCTION {signature} FROM PUBLIC")
        op.execute(f"GRANT EXECUTE ON FUNCTION {signature} TO srbg_worker_role")
    signature = "claim_due_fetch_schedule(timestamptz,timestamptz,uuid)"
    op.execute(f"REVOKE ALL ON FUNCTION {signature} FROM PUBLIC")
    op.execute(f"GRANT EXECUTE ON FUNCTION {signature} TO srbg_worker_role")


def downgrade() -> None:
    bind = op.get_bind()
    count = bind.execute(
        sa.text(
            "SELECT count(*) FROM fetch_run WHERE source_stream_id IS NOT NULL"
        )
    ).scalar_one()
    if count:
        raise RuntimeError("0023_DOWNGRADE_BLOCKED: personal stream runtime facts exist")
    op.execute("UPDATE source_stream SET schedule_id=NULL WHERE schedule_id IN "
               "(SELECT id FROM fetch_schedule WHERE authority_mode='PERSONAL_STREAM')")
    op.execute("DELETE FROM fetch_schedule WHERE authority_mode='PERSONAL_STREAM'")
    _restore_runtime_persistence_functions()
    _restore_legacy_claim_function()
    op.drop_index("ix_source_health_stream_observed", table_name="source_health_snapshot")
    for column in (
        "self_heal_state",
        "circuit_state",
        "next_interval_seconds",
        "new_content_count",
        "http_status",
        "reason_code",
    ):
        op.drop_column("source_health_snapshot", column)
    op.drop_constraint("fk_fetch_run_stream_config", "fetch_run", type_="foreignkey")
    op.drop_column("fetch_run", "stream_config_version_id")
    for table in ("source_anomaly", "source_health_snapshot", "fetch_run"):
        op.drop_constraint(f"fk_{table}_personal_stream", table, type_="foreignkey")
        op.drop_column(table, "source_stream_id")
    for constraint in (
        "ck_fetch_schedule_personal_binding",
        "ck_fetch_schedule_self_heal_state",
        "ck_fetch_schedule_access_state",
        "ck_fetch_schedule_authority_mode",
    ):
        op.drop_constraint(constraint, "fetch_schedule", type_="check")
    op.drop_index("uq_fetch_schedule_personal_stream", table_name="fetch_schedule")
    op.drop_index("uq_fetch_schedule_legacy_source", table_name="fetch_schedule")
    op.drop_constraint("fk_fetch_schedule_stream_config", "fetch_schedule", type_="foreignkey")
    op.drop_constraint("fk_fetch_schedule_source_stream", "fetch_schedule", type_="foreignkey")
    for column in (
        "health_reason",
        "health_status",
        "last_content_discovered_at",
        "last_successful_fetch_at",
        "zero_update_streak",
        "consecutive_zero_discovery",
        "next_self_heal_at",
        "self_heal_state",
        "access_state",
        "authority_mode",
        "stream_config_version_id",
        "source_stream_id",
    ):
        op.drop_column("fetch_schedule", column)
    op.create_unique_constraint("fetch_schedule_source_id_key", "fetch_schedule", ["source_id"])


def _restore_runtime_persistence_functions() -> None:
    raw_args = (
        "uuid,uuid,uuid,uuid,text,text,text,text,bigint,text,text,text,text,text,text,"
        "jsonb,integer,text,text,timestamptz"
    )
    document_args = (
        "uuid,uuid,uuid,uuid,uuid,uuid,uuid,uuid,uuid,text,text,text,text,text,timestamptz"
    )
    op.execute(f"DROP FUNCTION record_scheduled_source_raw({raw_args})")
    op.execute(f"DROP FUNCTION record_scheduled_source_document({document_args})")
    op.execute(
        f"ALTER FUNCTION record_scheduled_source_raw_pers02({raw_args}) "
        "RENAME TO record_scheduled_source_raw"
    )
    op.execute(
        f"ALTER FUNCTION record_scheduled_source_document_pers02({document_args}) "
        "RENAME TO record_scheduled_source_document"
    )


def _restore_legacy_claim_function() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION claim_due_fetch_schedule(
          p_now timestamptz,p_lease_until timestamptz,p_token uuid
        ) RETURNS TABLE(schedule_id uuid,source_id uuid)
        LANGUAGE sql SECURITY DEFINER
        SET search_path=pg_catalog,public AS $$
          WITH due AS (
            SELECT schedule.id,schedule.source_id
              FROM fetch_schedule schedule
              JOIN source source_row ON source_row.id=schedule.source_id
              JOIN source_policy_version policy
                ON policy.id=source_row.current_policy_version_id
              JOIN connector_config_version config
                ON config.id=source_row.current_connector_config_version_id
             WHERE schedule.status='ACTIVE'
               AND source_row.lifecycle_state='ACTIVE'
               AND source_policy_compliance_current(source_row.id,policy.id,p_now)
               AND source_private_evidence_capture_allowed(policy.document)
               AND config.validation_status='VALID'
               AND schedule.next_run_at<=p_now
               AND schedule.requests_used<schedule.daily_request_budget
               AND schedule.bytes_used<schedule.daily_byte_budget
               AND (schedule.leased_until IS NULL OR schedule.leased_until<=p_now)
               AND (schedule.circuit_state='CLOSED' OR
                    (schedule.circuit_state='OPEN' AND schedule.circuit_open_until<=p_now))
               AND EXISTS (
                 SELECT 1 FROM source_governance_decision decision
                  WHERE decision.source_id=source_row.id
                    AND decision.policy_version_id=policy.id
                    AND decision.connector_config_version_id=config.id
                    AND decision.trial_run_id=source_row.current_trial_run_id
                    AND decision.decision_type='PRODUCTION_APPROVAL'
                    AND decision.outcome='APPROVED'
                    AND (decision.valid_until IS NULL OR decision.valid_until>p_now)
               )
             ORDER BY schedule.next_run_at,schedule.id LIMIT 1
             FOR UPDATE OF schedule SKIP LOCKED
          )
          UPDATE fetch_schedule schedule
             SET lease_token=p_token,leased_until=p_lease_until,
                 circuit_state=CASE WHEN schedule.circuit_state='OPEN'
                                    THEN 'HALF_OPEN' ELSE schedule.circuit_state END
            FROM due WHERE schedule.id=due.id
          RETURNING schedule.id,schedule.source_id
        $$
        """
    )
