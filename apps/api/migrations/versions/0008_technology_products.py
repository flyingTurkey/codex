"""Round 07 governed software, IoT, low-altitude, and AI products.

Revision ID: 0008_technology_products
Revises: 0007_papers
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0008_technology_products"
down_revision = "0007_papers"
branch_labels = None
depends_on = None

ROUND07_TABLES = (
    "technology_vendor",
    "technology_product",
    "technology_product_model",
    "technology_product_version",
    "technology_product_profile",
    "technology_product_capability",
    "technology_product_taxonomy",
    "product_normalization_candidate",
)

PRODUCT_TYPES = (
    "SOFTWARE_PRODUCT",
    "IOT_PRODUCT",
    "LOW_ALTITUDE_EQUIPMENT",
    "AI_EQUIPMENT",
)


def _uuid() -> postgresql.UUID:
    return postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.drop_constraint("ck_round06_item_type", "intelligence_item", type_="check")
    op.create_check_constraint(
        "ck_round07_item_type",
        "intelligence_item",
        "item_type IN ('DIGITAL_CASE','JOURNAL_PAPER','SOFTWARE_PRODUCT','IOT_PRODUCT',"
        "'LOW_ALTITUDE_EQUIPMENT','AI_EQUIPMENT','SAFETY_REGULATION','SAFETY_CASE')",
    )
    _create_product_tables()
    _grant_permissions()


def _create_product_tables() -> None:
    op.create_table(
        "technology_vendor",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("name", sa.String(300), nullable=False),
        sa.Column("normalized_name", sa.String(300), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "technology_product",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column(
            "vendor_id",
            _uuid(),
            sa.ForeignKey("technology_vendor.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("name", sa.String(300), nullable=False),
        sa.Column("normalized_name", sa.String(300), nullable=False),
        sa.Column("product_kind", sa.String(100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("vendor_id", "normalized_name", name="uq_technology_product_identity"),
    )
    op.create_table(
        "technology_product_model",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column(
            "product_id",
            _uuid(),
            sa.ForeignKey("technology_product.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("model_no", sa.String(200)),
        sa.Column("normalized_model_no", sa.String(200), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "product_id", "normalized_model_no", name="uq_technology_model_identity"
        ),
    )
    op.create_table(
        "technology_product_version",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column(
            "model_id",
            _uuid(),
            sa.ForeignKey("technology_product_model.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("version", sa.String(200)),
        sa.Column("normalized_version", sa.String(200), nullable=False, server_default=""),
        sa.Column("released_at", sa.DateTime(timezone=True)),
        sa.Column(
            "supersedes_version_id",
            _uuid(),
            sa.ForeignKey("technology_product_version.id", ondelete="RESTRICT"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "model_id", "normalized_version", name="uq_technology_version_identity"
        ),
    )
    op.create_table(
        "technology_product_profile",
        sa.Column(
            "item_id",
            _uuid(),
            sa.ForeignKey("intelligence_item.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "version_id",
            _uuid(),
            sa.ForeignKey("technology_product_version.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("item_type", sa.String(40), nullable=False),
        sa.Column("evidence_level", sa.String(40), nullable=False, server_default="UNKNOWN"),
        sa.Column("permit_status", sa.String(20), nullable=False, server_default="UNKNOWN"),
        sa.Column("maturity_level", sa.String(40), nullable=False, server_default="UNKNOWN"),
        sa.Column("platform_type", sa.String(100)),
        sa.Column("equipment_form", sa.String(100)),
        sa.Column(
            "interfaces", postgresql.ARRAY(sa.String(200)), nullable=False, server_default="{}"
        ),
        sa.Column(
            "deployment_modes",
            postgresql.ARRAY(sa.String(100)),
            nullable=False,
            server_default="{}",
        ),
        sa.Column(
            "connectivity", postgresql.ARRAY(sa.String(100)), nullable=False, server_default="{}"
        ),
        sa.Column(
            "payload_types", postgresql.ARRAY(sa.String(100)), nullable=False, server_default="{}"
        ),
        sa.Column(
            "ai_tasks", postgresql.ARRAY(sa.String(100)), nullable=False, server_default="{}"
        ),
        sa.Column(
            "limitations", postgresql.ARRAY(sa.String(500)), nullable=False, server_default="{}"
        ),
        sa.Column("production_validation", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("image_downloaded", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "item_type IN ('SOFTWARE_PRODUCT','IOT_PRODUCT',"
            "'LOW_ALTITUDE_EQUIPMENT','AI_EQUIPMENT')",
            name="ck_technology_profile_item_type",
        ),
        sa.CheckConstraint(
            "permit_status IN ('VERIFIED','NOT_REQUIRED','UNKNOWN')",
            name="ck_technology_profile_permit",
        ),
        sa.CheckConstraint("image_downloaded = false", name="ck_technology_no_vendor_image"),
    )
    op.create_table(
        "technology_product_capability",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column(
            "item_id",
            _uuid(),
            sa.ForeignKey("technology_product_profile.item_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(30), nullable=False),
        sa.Column("statement", sa.String(1000), nullable=False),
        sa.Column("attribution", sa.String(300), nullable=False),
        sa.Column(
            "claim_id", _uuid(), sa.ForeignKey("claim.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column("evidence_ids", postgresql.ARRAY(_uuid()), nullable=False),
        sa.Column(
            "independent_evidence_ids",
            postgresql.ARRAY(_uuid()),
            nullable=False,
            server_default="{}",
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "kind IN ('PROMOTIONAL_CLAIM','VERIFIED_CAPABILITY')",
            name="ck_technology_capability_kind",
        ),
        sa.CheckConstraint(
            "cardinality(evidence_ids) > 0", name="ck_technology_capability_evidence"
        ),
        sa.CheckConstraint(
            "kind = 'PROMOTIONAL_CLAIM' OR cardinality(independent_evidence_ids) > 0",
            name="ck_technology_verified_independent_evidence",
        ),
        sa.CheckConstraint(
            "kind = 'VERIFIED_CAPABILITY' OR cardinality(independent_evidence_ids) = 0",
            name="ck_technology_claim_not_verified",
        ),
    )
    op.create_table(
        "technology_product_taxonomy",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column(
            "item_id",
            _uuid(),
            sa.ForeignKey("technology_product_profile.item_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("dimension", sa.String(40), nullable=False),
        sa.Column("code", sa.String(100), nullable=False),
        sa.Column(
            "claim_id", _uuid(), sa.ForeignKey("claim.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.UniqueConstraint("item_id", "dimension", "code", name="uq_technology_taxonomy"),
        sa.CheckConstraint(
            "dimension IN ('ENGINEERING_DOMAIN','APPLICATION_SCENARIO','TECHNOLOGY_TAG')",
            name="ck_technology_taxonomy_dimension",
        ),
    )
    op.create_index(
        "ix_technology_taxonomy_filter",
        "technology_product_taxonomy",
        ["dimension", "code", "item_id"],
    )
    op.create_table(
        "product_normalization_candidate",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column(
            "incoming_version_id",
            _uuid(),
            sa.ForeignKey("technology_product_version.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "candidate_version_id",
            _uuid(),
            sa.ForeignKey("technology_product_version.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("candidate_type", sa.String(30), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="PENDING_REVIEW"),
        sa.Column("decision", sa.String(30)),
        sa.Column("reason", sa.String(1000)),
        sa.Column("reviewed_by", _uuid()),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "candidate_type IN ('MODEL_ALIAS','VERSION_SUCCESSOR','POSSIBLE_DUPLICATE')",
            name="ck_product_normalization_candidate_type",
        ),
        sa.CheckConstraint(
            "status IN ('PENDING_REVIEW','ACCEPTED','REJECTED')",
            name="ck_product_normalization_status",
        ),
        sa.CheckConstraint(
            "decision IS NULL OR decision IN ('MERGE_ALIAS','LINK_AS_NEW_VERSION','KEEP_DISTINCT')",
            name="ck_product_normalization_decision",
        ),
    )


def _grant_permissions() -> None:
    tables = ", ".join(ROUND07_TABLES)
    op.execute(f"GRANT SELECT ON {tables} TO srbg_runtime, srbg_publication_writer")
    op.execute(
        "GRANT INSERT ON technology_vendor, technology_product, technology_product_model, "
        "technology_product_version, technology_product_profile, technology_product_capability, "
        "technology_product_taxonomy, product_normalization_candidate TO srbg_runtime"
    )
    op.execute(f"GRANT INSERT, UPDATE ON {tables} TO srbg_publication_writer")


def downgrade() -> None:
    connection = op.get_bind()
    if connection.scalar(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM intelligence_item "
            "WHERE item_type = ANY(CAST(:product_types AS text[])))"
        ),
        {"product_types": list(PRODUCT_TYPES)},
    ):
        raise RuntimeError("refusing Round07 downgrade while technology product data exists")
    for table in reversed(ROUND07_TABLES):
        op.drop_table(table)
    op.drop_constraint("ck_round07_item_type", "intelligence_item", type_="check")
    op.create_check_constraint(
        "ck_round06_item_type",
        "intelligence_item",
        "item_type IN ('DIGITAL_CASE','JOURNAL_PAPER','SAFETY_REGULATION','SAFETY_CASE')",
    )
