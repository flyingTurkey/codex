# ruff: noqa: E501
"""Durable budgets and global stop for unattended personal runs.

Revision ID: 0031_controlled_personal_runs
Revises: 0030_pers10_role_archive_repair
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0031_controlled_personal_runs"
down_revision = "0030_pers10_role_archive_repair"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _uuid() -> postgresql.UUID:
    return postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.create_table(
        "personal_controlled_run",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("state", sa.String(20), nullable=False),
        sa.Column("request_limit", sa.Integer(), nullable=False, server_default="80"),
        sa.Column("byte_limit", sa.BigInteger(), nullable=False, server_default="157286400"),
        sa.Column("response_limit", sa.BigInteger(), nullable=False, server_default="52428800"),
        sa.Column(
            "ai_cost_limit_microusd", sa.BigInteger(), nullable=False, server_default="1250000"
        ),
        sa.Column("failure_limit", sa.Integer(), nullable=False, server_default="10"),
        sa.Column("failure_rate_bps", sa.Integer(), nullable=False, server_default="3000"),
        sa.Column("failure_rate_min_samples", sa.Integer(), nullable=False, server_default="10"),
        sa.Column("requests_reserved", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("bytes_reserved", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("bytes_settled", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("attempts_settled", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("attempts_failed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("ai_cost_reserved_microusd", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("ai_cost_settled_microusd", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("active_seconds", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("wall_started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("wall_deadline", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_resumed_at", sa.DateTime(timezone=True)),
        sa.Column("stop_reason", sa.String(80)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "state IN ('PREPARING','ARMED','RUNNING','PAUSED','STOPPING','COMPLETED','FAILED')"
        ),
        sa.CheckConstraint(
            "request_limit = 80 AND byte_limit = 157286400 AND response_limit = 52428800"
        ),
        sa.CheckConstraint("ai_cost_limit_microusd = 1250000 AND failure_rate_min_samples = 10"),
        sa.CheckConstraint("requests_reserved>=0 AND bytes_reserved>=0 AND bytes_settled>=0"),
    )
    op.create_index(
        "uq_personal_controlled_run_active",
        "personal_controlled_run",
        [sa.text("(1)")],
        unique=True,
        postgresql_where=sa.text("state IN ('PREPARING','ARMED','RUNNING','PAUSED','STOPPING')"),
    )
    op.create_table(
        "personal_controlled_run_source",
        sa.Column(
            "run_id",
            _uuid(),
            sa.ForeignKey("personal_controlled_run.id", ondelete="RESTRICT"),
            primary_key=True,
        ),
        sa.Column(
            "source_id", _uuid(), sa.ForeignKey("source.id", ondelete="RESTRICT"), primary_key=True
        ),
        sa.Column("seed_url", sa.String(2048), nullable=False),
        sa.Column("expected_host", sa.String(253), nullable=False),
        sa.Column("path_prefix", sa.String(2048), nullable=False),
        sa.Column("last_request_at", sa.DateTime(timezone=True)),
        sa.Column("last_cycle_at", sa.DateTime(timezone=True)),
        sa.Column("state", sa.String(20), nullable=False, server_default="PENDING"),
        sa.CheckConstraint("state IN ('PENDING','ACTIVE','PAUSED','FAILED','COMPLETED')"),
    )
    op.create_table(
        "personal_controlled_http_attempt",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column(
            "run_id",
            _uuid(),
            sa.ForeignKey("personal_controlled_run.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("source_id", _uuid(), sa.ForeignKey("source.id", ondelete="RESTRICT")),
        sa.Column("purpose", sa.String(20), nullable=False),
        sa.Column("url_sha256", sa.String(64), nullable=False),
        sa.Column("host", sa.String(253), nullable=False),
        sa.Column("reserved_bytes", sa.BigInteger(), nullable=False),
        sa.Column("response_bytes", sa.BigInteger()),
        sa.Column("outcome", sa.String(20), nullable=False, server_default="RESERVED"),
        sa.Column("failure_code", sa.String(80)),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("settled_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("purpose IN ('ROBOTS','PROBE','FETCH','AI')"),
        sa.CheckConstraint("outcome IN ('RESERVED','SUCCEEDED','FAILED','CANCELLED')"),
        sa.CheckConstraint("reserved_bytes>=0 AND (response_bytes IS NULL OR response_bytes>=0)"),
    )
    op.add_column(
        "stream_probe_run",
        sa.Column(
            "controlled_run_id",
            _uuid(),
            sa.ForeignKey("personal_controlled_run.id", ondelete="RESTRICT"),
        ),
    )
    op.add_column(
        "fetch_run",
        sa.Column(
            "controlled_run_id",
            _uuid(),
            sa.ForeignKey("personal_controlled_run.id", ondelete="RESTRICT"),
        ),
    )
    op.add_column(
        "ai_pipeline_run",
        sa.Column(
            "controlled_run_id",
            _uuid(),
            sa.ForeignKey("personal_controlled_run.id", ondelete="RESTRICT"),
        ),
    )
    op.execute(
        "REVOKE ALL ON personal_controlled_run,personal_controlled_run_source,personal_controlled_http_attempt FROM PUBLIC"
    )
    op.execute(_RESERVE_FUNCTION)
    op.execute(_SETTLE_FUNCTION)
    op.execute(
        "REVOKE ALL ON FUNCTION reserve_personal_controlled_http_attempt(uuid,uuid,uuid,text,text,text,text,bigint,timestamptz) FROM PUBLIC"
    )
    op.execute(
        "REVOKE ALL ON FUNCTION settle_personal_controlled_http_attempt(uuid,bigint,boolean,text,timestamptz) FROM PUBLIC"
    )
    op.execute(
        "GRANT EXECUTE ON FUNCTION reserve_personal_controlled_http_attempt(uuid,uuid,uuid,text,text,text,text,bigint,timestamptz),settle_personal_controlled_http_attempt(uuid,bigint,boolean,text,timestamptz) TO srbg_worker_role"
    )


_RESERVE_FUNCTION = r"""
CREATE FUNCTION reserve_personal_controlled_http_attempt(p_attempt uuid,p_run uuid,p_source uuid,p_purpose text,p_url_sha text,p_host text,p_path text,p_max_bytes bigint,p_now timestamptz)
RETURNS bigint LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,public AS $$
DECLARE r personal_controlled_run%ROWTYPE; allowance bigint;
BEGIN
 SELECT * INTO r FROM personal_controlled_run WHERE id=p_run FOR UPDATE;
 IF r.state<>'RUNNING' OR p_now>=r.wall_deadline THEN RAISE EXCEPTION 'CONTROLLED_RUN_NOT_RUNNING'; END IF;
 IF r.requests_reserved>=r.request_limit THEN RAISE EXCEPTION 'CONTROLLED_RUN_REQUEST_LIMIT'; END IF;
 allowance:=least(p_max_bytes,r.response_limit,r.byte_limit-r.bytes_settled-r.bytes_reserved);
 IF allowance<=0 THEN RAISE EXCEPTION 'CONTROLLED_RUN_BYTE_LIMIT'; END IF;
 IF p_purpose<>'AI' AND NOT EXISTS(SELECT 1 FROM personal_controlled_run_source s WHERE s.run_id=p_run AND s.source_id=p_source AND s.expected_host=p_host AND s.state IN ('PENDING','ACTIVE')) THEN RAISE EXCEPTION 'CONTROLLED_RUN_SOURCE_DENIED'; END IF;
 IF p_purpose<>'AI' AND NOT EXISTS(
   SELECT 1 FROM personal_controlled_run_source s
    WHERE s.run_id=p_run AND s.source_id=p_source
      AND (p_path=regexp_replace(s.path_prefix,'/$','') OR p_path LIKE regexp_replace(s.path_prefix,'/$','')||'/%' OR (p_purpose='ROBOTS' AND p_path='/robots.txt'))
 ) THEN RAISE EXCEPTION 'CONTROLLED_RUN_PATH_DENIED'; END IF;
 IF EXISTS(SELECT 1 FROM personal_controlled_http_attempt a WHERE a.run_id=p_run AND a.host=p_host AND a.started_at>p_now-interval '1 minute') THEN RAISE EXCEPTION 'CONTROLLED_RUN_DOMAIN_RATE_LIMIT'; END IF;
 INSERT INTO personal_controlled_http_attempt(id,run_id,source_id,purpose,url_sha256,host,reserved_bytes,started_at) VALUES(p_attempt,p_run,p_source,p_purpose,p_url_sha,p_host,allowance,p_now);
 UPDATE personal_controlled_run SET requests_reserved=requests_reserved+1,bytes_reserved=bytes_reserved+allowance,updated_at=p_now WHERE id=p_run;
 RETURN allowance;
END $$;
"""

_SETTLE_FUNCTION = r"""
CREATE FUNCTION settle_personal_controlled_http_attempt(p_attempt uuid,p_bytes bigint,p_failed boolean,p_code text,p_now timestamptz)
RETURNS text LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,public AS $$
DECLARE a personal_controlled_http_attempt%ROWTYPE; new_state text;
BEGIN
 SELECT * INTO a FROM personal_controlled_http_attempt WHERE id=p_attempt FOR UPDATE;
 IF a.outcome<>'RESERVED' OR p_bytes<0 OR p_bytes>a.reserved_bytes THEN RAISE EXCEPTION 'CONTROLLED_RUN_INVALID_SETTLEMENT'; END IF;
 UPDATE personal_controlled_http_attempt SET response_bytes=p_bytes,outcome=CASE WHEN p_failed THEN 'FAILED' ELSE 'SUCCEEDED' END,failure_code=CASE WHEN p_failed THEN p_code END,settled_at=p_now WHERE id=p_attempt;
 UPDATE personal_controlled_run SET bytes_reserved=bytes_reserved-a.reserved_bytes,bytes_settled=bytes_settled+p_bytes,attempts_settled=attempts_settled+1,attempts_failed=attempts_failed+CASE WHEN p_failed THEN 1 ELSE 0 END,updated_at=p_now WHERE id=a.run_id;
 UPDATE personal_controlled_run SET state='STOPPING',stop_reason=CASE WHEN attempts_failed>=failure_limit THEN 'FAILURE_LIMIT' ELSE 'FAILURE_RATE' END,updated_at=p_now WHERE id=a.run_id AND state='RUNNING' AND (attempts_failed>=failure_limit OR (attempts_settled>=failure_rate_min_samples AND attempts_failed*10000>=attempts_settled*failure_rate_bps));
 SELECT state INTO new_state FROM personal_controlled_run WHERE id=a.run_id;
 RETURN new_state;
END $$;
"""


def downgrade() -> None:
    connection = op.get_bind()
    if connection.scalar(sa.text("SELECT EXISTS(SELECT 1 FROM personal_controlled_run)")):
        raise RuntimeError("CONTROLLED_RUN_DOWNGRADE_BLOCKED")
    op.execute(
        "DROP FUNCTION settle_personal_controlled_http_attempt(uuid,bigint,boolean,text,timestamptz)"
    )
    op.execute(
        "DROP FUNCTION reserve_personal_controlled_http_attempt(uuid,uuid,uuid,text,text,text,text,bigint,timestamptz)"
    )
    op.drop_column("ai_pipeline_run", "controlled_run_id")
    op.drop_column("fetch_run", "controlled_run_id")
    op.drop_column("stream_probe_run", "controlled_run_id")
    op.drop_table("personal_controlled_http_attempt")
    op.drop_table("personal_controlled_run_source")
    op.drop_index("uq_personal_controlled_run_active", table_name="personal_controlled_run")
    op.drop_table("personal_controlled_run")
