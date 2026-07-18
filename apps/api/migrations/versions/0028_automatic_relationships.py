"""PERS-08 automatic reversible intelligence relationships.

Revision ID: 0028_automatic_relationships
Revises: 0027_ai_judgment_versions
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0028_automatic_relationships"
down_revision = "0027_ai_judgment_versions"
branch_labels = None
depends_on = None


def _uuid() -> postgresql.UUID:
    return postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.create_table(
        "automatic_relationship_decision_version",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("relationship_key", sa.String(500), nullable=False),
        sa.Column("relationship_kind", sa.String(40), nullable=False),
        sa.Column(
            "source_item_id",
            _uuid(),
            sa.ForeignKey("intelligence_item.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "target_item_id",
            _uuid(),
            sa.ForeignKey("intelligence_item.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("algorithm_version", sa.String(100), nullable=False),
        sa.Column("model_version", sa.String(200)),
        sa.Column("score_bps", sa.Integer(), nullable=False),
        sa.Column("reason_codes", postgresql.ARRAY(sa.String(80)), nullable=False),
        sa.Column("reason", sa.String(1000), nullable=False),
        sa.Column("input_fingerprint_sha256", sa.String(64), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column(
            "supersedes_decision_id",
            _uuid(),
            sa.ForeignKey("automatic_relationship_decision_version.id", ondelete="RESTRICT"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("invalidated_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint(
            "relationship_key", "input_fingerprint_sha256", name="uq_automatic_relationship_input"
        ),
        sa.CheckConstraint(
            "source_item_id <> target_item_id", name="ck_automatic_relationship_distinct"
        ),
        sa.CheckConstraint("score_bps BETWEEN 0 AND 10000", name="ck_automatic_relationship_score"),
        sa.CheckConstraint(
            "input_fingerprint_sha256 ~ '^[0-9a-f]{64}$'", name="ck_automatic_relationship_hash"
        ),
        sa.CheckConstraint(
            "status IN ('ACTIVE','INVALIDATED','WITHDRAWN','SUPERSEDED')",
            name="ck_automatic_relationship_status",
        ),
    )
    op.create_index(
        "ix_automatic_relationship_active",
        "automatic_relationship_decision_version",
        ["relationship_key", "status"],
    )
    op.create_table(
        "automatic_relationship_member",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column(
            "decision_id",
            _uuid(),
            sa.ForeignKey("automatic_relationship_decision_version.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "intelligence_item_id",
            _uuid(),
            sa.ForeignKey("intelligence_item.id", ondelete="RESTRICT"),
        ),
        sa.Column("document_id", _uuid(), sa.ForeignKey("document.id", ondelete="RESTRICT")),
        sa.Column(
            "document_version_id",
            _uuid(),
            sa.ForeignKey("document_version.id", ondelete="RESTRICT"),
        ),
        sa.Column("claim_id", _uuid(), sa.ForeignKey("claim.id", ondelete="RESTRICT")),
        sa.Column(
            "claim_evidence_id", _uuid(), sa.ForeignKey("claim_evidence.id", ondelete="RESTRICT")
        ),
        sa.Column("event_id", _uuid(), sa.ForeignKey("event.id", ondelete="RESTRICT")),
        sa.Column("topic_id", _uuid(), sa.ForeignKey("topic_cluster.id", ondelete="RESTRICT")),
        sa.Column(
            "product_model_id",
            _uuid(),
            sa.ForeignKey("technology_product_model.id", ondelete="RESTRICT"),
        ),
        sa.Column(
            "product_version_id",
            _uuid(),
            sa.ForeignKey("technology_product_version.id", ondelete="RESTRICT"),
        ),
        sa.Column("content_sha256", sa.String(64)),
        sa.Column("source_role", sa.String(40)),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.UniqueConstraint(
            "decision_id", "position", name="uq_automatic_relationship_member_position"
        ),
        sa.CheckConstraint("position >= 1", name="ck_automatic_relationship_member_position"),
    )
    op.create_table(
        "owner_relationship_correction",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("command_id", _uuid(), nullable=False, unique=True),
        sa.Column(
            "event_id", _uuid(), sa.ForeignKey("event.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column(
            "decision_id",
            _uuid(),
            sa.ForeignKey("automatic_relationship_decision_version.id", ondelete="RESTRICT"),
        ),
        sa.Column(
            "resulting_decision_id",
            _uuid(),
            sa.ForeignKey("automatic_relationship_decision_version.id", ondelete="RESTRICT"),
        ),
        sa.Column("action", sa.String(40), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("reason", sa.String(1000), nullable=False),
        sa.Column("owner_id", _uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "action IN ('SPLIT_EVENT','KEEP_INDEPENDENT','CORRECT_MODEL_RELATION')",
            name="ck_owner_relationship_correction_action",
        ),
    )
    op.create_table(
        "owner_relationship_withdrawal",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("command_id", _uuid(), nullable=False, unique=True),
        sa.Column(
            "decision_id",
            _uuid(),
            sa.ForeignKey("automatic_relationship_decision_version.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("relationship_kind", sa.String(40), nullable=False),
        sa.Column("member_item_ids", postgresql.ARRAY(_uuid()), nullable=False),
        sa.Column("input_fingerprint_sha256", sa.String(64), nullable=False),
        sa.Column("reason", sa.String(1000), nullable=False),
        sa.Column("owner_id", _uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "input_fingerprint_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_owner_relationship_withdrawal_hash",
        ),
    )
    op.create_table(
        "automatic_relationship_invalidation",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column(
            "invalidated_decision_id",
            _uuid(),
            sa.ForeignKey("automatic_relationship_decision_version.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "correction_id",
            _uuid(),
            sa.ForeignKey("owner_relationship_correction.id", ondelete="RESTRICT"),
        ),
        sa.Column(
            "withdrawal_id",
            _uuid(),
            sa.ForeignKey("owner_relationship_withdrawal.id", ondelete="RESTRICT"),
        ),
        sa.Column(
            "successor_decision_id",
            _uuid(),
            sa.ForeignKey("automatic_relationship_decision_version.id", ondelete="RESTRICT"),
        ),
        sa.Column("reason", sa.String(1000), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "correction_id IS NOT NULL OR withdrawal_id IS NOT NULL "
            "OR successor_decision_id IS NOT NULL",
            name="ck_automatic_relationship_invalidation_cause",
        ),
    )

    op.drop_constraint("ck_document_event_source_role", "document_event_membership", type_="check")
    op.create_check_constraint(
        "ck_document_event_source_role",
        "document_event_membership",
        "source_role IS NULL OR source_role IN "
        "('ORIGINAL','REPRINT','MIRROR','INDEPENDENT_REPORT','VENDOR_STATEMENT',"
        "'MEDIA_REPORT','INDEPENDENT_VERIFICATION')",
    )
    op.drop_constraint("ck_source_lineage_role", "source_lineage", type_="check")
    op.create_check_constraint(
        "ck_source_lineage_role",
        "source_lineage",
        "role IN ('ORIGINAL','REPRINT','MIRROR','INDEPENDENT_REPORT','VENDOR_STATEMENT',"
        "'MEDIA_REPORT','INDEPENDENT_VERIFICATION')",
    )

    op.execute(
        "REVOKE ALL ON automatic_relationship_decision_version,automatic_relationship_member,"
        "owner_relationship_correction,owner_relationship_withdrawal,"
        "automatic_relationship_invalidation FROM PUBLIC"
    )
    op.execute(
        "GRANT SELECT,INSERT,UPDATE ON automatic_relationship_decision_version,"
        "automatic_relationship_member TO srbg_worker_role"
    )
    op.execute(
        "GRANT SELECT ON automatic_relationship_decision_version,automatic_relationship_member,"
        "owner_relationship_correction,owner_relationship_withdrawal,"
        "automatic_relationship_invalidation TO srbg_runtime,srbg_projection_reader"
    )
    op.execute(
        "GRANT SELECT,INSERT,UPDATE ON automatic_relationship_decision_version,"
        "automatic_relationship_member,owner_relationship_correction,"
        "owner_relationship_withdrawal,automatic_relationship_invalidation "
        "TO srbg_publication_writer"
    )
    op.execute("GRANT UPDATE (event_id) ON event_item TO srbg_publication_writer")

    op.execute("""
        CREATE FUNCTION reject_pers08_legacy_candidate_write() RETURNS trigger
        LANGUAGE plpgsql AS $$ BEGIN
          RAISE EXCEPTION 'PERS08_LEGACY_CANDIDATE_FROZEN';
        END $$
    """)
    for table in (
        "duplicate_candidate",
        "event_item_candidate",
        "event_relation_candidate",
        "product_normalization_candidate",
    ):
        op.execute(
            f"CREATE TRIGGER trg_{table}_pers08_frozen BEFORE INSERT ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION reject_pers08_legacy_candidate_write()"
        )
    op.execute("""
        CREATE TRIGGER trg_topic_cluster_pers08_frozen
        BEFORE INSERT ON topic_cluster FOR EACH ROW
        WHEN (NEW.status = 'PENDING_REVIEW')
        EXECUTE FUNCTION reject_pers08_legacy_candidate_write()
    """)


def downgrade() -> None:
    bind = op.get_bind()
    populated = bind.execute(
        sa.text(
            "SELECT EXISTS(SELECT 1 FROM automatic_relationship_decision_version) "
            "OR EXISTS(SELECT 1 FROM owner_relationship_correction) "
            "OR EXISTS(SELECT 1 FROM owner_relationship_withdrawal)"
        )
    ).scalar_one()
    if populated:
        raise RuntimeError("0028_DOWNGRADE_BLOCKED: automatic relationship facts exist")
    op.execute("DROP TRIGGER trg_topic_cluster_pers08_frozen ON topic_cluster")
    op.execute("REVOKE UPDATE (event_id) ON event_item FROM srbg_publication_writer")
    for table in (
        "duplicate_candidate",
        "event_item_candidate",
        "event_relation_candidate",
        "product_normalization_candidate",
    ):
        op.execute(f"DROP TRIGGER trg_{table}_pers08_frozen ON {table}")
    op.execute("DROP FUNCTION reject_pers08_legacy_candidate_write()")
    op.drop_constraint("ck_source_lineage_role", "source_lineage", type_="check")
    op.create_check_constraint(
        "ck_source_lineage_role",
        "source_lineage",
        "role IN ('ORIGINAL','REPRINT','MIRROR','INDEPENDENT_REPORT')",
    )
    op.drop_constraint("ck_document_event_source_role", "document_event_membership", type_="check")
    op.create_check_constraint(
        "ck_document_event_source_role",
        "document_event_membership",
        "source_role IS NULL OR source_role IN "
        "('ORIGINAL','REPRINT','MIRROR','INDEPENDENT_REPORT')",
    )
    for table in (
        "automatic_relationship_invalidation",
        "owner_relationship_withdrawal",
        "owner_relationship_correction",
        "automatic_relationship_member",
        "automatic_relationship_decision_version",
    ):
        op.drop_table(table)
