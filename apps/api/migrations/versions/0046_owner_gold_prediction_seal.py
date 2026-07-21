"""Add append-only Owner Gold prediction seals.

Revision ID: 0046_owner_gold_prediction_seal
Revises: 0045_t12_media_delivery
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0046_owner_gold_prediction_seal"
down_revision = "0045_t12_media_delivery"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "owner_gold_prediction_seal_v2",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("seal_version", sa.String(100), nullable=False),
        sa.Column("corpus_version", sa.String(120), nullable=False),
        sa.Column("rule_version", sa.String(120), nullable=False),
        sa.Column("model_id", sa.String(160), nullable=False),
        sa.Column("prompt_version", sa.String(120), nullable=False),
        sa.Column("schema_version", sa.String(120), nullable=False),
        sa.Column("case_count", sa.Integer(), nullable=False),
        sa.Column("corpus_manifest_sha256", sa.String(64), nullable=False),
        sa.Column("prediction_manifest_sha256", sa.String(64), nullable=False),
        sa.Column("sealed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("prediction_seal_sha256", sa.String(64), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "corpus_version",
            "rule_version",
            "model_id",
            "prompt_version",
            "schema_version",
            name="uq_owner_gold_prediction_seal_version_v2",
        ),
        sa.CheckConstraint("case_count=40", name="ck_owner_gold_prediction_seal_count_v2"),
        sa.CheckConstraint(
            "corpus_manifest_sha256 ~ '^[a-f0-9]{64}$' AND "
            "prediction_manifest_sha256 ~ '^[a-f0-9]{64}$' AND "
            "prediction_seal_sha256 ~ '^[a-f0-9]{64}$'",
            name="ck_owner_gold_prediction_seal_hashes_v2",
        ),
    )
    op.add_column(
        "owner_gold_calibration_v2",
        sa.Column("prediction_seal_sha256", sa.String(64), nullable=True),
    )
    op.create_foreign_key(
        "fk_owner_gold_calibration_prediction_seal_v2",
        "owner_gold_calibration_v2",
        "owner_gold_prediction_seal_v2",
        ["prediction_seal_sha256"],
        ["prediction_seal_sha256"],
        ondelete="RESTRICT",
    )
    op.execute(
        """
        CREATE FUNCTION prevent_owner_gold_prediction_seal_mutation() RETURNS trigger
        LANGUAGE plpgsql AS $$ BEGIN
          RAISE EXCEPTION 'OWNER_GOLD_PREDICTION_SEAL_APPEND_ONLY_FACT';
        END $$
        """
    )
    op.execute(
        "CREATE TRIGGER trg_owner_gold_prediction_seal_v2_append_only "
        "BEFORE UPDATE OR DELETE ON owner_gold_prediction_seal_v2 "
        "FOR EACH ROW EXECUTE FUNCTION prevent_owner_gold_prediction_seal_mutation()"
    )
    op.execute("REVOKE ALL ON TABLE owner_gold_prediction_seal_v2 FROM PUBLIC")
    op.execute(
        "GRANT SELECT,INSERT ON TABLE owner_gold_prediction_seal_v2 TO srbg_api_role"
    )
    op.execute(
        "GRANT SELECT ON TABLE owner_gold_prediction_seal_v2 TO srbg_worker_role"
    )
    op.execute(
        "GRANT SELECT ON TABLE owner_gold_prediction_seal_v2 TO srbg_publication_writer"
    )


def downgrade() -> None:
    bind = op.get_bind()
    has_seal = bind.execute(
        sa.text("SELECT EXISTS(SELECT 1 FROM owner_gold_prediction_seal_v2)")
    ).scalar_one()
    has_bound_fact = bind.execute(
        sa.text(
            "SELECT EXISTS(SELECT 1 FROM owner_gold_calibration_v2 "
            "WHERE prediction_seal_sha256 IS NOT NULL)"
        )
    ).scalar_one()
    if has_seal or has_bound_fact:
        raise RuntimeError("OWNER_GOLD_PREDICTION_SEAL_DOWNGRADE_BLOCKED")
    op.execute(
        "DROP TRIGGER trg_owner_gold_prediction_seal_v2_append_only "
        "ON owner_gold_prediction_seal_v2"
    )
    op.execute("DROP FUNCTION prevent_owner_gold_prediction_seal_mutation()")
    op.drop_constraint(
        "fk_owner_gold_calibration_prediction_seal_v2",
        "owner_gold_calibration_v2",
        type_="foreignkey",
    )
    op.drop_column("owner_gold_calibration_v2", "prediction_seal_sha256")
    op.drop_table("owner_gold_prediction_seal_v2")
