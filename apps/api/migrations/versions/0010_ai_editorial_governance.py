"""Round 09 controlled AI pipeline, editorial review, and projection governance.

Revision ID: 0010_ai_editorial_governance
Revises: 0009_dedup_events_scoring
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0010_ai_editorial_governance"
down_revision = "0009_dedup_events_scoring"
branch_labels = None
depends_on = None

ROUND09_TABLES = (
    "ai_prompt_version",
    "ai_schema_version",
    "ai_model_profile",
    "ai_pipeline_run",
    "ai_step_run",
    "ai_security_scan",
    "security_review_decision",
    "review_decision",
    "ai_replay_run",
    "ai_shadow_result",
    "ai_quality_report",
    "publication_projection_state",
    "publication_projection_invalidation",
)


def _uuid() -> postgresql.UUID:
    return postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    _extend_review_tasks()
    _create_ai_registry_and_runs()
    _create_security_and_review_records()
    _create_evaluation_records()
    _create_projection_contract()
    _create_append_only_guards()
    _enforce_least_privilege()


def _extend_review_tasks() -> None:
    op.add_column(
        "review_task",
        sa.Column(
            "task_type",
            sa.String(30),
            nullable=False,
            server_default="CONTENT_REVIEW",
        ),
    )
    op.create_check_constraint(
        "ck_review_task_type",
        "review_task",
        "task_type IN ('CONTENT_REVIEW','SECURITY_REVIEW','CORRECTION_REVIEW','WITHDRAWAL_REVIEW')",
    )
    op.drop_constraint("uq_review_item_version", "review_task", type_="unique")
    op.create_index(
        "uq_review_content_item_version",
        "review_task",
        ["item_id", "document_version_id"],
        unique=True,
        postgresql_where=sa.text("task_type = 'CONTENT_REVIEW'"),
    )


def _create_ai_registry_and_runs() -> None:
    op.create_table(
        "ai_prompt_version",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("step", sa.String(20), nullable=False),
        sa.Column("version", sa.String(80), nullable=False),
        sa.Column("system_prompt", sa.Text(), nullable=False),
        sa.Column("task_prompt", sa.Text(), nullable=False),
        sa.Column("prompt_sha256", sa.String(64), nullable=False),
        sa.Column("created_by", _uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("step", "version", name="uq_ai_prompt_step_version"),
        sa.CheckConstraint(
            "step IN ('CLASSIFY','EXTRACT','SUMMARIZE','VERIFY')", name="ck_ai_prompt_step"
        ),
        sa.CheckConstraint("prompt_sha256 ~ '^[a-f0-9]{64}$'", name="ck_ai_prompt_hash"),
    )
    op.create_table(
        "ai_schema_version",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("step", sa.String(20), nullable=False),
        sa.Column("version", sa.String(80), nullable=False),
        sa.Column("schema_document", postgresql.JSONB(), nullable=False),
        sa.Column("schema_sha256", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("step", "version", name="uq_ai_schema_step_version"),
        sa.CheckConstraint(
            "step IN ('CLASSIFY','EXTRACT','SUMMARIZE','VERIFY')", name="ck_ai_schema_step"
        ),
        sa.CheckConstraint("schema_sha256 ~ '^[a-f0-9]{64}$'", name="ck_ai_schema_hash"),
    )
    op.create_table(
        "ai_model_profile",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("version", sa.String(80), nullable=False, unique=True),
        sa.Column("provider", sa.String(80), nullable=False),
        sa.Column("model", sa.String(200), nullable=False),
        sa.Column("parameters", postgresql.JSONB(), nullable=False),
        sa.Column("pricing_version", sa.String(80), nullable=False),
        sa.Column("input_price_microusd_per_million", sa.BigInteger(), nullable=False),
        sa.Column("output_price_microusd_per_million", sa.BigInteger(), nullable=False),
        sa.Column("data_classifications", postgresql.ARRAY(sa.String(40)), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("input_price_microusd_per_million >= 0", name="ck_ai_model_input_price"),
        sa.CheckConstraint(
            "output_price_microusd_per_million >= 0", name="ck_ai_model_output_price"
        ),
    )
    op.create_table(
        "ai_pipeline_run",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column(
            "document_version_id",
            _uuid(),
            sa.ForeignKey("document_version.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("mode", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("input_sha256", sa.String(64), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("failure_code", sa.String(80)),
        sa.CheckConstraint("mode IN ('LIVE','REPLAY','SHADOW')", name="ck_ai_pipeline_mode"),
        sa.CheckConstraint(
            "status IN ('QUEUED','RUNNING','SUCCEEDED','FAILED','DEGRADED')",
            name="ck_ai_pipeline_status",
        ),
        sa.CheckConstraint("input_sha256 ~ '^[a-f0-9]{64}$'", name="ck_ai_pipeline_input_hash"),
    )
    op.create_table(
        "ai_step_run",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column(
            "pipeline_run_id",
            _uuid(),
            sa.ForeignKey("ai_pipeline_run.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("step", sa.String(20), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column(
            "prompt_version_id",
            _uuid(),
            sa.ForeignKey("ai_prompt_version.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "schema_version_id",
            _uuid(),
            sa.ForeignKey("ai_schema_version.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "model_profile_id",
            _uuid(),
            sa.ForeignKey("ai_model_profile.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("input_sha256", sa.String(64), nullable=False),
        sa.Column("raw_output", sa.Text()),
        sa.Column("validated_output", postgresql.JSONB()),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("output_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cost_microusd", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("latency_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("provider_request_id", sa.String(200)),
        sa.Column("error_code", sa.String(80)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("pipeline_run_id", "step", "attempt", name="uq_ai_step_attempt"),
        sa.CheckConstraint(
            "step IN ('CLASSIFY','EXTRACT','SUMMARIZE','VERIFY')", name="ck_ai_step_name"
        ),
        sa.CheckConstraint("attempt >= 1", name="ck_ai_step_attempt"),
        sa.CheckConstraint("status IN ('SUCCEEDED','REJECTED','FAILED')", name="ck_ai_step_status"),
        sa.CheckConstraint("input_sha256 ~ '^[a-f0-9]{64}$'", name="ck_ai_step_input_hash"),
        sa.CheckConstraint(
            "input_tokens >= 0 AND output_tokens >= 0 AND cost_microusd >= 0 AND latency_ms >= 0",
            name="ck_ai_step_metrics",
        ),
    )


def _create_security_and_review_records() -> None:
    op.create_table(
        "ai_security_scan",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column(
            "document_version_id",
            _uuid(),
            sa.ForeignKey("document_version.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("input_sha256", sa.String(64), nullable=False),
        sa.Column("scanner_version", sa.String(80), nullable=False),
        sa.Column("detected", sa.Boolean(), nullable=False),
        sa.Column("patterns", postgresql.ARRAY(sa.String(80)), nullable=False),
        sa.Column("risk_level", sa.String(10), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("risk_level IN ('R1','R4')", name="ck_ai_security_risk"),
        sa.CheckConstraint("input_sha256 ~ '^[a-f0-9]{64}$'", name="ck_ai_security_hash"),
    )
    op.create_table(
        "security_review_decision",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column(
            "security_scan_id",
            _uuid(),
            sa.ForeignKey("ai_security_scan.id", ondelete="RESTRICT"),
            nullable=False,
            unique=True,
        ),
        sa.Column("action", sa.String(20), nullable=False),
        sa.Column("reason", sa.String(1000), nullable=False),
        sa.Column("reviewed_by", _uuid(), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("action IN ('RESOLVE','REJECT')", name="ck_security_review_action"),
        sa.CheckConstraint("length(trim(reason)) > 0", name="ck_security_review_reason"),
    )
    op.create_table(
        "review_decision",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column(
            "review_task_id",
            _uuid(),
            sa.ForeignKey("review_task.id", ondelete="RESTRICT"),
            nullable=False,
            unique=True,
        ),
        sa.Column("action", sa.String(20), nullable=False),
        sa.Column("reason", sa.String(1000), nullable=False),
        sa.Column("submitted_by", _uuid(), nullable=False),
        sa.Column("decided_by", _uuid(), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "action IN ('APPROVE','REJECT','CORRECT','WITHDRAW')", name="ck_review_decision_action"
        ),
        sa.CheckConstraint("decided_by <> submitted_by", name="ck_review_decision_duties"),
        sa.CheckConstraint("length(trim(reason)) > 0", name="ck_review_decision_reason"),
    )


def _create_evaluation_records() -> None:
    op.create_table(
        "ai_replay_run",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column(
            "baseline_profile_id",
            _uuid(),
            sa.ForeignKey("ai_model_profile.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "candidate_profile_id",
            _uuid(),
            sa.ForeignKey("ai_model_profile.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("fixture_version", sa.String(80), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("status IN ('RUNNING','PASSED','FAILED')", name="ck_ai_replay_status"),
    )
    op.create_table(
        "ai_shadow_result",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column(
            "replay_run_id",
            _uuid(),
            sa.ForeignKey("ai_replay_run.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "document_version_id",
            _uuid(),
            sa.ForeignKey("document_version.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "baseline_step_run_id",
            _uuid(),
            sa.ForeignKey("ai_step_run.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "candidate_step_run_id",
            _uuid(),
            sa.ForeignKey("ai_step_run.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("diff", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "ai_quality_report",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column(
            "replay_run_id",
            _uuid(),
            sa.ForeignKey("ai_replay_run.id", ondelete="RESTRICT"),
            nullable=False,
            unique=True,
        ),
        sa.Column("schema_pass_rate_bps", sa.Integer(), nullable=False),
        sa.Column("evidence_support_rate_bps", sa.Integer(), nullable=False),
        sa.Column("unsupported_expansion_rate_bps", sa.Integer(), nullable=False),
        sa.Column("cost_microusd", sa.BigInteger(), nullable=False),
        sa.Column("p95_latency_ms", sa.Integer(), nullable=False),
        sa.Column("metrics", postgresql.JSONB(), nullable=False),
        sa.Column("passed", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("schema_pass_rate_bps BETWEEN 0 AND 10000", name="ck_ai_quality_schema"),
        sa.CheckConstraint(
            "evidence_support_rate_bps BETWEEN 0 AND 10000", name="ck_ai_quality_evidence"
        ),
        sa.CheckConstraint(
            "unsupported_expansion_rate_bps BETWEEN 0 AND 10000", name="ck_ai_quality_expansion"
        ),
        sa.CheckConstraint(
            "cost_microusd >= 0 AND p95_latency_ms >= 0", name="ck_ai_quality_cost_latency"
        ),
    )


def _create_projection_contract() -> None:
    op.create_table(
        "publication_projection_state",
        sa.Column(
            "publication_id",
            _uuid(),
            sa.ForeignKey("publication.id", ondelete="RESTRICT"),
            primary_key=True,
        ),
        sa.Column("projection", sa.String(20), primary_key=True),
        sa.Column(
            "revision_id",
            _uuid(),
            sa.ForeignKey("publication_revision.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("visible", sa.Boolean(), nullable=False),
        sa.Column("generation", sa.BigInteger(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "projection IN ('SEARCH','CACHE','DAILY_DIGEST')",
            name="ck_projection_state_type",
        ),
        sa.CheckConstraint("generation >= 1", name="ck_projection_state_generation"),
    )
    op.create_table(
        "publication_projection_invalidation",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column(
            "publication_id",
            _uuid(),
            sa.ForeignKey("publication.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "revision_id",
            _uuid(),
            sa.ForeignKey("publication_revision.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("projection", sa.String(20), nullable=False),
        sa.Column("action", sa.String(20), nullable=False),
        sa.Column("generation", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="PENDING"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("applied_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("revision_id", "projection", name="uq_projection_revision"),
        sa.CheckConstraint(
            "projection IN ('SEARCH','CACHE','DAILY_DIGEST')", name="ck_projection_type"
        ),
        sa.CheckConstraint("action IN ('UPSERT','WITHDRAW')", name="ck_projection_action"),
        sa.CheckConstraint("generation >= 1", name="ck_projection_generation"),
        sa.CheckConstraint("status IN ('PENDING','APPLIED','FAILED')", name="ck_projection_status"),
    )
    op.create_index(
        "ix_projection_invalidation_queue",
        "publication_projection_invalidation",
        ["status", "created_at"],
    )


def _create_append_only_guards() -> None:
    op.execute(
        """
        CREATE FUNCTION prevent_round09_audit_mutation() RETURNS trigger AS $$
        BEGIN
          RAISE EXCEPTION 'Round09 model, review, and evaluation records are append-only';
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute("REVOKE ALL ON FUNCTION prevent_round09_audit_mutation() FROM PUBLIC")
    for table in (
        "ai_prompt_version",
        "ai_schema_version",
        "ai_model_profile",
        "ai_step_run",
        "ai_security_scan",
        "security_review_decision",
        "review_decision",
        "ai_shadow_result",
        "ai_quality_report",
    ):
        op.execute(
            f"CREATE TRIGGER trg_{table}_round09_append_only BEFORE UPDATE OR DELETE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION prevent_round09_audit_mutation()"
        )


def _enforce_least_privilege() -> None:
    tables = ", ".join(ROUND09_TABLES)
    op.execute("REVOKE srbg_runtime FROM srbg_model_role")
    op.execute("REVOKE ALL ON SCHEMA public FROM srbg_model_role")
    op.execute(f"REVOKE ALL ON {tables} FROM PUBLIC, srbg_model_role")
    op.execute(f"GRANT SELECT ON {tables} TO srbg_runtime, srbg_publication_writer")
    op.execute(
        "GRANT INSERT, UPDATE ON ai_pipeline_run "
        "TO srbg_runtime"
    )
    op.execute(
        "GRANT INSERT ON ai_prompt_version, ai_schema_version, ai_model_profile, ai_step_run, "
        "ai_security_scan, ai_replay_run, ai_shadow_result, ai_quality_report TO srbg_runtime"
    )
    op.execute(
        "REVOKE INSERT, UPDATE, DELETE ON review_decision, security_review_decision, "
        "publication_projection_state, publication_projection_invalidation FROM srbg_runtime"
    )
    op.execute("GRANT INSERT ON review_decision TO srbg_publication_writer")
    op.execute("GRANT INSERT ON security_review_decision TO srbg_publication_writer")
    op.execute(
        "GRANT INSERT, UPDATE ON publication_projection_state, "
        "publication_projection_invalidation TO srbg_publication_writer"
    )
    op.execute(
        "REVOKE INSERT, UPDATE, DELETE ON publication, publication_revision FROM "
        "srbg_api_role, srbg_worker_role, srbg_admin_role, srbg_model_role"
    )


def downgrade() -> None:
    connection = op.get_bind()
    governed_count = int(
        connection.scalar(
            sa.text(
                "SELECT (SELECT count(*) FROM ai_prompt_version) + "
                "(SELECT count(*) FROM ai_schema_version) + "
                "(SELECT count(*) FROM ai_model_profile) + "
                "(SELECT count(*) FROM ai_pipeline_run) + "
                "(SELECT count(*) FROM ai_step_run) + "
                "(SELECT count(*) FROM ai_security_scan) + "
                "(SELECT count(*) FROM security_review_decision) + "
                "(SELECT count(*) FROM review_decision) + "
                "(SELECT count(*) FROM ai_replay_run) + "
                "(SELECT count(*) FROM ai_shadow_result) + "
                "(SELECT count(*) FROM ai_quality_report) + "
                "(SELECT count(*) FROM publication_projection_state) + "
                "(SELECT count(*) FROM publication_projection_invalidation)"
            )
        )
        or 0
    )
    r4_count = int(
        connection.scalar(
            sa.text(
                "SELECT count(*) FROM review_task WHERE risk_level = 'R4' "
                "OR task_type <> 'CONTENT_REVIEW'"
            )
        )
        or 0
    )
    if governed_count or r4_count:
        raise RuntimeError("refusing Round09 downgrade while governed AI or review records exist")
    for table in (
        "ai_prompt_version",
        "ai_schema_version",
        "ai_model_profile",
        "ai_step_run",
        "ai_security_scan",
        "security_review_decision",
        "review_decision",
        "ai_replay_run",
        "ai_shadow_result",
        "ai_quality_report",
    ):
        op.execute(f"DROP TRIGGER IF EXISTS trg_{table}_round09_append_only ON {table}")
    op.execute("DROP FUNCTION IF EXISTS prevent_round09_audit_mutation()")
    for table in reversed(ROUND09_TABLES):
        op.drop_table(table)
    op.drop_index("uq_review_content_item_version", table_name="review_task")
    op.drop_constraint("ck_review_task_type", "review_task", type_="check")
    op.drop_column("review_task", "task_type")
    op.create_unique_constraint(
        "uq_review_item_version",
        "review_task",
        ["item_id", "document_version_id"],
    )
    op.execute("GRANT srbg_runtime TO srbg_model_role")
