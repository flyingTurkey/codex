# ruff: noqa: E501
"""Add T07 stream-level research, intent, admission and runtime facts.

Revision ID: 0042_t07_controlled_stream
Revises: 0041_t06_ai_runtime_projection
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0042_t07_controlled_stream"
down_revision = "0041_t06_ai_runtime_projection"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _uuid() -> postgresql.UUID:
    return postgresql.UUID(as_uuid=True)


def _json() -> postgresql.JSONB:
    return postgresql.JSONB(astext_type=sa.Text())


_GATE_KEYS = (
    "public_network_safe",
    "robots_allowed",
    "terms_allowed",
    "copyright_allowed",
    "access_boundary_allowed",
    "rate_limit_configured",
    "budget_available",
    "quality_passed",
    "circuit_closed",
    "runtime_gate_open",
)


def upgrade() -> None:
    op.create_table(
        "source_research_disposition_v2",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("source_id", _uuid(), sa.ForeignKey("source.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("source_stream_id", _uuid(), sa.ForeignKey("source_stream.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("disposition", sa.String(30), nullable=False),
        sa.Column("research_sha256", sa.String(64), nullable=False),
        sa.Column("recorded_by", _uuid(), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("disposition IN ('ADMISSION_READY','BOUNDARY_DISCOVERY','MANUAL_SHADOW')", name="ck_t07_research_disposition"),
        sa.CheckConstraint("research_sha256 ~ '^[a-f0-9]{64}$'", name="ck_t07_research_hash"),
    )
    op.create_table(
        "source_owner_intent_v2",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("source_id", _uuid(), sa.ForeignKey("source.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("source_stream_id", _uuid(), sa.ForeignKey("source_stream.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("desired_enabled", sa.Boolean(), nullable=False),
        sa.Column("recorded_by", _uuid(), nullable=False),
        sa.Column("request_id", sa.String(100), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("request_id", name="uq_t07_owner_intent_request"),
    )
    op.create_table(
        "source_stream_admission_decision_v2",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("source_id", _uuid(), sa.ForeignKey("source.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("source_stream_id", _uuid(), sa.ForeignKey("source_stream.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("rule_version", sa.String(100), nullable=False),
        sa.Column("verdict", sa.String(10), nullable=False),
        sa.Column("gates", _json(), nullable=False),
        sa.Column("evidence_sha256", sa.String(64), nullable=False),
        sa.Column("reason_codes", postgresql.ARRAY(sa.String(80)), nullable=False),
        sa.Column("decided_by", _uuid(), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("verdict IN ('ADMIT','OBSERVE','PAUSE')", name="ck_t07_admission_verdict"),
        sa.CheckConstraint("evidence_sha256 ~ '^[a-f0-9]{64}$'", name="ck_t07_admission_hash"),
        sa.CheckConstraint("jsonb_typeof(gates)='object'", name="ck_t07_admission_gates_object"),
        sa.CheckConstraint("valid_until>decided_at", name="ck_t07_admission_validity"),
        sa.CheckConstraint(
            "verdict<>'ADMIT' OR (" + " AND ".join(f"gates->>'{key}'='true'" for key in _GATE_KEYS) + ")",
            name="ck_t07_admission_admit_complete",
        ),
    )
    op.create_table(
        "source_stream_runtime_event_v2",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("source_id", _uuid(), sa.ForeignKey("source.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("source_stream_id", _uuid(), sa.ForeignKey("source_stream.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("admission_decision_id", _uuid(), sa.ForeignKey("source_stream_admission_decision_v2.id", ondelete="RESTRICT")),
        sa.Column("run_id", _uuid()),
        sa.Column("state", sa.String(30), nullable=False),
        sa.Column("actual_running", sa.Boolean(), nullable=False),
        sa.Column("reason_codes", postgresql.ARRAY(sa.String(80)), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("state IN ('PAUSED','SHADOW_AUTHORIZED','SHADOW_RUNNING','COMPLETED','FAILED')", name="ck_t07_runtime_state"),
        sa.CheckConstraint("actual_running=(state='SHADOW_RUNNING')", name="ck_t07_runtime_actual"),
        sa.CheckConstraint("(state='SHADOW_RUNNING')=(run_id IS NOT NULL)", name="ck_t07_runtime_run"),
    )
    op.execute("CREATE FUNCTION prevent_t07_append_only_mutation() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'T07_APPEND_ONLY_FACT'; END $$")
    for table in (
        "source_research_disposition_v2",
        "source_owner_intent_v2",
        "source_stream_admission_decision_v2",
        "source_stream_runtime_event_v2",
    ):
        op.execute(f"CREATE TRIGGER trg_{table}_append_only BEFORE UPDATE OR DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION prevent_t07_append_only_mutation()")
        op.execute(f"REVOKE ALL ON TABLE {table} FROM PUBLIC")

    op.execute("""
      CREATE FUNCTION authorize_source_stream_shadow_v2(
        p_event_id uuid,p_source_id uuid,p_source_stream_id uuid,p_now timestamptz
      ) RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER SET search_path=public,pg_temp AS $$
      DECLARE v_admission source_stream_admission_decision_v2%ROWTYPE;
      BEGIN
        SELECT decision.* INTO v_admission
          FROM source_stream_admission_decision_v2 decision
          JOIN source_stream stream ON stream.id=decision.source_stream_id
          JOIN source source_row ON source_row.id=decision.source_id
         WHERE decision.source_id=p_source_id
           AND decision.source_stream_id=p_source_stream_id
           AND stream.source_id=source_row.id AND stream.status='READY'
           AND source_row.desired_enabled=true AND source_row.manual_disabled_at IS NULL
           AND decision.verdict='ADMIT' AND decision.valid_until>p_now
           AND decision.id=(
             SELECT latest.id FROM source_stream_admission_decision_v2 latest
              WHERE latest.source_id=p_source_id
                AND latest.source_stream_id=p_source_stream_id
              ORDER BY latest.decided_at DESC,latest.id DESC LIMIT 1)
           AND NOT EXISTS(
             SELECT 1 FROM source_owner_intent_v2 later_intent
              WHERE later_intent.source_id=p_source_id
                AND later_intent.source_stream_id=p_source_stream_id
                AND later_intent.recorded_at>decision.decided_at
                AND later_intent.desired_enabled=false)
         ORDER BY decision.decided_at DESC,decision.id DESC LIMIT 1;
        IF v_admission.id IS NULL THEN RETURN NULL; END IF;
        INSERT INTO source_stream_runtime_event_v2(
          id,source_id,source_stream_id,admission_decision_id,run_id,state,
          actual_running,reason_codes,recorded_at)
        VALUES(p_event_id,p_source_id,p_source_stream_id,v_admission.id,NULL,
          'SHADOW_AUTHORIZED',false,ARRAY[]::text[],p_now);
        RETURN p_event_id;
      END $$
    """)
    op.execute("""
      CREATE FUNCTION start_source_stream_shadow_v2(
        p_event_id uuid,p_authorization_event_id uuid,p_run_id uuid,p_now timestamptz
      ) RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER SET search_path=public,pg_temp AS $$
      DECLARE v_authorization source_stream_runtime_event_v2%ROWTYPE;
      BEGIN
        SELECT runtime.* INTO v_authorization
          FROM source_stream_runtime_event_v2 runtime
          JOIN source_stream_admission_decision_v2 decision ON decision.id=runtime.admission_decision_id
          JOIN source source_row ON source_row.id=runtime.source_id
          JOIN source_stream stream ON stream.id=runtime.source_stream_id
         WHERE runtime.id=p_authorization_event_id
           AND runtime.state='SHADOW_AUTHORIZED'
           AND source_row.desired_enabled=true AND source_row.manual_disabled_at IS NULL
           AND stream.source_id=source_row.id AND stream.status='READY'
           AND decision.verdict='ADMIT' AND decision.valid_until>p_now
           AND decision.id=(
             SELECT latest.id FROM source_stream_admission_decision_v2 latest
              WHERE latest.source_id=runtime.source_id
                AND latest.source_stream_id=runtime.source_stream_id
              ORDER BY latest.decided_at DESC,latest.id DESC LIMIT 1)
           AND NOT EXISTS(
             SELECT 1 FROM source_owner_intent_v2 later_intent
              WHERE later_intent.source_id=runtime.source_id
                AND later_intent.source_stream_id=runtime.source_stream_id
                AND later_intent.recorded_at>runtime.recorded_at
                AND later_intent.desired_enabled=false)
         LIMIT 1;
        IF v_authorization.id IS NULL THEN RETURN NULL; END IF;
        INSERT INTO source_stream_runtime_event_v2(
          id,source_id,source_stream_id,admission_decision_id,run_id,state,
          actual_running,reason_codes,recorded_at)
        VALUES(p_event_id,v_authorization.source_id,v_authorization.source_stream_id,
          v_authorization.admission_decision_id,p_run_id,'SHADOW_RUNNING',true,
          ARRAY[]::text[],p_now);
        RETURN p_event_id;
      END $$
    """)
    op.execute("REVOKE ALL ON FUNCTION authorize_source_stream_shadow_v2(uuid,uuid,uuid,timestamptz) FROM PUBLIC")
    op.execute("REVOKE ALL ON FUNCTION start_source_stream_shadow_v2(uuid,uuid,uuid,timestamptz) FROM PUBLIC")
    op.execute("GRANT SELECT,INSERT ON source_research_disposition_v2,source_owner_intent_v2,source_stream_admission_decision_v2,source_stream_runtime_event_v2 TO srbg_api_role")
    op.execute("GRANT SELECT ON source_stream_admission_decision_v2,source_stream_runtime_event_v2,source_owner_intent_v2 TO srbg_worker_role")
    op.execute("GRANT EXECUTE ON FUNCTION authorize_source_stream_shadow_v2(uuid,uuid,uuid,timestamptz),start_source_stream_shadow_v2(uuid,uuid,uuid,timestamptz) TO srbg_worker_role")


def downgrade() -> None:
    bind = op.get_bind()
    durable = bind.execute(sa.text(
        "SELECT EXISTS(SELECT 1 FROM source_research_disposition_v2 "
        "UNION ALL SELECT 1 FROM source_owner_intent_v2 "
        "UNION ALL SELECT 1 FROM source_stream_admission_decision_v2 "
        "UNION ALL SELECT 1 FROM source_stream_runtime_event_v2)"
    )).scalar_one()
    if durable:
        raise RuntimeError("T07_DOWNGRADE_BLOCKED: durable source control facts exist")
    op.execute("DROP FUNCTION start_source_stream_shadow_v2(uuid,uuid,uuid,timestamptz)")
    op.execute("DROP FUNCTION authorize_source_stream_shadow_v2(uuid,uuid,uuid,timestamptz)")
    for table in (
        "source_stream_runtime_event_v2",
        "source_stream_admission_decision_v2",
        "source_owner_intent_v2",
        "source_research_disposition_v2",
    ):
        op.execute(f"DROP TRIGGER trg_{table}_append_only ON {table}")
        op.drop_table(table)
    op.execute("DROP FUNCTION prevent_t07_append_only_mutation()")
