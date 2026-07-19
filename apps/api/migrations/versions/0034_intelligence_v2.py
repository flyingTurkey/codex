# ruff: noqa: E501
"""Create the empty civil-engineering intelligence v2 projection generation.

Revision ID: 0034_intelligence_v2
Revises: 0033_controlled_ai_budget_bridge
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0034_intelligence_v2"
down_revision = "0033_controlled_ai_budget_bridge"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _uuid() -> postgresql.UUID:
    return postgresql.UUID(as_uuid=True)


def _json() -> postgresql.JSONB:
    return postgresql.JSONB(astext_type=sa.Text())


def upgrade() -> None:
    op.create_table(
        "projection_generation",
        sa.Column("name", sa.String(20), primary_key=True),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_generation", sa.String(20)),
        sa.CheckConstraint("name IN ('v1','v2')", name="ck_projection_generation_name"),
    )
    op.execute("INSERT INTO projection_generation(name,active,activated_at) VALUES ('v2',true,now())")
    op.create_table(
        "projection_archive_manifest",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("generation", sa.String(20), nullable=False),
        sa.Column("object_key", sa.String(1000), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("row_count", sa.BigInteger(), nullable=False),
        sa.Column("audit_tail_anchor", sa.String(200), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("sha256 ~ '^[0-9a-f]{64}$'", name="ck_projection_archive_sha256"),
        sa.UniqueConstraint("generation", "object_key", name="uq_projection_archive_object"),
    )
    op.create_table(
        "owner_review_case_v2",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("event_id", _uuid(), sa.ForeignKey("event.id", ondelete="RESTRICT")),
        sa.Column("document_version_id", _uuid(), sa.ForeignKey("document_version.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("reason", sa.String(80), nullable=False),
        sa.Column("risk_tier", sa.String(2), nullable=False),
        sa.Column("safe_metadata", _json(), nullable=False),
        sa.Column("state", sa.String(20), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("risk_tier IN ('R1','R2','R3','R4')", name="ck_owner_review_v2_risk"),
        sa.CheckConstraint("state IN ('OPEN','RESOLVED','QUARANTINED')", name="ck_owner_review_v2_state"),
        sa.UniqueConstraint("document_version_id", name="uq_owner_review_v2_document"),
    )
    op.create_table(
        "ai_runtime_health_v2",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("provider", sa.String(30), nullable=False),
        sa.Column("model", sa.String(100), nullable=False),
        sa.Column("environment", sa.String(30), nullable=False),
        sa.Column("worker_heartbeat_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("queue_healthy", sa.Boolean(), nullable=False),
        sa.Column("budget_healthy", sa.Boolean(), nullable=False),
        sa.Column("last_real_schema_success_at", sa.DateTime(timezone=True)),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("provider", "environment", name="uq_ai_runtime_health_v2_provider_env"),
    )
    op.create_table(
        "owner_review_decision_v2",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("case_id", _uuid(), sa.ForeignKey("owner_review_case_v2.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("owner_id", _uuid(), nullable=False),
        sa.Column("command", sa.String(40), nullable=False),
        sa.Column("reason", sa.String(1000), nullable=False),
        sa.Column("payload", _json(), nullable=False),
        sa.Column("case_version", sa.Integer(), nullable=False),
        sa.Column("idempotency_key", _uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("idempotency_key", name="uq_owner_review_v2_idempotency"),
        sa.UniqueConstraint("case_id", "case_version", name="uq_owner_review_v2_version"),
    )
    op.create_table(
        "ai_summary_version_v2",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("event_id", _uuid(), sa.ForeignKey("event.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("document_version_id", _uuid(), sa.ForeignKey("document_version.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("body", sa.String(500)),
        sa.Column("claim_ids", postgresql.ARRAY(_uuid()), nullable=False),
        sa.Column("judgment_paragraphs", postgresql.ARRAY(sa.Integer()), nullable=False),
        sa.Column("model", sa.String(100)),
        sa.Column("prompt_version", sa.String(100)),
        sa.Column("schema_version", sa.String(100)),
        sa.Column("input_sha256", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("status IN ('NOT_GENERATED','PROCESSING','TEMPORARILY_UNAVAILABLE','SCHEMA_REJECTED','INSUFFICIENT_EVIDENCE','SUCCEEDED','STALE')", name="ck_ai_summary_v2_status"),
        sa.CheckConstraint("status <> 'SUCCEEDED' OR (body IS NOT NULL AND cardinality(claim_ids)>0 AND model IS NOT NULL)", name="ck_ai_summary_v2_success"),
    )
    op.create_table(
        "hotspot_award_v2",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("event_id", _uuid(), sa.ForeignKey("event.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("trigger_path", sa.String(30), nullable=False),
        sa.Column("independent_source_count", sa.Integer(), nullable=False),
        sa.Column("components", _json(), nullable=False),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("reasons", postgresql.ARRAY(sa.String(300)), nullable=False),
        sa.Column("rule_version", sa.String(100), nullable=False),
        sa.Column("awarded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("revocation_reason", sa.String(500)),
        sa.UniqueConstraint("event_id", "rule_version", name="uq_hotspot_v2_event_rule"),
        sa.CheckConstraint("score BETWEEN 0 AND 100", name="ck_hotspot_v2_score"),
    )
    op.create_table(
        "media_rights_v2",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("document_version_id", _uuid(), sa.ForeignKey("document_version.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("name", sa.String(300), nullable=False),
        sa.Column("object_key", sa.String(1000)),
        sa.Column("source_url", sa.String(2048), nullable=False),
        sa.Column("mime_type", sa.String(100), nullable=False),
        sa.Column("rights_basis", sa.String(30)),
        sa.Column("redistribution_allowed", sa.Boolean(), nullable=False),
        sa.Column("scan_status", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("rights_basis IS NULL OR rights_basis IN ('PUBLIC_DOMAIN','EXPLICIT_LICENSE','SOURCE_AUTHORIZED','OWNER_OWNED')", name="ck_media_v2_rights"),
        sa.CheckConstraint("scan_status IN ('PENDING','CLEAN','REJECTED')", name="ck_media_v2_scan"),
    )
    op.create_table(
        "intelligence_projection_v2",
        sa.Column("event_id", _uuid(), sa.ForeignKey("event.id", ondelete="RESTRICT"), primary_key=True),
        sa.Column("document_version_id", _uuid(), sa.ForeignKey("document_version.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("projection_kind", sa.String(20), nullable=False),
        sa.Column("primary_type", sa.String(30), nullable=False),
        sa.Column("risk_tier", sa.String(2), nullable=False),
        sa.Column("payload", _json(), nullable=False),
        sa.Column("appendix_payload", _json(), nullable=False),
        sa.Column("generation", sa.Integer(), nullable=False),
        sa.Column("projected_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("projection_kind IN ('FULL','R3_METADATA')", name="ck_projection_v2_kind"),
        sa.CheckConstraint("primary_type IN ('DIGITAL_TRANSFORMATION','SAFETY_INTELLIGENCE','INDUSTRY_UPDATE')", name="ck_projection_v2_primary_type"),
        sa.CheckConstraint("risk_tier <> 'R4'", name="ck_projection_v2_no_r4"),
    )
    op.create_table(
        "search_projection_v2",
        sa.Column("event_id", _uuid(), sa.ForeignKey("intelligence_projection_v2.event_id", ondelete="CASCADE"), primary_key=True),
        sa.Column("title_source_claims_excerpt", sa.Text(), nullable=False),
        sa.Column("ai_summary_low_weight", sa.Text()),
        sa.Column("search_vector", postgresql.TSVECTOR()),
        sa.Column("generation", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_search_projection_v2_vector", "search_projection_v2", ["search_vector"], postgresql_using="gin")
    op.execute("""
      CREATE FUNCTION prevent_v2_append_only_mutation() RETURNS trigger
      LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'V2_APPEND_ONLY_FACT'; END $$
    """)
    for table in ("owner_review_decision_v2", "ai_summary_version_v2"):
        op.execute(f"CREATE TRIGGER trg_{table}_append_only BEFORE UPDATE OR DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION prevent_v2_append_only_mutation()")
    for table in ("projection_archive_manifest", "owner_review_case_v2", "owner_review_decision_v2", "ai_runtime_health_v2", "ai_summary_version_v2", "hotspot_award_v2", "media_rights_v2", "intelligence_projection_v2", "search_projection_v2"):
        op.execute(f"REVOKE ALL ON TABLE {table} FROM PUBLIC")
    op.execute("GRANT SELECT ON projection_generation,owner_review_case_v2,hotspot_award_v2,media_rights_v2,intelligence_projection_v2,search_projection_v2 TO srbg_projection_reader")
    op.execute("GRANT SELECT,INSERT,UPDATE ON owner_review_case_v2 TO srbg_publication_writer")
    op.execute("GRANT SELECT ON ai_runtime_health_v2 TO srbg_api_role")
    op.execute("GRANT SELECT,INSERT,UPDATE ON ai_runtime_health_v2 TO srbg_worker_role")
    op.execute("GRANT SELECT,INSERT ON owner_review_decision_v2,ai_summary_version_v2,projection_archive_manifest TO srbg_publication_writer")
    op.execute("GRANT SELECT,INSERT,UPDATE ON hotspot_award_v2,media_rights_v2,intelligence_projection_v2,search_projection_v2,projection_generation TO srbg_publication_writer")


def downgrade() -> None:
    bind = op.get_bind()
    durable = bind.execute(sa.text("SELECT EXISTS(SELECT 1 FROM owner_review_decision_v2 UNION ALL SELECT 1 FROM ai_summary_version_v2 UNION ALL SELECT 1 FROM intelligence_projection_v2)")).scalar_one()
    if durable:
        raise RuntimeError("INTELLIGENCE_V2_DOWNGRADE_BLOCKED: durable v2 facts exist")
    for table in ("ai_summary_version_v2", "owner_review_decision_v2"):
        op.execute(f"DROP TRIGGER trg_{table}_append_only ON {table}")
    op.execute("DROP FUNCTION prevent_v2_append_only_mutation()")
    op.drop_index("ix_search_projection_v2_vector", table_name="search_projection_v2")
    for table in ("search_projection_v2", "intelligence_projection_v2", "media_rights_v2", "hotspot_award_v2", "ai_summary_version_v2", "ai_runtime_health_v2", "owner_review_decision_v2", "owner_review_case_v2", "projection_archive_manifest", "projection_generation"):
        op.drop_table(table)
