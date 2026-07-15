"""Round 06 journal papers, access boundaries, provenance, and reviewed relations.

Revision ID: 0007_papers
Revises: 0006_digital_cases
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0007_papers"
down_revision = "0006_digital_cases"
branch_labels = None
depends_on = None

ROUND06_TABLES = (
    "paper_profile",
    "paper_author",
    "paper_authorship",
    "paper_institution",
    "paper_author_affiliation",
    "paper_source_record",
    "paper_taxonomy",
    "paper_duplicate_candidate",
    "item_relation_candidate",
    "item_relation",
)


def _uuid() -> postgresql.UUID:
    return postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.drop_constraint("ck_round05_item_type", "intelligence_item", type_="check")
    op.create_check_constraint(
        "ck_round06_item_type",
        "intelligence_item",
        "item_type IN ('DIGITAL_CASE','JOURNAL_PAPER','SAFETY_REGULATION','SAFETY_CASE')",
    )
    _create_paper_tables()
    _grant_permissions()


def _create_paper_tables() -> None:
    jsonb = postgresql.JSONB(astext_type=sa.Text())
    op.create_table(
        "paper_profile",
        sa.Column(
            "item_id",
            _uuid(),
            sa.ForeignKey("intelligence_item.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("normalized_doi", sa.String(300)),
        sa.Column("journal", sa.String(300)),
        sa.Column("issns", postgresql.ARRAY(sa.String(20)), nullable=False, server_default="{}"),
        sa.Column("volume", sa.String(50)),
        sa.Column("issue", sa.String(50)),
        sa.Column("pages", sa.String(100)),
        sa.Column("publication_year", sa.SmallInteger()),
        sa.Column("paper_type", sa.String(30), nullable=False, server_default="UNKNOWN"),
        sa.Column("access_level", sa.String(30), nullable=False),
        sa.Column("open_status", sa.String(20), nullable=False, server_default="UNKNOWN"),
        sa.Column("open_license", sa.String(100)),
        sa.Column("open_fulltext_url", sa.String(2048)),
        sa.Column("abstract", sa.Text()),
        sa.Column("abstract_availability", sa.String(30), nullable=False),
        sa.Column(
            "keywords", postgresql.ARRAY(sa.String(300)), nullable=False, server_default="{}"
        ),
        sa.Column("maturity_level", sa.String(40), nullable=False, server_default="UNKNOWN"),
        sa.Column("research_interpretation", jsonb),
        sa.Column("relation_status", sa.String(30), nullable=False, server_default="CURRENT"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "access_level IN ('METADATA_ONLY','ABSTRACT_ALLOWED','OPEN_FULLTEXT')",
            name="ck_paper_access_level",
        ),
        sa.CheckConstraint(
            "paper_type IN ('ARTICLE','REVIEW','METHOD','CASE_STUDY','OTHER','UNKNOWN')",
            name="ck_paper_type",
        ),
        sa.CheckConstraint(
            "access_level <> 'METADATA_ONLY' OR abstract IS NULL",
            name="ck_paper_metadata_has_no_abstract",
        ),
        sa.CheckConstraint(
            "access_level = 'OPEN_FULLTEXT' OR open_fulltext_url IS NULL",
            name="ck_paper_fulltext_link_requires_access",
        ),
        sa.CheckConstraint(
            "normalized_doi IS NULL OR normalized_doi ~ '^10\\.[0-9]{4,9}/\\S+$'",
            name="ck_paper_normalized_doi",
        ),
    )
    op.create_index(
        "uq_paper_profile_normalized_doi",
        "paper_profile",
        ["normalized_doi"],
        unique=True,
        postgresql_where=sa.text("normalized_doi IS NOT NULL"),
    )
    op.create_table(
        "paper_author",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("name", sa.String(300), nullable=False),
        sa.Column("orcid", sa.String(64)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("orcid", name="uq_paper_author_orcid"),
    )
    op.create_table(
        "paper_institution",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("name", sa.String(500), nullable=False),
        sa.Column("ror", sa.String(64)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("ror", name="uq_paper_institution_ror"),
    )
    op.create_table(
        "paper_authorship",
        sa.Column(
            "item_id",
            _uuid(),
            sa.ForeignKey("paper_profile.item_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "author_id",
            _uuid(),
            sa.ForeignKey("paper_author.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("author_order", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("item_id", "author_id", name="pk_paper_authorship"),
        sa.UniqueConstraint("item_id", "author_order", name="uq_paper_authorship_order"),
        sa.CheckConstraint("author_order >= 1", name="ck_paper_author_order"),
    )
    op.create_table(
        "paper_author_affiliation",
        sa.Column("item_id", _uuid(), nullable=False),
        sa.Column("author_id", _uuid(), nullable=False),
        sa.Column(
            "institution_id",
            _uuid(),
            sa.ForeignKey("paper_institution.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["item_id", "author_id"],
            ["paper_authorship.item_id", "paper_authorship.author_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "item_id", "author_id", "institution_id", name="pk_paper_author_affiliation"
        ),
    )
    op.create_table(
        "paper_source_record",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column(
            "item_id",
            _uuid(),
            sa.ForeignKey("paper_profile.item_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "source_id", _uuid(), sa.ForeignKey("source.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column("external_id", sa.String(500), nullable=False),
        sa.Column(
            "document_version_id",
            _uuid(),
            sa.ForeignKey("document_version.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("metadata_sha256", sa.String(64), nullable=False),
        sa.Column("acquired_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("source_id", "external_id", name="uq_paper_source_external_id"),
        sa.CheckConstraint("metadata_sha256 ~ '^[a-f0-9]{64}$'", name="ck_paper_source_sha256"),
    )
    op.create_table(
        "paper_taxonomy",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column(
            "item_id",
            _uuid(),
            sa.ForeignKey("paper_profile.item_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("dimension", sa.String(40), nullable=False),
        sa.Column("code", sa.String(100), nullable=False),
        sa.Column(
            "claim_id", _uuid(), sa.ForeignKey("claim.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.UniqueConstraint("item_id", "dimension", "code", name="uq_paper_taxonomy"),
        sa.CheckConstraint(
            "dimension IN ('ENGINEERING_DOMAIN','TECHNOLOGY_TAG')",
            name="ck_paper_taxonomy_dimension",
        ),
    )
    op.create_table(
        "paper_duplicate_candidate",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("incoming_source_record_id", _uuid(), nullable=False),
        sa.Column(
            "candidate_item_id",
            _uuid(),
            sa.ForeignKey("paper_profile.item_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("fingerprint_sha256", sa.String(64), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="PENDING_REVIEW"),
        sa.Column("reviewed_by", _uuid()),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('PENDING_REVIEW','ACCEPTED','REJECTED')", name="ck_paper_duplicate_status"
        ),
    )
    op.create_table(
        "item_relation_candidate",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column(
            "source_item_id",
            _uuid(),
            sa.ForeignKey("intelligence_item.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "target_item_id", _uuid(), sa.ForeignKey("intelligence_item.id", ondelete="SET NULL")
        ),
        sa.Column("target_external_id", sa.String(500)),
        sa.Column("relation_type", sa.String(30), nullable=False),
        sa.Column("evidence_ids", postgresql.ARRAY(_uuid()), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="PENDING_REVIEW"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "relation_type IN ('CORRECTS','SUPERSEDES','RETRACTS','RELATED_TO',"
            "'SAME_PRODUCT','APPLIED_IN')",
            name="ck_item_relation_candidate_type",
        ),
        sa.CheckConstraint(
            "cardinality(evidence_ids) > 0", name="ck_item_relation_candidate_evidence"
        ),
        sa.CheckConstraint(
            "target_item_id IS NOT NULL OR target_external_id IS NOT NULL",
            name="ck_item_relation_candidate_target",
        ),
    )
    op.create_table(
        "item_relation",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column(
            "source_item_id",
            _uuid(),
            sa.ForeignKey("intelligence_item.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "target_item_id",
            _uuid(),
            sa.ForeignKey("intelligence_item.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("relation_type", sa.String(30), nullable=False),
        sa.Column(
            "candidate_id",
            _uuid(),
            sa.ForeignKey("item_relation_candidate.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("reviewed_by", _uuid(), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "source_item_id", "target_item_id", "relation_type", name="uq_item_relation"
        ),
    )


def _grant_permissions() -> None:
    tables = ", ".join(ROUND06_TABLES)
    op.execute(f"GRANT SELECT ON {tables} TO srbg_runtime, srbg_publication_writer")
    op.execute(
        "GRANT INSERT ON paper_profile, paper_author, paper_authorship, "
        "paper_institution, paper_author_affiliation, paper_source_record, "
        "paper_taxonomy, paper_duplicate_candidate, item_relation_candidate "
        "TO srbg_runtime"
    )
    op.execute(f"GRANT INSERT, UPDATE ON {tables} TO srbg_publication_writer")


def downgrade() -> None:
    connection = op.get_bind()
    if connection.scalar(
        sa.text("SELECT EXISTS (SELECT 1 FROM intelligence_item WHERE item_type = 'JOURNAL_PAPER')")
    ):
        raise RuntimeError("refusing Round06 downgrade while JOURNAL_PAPER data exists")
    for table in reversed(ROUND06_TABLES):
        op.drop_table(table)
    op.drop_constraint("ck_round06_item_type", "intelligence_item", type_="check")
    op.create_check_constraint(
        "ck_round05_item_type",
        "intelligence_item",
        "item_type IN ('DIGITAL_CASE','SAFETY_REGULATION','SAFETY_CASE')",
    )
