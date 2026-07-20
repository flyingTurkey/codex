# ruff: noqa: E501
"""Add permanent, server-derived T09 hotspot awards.

Revision ID: 0043_t09_hotspot_awards
Revises: 0042_t07_controlled_stream
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0043_t09_hotspot_awards"
down_revision = "0042_t07_controlled_stream"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _uuid() -> postgresql.UUID:
    return postgresql.UUID(as_uuid=True)


def _json() -> postgresql.JSONB:
    return postgresql.JSONB(astext_type=sa.Text())


def upgrade() -> None:
    op.create_table(
        "hotspot_candidate_v2",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("event_id", _uuid(), sa.ForeignKey("event.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("document_version_id", _uuid(), sa.ForeignKey("document_version.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("claim_ids", postgresql.ARRAY(_uuid()), nullable=False),
        sa.Column("reasons", _json(), nullable=False),
        sa.Column("model", sa.String(100), nullable=False),
        sa.Column("prompt_version", sa.String(100), nullable=False),
        sa.Column("schema_version", sa.String(100), nullable=False),
        sa.Column("input_sha256", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("cardinality(claim_ids)>0", name="ck_t09_candidate_claims"),
        sa.CheckConstraint("jsonb_array_length(reasons)>0", name="ck_t09_candidate_reasons"),
        sa.CheckConstraint("input_sha256 ~ '^[a-f0-9]{64}$'", name="ck_t09_candidate_hash"),
    )
    op.create_table(
        "hotspot_evaluation_v2",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("candidate_id", _uuid(), sa.ForeignKey("hotspot_candidate_v2.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("event_id", _uuid(), sa.ForeignKey("event.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("document_version_id", _uuid(), sa.ForeignKey("document_version.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("primary_type", sa.String(30), nullable=False),
        sa.Column("outcome", sa.String(20), nullable=False),
        sa.Column("trigger_path", sa.String(30)),
        sa.Column("independent_source_count", sa.Integer(), nullable=False),
        sa.Column("components", _json(), nullable=False),
        sa.Column("evaluation_inputs", _json(), nullable=False),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("reasons", postgresql.ARRAY(sa.String(300)), nullable=False),
        sa.Column("reason_codes", postgresql.ARRAY(sa.String(80)), nullable=False),
        sa.Column("rule_version", sa.String(100), nullable=False),
        sa.Column("evidence_sha256", sa.String(64), nullable=False),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("primary_type IN ('DIGITAL_TRANSFORMATION','SAFETY_INTELLIGENCE','INDUSTRY_UPDATE')", name="ck_t09_evaluation_primary_type"),
        sa.CheckConstraint("outcome IN ('AWARDED','REJECTED')", name="ck_t09_evaluation_outcome"),
        sa.CheckConstraint("trigger_path IS NULL OR trigger_path IN ('MULTI_SOURCE_7D','AUTHORITY_SCORE')", name="ck_t09_evaluation_trigger"),
        sa.CheckConstraint("score BETWEEN 0 AND 100", name="ck_t09_evaluation_score"),
        sa.CheckConstraint("independent_source_count>=0", name="ck_t09_evaluation_source_count"),
        sa.CheckConstraint("evidence_sha256 ~ '^[a-f0-9]{64}$'", name="ck_t09_evaluation_hash"),
    )
    op.drop_constraint("uq_hotspot_v2_event_rule", "hotspot_award_v2", type_="unique")
    op.add_column("hotspot_award_v2", sa.Column("evaluation_id", _uuid()))
    op.add_column("hotspot_award_v2", sa.Column("document_version_id", _uuid()))
    op.add_column("hotspot_award_v2", sa.Column("evidence_sha256", sa.String(64)))
    op.create_foreign_key(
        "fk_t09_award_evaluation",
        "hotspot_award_v2",
        "hotspot_evaluation_v2",
        ["evaluation_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_t09_award_document_version",
        "hotspot_award_v2",
        "document_version",
        ["document_version_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_unique_constraint("uq_t09_award_evaluation", "hotspot_award_v2", ["evaluation_id"])
    op.create_check_constraint(
        "ck_t09_award_current_shape",
        "hotspot_award_v2",
        "evaluation_id IS NULL OR (revoked_at IS NULL AND revocation_reason IS NULL)",
    )
    op.create_check_constraint(
        "ck_t09_award_evidence_hash",
        "hotspot_award_v2",
        "evidence_sha256 IS NULL OR evidence_sha256 ~ '^[a-f0-9]{64}$'",
    )
    op.execute(
        "CREATE FUNCTION prevent_t09_append_only_mutation() RETURNS trigger "
        "LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'T09_APPEND_ONLY_FACT'; END $$"
    )
    for table in ("hotspot_candidate_v2", "hotspot_evaluation_v2", "hotspot_award_v2"):
        op.execute(
            f"CREATE TRIGGER trg_{table}_t09_append_only BEFORE UPDATE OR DELETE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION prevent_t09_append_only_mutation()"
        )
        op.execute(f"REVOKE ALL ON TABLE {table} FROM PUBLIC")
    op.execute("REVOKE UPDATE,DELETE ON hotspot_award_v2 FROM srbg_publication_writer")
    op.execute("GRANT SELECT,INSERT ON hotspot_candidate_v2 TO srbg_worker_role")
    op.execute("GRANT SELECT,INSERT ON hotspot_candidate_v2 TO srbg_publication_writer")
    op.execute("GRANT SELECT,INSERT ON hotspot_evaluation_v2 TO srbg_publication_writer")
    op.execute("GRANT SELECT,INSERT ON hotspot_award_v2 TO srbg_publication_writer")
    op.execute("GRANT SELECT ON source_admission_assessment_v2 TO srbg_publication_writer")
    op.execute("GRANT SELECT ON hotspot_award_v2 TO srbg_projection_reader")


def downgrade() -> None:
    bind = op.get_bind()
    durable = bind.execute(
        sa.text(
            "SELECT EXISTS(SELECT 1 FROM hotspot_candidate_v2) OR "
            "EXISTS(SELECT 1 FROM hotspot_evaluation_v2) OR "
            "EXISTS(SELECT 1 FROM hotspot_award_v2 WHERE evaluation_id IS NOT NULL)"
        )
    ).scalar_one()
    if durable:
        raise RuntimeError("T09_DOWNGRADE_BLOCKED: durable hotspot facts exist")
    op.execute("REVOKE SELECT ON source_admission_assessment_v2 FROM srbg_publication_writer")
    for table in ("hotspot_award_v2", "hotspot_evaluation_v2", "hotspot_candidate_v2"):
        op.execute(f"DROP TRIGGER trg_{table}_t09_append_only ON {table}")
    op.execute("DROP FUNCTION prevent_t09_append_only_mutation()")
    op.drop_constraint("ck_t09_award_evidence_hash", "hotspot_award_v2", type_="check")
    op.drop_constraint("ck_t09_award_current_shape", "hotspot_award_v2", type_="check")
    op.drop_constraint("uq_t09_award_evaluation", "hotspot_award_v2", type_="unique")
    op.drop_constraint("fk_t09_award_document_version", "hotspot_award_v2", type_="foreignkey")
    op.drop_constraint("fk_t09_award_evaluation", "hotspot_award_v2", type_="foreignkey")
    op.drop_column("hotspot_award_v2", "evidence_sha256")
    op.drop_column("hotspot_award_v2", "document_version_id")
    op.drop_column("hotspot_award_v2", "evaluation_id")
    op.create_unique_constraint(
        "uq_hotspot_v2_event_rule", "hotspot_award_v2", ["event_id", "rule_version"]
    )
    op.drop_table("hotspot_evaluation_v2")
    op.drop_table("hotspot_candidate_v2")
