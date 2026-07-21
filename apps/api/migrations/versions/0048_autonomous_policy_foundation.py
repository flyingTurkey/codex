"""Expand autonomous qualification policy and shared control facts.

Revision ID: 0048_autonomous_policy_foundation
Revises: 0047_owner_gold_override_go
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0048_autonomous_policy_foundation"
down_revision = "0047_owner_gold_override_go"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _uuid() -> postgresql.UUID:
    return postgresql.UUID(as_uuid=True)


def _json() -> postgresql.JSONB:
    return postgresql.JSONB(astext_type=sa.Text())


def upgrade() -> None:
    op.create_table(
        "qualification_policy_bundle_v2",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("policy_version", sa.String(120), nullable=False),
        sa.Column("global_rule_version", sa.String(120), nullable=False),
        sa.Column("source_stream_policy_version", sa.String(120), nullable=False),
        sa.Column("ai_provider", sa.String(80), nullable=False),
        sa.Column("ai_model", sa.String(160), nullable=False),
        sa.Column("prompt_version", sa.String(120), nullable=False),
        sa.Column("schema_version", sa.String(120), nullable=False),
        sa.Column("code_version", sa.String(120), nullable=False),
        sa.Column("authorization_basis", sa.String(40), nullable=False),
        sa.Column("policy_payload", _json(), nullable=False),
        sa.Column("bundle_sha256", sa.String(64), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "authorization_basis='AUTONOMOUS_POLICY_GATE'",
            name="ck_qualification_policy_authority_v2",
        ),
        sa.CheckConstraint(
            "bundle_sha256 ~ '^[a-f0-9]{64}$'",
            name="ck_qualification_policy_hash_v2",
        ),
        sa.UniqueConstraint(
            "policy_version",
            "global_rule_version",
            "source_stream_policy_version",
            "ai_provider",
            "ai_model",
            "prompt_version",
            "schema_version",
            "code_version",
            name="uq_qualification_policy_identity_v2",
        ),
    )
    op.create_table(
        "automated_qualification_decision_v2",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column(
            "policy_bundle_id",
            _uuid(),
            sa.ForeignKey("qualification_policy_bundle_v2.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "document_version_id",
            _uuid(),
            sa.ForeignKey("document_version.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "raw_object_id",
            _uuid(),
            sa.ForeignKey("raw_object.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("normalized_input_sha256", sa.String(64), nullable=False),
        sa.Column("disposition", sa.String(30), nullable=False),
        sa.Column("reason_codes", postgresql.ARRAY(sa.String(80)), nullable=False),
        sa.Column("rule_signals", _json(), nullable=False),
        sa.Column("model_candidate", _json()),
        sa.Column("evidence_locators", postgresql.ARRAY(sa.String(200)), nullable=False),
        sa.Column("semantic_recheck_count", sa.SmallInteger(), nullable=False),
        sa.Column("model_latency_ms", sa.Integer()),
        sa.Column("model_input_tokens", sa.Integer()),
        sa.Column("model_output_tokens", sa.Integer()),
        sa.Column("model_cost_microusd", sa.BigInteger()),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "normalized_input_sha256 ~ '^[a-f0-9]{64}$'",
            name="ck_automated_decision_input_hash_v2",
        ),
        sa.CheckConstraint(
            "disposition IN ('AUTO_ACCEPTED','AUTO_FILTERED','TECHNICAL_RETRY',"
            "'TECHNICAL_FAILED','SAFETY_HOLD','OWNER_SUPPRESSED')",
            name="ck_automated_decision_disposition_v2",
        ),
        sa.CheckConstraint(
            "semantic_recheck_count BETWEEN 0 AND 1",
            name="ck_automated_decision_recheck_v2",
        ),
        sa.CheckConstraint(
            "cardinality(reason_codes) BETWEEN 1 AND 20",
            name="ck_automated_decision_reasons_v2",
        ),
        sa.UniqueConstraint(
            "document_version_id",
            "policy_bundle_id",
            name="uq_automated_decision_document_policy_v2",
        ),
    )
    op.create_table(
        "owner_exception_v2",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("overrideability", sa.String(30)),
        sa.Column("source_id", _uuid(), sa.ForeignKey("source.id", ondelete="RESTRICT")),
        sa.Column(
            "source_stream_id",
            _uuid(),
            sa.ForeignKey("source_stream.id", ondelete="RESTRICT"),
        ),
        sa.Column(
            "document_version_id",
            _uuid(),
            sa.ForeignKey("document_version.id", ondelete="RESTRICT"),
        ),
        sa.Column(
            "decision_id",
            _uuid(),
            sa.ForeignKey("automated_qualification_decision_v2.id", ondelete="RESTRICT"),
        ),
        sa.Column("reason_codes", postgresql.ARRAY(sa.String(80)), nullable=False),
        sa.Column("safe_metadata", _json(), nullable=False),
        sa.Column("attempt_count", sa.SmallInteger(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("kind IN ('TECHNICAL','SAFETY')", name="ck_owner_exception_kind_v2"),
        sa.CheckConstraint("status IN ('OPEN','RESOLVED')", name="ck_owner_exception_status_v2"),
        sa.CheckConstraint(
            "overrideability IS NULL OR overrideability IN ('OWNER_DECIDABLE','HARD_BLOCK')",
            name="ck_owner_exception_overrideability_v2",
        ),
        sa.CheckConstraint(
            "(kind='TECHNICAL' AND overrideability IS NULL) OR "
            "(kind='SAFETY' AND overrideability IS NOT NULL)",
            name="ck_owner_exception_kind_override_v2",
        ),
        sa.CheckConstraint(
            "attempt_count BETWEEN 0 AND 32767",
            name="ck_owner_exception_attempt_v2",
        ),
        sa.CheckConstraint("version > 0", name="ck_owner_exception_version_v2"),
    )
    op.create_index(
        "ix_owner_exception_current_v2",
        "owner_exception_v2",
        ["kind", "status", "updated_at"],
    )
    op.create_table(
        "owner_exception_event_v2",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column(
            "exception_id",
            _uuid(),
            sa.ForeignKey("owner_exception_v2.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("event_type", sa.String(30), nullable=False),
        sa.Column("expected_version", sa.Integer(), nullable=False),
        sa.Column("idempotency_key", _uuid(), nullable=False, unique=True),
        sa.Column("safe_metadata", _json(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "event_type IN ('CREATED','RETRY_REQUESTED','OWNER_ALLOWED','OWNER_DENIED',"
            "'AUTO_RESOLVED','SOURCE_DISABLED')",
            name="ck_owner_exception_event_type_v2",
        ),
        sa.CheckConstraint("expected_version > 0", name="ck_owner_exception_event_version_v2"),
    )
    op.create_table(
        "feed_suppression_rule_v2",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("scope", sa.String(30), nullable=False),
        sa.Column("target_key", sa.String(300), nullable=False),
        sa.Column("action", sa.String(20), nullable=False),
        sa.Column(
            "supersedes_rule_id",
            _uuid(),
            sa.ForeignKey("feed_suppression_rule_v2.id", ondelete="RESTRICT"),
        ),
        sa.Column("feedback_reason", sa.String(40), nullable=False),
        sa.Column("owner_id", _uuid(), nullable=False),
        sa.Column("idempotency_key", _uuid(), nullable=False, unique=True),
        sa.Column("effective_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "scope IN ('EVENT','PRIMARY_TYPE','ENGINEERING_OBJECT','SPECIALTY_FACET',"
            "'EQUIPMENT_DOMAIN','SOURCE','CUSTOM_TOPIC')",
            name="ck_feed_suppression_scope_v2",
        ),
        sa.CheckConstraint("action IN ('ACTIVATE','REVOKE')", name="ck_feed_suppression_action_v2"),
        sa.CheckConstraint(
            "feedback_reason IN ('OWNER_PREFERENCE','CLASSIFICATION_ERROR','SAFETY_DENIAL')",
            name="ck_feed_suppression_feedback_v2",
        ),
        sa.CheckConstraint(
            "(action='ACTIVATE' AND supersedes_rule_id IS NULL) OR "
            "(action='REVOKE' AND supersedes_rule_id IS NOT NULL)",
            name="ck_feed_suppression_supersedes_v2",
        ),
    )
    op.create_index(
        "ix_feed_suppression_target_v2",
        "feed_suppression_rule_v2",
        ["scope", "target_key", "effective_at"],
    )
    op.create_table(
        "qualification_policy_evaluation_v2",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column(
            "policy_bundle_id",
            _uuid(),
            sa.ForeignKey("qualification_policy_bundle_v2.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("mode", sa.String(20), nullable=False),
        sa.Column("benchmark_version", sa.String(120), nullable=False),
        sa.Column("corpus_manifest_sha256", sa.String(64), nullable=False),
        sa.Column("total_cases", sa.Integer(), nullable=False),
        sa.Column("auto_accepted_count", sa.Integer(), nullable=False),
        sa.Column("auto_filtered_count", sa.Integer(), nullable=False),
        sa.Column("technical_retry_count", sa.Integer(), nullable=False),
        sa.Column("technical_failed_count", sa.Integer(), nullable=False),
        sa.Column("safety_hold_count", sa.Integer(), nullable=False),
        sa.Column("owner_suppressed_count", sa.Integer(), nullable=False),
        sa.Column("precision_bps", sa.Integer(), nullable=False),
        sa.Column("recall_bps", sa.Integer(), nullable=False),
        sa.Column("locked_negative_leaks", sa.Integer(), nullable=False),
        sa.Column("schema_valid_bps", sa.Integer(), nullable=False),
        sa.Column("new_owner_semantic_tasks", sa.Integer(), nullable=False),
        sa.Column("gate_passed", sa.Boolean(), nullable=False),
        sa.Column("authorizes_production", sa.Boolean(), nullable=False),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "mode IN ('OFFLINE_REPLAY','SHADOW')",
            name="ck_policy_evaluation_mode_v2",
        ),
        sa.CheckConstraint(
            "precision_bps BETWEEN 0 AND 10000 AND recall_bps BETWEEN 0 AND 10000 "
            "AND schema_valid_bps BETWEEN 0 AND 10000",
            name="ck_policy_evaluation_bps_v2",
        ),
        sa.CheckConstraint(
            "total_cases>=0 AND auto_accepted_count>=0 AND auto_filtered_count>=0 "
            "AND technical_retry_count>=0 AND technical_failed_count>=0 "
            "AND safety_hold_count>=0 AND owner_suppressed_count>=0 AND "
            "auto_accepted_count+auto_filtered_count+technical_retry_count+"
            "technical_failed_count+safety_hold_count+owner_suppressed_count=total_cases",
            name="ck_policy_evaluation_disposition_counts_v2",
        ),
        sa.CheckConstraint(
            "NOT gate_passed OR (total_cases>0 AND "
            "auto_accepted_count+auto_filtered_count=total_cases AND "
            "precision_bps>=9000 AND recall_bps>=9000 AND locked_negative_leaks=0 AND "
            "schema_valid_bps=10000)",
            name="ck_policy_evaluation_gate_terminal_v2",
        ),
        sa.CheckConstraint("locked_negative_leaks>=0", name="ck_policy_evaluation_leaks_v2"),
        sa.CheckConstraint(
            "new_owner_semantic_tasks=0",
            name="ck_policy_evaluation_no_owner_tasks_v2",
        ),
        sa.CheckConstraint(
            "authorizes_production=false",
            name="ck_policy_evaluation_not_production_authority_v2",
        ),
        sa.CheckConstraint(
            "corpus_manifest_sha256 ~ '^[a-f0-9]{64}$'",
            name="ck_policy_evaluation_manifest_hash_v2",
        ),
    )
    op.create_table(
        "qualification_shadow_decision_v2",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column(
            "evaluation_id",
            _uuid(),
            sa.ForeignKey("qualification_policy_evaluation_v2.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "policy_bundle_id",
            _uuid(),
            sa.ForeignKey("qualification_policy_bundle_v2.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "document_version_id",
            _uuid(),
            sa.ForeignKey("document_version.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "raw_object_id",
            _uuid(),
            sa.ForeignKey("raw_object.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("disposition", sa.String(30), nullable=False),
        sa.Column("reason_codes", postgresql.ARRAY(sa.String(80)), nullable=False),
        sa.Column("decision_trace", _json(), nullable=False),
        sa.Column("affects_production", sa.Boolean(), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "disposition IN ('AUTO_ACCEPTED','AUTO_FILTERED','TECHNICAL_RETRY',"
            "'TECHNICAL_FAILED','SAFETY_HOLD','OWNER_SUPPRESSED')",
            name="ck_shadow_decision_disposition_v2",
        ),
        sa.CheckConstraint(
            "affects_production=false",
            name="ck_shadow_decision_no_production_effect_v2",
        ),
        sa.UniqueConstraint(
            "evaluation_id",
            "document_version_id",
            name="uq_shadow_decision_evaluation_document_v2",
        ),
    )

    op.execute(
        """
        CREATE FUNCTION prevent_autonomous_policy_fact_mutation() RETURNS trigger
        LANGUAGE plpgsql AS $$ BEGIN
          RAISE EXCEPTION 'AUTONOMOUS_POLICY_APPEND_ONLY_FACT';
        END $$
        """
    )
    immutable_tables = (
        "qualification_policy_bundle_v2",
        "automated_qualification_decision_v2",
        "owner_exception_event_v2",
        "feed_suppression_rule_v2",
        "qualification_policy_evaluation_v2",
        "qualification_shadow_decision_v2",
    )
    for table in immutable_tables:
        op.execute(
            f"CREATE TRIGGER trg_{table}_append_only BEFORE UPDATE OR DELETE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION prevent_autonomous_policy_fact_mutation()"
        )

    all_tables = (*immutable_tables, "owner_exception_v2")
    for table in all_tables:
        op.execute(f"REVOKE ALL ON TABLE {table} FROM PUBLIC")
    op.execute(
        "GRANT SELECT,INSERT ON qualification_policy_bundle_v2,"
        "automated_qualification_decision_v2,qualification_policy_evaluation_v2,"
        "qualification_shadow_decision_v2 TO srbg_api_role"
    )
    op.execute(
        "GRANT SELECT,INSERT,UPDATE ON owner_exception_v2 TO srbg_api_role"
    )
    op.execute(
        "GRANT SELECT,INSERT ON owner_exception_event_v2,feed_suppression_rule_v2 "
        "TO srbg_api_role"
    )
    op.execute(
        "GRANT SELECT ON qualification_policy_bundle_v2,feed_suppression_rule_v2 "
        "TO srbg_worker_role"
    )
    op.execute(
        "GRANT SELECT ON qualification_policy_bundle_v2,"
        "automated_qualification_decision_v2,owner_exception_v2,"
        "feed_suppression_rule_v2,qualification_policy_evaluation_v2,"
        "qualification_shadow_decision_v2 TO srbg_publication_writer"
    )


def downgrade() -> None:
    bind = op.get_bind()
    durable = bind.execute(
        sa.text(
            "SELECT EXISTS("
            "SELECT 1 FROM qualification_policy_bundle_v2 UNION ALL "
            "SELECT 1 FROM automated_qualification_decision_v2 UNION ALL "
            "SELECT 1 FROM owner_exception_v2 UNION ALL "
            "SELECT 1 FROM owner_exception_event_v2 UNION ALL "
            "SELECT 1 FROM feed_suppression_rule_v2 UNION ALL "
            "SELECT 1 FROM qualification_policy_evaluation_v2 UNION ALL "
            "SELECT 1 FROM qualification_shadow_decision_v2)"
        )
    ).scalar_one()
    if durable:
        raise RuntimeError("AUTONOMOUS_POLICY_DOWNGRADE_BLOCKED")

    immutable_tables = (
        "qualification_policy_bundle_v2",
        "automated_qualification_decision_v2",
        "owner_exception_event_v2",
        "feed_suppression_rule_v2",
        "qualification_policy_evaluation_v2",
        "qualification_shadow_decision_v2",
    )
    for table in immutable_tables:
        op.execute(f"DROP TRIGGER trg_{table}_append_only ON {table}")
    op.execute("DROP FUNCTION prevent_autonomous_policy_fact_mutation()")
    op.drop_index("ix_feed_suppression_target_v2", table_name="feed_suppression_rule_v2")
    op.drop_index("ix_owner_exception_current_v2", table_name="owner_exception_v2")
    for table in (
        "qualification_shadow_decision_v2",
        "qualification_policy_evaluation_v2",
        "feed_suppression_rule_v2",
        "owner_exception_event_v2",
        "owner_exception_v2",
        "automated_qualification_decision_v2",
        "qualification_policy_bundle_v2",
    ):
        op.drop_table(table)
