"""PERS-01 personal source intent and single-owner foundation.

Revision ID: 0021_personal_source_core
Revises: 0020_ai_content_preparation
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0021_personal_source_core"
down_revision = "0020_ai_content_preparation"
branch_labels = None
depends_on = None

LOCAL_OWNER_ID = "019b0000-0000-7000-8000-000000009001"
AUTOMATION_SETTING_ID = "019e0000-0000-7000-8000-000000002101"


def _uuid() -> postgresql.UUID:
    return postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.add_column(
        "source",
        sa.Column("desired_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "source",
        sa.Column(
            "runtime_state",
            sa.String(30),
            nullable=False,
            server_default="PENDING_CONFIGURATION",
        ),
    )
    op.add_column(
        "source",
        sa.Column("manual_disabled_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_check_constraint(
        "ck_source_personal_runtime_state",
        "source",
        "runtime_state IN ('PENDING_CONFIGURATION','STOPPED','RUNNING','ERROR')",
    )

    op.create_table(
        "personal_automation_setting",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("singleton_slot", sa.SmallInteger(), nullable=False, server_default="1"),
        sa.Column("owner_id", _uuid(), nullable=False),
        sa.Column("automation_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("singleton_slot", name="uq_personal_automation_singleton"),
        sa.UniqueConstraint("owner_id", name="uq_personal_automation_owner"),
        sa.CheckConstraint("singleton_slot = 1", name="ck_personal_automation_singleton"),
    )
    op.get_bind().execute(
        sa.text(
            "INSERT INTO personal_automation_setting("
            "id,singleton_slot,owner_id,automation_enabled,created_at,updated_at) VALUES ("
            "CAST(:id AS uuid),1,CAST(:owner_id AS uuid),false,now(),now())"
        ),
        {"id": AUTOMATION_SETTING_ID, "owner_id": LOCAL_OWNER_ID},
    )

    op.create_table(
        "source_key_activity_event",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column(
            "source_id",
            _uuid(),
            sa.ForeignKey("source.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("event_type", sa.String(40), nullable=False),
        sa.Column("actor_id", _uuid(), nullable=False),
        sa.Column("request_id", sa.String(100), nullable=False),
        sa.Column("before_state", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("after_state", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "event_type IN ('MANUAL_DISABLED','MANUAL_ENABLED','DISPLAY_NAME_CHANGED')",
            name="ck_source_key_activity_event_type",
        ),
    )
    op.create_index(
        "ix_source_key_activity_source_created",
        "source_key_activity_event",
        ["source_id", "created_at"],
    )
    op.execute(
        "CREATE TRIGGER trg_source_key_activity_event_append_only "
        "BEFORE UPDATE OR DELETE ON source_key_activity_event FOR EACH ROW "
        "EXECUTE FUNCTION prevent_round09_audit_mutation()"
    )

    op.execute(
        """
        CREATE FUNCTION prevent_personal_source_override() RETURNS trigger AS $$
        BEGIN
            IF NEW.manual_disabled_at IS NOT NULL
               AND (NEW.enabled OR NEW.runtime_state = 'RUNNING') THEN
                RAISE EXCEPTION 'manual source disable has priority';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        "CREATE TRIGGER trg_source_personal_disable_priority "
        "BEFORE INSERT OR UPDATE ON source FOR EACH ROW "
        "EXECUTE FUNCTION prevent_personal_source_override()"
    )

    op.execute(
        "GRANT SELECT ON personal_automation_setting,source_key_activity_event TO srbg_api_role"
    )
    op.execute("GRANT INSERT ON source_key_activity_event TO srbg_api_role")
    op.execute(
        "GRANT UPDATE (name,desired_enabled,manual_disabled_at,enabled,updated_at) "
        "ON source TO srbg_api_role"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_source_personal_disable_priority ON source")
    op.execute("DROP FUNCTION IF EXISTS prevent_personal_source_override()")
    op.execute(
        "DROP TRIGGER IF EXISTS trg_source_key_activity_event_append_only "
        "ON source_key_activity_event"
    )
    op.drop_index(
        "ix_source_key_activity_source_created",
        table_name="source_key_activity_event",
    )
    op.drop_table("source_key_activity_event")
    op.drop_table("personal_automation_setting")
    op.drop_constraint("ck_source_personal_runtime_state", "source", type_="check")
    op.drop_column("source", "manual_disabled_at")
    op.drop_column("source", "runtime_state")
    op.drop_column("source", "desired_enabled")
