"""Propagate controlled-run authority into source-content AI handoff.

Revision ID: 0056_phase4_controlled_handoff
Revises: 0055_phase3_trustworthy_event
"""

# ruff: noqa: S608

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision = "0056_phase4_controlled_handoff"
down_revision = "0055_phase3_trustworthy_event"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_HANDOFF_SIGNATURE = "handoff_source_content_to_ai(uuid,uuid,uuid,timestamptz)"


def upgrade() -> None:
    _replace_handoff(propagate_controlled_run=True)
    _configure_worker_command()


def downgrade() -> None:
    _replace_handoff(propagate_controlled_run=False)
    _configure_worker_command()


def _replace_handoff(*, propagate_controlled_run: bool) -> None:
    controlled_run_declaration = "v_controlled_run_id uuid;" if propagate_controlled_run else ""
    controlled_run_select = ",run.controlled_run_id" if propagate_controlled_run else ""
    controlled_run_into = ",v_controlled_run_id" if propagate_controlled_run else ""
    controlled_run_column = ",controlled_run_id" if propagate_controlled_run else ""
    controlled_run_value = ",v_controlled_run_id" if propagate_controlled_run else ""
    op.execute(
        f"""
        CREATE OR REPLACE FUNCTION handoff_source_content_to_ai(
          p_outbox_id uuid,p_pipeline_run_id uuid,p_policy_bundle_id uuid,
          p_now timestamptz
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
          v_stream_version text;
          {controlled_run_declaration}
        BEGIN
          IF substring(p_outbox_id::text,15,1)<>'7'
             OR substring(p_pipeline_run_id::text,15,1)<>'7'
             OR substring(p_policy_bundle_id::text,15,1)<>'7'
             OR substring(p_pipeline_run_id::text,20,1) !~ '^[89ab]$'
             OR p_now NOT BETWEEN clock_timestamp()-interval '5 minutes'
                                  AND clock_timestamp()+interval '5 minutes' THEN
            RAISE EXCEPTION 'source content handoff input is invalid';
          END IF;

          SELECT * INTO v_outbox FROM source_content_outbox content
           WHERE content.id=p_outbox_id FOR UPDATE;
          IF NOT FOUND THEN RETURN; END IF;
          IF v_outbox.status='WAITING_AI' THEN
            SELECT * INTO v_pipeline FROM ai_pipeline_run pipeline
             WHERE pipeline.id=v_outbox.pipeline_run_id
               AND pipeline.document_version_id=v_outbox.document_version_id
               AND pipeline.mode='LIVE'
               AND pipeline.policy_bundle_id IS NOT NULL;
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
             OR v_outbox.attempt_count>=5 OR v_outbox.available_at>p_now THEN
            RETURN;
          END IF;

          SELECT version.id,version.content_hash,
                 COALESCE(config.config_sha256,source_policy.policy_version,
                          'legacy-source-policy'){controlled_run_select}
            INTO v_document_version_id,v_input_sha256,v_stream_version{controlled_run_into}
            FROM document_version version
            JOIN document document ON document.id=version.document_id
            JOIN raw_object raw ON raw.id=version.raw_object_id
            JOIN raw_object_capture capture
              ON capture.id=version.raw_object_capture_id
             AND capture.raw_object_id=version.raw_object_id
             AND capture.source_id=document.source_id
            JOIN fetch_run run
              ON run.id=capture.fetch_run_id AND run.source_id=document.source_id
            LEFT JOIN stream_config_version config
              ON config.id=run.stream_config_version_id
            LEFT JOIN LATERAL(
              SELECT policy.policy_version FROM source_policy policy
               WHERE policy.source_id=document.source_id AND policy.status='VALID'
               ORDER BY policy.created_at DESC LIMIT 1
            ) source_policy ON true
            JOIN LATERAL(
              SELECT state.state FROM document_version_state_event state
               WHERE state.document_version_id=version.id
               ORDER BY state.created_at DESC,
                 CASE state.state
                   WHEN 'FAILED' THEN 90 WHEN 'QUARANTINED' THEN 90
                   WHEN 'READY' THEN 80 WHEN 'OCR_COMPLETE' THEN 70
                   WHEN 'SECURITY_PASSED' THEN 60 WHEN 'OCR_PENDING' THEN 50
                   WHEN 'PARSING' THEN 40 WHEN 'RECEIVED' THEN 30 ELSE 0
                 END DESC,state.id DESC LIMIT 1
            ) latest_state ON true
           WHERE version.id=v_outbox.document_version_id
             AND document.current_version_id=version.id
             AND latest_state.state='READY'
             AND document.admission_fixture=false
             AND version.execution_domain='PRODUCTION'
             AND capture.execution_domain='PRODUCTION'
             AND run.execution_domain='PRODUCTION'
             AND run.run_origin='SCHEDULED' AND run.trigger='SCHEDULED'
             AND run.pilot_window_source_id IS NULL
             AND version.content_hash=raw.sha256 AND raw.scan_status='CLEAN'
             AND EXISTS(
               SELECT 1 FROM raw_object_security_fact fact
                WHERE fact.raw_object_id=raw.id AND fact.status='CLEAN'
             )
             AND NOT EXISTS(
               SELECT 1 FROM raw_object_security_fact fact
                WHERE fact.raw_object_id=raw.id
                  AND fact.status IN ('REJECTED','QUARANTINED')
             )
           FOR SHARE OF version,document,raw,capture,run;
          IF NOT FOUND THEN
            RAISE EXCEPTION 'source content authority is no longer valid';
          END IF;
          IF NOT EXISTS(
            SELECT 1 FROM active_qualification_policy_v2 active
             WHERE active.source_stream_policy_version=v_stream_version
               AND active.policy_bundle_id=p_policy_bundle_id
          ) THEN
            RAISE EXCEPTION 'POLICY_BUNDLE_REQUIRED_AT_RUN_CREATION';
          END IF;

          INSERT INTO ai_pipeline_run(
            id,document_version_id,mode,status,input_sha256,started_at,
            completed_at,failure_code,policy_bundle_id{controlled_run_column}
          ) VALUES(
            p_pipeline_run_id,v_document_version_id,'LIVE','QUEUED',
            v_input_sha256,p_now,NULL,NULL,p_policy_bundle_id{controlled_run_value}
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


def _configure_worker_command() -> None:
    op.execute(f"REVOKE ALL ON FUNCTION {_HANDOFF_SIGNATURE} FROM PUBLIC")
    op.execute(f"GRANT EXECUTE ON FUNCTION {_HANDOFF_SIGNATURE} TO srbg_worker_role")
