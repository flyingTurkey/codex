"""Round 11 operations, recovery, pilot telemetry, and replay facts.

Revision ID: 0012_operations_readiness
Revises: 0011_feed_search_daily
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0012_operations_readiness"
down_revision = "0011_feed_search_daily"
branch_labels = None
depends_on = None

TABLES = (
    "failed_task",
    "replay_request",
    "usage_metric_bucket",
    "item_feedback",
    "recovery_exercise",
)


def _uuid() -> postgresql.UUID:
    return postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.create_table(
        "failed_task",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("task_kind", sa.String(40), nullable=False),
        sa.Column("execution_id", _uuid(), nullable=False),
        sa.Column("replayable", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("error_code", sa.String(80), nullable=False),
        sa.Column("priority", sa.SmallInteger(), nullable=False, server_default="5"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("failed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("priority BETWEEN 0 AND 9", name="ck_failed_task_priority"),
    )
    op.create_index(
        "ix_failed_task_open",
        "failed_task",
        ["failed_at"],
        postgresql_where=sa.text("resolved_at IS NULL"),
    )
    op.create_table(
        "replay_request",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("failed_task_id", _uuid(), sa.ForeignKey("failed_task.id"), nullable=False),
        sa.Column("actor_id", _uuid(), nullable=False),
        sa.Column("reason", sa.String(500), nullable=False),
        sa.Column("priority", sa.SmallInteger(), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False, unique=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="QUEUED"),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("priority BETWEEN 0 AND 9", name="ck_replay_request_priority"),
        sa.CheckConstraint("length(reason) >= 10", name="ck_replay_reason"),
        sa.CheckConstraint(
            "status IN ('QUEUED','RUNNING','SUCCEEDED','FAILED')",
            name="ck_replay_request_status",
        ),
    )
    op.create_index(
        "uq_replay_request_active_failed_task",
        "replay_request",
        ["failed_task_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('QUEUED','RUNNING')"),
    )
    op.create_table(
        "usage_metric_bucket",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("event_type", sa.String(40), nullable=False),
        sa.Column("bucket_started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("event_count", sa.BigInteger(), nullable=False, server_default="1"),
        sa.UniqueConstraint(
            "event_type",
            "bucket_started_at",
            name="uq_usage_metric_bucket_type_window",
        ),
        sa.CheckConstraint("event_count > 0", name="ck_usage_metric_bucket_positive"),
    )
    op.create_index(
        "ix_usage_metric_bucket_window",
        "usage_metric_bucket",
        ["bucket_started_at"],
    )
    op.create_table(
        "item_feedback",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("actor_id", _uuid(), nullable=False),
        sa.Column(
            "item_id",
            _uuid(),
            sa.ForeignKey("intelligence_item.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("value", sa.String(20), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("actor_id", "item_id", name="uq_item_feedback_actor_item"),
        sa.CheckConstraint("value IN ('USEFUL', 'NOT_USEFUL')", name="ck_item_feedback_value"),
    )
    op.create_table(
        "recovery_exercise",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("environment", sa.String(20), nullable=False),
        sa.Column("actor_id", sa.String(200), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("rpo_minutes", sa.Numeric(10, 2), nullable=False),
        sa.Column("rto_minutes", sa.Numeric(10, 2), nullable=False),
        sa.Column("evidence_sha256", sa.String(64), nullable=False),
        sa.Column("passed", sa.Boolean(), nullable=False),
        sa.CheckConstraint("evidence_sha256 ~ '^[a-f0-9]{64}$'", name="ck_recovery_hash"),
    )
    op.execute(f"REVOKE ALL ON {', '.join(TABLES)} FROM PUBLIC")
    op.execute(f"GRANT SELECT ON {', '.join(TABLES)} TO srbg_api_role")
    op.execute("GRANT SELECT ON failed_task, replay_request TO srbg_worker_role")
    op.execute("GRANT INSERT ON replay_request TO srbg_api_role")
    op.execute("GRANT INSERT, UPDATE ON usage_metric_bucket TO srbg_api_role")
    op.execute("GRANT INSERT, UPDATE ON item_feedback TO srbg_api_role")
    op.execute("GRANT INSERT ON failed_task TO srbg_worker_role")
    op.execute("GRANT UPDATE (status) ON replay_request TO srbg_worker_role")
    op.execute("GRANT UPDATE (resolved_at) ON failed_task TO srbg_worker_role")
    op.execute("GRANT SELECT, INSERT ON recovery_exercise TO srbg_admin_role")


def downgrade() -> None:
    for table in reversed(TABLES):
        op.drop_table(table)
