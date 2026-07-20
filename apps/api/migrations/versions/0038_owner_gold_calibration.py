"""Add append-only Owner Gold calibration facts.

Revision ID: 0038_owner_gold_calibration
Revises: 0037_engineering_closeout_campaign
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0038_owner_gold_calibration"
down_revision = "0037_engineering_closeout_campaign"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _uuid() -> postgresql.UUID:
    return postgresql.UUID(as_uuid=True)


def _json() -> postgresql.JSONB:
    return postgresql.JSONB(astext_type=sa.Text())


def upgrade() -> None:
    op.create_table(
        "owner_gold_calibration_v2",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("fact_version", sa.String(80), nullable=False),
        sa.Column("corpus_version", sa.String(120), nullable=False),
        sa.Column("rule_version", sa.String(120), nullable=False),
        sa.Column("model_id", sa.String(160), nullable=False),
        sa.Column("prompt_version", sa.String(120), nullable=False),
        sa.Column("calibrated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("label_authority", sa.String(40), nullable=False),
        sa.Column("decision", sa.String(20), nullable=False),
        sa.Column("reasons", _json(), nullable=False),
        sa.Column("authorizes_auto_pass", sa.Boolean(), nullable=False),
        sa.Column("auto_pass_threshold_bps", sa.Integer(), nullable=True),
        sa.Column("precision_bps", sa.Integer(), nullable=False),
        sa.Column("recall_bps", sa.Integer(), nullable=False),
        sa.Column("locked_negative_leaks", sa.Integer(), nullable=False),
        sa.Column("slice_metrics", _json(), nullable=False),
        sa.Column("evidence_manifest_sha256", sa.String(64), nullable=False),
        sa.Column("fact_sha256", sa.String(64), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "corpus_version",
            "rule_version",
            "model_id",
            "prompt_version",
            name="uq_owner_gold_calibration_version_v2",
        ),
        sa.CheckConstraint(
            "label_authority='HUMAN_OWNER'",
            name="ck_owner_gold_calibration_authority_v2",
        ),
        sa.CheckConstraint(
            "decision IN ('GO','NO_GO')",
            name="ck_owner_gold_calibration_decision_v2",
        ),
        sa.CheckConstraint(
            "precision_bps BETWEEN 0 AND 10000 AND recall_bps BETWEEN 0 AND 10000",
            name="ck_owner_gold_calibration_metrics_v2",
        ),
        sa.CheckConstraint(
            "locked_negative_leaks >= 0",
            name="ck_owner_gold_calibration_leaks_v2",
        ),
        sa.CheckConstraint(
            "(decision='GO' AND authorizes_auto_pass=true "
            "AND auto_pass_threshold_bps BETWEEN 0 AND 10000 "
            "AND precision_bps>=9000 AND recall_bps>=9000 "
            "AND locked_negative_leaks=0) OR "
            "(decision='NO_GO' AND authorizes_auto_pass=false "
            "AND auto_pass_threshold_bps IS NULL)",
            name="ck_owner_gold_calibration_fail_closed_v2",
        ),
        sa.CheckConstraint(
            "evidence_manifest_sha256 ~ '^[a-f0-9]{64}$' AND fact_sha256 ~ '^[a-f0-9]{64}$'",
            name="ck_owner_gold_calibration_hashes_v2",
        ),
    )
    op.execute(
        """
        CREATE FUNCTION prevent_owner_gold_calibration_mutation() RETURNS trigger
        LANGUAGE plpgsql AS $$ BEGIN
          RAISE EXCEPTION 'OWNER_GOLD_CALIBRATION_APPEND_ONLY_FACT';
        END $$
        """
    )
    op.execute(
        "CREATE TRIGGER trg_owner_gold_calibration_v2_append_only "
        "BEFORE UPDATE OR DELETE ON owner_gold_calibration_v2 "
        "FOR EACH ROW EXECUTE FUNCTION prevent_owner_gold_calibration_mutation()"
    )
    op.execute("REVOKE ALL ON TABLE owner_gold_calibration_v2 FROM PUBLIC")
    op.execute("GRANT SELECT,INSERT ON TABLE owner_gold_calibration_v2 TO srbg_api_role")
    op.execute("GRANT SELECT ON TABLE owner_gold_calibration_v2 TO srbg_worker_role")
    op.execute("GRANT SELECT ON TABLE owner_gold_calibration_v2 TO srbg_publication_writer")


def downgrade() -> None:
    bind = op.get_bind()
    if bind.execute(sa.text("SELECT EXISTS(SELECT 1 FROM owner_gold_calibration_v2)")).scalar_one():
        raise RuntimeError(
            "OWNER_GOLD_CALIBRATION_DOWNGRADE_BLOCKED: durable calibration facts exist"
        )
    op.execute(
        "DROP TRIGGER trg_owner_gold_calibration_v2_append_only ON owner_gold_calibration_v2"
    )
    op.execute("DROP FUNCTION prevent_owner_gold_calibration_mutation()")
    op.drop_table("owner_gold_calibration_v2")
