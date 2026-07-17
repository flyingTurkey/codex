# ruff: noqa: E501 -- migration SQL and constraint declarations remain auditable inline.
"""PERS-04 evidence-backed automatic source profiles.

Revision ID: 0024_automatic_source_profiles
Revises: 0023_personal_source_runtime
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql
from srbg_api.identifiers import uuid7

revision = "0024_automatic_source_profiles"
down_revision = "0023_personal_source_runtime"
branch_labels = None
depends_on = None


def _uuid() -> postgresql.UUID:
    return postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.create_table(
        "source_profile_run",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column(
            "source_id", _uuid(), sa.ForeignKey("source.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column("input_sha256", sa.String(64)),
        sa.Column("status", sa.String(20), nullable=False, server_default="QUEUED"),
        sa.Column("attempt_count", sa.SmallInteger(), nullable=False, server_default="0"),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lease_token", _uuid()),
        sa.Column("leased_until", sa.DateTime(timezone=True)),
        sa.Column("failure_code", sa.String(80)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('QUEUED','RUNNING','COMPLETE','PARTIAL')",
            name="ck_source_profile_run_status",
        ),
        sa.CheckConstraint("attempt_count BETWEEN 0 AND 3", name="ck_source_profile_run_attempts"),
        sa.CheckConstraint(
            "input_sha256 IS NULL OR input_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_source_profile_run_hash",
        ),
    )
    op.create_index(
        "ix_source_profile_run_pending", "source_profile_run", ["status", "next_attempt_at", "id"]
    )
    op.create_index(
        "uq_source_profile_active",
        "source_profile_run",
        ["source_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('QUEUED','RUNNING')"),
    )

    op.create_table(
        "source_profile_snapshot",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column(
            "source_id", _uuid(), sa.ForeignKey("source.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("input_sha256", sa.String(64), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("industries", postgresql.ARRAY(sa.String(50)), nullable=False),
        sa.Column("content_domains", postgresql.ARRAY(sa.String(60)), nullable=False),
        sa.Column("language_tags", postgresql.ARRAY(sa.String(35)), nullable=False),
        sa.Column("country_codes", postgresql.ARRAY(sa.String(2)), nullable=False),
        sa.Column("region_codes", postgresql.ARRAY(sa.String(16)), nullable=False),
        sa.Column("declared_roles", postgresql.ARRAY(sa.String(40)), nullable=False),
        sa.Column("authority_level", sa.String(10), nullable=False),
        sa.Column("independence_level", sa.String(40), nullable=False),
        sa.Column("authority_basis", sa.String(30), nullable=False, server_default="AUTO_INFERRED"),
        sa.Column(
            "independence_basis", sa.String(30), nullable=False, server_default="AUTO_INFERRED"
        ),
        sa.Column("field_explanations", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("overall_confidence", sa.SmallInteger(), nullable=False),
        sa.Column("reason_codes", postgresql.ARRAY(sa.String(100)), nullable=False),
        sa.Column("evidence", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("technical_facts", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("rule_version", sa.String(50), nullable=False),
        sa.Column("prompt_version", sa.String(50), nullable=False),
        sa.Column("schema_version", sa.String(50), nullable=False),
        sa.Column("model_version", sa.String(100), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("source_id", "version", name="uq_source_profile_version"),
        sa.CheckConstraint("version >= 1", name="ck_source_profile_version"),
        sa.CheckConstraint("input_sha256 ~ '^[0-9a-f]{64}$'", name="ck_source_profile_input_hash"),
        sa.CheckConstraint("status IN ('COMPLETE','PARTIAL')", name="ck_source_profile_status"),
        sa.CheckConstraint(
            "authority_basis='AUTO_INFERRED' AND independence_basis='AUTO_INFERRED'",
            name="ck_source_profile_auto_basis",
        ),
        sa.CheckConstraint(
            "overall_confidence BETWEEN 0 AND 100", name="ck_source_profile_confidence"
        ),
    )
    op.create_index("ix_source_profile_latest", "source_profile_snapshot", ["source_id", "version"])
    op.execute(
        "CREATE TRIGGER trg_source_profile_snapshot_append_only BEFORE UPDATE OR DELETE "
        "ON source_profile_snapshot FOR EACH ROW EXECUTE FUNCTION prevent_round09_audit_mutation()"
    )

    op.create_table(
        "source_profile_override",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column(
            "source_id", _uuid(), sa.ForeignKey("source.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column("action", sa.String(10), nullable=False),
        sa.Column("values", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "supersedes_id",
            _uuid(),
            sa.ForeignKey("source_profile_override.id", ondelete="RESTRICT"),
        ),
        sa.Column("actor_id", _uuid(), nullable=False),
        sa.Column("request_id", sa.String(100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "action IN ('APPLY','REVOKE')", name="ck_source_profile_override_action"
        ),
        sa.CheckConstraint(
            "jsonb_typeof(values)='object' AND NOT (values ?| ARRAY['technical_facts','desired_enabled','publication_status','review_status','network_target','security_resolved'])",
            name="ck_source_profile_override_fields",
        ),
        sa.CheckConstraint(
            "(action='APPLY') OR (action='REVOKE' AND values='{}'::jsonb)",
            name="ck_source_profile_override_revoke",
        ),
    )
    op.create_index(
        "ix_source_profile_override_latest",
        "source_profile_override",
        ["source_id", "created_at", "id"],
    )
    op.execute(
        "CREATE TRIGGER trg_source_profile_override_append_only BEFORE UPDATE OR DELETE "
        "ON source_profile_override FOR EACH ROW EXECUTE FUNCTION prevent_round09_audit_mutation()"
    )

    op.create_table(
        "source_profile_model_attempt",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column(
            "run_id",
            _uuid(),
            sa.ForeignKey("source_profile_run.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("attempt", sa.SmallInteger(), nullable=False),
        sa.Column("attempt_kind", sa.String(20), nullable=False),
        sa.Column("input_sha256", sa.String(64), nullable=False),
        sa.Column("prompt_version", sa.String(50), nullable=False),
        sa.Column("schema_version", sa.String(50), nullable=False),
        sa.Column("model_version", sa.String(100), nullable=False),
        sa.Column("raw_output", sa.Text()),
        sa.Column("validated_output", postgresql.JSONB(astext_type=sa.Text())),
        sa.Column("input_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("output_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cost_microusd", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("latency_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("outcome", sa.String(20), nullable=False),
        sa.Column("error_code", sa.String(80)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("run_id", "attempt", name="uq_source_profile_model_attempt"),
        sa.CheckConstraint(
            "attempt BETWEEN 1 AND 4", name="ck_source_profile_model_attempt_number"
        ),
        sa.CheckConstraint(
            "attempt_kind IN ('PRIMARY','NETWORK_RETRY','REPAIR')",
            name="ck_source_profile_model_attempt_kind",
        ),
        sa.CheckConstraint(
            "outcome IN ('SUCCEEDED','FAILED')", name="ck_source_profile_model_outcome"
        ),
        sa.CheckConstraint("input_sha256 ~ '^[0-9a-f]{64}$'", name="ck_source_profile_model_hash"),
        sa.CheckConstraint(
            "input_tokens>=0 AND output_tokens>=0 AND cost_microusd>=0 AND latency_ms>=0",
            name="ck_source_profile_model_usage",
        ),
    )
    op.execute(
        "CREATE TRIGGER trg_source_profile_model_attempt_append_only BEFORE UPDATE OR DELETE "
        "ON source_profile_model_attempt FOR EACH ROW EXECUTE FUNCTION prevent_round09_audit_mutation()"
    )

    op.create_table(
        "source_profile_budget_reservation",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column(
            "run_id",
            _uuid(),
            sa.ForeignKey("source_profile_run.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "policy_id",
            _uuid(),
            sa.ForeignKey("ai_budget_policy.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("attempt", sa.SmallInteger(), nullable=False),
        sa.Column("month_start", sa.Date(), nullable=False),
        sa.Column("reserved_points", sa.Integer(), nullable=False),
        sa.Column("settled_points", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cost_microusd", sa.BigInteger()),
        sa.Column("billing_status", sa.String(20), nullable=False, server_default="RESERVED"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("settled_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("run_id", "attempt", name="uq_source_profile_budget_attempt"),
        sa.CheckConstraint(
            "attempt BETWEEN 1 AND 4 AND reserved_points BETWEEN 1 AND 100",
            name="ck_source_profile_budget_bounds",
        ),
        sa.CheckConstraint(
            "billing_status IN ('RESERVED','SETTLED','RELEASED')",
            name="ck_source_profile_budget_status",
        ),
    )

    bind = op.get_bind()
    for source_id in bind.execute(sa.text("SELECT id FROM source ORDER BY id")).scalars():
        bind.execute(
            sa.text(
                "INSERT INTO source_profile_run(id,source_id,status,next_attempt_at,"
                "created_at,updated_at) VALUES(CAST(:id AS uuid),:source_id,'QUEUED',"
                "now(),now(),now())"
            ),
            {"id": str(uuid7()), "source_id": source_id},
        )
    op.execute("GRANT SELECT,INSERT,UPDATE ON source_profile_run TO srbg_worker_role")
    op.execute(
        "GRANT SELECT,INSERT ON source_profile_snapshot,source_profile_model_attempt,"
        "source_profile_budget_reservation TO srbg_worker_role"
    )
    op.execute(
        "GRANT SELECT ON source_profile_snapshot,source_profile_override TO srbg_api_role"
    )
    op.execute("GRANT INSERT ON source_profile_override TO srbg_api_role")


def downgrade() -> None:
    bind = op.get_bind()
    materialized = bind.execute(
        sa.text(
            "SELECT EXISTS(SELECT 1 FROM source_profile_snapshot) OR "
            "EXISTS(SELECT 1 FROM source_profile_override) OR "
            "EXISTS(SELECT 1 FROM source_profile_model_attempt)"
        )
    ).scalar_one()
    if materialized:
        raise RuntimeError("0024_DOWNGRADE_BLOCKED: source profile facts exist")
    for table in (
        "source_profile_budget_reservation",
        "source_profile_model_attempt",
        "source_profile_override",
        "source_profile_snapshot",
        "source_profile_run",
    ):
        op.drop_table(table)
