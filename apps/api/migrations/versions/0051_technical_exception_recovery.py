"""Add the narrow command used to resume an exhausted content pipeline.

Revision ID: 0051_technical_exception_recovery
Revises: 0050_autonomous_handoff_state_order
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision = "0051_technical_exception_recovery"
down_revision = "0050_autonomous_handoff_state_order"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_FUNCTION_SIGNATURE = (
    "reopen_source_content_ai_run(uuid,uuid,uuid,uuid,timestamptz,timestamptz)"
)
_FETCH_FUNCTION_SIGNATURE = (
    "reopen_failed_source_fetch(uuid,uuid,uuid,timestamptz,timestamptz)"
)


def upgrade() -> None:
    op.execute(
        r"""
        CREATE FUNCTION reopen_source_content_ai_run(
          p_pipeline_run_id uuid,p_recovery_pipeline_run_id uuid,
          p_recovery_compensation_id uuid,p_retry_event_id uuid,
          p_requested_at timestamptz,p_now timestamptz
        ) RETURNS uuid
        LANGUAGE plpgsql SECURITY DEFINER
        SET search_path=pg_catalog,public AS $$
        DECLARE v_outbox_id uuid; v_reason_code text;
        BEGIN
          IF substring(p_pipeline_run_id::text,15,1)<>'7'
             OR substring(p_recovery_pipeline_run_id::text,15,1)<>'7'
             OR substring(p_recovery_compensation_id::text,15,1)<>'7'
             OR substring(p_retry_event_id::text,15,1)<>'7'
             OR p_requested_at IS NULL OR p_now IS NULL
             OR p_now<p_requested_at THEN
            RAISE EXCEPTION 'technical retry input is invalid';
          END IF;

          SELECT content.id,compensation.reason_code
            INTO v_outbox_id,v_reason_code
            FROM owner_exception_event_v2 event
            JOIN owner_exception_v2 exception ON exception.id=event.exception_id
            JOIN ai_compensation_run_v2 compensation
              ON compensation.original_pipeline_run_id=p_pipeline_run_id
            JOIN ai_pipeline_run pipeline ON pipeline.id=p_pipeline_run_id
            JOIN source_content_outbox content
              ON content.pipeline_run_id=p_pipeline_run_id
           WHERE event.id=p_retry_event_id
             AND event.event_type='RETRY_REQUESTED'
             AND event.created_at=p_requested_at
             AND exception.kind='TECHNICAL' AND exception.status='OPEN'
             AND exception.safe_metadata->>'pipeline_run_id'=p_pipeline_run_id::text
             AND compensation.status='DEAD_LETTER'
             AND compensation.completed_at<p_requested_at
             AND pipeline.status='FAILED'
             AND pipeline.failure_code='TECHNICAL_FAILED'
             AND content.status='DEAD_LETTER'
           FOR UPDATE OF exception,compensation,pipeline,content;

          IF v_outbox_id IS NULL THEN
            RETURN NULL;
          END IF;

          INSERT INTO ai_pipeline_run(
            id,document_version_id,mode,status,input_sha256,started_at,
            completed_at,failure_code,controlled_run_id
          )
          SELECT p_recovery_pipeline_run_id,pipeline.document_version_id,
                 pipeline.mode,'QUEUED',pipeline.input_sha256,p_now,NULL,NULL,
                 pipeline.controlled_run_id
            FROM ai_pipeline_run pipeline WHERE pipeline.id=p_pipeline_run_id;
          UPDATE ai_compensation_run_v2 compensation
             SET status='SUCCEEDED',recovery_pipeline_run_id=p_recovery_pipeline_run_id,
                 completed_at=p_now
           WHERE compensation.original_pipeline_run_id=p_pipeline_run_id
             AND compensation.status='DEAD_LETTER';
          INSERT INTO ai_compensation_run_v2(
            id,original_pipeline_run_id,recovery_pipeline_run_id,reason_code,status,
            attempt_count,available_at,started_at,completed_at
          ) VALUES(
            p_recovery_compensation_id,p_recovery_pipeline_run_id,NULL,v_reason_code,
            'PENDING',0,p_now,p_now,NULL
          );
          UPDATE source_content_outbox content
             SET pipeline_run_id=p_recovery_pipeline_run_id,status='WAITING_AI',
                 attempt_count=0,last_error_code=NULL,updated_at=p_now
           WHERE content.id=v_outbox_id AND content.status='DEAD_LETTER';
          RETURN p_recovery_pipeline_run_id;
        END $$
        """
    )
    op.execute(
        f"REVOKE ALL ON FUNCTION {_FUNCTION_SIGNATURE} FROM PUBLIC,srbg_api_role,"
        "srbg_worker_role,srbg_publication_writer,srbg_projection_reader"
    )
    op.execute(
        "GRANT EXECUTE ON FUNCTION "
        "reopen_source_content_ai_run(uuid,uuid,uuid,uuid,timestamptz,timestamptz) "
        "TO srbg_worker_role"
    )
    op.execute(
        r"""
        CREATE FUNCTION reopen_failed_source_fetch(
          p_failed_run_id uuid,p_recovery_run_id uuid,p_retry_event_id uuid,
          p_requested_at timestamptz,p_now timestamptz
        ) RETURNS uuid
        LANGUAGE plpgsql SECURITY DEFINER
        SET search_path=pg_catalog,public AS $$
        DECLARE v_recovery_id uuid;
        BEGIN
          IF substring(p_failed_run_id::text,15,1)<>'7'
             OR substring(p_recovery_run_id::text,15,1)<>'7'
             OR substring(p_retry_event_id::text,15,1)<>'7'
             OR p_requested_at IS NULL OR p_now IS NULL
             OR p_now<p_requested_at THEN
            RAISE EXCEPTION 'source fetch retry input is invalid';
          END IF;
          INSERT INTO fetch_run(
            id,source_connector_id,trigger,status,started_at,discovered_count,
            fetched_count,failed_count,request_id,execution_domain,source_id,
            schedule_id,policy_version_id,connector_config_version_id,
            idempotency_key,attempt_count,run_origin,replayed_from_run_id,
            request_count,response_bytes,source_stream_id,stream_config_version_id,
            controlled_run_id
          )
          SELECT p_recovery_run_id,failed.source_connector_id,failed.trigger,
                 'PENDING_DISPATCH',p_now,0,0,0,
                 'owner-technical-retry:' || p_retry_event_id::text,
                 failed.execution_domain,failed.source_id,failed.schedule_id,
                 failed.policy_version_id,failed.connector_config_version_id,
                 'owner-technical-retry:' || p_retry_event_id::text,0,
                 failed.run_origin,failed.id,0,0,failed.source_stream_id,
                 failed.stream_config_version_id,failed.controlled_run_id
            FROM fetch_run failed
            JOIN owner_exception_event_v2 event ON event.id=p_retry_event_id
            JOIN owner_exception_v2 exception ON exception.id=event.exception_id
           WHERE failed.id=p_failed_run_id AND failed.status='FAILED'
             AND failed.completed_at<p_requested_at
             AND event.event_type='RETRY_REQUESTED'
             AND event.created_at=p_requested_at
             AND exception.kind='TECHNICAL' AND exception.status='OPEN'
             AND exception.safe_metadata->>'technical_work_kind'='SOURCE_FETCH'
             AND exception.safe_metadata->>'technical_work_id'=p_failed_run_id::text
          ON CONFLICT(idempotency_key) DO UPDATE
             SET idempotency_key=EXCLUDED.idempotency_key
          RETURNING id INTO v_recovery_id;
          IF v_recovery_id IS NOT NULL THEN
            UPDATE fetch_schedule schedule
               SET next_run_at=p_now,leased_until=NULL,lease_token=NULL,updated_at=p_now
              FROM fetch_run recovery
             WHERE recovery.id=v_recovery_id AND schedule.id=recovery.schedule_id;
          END IF;
          RETURN v_recovery_id;
        END $$
        """
    )
    op.execute(
        f"REVOKE ALL ON FUNCTION {_FETCH_FUNCTION_SIGNATURE} FROM PUBLIC,srbg_api_role,"
        "srbg_worker_role,srbg_publication_writer,srbg_projection_reader"
    )
    op.execute(
        "GRANT EXECUTE ON FUNCTION "
        "reopen_failed_source_fetch(uuid,uuid,uuid,timestamptz,timestamptz) "
        "TO srbg_worker_role"
    )


def downgrade() -> None:
    op.execute(f"DROP FUNCTION {_FETCH_FUNCTION_SIGNATURE}")
    op.execute(f"DROP FUNCTION {_FUNCTION_SIGNATURE}")
