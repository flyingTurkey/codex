"""Round 02 safety regulation acquisition, review, and publication facts.

Revision ID: 0003_safety_publication
Revises: 0002_source_vault
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003_safety_publication"
down_revision: str | None = "0002_source_vault"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ROUND02_TABLES = (
    "source_checkpoint",
    "fetch_run",
    "fetch_record",
    "processing_run",
    "intelligence_item",
    "safety_regulation_profile",
    "claim",
    "claim_evidence",
    "review_task",
    "publication",
    "publication_revision",
)


def _uuid() -> postgresql.UUID:
    return postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.add_column(
        "document",
        sa.Column(
            "admission_fixture",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
    )
    op.create_table(
        "source_checkpoint",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column(
            "source_connector_id",
            _uuid(),
            sa.ForeignKey("source_connector.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("cursor", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("etag", sa.String(500)),
        sa.Column("last_modified", sa.String(500)),
        sa.Column("last_success_at", sa.DateTime(timezone=True)),
        sa.Column("consecutive_failures", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("circuit_open_until", sa.DateTime(timezone=True)),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("consecutive_failures >= 0", name="ck_checkpoint_failures"),
    )

    op.create_table(
        "fetch_run",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column(
            "source_connector_id",
            _uuid(),
            sa.ForeignKey("source_connector.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("trigger", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("discovered_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("fetched_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_code", sa.String(100)),
        sa.Column("request_id", sa.String(100), nullable=False),
        sa.CheckConstraint(
            "trigger IN ('SCHEDULED','MANUAL','FIXTURE')", name="ck_fetch_run_trigger"
        ),
        sa.CheckConstraint(
            "status IN ('RUNNING','SUCCEEDED','PARTIAL','FAILED','CIRCUIT_OPEN')",
            name="ck_fetch_run_status",
        ),
    )
    op.create_index(
        "ix_fetch_run_connector_started", "fetch_run", ["source_connector_id", "started_at"]
    )

    op.create_table(
        "fetch_record",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column(
            "fetch_run_id",
            _uuid(),
            sa.ForeignKey("fetch_run.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "source_connector_id",
            _uuid(),
            sa.ForeignKey("source_connector.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("external_id", sa.String(300), nullable=False),
        sa.Column("canonical_url", sa.String(2048), nullable=False),
        sa.Column("discovered_title", sa.String(500), nullable=False),
        sa.Column("discovered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("http_status", sa.Integer()),
        sa.Column("etag", sa.String(500)),
        sa.Column("last_modified", sa.String(500)),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("next_retry_at", sa.DateTime(timezone=True)),
        sa.Column("error_code", sa.String(100)),
        sa.Column("document_id", _uuid(), sa.ForeignKey("document.id", ondelete="SET NULL")),
        sa.Column(
            "document_version_id",
            _uuid(),
            sa.ForeignKey("document_version.id", ondelete="SET NULL"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "source_connector_id", "external_id", name="uq_fetch_record_connector_external"
        ),
        sa.CheckConstraint("attempt_count >= 0", name="ck_fetch_record_attempts"),
        sa.CheckConstraint(
            "status IN ('DISCOVERED','FETCHED','NOT_MODIFIED','RETRY_PENDING','FAILED')",
            name="ck_fetch_record_status",
        ),
    )
    op.create_index("ix_fetch_record_run_status", "fetch_record", ["fetch_run_id", "status"])

    op.create_table(
        "processing_run",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column(
            "fetch_record_id",
            _uuid(),
            sa.ForeignKey("fetch_record.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "document_version_id",
            _uuid(),
            sa.ForeignKey("document_version.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("parser_name", sa.String(100), nullable=False),
        sa.Column("parser_version", sa.String(50), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("error_code", sa.String(100)),
        sa.Column("paragraphs", postgresql.JSONB(astext_type=sa.Text())),
        sa.Column("semantic_safety_scan_pass", sa.Boolean()),
        sa.Column("prompt_injection_detected", sa.Boolean()),
        sa.Column("security_resolution_status", sa.String(40)),
        sa.Column("security_scanner_version", sa.String(50)),
        sa.UniqueConstraint(
            "document_version_id",
            "parser_name",
            "parser_version",
            name="uq_processing_version_parser",
        ),
        sa.CheckConstraint(
            "status IN ('RUNNING','SUCCEEDED','FAILED')", name="ck_processing_status"
        ),
    )

    op.create_table(
        "intelligence_item",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column(
            "source_id", _uuid(), sa.ForeignKey("source.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column(
            "primary_document_id",
            _uuid(),
            sa.ForeignKey("document.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "current_document_version_id",
            _uuid(),
            sa.ForeignKey("document_version.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("item_type", sa.String(50), nullable=False),
        sa.Column("channel", sa.String(20), nullable=False),
        sa.Column("risk_level", sa.String(10), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("original_url", sa.String(2048), nullable=False),
        sa.Column("source_published_at", sa.DateTime(timezone=True)),
        sa.Column("first_discovered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("activity_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("processing_status", sa.String(30), nullable=False),
        sa.Column("review_status", sa.String(20), nullable=False),
        sa.Column("submitted_by", _uuid(), nullable=False),
        sa.Column("is_demo", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("publishable", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("primary_document_id", name="uq_intelligence_item_document"),
        sa.CheckConstraint("item_type = 'SAFETY_REGULATION'", name="ck_round02_item_type"),
        sa.CheckConstraint("channel = 'SAFETY'", name="ck_round02_item_channel"),
        sa.CheckConstraint("risk_level = 'R3'", name="ck_round02_item_risk"),
        sa.CheckConstraint(
            "review_status IN ('PENDING','APPROVED','REJECTED')",
            name="ck_intelligence_review_status",
        ),
    )
    op.create_index("ix_intelligence_feed_activity", "intelligence_item", ["activity_at", "id"])

    op.create_table(
        "safety_regulation_profile",
        sa.Column(
            "item_id",
            _uuid(),
            sa.ForeignKey("intelligence_item.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("classification", sa.String(50), nullable=False),
        sa.Column("document_number", sa.String(200), nullable=False),
        sa.Column("issuing_authority", sa.String(200), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("effective_at", sa.DateTime(timezone=True)),
        sa.Column("regulation_status", sa.String(30), nullable=False, server_default="UNKNOWN"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "classification IN ('LAW','ADMINISTRATIVE_REGULATION','DEPARTMENT_RULE',"
            "'NORMATIVE_DOCUMENT','STANDARD_OR_GUIDE')",
            name="ck_regulation_classification",
        ),
        sa.CheckConstraint(
            "regulation_status IN ('DRAFT','NOT_EFFECTIVE','EFFECTIVE','AMENDED',"
            "'REPEALED','SUPERSEDED','EXPIRED','UNKNOWN')",
            name="ck_regulation_status",
        ),
    )

    op.create_table(
        "claim",
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
        sa.Column("claim_type", sa.String(100), nullable=False),
        sa.Column("subject", sa.String(500), nullable=False),
        sa.Column("predicate", sa.String(100), nullable=False),
        sa.Column("literal_value", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("verification_status", sa.String(20), nullable=False),
        sa.Column("critical", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "item_id", "document_version_id", "claim_type", name="uq_claim_item_version_type"
        ),
        sa.CheckConstraint(
            "verification_status IN ('CANDIDATE','ACCEPTED','REJECTED')",
            name="ck_claim_verification_status",
        ),
    )

    op.create_table(
        "claim_evidence",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column(
            "claim_id", _uuid(), sa.ForeignKey("claim.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "document_version_id",
            _uuid(),
            sa.ForeignKey("document_version.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("evidence_role", sa.String(50), nullable=False),
        sa.Column("paragraph_id", sa.String(100), nullable=False),
        sa.Column("char_start", sa.Integer(), nullable=False),
        sa.Column("char_end", sa.Integer(), nullable=False),
        sa.Column("excerpt", sa.Text(), nullable=False),
        sa.Column("excerpt_sha256", sa.String(64), nullable=False),
        sa.Column("original_url", sa.String(2048), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("char_start >= 0 AND char_end > char_start", name="ck_evidence_range"),
        sa.CheckConstraint("excerpt_sha256 ~ '^[a-f0-9]{64}$'", name="ck_evidence_sha256"),
    )
    op.create_index("ix_claim_evidence_claim", "claim_evidence", ["claim_id"])

    op.create_table(
        "review_task",
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
        sa.Column(
            "source_policy_id",
            _uuid(),
            sa.ForeignKey("source_policy.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("risk_level", sa.String(10), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("submitted_by", _uuid(), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("assigned_to", _uuid()),
        sa.Column("decided_by", _uuid()),
        sa.Column("decided_at", sa.DateTime(timezone=True)),
        sa.Column("decision_reason", sa.String(1000)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("item_id", "document_version_id", name="uq_review_item_version"),
        sa.CheckConstraint("risk_level = 'R3'", name="ck_review_risk_level"),
        sa.CheckConstraint("status IN ('PENDING','APPROVED','REJECTED')", name="ck_review_status"),
        sa.CheckConstraint(
            "decided_by IS NULL OR decided_by <> submitted_by",
            name="ck_review_duties_separated",
        ),
    )
    op.create_index("ix_review_task_queue", "review_task", ["status", "submitted_at"])

    op.create_table(
        "publication",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column(
            "item_id",
            _uuid(),
            sa.ForeignKey("intelligence_item.id", ondelete="RESTRICT"),
            nullable=False,
            unique=True,
        ),
        sa.Column("current_revision_id", _uuid()),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.Column("withdrawn_at", sa.DateTime(timezone=True)),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("status IN ('PUBLISHED','WITHDRAWN')", name="ck_publication_status"),
    )

    op.create_table(
        "publication_revision",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column(
            "publication_id",
            _uuid(),
            sa.ForeignKey("publication.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("revision_number", sa.Integer(), nullable=False),
        sa.Column(
            "document_version_id",
            _uuid(),
            sa.ForeignKey("document_version.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "source_policy_id",
            _uuid(),
            sa.ForeignKey("source_policy.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("source_policy_sha256", sa.String(64), nullable=False),
        sa.Column(
            "review_task_id",
            _uuid(),
            sa.ForeignKey("review_task.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("evaluation", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("evaluation_sha256", sa.String(64), nullable=False),
        sa.Column("action", sa.String(20), nullable=False),
        sa.Column("valid", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_by", _uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "publication_id", "revision_number", name="uq_publication_revision_number"
        ),
        sa.CheckConstraint("revision_number >= 1", name="ck_publication_revision_number"),
        sa.CheckConstraint(
            "action IN ('PUBLISH','REVISE','WITHDRAW','REPUBLISH')",
            name="ck_publication_revision_action",
        ),
        sa.CheckConstraint(
            "source_policy_sha256 ~ '^[a-f0-9]{64}$'", name="ck_revision_policy_sha256"
        ),
        sa.CheckConstraint(
            "evaluation_sha256 ~ '^[a-f0-9]{64}$'", name="ck_revision_evaluation_sha256"
        ),
    )
    op.create_foreign_key(
        "fk_publication_current_revision",
        "publication",
        "publication_revision",
        ["current_revision_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    for table_name in ("claim", "claim_evidence", "publication_revision"):
        op.execute(
            f"""
            CREATE TRIGGER trg_{table_name}_immutable
            BEFORE UPDATE OR DELETE ON {table_name}
            FOR EACH ROW EXECUTE FUNCTION reject_immutable_source_vault_change()
            """
        )

    op.execute(
        """
        INSERT INTO source_connector (id, source_id, connector_type, config, enabled, created_at)
        SELECT
            '019b0000-0000-7000-8000-000000020006'::uuid,
            id,
            'MEM_SAFETY_REGULATION_HTML',
            jsonb_build_object(
                'list_url',
                'https://www.mem.gov.cn/gk/zfxxgkpt/fdzdgknr/gz11/index.shtml',
                'allowed_hosts',
                jsonb_build_array('www.mem.gov.cn')
            ),
            false,
            now()
        FROM source
        WHERE registry_code = 'GOV-006'
        ON CONFLICT (source_id) DO NOTHING
        """
    )

    _configure_roles()


def _configure_roles() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'srbg_runtime') THEN
                CREATE ROLE srbg_runtime NOLOGIN;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'srbg_publication_writer') THEN
                CREATE ROLE srbg_publication_writer NOLOGIN;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'srbg_api_role') THEN
                CREATE ROLE srbg_api_role NOLOGIN;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'srbg_worker_role') THEN
                CREATE ROLE srbg_worker_role NOLOGIN;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'srbg_admin_role') THEN
                CREATE ROLE srbg_admin_role NOLOGIN;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'srbg_model_role') THEN
                CREATE ROLE srbg_model_role NOLOGIN;
            END IF;
        END
        $$
        """
    )
    op.execute("GRANT USAGE ON SCHEMA public TO srbg_runtime, srbg_publication_writer")
    op.execute(
        "GRANT srbg_runtime TO srbg_api_role, srbg_worker_role, "
        "srbg_admin_role, srbg_model_role"
    )
    op.execute("REVOKE INSERT, UPDATE, DELETE ON publication FROM PUBLIC")
    op.execute("REVOKE INSERT, UPDATE, DELETE ON publication_revision FROM PUBLIC")
    op.execute("REVOKE INSERT, UPDATE, DELETE ON publication FROM srbg_runtime")
    op.execute("REVOKE INSERT, UPDATE, DELETE ON publication_revision FROM srbg_runtime")
    op.execute("GRANT SELECT ON publication, publication_revision TO srbg_runtime")
    op.execute("GRANT SELECT, INSERT, UPDATE ON publication TO srbg_publication_writer")
    op.execute("GRANT SELECT, INSERT ON publication_revision TO srbg_publication_writer")
    op.execute(
        "GRANT SELECT ON source, source_policy, source_onboarding_record, source_connector, "
        "raw_object, document, document_version, processing_run, intelligence_item, "
        "safety_regulation_profile, claim, claim_evidence, review_task "
        "TO srbg_publication_writer"
    )
    op.execute("GRANT UPDATE ON review_task, intelligence_item TO srbg_publication_writer")
    op.execute("GRANT SELECT, INSERT ON audit_log TO srbg_publication_writer")
    op.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE ON source_checkpoint, fetch_run, fetch_record, "
        "processing_run, intelligence_item, safety_regulation_profile TO srbg_runtime"
    )
    op.execute("GRANT SELECT, INSERT ON claim, claim_evidence, review_task TO srbg_runtime")
    op.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE ON source, source_policy, source_connector, "
        "raw_object, document, document_version, document_attachment, "
        "source_onboarding_record, audit_log TO srbg_runtime"
    )


def downgrade() -> None:
    op.drop_constraint("fk_publication_current_revision", "publication", type_="foreignkey")
    for table_name in reversed(ROUND02_TABLES):
        op.drop_table(table_name)
    op.execute("ALTER TABLE document DROP COLUMN IF EXISTS admission_fixture")
