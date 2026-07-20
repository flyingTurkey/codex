"""Add append-only evidence-led content preparation candidates.

Revision ID: 0039_t04_content_candidates
Revises: 0038_owner_gold_calibration
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0039_t04_content_candidates"
down_revision = "0038_owner_gold_calibration"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _uuid() -> postgresql.UUID:
    return postgresql.UUID(as_uuid=True)


def _json() -> postgresql.JSONB:
    return postgresql.JSONB(astext_type=sa.Text())


def upgrade() -> None:
    op.create_table(
        "content_preparation_candidate_v2",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column(
            "event_id", _uuid(), sa.ForeignKey("event.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column(
            "document_version_id",
            _uuid(),
            sa.ForeignKey("document_version.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("accepted_claim_set_sha256", sa.String(64), nullable=False),
        sa.Column("source_excerpt", sa.String(500), nullable=False),
        sa.Column("claim_ids", postgresql.ARRAY(_uuid()), nullable=False),
        sa.Column("source_excerpt_claim_ids", postgresql.ARRAY(_uuid()), nullable=False),
        sa.Column("evidence_locators", postgresql.ARRAY(sa.String(500)), nullable=False),
        sa.Column("claim_basis", postgresql.ARRAY(sa.String(40)), nullable=False),
        sa.Column("claims_payload", _json(), nullable=False),
        sa.Column("summary_payload", _json(), nullable=False),
        sa.Column("visible_character_count", sa.Integer(), nullable=False),
        sa.Column("model", sa.String(100), nullable=False),
        sa.Column("prompt_version", sa.String(100), nullable=False),
        sa.Column("schema_version", sa.String(100), nullable=False),
        sa.Column("input_sha256", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "accepted_claim_set_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_t04_candidate_claim_hash",
        ),
        sa.CheckConstraint("input_sha256 ~ '^[0-9a-f]{64}$'", name="ck_t04_candidate_input_hash"),
        sa.CheckConstraint(
            "visible_character_count BETWEEN 300 AND 500",
            name="ck_t04_candidate_summary_length",
        ),
        sa.CheckConstraint(
            "cardinality(claim_ids)>0 AND cardinality(source_excerpt_claim_ids)>0 "
            "AND cardinality(evidence_locators)>0",
            name="ck_t04_candidate_evidence",
        ),
        sa.UniqueConstraint(
            "document_version_id",
            "accepted_claim_set_sha256",
            "prompt_version",
            "schema_version",
            "model",
            name="uq_t04_candidate_dependencies",
        ),
    )
    op.create_table(
        "content_preparation_invalidation_v2",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column(
            "candidate_id",
            _uuid(),
            sa.ForeignKey("content_preparation_candidate_v2.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("reason", sa.String(40), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "reason IN ('DOCUMENT_VERSION_CHANGED','ACCEPTED_CLAIMS_CHANGED',"
            "'SOURCE_WITHDRAWN','SOURCE_CORRECTED')",
            name="ck_t04_invalidation_reason",
        ),
        sa.UniqueConstraint("candidate_id", name="uq_t04_invalidation_candidate"),
    )
    op.execute(
        "CREATE FUNCTION prevent_t04_append_only_mutation() RETURNS trigger "
        "LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'T04_APPEND_ONLY_FACT'; END $$"
    )
    for table in (
        "content_preparation_candidate_v2",
        "content_preparation_invalidation_v2",
    ):
        op.execute(
            f"CREATE TRIGGER trg_{table}_append_only BEFORE UPDATE OR DELETE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION prevent_t04_append_only_mutation()"
        )
        op.execute(f"REVOKE ALL ON TABLE {table} FROM PUBLIC")
    op.execute(
        "GRANT SELECT,INSERT ON content_preparation_candidate_v2,"
        "content_preparation_invalidation_v2 TO srbg_worker_role"
    )
    op.execute(
        "GRANT SELECT ON content_preparation_candidate_v2,"
        "content_preparation_invalidation_v2 TO srbg_projection_reader"
    )
    op.execute(
        "GRANT SELECT ON content_preparation_candidate_v2 TO srbg_publication_writer"
    )
    op.execute(
        "GRANT SELECT,INSERT ON content_preparation_invalidation_v2 "
        "TO srbg_publication_writer"
    )


def downgrade() -> None:
    bind = op.get_bind()
    durable = bind.execute(
        sa.text(
            "SELECT EXISTS(SELECT 1 FROM content_preparation_candidate_v2) OR "
            "EXISTS(SELECT 1 FROM content_preparation_invalidation_v2)"
        )
    ).scalar_one()
    if durable:
        raise RuntimeError("T04_DOWNGRADE_BLOCKED: durable candidate facts exist")
    for table in (
        "content_preparation_invalidation_v2",
        "content_preparation_candidate_v2",
    ):
        op.execute(f"DROP TRIGGER trg_{table}_append_only ON {table}")
    op.drop_table("content_preparation_invalidation_v2")
    op.drop_table("content_preparation_candidate_v2")
    op.execute("DROP FUNCTION prevent_t04_append_only_mutation()")
