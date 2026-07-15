"""Round 10 feed search, daily reports, saved items, and collections.

Revision ID: 0011_feed_search_daily
Revises: 0010_ai_editorial_governance
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0011_feed_search_daily"
down_revision = "0010_ai_editorial_governance"
branch_labels = None
depends_on = None

ROUND10_TABLES = (
    "search_projection",
    "search_identifier",
    "daily_report",
    "daily_report_item",
    "saved_item",
    "user_collection",
    "collection_item",
    "idempotency_record",
)


def _uuid() -> postgresql.UUID:
    return postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    _create_search_projection()
    _create_daily_reports()
    _create_personal_library()
    _grant_permissions()


def _create_search_projection() -> None:
    op.create_table(
        "search_projection",
        sa.Column(
            "item_id",
            _uuid(),
            sa.ForeignKey("intelligence_item.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "publication_revision_id",
            _uuid(),
            sa.ForeignKey("publication_revision.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("domain", sa.String(20), nullable=False),
        sa.Column("content_type", sa.String(50), nullable=False),
        sa.Column(
            "source_id",
            _uuid(),
            sa.ForeignKey("source.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("region", sa.String(100)),
        sa.Column("evidence_status", sa.String(20)),
        sa.Column("risk_level", sa.String(2), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("entity_text", sa.Text(), nullable=False, server_default=""),
        sa.Column("tag_text", sa.Text(), nullable=False, server_default=""),
        sa.Column("body_tokens", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "search_vector",
            postgresql.TSVECTOR(),
            sa.Computed(
                "setweight(to_tsvector('simple', coalesce(title, '')), 'A') || "
                "setweight(to_tsvector('simple', coalesce(entity_text, '')), 'B') || "
                "setweight(to_tsvector('simple', coalesce(tag_text, '')), 'B') || "
                "setweight(to_tsvector('simple', coalesce(body_tokens, '')), 'C')",
                persisted=True,
            ),
            nullable=False,
        ),
        sa.Column("embedding_model", sa.String(100)),
        sa.Column("embedding_input_sha256", sa.String(64)),
        sa.Column("visible", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("generation", sa.BigInteger(), nullable=False),
        sa.Column("activity_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("indexed_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("domain IN ('DIGITAL','SAFETY')", name="ck_search_domain"),
        sa.CheckConstraint(
            "evidence_status IS NULL OR evidence_status IN ('WITHHELD','VERIFIED')",
            name="ck_search_evidence_status",
        ),
        sa.CheckConstraint("risk_level IN ('R1','R2','R3','R4')", name="ck_search_risk"),
        sa.CheckConstraint("generation >= 1", name="ck_search_generation"),
    )
    op.execute("ALTER TABLE search_projection ADD COLUMN embedding vector(1536)")
    op.create_index(
        "ix_search_title_trgm",
        "search_projection",
        ["title"],
        postgresql_using="gin",
        postgresql_ops={"title": "gin_trgm_ops"},
    )
    op.create_index(
        "ix_search_entity_trgm",
        "search_projection",
        ["entity_text"],
        postgresql_using="gin",
        postgresql_ops={"entity_text": "gin_trgm_ops"},
    )
    op.create_index(
        "ix_search_tag_trgm",
        "search_projection",
        ["tag_text"],
        postgresql_using="gin",
        postgresql_ops={"tag_text": "gin_trgm_ops"},
    )
    op.create_index(
        "ix_search_vector_gin",
        "search_projection",
        ["search_vector"],
        postgresql_using="gin",
    )
    op.execute(
        "CREATE INDEX ix_search_embedding_hnsw ON search_projection "
        "USING hnsw (embedding vector_cosine_ops) WHERE embedding IS NOT NULL AND visible"
    )
    op.create_index(
        "ix_search_acl_activity",
        "search_projection",
        ["visible", "risk_level", "domain", "content_type", "activity_at", "item_id"],
    )

    op.create_table(
        "search_identifier",
        sa.Column(
            "item_id",
            _uuid(),
            sa.ForeignKey("search_projection.item_id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("kind", sa.String(30), primary_key=True),
        sa.Column("normalized_value", sa.String(2048), primary_key=True),
        sa.Column("display_value", sa.String(2048), nullable=False),
        sa.CheckConstraint(
            "kind IN ('DOCUMENT_NUMBER','STANDARD_NUMBER','DOI','EXTERNAL_ID')",
            name="ck_search_identifier_kind",
        ),
    )
    op.create_index(
        "ix_search_identifier_exact",
        "search_identifier",
        ["normalized_value", "kind", "item_id"],
    )


def _create_daily_reports() -> None:
    op.create_table(
        "daily_report",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("report_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("snapshot_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.Column("created_by", _uuid(), nullable=False),
        sa.Column("reviewer_id", _uuid()),
        sa.Column("requires_regeneration", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.CheckConstraint("status IN ('DRAFT','PUBLISHED')", name="ck_daily_report_status"),
        sa.CheckConstraint("version >= 1", name="ck_daily_report_version"),
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_daily_report_published_date ON daily_report (report_date) "
        "WHERE status = 'PUBLISHED'"
    )
    op.create_index(
        "ix_daily_report_date_status",
        "daily_report",
        ["report_date", "status", "snapshot_at"],
    )
    op.create_table(
        "daily_report_item",
        sa.Column(
            "report_id",
            _uuid(),
            sa.ForeignKey("daily_report.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("section", sa.String(30), primary_key=True),
        sa.Column("position", sa.Integer(), primary_key=True),
        sa.Column(
            "item_id",
            _uuid(),
            sa.ForeignKey("intelligence_item.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "publication_revision_id",
            _uuid(),
            sa.ForeignKey("publication_revision.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("summary", sa.String(1000)),
        sa.Column("original_url", sa.String(2048), nullable=False),
        sa.UniqueConstraint("report_id", "item_id", name="uq_daily_report_item"),
        sa.CheckConstraint(
            "section IN ('TODAY_HIGHLIGHTS','DIGITAL_SELECTED','SAFETY_HIGHLIGHTS',"
            "'WATCHLIST','SOURCE_ANOMALIES')",
            name="ck_daily_report_section",
        ),
        sa.CheckConstraint("position >= 1", name="ck_daily_report_position"),
    )


def _create_personal_library() -> None:
    op.create_table(
        "saved_item",
        sa.Column("owner_id", _uuid(), primary_key=True),
        sa.Column(
            "item_id",
            _uuid(),
            sa.ForeignKey("intelligence_item.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("saved_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "user_collection",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("owner_id", _uuid(), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("archived", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("id", "owner_id", name="uq_collection_owner"),
        sa.CheckConstraint("version >= 1", name="ck_collection_version"),
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_collection_active_name ON user_collection "
        "(owner_id, lower(name)) WHERE NOT archived"
    )
    op.create_index(
        "ix_collection_owner_updated",
        "user_collection",
        ["owner_id", "archived", "updated_at"],
    )
    op.create_table(
        "collection_item",
        sa.Column("collection_id", _uuid(), primary_key=True),
        sa.Column("owner_id", _uuid(), nullable=False),
        sa.Column("item_id", _uuid(), primary_key=True),
        sa.Column("added_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["collection_id", "owner_id"],
            ["user_collection.id", "user_collection.owner_id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["owner_id", "item_id"],
            ["saved_item.owner_id", "saved_item.item_id"],
            ondelete="CASCADE",
        ),
    )
    op.create_table(
        "idempotency_record",
        sa.Column("owner_id", _uuid(), primary_key=True),
        sa.Column("scope", sa.String(50), primary_key=True),
        sa.Column("idempotency_key", sa.String(200), primary_key=True),
        sa.Column("request_sha256", sa.String(64), nullable=False),
        sa.Column("response_id", _uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "request_sha256 ~ '^[0-9a-f]{64}$'", name="ck_idempotency_request_sha256"
        ),
    )


def _grant_permissions() -> None:
    tables = ", ".join(ROUND10_TABLES)
    op.execute(f"REVOKE ALL ON {tables} FROM PUBLIC")
    op.execute(f"GRANT SELECT ON {tables} TO srbg_runtime, srbg_publication_writer")
    op.execute(
        "GRANT INSERT, UPDATE, DELETE ON saved_item, user_collection, collection_item, "
        "idempotency_record TO srbg_runtime"
    )
    op.execute(
        "GRANT INSERT, UPDATE, DELETE ON search_projection, search_identifier, daily_report, "
        "daily_report_item, idempotency_record TO srbg_publication_writer"
    )


def downgrade() -> None:
    connection = op.get_bind()
    protected_count = int(
        connection.scalar(
            sa.text(
                "SELECT (SELECT count(*) FROM daily_report) + "
                "(SELECT count(*) FROM saved_item) + (SELECT count(*) FROM user_collection)"
            )
        )
        or 0
    )
    if protected_count:
        raise RuntimeError(
            "refusing Round10 downgrade while daily reports or personal library records exist"
        )
    for table in reversed(ROUND10_TABLES):
        op.drop_table(table)
