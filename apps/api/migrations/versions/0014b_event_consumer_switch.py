"""Finish the Round 14 projection and event-keyed consumer expand phase.

Revision ID: 0014b_event_consumer_switch
Revises: 0014_event_unification

This migration is bounded DDL only. The versioned Round 14 backfill performs data
work before the guarded SHADOW -> EVENT switch.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0014b_event_consumer_switch"
down_revision = "0014_event_unification"
branch_labels = None
depends_on = None


def _uuid() -> postgresql.UUID:
    return postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.add_column(
        "event_projection_revision",
        sa.Column("event_revision_id", _uuid(), nullable=True),
        schema="published_v1",
    )
    op.add_column(
        "event_projection_revision",
        sa.Column(
            "publication_revision_ids",
            postgresql.ARRAY(_uuid()),
            nullable=False,
            server_default=sa.text("'{}'::uuid[]"),
        ),
        schema="published_v1",
    )
    op.execute(
        "UPDATE published_v1.event_projection_revision "
        "SET event_revision_id=id, publication_revision_ids="
        "CASE WHEN publication_revision_id IS NULL THEN '{}'::uuid[] "
        "ELSE ARRAY[publication_revision_id] END WHERE event_revision_id IS NULL"
    )
    op.alter_column(
        "event_projection_revision", "event_revision_id", nullable=False, schema="published_v1"
    )
    op.create_unique_constraint(
        "uq_event_projection_public_revision",
        "event_projection_revision",
        ["event_revision_id"],
        schema="published_v1",
    )

    op.create_table(
        "event_consumer_switch",
        sa.Column("singleton", sa.Boolean(), primary_key=True, server_default=sa.true()),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("changed_by", _uuid(), nullable=True),
        sa.Column("publication_revision_id", _uuid(), nullable=True),
        sa.Column(
            "changed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint("singleton", name="ck_event_consumer_switch_singleton"),
        sa.CheckConstraint(
            "status IN ('SHADOW','EVENT','ROLLBACK_READ_ONLY')",
            name="ck_event_consumer_switch_status",
        ),
    )
    op.execute("INSERT INTO event_consumer_switch (singleton,status) VALUES (true,'SHADOW')")

    op.add_column("daily_report_item", sa.Column("event_revision_id", _uuid(), nullable=True))
    op.create_foreign_key(
        "fk_daily_report_event_revision",
        "daily_report_item",
        "event_projection_revision",
        ["event_revision_id"],
        ["event_revision_id"],
        source_schema=None,
        referent_schema="published_v1",
        ondelete="RESTRICT",
    )
    op.create_index("ix_daily_report_event_revision", "daily_report_item", ["event_revision_id"])

    # Legacy item_id remains nullable, immutable provenance. Event is the only new key.
    op.execute(
        "ALTER TABLE collection_item DROP CONSTRAINT IF EXISTS "
        "collection_item_owner_id_item_id_fkey"
    )
    op.execute("ALTER TABLE saved_item DROP CONSTRAINT IF EXISTS saved_item_pkey")
    op.execute("ALTER TABLE collection_item DROP CONSTRAINT IF EXISTS collection_item_pkey")
    op.alter_column("saved_item", "item_id", existing_type=_uuid(), nullable=True)
    op.alter_column("collection_item", "item_id", existing_type=_uuid(), nullable=True)
    op.alter_column("item_feedback", "item_id", existing_type=_uuid(), nullable=True)
    op.create_unique_constraint("uq_saved_event", "saved_item", ["owner_id", "event_id"])
    op.create_unique_constraint(
        "uq_collection_event", "collection_item", ["collection_id", "event_id"]
    )
    op.create_unique_constraint(
        "uq_feedback_actor_event", "item_feedback", ["actor_id", "event_id"]
    )
    op.create_foreign_key(
        "fk_collection_saved_event",
        "collection_item",
        "saved_item",
        ["owner_id", "event_id"],
        ["owner_id", "event_id"],
        ondelete="CASCADE",
    )

    op.execute(
        """
        CREATE VIEW published_v1.event_redirect AS
        SELECT event.id AS event_id, event.canonical_event_id
          FROM public.event event
         WHERE event.id <> event.canonical_event_id
           AND EXISTS (
             SELECT 1 FROM published_v1.current_event_summary summary
              WHERE summary.event_id IN (event.id, event.canonical_event_id)
           )
        """
    )
    op.execute(
        """
        CREATE VIEW published_v1.event_search AS
        SELECT search.event_id, search.generation, search.title, summary.summary_payload
          FROM published_v1.title_search search
          JOIN published_v1.current_event_summary summary
            USING (event_id, generation)
        """
    )
    op.execute(
        """
        CREATE VIEW published_v1.daily_report AS
        SELECT id, report_date, snapshot_at, published_at, version
          FROM public.daily_report
         WHERE status='PUBLISHED'
        """
    )
    op.execute(
        """
        CREATE VIEW published_v1.daily_report_event AS
        SELECT item.report_id, item.section, item.position, item.event_id,
               item.event_revision_id, item.publication_revision_id,
               item.title, item.summary, item.original_url,
               CASE WHEN projection.event_id IS NULL THEN 'SOURCE_UNAVAILABLE'
                    ELSE 'PUBLISHED' END AS current_state
          FROM public.daily_report_item item
          JOIN public.daily_report report ON report.id=item.report_id
             AND report.status='PUBLISHED'
          LEFT JOIN published_v1.current_event_summary projection
            ON projection.event_id=item.event_id
         WHERE item.event_id IS NOT NULL
        """
    )
    op.execute(
        "GRANT SELECT ON published_v1.event_redirect, published_v1.event_search, "
        "published_v1.daily_report, published_v1.daily_report_event "
        "TO srbg_projection_reader"
    )
    op.execute("REVOKE ALL ON event_consumer_switch FROM PUBLIC")
    op.execute("GRANT SELECT ON event_consumer_switch TO srbg_runtime, srbg_publication_writer")
    op.execute("GRANT UPDATE ON event_consumer_switch TO srbg_publication_writer")


def downgrade() -> None:
    op.execute("DROP VIEW published_v1.daily_report_event")
    op.execute("DROP VIEW published_v1.daily_report")
    op.execute("DROP VIEW published_v1.event_search")
    op.execute("DROP VIEW published_v1.event_redirect")
    op.drop_constraint("fk_collection_saved_event", "collection_item", type_="foreignkey")
    op.drop_constraint("uq_feedback_actor_event", "item_feedback", type_="unique")
    op.drop_constraint("uq_collection_event", "collection_item", type_="unique")
    op.drop_constraint("uq_saved_event", "saved_item", type_="unique")
    op.alter_column("item_feedback", "item_id", existing_type=_uuid(), nullable=False)
    op.alter_column("collection_item", "item_id", existing_type=_uuid(), nullable=False)
    op.alter_column("saved_item", "item_id", existing_type=_uuid(), nullable=False)
    op.create_primary_key("saved_item_pkey", "saved_item", ["owner_id", "item_id"])
    op.create_primary_key("collection_item_pkey", "collection_item", ["collection_id", "item_id"])
    op.create_foreign_key(
        "collection_item_owner_id_item_id_fkey",
        "collection_item",
        "saved_item",
        ["owner_id", "item_id"],
        ["owner_id", "item_id"],
        ondelete="CASCADE",
    )
    op.drop_index("ix_daily_report_event_revision", table_name="daily_report_item")
    op.drop_constraint("fk_daily_report_event_revision", "daily_report_item", type_="foreignkey")
    op.drop_column("daily_report_item", "event_revision_id")
    op.drop_table("event_consumer_switch")
    op.drop_constraint(
        "uq_event_projection_public_revision",
        "event_projection_revision",
        schema="published_v1",
        type_="unique",
    )
    op.drop_column("event_projection_revision", "publication_revision_ids", schema="published_v1")
    op.drop_column("event_projection_revision", "event_revision_id", schema="published_v1")
