"""Project autonomous safety holds into the shared Owner exception lifecycle.

Revision ID: 0053_safety_exception_lifecycle
Revises: 0052_feed_suppression_projection
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision = "0053_safety_exception_lifecycle"
down_revision = "0052_feed_suppression_projection"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_FUNCTION_SIGNATURE = "record_safety_exception_v2(uuid,uuid,uuid,uuid,timestamptz)"

_VISIBLE_PROJECTION_SQL = r"""
CREATE OR REPLACE VIEW visible_intelligence_projection_v2
WITH (security_barrier=true) AS
SELECT projection.*
FROM intelligence_projection_v2 projection
WHERE NOT EXISTS (
  SELECT 1
  FROM event_suppression_match_v2 match
  JOIN feed_suppression_effective_v2 rule
    ON rule.scope=match.scope AND rule.target_key=match.target_key
  WHERE match.event_id=projection.event_id
    AND (rule.revoked_at IS NULL OR projection.projected_at<=rule.revoked_at)
)
AND NOT EXISTS (
  SELECT 1
  FROM owner_exception_v2 exception
  WHERE exception.kind='SAFETY'
    AND exception.status='OPEN'
    AND exception.document_version_id=projection.document_version_id
)
"""

_PREVIOUS_VISIBLE_PROJECTION_SQL = r"""
CREATE OR REPLACE VIEW visible_intelligence_projection_v2
WITH (security_barrier=true) AS
SELECT projection.*
FROM intelligence_projection_v2 projection
WHERE NOT EXISTS (
  SELECT 1
  FROM event_suppression_match_v2 match
  JOIN feed_suppression_effective_v2 rule
    ON rule.scope=match.scope AND rule.target_key=match.target_key
  WHERE match.event_id=projection.event_id
    AND (rule.revoked_at IS NULL OR projection.projected_at<=rule.revoked_at)
)
"""


def upgrade() -> None:
    op.create_index(
        "uq_owner_safety_exception_decision_v2",
        "owner_exception_v2",
        ["decision_id"],
        unique=True,
        postgresql_where=sa.text("kind='SAFETY' AND decision_id IS NOT NULL"),
    )
    op.execute(
        r"""
        CREATE FUNCTION record_safety_exception_v2(
          p_decision_id uuid,p_exception_id uuid,p_created_event_id uuid,p_audit_id uuid,
          p_now timestamptz
        ) RETURNS uuid
        LANGUAGE plpgsql SECURITY DEFINER
        SET search_path=pg_catalog,public AS $$
        DECLARE
          v_existing uuid;
          v_decision automated_qualification_decision_v2%ROWTYPE;
          v_source_id uuid;
          v_source_stream_id uuid;
          v_source_name text;
          v_discovered_at timestamptz;
          v_safe_evidence_ids jsonb;
          v_signals jsonb;
          v_signal text;
          v_overrideability text;
          v_safety_reason_code text;
        BEGIN
          IF substring(p_exception_id::text,15,1)<>'7'
             OR substring(p_created_event_id::text,15,1)<>'7'
             OR substring(p_audit_id::text,15,1)<>'7'
             OR p_now IS NULL THEN
            RAISE EXCEPTION 'safety exception input is invalid';
          END IF;
          SELECT safety_exception.id INTO v_existing
            FROM owner_exception_v2 safety_exception
           WHERE safety_exception.kind='SAFETY'
             AND safety_exception.decision_id=p_decision_id;
          IF v_existing IS NOT NULL THEN
            RETURN v_existing;
          END IF;

          SELECT stored_decision.* INTO v_decision
            FROM automated_qualification_decision_v2 stored_decision
           WHERE stored_decision.id=p_decision_id
             AND stored_decision.disposition='SAFETY_HOLD'
           FOR SHARE;
          IF v_decision.id IS NULL THEN
            RAISE EXCEPTION 'safety hold decision does not exist';
          END IF;

          v_signals := CASE
            WHEN jsonb_typeof(v_decision.model_candidate->'security_signals')='array'
             AND jsonb_array_length(v_decision.model_candidate->'security_signals')>0
            THEN v_decision.model_candidate->'security_signals'
            WHEN EXISTS(
              SELECT 1 FROM jsonb_array_elements_text(v_decision.rule_signals) signal
              WHERE signal LIKE 'SAFETY_SIGNAL:%'
            ) THEN (
              SELECT jsonb_agg(substring(signal from 15))
              FROM jsonb_array_elements_text(v_decision.rule_signals) signal
              WHERE signal LIKE 'SAFETY_SIGNAL:%'
            )
            ELSE v_decision.rule_signals
          END;
          FOR v_signal IN
            SELECT upper(btrim(value)) FROM jsonb_array_elements_text(v_signals) value
          LOOP
            IF v_signal IN (
              'PRIVATE_NETWORK_TARGET','LOOPBACK_TARGET','CLOUD_METADATA_TARGET',
              'MALICIOUS_PAYLOAD','ACCESS_CONTROL_BYPASS','SAFE_BYTES_UNAVAILABLE'
            ) THEN
              v_overrideability := 'HARD_BLOCK';
              v_safety_reason_code := v_signal;
              EXIT;
            ELSIF v_signal IN (
              'MANDATORY_MALWARE_SCAN_FAILED','MALWARE_SCAN_FAILED',
              'MALWARE_SCAN_INCONCLUSIVE'
            ) THEN
              v_overrideability := 'HARD_BLOCK';
              v_safety_reason_code := 'MANDATORY_MALWARE_SCAN_FAILED';
              EXIT;
            ELSIF v_signal IN ('PROMPT_INJECTION','PROMPT_INJECTION_DETECTED') THEN
              IF v_safety_reason_code IS NULL THEN
                v_overrideability := 'OWNER_DECIDABLE';
                v_safety_reason_code := 'PROMPT_INJECTION_DETECTED';
              END IF;
            ELSIF v_signal IN ('SUSPICIOUS_PATTERN','SUSPICIOUS_MODEL_SIGNAL') THEN
              IF v_safety_reason_code IS NULL THEN
                v_overrideability := 'OWNER_DECIDABLE';
                v_safety_reason_code := 'SUSPICIOUS_MODEL_SIGNAL';
              END IF;
            ELSE
              v_overrideability := 'HARD_BLOCK';
              v_safety_reason_code := 'UNRECOGNIZED_SECURITY_SIGNAL';
              EXIT;
            END IF;
          END LOOP;
          IF v_safety_reason_code IS NULL THEN
            RAISE EXCEPTION 'safety hold has no server-classifiable signal';
          END IF;

          SELECT d.source_id,s.name,d.first_discovered_at,cap.source_stream_id
            INTO v_source_id,v_source_name,v_discovered_at,v_source_stream_id
            FROM document_version dv
            JOIN document d ON d.id=dv.document_id
            JOIN source s ON s.id=d.source_id
            LEFT JOIN LATERAL (
              SELECT fr.source_stream_id
                FROM raw_object_capture capture_row
                JOIN fetch_run fr ON fr.id=capture_row.fetch_run_id
               WHERE capture_row.raw_object_id=v_decision.raw_object_id
               ORDER BY capture_row.captured_at DESC
               LIMIT 1
            ) cap ON true
           WHERE dv.id=v_decision.document_version_id;
          IF v_source_id IS NULL THEN
            RAISE EXCEPTION 'safety hold source context does not exist';
          END IF;

          SELECT COALESCE(jsonb_agg(valid_locator.id ORDER BY valid_locator.id),'[]'::jsonb)
            INTO v_safe_evidence_ids
            FROM (
              SELECT CASE WHEN locator ~*
                '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$'
                THEN locator::uuid END AS id
              FROM unnest(v_decision.evidence_locators) locator
            ) valid_locator
            JOIN document_text_block evidence_block
              ON evidence_block.id=valid_locator.id
            JOIN document_page evidence_page
              ON evidence_page.id=evidence_block.document_page_id
           WHERE valid_locator.id IS NOT NULL
             AND evidence_page.document_version_id=v_decision.document_version_id;

          INSERT INTO owner_exception_v2(
            id,kind,status,overrideability,source_id,source_stream_id,
            document_version_id,decision_id,reason_codes,safe_metadata,
            attempt_count,version,opened_at,updated_at,resolved_at
          ) VALUES(
            p_exception_id,'SAFETY','OPEN',v_overrideability,v_source_id,v_source_stream_id,
            v_decision.document_version_id,v_decision.id,v_decision.reason_codes,
            jsonb_build_object(
              'safety_reason_code',v_safety_reason_code,
              'safe_title',CASE WHEN v_overrideability='HARD_BLOCK'
                THEN '内容安全硬阻断' ELSE '内容安全风险待处理' END,
              'source_name',v_source_name,
              'discovered_at',v_discovered_at,
              'safe_evidence_ids',v_safe_evidence_ids
            ),
            v_decision.attempt_number,1,p_now,p_now,NULL
          );
          INSERT INTO owner_exception_event_v2(
            id,exception_id,event_type,expected_version,idempotency_key,
            safe_metadata,created_at
          ) VALUES(
            p_created_event_id,p_exception_id,'CREATED',1,p_decision_id,
            jsonb_build_object(
              'safety_reason_code',v_safety_reason_code,
              'overrideability',v_overrideability
            ),
            p_now
          );
          PERFORM append_audit_event(
            p_audit_id,'SAFETY_HOLD_CREATED',
            '019b0000-0000-7000-8000-000000009002'::uuid,
            'OWNER_EXCEPTION',p_exception_id,NULL,
            jsonb_build_object(
              'safety_reason_code',v_safety_reason_code,
              'overrideability',v_overrideability
            ),
            'SERVER_SAFETY_SIGNAL_CLASSIFIED',p_decision_id::text,p_now
          );
          RETURN p_exception_id;
        END $$
        """
    )
    op.execute(
        f"REVOKE ALL ON FUNCTION {_FUNCTION_SIGNATURE} FROM PUBLIC,srbg_api_role,"
        "srbg_worker_role,srbg_publication_writer,srbg_projection_reader"
    )
    op.execute(
        "GRANT EXECUTE ON FUNCTION record_safety_exception_v2("
        "uuid,uuid,uuid,uuid,timestamptz) TO srbg_worker_role"
    )
    op.execute(_VISIBLE_PROJECTION_SQL)


def downgrade() -> None:
    bind = op.get_bind()
    durable = bind.execute(
        sa.text("SELECT EXISTS(SELECT 1 FROM owner_exception_v2 WHERE kind='SAFETY')")
    ).scalar_one()
    if durable:
        raise RuntimeError("SAFETY_EXCEPTION_DOWNGRADE_BLOCKED")
    op.execute(_PREVIOUS_VISIBLE_PROJECTION_SQL)
    op.execute(f"DROP FUNCTION {_FUNCTION_SIGNATURE}")
    op.drop_index(
        "uq_owner_safety_exception_decision_v2",
        table_name="owner_exception_v2",
    )
