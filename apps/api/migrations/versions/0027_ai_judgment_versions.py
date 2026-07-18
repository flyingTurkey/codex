# ruff: noqa: E501
"""PERS-07 versioned AI judgments and automatic signal projections.

Revision ID: 0027_ai_judgment_versions
Revises: 0026_automatic_evidence_facts
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0027_ai_judgment_versions"
down_revision = "0026_automatic_evidence_facts"
branch_labels = None
depends_on = None


def _uuid() -> postgresql.UUID:
    return postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.drop_constraint("ck_ai_pipeline_status", "ai_pipeline_run", type_="check")
    op.create_check_constraint(
        "ck_ai_pipeline_status",
        "ai_pipeline_run",
        "status IN ('QUEUED','PREPARING','CLASSIFYING','EXTRACTING','EVIDENCE_GATING','SUMMARIZING','VERIFYING','WAITING_CLAIM_REVIEW','RUNNING','SUCCEEDED','FAILED','DEGRADED')",
    )
    op.create_table(
        "ai_judgment_version",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("event_id", _uuid(), sa.ForeignKey("event.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("item_id", _uuid(), sa.ForeignKey("intelligence_item.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("document_version_id", _uuid(), sa.ForeignKey("document_version.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("pipeline_run_id", _uuid(), sa.ForeignKey("ai_pipeline_run.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("summarize_step_run_id", _uuid(), sa.ForeignKey("ai_step_run.id", ondelete="RESTRICT")),
        sa.Column("verify_step_run_id", _uuid(), sa.ForeignKey("ai_step_run.id", ondelete="RESTRICT")),
        sa.Column("evidence_fact_set_sha256", sa.String(64), nullable=False),
        sa.Column("summarize_prompt_version", sa.String(100), nullable=False),
        sa.Column("verify_prompt_version", sa.String(100), nullable=False),
        sa.Column("schema_version", sa.String(100), nullable=False),
        sa.Column("model_version", sa.String(100), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("judgment_payload", postgresql.JSONB(astext_type=sa.Text())),
        sa.Column("verification_result", postgresql.JSONB(astext_type=sa.Text())),
        sa.Column("input_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("output_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("latency_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cost_microusd", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("failure_reason_codes", postgresql.ARRAY(sa.String(100)), nullable=False, server_default="{}"),
        sa.Column("invalidation_reason", sa.String(100)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("invalidated_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("document_version_id", "evidence_fact_set_sha256", "summarize_prompt_version", "verify_prompt_version", "schema_version", "model_version", name="uq_ai_judgment_version_input"),
        sa.CheckConstraint("evidence_fact_set_sha256 ~ '^[0-9a-f]{64}$'", name="ck_ai_judgment_version_hash"),
        sa.CheckConstraint("status IN ('AI_JUDGMENT','UNVERIFIED_AI','AI_PROCESSING_FAILED','INVALIDATED')", name="ck_ai_judgment_version_status"),
        sa.CheckConstraint("input_tokens>=0 AND output_tokens>=0 AND latency_ms>=0 AND cost_microusd>=0", name="ck_ai_judgment_version_usage"),
    )
    op.create_table(
        "personal_signal_projection",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("event_id", _uuid(), sa.ForeignKey("event.id", ondelete="CASCADE"), nullable=False),
        sa.Column("item_id", _uuid(), sa.ForeignKey("intelligence_item.id", ondelete="CASCADE"), nullable=False),
        sa.Column("document_version_id", _uuid(), sa.ForeignKey("document_version.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("judgment_version_id", _uuid(), sa.ForeignKey("ai_judgment_version.id", ondelete="RESTRICT")),
        sa.Column("result_type", sa.String(30), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("visible", sa.Boolean(), nullable=False),
        sa.Column("generation", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("document_version_id", "result_type", name="uq_personal_signal_version_type"),
        sa.CheckConstraint("result_type IN ('EVIDENCE_FACT','AI_JUDGMENT','UNVERIFIED_AI','AI_PROCESSING_FAILED')", name="ck_personal_signal_type"),
        sa.CheckConstraint("generation>=1", name="ck_personal_signal_generation"),
    )
    for table, allowed in (
        ("personal_primary_search_projection", "('EVIDENCE_FACT','AI_JUDGMENT')"),
        ("unverified_ai_search_projection", "('UNVERIFIED_AI')"),
    ):
        op.create_table(
            table,
            sa.Column("signal_id", _uuid(), sa.ForeignKey("personal_signal_projection.id", ondelete="CASCADE"), primary_key=True),
            sa.Column("event_id", _uuid(), nullable=False),
            sa.Column("result_type", sa.String(30), nullable=False),
            sa.Column("title", sa.String(500), nullable=False),
            sa.Column("search_text", sa.Text(), nullable=False),
            sa.Column("activity_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("visible", sa.Boolean(), nullable=False),
            sa.Column("generation", sa.BigInteger(), nullable=False),
            sa.CheckConstraint(f"result_type IN {allowed}", name=f"ck_{table}_type"),
        )
        op.execute(f"ALTER TABLE {table} ADD COLUMN search_vector tsvector GENERATED ALWAYS AS (to_tsvector('simple', search_text)) STORED")
        op.create_index(f"ix_{table}_vector", table, ["search_vector"], postgresql_using="gin")
    op.create_table(
        "personal_daily_report_projection",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("report_date", sa.Date(), nullable=False, unique=True),
        sa.Column("snapshot_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("visible", sa.Boolean(), nullable=False),
        sa.Column("generation", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "personal_daily_signal_projection",
        sa.Column("report_id", _uuid(), sa.ForeignKey("personal_daily_report_projection.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("signal_id", _uuid(), sa.ForeignKey("personal_signal_projection.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("section", sa.String(30), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.CheckConstraint("section IN ('EVIDENCE_FACTS','UNVERIFIED_AI')", name="ck_personal_daily_section"),
        sa.UniqueConstraint("report_id", "section", "position", name="uq_personal_daily_position"),
    )
    op.create_table(
        "ai_judgment_projection_reference",
        sa.Column("judgment_version_id", _uuid(), sa.ForeignKey("ai_judgment_version.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("signal_id", _uuid(), sa.ForeignKey("personal_signal_projection.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("surface", sa.String(20), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("surface IN ('FEED','SEARCH','DAILY','CACHE')", name="ck_ai_projection_surface"),
    )
    op.execute("REVOKE ALL ON ai_judgment_version,personal_signal_projection,personal_primary_search_projection,unverified_ai_search_projection,personal_daily_report_projection,personal_daily_signal_projection,ai_judgment_projection_reference FROM PUBLIC")
    op.execute("GRANT SELECT,INSERT,UPDATE ON ai_judgment_version TO srbg_worker_role")
    op.execute("GRANT SELECT ON ai_judgment_version TO srbg_runtime,srbg_publication_writer")
    op.execute("GRANT SELECT,INSERT,UPDATE,DELETE ON personal_signal_projection,personal_primary_search_projection,unverified_ai_search_projection,personal_daily_report_projection,personal_daily_signal_projection,ai_judgment_projection_reference TO srbg_publication_writer")
    op.execute("GRANT SELECT ON personal_signal_projection,personal_primary_search_projection,unverified_ai_search_projection,personal_daily_report_projection,personal_daily_signal_projection TO srbg_runtime,srbg_projection_reader")


def downgrade() -> None:
    bind = op.get_bind()
    if bind.execute(sa.text("SELECT EXISTS(SELECT 1 FROM ai_judgment_version) OR EXISTS(SELECT 1 FROM personal_signal_projection)")).scalar_one():
        raise RuntimeError("0027_DOWNGRADE_BLOCKED: AI judgment versions or projections exist")
    for table in (
        "ai_judgment_projection_reference",
        "personal_daily_signal_projection",
        "personal_daily_report_projection",
        "unverified_ai_search_projection",
        "personal_primary_search_projection",
        "personal_signal_projection",
        "ai_judgment_version",
    ):
        op.drop_table(table)
    op.drop_constraint("ck_ai_pipeline_status", "ai_pipeline_run", type_="check")
    op.create_check_constraint(
        "ck_ai_pipeline_status",
        "ai_pipeline_run",
        "status IN ('QUEUED','PREPARING','CLASSIFYING','EXTRACTING','EVIDENCE_GATING','WAITING_CLAIM_REVIEW','RUNNING','SUCCEEDED','FAILED','DEGRADED')",
    )
