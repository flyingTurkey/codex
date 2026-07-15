"""Round 05 digital transformation cases, evidence attribution, and relevance.

Revision ID: 0006_digital_cases
Revises: 0005_safety_case_lifecycle
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0006_digital_cases"
down_revision = "0005_safety_case_lifecycle"
branch_labels = None
depends_on = None

ROUND05_TABLES = (
    "digital_case_profile",
    "digital_case_taxonomy",
    "digital_case_entity",
    "digital_case_entity_relation",
    "digital_case_outcome",
    "digital_case_relevance",
)

ROUND05_SOURCE_IDS = (
    UUID("019b0000-0000-7000-8000-000000005501"),
    UUID("019b0000-0000-7000-8000-000000005502"),
)


def _uuid() -> postgresql.UUID:
    return postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    _expand_content_constraints()
    _expand_claim_multiplicity()
    _create_digital_case_tables()
    _seed_candidate_sources()
    _grant_permissions()


def _expand_content_constraints() -> None:
    op.drop_constraint("ck_round04_item_type", "intelligence_item", type_="check")
    op.drop_constraint("ck_round02_item_channel", "intelligence_item", type_="check")
    op.drop_constraint("ck_round04_item_risk", "intelligence_item", type_="check")
    op.drop_constraint("ck_round04_review_risk", "review_task", type_="check")
    op.create_check_constraint(
        "ck_round05_item_type",
        "intelligence_item",
        "item_type IN ('DIGITAL_CASE','SAFETY_REGULATION','SAFETY_CASE')",
    )
    op.create_check_constraint(
        "ck_round05_item_channel",
        "intelligence_item",
        "channel IN ('DIGITAL','SAFETY')",
    )
    op.create_check_constraint(
        "ck_round05_item_risk",
        "intelligence_item",
        "risk_level IN ('R1','R2','R3','R4')",
    )
    op.create_check_constraint(
        "ck_round05_review_risk",
        "review_task",
        "risk_level IN ('R1','R2','R3','R4')",
    )


def _expand_claim_multiplicity() -> None:
    op.drop_constraint("uq_claim_item_version_type", "claim", type_="unique")
    op.create_unique_constraint(
        "uq_claim_item_version_type_subject_predicate",
        "claim",
        ["item_id", "document_version_id", "claim_type", "subject", "predicate"],
    )


def _create_digital_case_tables() -> None:
    jsonb = postgresql.JSONB(astext_type=sa.Text())
    op.create_table(
        "digital_case_profile",
        sa.Column(
            "item_id",
            _uuid(),
            sa.ForeignKey("intelligence_item.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("source_nature", sa.String(40), nullable=False),
        sa.Column("maturity_level", sa.String(40), nullable=False),
        sa.Column("deployment_scale", sa.String(500)),
        sa.Column(
            "maturity_evidence_ids",
            postgresql.ARRAY(_uuid()),
            nullable=False,
            server_default=sa.text("'{}'::uuid[]"),
        ),
        sa.Column("applicability", jsonb, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column(
            "replication_conditions", jsonb, nullable=False, server_default=sa.text("'[]'::jsonb")
        ),
        sa.Column("limitations", jsonb, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("risks", jsonb, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("srbg_relationship", sa.String(500), nullable=False),
        sa.Column("is_sichuan", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "source_nature IN ('GOVERNMENT_CASE_COLLECTION','ENTERPRISE_SELF_REPORT')",
            name="ck_digital_case_source_nature",
        ),
        sa.CheckConstraint(
            "maturity_level IN ('CONCEPT','LAB_PROTOTYPE','ENGINEERING_PROTOTYPE',"
            "'PILOT','SINGLE_PROJECT_PRODUCTION','MULTI_PROJECT_REPLICATION',"
            "'ENTERPRISE_SCALE','UNKNOWN')",
            name="ck_digital_case_maturity",
        ),
    )
    op.create_table(
        "digital_case_taxonomy",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column(
            "item_id",
            _uuid(),
            sa.ForeignKey("digital_case_profile.item_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("facet", sa.String(30), nullable=False),
        sa.Column("code", sa.String(100), nullable=False),
        sa.Column(
            "claim_id", _uuid(), sa.ForeignKey("claim.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("item_id", "facet", "code", name="uq_digital_case_taxonomy"),
        sa.CheckConstraint(
            "facet IN ('ENGINEERING_DOMAIN','LIFECYCLE_STAGE',"
            "'TECHNOLOGY_TAG','APPLICATION_SCENARIO')",
            name="ck_digital_case_taxonomy_facet",
        ),
    )
    op.create_index(
        "ix_digital_case_taxonomy_filter", "digital_case_taxonomy", ["facet", "code", "item_id"]
    )
    op.create_table(
        "digital_case_entity",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("entity_type", sa.String(30), nullable=False),
        sa.Column("name", sa.String(300), nullable=False),
        sa.Column("canonical_key", sa.String(300), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "entity_type IN ('ORGANIZATION','TECHNOLOGY','PROJECT')",
            name="ck_digital_case_entity_type",
        ),
    )
    op.create_table(
        "digital_case_entity_relation",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column(
            "item_id",
            _uuid(),
            sa.ForeignKey("digital_case_profile.item_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "entity_id",
            _uuid(),
            sa.ForeignKey("digital_case_entity.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("relation_type", sa.String(40), nullable=False),
        sa.Column(
            "claim_id", _uuid(), sa.ForeignKey("claim.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column("direct_srbg", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "item_id", "entity_id", "relation_type", name="uq_digital_case_entity_relation"
        ),
        sa.CheckConstraint(
            "relation_type IN ('PUBLISHER','IMPLEMENTER','OWNER','SUPPLIER',"
            "'APPLIED_TECHNOLOGY','APPLIED_PROJECT')",
            name="ck_digital_case_relation_type",
        ),
    )
    op.create_table(
        "digital_case_outcome",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column(
            "item_id",
            _uuid(),
            sa.ForeignKey("digital_case_profile.item_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("statement", sa.String(1000), nullable=False),
        sa.Column("metric_name", sa.String(200)),
        sa.Column("numeric_value", sa.Numeric(30, 8)),
        sa.Column("unit", sa.String(50)),
        sa.Column(
            "attribution_entity_id",
            _uuid(),
            sa.ForeignKey("digital_case_entity.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("outcome_kind", sa.String(20), nullable=False),
        sa.Column(
            "claim_id", _uuid(), sa.ForeignKey("claim.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column("evidence_ids", postgresql.ARRAY(_uuid()), nullable=False),
        sa.Column(
            "independent_evidence_ids",
            postgresql.ARRAY(_uuid()),
            nullable=False,
            server_default=sa.text("'{}'::uuid[]"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "outcome_kind IN ('CLAIMED','VERIFIED')", name="ck_digital_outcome_kind"
        ),
        sa.CheckConstraint("cardinality(evidence_ids) > 0", name="ck_digital_outcome_evidence"),
        sa.CheckConstraint(
            "outcome_kind = 'CLAIMED' OR cardinality(independent_evidence_ids) > 0",
            name="ck_digital_verified_independent_evidence",
        ),
    )
    op.create_table(
        "digital_case_relevance",
        sa.Column(
            "item_id",
            _uuid(),
            sa.ForeignKey("digital_case_profile.item_id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("score", sa.SmallInteger(), nullable=False),
        sa.Column("rule_version", sa.String(50), nullable=False, server_default="relevance-v1.0.0"),
        sa.Column("engineering_points", sa.SmallInteger(), nullable=False),
        sa.Column("sichuan_points", sa.SmallInteger(), nullable=False),
        sa.Column("srbg_direct_points", sa.SmallInteger(), nullable=False),
        sa.Column("factor_claim_ids", postgresql.ARRAY(_uuid()), nullable=False),
        sa.Column("calculated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("score BETWEEN 0 AND 100", name="ck_digital_relevance_score"),
        sa.CheckConstraint(
            "score = engineering_points + sichuan_points + srbg_direct_points",
            name="ck_digital_relevance_sum",
        ),
        sa.CheckConstraint(
            "rule_version = 'relevance-v1.0.0'", name="ck_digital_relevance_version"
        ),
    )
    op.create_index(
        "ix_digital_case_relevance_sort", "digital_case_relevance", ["score", "item_id"]
    )


def _seed_candidate_sources() -> None:
    now = datetime.now(UTC)
    table = sa.table(
        "source",
        sa.column("id", _uuid()),
        sa.column("registry_code", sa.String()),
        sa.column("name", sa.String()),
        sa.column("base_url", sa.String()),
        sa.column("channel", sa.String()),
        sa.column("source_type", sa.String()),
        sa.column("authority_level", sa.String()),
        sa.column("priority", sa.String()),
        sa.column("collection_method", sa.String()),
        sa.column("poll_interval_minutes", sa.Integer()),
        sa.column("owner", sa.String()),
        sa.column("state", sa.String()),
        sa.column("enabled", sa.Boolean()),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    op.bulk_insert(
        table,
        [
            {
                "id": ROUND05_SOURCE_IDS[0],
                "registry_code": "GOV-ROUND05-MOT",
                "name": "交通运输部数字化案例集",
                "base_url": "https://zizhan.mot.gov.cn/",
                "channel": "DIGITAL",
                "source_type": "government",
                "authority_level": "A1",
                "priority": "P1",
                "collection_method": "PDF",
                "poll_interval_minutes": 1440,
                "owner": "source_ops",
                "state": "CANDIDATE",
                "enabled": False,
                "created_at": now,
                "updated_at": now,
            },
            {
                "id": ROUND05_SOURCE_IDS[1],
                "registry_code": "ENT-ROUND05-SHUDAO",
                "name": "蜀道集团企业案例",
                "base_url": "https://www.shudaojt.com/",
                "channel": "DIGITAL",
                "source_type": "enterprise",
                "authority_level": "B2",
                "priority": "P1",
                "collection_method": "PDF",
                "poll_interval_minutes": 1440,
                "owner": "source_ops",
                "state": "CANDIDATE",
                "enabled": False,
                "created_at": now,
                "updated_at": now,
            },
        ],
    )


def _grant_permissions() -> None:
    tables = ", ".join(ROUND05_TABLES)
    op.execute(f"GRANT SELECT ON {tables} TO srbg_runtime, srbg_publication_writer")
    op.execute(
        "GRANT INSERT, UPDATE ON digital_case_profile, digital_case_taxonomy, "
        "digital_case_entity, digital_case_entity_relation, digital_case_outcome, "
        "digital_case_relevance TO srbg_publication_writer"
    )
    op.execute(
        "GRANT INSERT ON digital_case_profile, digital_case_taxonomy, digital_case_entity, "
        "digital_case_entity_relation, digital_case_outcome, digital_case_relevance TO srbg_runtime"
    )


def downgrade() -> None:
    connection = op.get_bind()
    if connection.scalar(
        sa.text("SELECT EXISTS (SELECT 1 FROM intelligence_item WHERE item_type = 'DIGITAL_CASE')")
    ):
        raise RuntimeError("refusing Round05 downgrade while DIGITAL_CASE data exists")
    connection.execute(
        sa.text("DELETE FROM source WHERE id IN (:government_id, :enterprise_id)"),
        {
            "government_id": ROUND05_SOURCE_IDS[0],
            "enterprise_id": ROUND05_SOURCE_IDS[1],
        },
    )
    for table in reversed(ROUND05_TABLES):
        op.drop_table(table)
    op.drop_constraint("uq_claim_item_version_type_subject_predicate", "claim", type_="unique")
    op.create_unique_constraint(
        "uq_claim_item_version_type",
        "claim",
        ["item_id", "document_version_id", "claim_type"],
    )
    op.drop_constraint("ck_round05_review_risk", "review_task", type_="check")
    op.drop_constraint("ck_round05_item_risk", "intelligence_item", type_="check")
    op.drop_constraint("ck_round05_item_channel", "intelligence_item", type_="check")
    op.drop_constraint("ck_round05_item_type", "intelligence_item", type_="check")
    op.create_check_constraint("ck_round04_review_risk", "review_task", "risk_level IN ('R3','R4')")
    op.create_check_constraint(
        "ck_round04_item_risk", "intelligence_item", "risk_level IN ('R3','R4')"
    )
    op.create_check_constraint("ck_round02_item_channel", "intelligence_item", "channel = 'SAFETY'")
    op.create_check_constraint(
        "ck_round04_item_type",
        "intelligence_item",
        "item_type IN ('SAFETY_REGULATION','SAFETY_CASE')",
    )
