"""Round 03 PDF/OCR evidence, version changes, and append-only lifecycle facts.

Revision ID: 0004_pdf_ocr_versioning
Revises: 0003_safety_publication
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004_pdf_ocr_versioning"
down_revision: str | None = "0003_safety_publication"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JSON = postgresql.JSONB(astext_type=sa.Text())

ROUND03_TABLES = (
    "raw_object_security_fact",
    "document_version_state_event",
    "document_page",
    "document_text_block",
    "document_table_cell",
    "version_change",
    "version_change_state_event",
    "document_relation_candidate",
    "document_relation_decision",
    "document_relation",
    "regulation_status_candidate",
    "regulation_status_decision",
    "content_lifecycle_event",
    "derived_summary",
    "source_url_check",
    "outbox_event",
)


def _uuid() -> postgresql.UUID:
    return postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.add_column("document_attachment", sa.Column("parent_attachment_id", _uuid()))
    op.add_column("document_attachment", sa.Column("normalized_path", sa.String(1000)))
    op.add_column("document_attachment", sa.Column("depth", sa.SmallInteger()))
    op.add_column("document_attachment", sa.Column("detected_mime", sa.String(100)))
    op.add_column("document_attachment", sa.Column("byte_size", sa.BigInteger()))
    op.add_column("document_attachment", sa.Column("security_status", sa.String(20)))
    op.create_foreign_key(
        "fk_document_attachment_parent",
        "document_attachment",
        "document_attachment",
        ["parent_attachment_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_check_constraint(
        "ck_document_attachment_depth",
        "document_attachment",
        "depth IS NULL OR depth BETWEEN 0 AND 1",
    )
    op.create_check_constraint(
        "ck_document_attachment_size", "document_attachment", "byte_size IS NULL OR byte_size >= 0"
    )
    op.create_check_constraint(
        "ck_document_attachment_security",
        "document_attachment",
        "security_status IS NULL OR security_status IN ('CLEAN','QUARANTINED','REJECTED')",
    )

    op.create_table(
        "raw_object_security_fact",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column(
            "raw_object_id",
            _uuid(),
            sa.ForeignKey("raw_object.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("detected_mime", sa.String(100), nullable=False),
        sa.Column("rule_version", sa.String(50), nullable=False),
        sa.Column("reason_code", sa.String(100)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('CLEAN','QUARANTINED','REJECTED')",
            name="ck_raw_security_status",
        ),
        sa.UniqueConstraint("raw_object_id", "rule_version", name="uq_raw_security_object_rule"),
    )
    op.create_index(
        "ix_raw_security_object_created",
        "raw_object_security_fact",
        ["raw_object_id", "created_at"],
    )

    op.create_table(
        "document_version_state_event",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column(
            "document_version_id",
            _uuid(),
            sa.ForeignKey("document_version.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("state", sa.String(30), nullable=False),
        sa.Column("reason_code", sa.String(100)),
        sa.Column("actor_type", sa.String(30), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "state IN ('RECEIVED','SECURITY_PASSED','PARSING','OCR_PENDING',"
            "'OCR_COMPLETE','READY','QUARANTINED','FAILED')",
            name="ck_document_version_state",
        ),
        sa.CheckConstraint(
            "actor_type IN ('SYSTEM','WORKER','REVIEWER')",
            name="ck_document_version_state_actor",
        ),
    )
    op.create_index(
        "ix_document_version_state_created",
        "document_version_state_event",
        ["document_version_id", "created_at"],
    )

    op.create_table(
        "document_page",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column(
            "document_version_id",
            _uuid(),
            sa.ForeignKey("document_version.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("page_number", sa.Integer(), nullable=False),
        sa.Column("width_mpt", sa.Integer(), nullable=False),
        sa.Column("height_mpt", sa.Integer(), nullable=False),
        sa.Column("rotation", sa.SmallInteger(), nullable=False),
        sa.Column("text_source", sa.String(10), nullable=False),
        sa.Column("normalized_text_sha256", sa.String(64), nullable=False),
        sa.Column("preview_object_key", sa.String(500), nullable=False),
        sa.Column("preview_sha256", sa.String(64), nullable=False),
        sa.Column("preview_mime", sa.String(30), nullable=False, server_default="image/png"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "document_version_id", "page_number", name="uq_document_page_version_number"
        ),
        sa.CheckConstraint("page_number BETWEEN 1 AND 10000", name="ck_document_page_number"),
        sa.CheckConstraint("width_mpt > 0 AND height_mpt > 0", name="ck_document_page_size"),
        sa.CheckConstraint("rotation IN (0,90,180,270)", name="ck_document_page_rotation"),
        sa.CheckConstraint(
            "text_source IN ('NATIVE','OCR','MIXED')", name="ck_document_page_source"
        ),
        sa.CheckConstraint(
            "normalized_text_sha256 ~ '^[a-f0-9]{64}$'",
            name="ck_document_page_text_hash",
        ),
        sa.CheckConstraint(
            "preview_sha256 ~ '^[a-f0-9]{64}$'", name="ck_document_page_preview_hash"
        ),
    )

    op.create_table(
        "document_text_block",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column(
            "document_page_id",
            _uuid(),
            sa.ForeignKey("document_page.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("block_index", sa.Integer(), nullable=False),
        sa.Column("block_kind", sa.String(20), nullable=False),
        sa.Column("text_source", sa.String(10), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("normalized_text", sa.Text(), nullable=False),
        sa.Column("text_sha256", sa.String(64), nullable=False),
        sa.Column("x0_mpt", sa.Integer(), nullable=False),
        sa.Column("y0_mpt", sa.Integer(), nullable=False),
        sa.Column("x1_mpt", sa.Integer(), nullable=False),
        sa.Column("y1_mpt", sa.Integer(), nullable=False),
        sa.Column("confidence_bps", sa.Integer()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "document_page_id", "block_index", name="uq_document_text_block_page_index"
        ),
        sa.CheckConstraint("block_index >= 0", name="ck_document_text_block_index"),
        sa.CheckConstraint(
            "block_kind IN ('BODY','HEADER','FOOTER','TABLE','CAPTION')",
            name="ck_document_text_block_kind",
        ),
        sa.CheckConstraint("text_source IN ('NATIVE','OCR')", name="ck_document_text_block_source"),
        sa.CheckConstraint(
            "x0_mpt >= 0 AND y0_mpt >= 0 AND x1_mpt > x0_mpt AND y1_mpt > y0_mpt",
            name="ck_document_text_block_box",
        ),
        sa.CheckConstraint(
            "confidence_bps IS NULL OR confidence_bps BETWEEN 0 AND 10000",
            name="ck_document_text_block_confidence",
        ),
    )

    op.create_table(
        "document_table_cell",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column(
            "document_page_id",
            _uuid(),
            sa.ForeignKey("document_page.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("table_index", sa.Integer(), nullable=False),
        sa.Column("row_index", sa.Integer(), nullable=False),
        sa.Column("column_index", sa.Integer(), nullable=False),
        sa.Column("row_span", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("column_span", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("text_sha256", sa.String(64), nullable=False),
        sa.Column("x0_mpt", sa.Integer(), nullable=False),
        sa.Column("y0_mpt", sa.Integer(), nullable=False),
        sa.Column("x1_mpt", sa.Integer(), nullable=False),
        sa.Column("y1_mpt", sa.Integer(), nullable=False),
        sa.Column("confidence_bps", sa.Integer()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "document_page_id",
            "table_index",
            "row_index",
            "column_index",
            name="uq_document_table_cell_position",
        ),
        sa.CheckConstraint(
            "table_index >= 0 AND row_index >= 0 AND column_index >= 0",
            name="ck_document_table_cell_index",
        ),
        sa.CheckConstraint(
            "row_span >= 1 AND column_span >= 1", name="ck_document_table_cell_span"
        ),
        sa.CheckConstraint(
            "x0_mpt >= 0 AND y0_mpt >= 0 AND x1_mpt > x0_mpt AND y1_mpt > y0_mpt",
            name="ck_document_table_cell_box",
        ),
    )

    op.add_column("claim", sa.Column("derived_from_claim_id", _uuid()))
    op.add_column("claim", sa.Column("confidence_bps", sa.Integer()))
    op.create_foreign_key(
        "fk_claim_derived_from",
        "claim",
        "claim",
        ["derived_from_claim_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_check_constraint(
        "ck_claim_confidence",
        "claim",
        "confidence_bps IS NULL OR confidence_bps BETWEEN 0 AND 10000",
    )
    op.add_column("claim_evidence", sa.Column("locator_type", sa.String(30)))
    op.add_column("claim_evidence", sa.Column("derived_from_evidence_id", _uuid()))
    op.add_column("claim_evidence", sa.Column("page_number", sa.Integer()))
    op.add_column("claim_evidence", sa.Column("document_text_block_id", _uuid()))
    op.add_column("claim_evidence", sa.Column("document_table_cell_id", _uuid()))
    op.add_column("claim_evidence", sa.Column("x0_mpt", sa.Integer()))
    op.add_column("claim_evidence", sa.Column("y0_mpt", sa.Integer()))
    op.add_column("claim_evidence", sa.Column("x1_mpt", sa.Integer()))
    op.add_column("claim_evidence", sa.Column("y1_mpt", sa.Integer()))
    op.add_column("claim_evidence", sa.Column("confidence_bps", sa.Integer()))
    op.create_foreign_key(
        "fk_evidence_derived_from",
        "claim_evidence",
        "claim_evidence",
        ["derived_from_evidence_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_evidence_text_block",
        "claim_evidence",
        "document_text_block",
        ["document_text_block_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_evidence_table_cell",
        "claim_evidence",
        "document_table_cell",
        ["document_table_cell_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.alter_column("claim_evidence", "paragraph_id", existing_type=sa.String(100), nullable=True)
    op.alter_column("claim_evidence", "char_start", existing_type=sa.Integer(), nullable=True)
    op.alter_column("claim_evidence", "char_end", existing_type=sa.Integer(), nullable=True)
    op.create_check_constraint(
        "ck_evidence_locator_type",
        "claim_evidence",
        "locator_type IS NULL OR locator_type IN "
        "('HTML_PARAGRAPH','PDF_TEXT','PDF_OCR','PDF_TABLE_CELL')",
    )
    op.create_check_constraint(
        "ck_evidence_pdf_page",
        "claim_evidence",
        "page_number IS NULL OR page_number BETWEEN 1 AND 10000",
    )
    op.create_check_constraint(
        "ck_evidence_pdf_box",
        "claim_evidence",
        "x0_mpt IS NULL OR (x0_mpt >= 0 AND y0_mpt >= 0 AND x1_mpt > x0_mpt AND y1_mpt > y0_mpt)",
    )
    op.create_check_constraint(
        "ck_evidence_confidence",
        "claim_evidence",
        "confidence_bps IS NULL OR confidence_bps BETWEEN 0 AND 10000",
    )
    op.add_column("processing_run", sa.Column("normalized_text_sha256", sa.String(64)))
    op.add_column("processing_run", sa.Column("semantic_body_sha256", sa.String(64)))
    op.add_column("processing_run", sa.Column("metadata_sha256", sa.String(64)))
    op.add_column("processing_run", sa.Column("page_count", sa.Integer()))
    op.add_column("processing_run", sa.Column("ocr_page_count", sa.Integer()))
    op.add_column("processing_run", sa.Column("ocr_usable_page_count", sa.Integer()))
    op.add_column("processing_run", sa.Column("low_confidence_critical_count", sa.Integer()))

    op.create_table(
        "version_change",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column(
            "document_id",
            _uuid(),
            sa.ForeignKey("document.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "from_document_version_id",
            _uuid(),
            sa.ForeignKey("document_version.id", ondelete="RESTRICT"),
        ),
        sa.Column(
            "to_document_version_id",
            _uuid(),
            sa.ForeignKey("document_version.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("change_type", sa.String(30), nullable=False),
        sa.Column("resolved_change_type", sa.String(30)),
        sa.Column("material", sa.Boolean(), nullable=False),
        sa.Column("review_state", sa.String(30), nullable=False),
        sa.Column("raw_sha256", sa.String(64), nullable=False),
        sa.Column("normalized_text_sha256", sa.String(64), nullable=False),
        sa.Column("semantic_body_sha256", sa.String(64), nullable=False),
        sa.Column("metadata_sha256", sa.String(64), nullable=False),
        sa.Column("changed_token_count", sa.Integer(), nullable=False),
        sa.Column("changed_token_ratio_bps", sa.Integer(), nullable=False),
        sa.Column("page_diffs", JSON, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column(
            "critical_field_diffs", JSON, nullable=False, server_default=sa.text("'[]'::jsonb")
        ),
        sa.Column("classifier_version", sa.String(50), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("to_document_version_id", name="uq_version_change_to_version"),
        sa.CheckConstraint(
            "change_type IN ('INITIAL','METADATA_ONLY','CONTENT_UPDATE','CORRECTION',"
            "'AMENDMENT','REPLACEMENT','WITHDRAWAL')",
            name="ck_version_change_type",
        ),
        sa.CheckConstraint(
            "resolved_change_type IS NULL OR resolved_change_type IN "
            "('CORRECTION','AMENDMENT','REPLACEMENT','WITHDRAWAL')",
            name="ck_version_change_resolved_type",
        ),
        sa.CheckConstraint(
            "review_state IN ('DETECTED','NO_REVIEW_REQUIRED','RE_REVIEW_PENDING',"
            "'APPROVED','REJECTED')",
            name="ck_version_change_review_state",
        ),
        sa.CheckConstraint("changed_token_count >= 0", name="ck_version_change_token_count"),
        sa.CheckConstraint(
            "changed_token_ratio_bps BETWEEN 0 AND 10000",
            name="ck_version_change_token_ratio",
        ),
    )

    op.create_table(
        "version_change_state_event",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column(
            "version_change_id",
            _uuid(),
            sa.ForeignKey("version_change.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("state", sa.String(30), nullable=False),
        sa.Column("change_type", sa.String(30), nullable=False),
        sa.Column("material", sa.Boolean(), nullable=False),
        sa.Column("resolved_change_type", sa.String(30)),
        sa.Column("reviewer_id", _uuid()),
        sa.Column("reason", sa.String(1000), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "state IN ('DETECTED','NO_REVIEW_REQUIRED','RE_REVIEW_PENDING','APPROVED','REJECTED')",
            name="ck_version_change_event_state",
        ),
        sa.CheckConstraint(
            "change_type IN ('INITIAL','METADATA_ONLY','CONTENT_UPDATE','CORRECTION',"
            "'AMENDMENT','REPLACEMENT','WITHDRAWAL')",
            name="ck_version_change_event_type",
        ),
        sa.CheckConstraint(
            "resolved_change_type IS NULL OR resolved_change_type IN "
            "('CORRECTION','AMENDMENT','REPLACEMENT','WITHDRAWAL')",
            name="ck_version_change_event_resolved_type",
        ),
    )
    op.create_index(
        "ix_version_change_state_created",
        "version_change_state_event",
        ["version_change_id", "created_at"],
    )

    op.create_table(
        "document_relation_candidate",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column(
            "item_id",
            _uuid(),
            sa.ForeignKey("intelligence_item.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "document_version_id",
            _uuid(),
            sa.ForeignKey("document_version.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("relation_type", sa.String(20), nullable=False),
        sa.Column("target_document_id", _uuid(), sa.ForeignKey("document.id", ondelete="RESTRICT")),
        sa.Column("target_title", sa.String(500), nullable=False),
        sa.Column("target_document_number", sa.String(200)),
        sa.Column(
            "evidence_id",
            _uuid(),
            sa.ForeignKey("claim_evidence.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "relation_type IN ('AMENDS','SUPERSEDES')", name="ck_relation_candidate_type"
        ),
    )

    op.create_table(
        "document_relation_decision",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column(
            "candidate_id",
            _uuid(),
            sa.ForeignKey("document_relation_candidate.id", ondelete="RESTRICT"),
            nullable=False,
            unique=True,
        ),
        sa.Column("action", sa.String(30), nullable=False),
        sa.Column("target_document_id", _uuid(), sa.ForeignKey("document.id", ondelete="RESTRICT")),
        sa.Column("reviewer_id", _uuid(), nullable=False),
        sa.Column("reason", sa.String(1000), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "action IN ('ACCEPT','REJECT','CONFIRM_UNRESOLVED')",
            name="ck_document_relation_decision_action",
        ),
        sa.CheckConstraint(
            "(action = 'ACCEPT' AND target_document_id IS NOT NULL) OR "
            "(action <> 'ACCEPT' AND target_document_id IS NULL)",
            name="ck_document_relation_decision_target",
        ),
    )

    op.create_table(
        "document_relation",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column(
            "candidate_id",
            _uuid(),
            sa.ForeignKey("document_relation_candidate.id", ondelete="RESTRICT"),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "source_document_id",
            _uuid(),
            sa.ForeignKey("document.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "target_document_id",
            _uuid(),
            sa.ForeignKey("document.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("relation_type", sa.String(20), nullable=False),
        sa.Column("confirmed_by", _uuid(), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "relation_type IN ('AMENDS','SUPERSEDES')", name="ck_document_relation_type"
        ),
        sa.CheckConstraint(
            "source_document_id <> target_document_id", name="ck_document_relation_distinct"
        ),
    )

    op.create_table(
        "regulation_status_candidate",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column(
            "item_id",
            _uuid(),
            sa.ForeignKey("intelligence_item.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "document_version_id",
            _uuid(),
            sa.ForeignKey("document_version.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("candidate_status", sa.String(30), nullable=False),
        sa.Column(
            "evidence_id",
            _uuid(),
            sa.ForeignKey("claim_evidence.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "candidate_status IN ('DRAFT','NOT_EFFECTIVE','EFFECTIVE','AMENDED',"
            "'REPEALED','SUPERSEDED','EXPIRED')",
            name="ck_regulation_status_candidate",
        ),
    )

    op.create_table(
        "regulation_status_decision",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column(
            "candidate_id",
            _uuid(),
            sa.ForeignKey("regulation_status_candidate.id", ondelete="RESTRICT"),
            nullable=False,
            unique=True,
        ),
        sa.Column("action", sa.String(20), nullable=False),
        sa.Column("reviewer_id", _uuid(), nullable=False),
        sa.Column("reason", sa.String(1000), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "action IN ('ACCEPT','REJECT')",
            name="ck_regulation_status_decision_action",
        ),
    )

    op.create_table(
        "content_lifecycle_event",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column(
            "item_id",
            _uuid(),
            sa.ForeignKey("intelligence_item.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("target_type", sa.String(40), nullable=False),
        sa.Column("target_id", _uuid(), nullable=False),
        sa.Column("state", sa.String(40), nullable=False),
        sa.Column(
            "cause_version_change_id",
            _uuid(),
            sa.ForeignKey("version_change.id", ondelete="RESTRICT"),
        ),
        sa.Column("actor_id", _uuid()),
        sa.Column("reason", sa.String(1000), nullable=False),
        sa.Column("metadata", JSON, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "target_type IN ('CLAIM','SUMMARY','PUBLICATION_REVISION','RELATION_CANDIDATE',"
            "'REGULATION_STATUS_CANDIDATE','ITEM')",
            name="ck_content_lifecycle_target",
        ),
        sa.CheckConstraint(
            "state IN ('ACTIVE','UPDATE_DETECTED','RE_REVIEW_PENDING','SUPERSEDED',"
            "'WITHDRAWN','ACCEPTED','REJECTED','CONFIRMED_UNRESOLVED')",
            name="ck_content_lifecycle_state",
        ),
    )
    op.create_index(
        "ix_content_lifecycle_target_created",
        "content_lifecycle_event",
        ["target_type", "target_id", "created_at"],
    )

    op.create_table(
        "derived_summary",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column(
            "item_id",
            _uuid(),
            sa.ForeignKey("intelligence_item.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "document_version_id",
            _uuid(),
            sa.ForeignKey("document_version.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("template_version", sa.String(100), nullable=False),
        sa.Column("text", sa.String(500), nullable=False),
        sa.Column("claim_ids", postgresql.ARRAY(_uuid()), nullable=False),
        sa.Column(
            "derived_from_summary_id",
            _uuid(),
            sa.ForeignKey("derived_summary.id", ondelete="RESTRICT"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "item_id",
            "document_version_id",
            "template_version",
            name="uq_derived_summary_item_version_template",
        ),
    )

    op.create_table(
        "source_url_check",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column(
            "document_id", _uuid(), sa.ForeignKey("document.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("outcome", sa.String(20), nullable=False),
        sa.Column("http_status", sa.Integer()),
        sa.Column("error_code", sa.String(100)),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "outcome IN ('AVAILABLE','NOT_FOUND','GONE','TIMEOUT','SERVER_ERROR')",
            name="ck_source_url_check_outcome",
        ),
    )
    op.create_index(
        "ix_source_url_check_document_checked",
        "source_url_check",
        ["document_id", "checked_at"],
    )

    op.create_table(
        "outbox_event",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("aggregate_type", sa.String(50), nullable=False),
        sa.Column("aggregate_id", _uuid(), nullable=False),
        sa.Column("payload", JSON, nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="PENDING"),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True)),
        sa.Column("last_error_code", sa.String(100)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('PENDING','PROCESSING','PROCESSED','FAILED','DEAD_LETTER')",
            name="ck_outbox_status",
        ),
        sa.CheckConstraint("attempt_count >= 0", name="ck_outbox_attempts"),
    )
    op.create_index("ix_outbox_status_available", "outbox_event", ["status", "available_at"])

    immutable_tables = tuple(table for table in ROUND03_TABLES if table != "outbox_event")
    for table_name in immutable_tables:
        op.execute(
            f"""
            CREATE TRIGGER trg_{table_name}_immutable
            BEFORE UPDATE OR DELETE ON {table_name}
            FOR EACH ROW EXECUTE FUNCTION reject_immutable_source_vault_change()
            """
        )

    op.execute(
        """
        INSERT INTO raw_object_security_fact (
            id, raw_object_id, status, detected_mime, rule_version, reason_code, created_at
        )
        SELECT
            ('019b0000-0000-7000-8000-' || substr(md5('round03-raw:' || id::text), 1, 12))::uuid,
            id, scan_status, detected_mime, 'legacy-source-vault-1.0.0',
            'BACKFILLED_ROUND03', created_at
        FROM raw_object
        ON CONFLICT (raw_object_id, rule_version) DO NOTHING
        """
    )
    op.execute(
        """
        INSERT INTO document_version_state_event (
            id, document_version_id, state, reason_code, actor_type, created_at
        )
        SELECT
            (
                '019b0000-0000-7000-8001-'
                || substr(md5('round03-version:' || id::text), 1, 12)
            )::uuid,
            id, 'READY', 'BACKFILLED_ROUND03', 'SYSTEM', acquired_at
        FROM document_version
        """
    )

    _configure_roles()


def _configure_roles() -> None:
    all_tables = ", ".join(ROUND03_TABLES)
    worker_insert_tables = (
        "raw_object_security_fact, document_version_state_event, document_page, "
        "document_text_block, document_table_cell, version_change, version_change_state_event, "
        "document_relation_candidate, regulation_status_candidate, source_url_check, outbox_event"
    )
    publisher_tables = (
        "content_lifecycle_event, derived_summary, document_relation, "
        "version_change_state_event, document_relation_decision, regulation_status_decision"
    )
    op.execute(f"GRANT SELECT ON {all_tables} TO srbg_runtime, srbg_publication_writer")
    op.execute("GRANT SELECT ON document_attachment TO srbg_publication_writer")
    op.execute(f"GRANT INSERT ON {worker_insert_tables} TO srbg_worker_role")
    op.execute(f"GRANT INSERT ON {worker_insert_tables} TO srbg_runtime")
    op.execute(f"GRANT INSERT ON {publisher_tables} TO srbg_publication_writer")
    op.execute("GRANT SELECT, INSERT, UPDATE ON outbox_event TO srbg_publication_writer")
    op.execute("GRANT INSERT ON version_change_state_event TO srbg_publication_writer")
    op.execute("GRANT INSERT ON review_task TO srbg_publication_writer")
    op.execute("GRANT UPDATE ON safety_regulation_profile TO srbg_publication_writer")
    op.execute("REVOKE INSERT, UPDATE, DELETE ON content_lifecycle_event FROM PUBLIC")
    op.execute("REVOKE INSERT, UPDATE, DELETE ON content_lifecycle_event FROM srbg_runtime")
    op.execute("REVOKE INSERT, UPDATE, DELETE ON content_lifecycle_event FROM srbg_worker_role")
    op.execute("GRANT SELECT, INSERT ON content_lifecycle_event TO srbg_publication_writer")


def downgrade() -> None:
    for constraint_name, table_name in (
        ("ck_evidence_confidence", "claim_evidence"),
        ("ck_evidence_pdf_box", "claim_evidence"),
        ("ck_evidence_pdf_page", "claim_evidence"),
        ("ck_evidence_locator_type", "claim_evidence"),
        ("fk_evidence_derived_from", "claim_evidence"),
        ("fk_evidence_table_cell", "claim_evidence"),
        ("fk_evidence_text_block", "claim_evidence"),
    ):
        op.execute(
            sa.text(f'ALTER TABLE "{table_name}" DROP CONSTRAINT IF EXISTS "{constraint_name}"')
        )
    for column_name in (
        "confidence_bps",
        "y1_mpt",
        "x1_mpt",
        "y0_mpt",
        "x0_mpt",
        "document_table_cell_id",
        "document_text_block_id",
        "page_number",
        "locator_type",
    ):
        op.drop_column("claim_evidence", column_name)
    op.execute(sa.text("ALTER TABLE claim_evidence DROP COLUMN IF EXISTS derived_from_evidence_id"))
    op.execute(sa.text("ALTER TABLE claim_evidence DISABLE TRIGGER trg_claim_evidence_immutable"))
    op.execute(
        sa.text(
            "UPDATE claim_evidence "
            "SET paragraph_id = COALESCE(paragraph_id, 'round03-pdf-rollback'), "
            "char_start = COALESCE(char_start, 0), "
            "char_end = COALESCE(char_end, GREATEST(COALESCE(char_start, 0) + 1, 1))"
        )
    )
    op.execute(sa.text("ALTER TABLE claim_evidence ENABLE TRIGGER trg_claim_evidence_immutable"))
    op.alter_column("claim_evidence", "char_end", existing_type=sa.Integer(), nullable=False)
    op.alter_column("claim_evidence", "char_start", existing_type=sa.Integer(), nullable=False)
    op.alter_column("claim_evidence", "paragraph_id", existing_type=sa.String(100), nullable=False)
    op.drop_constraint("ck_claim_confidence", "claim", type_="check")
    op.drop_constraint("fk_claim_derived_from", "claim", type_="foreignkey")
    op.drop_column("claim", "confidence_bps")
    op.drop_column("claim", "derived_from_claim_id")
    for column_name in (
        "low_confidence_critical_count",
        "ocr_usable_page_count",
        "ocr_page_count",
        "page_count",
        "metadata_sha256",
        "semantic_body_sha256",
        "normalized_text_sha256",
    ):
        op.drop_column("processing_run", column_name)
    for table_name in reversed(ROUND03_TABLES):
        op.execute(sa.text(f'DROP TABLE IF EXISTS "{table_name}"'))
    op.drop_constraint("ck_document_attachment_security", "document_attachment", type_="check")
    op.drop_constraint("ck_document_attachment_size", "document_attachment", type_="check")
    op.drop_constraint("ck_document_attachment_depth", "document_attachment", type_="check")
    op.drop_constraint("fk_document_attachment_parent", "document_attachment", type_="foreignkey")
    for column_name in (
        "security_status",
        "byte_size",
        "detected_mime",
        "depth",
        "normalized_path",
        "parent_attachment_id",
    ):
        op.drop_column("document_attachment", column_name)
