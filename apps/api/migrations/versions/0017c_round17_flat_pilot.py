"""Round 17 signed-local flat pilot authority and single-expert reference facts."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0017c_round17_flat_pilot"
down_revision = "0017b_round17_pilot"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
SINGLE_EXPERT_MODEL = "LEO_SINGLE_EXPERT_REFERENCE_SET"


def _uuid() -> postgresql.UUID:
    return postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.add_column(
        "round17_staff_binding",
        sa.Column(
            "authority_mode",
            sa.String(30),
            nullable=False,
            server_default="OIDC",
        ),
    )
    op.drop_constraint(
        "ck_round17_staff_oidc_hashes", "round17_staff_binding", type_="check"
    )
    op.alter_column("round17_staff_binding", "oidc_issuer_sha256", nullable=True)
    op.alter_column("round17_staff_binding", "oidc_subject_sha256", nullable=True)
    op.drop_constraint(
        "ck_round17_staff_not_local", "round17_staff_binding", type_="check"
    )
    op.create_check_constraint(
        "ck_round17_staff_authority_mode",
        "round17_staff_binding",
        "authority_mode IN ('OIDC','SIGNED_LOCAL_PILOT')",
    )
    op.create_check_constraint(
        "ck_round17_staff_identity_assurance",
        "round17_staff_binding",
        "(authority_mode='OIDC' AND local_identity=false) OR "
        "(authority_mode='SIGNED_LOCAL_PILOT' AND local_identity=true "
        "AND display_name='LEO' AND responsibility='SOURCE_APPROVER')",
    )
    op.create_check_constraint(
        "ck_round17_staff_identity_hashes",
        "round17_staff_binding",
        "(authority_mode='OIDC' AND "
        "oidc_issuer_sha256 ~ '^[0-9a-f]{64}$' AND "
        "oidc_subject_sha256 ~ '^[0-9a-f]{64}$') OR "
        "(authority_mode='SIGNED_LOCAL_PILOT' AND "
        "oidc_issuer_sha256 IS NULL AND oidc_subject_sha256 IS NULL)",
    )

    op.create_table(
        "round17_signed_approval",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("approval_type", sa.String(40), nullable=False),
        sa.Column("authority_mode", sa.String(30), nullable=False),
        sa.Column("approval_document", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("approval_document_sha256", sa.String(64), nullable=False),
        sa.Column("approval_signature", sa.String(88), nullable=False),
        sa.Column("signer_public_key_sha256", sa.String(64), nullable=False),
        sa.Column("approved_by", _uuid(), nullable=False),
        sa.Column("approved_by_display_name", sa.String(200), nullable=False),
        sa.Column("approved_by_responsibility", sa.String(40), nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["approved_by", "approved_by_display_name", "approved_by_responsibility"],
            [
                "round17_staff_binding.actor_id",
                "round17_staff_binding.display_name",
                "round17_staff_binding.responsibility",
            ],
            ondelete="RESTRICT",
            name="fk_round17_signed_approval_staff",
        ),
        sa.CheckConstraint(
            "approval_type IN ("
            "'ROUND17_ATOMIC_AUTHORITY','WINDOW_START')",
            name="ck_round17_signed_approval_type",
        ),
        sa.CheckConstraint(
            "authority_mode='SIGNED_LOCAL_PILOT' AND "
            "approved_by_display_name='LEO' AND "
            "approved_by_responsibility='SOURCE_APPROVER'",
            name="ck_round17_signed_approval_authority",
        ),
        sa.CheckConstraint(
            "approval_document_sha256 ~ '^[0-9a-f]{64}$' AND "
            "signer_public_key_sha256 ~ '^[0-9a-f]{64}$' AND "
            "approval_signature ~ '^[A-Za-z0-9+/]{86}==$'",
            name="ck_round17_signed_approval_crypto",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(approval_document)='object' AND "
            "approval_document->>'schema_version'='round17-authority-v1'",
            name="ck_round17_signed_approval_document",
        ),
        sa.CheckConstraint(
            "valid_from <= created_at AND valid_until > created_at",
            name="ck_round17_signed_approval_validity",
        ),
        sa.UniqueConstraint(
            "approval_type",
            "approval_document_sha256",
            name="uq_round17_signed_approval_document",
        ),
    )

    op.create_table(
        "round17_reference_annotation",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("reference_version", sa.String(80), nullable=False),
        sa.Column("reference_kind", sa.String(30), nullable=False),
        sa.Column("sample_id", _uuid(), nullable=False),
        sa.Column(
            "source_id",
            _uuid(),
            sa.ForeignKey("source.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("content_sha256", sa.String(64), nullable=False),
        sa.Column("evidence_ref", sa.String(500), nullable=False),
        sa.Column("label_code", sa.String(100), nullable=False),
        sa.Column("label_sha256", sa.String(64), nullable=False),
        sa.Column("annotator_id", _uuid(), nullable=False),
        sa.Column("annotator_display_name", sa.String(200), nullable=False),
        sa.Column("annotator_responsibility", sa.String(40), nullable=False),
        sa.Column("annotation_model", sa.String(50), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["annotator_id", "annotator_display_name", "annotator_responsibility"],
            [
                "round17_staff_binding.actor_id",
                "round17_staff_binding.display_name",
                "round17_staff_binding.responsibility",
            ],
            ondelete="RESTRICT",
            name="fk_round17_reference_annotator",
        ),
        sa.CheckConstraint(
            f"annotation_model='{SINGLE_EXPERT_MODEL}' AND "
            "annotator_display_name='LEO' AND "
            "annotator_responsibility='SOURCE_APPROVER'",
            name="ck_round17_reference_annotation_model",
        ),
        sa.CheckConstraint(
            "reference_kind IN ('DOCUMENT','DUPLICATE_PAIR','EVENT_CLUSTER',"
            "'CLAIM_EVIDENCE','SEARCH_QUESTION')",
            name="ck_round17_reference_kind",
        ),
        sa.CheckConstraint(
            "content_sha256 ~ '^[0-9a-f]{64}$' AND "
            "label_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_round17_reference_hashes",
        ),
        sa.UniqueConstraint(
            "reference_version",
            "reference_kind",
            "sample_id",
            name="uq_round17_reference_sample",
        ),
    )

    op.execute(
        "CREATE TRIGGER trg_round17_signed_approval_immutable "
        "BEFORE UPDATE OR DELETE ON round17_signed_approval "
        "FOR EACH ROW EXECUTE FUNCTION reject_immutable_source_vault_change()"
    )
    op.execute(
        "CREATE TRIGGER trg_round17_reference_annotation_immutable "
        "BEFORE UPDATE OR DELETE ON round17_reference_annotation "
        "FOR EACH ROW EXECUTE FUNCTION reject_immutable_source_vault_change()"
    )

    op.execute("REVOKE ALL ON round17_signed_approval FROM PUBLIC")
    op.execute("REVOKE ALL ON round17_signed_approval FROM srbg_api_role")
    op.execute("REVOKE ALL ON round17_signed_approval FROM srbg_worker_role")
    op.execute("REVOKE ALL ON round17_signed_approval FROM srbg_admin_role")
    op.execute("REVOKE ALL ON round17_reference_annotation FROM PUBLIC")
    op.execute("REVOKE ALL ON round17_reference_annotation FROM srbg_api_role")
    op.execute("REVOKE ALL ON round17_reference_annotation FROM srbg_worker_role")
    op.execute("REVOKE ALL ON round17_reference_annotation FROM srbg_admin_role")
    op.execute("GRANT SELECT ON round17_signed_approval TO srbg_api_role")
    op.execute("GRANT SELECT ON round17_reference_annotation TO srbg_api_role")


def downgrade() -> None:
    op.execute(
        """DO $$
        BEGIN
          IF EXISTS (SELECT 1 FROM round17_signed_approval)
             OR EXISTS (SELECT 1 FROM round17_reference_annotation)
             OR EXISTS (
               SELECT 1 FROM round17_staff_binding
                WHERE authority_mode='SIGNED_LOCAL_PILOT'
             ) THEN
            RAISE EXCEPTION 'round17 flat-pilot facts exist; destructive downgrade refused';
          END IF;
        END $$"""
    )
    op.execute(
        "DROP TRIGGER IF EXISTS trg_round17_reference_annotation_immutable "
        "ON round17_reference_annotation"
    )
    op.execute(
        "DROP TRIGGER IF EXISTS trg_round17_signed_approval_immutable "
        "ON round17_signed_approval"
    )
    op.drop_table("round17_reference_annotation")
    op.drop_table("round17_signed_approval")
    op.drop_constraint(
        "ck_round17_staff_identity_hashes", "round17_staff_binding", type_="check"
    )
    op.drop_constraint(
        "ck_round17_staff_identity_assurance", "round17_staff_binding", type_="check"
    )
    op.drop_constraint(
        "ck_round17_staff_authority_mode", "round17_staff_binding", type_="check"
    )
    op.drop_column("round17_staff_binding", "authority_mode")
    op.alter_column("round17_staff_binding", "oidc_issuer_sha256", nullable=False)
    op.alter_column("round17_staff_binding", "oidc_subject_sha256", nullable=False)
    op.create_check_constraint(
        "ck_round17_staff_oidc_hashes",
        "round17_staff_binding",
        "oidc_issuer_sha256 ~ '^[0-9a-f]{64}$' AND "
        "oidc_subject_sha256 ~ '^[0-9a-f]{64}$'",
    )
    op.create_check_constraint(
        "ck_round17_staff_not_local",
        "round17_staff_binding",
        "local_identity IS FALSE",
    )
