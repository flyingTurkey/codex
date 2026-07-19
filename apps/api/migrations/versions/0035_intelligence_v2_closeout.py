# ruff: noqa: E501
"""Add durable v2 closeout observations, assessments and review reprocessing.

Revision ID: 0035_intelligence_v2_closeout
Revises: 0034_intelligence_v2
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0035_intelligence_v2_closeout"
down_revision = "0034_intelligence_v2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _uuid() -> postgresql.UUID:
    return postgresql.UUID(as_uuid=True)


def _json() -> postgresql.JSONB:
    return postgresql.JSONB(astext_type=sa.Text())


def upgrade() -> None:
    op.create_table(
        "owner_review_reprocessing_outbox_v2",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("case_id", _uuid(), sa.ForeignKey("owner_review_case_v2.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("decision_id", _uuid(), sa.ForeignKey("owner_review_decision_v2.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("document_version_id", _uuid(), sa.ForeignKey("document_version.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_error_code", sa.String(80)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("decision_id", name="uq_owner_review_reprocessing_decision_v2"),
        sa.CheckConstraint("status IN ('PENDING','PROCESSING','COMPLETED','FAILED','DEAD_LETTER')", name="ck_owner_review_reprocessing_status_v2"),
        sa.CheckConstraint("attempt_count BETWEEN 0 AND 3", name="ck_owner_review_reprocessing_attempts_v2"),
    )
    op.create_table(
        "ai_runtime_observation_v2",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("provider", sa.String(30), nullable=False),
        sa.Column("model", sa.String(100), nullable=False),
        sa.Column("environment", sa.String(30), nullable=False),
        sa.Column("worker_heartbeat_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("queue_healthy", sa.Boolean(), nullable=False),
        sa.Column("budget_healthy", sa.Boolean(), nullable=False),
        sa.Column("last_real_schema_success_at", sa.DateTime(timezone=True)),
        sa.Column("external_balance_state", sa.String(40), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("provider", "environment", "observed_at", name="uq_ai_runtime_observation_v2"),
        sa.CheckConstraint("external_balance_state IN ('SUFFICIENT_AT_LAST_REAL_CALL','INSUFFICIENT','UNKNOWN')", name="ck_ai_runtime_balance_v2"),
    )
    op.create_table(
        "ai_compensation_run_v2",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("original_pipeline_run_id", _uuid(), sa.ForeignKey("ai_pipeline_run.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("recovery_pipeline_run_id", _uuid(), sa.ForeignKey("ai_pipeline_run.id", ondelete="RESTRICT")),
        sa.Column("reason_code", sa.String(80), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("original_pipeline_run_id", name="uq_ai_compensation_original_v2"),
        sa.CheckConstraint("reason_code IN ('PROVIDER_TIMEOUT','PROVIDER_NETWORK_ERROR','TRANSIENT_UNAVAILABLE')", name="ck_ai_compensation_reason_v2"),
        sa.CheckConstraint("status IN ('PENDING','PROCESSING','SUCCEEDED','FAILED','DEAD_LETTER')", name="ck_ai_compensation_status_v2"),
        sa.CheckConstraint("attempt_count BETWEEN 0 AND 3", name="ck_ai_compensation_attempts_v2"),
    )
    op.create_table(
        "source_admission_assessment_v2",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("source_id", _uuid(), sa.ForeignKey("source.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("rule_version", sa.String(100), nullable=False),
        sa.Column("sample_cutoff", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lookback_days", sa.Integer(), nullable=False),
        sa.Column("sample_size", sa.Integer(), nullable=False),
        sa.Column("sample_manifest_sha256", sa.String(64), nullable=False),
        sa.Column("metrics", _json(), nullable=False),
        sa.Column("evidence_refs", _json(), nullable=False),
        sa.Column("verdict", sa.String(10), nullable=False),
        sa.Column("assessed_by", _uuid(), nullable=False),
        sa.Column("assessed_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("lookback_days=90", name="ck_source_admission_lookback_v2"),
        sa.CheckConstraint("sample_size BETWEEN 0 AND 30", name="ck_source_admission_sample_v2"),
        sa.CheckConstraint("sample_manifest_sha256 ~ '^[a-f0-9]{64}$'", name="ck_source_admission_hash_v2"),
        sa.CheckConstraint("verdict IN ('ADMIT','OBSERVE','PAUSE')", name="ck_source_admission_verdict_v2"),
    )
    op.execute("""
      CREATE FUNCTION prevent_v2_closeout_append_only_mutation() RETURNS trigger
      LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'V2_CLOSEOUT_APPEND_ONLY_FACT'; END $$
    """)
    for table in ("ai_runtime_observation_v2", "source_admission_assessment_v2"):
        op.execute(f"CREATE TRIGGER trg_{table}_append_only BEFORE UPDATE OR DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION prevent_v2_closeout_append_only_mutation()")
    op.execute("""
      INSERT INTO owner_review_reprocessing_outbox_v2(
        id,case_id,decision_id,document_version_id,status,attempt_count,
        available_at,created_at,updated_at)
      SELECT decision.id,decision.case_id,decision.id,review.document_version_id,
             'PENDING',0,decision.created_at,decision.created_at,decision.created_at
      FROM owner_review_decision_v2 decision
      JOIN owner_review_case_v2 review ON review.id=decision.case_id
      ON CONFLICT(decision_id) DO NOTHING
    """)
    for table in (
        "owner_review_reprocessing_outbox_v2",
        "ai_runtime_observation_v2",
        "ai_compensation_run_v2",
        "source_admission_assessment_v2",
    ):
        op.execute(f"REVOKE ALL ON TABLE {table} FROM PUBLIC")
    op.execute("GRANT SELECT,INSERT,UPDATE ON owner_review_reprocessing_outbox_v2 TO srbg_publication_writer")
    op.execute("GRANT DELETE ON intelligence_projection_v2,search_projection_v2 TO srbg_publication_writer")
    op.execute("GRANT SELECT,UPDATE ON owner_review_reprocessing_outbox_v2 TO srbg_worker_role")
    op.execute("GRANT SELECT,INSERT ON ai_runtime_observation_v2,ai_compensation_run_v2 TO srbg_worker_role")
    op.execute("GRANT UPDATE ON ai_compensation_run_v2 TO srbg_worker_role")
    op.execute("GRANT SELECT ON ai_runtime_observation_v2,source_admission_assessment_v2 TO srbg_api_role")
    op.execute("GRANT INSERT ON source_admission_assessment_v2 TO srbg_publication_writer")


def downgrade() -> None:
    bind = op.get_bind()
    durable = bind.execute(
        sa.text(
            "SELECT EXISTS(SELECT 1 FROM owner_review_reprocessing_outbox_v2 "
            "UNION ALL SELECT 1 FROM ai_runtime_observation_v2 "
            "UNION ALL SELECT 1 FROM ai_compensation_run_v2 "
            "UNION ALL SELECT 1 FROM source_admission_assessment_v2)"
        )
    ).scalar_one()
    if durable:
        raise RuntimeError("INTELLIGENCE_V2_CLOSEOUT_DOWNGRADE_BLOCKED: durable closeout facts exist")
    for table in ("source_admission_assessment_v2", "ai_runtime_observation_v2"):
        op.execute(f"DROP TRIGGER trg_{table}_append_only ON {table}")
    op.execute("DROP FUNCTION prevent_v2_closeout_append_only_mutation()")
    for table in (
        "source_admission_assessment_v2",
        "ai_compensation_run_v2",
        "ai_runtime_observation_v2",
        "owner_review_reprocessing_outbox_v2",
    ):
        op.drop_table(table)
