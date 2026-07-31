"""PostgreSQL authoritative scheduling, source health and safe replay.

Revision ID: 0016_scheduling_health_replay
Revises: 0015b_source_center_convergence
"""

# SQL DDL is intentionally kept intact for migration evidence review.
# ruff: noqa: E501

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0016_scheduling_health_replay"
down_revision: str | Sequence[str] | None = "0015b_source_center_convergence"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _uuid() -> postgresql.UUID:
    return postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.create_table(
        "fetch_schedule",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column(
            "source_id",
            _uuid(),
            sa.ForeignKey("source.id", ondelete="RESTRICT"),
            nullable=False,
            unique=True,
        ),
        sa.Column("authority_level", sa.String(10), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("interval_seconds", sa.Integer(), nullable=False),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lease_token", _uuid()),
        sa.Column("leased_until", sa.DateTime(timezone=True)),
        sa.Column("backoff_base_seconds", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("backoff_cap_seconds", sa.Integer(), nullable=False, server_default="21600"),
        sa.Column("max_attempts", sa.SmallInteger(), nullable=False, server_default="3"),
        sa.Column("consecutive_failures", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("circuit_state", sa.String(20), nullable=False, server_default="CLOSED"),
        sa.Column("circuit_open_until", sa.DateTime(timezone=True)),
        sa.Column("freshness_slo_seconds", sa.Integer(), nullable=False),
        sa.Column("rate_limit_per_minute", sa.Integer(), nullable=False),
        sa.Column("daily_request_budget", sa.Integer(), nullable=False),
        sa.Column("daily_byte_budget", sa.BigInteger(), nullable=False),
        sa.Column("requests_used", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("bytes_used", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("budget_window_started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("last_idempotency_key", sa.String(128), unique=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('ACTIVE','PAUSED','RETIRED')", name="ck_fetch_schedule_status"
        ),
        sa.CheckConstraint(
            "circuit_state IN ('CLOSED','OPEN','HALF_OPEN')", name="ck_fetch_schedule_circuit"
        ),
        sa.CheckConstraint(
            "interval_seconds > 0 AND freshness_slo_seconds > 0", name="ck_fetch_schedule_intervals"
        ),
        sa.CheckConstraint("max_attempts BETWEEN 1 AND 10", name="ck_fetch_schedule_attempts"),
        sa.CheckConstraint(
            "rate_limit_per_minute > 0 AND daily_request_budget > 0 AND daily_byte_budget > 0",
            name="ck_fetch_schedule_budgets",
        ),
    )
    op.create_index(
        "ix_fetch_schedule_due",
        "fetch_schedule",
        ["next_run_at"],
        postgresql_where=sa.text("status = 'ACTIVE'"),
    )

    op.alter_column("fetch_run", "source_connector_id", existing_type=_uuid(), nullable=True)
    for name, column, target in (
        ("source_id", sa.Column("source_id", _uuid()), "source.id"),
        ("schedule_id", sa.Column("schedule_id", _uuid()), "fetch_schedule.id"),
        ("policy_version_id", sa.Column("policy_version_id", _uuid()), "source_policy_version.id"),
        (
            "connector_config_version_id",
            sa.Column("connector_config_version_id", _uuid()),
            "connector_config_version.id",
        ),
    ):
        op.add_column("fetch_run", column)
        op.create_foreign_key(
            f"fk_fetch_run_{name}",
            "fetch_run",
            target.split(".")[0],
            [name],
            [target.split(".")[1]],
            ondelete="RESTRICT",
        )
    op.add_column("fetch_run", sa.Column("idempotency_key", sa.String(160)))
    op.add_column("fetch_run", sa.Column("execution_lease_token", _uuid()))
    op.add_column("fetch_run", sa.Column("execution_lease_until", sa.DateTime(timezone=True)))
    op.add_column("fetch_run", sa.Column("heartbeat_at", sa.DateTime(timezone=True)))
    op.add_column(
        "fetch_run", sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0")
    )
    op.add_column("fetch_run", sa.Column("failure_class", sa.String(50)))
    op.add_column("fetch_run", sa.Column("next_retry_at", sa.DateTime(timezone=True)))
    op.add_column("fetch_run", sa.Column("transport_status", sa.String(20)))
    op.add_column("fetch_run", sa.Column("discovery_status", sa.String(20)))
    op.add_column("fetch_run", sa.Column("parse_status", sa.String(20)))
    op.add_column("fetch_run", sa.Column("quality_status", sa.String(20)))
    op.create_unique_constraint("uq_fetch_run_idempotency_key", "fetch_run", ["idempotency_key"])
    op.drop_constraint("ck_fetch_run_status", "fetch_run", type_="check")
    op.create_check_constraint(
        "ck_fetch_run_status",
        "fetch_run",
        "status IN ('PENDING_DISPATCH','DISPATCHED','RUNNING','RETRY_WAIT','SUCCEEDED','NOT_MODIFIED','PARTIAL','FAILED','CANCELLED','CIRCUIT_OPEN')",
    )

    op.create_table(
        "source_health_snapshot",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column(
            "source_id", _uuid(), sa.ForeignKey("source.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column(
            "fetch_run_id",
            _uuid(),
            sa.ForeignKey("fetch_run.id", ondelete="RESTRICT"),
            nullable=False,
            unique=True,
        ),
        sa.Column("transport_status", sa.String(20), nullable=False),
        sa.Column("discovery_status", sa.String(20), nullable=False),
        sa.Column("parse_status", sa.String(20), nullable=False),
        sa.Column("quality_status", sa.String(20), nullable=False),
        sa.Column("freshness_status", sa.String(20), nullable=False),
        sa.Column("latest_published_at", sa.DateTime(timezone=True)),
        sa.Column("discovered_count", sa.Integer(), nullable=False),
        sa.Column("parsed_count", sa.Integer(), nullable=False),
        sa.Column("required_field_basis_points", sa.Integer(), nullable=False),
        sa.Column("duplicate_basis_points", sa.Integer(), nullable=False),
        sa.Column("oldest_queue_age_seconds", sa.Integer(), nullable=False),
        sa.Column("rule_version", sa.String(50), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "source_anomaly",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column(
            "source_id", _uuid(), sa.ForeignKey("source.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column(
            "health_snapshot_id",
            _uuid(),
            sa.ForeignKey("source_health_snapshot.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("code", sa.String(60), nullable=False),
        sa.Column("severity", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="OPEN"),
        sa.Column("rule_version", sa.String(50), nullable=False),
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "severity IN ('INFO','WARNING','CRITICAL')", name="ck_source_anomaly_severity"
        ),
        sa.CheckConstraint(
            "status IN ('OPEN','ACKNOWLEDGED','RESOLVED')", name="ck_source_anomaly_status"
        ),
    )

    # Some long-lived pre-R12 installations used the original operations
    # prototype shape (target_id/payload_sha256) even though their Alembic
    # version was advanced.  R16 must repair that drift without treating the
    # Celery target id as a verified business reference.  The canonical R12
    # schema already has these columns, so these statements are no-ops there.
    op.execute(
        "ALTER TABLE failed_task ADD COLUMN IF NOT EXISTS execution_id uuid"
    )
    op.execute(
        "ALTER TABLE failed_task ADD COLUMN IF NOT EXISTS replayable boolean "
        "NOT NULL DEFAULT false"
    )

    for column in (
        sa.Column("source_id", _uuid()),
        sa.Column("run_id", _uuid()),
        sa.Column("document_version_id", _uuid()),
        sa.Column("event_id", _uuid()),
        sa.Column("processing_version", sa.String(100)),
        sa.Column(
            "reconstruction_status", sa.String(30), nullable=False, server_default="NON_REPLAYABLE"
        ),
        sa.Column("blocked_reason", sa.String(80)),
    ):
        op.add_column("failed_task", column)
    op.create_foreign_key(
        "fk_failed_task_source", "failed_task", "source", ["source_id"], ["id"], ondelete="RESTRICT"
    )
    op.create_foreign_key(
        "fk_failed_task_run", "failed_task", "fetch_run", ["run_id"], ["id"], ondelete="RESTRICT"
    )
    op.create_foreign_key(
        "fk_failed_task_document_version",
        "failed_task",
        "document_version",
        ["document_version_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_failed_task_event", "failed_task", "event", ["event_id"], ["id"], ondelete="RESTRICT"
    )
    op.create_check_constraint(
        "ck_failed_task_reconstruction",
        "failed_task",
        "reconstruction_status IN ('REPLAYABLE','NON_REPLAYABLE','BLOCKED')",
    )
    op.execute("""
        UPDATE failed_task SET replayable=FALSE,
          reconstruction_status='NON_REPLAYABLE', blocked_reason='LEGACY_TASK_ID_ONLY'
        WHERE task_kind='SOURCE_FETCH' AND run_id IS NULL
    """)
    op.execute("""
        UPDATE failed_task SET reconstruction_status='REPLAYABLE'
        WHERE replayable IS TRUE AND task_kind IN ('PUBLICATION_OUTBOX','PROJECTION')
    """)
    op.add_column("replay_request", sa.Column("lease_token", _uuid()))
    op.add_column("replay_request", sa.Column("leased_until", sa.DateTime(timezone=True)))
    op.add_column("replay_request", sa.Column("completed_at", sa.DateTime(timezone=True)))
    op.add_column("replay_request", sa.Column("outcome_reason", sa.String(80)))
    op.drop_constraint("ck_replay_request_status", "replay_request", type_="check")
    op.create_check_constraint(
        "ck_replay_request_status",
        "replay_request",
        "status IN ('QUEUED','RUNNING','SUCCEEDED','FAILED','BLOCKED','NON_REPLAYABLE')",
    )

    op.create_table(
        "retention_execution",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column(
            "source_id", _uuid(), sa.ForeignKey("source.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column(
            "raw_object_id",
            _uuid(),
            sa.ForeignKey("raw_object.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "document_version_id",
            _uuid(),
            sa.ForeignKey("document_version.id", ondelete="RESTRICT"),
        ),
        sa.Column(
            "policy_version_id",
            _uuid(),
            sa.ForeignKey("source_policy_version.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("legal_hold_checked", sa.Boolean(), nullable=False),
        sa.Column("unique_evidence_checked", sa.Boolean(), nullable=False),
        sa.Column(
            "publication_invalidated", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column("erasure_method", sa.String(30)),
        sa.Column("content_sha256", sa.String(64), nullable=False),
        sa.Column("byte_size", sa.BigInteger(), nullable=False),
        sa.Column("mime_type", sa.String(200), nullable=False),
        sa.Column("reason_code", sa.String(80), nullable=False),
        sa.Column("actor_id", _uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("raw_object_id", name="uq_retention_execution_raw_object"),
        sa.CheckConstraint(
            "status IN ('PENDING','BLOCKED_LEGAL_HOLD','BLOCKED_UNIQUE_EVIDENCE','INVALIDATING','ERASED','FAILED')",
            name="ck_retention_execution_status",
        ),
        sa.CheckConstraint("content_sha256 ~ '^[0-9a-f]{64}$'", name="ck_retention_execution_hash"),
    )

    # The runtime claim uses this exact eligibility shape with FOR UPDATE SKIP LOCKED.
    op.execute("""
      CREATE OR REPLACE FUNCTION claim_due_fetch_schedule(p_now timestamptz, p_lease_until timestamptz, p_token uuid)
      RETURNS TABLE(schedule_id uuid, source_id uuid) LANGUAGE sql SECURITY DEFINER AS $$
        WITH due AS (
          SELECT fs.id, fs.source_id FROM fetch_schedule fs
          JOIN source s ON s.id=fs.source_id
          JOIN source_policy_version p ON p.id=s.current_policy_version_id
          JOIN connector_config_version c ON c.id=s.current_connector_config_version_id
          WHERE fs.status='ACTIVE' AND s.lifecycle_state='ACTIVE'
            AND p.status='APPROVED' AND p.valid_from <= p_now AND p.valid_until > p_now
            AND c.validation_status='VALID' AND fs.next_run_at <= p_now
            AND fs.requests_used < fs.daily_request_budget AND fs.bytes_used < fs.daily_byte_budget
            AND (fs.leased_until IS NULL OR fs.leased_until <= p_now)
            AND (fs.circuit_state='CLOSED' OR (fs.circuit_state='OPEN' AND fs.circuit_open_until <= p_now))
            AND EXISTS (SELECT 1 FROM source_governance_decision d WHERE d.source_id=s.id AND d.decision_type='PRODUCTION_APPROVAL' AND d.outcome='APPROVED' AND (d.valid_until IS NULL OR d.valid_until > p_now))
          ORDER BY fs.next_run_at, fs.id LIMIT 1 FOR UPDATE SKIP LOCKED
        )
        UPDATE fetch_schedule fs SET lease_token=p_token, leased_until=p_lease_until,
          circuit_state=CASE WHEN fs.circuit_state='OPEN' THEN 'HALF_OPEN' ELSE fs.circuit_state END
        FROM due WHERE fs.id=due.id RETURNING fs.id, fs.source_id
      $$
    """)
    op.execute(
        "REVOKE ALL ON FUNCTION claim_due_fetch_schedule(timestamptz,timestamptz,uuid) FROM PUBLIC"
    )
    op.execute(
        "GRANT EXECUTE ON FUNCTION claim_due_fetch_schedule(timestamptz,timestamptz,uuid) TO srbg_worker_role"
    )
    tables = "fetch_schedule, source_health_snapshot, source_anomaly, retention_execution"
    op.execute(f"REVOKE ALL ON {tables} FROM PUBLIC")
    op.execute(f"GRANT SELECT ON {tables} TO srbg_api_role")
    op.execute("GRANT INSERT, UPDATE ON fetch_schedule TO srbg_api_role")
    op.execute(
        "GRANT SELECT, INSERT, UPDATE ON fetch_schedule, source_health_snapshot, source_anomaly TO srbg_worker_role"
    )
    op.execute(
        "GRANT UPDATE (lease_token,leased_until,completed_at,outcome_reason,status) ON replay_request TO srbg_worker_role"
    )
    op.execute(
        "GRANT UPDATE (replayable,reconstruction_status,blocked_reason,resolved_at) "
        "ON failed_task TO srbg_worker_role"
    )
    op.execute("GRANT SELECT, INSERT, UPDATE ON retention_execution TO srbg_publication_writer")
    op.execute(
        "REVOKE ALL ON fetch_schedule, source_health_snapshot, source_anomaly, retention_execution FROM srbg_projection_reader"
    )


def downgrade() -> None:
    bind = op.get_bind()
    count = bind.execute(
        sa.text(
            "SELECT (SELECT count(*) FROM fetch_schedule) + (SELECT count(*) FROM source_health_snapshot) + (SELECT count(*) FROM source_anomaly) + (SELECT count(*) FROM retention_execution)"
        )
    ).scalar_one()
    if count:
        raise RuntimeError("0016_DOWNGRADE_BLOCKED: authoritative scheduling facts exist")
    op.execute("DROP FUNCTION IF EXISTS claim_due_fetch_schedule(timestamptz,timestamptz,uuid)")
    op.drop_table("retention_execution")
    for name in ("outcome_reason", "completed_at", "leased_until", "lease_token"):
        op.drop_column("replay_request", name)
    op.drop_constraint("ck_failed_task_reconstruction", "failed_task", type_="check")
    for name in ("event_id", "document_version_id", "run_id", "source_id"):
        op.drop_constraint(
            f"fk_failed_task_{'document_version' if name == 'document_version_id' else name.removesuffix('_id')}",
            "failed_task",
            type_="foreignkey",
        )
    for name in (
        "blocked_reason",
        "reconstruction_status",
        "processing_version",
        "event_id",
        "document_version_id",
        "run_id",
        "source_id",
    ):
        op.drop_column("failed_task", name)
    op.drop_table("source_anomaly")
    op.drop_table("source_health_snapshot")
    op.drop_constraint("uq_fetch_run_idempotency_key", "fetch_run", type_="unique")
    for name in (
        "quality_status",
        "parse_status",
        "discovery_status",
        "transport_status",
        "next_retry_at",
        "failure_class",
        "attempt_count",
        "heartbeat_at",
        "execution_lease_until",
        "execution_lease_token",
        "idempotency_key",
    ):
        op.drop_column("fetch_run", name)
    for name in ("connector_config_version_id", "policy_version_id", "schedule_id", "source_id"):
        op.drop_constraint(f"fk_fetch_run_{name}", "fetch_run", type_="foreignkey")
        op.drop_column("fetch_run", name)
    op.drop_table("fetch_schedule")
