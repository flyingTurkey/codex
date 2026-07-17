"""Durable ID-only handoff from governed source documents to the AI queue.

Revision ID: 0019_source_content_bridge
Revises: 0018_source_automation
"""

# SQL command boundaries are intentionally explicit for security review.
# ruff: noqa: E501

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0019_source_content_bridge"
down_revision: str | Sequence[str] | None = "0018_source_automation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SOURCE_CONTENT_TABLES = ("source_content_outbox",)

WORKER_COMMAND_SIGNATURES = (
    "list_pending_source_content_ids(timestamptz,integer)",
    "handoff_source_content_to_ai(uuid,uuid,timestamptz)",
    "fail_source_content_handoff(uuid,text,timestamptz)",
)


def _uuid() -> postgresql.UUID:
    return postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    _create_outbox()
    _create_ready_trigger()
    _backfill_ready_versions()
    _create_worker_commands()
    _configure_roles()


def _create_outbox() -> None:
    op.create_table(
        "source_content_outbox",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column(
            "document_version_id",
            _uuid(),
            sa.ForeignKey("document_version.id", ondelete="RESTRICT"),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "pipeline_run_id",
            _uuid(),
            sa.ForeignKey("ai_pipeline_run.id", ondelete="RESTRICT"),
            unique=True,
        ),
        sa.Column("status", sa.String(20), nullable=False, server_default="PENDING"),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_error_code", sa.String(80)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('PENDING','FAILED','WAITING_AI','DEAD_LETTER')",
            name="ck_source_content_outbox_status",
        ),
        sa.CheckConstraint(
            "attempt_count BETWEEN 0 AND 5",
            name="ck_source_content_outbox_attempts",
        ),
        sa.CheckConstraint(
            "last_error_code IS NULL OR last_error_code ~ '^[A-Z0-9_]{1,80}$'",
            name="ck_source_content_outbox_error_code",
        ),
        sa.CheckConstraint(
            "(status='PENDING' AND pipeline_run_id IS NULL AND last_error_code IS NULL) OR "
            "(status='WAITING_AI' AND pipeline_run_id IS NOT NULL AND last_error_code IS NULL) OR "
            "(status IN ('FAILED','DEAD_LETTER') AND pipeline_run_id IS NULL "
            "AND last_error_code IS NOT NULL)",
            name="ck_source_content_outbox_consistency",
        ),
        sa.CheckConstraint(
            "updated_at >= created_at",
            name="ck_source_content_outbox_times",
        ),
    )
    op.create_index(
        "ix_source_content_outbox_dispatch",
        "source_content_outbox",
        ["status", "available_at", "id"],
    )


def _create_ready_trigger() -> None:
    op.execute(
        r"""
        CREATE FUNCTION enqueue_source_content_ready_event()
        RETURNS trigger
        LANGUAGE plpgsql SECURITY DEFINER
        SET search_path=pg_catalog,public AS $$
        BEGIN
          IF NEW.state='READY' THEN
            INSERT INTO source_content_outbox(
              id,document_version_id,pipeline_run_id,status,attempt_count,
              available_at,last_error_code,created_at,updated_at
            )
            SELECT source_automation_derived_uuid(version.id,'source-content-outbox'),
                   version.id,NULL,'PENDING',0,NEW.created_at,NULL,
                   NEW.created_at,NEW.created_at
              FROM document_version version
              JOIN document document ON document.id=version.document_id
              JOIN raw_object_capture capture
                ON capture.id=version.raw_object_capture_id
               AND capture.raw_object_id=version.raw_object_id
               AND capture.source_id=document.source_id
              JOIN fetch_run run
                ON run.id=capture.fetch_run_id
               AND run.source_id=document.source_id
             WHERE version.id=NEW.document_version_id
               AND version.execution_domain='PRODUCTION'
               AND capture.execution_domain='PRODUCTION'
               AND run.execution_domain='PRODUCTION'
               AND run.run_origin='SCHEDULED'
               AND run.trigger='SCHEDULED'
               AND run.pilot_window_source_id IS NULL
               AND document.admission_fixture=false
            ON CONFLICT (document_version_id) DO NOTHING;
          END IF;
          RETURN NEW;
        END $$
        """
    )
    op.execute(
        "REVOKE ALL ON FUNCTION enqueue_source_content_ready_event() FROM PUBLIC,"
        "srbg_api_role,srbg_worker_role,srbg_publication_writer,srbg_model_role,"
        "srbg_projection_reader"
    )
    op.execute(
        "CREATE TRIGGER trg_source_content_ready_outbox "
        "AFTER INSERT ON document_version_state_event "
        "FOR EACH ROW EXECUTE FUNCTION enqueue_source_content_ready_event()"
    )


def _backfill_ready_versions() -> None:
    op.execute(
        r"""
        INSERT INTO source_content_outbox(
          id,document_version_id,pipeline_run_id,status,attempt_count,
          available_at,last_error_code,created_at,updated_at
        )
        SELECT source_automation_derived_uuid(version.id,'source-content-outbox'),
               version.id,NULL,'PENDING',0,statement_timestamp(),NULL,
               statement_timestamp(),statement_timestamp()
          FROM document_version version
          JOIN document document
            ON document.id=version.document_id
           AND document.current_version_id=version.id
          JOIN raw_object_capture capture
            ON capture.id=version.raw_object_capture_id
           AND capture.raw_object_id=version.raw_object_id
           AND capture.source_id=document.source_id
          JOIN fetch_run run
            ON run.id=capture.fetch_run_id
           AND run.source_id=document.source_id
          JOIN LATERAL (
            SELECT state.state
              FROM document_version_state_event state
             WHERE state.document_version_id=version.id
             ORDER BY state.created_at DESC,state.id DESC
             LIMIT 1
          ) latest_state ON true
         WHERE latest_state.state='READY'
           AND version.execution_domain='PRODUCTION'
           AND capture.execution_domain='PRODUCTION'
           AND run.execution_domain='PRODUCTION'
           AND run.run_origin='SCHEDULED'
           AND run.trigger='SCHEDULED'
           AND run.pilot_window_source_id IS NULL
           AND document.admission_fixture=false
        ON CONFLICT (document_version_id) DO NOTHING
        """
    )


def _create_worker_commands() -> None:
    op.execute(
        r"""
        CREATE FUNCTION list_pending_source_content_ids(
          p_now timestamptz,p_limit integer
        ) RETURNS TABLE(outbox_id uuid)
        LANGUAGE plpgsql STABLE SECURITY DEFINER
        SET search_path=pg_catalog,public AS $$
        BEGIN
          IF p_limit NOT BETWEEN 1 AND 100
             OR p_now NOT BETWEEN clock_timestamp()-interval '5 minutes'
                                  AND clock_timestamp()+interval '5 minutes' THEN
            RAISE EXCEPTION 'source content dispatch input is invalid';
          END IF;
          RETURN QUERY
          SELECT content.id
            FROM source_content_outbox content
           WHERE content.status IN ('PENDING','FAILED')
             AND content.attempt_count<5
             AND content.available_at<=p_now
           ORDER BY content.available_at,content.id
           LIMIT p_limit;
        END $$
        """
    )
    op.execute(
        r"""
        CREATE FUNCTION handoff_source_content_to_ai(
          p_outbox_id uuid,p_pipeline_run_id uuid,p_now timestamptz
        ) RETURNS TABLE(
          outbox_id uuid,document_version_id uuid,pipeline_run_id uuid,
          status text,queued boolean
        )
        LANGUAGE plpgsql SECURITY DEFINER
        SET search_path=pg_catalog,public AS $$
        DECLARE
          v_outbox source_content_outbox%ROWTYPE;
          v_pipeline ai_pipeline_run%ROWTYPE;
          v_document_version_id uuid;
          v_input_sha256 text;
        BEGIN
          IF substring(p_outbox_id::text,15,1)<>'7'
             OR substring(p_pipeline_run_id::text,15,1)<>'7'
             OR substring(p_pipeline_run_id::text,20,1) !~ '^[89ab]$'
             OR p_now NOT BETWEEN clock_timestamp()-interval '5 minutes'
                                  AND clock_timestamp()+interval '5 minutes' THEN
            RAISE EXCEPTION 'source content handoff input is invalid';
          END IF;

          SELECT * INTO v_outbox
            FROM source_content_outbox content
           WHERE content.id=p_outbox_id
           FOR UPDATE;
          IF NOT FOUND THEN
            RETURN;
          END IF;

          IF v_outbox.status='WAITING_AI' THEN
            SELECT * INTO v_pipeline
              FROM ai_pipeline_run pipeline
             WHERE pipeline.id=v_outbox.pipeline_run_id
               AND pipeline.document_version_id=v_outbox.document_version_id
               AND pipeline.mode='LIVE';
            IF NOT FOUND THEN
              RAISE EXCEPTION 'source content handoff fact is inconsistent';
            END IF;
            outbox_id:=v_outbox.id;
            document_version_id:=v_outbox.document_version_id;
            pipeline_run_id:=v_pipeline.id;
            status:='WAITING_AI';
            queued:=false;
            RETURN NEXT;
            RETURN;
          END IF;

          IF v_outbox.status NOT IN ('PENDING','FAILED')
             OR v_outbox.attempt_count>=5
             OR v_outbox.available_at>p_now THEN
            RETURN;
          END IF;

          SELECT version.id,version.content_hash
            INTO v_document_version_id,v_input_sha256
            FROM document_version version
            JOIN document document ON document.id=version.document_id
            JOIN raw_object raw ON raw.id=version.raw_object_id
            JOIN raw_object_capture capture
              ON capture.id=version.raw_object_capture_id
             AND capture.raw_object_id=version.raw_object_id
             AND capture.source_id=document.source_id
            JOIN fetch_run run
              ON run.id=capture.fetch_run_id
             AND run.source_id=document.source_id
            JOIN LATERAL (
              SELECT state.state
                FROM document_version_state_event state
               WHERE state.document_version_id=version.id
               ORDER BY state.created_at DESC,state.id DESC
               LIMIT 1
            ) latest_state ON true
           WHERE version.id=v_outbox.document_version_id
             AND document.current_version_id=version.id
             AND latest_state.state='READY'
             AND document.admission_fixture=false
             AND version.execution_domain='PRODUCTION'
             AND capture.execution_domain='PRODUCTION'
             AND run.execution_domain='PRODUCTION'
             AND run.run_origin='SCHEDULED'
             AND run.trigger='SCHEDULED'
             AND run.pilot_window_source_id IS NULL
             AND version.content_hash=raw.sha256
             AND raw.scan_status='CLEAN'
             AND EXISTS (
               SELECT 1 FROM raw_object_security_fact fact
                WHERE fact.raw_object_id=raw.id AND fact.status='CLEAN'
             )
             AND NOT EXISTS (
               SELECT 1 FROM raw_object_security_fact fact
                WHERE fact.raw_object_id=raw.id
                  AND fact.status IN ('REJECTED','QUARANTINED')
             )
           FOR SHARE OF version,document,raw,capture,run;
          IF NOT FOUND THEN
            RAISE EXCEPTION 'source content authority is no longer valid';
          END IF;

          INSERT INTO ai_pipeline_run(
            id,document_version_id,mode,status,input_sha256,started_at,
            completed_at,failure_code
          ) VALUES (
            p_pipeline_run_id,v_document_version_id,'LIVE','QUEUED',
            v_input_sha256,p_now,NULL,NULL
          );

          UPDATE source_content_outbox content
             SET pipeline_run_id=p_pipeline_run_id,status='WAITING_AI',
                 attempt_count=content.attempt_count+1,last_error_code=NULL,
                 updated_at=p_now
           WHERE content.id=v_outbox.id;

          outbox_id:=v_outbox.id;
          document_version_id:=v_document_version_id;
          pipeline_run_id:=p_pipeline_run_id;
          status:='WAITING_AI';
          queued:=true;
          RETURN NEXT;
        END $$
        """
    )
    op.execute(
        r"""
        CREATE FUNCTION fail_source_content_handoff(
          p_outbox_id uuid,p_reason_code text,p_now timestamptz
        ) RETURNS uuid
        LANGUAGE plpgsql SECURITY DEFINER
        SET search_path=pg_catalog,public AS $$
        DECLARE v_outbox_id uuid;
        BEGIN
          IF substring(p_outbox_id::text,15,1)<>'7'
             OR p_reason_code !~ '^[A-Z0-9_]{1,80}$'
             OR p_now NOT BETWEEN clock_timestamp()-interval '5 minutes'
                                  AND clock_timestamp()+interval '5 minutes' THEN
            RAISE EXCEPTION 'source content failure input is invalid';
          END IF;
          UPDATE source_content_outbox content
             SET attempt_count=content.attempt_count+1,
                 status=CASE WHEN content.attempt_count+1>=5
                             THEN 'DEAD_LETTER' ELSE 'FAILED' END,
                 available_at=p_now+make_interval(secs=>CASE content.attempt_count
                   WHEN 0 THEN 5 WHEN 1 THEN 15 WHEN 2 THEN 60 ELSE 300 END),
                 last_error_code=p_reason_code,updated_at=p_now
           WHERE content.id=p_outbox_id
             AND content.status IN ('PENDING','FAILED')
             AND content.attempt_count<5
          RETURNING content.id INTO v_outbox_id;
          RETURN v_outbox_id;
        END $$
        """
    )

    for signature in WORKER_COMMAND_SIGNATURES:
        op.execute(
            f"REVOKE ALL ON FUNCTION {signature} FROM PUBLIC,srbg_api_role,"
            "srbg_worker_role,srbg_publication_writer,srbg_model_role,"
            "srbg_projection_reader"
        )
    op.execute("GRANT EXECUTE ON FUNCTION list_pending_source_content_ids(timestamptz,integer) TO srbg_worker_role")
    op.execute("GRANT EXECUTE ON FUNCTION handoff_source_content_to_ai(uuid,uuid,timestamptz) TO srbg_worker_role")
    op.execute("GRANT EXECUTE ON FUNCTION fail_source_content_handoff(uuid,text,timestamptz) TO srbg_worker_role")


def _configure_roles() -> None:
    op.execute(
        "REVOKE ALL ON source_content_outbox FROM PUBLIC,srbg_runtime,srbg_api_role,"
        "srbg_worker_role,srbg_publication_writer,srbg_model_role,"
        "srbg_projection_reader,srbg_admin_role"
    )
    op.execute("GRANT SELECT ON source_content_outbox TO srbg_api_role,srbg_publication_writer,srbg_admin_role")


def downgrade() -> None:
    bind = op.get_bind()
    has_outbox_facts = bind.execute(
        sa.text("SELECT EXISTS(SELECT 1 FROM source_content_outbox)")
    ).scalar_one()
    if has_outbox_facts:
        raise RuntimeError(
            "ROUND19_DOWNGRADE_BLOCKED: durable source content handoffs exist"
        )
    op.execute(
        """
        DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM source_content_outbox LIMIT 1) THEN
            RAISE EXCEPTION 'ROUND19_DOWNGRADE_BLOCKED';
          END IF;
        END $$
        """
    )
    op.execute(
        "DROP TRIGGER IF EXISTS trg_source_content_ready_outbox "
        "ON document_version_state_event"
    )
    op.execute("DROP FUNCTION IF EXISTS enqueue_source_content_ready_event()")
    for signature in reversed(WORKER_COMMAND_SIGNATURES):
        op.execute(f"DROP FUNCTION IF EXISTS {signature}")
    op.drop_index(
        "ix_source_content_outbox_dispatch",
        table_name="source_content_outbox",
    )
    op.drop_table("source_content_outbox")
