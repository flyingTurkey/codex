"""Freeze run policy, add aggregate promotion, and append-only rollback facts.

Revision ID: 0054_policy_optimization
Revises: 0053_safety_exception_lifecycle
"""
# ruff: noqa: S608

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0054_policy_optimization"
down_revision = "0053_safety_exception_lifecycle"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_HANDOFF_V3 = "handoff_source_content_to_ai(uuid,uuid,timestamptz)"
_HANDOFF_V4 = "handoff_source_content_to_ai(uuid,uuid,uuid,timestamptz)"
_POLICY_CONTEXT = "source_content_policy_context_v2(uuid)"
_RECOVERY = "reopen_source_content_ai_run(uuid,uuid,uuid,uuid,timestamptz,timestamptz)"
_ACTIVATE = (
    "append_qualification_policy_activation_v2("
    "uuid,text,uuid,uuid,text,text,uuid,uuid,timestamptz)"
)


def _uuid() -> postgresql.UUID:
    return postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.create_table(
        "qualification_policy_evaluation_invariant_v2",
        sa.Column(
            "evaluation_id",
            _uuid(),
            sa.ForeignKey("qualification_policy_evaluation_v2.id", ondelete="RESTRICT"),
            primary_key=True,
        ),
        sa.Column("terminal_cases", sa.Integer(), nullable=False),
        sa.Column("authority_violations", sa.Integer(), nullable=False),
        sa.Column("evidence_violations", sa.Integer(), nullable=False),
        sa.Column("projection_failures", sa.Integer(), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "terminal_cases>=0 AND authority_violations>=0 "
            "AND evidence_violations>=0 AND projection_failures>=0",
            name="ck_policy_evaluation_invariant_counts_v2",
        ),
    )
    op.execute(
        "CREATE TRIGGER trg_qualification_policy_evaluation_invariant_v2_append_only "
        "BEFORE UPDATE OR DELETE ON qualification_policy_evaluation_invariant_v2 "
        "FOR EACH ROW EXECUTE FUNCTION prevent_autonomous_policy_fact_mutation()"
    )
    op.execute(
        "REVOKE ALL ON TABLE qualification_policy_evaluation_invariant_v2 FROM PUBLIC"
    )
    op.create_table(
        "qualification_policy_shadow_window_v2",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column(
            "policy_bundle_id",
            _uuid(),
            sa.ForeignKey("qualification_policy_bundle_v2.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("window_started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_ended_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("total_cases", sa.Integer(), nullable=False),
        sa.Column("terminal_cases", sa.Integer(), nullable=False),
        sa.Column("decision_stability_bps", sa.Integer(), nullable=False),
        sa.Column("auto_accepted_count", sa.Integer(), nullable=False),
        sa.Column("auto_filtered_count", sa.Integer(), nullable=False),
        sa.Column("technical_retry_count", sa.Integer(), nullable=False),
        sa.Column("technical_failed_count", sa.Integer(), nullable=False),
        sa.Column("safety_hold_count", sa.Integer(), nullable=False),
        sa.Column("owner_suppressed_count", sa.Integer(), nullable=False),
        sa.Column("category_distribution", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("ai_cost_microusd", sa.BigInteger(), nullable=False),
        sa.Column("p95_latency_ms", sa.Integer(), nullable=False),
        sa.Column("locked_negative_leaks", sa.Integer(), nullable=False),
        sa.Column("schema_failures", sa.Integer(), nullable=False),
        sa.Column("authority_violations", sa.Integer(), nullable=False),
        sa.Column("evidence_violations", sa.Integer(), nullable=False),
        sa.Column("projection_failures", sa.Integer(), nullable=False),
        sa.Column("new_owner_semantic_tasks", sa.Integer(), nullable=False),
        sa.Column("technical_exception_bps", sa.Integer(), nullable=False),
        sa.Column("safety_hold_bps", sa.Integer(), nullable=False),
        sa.Column("suppression_bps", sa.Integer(), nullable=False),
        sa.Column("category_drift_bps", sa.Integer(), nullable=False),
        sa.Column("gate_passed", sa.Boolean(), nullable=False),
        sa.Column("affects_production", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "window_started_at<window_ended_at AND window_ended_at<=created_at",
            name="ck_policy_shadow_window_time_v2",
        ),
        sa.CheckConstraint(
            "total_cases>=0 AND terminal_cases BETWEEN 0 AND total_cases "
            "AND auto_accepted_count+auto_filtered_count+technical_retry_count+"
            "technical_failed_count+safety_hold_count+owner_suppressed_count=total_cases",
            name="ck_policy_shadow_window_counts_v2",
        ),
        sa.CheckConstraint(
            "decision_stability_bps BETWEEN 0 AND 10000 "
            "AND technical_exception_bps BETWEEN 0 AND 10000 "
            "AND safety_hold_bps BETWEEN 0 AND 10000 "
            "AND suppression_bps BETWEEN 0 AND 10000 "
            "AND category_drift_bps BETWEEN 0 AND 10000",
            name="ck_policy_shadow_window_rates_v2",
        ),
        sa.CheckConstraint(
            "locked_negative_leaks>=0 AND schema_failures>=0 "
            "AND authority_violations>=0 AND evidence_violations>=0 "
            "AND projection_failures>=0 AND new_owner_semantic_tasks=0 "
            "AND ai_cost_microusd>=0 AND p95_latency_ms>=0",
            name="ck_policy_shadow_window_invariants_v2",
        ),
        sa.CheckConstraint(
            "affects_production=false",
            name="ck_policy_shadow_window_no_production_effect_v2",
        ),
        sa.UniqueConstraint(
            "policy_bundle_id",
            "window_started_at",
            "window_ended_at",
            name="uq_policy_shadow_window_v2",
        ),
    )
    op.execute(
        "CREATE TRIGGER trg_qualification_policy_shadow_window_v2_append_only "
        "BEFORE UPDATE OR DELETE ON qualification_policy_shadow_window_v2 "
        "FOR EACH ROW EXECUTE FUNCTION prevent_autonomous_policy_fact_mutation()"
    )
    op.execute("REVOKE ALL ON TABLE qualification_policy_shadow_window_v2 FROM PUBLIC")

    op.add_column(
        "ai_pipeline_run",
        sa.Column(
            "policy_bundle_id",
            _uuid(),
            sa.ForeignKey("qualification_policy_bundle_v2.id", ondelete="RESTRICT"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_ai_pipeline_run_policy_bundle",
        "ai_pipeline_run",
        ["policy_bundle_id", "started_at"],
    )

    op.create_table(
        "qualification_policy_activation_v2",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column(
            "ledger_position",
            sa.BigInteger(),
            sa.Identity(always=True),
            nullable=False,
            unique=True,
        ),
        sa.Column("source_stream_policy_version", sa.String(120), nullable=False),
        sa.Column(
            "policy_bundle_id",
            _uuid(),
            sa.ForeignKey("qualification_policy_bundle_v2.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "previous_activation_id",
            _uuid(),
            sa.ForeignKey("qualification_policy_activation_v2.id", ondelete="RESTRICT"),
        ),
        sa.Column("action", sa.String(20), nullable=False),
        sa.Column("reason_code", sa.String(80), nullable=False),
        sa.Column(
            "offline_evaluation_id",
            _uuid(),
            sa.ForeignKey("qualification_policy_evaluation_v2.id", ondelete="RESTRICT"),
        ),
        sa.Column(
            "shadow_window_id",
            _uuid(),
            sa.ForeignKey("qualification_policy_shadow_window_v2.id", ondelete="RESTRICT"),
        ),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "action IN ('BOOTSTRAP','PROMOTE','ROLLBACK')",
            name="ck_policy_activation_action_v2",
        ),
        sa.CheckConstraint(
            "reason_code ~ '^[A-Z0-9_]{1,80}$'",
            name="ck_policy_activation_reason_v2",
        ),
        sa.CheckConstraint(
            "(action='BOOTSTRAP' AND previous_activation_id IS NULL "
            "AND offline_evaluation_id IS NULL AND shadow_window_id IS NULL) OR "
            "(action='PROMOTE' AND previous_activation_id IS NOT NULL "
            "AND offline_evaluation_id IS NOT NULL AND shadow_window_id IS NOT NULL) OR "
            "(action='ROLLBACK' AND previous_activation_id IS NOT NULL "
            "AND offline_evaluation_id IS NULL AND shadow_window_id IS NULL)",
            name="ck_policy_activation_evidence_v2",
        ),
        sa.UniqueConstraint(
            "previous_activation_id",
            "action",
            name="uq_policy_activation_transition_v2",
        ),
    )
    op.create_index(
        "ix_policy_activation_active_v2",
        "qualification_policy_activation_v2",
        ["source_stream_policy_version", "activated_at", "id"],
    )
    op.execute(
        """
        CREATE VIEW active_qualification_policy_v2 AS
        SELECT DISTINCT ON (activation.source_stream_policy_version)
               activation.id AS activation_id,
               activation.source_stream_policy_version,
               activation.policy_bundle_id,
               activation.action,
               activation.reason_code,
               activation.activated_at
          FROM qualification_policy_activation_v2 activation
         ORDER BY activation.source_stream_policy_version,
                  activation.ledger_position DESC
        """
    )

    op.create_table(
        "qualification_policy_health_v2",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column(
            "activation_id",
            _uuid(),
            sa.ForeignKey("qualification_policy_activation_v2.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("window_started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_ended_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("total_runs", sa.Integer(), nullable=False),
        sa.Column("feed_yield_bps", sa.Integer(), nullable=False),
        sa.Column("technical_exception_bps", sa.Integer(), nullable=False),
        sa.Column("safety_hold_bps", sa.Integer(), nullable=False),
        sa.Column("suppression_bps", sa.Integer(), nullable=False),
        sa.Column("schema_failures", sa.Integer(), nullable=False),
        sa.Column("projection_failures", sa.Integer(), nullable=False),
        sa.Column("hard_negative_leaks", sa.Integer(), nullable=False),
        sa.Column("cost_budget_exceeded", sa.Boolean(), nullable=False),
        sa.Column("category_drift_bps", sa.Integer(), nullable=False),
        sa.Column("regression_reason_codes", postgresql.ARRAY(sa.String(80)), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "window_started_at<window_ended_at AND window_ended_at<=recorded_at",
            name="ck_policy_health_window_v2",
        ),
        sa.CheckConstraint(
            "total_runs>=0 AND schema_failures>=0 AND projection_failures>=0 "
            "AND hard_negative_leaks>=0",
            name="ck_policy_health_counts_v2",
        ),
        sa.CheckConstraint(
            "feed_yield_bps BETWEEN 0 AND 10000 "
            "AND technical_exception_bps BETWEEN 0 AND 10000 "
            "AND safety_hold_bps BETWEEN 0 AND 10000 "
            "AND suppression_bps BETWEEN 0 AND 10000 "
            "AND category_drift_bps BETWEEN 0 AND 10000",
            name="ck_policy_health_rates_v2",
        ),
        sa.UniqueConstraint(
            "activation_id",
            "window_started_at",
            "window_ended_at",
            name="uq_policy_health_window_v2",
        ),
    )
    for table in ("qualification_policy_activation_v2", "qualification_policy_health_v2"):
        op.execute(
            f"CREATE TRIGGER trg_{table}_append_only BEFORE UPDATE OR DELETE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION prevent_autonomous_policy_fact_mutation()"
        )
        op.execute(f"REVOKE ALL ON TABLE {table} FROM PUBLIC")

    _create_activation_command()
    _create_source_content_policy_context()
    _create_policy_bound_handoff()
    _replace_recovery_function(include_policy=True)

    op.execute(
        "REVOKE EXECUTE ON FUNCTION "
        f"{_HANDOFF_V3} FROM srbg_worker_role"
    )
    op.execute(f"REVOKE ALL ON FUNCTION {_HANDOFF_V4} FROM PUBLIC")
    op.execute(f"GRANT EXECUTE ON FUNCTION {_HANDOFF_V4} TO srbg_worker_role")
    op.execute(f"REVOKE ALL ON FUNCTION {_POLICY_CONTEXT} FROM PUBLIC")
    op.execute(f"GRANT EXECUTE ON FUNCTION {_POLICY_CONTEXT} TO srbg_worker_role")
    op.execute(f"REVOKE ALL ON FUNCTION {_ACTIVATE} FROM PUBLIC")
    op.execute(
        f"GRANT EXECUTE ON FUNCTION {_ACTIVATE} TO srbg_api_role,srbg_worker_role"
    )
    op.execute(
        "GRANT SELECT ON qualification_policy_activation_v2,"
        "active_qualification_policy_v2,qualification_policy_health_v2,"
        "qualification_policy_evaluation_invariant_v2,"
        "qualification_policy_shadow_window_v2 "
        "TO srbg_api_role,srbg_worker_role,srbg_publication_writer"
    )
    op.execute(
        "GRANT INSERT ON qualification_policy_health_v2,"
        "qualification_policy_evaluation_invariant_v2,"
        "qualification_policy_shadow_window_v2 TO srbg_api_role"
    )
    op.execute(
        "GRANT INSERT ON qualification_policy_health_v2,"
        "qualification_policy_shadow_window_v2 TO srbg_worker_role"
    )
    op.execute(
        "GRANT SELECT ON publication_decision_v2,event_suppression_match_v2,"
        "feed_suppression_effective_v2,ai_budget_reservation,ai_budget_policy,"
        "ai_budget_month TO srbg_api_role,srbg_worker_role"
    )


def _create_activation_command() -> None:
    op.execute(
        r"""
        CREATE FUNCTION append_qualification_policy_activation_v2(
          p_activation_id uuid,p_stream_version text,p_policy_bundle_id uuid,
          p_previous_activation_id uuid,p_action text,p_reason_code text,
          p_offline_evaluation_id uuid,p_shadow_window_id uuid,
          p_now timestamptz
        ) RETURNS uuid
        LANGUAGE plpgsql SECURITY DEFINER
        SET search_path=pg_catalog,public AS $$
        DECLARE
          v_current qualification_policy_activation_v2%ROWTYPE;
          v_previous qualification_policy_activation_v2%ROWTYPE;
          v_bundle qualification_policy_bundle_v2%ROWTYPE;
          v_offline qualification_policy_evaluation_v2%ROWTYPE;
          v_shadow qualification_policy_shadow_window_v2%ROWTYPE;
          v_offline_invariant qualification_policy_evaluation_invariant_v2%ROWTYPE;
        BEGIN
          IF substring(p_activation_id::text,15,1)<>'7'
             OR p_stream_version IS NULL OR length(p_stream_version) NOT BETWEEN 1 AND 120
             OR p_action NOT IN ('BOOTSTRAP','PROMOTE','ROLLBACK')
             OR p_reason_code !~ '^[A-Z0-9_]{1,80}$'
             OR p_now NOT BETWEEN clock_timestamp()-interval '5 minutes'
                                  AND clock_timestamp()+interval '5 minutes' THEN
            RAISE EXCEPTION 'policy activation input is invalid';
          END IF;
          PERFORM pg_advisory_xact_lock(hashtext(p_stream_version));
          SELECT * INTO v_bundle FROM qualification_policy_bundle_v2
           WHERE id=p_policy_bundle_id;
          IF NOT FOUND OR v_bundle.source_stream_policy_version<>p_stream_version THEN
            RAISE EXCEPTION 'policy bundle stream identity mismatch';
          END IF;
          SELECT activation.* INTO v_current
            FROM qualification_policy_activation_v2 activation
           WHERE activation.source_stream_policy_version=p_stream_version
           ORDER BY activation.ledger_position DESC LIMIT 1;
          IF p_action='BOOTSTRAP'
             AND v_current.policy_bundle_id=p_policy_bundle_id
             AND v_current.action='BOOTSTRAP' THEN
            RETURN v_current.id;
          END IF;
          IF p_action IN ('PROMOTE','ROLLBACK')
             AND v_current.action=p_action
             AND v_current.policy_bundle_id=p_policy_bundle_id
             AND v_current.previous_activation_id=p_previous_activation_id THEN
            RETURN v_current.id;
          END IF;

          IF p_action='BOOTSTRAP' THEN
            IF v_current.id IS NOT NULL OR p_previous_activation_id IS NOT NULL
               OR p_offline_evaluation_id IS NOT NULL
               OR p_shadow_window_id IS NOT NULL
               OR v_bundle.policy_version<>'qualification-policy-2.2.0'
               OR v_bundle.global_rule_version<>'global-rules-2.1.0'
               OR v_bundle.prompt_version<>'autonomous-classify-2.7.0'
               OR v_bundle.schema_version<>'autonomous-classify-output-2.0.0'
               OR v_bundle.code_version<>'issue-41-production-switch-1'
               OR v_bundle.ai_provider<>'deepseek'
               OR v_bundle.ai_model<>'deepseek-v4-flash'
               OR v_bundle.policy_payload->'source_allow_terms'<>'[]'::jsonb
               OR v_bundle.policy_payload->'source_exclude_terms'<>'[]'::jsonb THEN
              RAISE EXCEPTION 'policy bootstrap authority denied';
            END IF;
          ELSIF p_action='PROMOTE' THEN
            IF v_current.id IS NULL OR v_current.id<>p_previous_activation_id THEN
              RAISE EXCEPTION 'policy activation predecessor conflict';
            END IF;
            IF v_bundle.ai_provider<>'deepseek'
               OR v_bundle.ai_model<>'deepseek-v4-flash'
               OR v_bundle.prompt_version<>'autonomous-classify-2.7.0'
               OR v_bundle.schema_version<>'autonomous-classify-output-2.0.0' THEN
              RAISE EXCEPTION 'policy runtime identity unsupported';
            END IF;
            SELECT * INTO v_offline FROM qualification_policy_evaluation_v2
             WHERE id=p_offline_evaluation_id AND policy_bundle_id=p_policy_bundle_id
               AND mode='OFFLINE_REPLAY';
            SELECT * INTO v_shadow FROM qualification_policy_shadow_window_v2
             WHERE id=p_shadow_window_id AND policy_bundle_id=p_policy_bundle_id;
            SELECT * INTO v_offline_invariant
              FROM qualification_policy_evaluation_invariant_v2
             WHERE evaluation_id=p_offline_evaluation_id;
            IF v_offline.id IS NULL OR NOT v_offline.gate_passed
               OR v_offline.authorizes_production<>false
               OR v_offline.total_cases<=0
               OR v_offline_invariant.evaluation_id IS NULL
               OR v_offline_invariant.terminal_cases<>v_offline.total_cases
               OR v_offline.precision_bps<9000 OR v_offline.recall_bps<9000
               OR v_offline.locked_negative_leaks<>0
               OR v_offline.schema_valid_bps<>10000
               OR v_offline_invariant.authority_violations<>0
               OR v_offline_invariant.evidence_violations<>0
               OR v_offline_invariant.projection_failures<>0
               OR v_offline.new_owner_semantic_tasks<>0 THEN
              RAISE EXCEPTION 'offline replay gate failed';
            END IF;
            IF v_shadow.id IS NULL OR NOT v_shadow.gate_passed
               OR v_shadow.affects_production<>false
               OR v_shadow.total_cases<20
               OR v_shadow.terminal_cases<>v_shadow.total_cases
               OR (
                 SELECT count(DISTINCT shadow.document_version_id)
                   FROM qualification_shadow_decision_v2 shadow
                  WHERE shadow.policy_bundle_id=p_policy_bundle_id
                    AND shadow.decided_at>=v_shadow.window_started_at
                    AND shadow.decided_at<v_shadow.window_ended_at
               )<>v_shadow.total_cases
               OR v_shadow.decision_stability_bps<9000
               OR v_shadow.locked_negative_leaks<>0
               OR v_shadow.schema_failures<>0
               OR v_shadow.authority_violations<>0
               OR v_shadow.evidence_violations<>0
               OR v_shadow.projection_failures<>0
               OR v_shadow.new_owner_semantic_tasks<>0
               OR v_shadow.technical_exception_bps>2000
               OR v_shadow.safety_hold_bps>2000
               OR v_shadow.suppression_bps>2000
               OR v_shadow.category_drift_bps>2000
               OR EXISTS(
                 SELECT 1 FROM qualification_shadow_decision_v2 shadow
                  WHERE shadow.policy_bundle_id=p_policy_bundle_id
                    AND shadow.decided_at>=v_shadow.window_started_at
                    AND shadow.decided_at<v_shadow.window_ended_at
                    AND shadow.affects_production<>false
               ) THEN
              RAISE EXCEPTION 'aggregate shadow gate failed';
            END IF;
          ELSE
            IF v_current.id IS NULL OR v_current.id<>p_previous_activation_id
               OR p_offline_evaluation_id IS NOT NULL
               OR p_shadow_window_id IS NOT NULL
               OR v_current.previous_activation_id IS NULL THEN
              RAISE EXCEPTION 'policy rollback predecessor conflict';
            END IF;
            SELECT * INTO v_previous FROM qualification_policy_activation_v2
             WHERE id=v_current.previous_activation_id;
            IF v_previous.id IS NULL OR v_previous.policy_bundle_id<>p_policy_bundle_id THEN
              RAISE EXCEPTION 'policy rollback target is not previous champion';
            END IF;
          END IF;

          INSERT INTO qualification_policy_activation_v2(
            id,source_stream_policy_version,policy_bundle_id,previous_activation_id,
            action,reason_code,offline_evaluation_id,shadow_window_id,activated_at
          ) VALUES(
            p_activation_id,p_stream_version,p_policy_bundle_id,p_previous_activation_id,
            p_action,p_reason_code,p_offline_evaluation_id,p_shadow_window_id,p_now
          ) ON CONFLICT(previous_activation_id,action) DO NOTHING;
          RETURN (
            SELECT activation.id FROM qualification_policy_activation_v2 activation
           WHERE activation.source_stream_policy_version=p_stream_version
             ORDER BY activation.ledger_position DESC LIMIT 1
          );
        END $$
        """
    )


def _create_policy_bound_handoff() -> None:
    op.execute(
        r"""
        CREATE FUNCTION handoff_source_content_to_ai(
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
                          'legacy-source-policy')
            INTO v_document_version_id,v_input_sha256,v_stream_version
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
            completed_at,failure_code,policy_bundle_id
          ) VALUES(
            p_pipeline_run_id,v_document_version_id,'LIVE','QUEUED',
            v_input_sha256,p_now,NULL,NULL,p_policy_bundle_id
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


def _create_source_content_policy_context() -> None:
    op.execute(
        r"""
        CREATE FUNCTION source_content_policy_context_v2(p_outbox_id uuid)
        RETURNS TABLE(source_stream_policy_version text,policy_bundle_id uuid)
        LANGUAGE plpgsql STABLE SECURITY DEFINER
        SET search_path=pg_catalog,public AS $$
        BEGIN
          IF substring(p_outbox_id::text,15,1)<>'7' THEN
            RAISE EXCEPTION 'source content policy input is invalid';
          END IF;
          RETURN QUERY
          SELECT stream.version::text,active.policy_bundle_id
            FROM source_content_outbox content
            JOIN document_version version ON version.id=content.document_version_id
            JOIN document document ON document.id=version.document_id
            LEFT JOIN raw_object_capture capture
              ON capture.id=version.raw_object_capture_id
            LEFT JOIN fetch_run fetch_row ON fetch_row.id=capture.fetch_run_id
            LEFT JOIN stream_config_version config
              ON config.id=fetch_row.stream_config_version_id
            LEFT JOIN LATERAL(
              SELECT policy.policy_version FROM source_policy policy
               WHERE policy.source_id=document.source_id AND policy.status='VALID'
               ORDER BY policy.created_at DESC LIMIT 1
            ) source_policy ON true
            CROSS JOIN LATERAL(
              SELECT COALESCE(
                config.config_sha256,source_policy.policy_version,'legacy-source-policy'
              ) AS version
            ) stream
            LEFT JOIN active_qualification_policy_v2 active
              ON active.source_stream_policy_version=stream.version
           WHERE content.id=p_outbox_id;
        END $$
        """
    )


def _replace_recovery_function(*, include_policy: bool) -> None:
    policy_column = ",policy_bundle_id" if include_policy else ""
    policy_value = ",pipeline.policy_bundle_id" if include_policy else ""
    op.execute(
        f"""
        CREATE OR REPLACE FUNCTION reopen_source_content_ai_run(
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
             OR p_requested_at IS NULL OR p_now IS NULL OR p_now<p_requested_at THEN
            RAISE EXCEPTION 'technical retry input is invalid';
          END IF;
          SELECT content.id,compensation.reason_code
            INTO v_outbox_id,v_reason_code
            FROM owner_exception_event_v2 event
            JOIN owner_exception_v2 exception ON exception.id=event.exception_id
            JOIN ai_compensation_run_v2 compensation
              ON compensation.original_pipeline_run_id=p_pipeline_run_id
            JOIN ai_pipeline_run pipeline ON pipeline.id=p_pipeline_run_id
            JOIN source_content_outbox content ON content.pipeline_run_id=p_pipeline_run_id
           WHERE event.id=p_retry_event_id AND event.event_type='RETRY_REQUESTED'
             AND event.created_at=p_requested_at
             AND exception.kind='TECHNICAL' AND exception.status='OPEN'
             AND exception.safe_metadata->>'pipeline_run_id'=p_pipeline_run_id::text
             AND compensation.status='DEAD_LETTER'
             AND compensation.completed_at<p_requested_at
             AND pipeline.status='FAILED' AND pipeline.failure_code='TECHNICAL_FAILED'
             AND content.status='DEAD_LETTER'
           FOR UPDATE OF exception,compensation,pipeline,content;
          IF v_outbox_id IS NULL THEN RETURN NULL; END IF;
          INSERT INTO ai_pipeline_run(
            id,document_version_id,mode,status,input_sha256,started_at,
            completed_at,failure_code,controlled_run_id{policy_column}
          )
          SELECT p_recovery_pipeline_run_id,pipeline.document_version_id,
                 pipeline.mode,'QUEUED',pipeline.input_sha256,p_now,NULL,NULL,
                 pipeline.controlled_run_id{policy_value}
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


def downgrade() -> None:
    bind = op.get_bind()
    durable = bind.execute(
        sa.text(
            "SELECT EXISTS("
            "SELECT 1 FROM qualification_policy_activation_v2 UNION ALL "
            "SELECT 1 FROM qualification_policy_health_v2 UNION ALL "
            "SELECT 1 FROM qualification_policy_shadow_window_v2 UNION ALL "
            "SELECT 1 FROM qualification_policy_evaluation_invariant_v2 UNION ALL "
            "SELECT 1 FROM ai_pipeline_run WHERE policy_bundle_id IS NOT NULL)"
        )
    ).scalar_one()
    if durable:
        raise RuntimeError("POLICY_ACTIVATION_DOWNGRADE_BLOCKED")

    _replace_recovery_function(include_policy=False)
    op.execute(f"DROP FUNCTION {_POLICY_CONTEXT}")
    op.execute(f"REVOKE EXECUTE ON FUNCTION {_HANDOFF_V4} FROM srbg_worker_role")
    op.execute(f"DROP FUNCTION {_HANDOFF_V4}")
    op.execute(f"GRANT EXECUTE ON FUNCTION {_HANDOFF_V3} TO srbg_worker_role")
    op.execute(f"DROP FUNCTION {_ACTIVATE}")
    op.execute("DROP VIEW active_qualification_policy_v2")
    for table in ("qualification_policy_health_v2", "qualification_policy_activation_v2"):
        op.execute(f"DROP TRIGGER trg_{table}_append_only ON {table}")
        op.drop_table(table)
    op.drop_index("ix_ai_pipeline_run_policy_bundle", table_name="ai_pipeline_run")
    op.drop_column("ai_pipeline_run", "policy_bundle_id")
    op.execute(
        "DROP TRIGGER trg_qualification_policy_shadow_window_v2_append_only "
        "ON qualification_policy_shadow_window_v2"
    )
    op.drop_table("qualification_policy_shadow_window_v2")
    op.execute(
        "DROP TRIGGER trg_qualification_policy_evaluation_invariant_v2_append_only "
        "ON qualification_policy_evaluation_invariant_v2"
    )
    op.drop_table("qualification_policy_evaluation_invariant_v2")
