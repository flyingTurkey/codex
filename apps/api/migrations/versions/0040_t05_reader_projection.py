# ruff: noqa: E501
"""Add rebuildable T05 qualification, publication and archive facts.

Revision ID: 0040_t05_reader_projection
Revises: 0039_t04_content_candidates
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0040_t05_reader_projection"
down_revision = "0039_t04_content_candidates"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _uuid() -> postgresql.UUID:
    return postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.create_table(
        "qualification_acceptance_v2",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("event_id", _uuid(), sa.ForeignKey("event.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("document_version_id", _uuid(), sa.ForeignKey("document_version.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("pipeline_run_id", _uuid(), sa.ForeignKey("ai_pipeline_run.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("primary_type", sa.String(30), nullable=False),
        sa.Column("engineering_objects", postgresql.ARRAY(sa.String(30)), nullable=False),
        sa.Column("specialty_facets", postgresql.ARRAY(sa.String(40)), nullable=False),
        sa.Column("equipment_domains", postgresql.ARRAY(sa.String(40)), nullable=False),
        sa.Column("cross_type_tags", postgresql.ARRAY(sa.String(30)), nullable=False),
        sa.Column("classification_sha256", sa.String(64), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("primary_type IN ('DIGITAL_TRANSFORMATION','SAFETY_INTELLIGENCE','INDUSTRY_UPDATE')", name="ck_t05_qualification_primary_type"),
        sa.CheckConstraint(
            "cardinality(engineering_objects)>0 OR cardinality(equipment_domains)>0",
            name="ck_t05_qualification_scope",
        ),
        sa.CheckConstraint("classification_sha256 ~ '^[a-f0-9]{64}$'", name="ck_t05_qualification_hash"),
        sa.UniqueConstraint("document_version_id", name="uq_t05_qualification_document"),
    )
    op.create_table(
        "publication_decision_v2",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("event_id", _uuid(), sa.ForeignKey("event.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("document_version_id", _uuid(), sa.ForeignKey("document_version.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("outcome", sa.String(20), nullable=False),
        sa.Column("reason_codes", postgresql.ARRAY(sa.String(80)), nullable=False),
        sa.Column("projection_sha256", sa.String(64)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("outcome IN ('FULL','R3_METADATA','NOT_FOUND','QUARANTINE')", name="ck_t05_publication_outcome"),
        sa.CheckConstraint("projection_sha256 IS NULL OR projection_sha256 ~ '^[a-f0-9]{64}$'", name="ck_t05_publication_hash"),
    )
    op.create_table(
        "projection_archive_row_v2",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("manifest_id", _uuid(), sa.ForeignKey("projection_archive_manifest.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("source_table", sa.String(100), nullable=False),
        sa.Column("row_key", sa.String(500), nullable=False),
        sa.Column("row_sha256", sa.String(64), nullable=False),
        sa.CheckConstraint("row_sha256 ~ '^[a-f0-9]{64}$'", name="ck_t05_archive_row_hash"),
        sa.UniqueConstraint("manifest_id", "source_table", "row_key", name="uq_t05_archive_row"),
    )
    op.execute(
        "CREATE FUNCTION prevent_t05_append_only_mutation() RETURNS trigger "
        "LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'T05_APPEND_ONLY_FACT'; END $$"
    )
    for table in (
        "qualification_acceptance_v2",
        "publication_decision_v2",
        "projection_archive_row_v2",
    ):
        op.execute(
            f"CREATE TRIGGER trg_{table}_append_only BEFORE UPDATE OR DELETE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION prevent_t05_append_only_mutation()"
        )
        op.execute(f"REVOKE ALL ON TABLE {table} FROM PUBLIC")
    op.execute("GRANT SELECT,INSERT ON qualification_acceptance_v2 TO srbg_worker_role")
    op.execute("GRANT SELECT ON qualification_acceptance_v2 TO srbg_publication_writer")
    op.execute("GRANT SELECT,INSERT ON publication_decision_v2,projection_archive_row_v2 TO srbg_publication_writer")
    op.execute("GRANT SELECT ON projection_archive_row_v2 TO srbg_projection_reader")


def downgrade() -> None:
    bind = op.get_bind()
    durable = bind.execute(
        sa.text(
            "SELECT EXISTS(SELECT 1 FROM qualification_acceptance_v2) OR "
            "EXISTS(SELECT 1 FROM publication_decision_v2) OR "
            "EXISTS(SELECT 1 FROM projection_archive_row_v2)"
        )
    ).scalar_one()
    if durable:
        raise RuntimeError("T05_DOWNGRADE_BLOCKED: durable qualification/publication/archive facts exist")
    for table in (
        "projection_archive_row_v2",
        "publication_decision_v2",
        "qualification_acceptance_v2",
    ):
        op.execute(f"DROP TRIGGER trg_{table}_append_only ON {table}")
        op.drop_table(table)
    op.execute("DROP FUNCTION prevent_t05_append_only_mutation()")
