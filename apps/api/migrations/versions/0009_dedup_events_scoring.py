"""Round 08 explainable deduplication, clustering, lineage, and scoring.

Revision ID: 0009_dedup_events_scoring
Revises: 0008_technology_products
"""

from __future__ import annotations

import json
import secrets
import time
from uuid import UUID

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0009_dedup_events_scoring"
down_revision = "0008_technology_products"
branch_labels = None
depends_on = None

ROUND08_TABLES = (
    "item_identity_key",
    "document_fingerprint",
    "duplicate_candidate",
    "duplicate_decision",
    "duplicate_link",
    "source_affiliation",
    "source_lineage",
    "topic_cluster",
    "topic_cluster_event",
    "cluster_decision",
    "score_set",
    "score_dimension",
    "score_override",
    "resolution_regression_sample",
)

EVENT_TYPES = (
    "SAFETY_INCIDENT",
    "REGULATION_CHANGE",
    "DIGITAL_PROJECT",
    "RESEARCH_RESULT",
    "PRODUCT_RELEASE",
)
HARD_CONSTRAINTS = (
    "PROJECT",
    "CONTRACT_SECTION",
    "MODEL_NO",
    "DOCUMENT_NUMBER",
    "ACCIDENT_STAGE",
)


def _uuid() -> postgresql.UUID:
    return postgresql.UUID(as_uuid=True)


def _uuid7() -> UUID:
    timestamp_ms = time.time_ns() // 1_000_000
    value = (
        ((timestamp_ms & ((1 << 48) - 1)) << 80)
        | (0x7 << 76)
        | (secrets.randbits(12) << 64)
        | (0b10 << 62)
        | secrets.randbits(62)
    )
    return UUID(int=value)


def upgrade() -> None:
    op.drop_constraint("ck_event_type", "event", type_="check")
    op.create_check_constraint(
        "ck_event_type",
        "event",
        "event_type IN ('SAFETY_INCIDENT','REGULATION_CHANGE','DIGITAL_PROJECT',"
        "'RESEARCH_RESULT','PRODUCT_RELEASE')",
    )
    op.alter_column("event", "incident_status", existing_type=sa.String(40), nullable=True)
    _create_resolution_tables()
    _backfill_legacy_relevance()
    _create_append_only_guards()
    _grant_permissions()


def _create_resolution_tables() -> None:
    op.create_table(
        "item_identity_key",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column(
            "item_id",
            _uuid(),
            sa.ForeignKey("intelligence_item.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("key_type", sa.String(30), nullable=False),
        sa.Column("scope_key", sa.String(300), nullable=False, server_default="GLOBAL"),
        sa.Column("normalized_value", sa.String(2048), nullable=False),
        sa.Column("is_authoritative", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "key_type", "scope_key", "normalized_value", name="uq_item_identity_key"
        ),
        sa.CheckConstraint(
            "key_type IN ('CANONICAL_URL','EXTERNAL_ID','DOI','DOCUMENT_NUMBER','CONTENT_SHA256')",
            name="ck_item_identity_key_type",
        ),
    )
    op.create_index("ix_item_identity_item", "item_identity_key", ["item_id", "key_type"])

    op.create_table(
        "document_fingerprint",
        sa.Column(
            "item_id",
            _uuid(),
            sa.ForeignKey("intelligence_item.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("title_fingerprint", sa.String(64), nullable=False),
        sa.Column("body_simhash", sa.String(64)),
        sa.Column(
            "entity_keys", postgresql.ARRAY(sa.String(300)), nullable=False, server_default="{}"
        ),
        sa.Column("occurred_at", sa.DateTime(timezone=True)),
        sa.Column("region_key", sa.String(200)),
        sa.Column("project_key", sa.String(300)),
        sa.Column("contract_section_key", sa.String(200)),
        sa.Column("model_no_key", sa.String(200)),
        sa.Column("document_number_key", sa.String(300)),
        sa.Column("accident_stage", sa.String(40)),
        sa.Column("embedding", postgresql.ARRAY(sa.REAL())),
        sa.Column("embedding_model", sa.String(100)),
        sa.Column("rule_version", sa.String(50), nullable=False, server_default="dedup-v1.0.0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_document_fingerprint_time_region", "document_fingerprint", ["occurred_at", "region_key"]
    )

    op.create_table(
        "duplicate_candidate",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column(
            "left_item_id",
            _uuid(),
            sa.ForeignKey("intelligence_item.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "right_item_id",
            _uuid(),
            sa.ForeignKey("intelligence_item.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("score_bps", sa.Integer(), nullable=False),
        sa.Column("features", postgresql.JSONB(), nullable=False),
        sa.Column(
            "hard_conflicts", postgresql.ARRAY(sa.String(40)), nullable=False, server_default="{}"
        ),
        sa.Column("recall_methods", postgresql.ARRAY(sa.String(20)), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="PENDING_REVIEW"),
        sa.Column("rule_version", sa.String(50), nullable=False, server_default="dedup-v1.0.0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("left_item_id < right_item_id", name="ck_duplicate_candidate_order"),
        sa.CheckConstraint("score_bps BETWEEN 0 AND 10000", name="ck_duplicate_candidate_score"),
        sa.CheckConstraint(
            "status IN ('PENDING_REVIEW','ACCEPTED','REJECTED')",
            name="ck_duplicate_candidate_status",
        ),
        sa.UniqueConstraint(
            "left_item_id", "right_item_id", "rule_version", name="uq_duplicate_candidate_pair"
        ),
    )
    op.create_index("ix_duplicate_candidate_queue", "duplicate_candidate", ["status", "score_bps"])

    op.create_table(
        "duplicate_decision",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column(
            "candidate_id",
            _uuid(),
            sa.ForeignKey("duplicate_candidate.id", ondelete="RESTRICT"),
            nullable=False,
            unique=True,
        ),
        sa.Column("action", sa.String(30), nullable=False),
        sa.Column("relation_type", sa.String(50)),
        sa.Column("reason", sa.String(1000), nullable=False),
        sa.Column("reviewed_by", _uuid(), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "action IN ('MERGE','KEEP_DISTINCT','LINK_RELATION')",
            name="ck_duplicate_decision_action",
        ),
    )
    op.create_table(
        "duplicate_link",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column(
            "canonical_item_id",
            _uuid(),
            sa.ForeignKey("intelligence_item.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "duplicate_item_id",
            _uuid(),
            sa.ForeignKey("intelligence_item.id", ondelete="RESTRICT"),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "decision_id",
            _uuid(),
            sa.ForeignKey("duplicate_decision.id", ondelete="RESTRICT"),
            nullable=False,
            unique=True,
        ),
        sa.Column("linked_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "canonical_item_id <> duplicate_item_id", name="ck_duplicate_link_distinct"
        ),
    )

    op.create_table(
        "source_affiliation",
        sa.Column(
            "source_id", _uuid(), sa.ForeignKey("source.id", ondelete="CASCADE"), primary_key=True
        ),
        sa.Column("organization_key", sa.String(200), nullable=False),
        sa.Column("mirror_group_key", sa.String(200)),
        sa.Column("reviewed_by", _uuid()),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "source_lineage",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column(
            "item_id",
            _uuid(),
            sa.ForeignKey("intelligence_item.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "source_id", _uuid(), sa.ForeignKey("source.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column("lineage_root", sa.String(200), nullable=False),
        sa.Column("role", sa.String(30), nullable=False),
        sa.Column("rule_version", sa.String(50), nullable=False, server_default="lineage-v1.0.0"),
        sa.Column("reviewed_by", _uuid()),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "role IN ('ORIGINAL','REPRINT','MIRROR','INDEPENDENT_REPORT')",
            name="ck_source_lineage_role",
        ),
    )
    op.create_index("ix_source_lineage_root", "source_lineage", ["lineage_root", "role"])

    op.create_table(
        "topic_cluster",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("domain", sa.String(10), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="PENDING_REVIEW"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("domain IN ('DIGITAL','SAFETY')", name="ck_topic_cluster_domain"),
        sa.CheckConstraint(
            "status IN ('PENDING_REVIEW','CONFIRMED','REJECTED')", name="ck_topic_cluster_status"
        ),
    )
    op.create_table(
        "topic_cluster_event",
        sa.Column(
            "topic_id",
            _uuid(),
            sa.ForeignKey("topic_cluster.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "event_id", _uuid(), sa.ForeignKey("event.id", ondelete="RESTRICT"), primary_key=True
        ),
        sa.Column("decision_id", _uuid(), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "cluster_decision",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("candidate_kind", sa.String(20), nullable=False),
        sa.Column("candidate_id", _uuid(), nullable=False),
        sa.Column("action", sa.String(30), nullable=False),
        sa.Column("member_ids", postgresql.ARRAY(_uuid()), nullable=False),
        sa.Column("relation_type", sa.String(50)),
        sa.Column("reason", sa.String(1000), nullable=False),
        sa.Column("reviewed_by", _uuid(), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "candidate_kind IN ('DUPLICATE','EVENT','TOPIC','RELATION')",
            name="ck_cluster_decision_kind",
        ),
        sa.CheckConstraint(
            "action IN ('MERGE','SPLIT','KEEP_DISTINCT','LINK_RELATION')",
            name="ck_cluster_decision_action",
        ),
        sa.CheckConstraint("cardinality(member_ids) >= 2", name="ck_cluster_decision_members"),
    )

    op.create_table(
        "score_set",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column(
            "item_id",
            _uuid(),
            sa.ForeignKey("intelligence_item.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("rule_version", sa.String(50), nullable=False, server_default="scoring-v1.0.0"),
        sa.Column("calculated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_current", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.UniqueConstraint(
            "item_id", "rule_version", "calculated_at", name="uq_score_set_version"
        ),
    )
    op.create_index("ix_score_set_current", "score_set", ["item_id", "is_current"])
    op.create_index(
        "uq_score_set_one_current",
        "score_set",
        ["item_id"],
        unique=True,
        postgresql_where=sa.text("is_current"),
    )
    op.create_table(
        "score_dimension",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column(
            "score_set_id",
            _uuid(),
            sa.ForeignKey("score_set.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("dimension", sa.String(20), nullable=False),
        sa.Column("raw_score", sa.Integer(), nullable=False),
        sa.Column("features", postgresql.JSONB(), nullable=False),
        sa.UniqueConstraint("score_set_id", "dimension", name="uq_score_dimension"),
        sa.CheckConstraint("raw_score BETWEEN 0 AND 100", name="ck_score_dimension_value"),
        sa.CheckConstraint(
            "dimension IN ('RELEVANCE','AUTHORITY','IMPACT','NOVELTY',"
            "'TIMELINESS','EVIDENCE','CONFIDENCE','HEAT')",
            name="ck_score_dimension_name",
        ),
    )
    op.create_table(
        "score_override",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column(
            "score_dimension_id",
            _uuid(),
            sa.ForeignKey("score_dimension.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("reason", sa.String(1000), nullable=False),
        sa.Column("reviewed_by", _uuid(), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "supersedes_override_id",
            _uuid(),
            sa.ForeignKey("score_override.id", ondelete="RESTRICT"),
        ),
        sa.CheckConstraint("score BETWEEN 0 AND 100", name="ck_score_override_value"),
    )
    op.create_table(
        "resolution_regression_sample",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("sample_kind", sa.String(20), nullable=False),
        sa.Column("decision_id", _uuid(), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "sample_kind IN ('DUPLICATE','EVENT','TOPIC','SCORE')",
            name="ck_resolution_regression_kind",
        ),
    )


def _backfill_legacy_relevance() -> None:
    connection = op.get_bind()
    rows = connection.execute(
        sa.text(
            """
            SELECT item_id, score, engineering_points, sichuan_points,
                   srbg_direct_points, calculated_at
            FROM digital_case_relevance
            """
        )
    ).mappings()
    for row in rows:
        score_set_id = _uuid7()
        connection.execute(
            sa.text(
                """
                INSERT INTO score_set (
                    id, item_id, rule_version, calculated_at, is_current
                ) VALUES (:id, :item_id, 'scoring-v1.0.0', :calculated_at, true)
                """
            ),
            {
                "id": score_set_id,
                "item_id": row["item_id"],
                "calculated_at": row["calculated_at"],
            },
        )
        features = [
            {
                "code": code,
                "label": label,
                "points": row[column],
                "explanation": explanation,
            }
            for code, label, column, explanation in (
                ("ENGINEERING_DOMAIN", "工程专业匹配", "engineering_points", "来自已接受分类事实"),
                ("SICHUAN", "四川实施", "sichuan_points", "来自已接受地区事实"),
                ("SRBG_DIRECT", "四川路桥直接关系", "srbg_direct_points", "来自已接受实体关系"),
            )
        ]
        connection.execute(
            sa.text(
                """
                INSERT INTO score_dimension (
                    id, score_set_id, dimension, raw_score, features
                ) VALUES (
                    :id, :score_set_id, 'RELEVANCE', :score, CAST(:features AS jsonb)
                )
                """
            ),
            {
                "id": _uuid7(),
                "score_set_id": score_set_id,
                "score": row["score"],
                "features": json.dumps(features, ensure_ascii=False),
            },
        )


def _create_append_only_guards() -> None:
    op.execute(
        """
        CREATE FUNCTION prevent_round08_mutation() RETURNS trigger AS $$
        BEGIN
          RAISE EXCEPTION 'Round08 decisions and audit facts are append-only';
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute("REVOKE ALL ON FUNCTION prevent_round08_mutation() FROM PUBLIC")
    for table in (
        "duplicate_decision",
        "duplicate_link",
        "cluster_decision",
        "score_override",
        "resolution_regression_sample",
    ):
        op.execute(
            f"CREATE TRIGGER trg_{table}_append_only BEFORE UPDATE OR DELETE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION prevent_round08_mutation()"
        )


def _grant_permissions() -> None:
    tables = ", ".join(ROUND08_TABLES)
    op.execute(f"GRANT SELECT ON {tables} TO srbg_runtime, srbg_publication_writer")
    op.execute(
        "GRANT INSERT, UPDATE ON item_identity_key, document_fingerprint, duplicate_candidate, "
        "source_lineage, score_set, score_dimension TO srbg_runtime"
    )
    op.execute(
        "GRANT INSERT, UPDATE ON duplicate_decision, duplicate_link, source_affiliation, "
        "topic_cluster, topic_cluster_event, cluster_decision, score_override, "
        "resolution_regression_sample TO srbg_publication_writer"
    )
    op.execute(
        "REVOKE INSERT, UPDATE, DELETE ON duplicate_decision, duplicate_link, cluster_decision, "
        "score_override, resolution_regression_sample FROM srbg_runtime"
    )


def downgrade() -> None:
    connection = op.get_bind()
    if connection.scalar(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM event WHERE event_type <> 'SAFETY_INCIDENT') OR "
            "EXISTS (SELECT 1 FROM duplicate_decision) OR EXISTS (SELECT 1 FROM cluster_decision) "
            "OR EXISTS (SELECT 1 FROM score_override)"
        )
    ):
        raise RuntimeError(
            "refusing Round08 downgrade while resolution decisions or all-domain events exist"
        )
    for table in (
        "duplicate_decision",
        "duplicate_link",
        "cluster_decision",
        "score_override",
        "resolution_regression_sample",
    ):
        op.execute(f"DROP TRIGGER IF EXISTS trg_{table}_append_only ON {table}")
    op.execute("DROP FUNCTION IF EXISTS prevent_round08_mutation()")
    for table in reversed(ROUND08_TABLES):
        op.drop_table(table)
    op.alter_column("event", "incident_status", existing_type=sa.String(40), nullable=False)
    op.drop_constraint("ck_event_type", "event", type_="check")
    op.create_check_constraint("ck_event_type", "event", "event_type = 'SAFETY_INCIDENT'")
