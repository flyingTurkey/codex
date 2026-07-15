"""Round 14 canonical Event identity expand migration.

Revision ID: 0014_event_unification
Revises: 0013_internal_projection

The data backfill is intentionally not executed here.  It is versioned,
chunked and resumable through the event_migration_* control tables.
"""

# ruff: noqa: E501 -- auditable PostgreSQL DDL is intentionally kept inline.

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0014_event_unification"
down_revision = "0013_internal_projection"
branch_labels = None
depends_on = None

ROUND14_TABLES = (
    "document_event_membership",
    "event_entity_relation",
    "topic_event",
    "event_taxonomy_assignment",
    "event_migration_run",
    "event_migration_checkpoint",
    "event_migration_blocker",
    "event_consumer_parity_difference",
    "event_identity_change_request",
    "event_identity_change_decision",
    "event_identity_change_target",
    "event_split_allocation",
)

EVENT_TYPES = (
    "SAFETY_INCIDENT",
    "REGULATION_CHANGE",
    "DIGITAL_PROJECT",
    "RESEARCH_RESULT",
    "PRODUCT_RELEASE",
)


def _uuid() -> postgresql.UUID:
    return postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    _expand_event_identity()
    _make_item_alias_immutable()
    _create_relation_models()
    _create_identity_change_workflow()
    _create_resumable_migration_controls()
    _expand_consumers_for_single_switch()
    _grant_permissions()


def _expand_event_identity() -> None:
    op.add_column("event", sa.Column("status", sa.String(20), nullable=False, server_default="ACTIVE"))
    op.add_column("event", sa.Column("canonical_event_id", _uuid(), nullable=True))
    op.add_column("event", sa.Column("version", sa.Integer(), nullable=False, server_default="1"))
    op.create_foreign_key("fk_event_canonical", "event", "event", ["canonical_event_id"], ["id"], ondelete="RESTRICT")
    op.create_check_constraint("ck_event_status", "event", "status IN ('ACTIVE','MERGED','SPLIT','WITHDRAWN')")
    op.create_check_constraint("ck_event_version", "event", "version >= 1")
    op.execute("UPDATE event SET canonical_event_id = id WHERE canonical_event_id IS NULL")
    op.alter_column("event", "canonical_event_id", nullable=False)
    op.create_index("ix_event_canonical_status", "event", ["canonical_event_id", "status"])
    op.execute(
        """
        CREATE FUNCTION initialize_event_identity() RETURNS trigger
        LANGUAGE plpgsql AS $$ BEGIN
          IF NEW.canonical_event_id IS NULL THEN NEW.canonical_event_id := NEW.id; END IF;
          RETURN NEW;
        END $$
        """
    )
    op.execute("CREATE TRIGGER trg_initialize_event_identity BEFORE INSERT ON event FOR EACH ROW EXECUTE FUNCTION initialize_event_identity()")
    # Generic Events must always be typed by their caller; there is no incident default.
    op.alter_column("event", "event_type", existing_type=sa.String(30), server_default=None)


def _make_item_alias_immutable() -> None:
    op.drop_constraint("ck_event_identity_binding_kind", "event_identity_binding", type_="check")
    op.create_check_constraint(
        "ck_event_identity_binding_kind",
        "event_identity_binding",
        "binding_kind IN ('CONFIRMED_MEMBERSHIP','ROUND13_ONE_TO_ONE','ROUND14_ONE_TO_ONE')",
    )
    op.add_column("event_identity_binding", sa.Column("rule_version", sa.String(50), nullable=False, server_default="round14-v1"))
    op.add_column("event_identity_binding", sa.Column("identity_key", sa.String(2048), nullable=True))
    op.execute(
        """
        CREATE FUNCTION prevent_event_identity_binding_mutation() RETURNS trigger
        LANGUAGE plpgsql AS $$ BEGIN
          RAISE EXCEPTION 'item_id to event_id binding is immutable';
        END $$
        """
    )
    op.execute("CREATE TRIGGER trg_event_identity_binding_immutable BEFORE UPDATE OR DELETE ON event_identity_binding FOR EACH ROW EXECUTE FUNCTION prevent_event_identity_binding_mutation()")


def _create_relation_models() -> None:
    op.create_table(
        "document_event_membership",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("document_id", _uuid(), sa.ForeignKey("document.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("event_id", _uuid(), sa.ForeignKey("event.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("source_role", sa.String(30), nullable=True),
        sa.Column("decided_by", _uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("document_id", "event_id", name="uq_document_event_membership"),
        sa.CheckConstraint("source_role IS NULL OR source_role IN ('ORIGINAL','REPRINT','MIRROR','INDEPENDENT_REPORT')", name="ck_document_event_source_role"),
    )
    # Existing event_relation rows remain readable; new rows use Event endpoints only.
    op.alter_column("event_relation", "candidate_id", existing_type=_uuid(), nullable=True)
    op.alter_column("event_relation", "event_id", existing_type=_uuid(), nullable=True)
    op.alter_column("event_relation", "source_item_id", existing_type=_uuid(), nullable=True)
    op.alter_column("event_relation", "target_item_id", existing_type=_uuid(), nullable=True)
    op.drop_constraint("ck_event_relation_type", "event_relation", type_="check")
    op.create_check_constraint(
        "ck_event_relation_type",
        "event_relation",
        "relation_type IN ('FOLLOW_UP','INVESTIGATES','PENALIZES','RECTIFIES','CORRECTS',"
        "'FOLLOW_UP_OF','SUPERSEDES','WITHDRAWS')",
    )
    op.add_column("event_relation", sa.Column("source_event_id", _uuid(), nullable=True))
    op.add_column("event_relation", sa.Column("target_event_id", _uuid(), nullable=True))
    op.add_column("event_relation", sa.Column("relation_scope", sa.String(20), nullable=False, server_default="LEGACY_ITEM"))
    op.execute("DROP TRIGGER trg_event_relation_projection ON event_relation")
    op.execute(
        "CREATE TRIGGER trg_event_relation_projection BEFORE INSERT ON event_relation "
        "FOR EACH ROW WHEN (NEW.relation_scope = 'LEGACY_ITEM') "
        "EXECUTE FUNCTION validate_event_relation_projection()"
    )
    op.create_foreign_key("fk_event_relation_source_event", "event_relation", "event", ["source_event_id"], ["id"], ondelete="RESTRICT")
    op.create_foreign_key("fk_event_relation_target_event", "event_relation", "event", ["target_event_id"], ["id"], ondelete="RESTRICT")
    op.create_check_constraint("ck_event_relation_scope", "event_relation", "relation_scope IN ('LEGACY_ITEM','EVENT_LIFECYCLE')")
    op.create_check_constraint("ck_event_relation_event_endpoints", "event_relation", "relation_scope <> 'EVENT_LIFECYCLE' OR (source_event_id IS NOT NULL AND target_event_id IS NOT NULL AND source_event_id <> target_event_id)")
    op.create_table(
        "event_entity_relation",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("event_id", _uuid(), sa.ForeignKey("event.id", ondelete="CASCADE"), nullable=False),
        sa.Column("entity_type", sa.String(50), nullable=False),
        sa.Column("entity_id", _uuid(), nullable=False),
        sa.Column("relation_type", sa.String(50), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("event_id", "entity_type", "entity_id", "relation_type", name="uq_event_entity_relation"),
    )
    op.create_table(
        "topic_event",
        sa.Column("topic_id", _uuid(), sa.ForeignKey("topic_cluster.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("event_id", _uuid(), sa.ForeignKey("event.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "event_taxonomy_assignment",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("event_id", _uuid(), sa.ForeignKey("event.id", ondelete="CASCADE"), nullable=False),
        sa.Column("taxonomy", sa.String(80), nullable=False),
        sa.Column("term", sa.String(200), nullable=False),
        sa.Column("rule_version", sa.String(50), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("event_id", "taxonomy", "term", name="uq_event_taxonomy_assignment"),
    )
    op.drop_constraint("ck_document_relation_type", "document_relation", type_="check")
    op.create_check_constraint(
        "ck_document_relation_type",
        "document_relation",
        "relation_type IN ('AMENDS','SUPERSEDES','FOLLOW_UP_OF','INVESTIGATES',"
        "'ENFORCES','RECTIFIES','CORRECTS')",
    )


def _create_identity_change_workflow() -> None:
    op.create_table(
        "event_identity_change_request",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("operation", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("reason", sa.String(1000), nullable=False),
        sa.Column("submitted_by", _uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("operation IN ('MERGE','SPLIT','ROLLBACK')", name="ck_event_identity_change_operation"),
        sa.CheckConstraint("status IN ('PENDING','APPROVED','REJECTED','APPLIED')", name="ck_event_identity_change_status"),
    )
    op.create_table(
        "event_identity_change_target",
        sa.Column("request_id", _uuid(), sa.ForeignKey("event_identity_change_request.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("event_id", _uuid(), sa.ForeignKey("event.id", ondelete="RESTRICT"), primary_key=True),
        sa.Column("target_role", sa.String(20), nullable=False),
    )
    op.create_table(
        "event_identity_change_decision",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("request_id", _uuid(), sa.ForeignKey("event_identity_change_request.id", ondelete="RESTRICT"), nullable=False, unique=True),
        sa.Column("decision", sa.String(20), nullable=False),
        sa.Column("reviewer_id", _uuid(), nullable=False),
        sa.Column("submitted_by", _uuid(), nullable=False),
        sa.Column("publication_revision_id", _uuid(), sa.ForeignKey("publication_revision.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("audit_log_id", _uuid(), sa.ForeignKey("audit_log.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("decision IN ('APPROVE','REJECT')", name="ck_event_identity_change_decision"),
        sa.CheckConstraint("reviewer_id <> submitted_by", name="ck_event_identity_change_duties"),
    )
    op.create_table(
        "event_split_allocation",
        sa.Column("request_id", _uuid(), sa.ForeignKey("event_identity_change_request.id", ondelete="RESTRICT"), primary_key=True),
        sa.Column("item_id", _uuid(), sa.ForeignKey("intelligence_item.id", ondelete="RESTRICT"), primary_key=True),
        sa.Column("child_event_id", _uuid(), sa.ForeignKey("event.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def _create_resumable_migration_controls() -> None:
    op.create_table(
        "event_migration_run",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("task_version", sa.String(50), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("auto_merge", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("task_version", name="uq_event_migration_task_version"),
        sa.CheckConstraint("auto_merge = false", name="ck_event_migration_auto_merge_disabled"),
    )
    op.create_table(
        "event_migration_checkpoint",
        sa.Column("run_id", _uuid(), sa.ForeignKey("event_migration_run.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("consumer", sa.String(80), primary_key=True),
        sa.Column("last_item_id", _uuid()),
        sa.Column("processed_count", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "event_migration_blocker",
        sa.Column("run_id", _uuid(), sa.ForeignKey("event_migration_run.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("item_id", _uuid(), sa.ForeignKey("intelligence_item.id", ondelete="RESTRICT"), primary_key=True),
        sa.Column("reason_code", sa.String(80), nullable=False),
        sa.Column("details", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "event_consumer_parity_difference",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("run_id", _uuid(), sa.ForeignKey("event_migration_run.id", ondelete="CASCADE"), nullable=False),
        sa.Column("consumer", sa.String(80), nullable=False),
        sa.Column("difference_code", sa.String(80), nullable=False),
        sa.Column("item_id", _uuid()),
        sa.Column("event_id", _uuid()),
        sa.Column("details", postgresql.JSONB(), nullable=False),
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False),
    )


def _expand_consumers_for_single_switch() -> None:
    for table in (
        "search_projection",
        "daily_report_item",
        "saved_item",
        "collection_item",
        "item_feedback",
    ):
        op.add_column(table, sa.Column("event_id", _uuid(), nullable=True))
        op.create_foreign_key(f"fk_{table}_event", table, "event", ["event_id"], ["id"], ondelete="RESTRICT")
        op.create_index(f"ix_{table}_event", table, ["event_id"])


def _grant_permissions() -> None:
    tables = ", ".join(ROUND14_TABLES)
    op.execute(f"REVOKE ALL ON {tables} FROM PUBLIC")
    op.execute(f"GRANT SELECT ON {tables} TO srbg_runtime, srbg_publication_writer")
    op.execute(f"GRANT INSERT, UPDATE ON {tables} TO srbg_publication_writer")
    op.execute("GRANT SELECT ON event_identity_binding TO srbg_runtime")
    op.execute("GRANT INSERT ON event_identity_binding TO srbg_publication_writer")
    op.execute("GRANT SELECT, UPDATE ON event TO srbg_publication_writer")
    op.execute(
        "GRANT SELECT, UPDATE ON search_projection, daily_report_item, "
        "saved_item, collection_item, item_feedback TO srbg_publication_writer"
    )


def downgrade() -> None:
    # Compatibility rollback is schema-only and is refused after consumer facts use event_id.
    op.execute(
        """
        DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM search_projection WHERE event_id IS NOT NULL)
             OR EXISTS (SELECT 1 FROM daily_report_item WHERE event_id IS NOT NULL)
             OR EXISTS (SELECT 1 FROM saved_item WHERE event_id IS NOT NULL)
             OR EXISTS (SELECT 1 FROM collection_item WHERE event_id IS NOT NULL)
             OR EXISTS (SELECT 1 FROM item_feedback WHERE event_id IS NOT NULL)
             OR EXISTS (SELECT 1 FROM event_relation WHERE relation_scope='EVENT_LIFECYCLE')
             OR EXISTS (
               SELECT 1 FROM document_relation
                WHERE relation_type NOT IN ('AMENDS','SUPERSEDES')
             ) THEN
            RAISE EXCEPTION 'Round14 downgrade blocked: event-keyed consumer facts exist';
          END IF;
        END $$
        """
    )
    for table in reversed(
        ("search_projection", "daily_report_item", "saved_item", "collection_item", "item_feedback")
    ):
        op.drop_index(f"ix_{table}_event", table_name=table)
        op.drop_constraint(f"fk_{table}_event", table, type_="foreignkey")
        op.drop_column(table, "event_id")
    for table in reversed(ROUND14_TABLES):
        op.drop_table(table)
    op.drop_constraint("ck_event_relation_event_endpoints", "event_relation", type_="check")
    op.drop_constraint("ck_event_relation_scope", "event_relation", type_="check")
    op.drop_constraint("fk_event_relation_target_event", "event_relation", type_="foreignkey")
    op.drop_constraint("fk_event_relation_source_event", "event_relation", type_="foreignkey")
    op.execute("DROP TRIGGER trg_event_relation_projection ON event_relation")
    op.drop_column("event_relation", "relation_scope")
    op.drop_column("event_relation", "target_event_id")
    op.drop_column("event_relation", "source_event_id")
    op.execute(
        "CREATE TRIGGER trg_event_relation_projection BEFORE INSERT ON event_relation "
        "FOR EACH ROW EXECUTE FUNCTION validate_event_relation_projection()"
    )
    op.drop_constraint("ck_event_relation_type", "event_relation", type_="check")
    op.create_check_constraint(
        "ck_event_relation_type",
        "event_relation",
        "relation_type IN ('FOLLOW_UP','INVESTIGATES','PENALIZES','RECTIFIES','CORRECTS')",
    )
    op.alter_column("event_relation", "target_item_id", existing_type=_uuid(), nullable=False)
    op.alter_column("event_relation", "source_item_id", existing_type=_uuid(), nullable=False)
    op.alter_column("event_relation", "event_id", existing_type=_uuid(), nullable=False)
    op.alter_column("event_relation", "candidate_id", existing_type=_uuid(), nullable=False)
    op.drop_constraint("ck_document_relation_type", "document_relation", type_="check")
    op.create_check_constraint(
        "ck_document_relation_type",
        "document_relation",
        "relation_type IN ('AMENDS','SUPERSEDES')",
    )
    op.execute("DROP TRIGGER trg_event_identity_binding_immutable ON event_identity_binding")
    op.execute("DROP FUNCTION prevent_event_identity_binding_mutation()")
    op.drop_column("event_identity_binding", "identity_key")
    op.drop_column("event_identity_binding", "rule_version")
    op.drop_constraint("ck_event_identity_binding_kind", "event_identity_binding", type_="check")
    op.create_check_constraint(
        "ck_event_identity_binding_kind",
        "event_identity_binding",
        "binding_kind IN ('CONFIRMED_MEMBERSHIP','ROUND13_ONE_TO_ONE')",
    )
    op.alter_column(
        "event",
        "event_type",
        existing_type=sa.String(30),
        server_default=sa.text("'SAFETY_INCIDENT'"),
    )
    op.execute("DROP TRIGGER trg_initialize_event_identity ON event")
    op.execute("DROP FUNCTION initialize_event_identity()")
    op.drop_index("ix_event_canonical_status", table_name="event")
    op.drop_constraint("ck_event_version", "event", type_="check")
    op.drop_constraint("ck_event_status", "event", type_="check")
    op.drop_constraint("fk_event_canonical", "event", type_="foreignkey")
    op.drop_column("event", "version")
    op.drop_column("event", "canonical_event_id")
    op.drop_column("event", "status")
