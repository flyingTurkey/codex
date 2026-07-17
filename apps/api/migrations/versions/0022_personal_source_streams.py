"""PERS-02 public URL detection and personal source streams.

Revision ID: 0022_personal_source_streams
Revises: 0021_personal_source_core
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0022_personal_source_streams"
down_revision = "0021_personal_source_core"
branch_labels = None
depends_on = None


def _uuid() -> postgresql.UUID:
    return postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.add_column("source", sa.Column("normalized_origin", sa.String(2048)))
    op.create_index(
        "uq_source_personal_normalized_origin",
        "source",
        ["normalized_origin"],
        unique=True,
        postgresql_where=sa.text("normalized_origin IS NOT NULL"),
    )

    op.drop_constraint("ck_source_stream_status", "source_stream", type_="check")
    op.add_column(
        "source_stream",
        sa.Column("stream_type", sa.String(30), nullable=False, server_default="UNKNOWN"),
    )
    op.add_column(
        "source_stream",
        sa.Column(
            "allowed_hosts", postgresql.ARRAY(sa.String(253)), nullable=False, server_default="{}"
        ),
    )
    op.add_column("source_stream", sa.Column("config_sha256", sa.String(64)))
    op.add_column(
        "source_stream",
        sa.Column("discovery_method", sa.String(40), nullable=False, server_default="LEGACY"),
    )
    op.add_column("source_stream", sa.Column("failure_reason", sa.String(500)))
    op.execute(
        "UPDATE source_stream SET allowed_hosts=ARRAY[authorization_boundary] "
        "WHERE cardinality(allowed_hosts)=0"
    )
    op.create_check_constraint(
        "ck_source_stream_status",
        "source_stream",
        "status IN ('QUALIFIED','ACTIVE','PAUSED','REVOKED','PROBING','READY','PROBE_FAILED')",
    )
    op.create_check_constraint(
        "ck_source_stream_type",
        "source_stream",
        "stream_type IN ('UNKNOWN','RSS_ATOM','SITEMAP','JSON_API','DIRECT_PDF','LIST_DETAIL')",
    )
    op.create_check_constraint(
        "ck_source_stream_personal_hash",
        "source_stream",
        "config_sha256 IS NULL OR config_sha256 ~ '^[0-9a-f]{64}$'",
    )
    op.create_check_constraint(
        "ck_source_stream_allowed_hosts",
        "source_stream",
        "cardinality(allowed_hosts) BETWEEN 1 AND 32",
    )

    op.create_table(
        "stream_probe_run",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column(
            "source_id", _uuid(), sa.ForeignKey("source.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column(
            "stream_id",
            _uuid(),
            sa.ForeignKey("source_stream.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("requested_url", sa.String(2048), nullable=False),
        sa.Column("normalized_url", sa.String(2048), nullable=False),
        sa.Column("normalized_origin", sa.String(2048), nullable=False),
        sa.Column("input_kind", sa.String(30), nullable=False, server_default="UNKNOWN"),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("attempt_count", sa.SmallInteger(), nullable=False, server_default="0"),
        sa.Column("failure_code", sa.String(80)),
        sa.Column("failure_reason", sa.String(500)),
        sa.Column(
            "capture_manifest",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
        ),
        sa.Column("requested_by", _uuid(), nullable=False),
        sa.Column("request_id", sa.String(100), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("duration_ms", sa.Integer()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('QUEUED','RUNNING','SUCCEEDED','FAILED')", name="ck_stream_probe_status"
        ),
        sa.CheckConstraint("attempt_count BETWEEN 0 AND 2", name="ck_stream_probe_attempts"),
        sa.CheckConstraint(
            "duration_ms IS NULL OR duration_ms >= 0", name="ck_stream_probe_duration"
        ),
    )
    op.create_index("ix_stream_probe_pending", "stream_probe_run", ["status", "created_at", "id"])
    op.create_index(
        "uq_stream_probe_active_url",
        "stream_probe_run",
        ["source_id", "normalized_url"],
        unique=True,
        postgresql_where=sa.text("status IN ('QUEUED','RUNNING')"),
    )

    op.create_table(
        "stream_config_version",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column(
            "stream_id",
            _uuid(),
            sa.ForeignKey("source_stream.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "probe_run_id",
            _uuid(),
            sa.ForeignKey("stream_probe_run.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("connector_type", sa.String(30), nullable=False),
        sa.Column("definition_version", sa.String(30), nullable=False),
        sa.Column("schema_version", sa.String(30), nullable=False),
        sa.Column("config", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("config_sha256", sa.String(64), nullable=False),
        sa.Column("discovery_method", sa.String(40), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("stream_id", "config_sha256", name="uq_stream_config_hash"),
        sa.CheckConstraint("config_sha256 ~ '^[0-9a-f]{64}$'", name="ck_stream_config_hash"),
    )
    op.execute(
        "CREATE TRIGGER trg_stream_config_version_append_only BEFORE UPDATE OR DELETE "
        "ON stream_config_version FOR EACH ROW EXECUTE FUNCTION prevent_round09_audit_mutation()"
    )
    op.execute("GRANT SELECT, INSERT, UPDATE ON stream_probe_run TO srbg_api_role")
    op.execute("GRANT SELECT, INSERT ON stream_config_version TO srbg_api_role")
    op.execute("GRANT SELECT, INSERT, UPDATE ON source_stream TO srbg_api_role")
    op.execute(
        "GRANT UPDATE (normalized_origin,runtime_state,desired_enabled,updated_at) "
        "ON source TO srbg_api_role"
    )
    op.execute("GRANT SELECT, INSERT, UPDATE ON stream_probe_run TO srbg_worker_role")
    op.execute("GRANT SELECT, INSERT ON stream_config_version TO srbg_worker_role")
    op.execute("GRANT SELECT, INSERT, UPDATE ON source_stream TO srbg_worker_role")
    op.execute("GRANT UPDATE (runtime_state,updated_at) ON source TO srbg_worker_role")


def downgrade() -> None:
    op.execute(
        "DROP TRIGGER IF EXISTS trg_stream_config_version_append_only ON stream_config_version"
    )
    op.drop_table("stream_config_version")
    op.drop_index("uq_stream_probe_active_url", table_name="stream_probe_run")
    op.drop_index("ix_stream_probe_pending", table_name="stream_probe_run")
    op.drop_table("stream_probe_run")
    op.drop_constraint("ck_source_stream_allowed_hosts", "source_stream", type_="check")
    op.drop_constraint("ck_source_stream_personal_hash", "source_stream", type_="check")
    op.drop_constraint("ck_source_stream_type", "source_stream", type_="check")
    op.drop_constraint("ck_source_stream_status", "source_stream", type_="check")
    op.execute("DELETE FROM source_stream WHERE status IN ('PROBING','READY','PROBE_FAILED')")
    op.create_check_constraint(
        "ck_source_stream_status",
        "source_stream",
        "status IN ('QUALIFIED','ACTIVE','PAUSED','REVOKED')",
    )
    for column in (
        "failure_reason",
        "discovery_method",
        "config_sha256",
        "allowed_hosts",
        "stream_type",
    ):
        op.drop_column("source_stream", column)
    op.drop_index("uq_source_personal_normalized_origin", table_name="source")
    op.drop_column("source", "normalized_origin")
