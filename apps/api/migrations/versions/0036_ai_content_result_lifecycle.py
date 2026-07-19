"""Close durable content handoffs when their AI pipeline reaches a terminal state.

Revision ID: 0036_ai_content_result_lifecycle
Revises: 0035_intelligence_v2_closeout
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision = "0036_ai_content_result_lifecycle"
down_revision = "0035_intelligence_v2_closeout"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_FUNCTION_SIGNATURE = "finalize_source_content_ai_run(uuid,text,text,timestamptz)"


def upgrade() -> None:
    op.drop_constraint(
        "ck_source_content_outbox_status",
        "source_content_outbox",
        type_="check",
    )
    op.create_check_constraint(
        "ck_source_content_outbox_status",
        "source_content_outbox",
        "status IN ('PENDING','WAITING_AI','COMPLETED','FAILED','DEAD_LETTER')",
    )
    op.drop_constraint(
        "ck_source_content_outbox_consistency",
        "source_content_outbox",
        type_="check",
    )
    op.create_check_constraint(
        "ck_source_content_outbox_consistency",
        "source_content_outbox",
        "(status='PENDING' AND pipeline_run_id IS NULL AND last_error_code IS NULL) OR "
        "(status='WAITING_AI' AND pipeline_run_id IS NOT NULL "
        "AND last_error_code IS NULL) OR "
        "(status='COMPLETED' AND pipeline_run_id IS NOT NULL) OR "
        "(status IN ('FAILED','DEAD_LETTER') AND last_error_code IS NOT NULL)",
    )
    op.execute(
        """
        UPDATE source_content_outbox content
           SET status=CASE WHEN pipeline.status='FAILED'
                           THEN 'DEAD_LETTER' ELSE 'COMPLETED' END,
               attempt_count=CASE WHEN pipeline.status='FAILED'
                                  THEN 5 ELSE content.attempt_count END,
               last_error_code=CASE WHEN pipeline.status IN ('FAILED','DEGRADED')
                                    THEN CASE
                                      WHEN pipeline.failure_code ~ '^[A-Z0-9_]{1,80}$'
                                      THEN pipeline.failure_code
                                      ELSE 'LEGACY_AI_PIPELINE_FAILURE'
                                    END
                                    ELSE NULL END,
               updated_at=COALESCE(pipeline.completed_at,clock_timestamp())
          FROM ai_pipeline_run pipeline
         WHERE content.pipeline_run_id=pipeline.id
           AND content.status='WAITING_AI'
           AND pipeline.status IN (
             'WAITING_CLAIM_REVIEW','SUCCEEDED','FAILED','DEGRADED'
           )
        """
    )
    op.execute(
        r"""
        CREATE FUNCTION finalize_source_content_ai_run(
          p_pipeline_run_id uuid,p_terminal_status text,
          p_reason_code text,p_now timestamptz
        ) RETURNS uuid
        LANGUAGE plpgsql SECURITY DEFINER
        SET search_path=pg_catalog,public AS $$
        DECLARE v_outbox_id uuid;
        BEGIN
          IF substring(p_pipeline_run_id::text,15,1)<>'7'
             OR p_terminal_status NOT IN (
               'WAITING_CLAIM_REVIEW','SUCCEEDED','FAILED','DEGRADED'
             )
             OR (p_reason_code IS NOT NULL
                 AND p_reason_code !~ '^[A-Z0-9_]{1,80}$')
             OR (p_terminal_status IN ('FAILED','DEGRADED')
                 AND p_reason_code IS NULL)
             OR p_now NOT BETWEEN clock_timestamp()-interval '5 minutes'
                                  AND clock_timestamp()+interval '5 minutes' THEN
            RAISE EXCEPTION 'AI content finalization input is invalid';
          END IF;

          UPDATE source_content_outbox content
             SET status=CASE WHEN p_terminal_status='FAILED'
                             THEN 'DEAD_LETTER' ELSE 'COMPLETED' END,
                 attempt_count=CASE WHEN p_terminal_status='FAILED'
                                    THEN 5 ELSE content.attempt_count END,
                 last_error_code=CASE
                   WHEN p_terminal_status IN ('FAILED','DEGRADED')
                   THEN p_reason_code ELSE NULL END,
                 updated_at=p_now
            FROM ai_pipeline_run pipeline
           WHERE pipeline.id=p_pipeline_run_id
             AND pipeline.status=p_terminal_status
             AND content.pipeline_run_id=pipeline.id
             AND content.status='WAITING_AI'
          RETURNING content.id INTO v_outbox_id;
          RETURN v_outbox_id;
        END $$
        """
    )
    op.execute(
        f"REVOKE ALL ON FUNCTION {_FUNCTION_SIGNATURE} FROM PUBLIC,srbg_api_role,"
        "srbg_worker_role,srbg_publication_writer,srbg_projection_reader"
    )
    op.execute(
        "GRANT EXECUTE ON FUNCTION "
        "finalize_source_content_ai_run(uuid,text,text,timestamptz) "
        "TO srbg_worker_role"
    )


def downgrade() -> None:
    bind = op.get_bind()
    has_new_terminal_shape = bind.execute(
        sa.text(
            "SELECT EXISTS(SELECT 1 FROM source_content_outbox "
            "WHERE status='COMPLETED' OR (pipeline_run_id IS NOT NULL "
            "AND status IN ('FAILED','DEAD_LETTER')))"
        )
    ).scalar_one()
    if has_new_terminal_shape:
        raise RuntimeError(
            "AI_CONTENT_RESULT_LIFECYCLE_DOWNGRADE_BLOCKED: completed handoffs exist"
        )
    op.execute(f"DROP FUNCTION {_FUNCTION_SIGNATURE}")
    op.drop_constraint(
        "ck_source_content_outbox_consistency",
        "source_content_outbox",
        type_="check",
    )
    op.create_check_constraint(
        "ck_source_content_outbox_consistency",
        "source_content_outbox",
        "(status='PENDING' AND pipeline_run_id IS NULL AND last_error_code IS NULL) OR "
        "(status='WAITING_AI' AND pipeline_run_id IS NOT NULL "
        "AND last_error_code IS NULL) OR "
        "(status IN ('FAILED','DEAD_LETTER') AND pipeline_run_id IS NULL "
        "AND last_error_code IS NOT NULL)",
    )
    op.drop_constraint(
        "ck_source_content_outbox_status",
        "source_content_outbox",
        type_="check",
    )
    op.create_check_constraint(
        "ck_source_content_outbox_status",
        "source_content_outbox",
        "status IN ('PENDING','WAITING_AI','FAILED','DEAD_LETTER')",
    )
