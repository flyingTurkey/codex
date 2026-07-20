"""Add append-only engineering closeout campaign facts.

Revision ID: 0037_engineering_closeout_campaign
Revises: 0036_ai_content_result_lifecycle
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0037_engineering_closeout_campaign"
down_revision = "0036_ai_content_result_lifecycle"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
_ARCHIVE_PREFLIGHT_FUNCTION = "verify_engineering_closeout_archive_preflight()"
_AUDIT_PREFLIGHT_FUNCTION = "verify_engineering_closeout_audit_anchor()"


def _uuid() -> postgresql.UUID:
    return postgresql.UUID(as_uuid=True)


def _json() -> postgresql.JSONB:
    return postgresql.JSONB(astext_type=sa.Text())


def upgrade() -> None:
    op.execute("GRANT SELECT ON alembic_version TO srbg_api_role")
    op.execute("GRANT SELECT ON source_admission_assessment_v2 TO srbg_worker_role")
    op.execute("GRANT INSERT ON source_admission_assessment_v2 TO srbg_api_role")
    op.create_table(
        "engineering_closeout_campaign_v2",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("acceptance_profile", sa.String(40), nullable=False),
        sa.Column("baseline_commit", sa.String(40), nullable=False),
        sa.Column("migration_head", sa.String(80), nullable=False),
        sa.Column("environment", sa.String(40), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "acceptance_profile='ENGINEERING_CLOSEOUT'",
            name="ck_engineering_campaign_profile_v2",
        ),
        sa.CheckConstraint(
            "baseline_commit ~ '^[a-f0-9]{40}$'",
            name="ck_engineering_campaign_commit_v2",
        ),
    )
    op.create_table(
        "engineering_closeout_campaign_event_v2",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column(
            "campaign_id",
            _uuid(),
            sa.ForeignKey("engineering_closeout_campaign_v2.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("event_type", sa.String(60), nullable=False),
        sa.Column("payload", _json(), nullable=False),
        sa.Column("payload_sha256", sa.String(64), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "campaign_id",
            "event_type",
            "payload_sha256",
            name="uq_engineering_campaign_event_fact_v2",
        ),
        sa.CheckConstraint(
            "event_type IN ('PREPARED','STARTED','EVIDENCE_EXPORTED','FINALIZED','RESTORED',"
            "'HISTORICAL_BUDGET_RECONCILED','FAULT_TRANSIENT_INJECTED',"
            "'FAULT_TRANSIENT_RECOVERED','FAULT_PERMANENT_INJECTED',"
            "'FAULT_PERMANENT_OBSERVED','FAULT_DUPLICATE_SIDE_EFFECT',"
            "'FAULT_STALE_VERSION_RECOVERY','FAULT_PERMANENT_RETRY')",
            name="ck_engineering_campaign_event_type_v2",
        ),
        sa.CheckConstraint(
            "payload_sha256 ~ '^[a-f0-9]{64}$'",
            name="ck_engineering_campaign_event_hash_v2",
        ),
    )
    op.execute(
        """
        CREATE FUNCTION prevent_engineering_campaign_fact_mutation() RETURNS trigger
        LANGUAGE plpgsql AS $$ BEGIN
          RAISE EXCEPTION 'ENGINEERING_CAMPAIGN_APPEND_ONLY_FACT';
        END $$
        """
    )
    for table in (
        "engineering_closeout_campaign_v2",
        "engineering_closeout_campaign_event_v2",
    ):
        op.execute(
            f"CREATE TRIGGER trg_{table}_append_only BEFORE UPDATE OR DELETE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION prevent_engineering_campaign_fact_mutation()"
        )
        op.execute(f"REVOKE ALL ON TABLE {table} FROM PUBLIC")
        op.execute(f"GRANT SELECT,INSERT ON TABLE {table} TO srbg_api_role")
    op.execute(
        "GRANT SELECT,INSERT ON engineering_closeout_campaign_v2,"
        "engineering_closeout_campaign_event_v2 TO srbg_worker_role"
    )
    op.execute(
        "GRANT SELECT,INSERT ON engineering_closeout_campaign_v2,"
        "engineering_closeout_campaign_event_v2 TO srbg_publication_writer"
    )
    op.execute(
        """
        CREATE FUNCTION verify_engineering_closeout_archive_preflight() RETURNS boolean
        LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog,public AS $$
          SELECT NOT EXISTS(
            SELECT 1 FROM legacy_governance_archive.legacy_governance_archive_record r
             WHERE r.row_sha256<>encode(digest(convert_to(jsonb_build_object(
               'entity_type',r.entity_type,'original_id',r.original_id,
               'source_id',r.source_id,'payload',r.normalized_payload
             )::text,'UTF8'),'sha256'),'hex')
          ) AND NOT EXISTS(
            SELECT 1 FROM legacy_governance_archive.legacy_governance_archive_manifest m
            LEFT JOIN LATERAL(
              SELECT count(*) actual_count,encode(digest(convert_to(
                count(*)::text||E'\n'||COALESCE(string_agg(
                  r.original_id||':'||r.row_sha256,E'\n' ORDER BY r.original_id
                ),''),'UTF8'),'sha256'),'hex') actual_hash
                FROM legacy_governance_archive.legacy_governance_archive_record r
               WHERE r.entity_type=m.entity_type
            ) a ON true
           WHERE m.original_count<>m.archive_count
              OR m.archive_count<>a.actual_count
              OR m.aggregate_sha256<>a.actual_hash
          )
        $$
        """
    )
    op.execute(f"REVOKE ALL ON FUNCTION {_ARCHIVE_PREFLIGHT_FUNCTION} FROM PUBLIC")
    op.execute(
        f"GRANT EXECUTE ON FUNCTION {_ARCHIVE_PREFLIGHT_FUNCTION} TO srbg_api_role"
    )
    op.execute(
        "CREATE FUNCTION verify_engineering_closeout_audit_anchor() RETURNS boolean "
        "LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog,public AS $$ "
        "SELECT EXISTS(SELECT 1 FROM audit_chain_anchor WHERE entry_hash IS NOT NULL "
        "AND anchor_object_key IS NOT NULL) $$"
    )
    op.execute(f"REVOKE ALL ON FUNCTION {_AUDIT_PREFLIGHT_FUNCTION} FROM PUBLIC")
    op.execute(
        f"GRANT EXECUTE ON FUNCTION {_AUDIT_PREFLIGHT_FUNCTION} TO srbg_api_role"
    )


def downgrade() -> None:
    bind = op.get_bind()
    durable = bind.execute(
        sa.text(
            "SELECT EXISTS(SELECT 1 FROM engineering_closeout_campaign_v2 "
            "UNION ALL SELECT 1 FROM engineering_closeout_campaign_event_v2)"
        )
    ).scalar_one()
    if durable:
        raise RuntimeError(
            "ENGINEERING_CLOSEOUT_CAMPAIGN_DOWNGRADE_BLOCKED: durable campaign facts exist"
        )
    op.execute(f"DROP FUNCTION {_AUDIT_PREFLIGHT_FUNCTION}")
    op.execute(f"DROP FUNCTION {_ARCHIVE_PREFLIGHT_FUNCTION}")
    for table in (
        "engineering_closeout_campaign_event_v2",
        "engineering_closeout_campaign_v2",
    ):
        op.execute(f"DROP TRIGGER trg_{table}_append_only ON {table}")
    op.execute("DROP FUNCTION prevent_engineering_campaign_fact_mutation()")
    op.drop_table("engineering_closeout_campaign_event_v2")
    op.drop_table("engineering_closeout_campaign_v2")
