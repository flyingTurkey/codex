"""Round 04 safety-case events, protected facts, conflicts, and audit.

Revision ID: 0005_safety_case_lifecycle
Revises: 0004_pdf_ocr_versioning
"""

from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005_safety_case_lifecycle"
down_revision: str | None = "0004_pdf_ocr_versioning"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JSON = postgresql.JSONB(astext_type=sa.Text())

ROUND04_TABLES = (
    "safety_case_profile",
    "event",
    "event_item_candidate",
    "event_item_decision",
    "event_item",
    "event_relation_candidate",
    "event_relation_decision",
    "event_relation",
    "claim_field_decision",
    "claim_conflict",
    "claim_conflict_decision",
    "safety_case_audit_event",
)

REPORT_STAGES = (
    "INITIAL_REPORT",
    "FOLLOW_UP_REPORT",
    "FINAL_INVESTIGATION",
    "ENFORCEMENT",
    "RECTIFICATION",
)
INCIDENT_STATUSES = (
    "UNVERIFIED_LEAD",
    "INITIAL_OFFICIAL_REPORT",
    "UNDER_INVESTIGATION",
    "FINAL_INVESTIGATION_REPORT",
    "ENFORCEMENT_DECISION",
    "RECTIFICATION_FOLLOW_UP",
    "CLOSED",
    "CORRECTED",
    "WITHDRAWN",
)
RELATION_TYPES = (
    "FOLLOW_UP",
    "INVESTIGATES",
    "PENALIZES",
    "RECTIFIES",
    "CORRECTS",
)
PROTECTED_FIELDS = (
    "deaths",
    "injuries",
    "loss_amount_minor",
    "official_direct_causes",
    "responsibility_findings",
)
ROUND04_SOURCE_SEEDS = (
    (
        "GOV-019",
        "大埔县人民政府",
        "https://www.dabu.gov.cn/",
        "SAFETY",
        "government",
        "A1",
        "P0",
        "html",
        15,
    ),
    (
        "GOV-020",
        "广东省应急管理厅事故调查报告",
        "https://yjgl.gd.gov.cn/gk/zdlyxxgk/sgdcbg/",
        "SAFETY",
        "government",
        "A0",
        "P0",
        "html_pdf",
        30,
    ),
    (
        "GOV-021",
        "广东省应急管理厅",
        "https://yjgl.gd.gov.cn/",
        "SAFETY",
        "government",
        "A1",
        "P0",
        "html_pdf",
        30,
    ),
    (
        "GOV-022",
        "广东省纪委监委南粤清风网",
        "https://www.gdjct.gd.gov.cn/",
        "SAFETY",
        "government",
        "A1",
        "P0",
        "html",
        60,
    ),
)


def _uuid() -> postgresql.UUID:
    return postgresql.UUID(as_uuid=True)


def _in(values: tuple[str, ...]) -> str:
    return ",".join(f"'{value}'" for value in values)


def upgrade() -> None:
    _expand_round02_constraints()
    _seed_round04_sources()
    _create_safety_case_profile()
    _create_event_tables()
    _create_claim_decision_tables()
    _create_audit_table()
    _create_safety_triggers()
    _create_safe_projection_views()
    _configure_roles_and_rls()


def _seed_round04_sources() -> None:
    source_table = sa.table(
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
    now = datetime.now(UTC)
    op.bulk_insert(
        source_table,
        [
            {
                "id": UUID(f"019b0000-0000-7000-8000-{4019 + index:012d}"),
                "registry_code": row[0],
                "name": row[1],
                "base_url": row[2],
                "channel": row[3],
                "source_type": row[4],
                "authority_level": row[5],
                "priority": row[6],
                "collection_method": row[7],
                "poll_interval_minutes": row[8],
                "owner": "source_ops",
                "state": "CANDIDATE",
                "enabled": False,
                "created_at": now,
                "updated_at": now,
            }
            for index, row in enumerate(ROUND04_SOURCE_SEEDS)
        ],
    )


def _expand_round02_constraints() -> None:
    op.drop_constraint("ck_round02_item_type", "intelligence_item", type_="check")
    op.drop_constraint("ck_round02_item_risk", "intelligence_item", type_="check")
    op.drop_constraint("ck_review_risk_level", "review_task", type_="check")
    op.create_check_constraint(
        "ck_round04_item_type",
        "intelligence_item",
        "item_type IN ('SAFETY_REGULATION','SAFETY_CASE')",
    )
    op.create_check_constraint(
        "ck_round04_item_risk",
        "intelligence_item",
        "risk_level IN ('R3','R4')",
    )
    op.create_check_constraint(
        "ck_round04_review_risk",
        "review_task",
        "risk_level IN ('R3','R4')",
    )


def _create_safety_case_profile() -> None:
    op.create_table(
        "safety_case_profile",
        sa.Column(
            "item_id",
            _uuid(),
            sa.ForeignKey("intelligence_item.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("report_stage", sa.String(30), nullable=False),
        sa.Column("accident_type", sa.String(100)),
        sa.Column("engineering_type", sa.String(100)),
        sa.Column("occurred_at", sa.DateTime(timezone=True)),
        sa.Column("region_code", sa.String(30)),
        sa.Column("region_name", sa.String(300)),
        sa.Column("project_name", sa.String(500)),
        sa.Column("subject_names", JSON, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("deaths", sa.Integer()),
        sa.Column("injuries", sa.Integer()),
        sa.Column("missing_count", sa.Integer()),
        sa.Column("loss_amount_minor", sa.BigInteger()),
        sa.Column("loss_currency", sa.String(3)),
        sa.Column("incident_status", sa.String(40), nullable=False),
        sa.Column("official_direct_causes", JSON),
        sa.Column("responsibility_findings", JSON),
        sa.Column("rectification_has_open_issues", sa.Boolean()),
        sa.Column(
            "similar_scenario_tags", JSON, nullable=False, server_default=sa.text("'[]'::jsonb")
        ),
        sa.Column(
            "prevention_measure_tags", JSON, nullable=False, server_default=sa.text("'[]'::jsonb")
        ),
        sa.Column(
            "privacy_status",
            sa.String(30),
            nullable=False,
            server_default="PENDING_REVIEW",
        ),
        sa.Column("privacy_reviewed_by", _uuid()),
        sa.Column("privacy_reviewed_at", sa.DateTime(timezone=True)),
        sa.Column(
            "reputational_risk_reviewed",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column("reputational_reviewed_by", _uuid()),
        sa.Column("reputational_reviewed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            f"report_stage IN ({_in(REPORT_STAGES)})",
            name="ck_safety_case_report_stage",
        ),
        sa.CheckConstraint(
            f"incident_status IN ({_in(INCIDENT_STATUSES)})",
            name="ck_safety_case_incident_status",
        ),
        sa.CheckConstraint(
            "deaths IS NULL OR deaths >= 0",
            name="ck_safety_case_deaths",
        ),
        sa.CheckConstraint(
            "injuries IS NULL OR injuries >= 0",
            name="ck_safety_case_injuries",
        ),
        sa.CheckConstraint(
            "missing_count IS NULL OR missing_count >= 0",
            name="ck_safety_case_missing",
        ),
        sa.CheckConstraint(
            "loss_amount_minor IS NULL OR loss_amount_minor >= 0",
            name="ck_safety_case_loss",
        ),
        sa.CheckConstraint(
            "(loss_amount_minor IS NULL AND loss_currency IS NULL) OR "
            "(loss_amount_minor IS NOT NULL AND loss_currency ~ '^[A-Z]{3}$')",
            name="ck_safety_case_loss_currency",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(subject_names) = 'array' "
            "AND jsonb_typeof(similar_scenario_tags) = 'array' "
            "AND jsonb_typeof(prevention_measure_tags) = 'array'",
            name="ck_safety_case_controlled_arrays",
        ),
        sa.CheckConstraint(
            "official_direct_causes IS NULL OR jsonb_typeof(official_direct_causes) = 'array'",
            name="ck_safety_case_causes_array",
        ),
        sa.CheckConstraint(
            "responsibility_findings IS NULL OR jsonb_typeof(responsibility_findings) = 'array'",
            name="ck_safety_case_responsibility_array",
        ),
        sa.CheckConstraint(
            "(official_direct_causes IS NULL AND responsibility_findings IS NULL) "
            "OR report_stage IN ('FINAL_INVESTIGATION','ENFORCEMENT')",
            name="ck_safety_case_formal_findings_stage",
        ),
        sa.CheckConstraint(
            "report_stage = 'RECTIFICATION' OR rectification_has_open_issues IS NULL",
            name="ck_safety_case_rectification_issues_stage",
        ),
        sa.CheckConstraint(
            "privacy_status IN ('PENDING_REVIEW','CLEAR','REDACTED_AND_APPROVED','BLOCKED')",
            name="ck_safety_case_privacy_status",
        ),
        sa.CheckConstraint(
            "(privacy_status = 'PENDING_REVIEW' "
            "AND privacy_reviewed_by IS NULL AND privacy_reviewed_at IS NULL) OR "
            "(privacy_status <> 'PENDING_REVIEW' "
            "AND privacy_reviewed_by IS NOT NULL AND privacy_reviewed_at IS NOT NULL)",
            name="ck_safety_case_privacy_review",
        ),
        sa.CheckConstraint(
            "(reputational_risk_reviewed = false "
            "AND reputational_reviewed_by IS NULL AND reputational_reviewed_at IS NULL) OR "
            "(reputational_risk_reviewed = true "
            "AND reputational_reviewed_by IS NOT NULL "
            "AND reputational_reviewed_at IS NOT NULL)",
            name="ck_safety_case_reputational_review",
        ),
    )
    op.create_index(
        "ix_safety_case_profile_stage_status",
        "safety_case_profile",
        ["report_stage", "incident_status"],
    )
    op.create_index(
        "ix_safety_case_profile_identity",
        "safety_case_profile",
        ["occurred_at", "region_code", "accident_type"],
    )


def _create_event_tables() -> None:
    op.create_table(
        "event",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("event_type", sa.String(30), nullable=False, server_default="SAFETY_INCIDENT"),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True)),
        sa.Column("region_code", sa.String(30)),
        sa.Column("region_name", sa.String(300)),
        sa.Column("project_name", sa.String(500)),
        sa.Column("subject_names", JSON, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("accident_type", sa.String(100)),
        sa.Column("engineering_type", sa.String(100)),
        sa.Column("incident_status", sa.String(40), nullable=False),
        sa.Column(
            "confirmation_status",
            sa.String(20),
            nullable=False,
            server_default="PENDING_REVIEW",
        ),
        sa.Column("confirmed_by", _uuid()),
        sa.Column("confirmed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("event_type = 'SAFETY_INCIDENT'", name="ck_event_type"),
        sa.CheckConstraint(
            f"incident_status IN ({_in(INCIDENT_STATUSES)})",
            name="ck_event_incident_status",
        ),
        sa.CheckConstraint(
            "confirmation_status IN ('PENDING_REVIEW','CONFIRMED','REJECTED')",
            name="ck_event_confirmation_status",
        ),
        sa.CheckConstraint(
            "(confirmation_status = 'CONFIRMED' "
            "AND confirmed_by IS NOT NULL AND confirmed_at IS NOT NULL) OR "
            "(confirmation_status <> 'CONFIRMED' "
            "AND confirmed_by IS NULL AND confirmed_at IS NULL)",
            name="ck_event_confirmation_actor",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(subject_names) = 'array'",
            name="ck_event_subject_names",
        ),
    )
    op.create_index("ix_event_identity", "event", ["occurred_at", "region_code", "project_name"])

    op.create_table(
        "event_item_candidate",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column(
            "event_id", _uuid(), sa.ForeignKey("event.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "item_id",
            _uuid(),
            sa.ForeignKey("intelligence_item.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("score", sa.SmallInteger(), nullable=False),
        sa.Column("matched_dimensions", JSON, nullable=False),
        sa.Column("algorithm_version", sa.String(50), nullable=False),
        sa.Column("submitted_by", _uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("event_id", "item_id", name="uq_event_item_candidate"),
        sa.CheckConstraint("score BETWEEN 0 AND 100", name="ck_event_item_candidate_score"),
        sa.CheckConstraint(
            "jsonb_typeof(matched_dimensions) = 'object'",
            name="ck_event_item_candidate_dimensions",
        ),
    )

    op.create_table(
        "event_item_decision",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column(
            "candidate_id",
            _uuid(),
            sa.ForeignKey("event_item_candidate.id", ondelete="RESTRICT"),
            nullable=False,
            unique=True,
        ),
        sa.Column("action", sa.String(20), nullable=False),
        sa.Column("reviewer_id", _uuid(), nullable=False),
        sa.Column("submitted_by", _uuid(), nullable=False),
        sa.Column("reason", sa.String(1000), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("action IN ('ACCEPT','REJECT')", name="ck_event_item_decision"),
        sa.CheckConstraint(
            "reviewer_id <> submitted_by",
            name="ck_event_item_decision_duties",
        ),
    )

    op.create_table(
        "event_item",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column(
            "candidate_id",
            _uuid(),
            sa.ForeignKey("event_item_candidate.id", ondelete="RESTRICT"),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "event_id", _uuid(), sa.ForeignKey("event.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column(
            "item_id",
            _uuid(),
            sa.ForeignKey("intelligence_item.id", ondelete="RESTRICT"),
            nullable=False,
            unique=True,
        ),
        sa.Column("confirmed_by", _uuid(), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_event_item_event", "event_item", ["event_id", "confirmed_at"])

    op.create_table(
        "event_relation_candidate",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column(
            "event_id", _uuid(), sa.ForeignKey("event.id", ondelete="CASCADE"), nullable=False
        ),
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
        sa.Column("relation_type", sa.String(20), nullable=False),
        sa.Column("evidence_id", _uuid(), sa.ForeignKey("claim_evidence.id", ondelete="RESTRICT")),
        sa.Column("submitted_by", _uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "source_item_id",
            "target_item_id",
            "relation_type",
            name="uq_event_relation_candidate",
        ),
        sa.CheckConstraint(
            f"relation_type IN ({_in(RELATION_TYPES)})",
            name="ck_event_relation_candidate_type",
        ),
        sa.CheckConstraint(
            "source_item_id <> target_item_id",
            name="ck_event_relation_candidate_distinct",
        ),
    )

    op.create_table(
        "event_relation_decision",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column(
            "candidate_id",
            _uuid(),
            sa.ForeignKey("event_relation_candidate.id", ondelete="RESTRICT"),
            nullable=False,
            unique=True,
        ),
        sa.Column("action", sa.String(20), nullable=False),
        sa.Column("reviewer_id", _uuid(), nullable=False),
        sa.Column("submitted_by", _uuid(), nullable=False),
        sa.Column("reason", sa.String(1000), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("action IN ('ACCEPT','REJECT')", name="ck_event_relation_decision"),
        sa.CheckConstraint(
            "reviewer_id <> submitted_by",
            name="ck_event_relation_decision_duties",
        ),
    )

    op.create_table(
        "event_relation",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column(
            "candidate_id",
            _uuid(),
            sa.ForeignKey("event_relation_candidate.id", ondelete="RESTRICT"),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "event_id", _uuid(), sa.ForeignKey("event.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column(
            "source_item_id",
            _uuid(),
            sa.ForeignKey("intelligence_item.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "target_item_id",
            _uuid(),
            sa.ForeignKey("intelligence_item.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("relation_type", sa.String(20), nullable=False),
        sa.Column("confirmed_by", _uuid(), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            f"relation_type IN ({_in(RELATION_TYPES)})",
            name="ck_event_relation_type",
        ),
        sa.CheckConstraint(
            "source_item_id <> target_item_id",
            name="ck_event_relation_distinct",
        ),
    )
    op.create_index(
        "ix_event_relation_event_confirmed",
        "event_relation",
        ["event_id", "confirmed_at"],
    )


def _create_claim_decision_tables() -> None:
    op.create_table(
        "claim_field_decision",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column(
            "claim_id", _uuid(), sa.ForeignKey("claim.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column(
            "evidence_id",
            _uuid(),
            sa.ForeignKey("claim_evidence.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("field_name", sa.String(50), nullable=False),
        sa.Column("action", sa.String(20), nullable=False),
        sa.Column("evidence_authority_level", sa.String(2), nullable=False),
        sa.Column("evidence_report_stage", sa.String(30), nullable=False),
        sa.Column("evidence_role", sa.String(50), nullable=False),
        sa.Column("reviewer_id", _uuid(), nullable=False),
        sa.Column("submitted_by", _uuid(), nullable=False),
        sa.Column("reason", sa.String(1000), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            f"field_name IN ({_in(PROTECTED_FIELDS)})",
            name="ck_claim_field_decision_field",
        ),
        sa.CheckConstraint(
            "action IN ('ACCEPT','REJECT','REVOKE')",
            name="ck_claim_field_decision_action",
        ),
        sa.CheckConstraint(
            f"evidence_report_stage IN ({_in(REPORT_STAGES)})",
            name="ck_claim_field_decision_stage",
        ),
        sa.CheckConstraint(
            "evidence_authority_level IN ('A0','A1','A2','B1','B2','C')",
            name="ck_claim_field_decision_authority",
        ),
        sa.CheckConstraint(
            "reviewer_id <> submitted_by",
            name="ck_claim_field_decision_duties",
        ),
    )
    op.create_index(
        "ix_claim_field_decision_claim_created",
        "claim_field_decision",
        ["claim_id", "created_at"],
    )

    op.create_table(
        "claim_conflict",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column(
            "event_id", _uuid(), sa.ForeignKey("event.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column("field_name", sa.String(50), nullable=False),
        sa.Column(
            "current_claim_id",
            _uuid(),
            sa.ForeignKey("claim.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "candidate_claim_id",
            _uuid(),
            sa.ForeignKey("claim.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("current_value_snapshot", JSON, nullable=False),
        sa.Column("candidate_value_snapshot", JSON, nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="PENDING_REVIEW"),
        sa.Column("risk_level", sa.String(2), nullable=False, server_default="R4"),
        sa.Column(
            "public_value_available", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column("opened_by", _uuid()),
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "current_claim_id",
            "candidate_claim_id",
            "field_name",
            name="uq_claim_conflict_pair",
        ),
        sa.CheckConstraint(
            f"field_name IN ({_in(PROTECTED_FIELDS)})",
            name="ck_claim_conflict_field",
        ),
        sa.CheckConstraint(
            "current_claim_id <> candidate_claim_id",
            name="ck_claim_conflict_distinct",
        ),
        sa.CheckConstraint(
            "status IN ('PENDING_REVIEW','RESOLVED')",
            name="ck_claim_conflict_status",
        ),
        sa.CheckConstraint("risk_level = 'R4'", name="ck_claim_conflict_risk"),
        sa.CheckConstraint(
            "status <> 'PENDING_REVIEW' OR public_value_available = false",
            name="ck_claim_conflict_fail_closed",
        ),
    )
    op.create_index(
        "ix_claim_conflict_queue",
        "claim_conflict",
        ["status", "detected_at"],
    )

    op.create_table(
        "claim_conflict_decision",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column(
            "conflict_id",
            _uuid(),
            sa.ForeignKey("claim_conflict.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("action", sa.String(30), nullable=False),
        sa.Column("chosen_claim_id", _uuid(), sa.ForeignKey("claim.id", ondelete="RESTRICT")),
        sa.Column("reviewer_id", _uuid(), nullable=False),
        sa.Column("submitted_by", _uuid(), nullable=False),
        sa.Column("reason", sa.String(1000), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "action IN ('ACCEPT_CANDIDATE','KEEP_CURRENT','MARK_UNRESOLVED')",
            name="ck_claim_conflict_decision_action",
        ),
        sa.CheckConstraint(
            "(action = 'MARK_UNRESOLVED' AND chosen_claim_id IS NULL) OR "
            "(action <> 'MARK_UNRESOLVED' AND chosen_claim_id IS NOT NULL)",
            name="ck_claim_conflict_decision_choice",
        ),
        sa.CheckConstraint(
            "reviewer_id <> submitted_by",
            name="ck_claim_conflict_decision_duties",
        ),
    )
    op.create_index(
        "ix_claim_conflict_decision_created",
        "claim_conflict_decision",
        ["conflict_id", "created_at"],
    )


def _create_audit_table() -> None:
    op.create_table(
        "safety_case_audit_event",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("item_id", _uuid(), sa.ForeignKey("intelligence_item.id", ondelete="RESTRICT")),
        sa.Column("event_id", _uuid(), sa.ForeignKey("event.id", ondelete="RESTRICT")),
        sa.Column("target_type", sa.String(40), nullable=False),
        sa.Column("target_id", _uuid(), nullable=False),
        sa.Column("action", sa.String(40), nullable=False),
        sa.Column("actor_id", _uuid()),
        sa.Column("reason", sa.String(1000), nullable=False),
        sa.Column("metadata", JSON, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "item_id IS NOT NULL OR event_id IS NOT NULL",
            name="ck_safety_case_audit_aggregate",
        ),
        sa.CheckConstraint(
            "target_type IN "
            "('SAFETY_CASE','EVENT','EVENT_ITEM','EVENT_RELATION','CLAIM_FIELD',"
            "'CLAIM_CONFLICT')",
            name="ck_safety_case_audit_target",
        ),
        sa.CheckConstraint(
            "action IN "
            "('CREATED','UPDATED','CONFIRMED','REJECTED','CORRECTED','WITHDRAWN',"
            "'CONFLICT_OPENED','CONFLICT_RESOLVED','PUBLIC_VALUE_HIDDEN',"
            "'PUBLIC_VALUE_RESTORED')",
            name="ck_safety_case_audit_action",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(metadata) = 'object'",
            name="ck_safety_case_audit_metadata",
        ),
    )
    op.create_index(
        "ix_safety_case_audit_target_created",
        "safety_case_audit_event",
        ["target_type", "target_id", "created_at"],
    )


def _create_claim_evidence_provenance_trigger() -> None:
    op.execute(
        """
        CREATE FUNCTION validate_claim_evidence_provenance() RETURNS trigger AS $$
        DECLARE
            claim_version uuid;
            source_authority text;
            locator_version uuid;
            locator_page integer;
            paragraph_text text;
        BEGIN
            SELECT claim.document_version_id, source.authority_level
            INTO claim_version, source_authority
            FROM claim
            JOIN intelligence_item AS item ON item.id = claim.item_id
            JOIN document_version AS version ON version.id = claim.document_version_id
            JOIN document ON document.id = version.document_id
             AND document.id = item.primary_document_id
             AND document.source_id = item.source_id
            JOIN source ON source.id = item.source_id
            WHERE claim.id = NEW.claim_id;

            IF claim_version IS NULL THEN
                RAISE EXCEPTION
                    'claim evidence requires a claim version owned by its intelligence item';
            END IF;
            IF NEW.document_version_id IS DISTINCT FROM claim_version THEN
                RAISE EXCEPTION 'claim evidence version must match claim version';
            END IF;
            IF NEW.evidence_role = 'PRIMARY_OFFICIAL'
               AND (source_authority IS NULL OR source_authority NOT IN ('A0','A1')) THEN
                RAISE EXCEPTION
                    'PRIMARY_OFFICIAL evidence requires an A0/A1 item source';
            END IF;

            IF NEW.locator_type = 'HTML_PARAGRAPH' THEN
                SELECT paragraph.value ->> 'text'
                INTO paragraph_text
                FROM processing_run AS run
                CROSS JOIN LATERAL jsonb_array_elements(
                    COALESCE(run.paragraphs, '[]'::jsonb)
                ) AS paragraph(value)
                WHERE run.document_version_id = claim_version
                  AND run.status = 'SUCCEEDED'
                  AND paragraph.value ->> 'paragraph_id' = NEW.paragraph_id
                ORDER BY run.completed_at DESC NULLS LAST, run.id DESC
                LIMIT 1;
                IF paragraph_text IS NULL
                   OR NEW.char_start IS NULL OR NEW.char_end IS NULL
                   OR substring(
                       paragraph_text FROM NEW.char_start + 1
                       FOR NEW.char_end - NEW.char_start
                   ) IS DISTINCT FROM NEW.excerpt THEN
                    RAISE EXCEPTION
                        'HTML evidence locator must resolve in the claim version processing run';
                END IF;
            ELSIF NEW.locator_type IN ('PDF_TEXT','PDF_OCR') THEN
                SELECT page.document_version_id, page.page_number
                INTO locator_version, locator_page
                FROM document_text_block AS block
                JOIN document_page AS page ON page.id = block.document_page_id
                WHERE block.id = NEW.document_text_block_id;
                IF locator_version IS DISTINCT FROM claim_version
                   OR locator_page IS DISTINCT FROM NEW.page_number THEN
                    RAISE EXCEPTION
                        'PDF evidence block must belong to the claim version and page';
                END IF;
            ELSIF NEW.locator_type = 'PDF_TABLE_CELL' THEN
                SELECT page.document_version_id, page.page_number
                INTO locator_version, locator_page
                FROM document_table_cell AS cell
                JOIN document_page AS page ON page.id = cell.document_page_id
                WHERE cell.id = NEW.document_table_cell_id;
                IF locator_version IS DISTINCT FROM claim_version
                   OR locator_page IS DISTINCT FROM NEW.page_number THEN
                    RAISE EXCEPTION
                        'PDF evidence cell must belong to the claim version and page';
                END IF;
            ELSE
                RAISE EXCEPTION 'claim evidence requires a supported authoritative locator';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, public
        """
    )
    op.execute("REVOKE ALL ON FUNCTION validate_claim_evidence_provenance() FROM PUBLIC")
    op.execute(
        """
        CREATE TRIGGER trg_claim_evidence_provenance
        BEFORE INSERT ON claim_evidence
        FOR EACH ROW EXECUTE FUNCTION validate_claim_evidence_provenance()
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM claim_evidence AS evidence
                JOIN claim ON claim.id = evidence.claim_id
                WHERE evidence.document_version_id IS DISTINCT FROM claim.document_version_id
            ) THEN
                RAISE EXCEPTION 'existing claim evidence crosses document versions';
            END IF;
            IF EXISTS (
                SELECT 1
                FROM claim_evidence AS evidence
                JOIN claim ON claim.id = evidence.claim_id
                JOIN intelligence_item AS item ON item.id = claim.item_id
                JOIN source ON source.id = item.source_id
                WHERE evidence.evidence_role = 'PRIMARY_OFFICIAL'
                  AND (
                      source.authority_level IS NULL
                      OR source.authority_level NOT IN ('A0','A1')
                  )
            ) THEN
                RAISE EXCEPTION 'existing PRIMARY_OFFICIAL evidence has a non-official source';
            END IF;
            IF EXISTS (
                SELECT 1
                FROM claim_evidence AS evidence
                JOIN claim ON claim.id = evidence.claim_id
                LEFT JOIN document_text_block AS block
                  ON block.id = evidence.document_text_block_id
                LEFT JOIN document_page AS page ON page.id = block.document_page_id
                WHERE evidence.locator_type IN ('PDF_TEXT','PDF_OCR')
                  AND (
                      page.document_version_id IS DISTINCT FROM claim.document_version_id
                      OR page.page_number IS DISTINCT FROM evidence.page_number
                  )
            ) THEN
                RAISE EXCEPTION 'existing PDF evidence block crosses document versions';
            END IF;
            IF EXISTS (
                SELECT 1
                FROM claim_evidence AS evidence
                JOIN claim ON claim.id = evidence.claim_id
                LEFT JOIN document_table_cell AS cell
                  ON cell.id = evidence.document_table_cell_id
                LEFT JOIN document_page AS page ON page.id = cell.document_page_id
                WHERE evidence.locator_type = 'PDF_TABLE_CELL'
                  AND (
                      page.document_version_id IS DISTINCT FROM claim.document_version_id
                      OR page.page_number IS DISTINCT FROM evidence.page_number
                  )
            ) THEN
                RAISE EXCEPTION 'existing PDF evidence cell crosses document versions';
            END IF;
            IF EXISTS (
                SELECT 1
                FROM claim_evidence AS evidence
                JOIN claim ON claim.id = evidence.claim_id
                WHERE evidence.locator_type = 'HTML_PARAGRAPH'
                  AND NOT EXISTS (
                      SELECT 1
                      FROM processing_run AS run
                      CROSS JOIN LATERAL jsonb_array_elements(
                          COALESCE(run.paragraphs, '[]'::jsonb)
                      ) AS paragraph(value)
                      WHERE run.document_version_id = claim.document_version_id
                        AND run.status = 'SUCCEEDED'
                        AND paragraph.value ->> 'paragraph_id' = evidence.paragraph_id
                        AND substring(
                            paragraph.value ->> 'text' FROM evidence.char_start + 1
                            FOR evidence.char_end - evidence.char_start
                        ) = evidence.excerpt
                  )
            ) THEN
                RAISE EXCEPTION 'existing HTML evidence does not resolve in its claim version';
            END IF;
        END
        $$
        """
    )


def _create_candidate_submitter_triggers() -> None:
    op.execute(
        """
        CREATE FUNCTION validate_safety_case_candidate_submitter() RETURNS trigger AS $$
        DECLARE
            canonical_submitter uuid;
        BEGIN
            IF TG_TABLE_NAME = 'event_item_candidate' THEN
                SELECT item.submitted_by INTO canonical_submitter
                FROM intelligence_item AS item
                WHERE item.id = NEW.item_id;
            ELSIF TG_TABLE_NAME = 'event_relation_candidate' THEN
                SELECT item.submitted_by INTO canonical_submitter
                FROM intelligence_item AS item
                WHERE item.id = NEW.source_item_id;
            END IF;
            IF canonical_submitter IS NULL
               OR NEW.submitted_by IS DISTINCT FROM canonical_submitter THEN
                RAISE EXCEPTION USING
                    ERRCODE = '42501',
                    MESSAGE = 'candidate submitter does not match authoritative item submitter';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, public
        """
    )
    op.execute("REVOKE ALL ON FUNCTION validate_safety_case_candidate_submitter() FROM PUBLIC")
    for table_name, trigger_name in (
        ("event_item_candidate", "trg_event_item_candidate_submitter"),
        ("event_relation_candidate", "trg_event_relation_candidate_submitter"),
    ):
        op.execute(
            f"""
            CREATE TRIGGER {trigger_name}
            BEFORE INSERT ON {table_name}
            FOR EACH ROW EXECUTE FUNCTION validate_safety_case_candidate_submitter()
            """
        )
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM event_item_candidate AS candidate
                JOIN intelligence_item AS item ON item.id = candidate.item_id
                WHERE candidate.submitted_by IS DISTINCT FROM item.submitted_by
            ) OR EXISTS (
                SELECT 1
                FROM event_relation_candidate AS candidate
                JOIN intelligence_item AS item ON item.id = candidate.source_item_id
                WHERE candidate.submitted_by IS DISTINCT FROM item.submitted_by
            ) THEN
                RAISE EXCEPTION
                    'existing safety-case candidate has a forged submitter';
            END IF;
        END
        $$
        """
    )


def _create_safety_triggers() -> None:
    _create_claim_evidence_provenance_trigger()
    _create_candidate_submitter_triggers()

    op.execute(
        """
        CREATE FUNCTION validate_safety_case_profile_projection() RETURNS trigger AS $$
        DECLARE
            accepted boolean;
            unresolved boolean;
        BEGIN
            IF TG_OP = 'INSERT' THEN
                IF NEW.deaths IS NOT NULL OR NEW.injuries IS NOT NULL
                   OR NEW.loss_amount_minor IS NOT NULL
                   OR NEW.official_direct_causes IS NOT NULL
                   OR NEW.responsibility_findings IS NOT NULL THEN
                    RAISE EXCEPTION
                        'protected safety-case fields must enter through claim decisions';
                END IF;
                RETURN NEW;
            END IF;

            IF NEW.deaths IS DISTINCT FROM OLD.deaths AND NEW.deaths IS NOT NULL THEN
                SELECT safety_case_claim_value_is_accepted(
                    NEW.item_id, 'deaths', to_jsonb(NEW.deaths)
                ) INTO accepted;
                IF NOT accepted THEN
                    RAISE EXCEPTION 'deaths requires an accepted claim field decision';
                END IF;
            END IF;
            IF NEW.injuries IS DISTINCT FROM OLD.injuries AND NEW.injuries IS NOT NULL THEN
                SELECT safety_case_claim_value_is_accepted(
                    NEW.item_id, 'injuries', to_jsonb(NEW.injuries)
                ) INTO accepted;
                IF NOT accepted THEN
                    RAISE EXCEPTION 'injuries requires an accepted claim field decision';
                END IF;
            END IF;
            IF NEW.loss_amount_minor IS DISTINCT FROM OLD.loss_amount_minor
               AND NEW.loss_amount_minor IS NOT NULL THEN
                SELECT safety_case_claim_value_is_accepted(
                    NEW.item_id, 'loss_amount_minor', to_jsonb(NEW.loss_amount_minor)
                ) INTO accepted;
                IF NOT accepted THEN
                    RAISE EXCEPTION 'loss requires an accepted claim field decision';
                END IF;
            END IF;
            IF NEW.official_direct_causes IS DISTINCT FROM OLD.official_direct_causes
               AND NEW.official_direct_causes IS NOT NULL THEN
                SELECT safety_case_claim_value_is_accepted(
                    NEW.item_id, 'official_direct_causes', NEW.official_direct_causes
                ) INTO accepted;
                IF NOT accepted THEN
                    RAISE EXCEPTION 'causes require an accepted claim field decision';
                END IF;
            END IF;
            IF NEW.responsibility_findings IS DISTINCT FROM OLD.responsibility_findings
               AND NEW.responsibility_findings IS NOT NULL THEN
                SELECT safety_case_claim_value_is_accepted(
                    NEW.item_id, 'responsibility_findings', NEW.responsibility_findings
                ) INTO accepted;
                IF NOT accepted THEN
                    RAISE EXCEPTION 'responsibility requires an accepted claim field decision';
                END IF;
            END IF;

            SELECT EXISTS (
                SELECT 1
                FROM claim_conflict AS conflict
                JOIN claim AS current_claim ON current_claim.id = conflict.current_claim_id
                JOIN claim AS candidate_claim ON candidate_claim.id = conflict.candidate_claim_id
                WHERE conflict.status = 'PENDING_REVIEW'
                  AND conflict.field_name IN (
                      CASE WHEN NEW.deaths IS DISTINCT FROM OLD.deaths
                                AND NEW.deaths IS NOT NULL THEN 'deaths' END,
                      CASE WHEN NEW.injuries IS DISTINCT FROM OLD.injuries
                                AND NEW.injuries IS NOT NULL THEN 'injuries' END,
                      CASE WHEN NEW.loss_amount_minor IS DISTINCT FROM OLD.loss_amount_minor
                                AND NEW.loss_amount_minor IS NOT NULL
                           THEN 'loss_amount_minor' END,
                      CASE WHEN NEW.official_direct_causes
                                    IS DISTINCT FROM OLD.official_direct_causes
                                AND NEW.official_direct_causes IS NOT NULL
                           THEN 'official_direct_causes' END,
                      CASE WHEN NEW.responsibility_findings
                                    IS DISTINCT FROM OLD.responsibility_findings
                                AND NEW.responsibility_findings IS NOT NULL
                           THEN 'responsibility_findings' END
                  )
                  AND (current_claim.item_id = NEW.item_id OR candidate_claim.item_id = NEW.item_id)
            ) INTO unresolved;
            IF unresolved THEN
                RAISE EXCEPTION 'unresolved claim conflict keeps the public field unavailable';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, public
        """
    )
    op.execute("REVOKE ALL ON FUNCTION validate_safety_case_profile_projection() FROM PUBLIC")
    op.execute(
        """
        CREATE TRIGGER trg_safety_case_profile_projection
        BEFORE INSERT OR UPDATE ON safety_case_profile
        FOR EACH ROW EXECUTE FUNCTION validate_safety_case_profile_projection()
        """
    )

    op.execute(
        """
        CREATE FUNCTION enforce_pending_event_insert() RETURNS trigger AS $$
        BEGIN
            IF NEW.confirmation_status <> 'PENDING_REVIEW'
               OR NEW.confirmed_by IS NOT NULL OR NEW.confirmed_at IS NOT NULL THEN
                RAISE EXCEPTION 'events must be confirmed after creation by a reviewer';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute("REVOKE ALL ON FUNCTION enforce_pending_event_insert() FROM PUBLIC")
    op.execute(
        """
        CREATE TRIGGER trg_event_pending_insert
        BEFORE INSERT ON event
        FOR EACH ROW EXECUTE FUNCTION enforce_pending_event_insert()
        """
    )

    op.execute(
        """
        CREATE FUNCTION reject_safety_case_self_approval() RETURNS trigger AS $$
        DECLARE
            canonical_submitter uuid;
            current_submitter uuid;
            current_claim uuid;
            candidate_claim uuid;
        BEGIN
            IF TG_TABLE_NAME = 'event_item_decision' THEN
                SELECT item.submitted_by INTO canonical_submitter
                FROM event_item_candidate AS candidate
                JOIN intelligence_item AS item ON item.id = candidate.item_id
                WHERE candidate.id = NEW.candidate_id;
            ELSIF TG_TABLE_NAME = 'event_relation_decision' THEN
                SELECT source_item.submitted_by, target_item.submitted_by
                INTO canonical_submitter, current_submitter
                FROM event_relation_candidate AS candidate
                JOIN intelligence_item AS source_item
                  ON source_item.id = candidate.source_item_id
                JOIN intelligence_item AS target_item
                  ON target_item.id = candidate.target_item_id
                WHERE candidate.id = NEW.candidate_id;
                IF NEW.reviewer_id = current_submitter THEN
                    RAISE EXCEPTION USING
                        ERRCODE = '42501',
                        MESSAGE = 'submitter cannot approve their own safety case';
                END IF;
            ELSIF TG_TABLE_NAME = 'claim_field_decision' THEN
                SELECT item.submitted_by INTO canonical_submitter
                FROM claim
                JOIN intelligence_item AS item ON item.id = claim.item_id
                WHERE claim.id = NEW.claim_id;
            ELSIF TG_TABLE_NAME = 'claim_conflict_decision' THEN
                SELECT conflict.current_claim_id, conflict.candidate_claim_id,
                       current_item.submitted_by, candidate_item.submitted_by
                INTO current_claim, candidate_claim, current_submitter, canonical_submitter
                FROM claim_conflict AS conflict
                JOIN claim AS current ON current.id = conflict.current_claim_id
                JOIN intelligence_item AS current_item ON current_item.id = current.item_id
                JOIN claim AS candidate ON candidate.id = conflict.candidate_claim_id
                JOIN intelligence_item AS candidate_item ON candidate_item.id = candidate.item_id
                WHERE conflict.id = NEW.conflict_id;
                IF NEW.action = 'ACCEPT_CANDIDATE'
                   AND NEW.chosen_claim_id IS DISTINCT FROM candidate_claim THEN
                    RAISE EXCEPTION 'chosen claim must be the conflict candidate';
                END IF;
                IF NEW.action = 'KEEP_CURRENT'
                   AND NEW.chosen_claim_id IS DISTINCT FROM current_claim THEN
                    RAISE EXCEPTION 'chosen claim must be the current claim';
                END IF;
                IF NEW.reviewer_id = current_submitter THEN
                    RAISE EXCEPTION USING
                        ERRCODE = '42501',
                        MESSAGE = 'submitter cannot approve their own safety case';
                END IF;
            END IF;

            IF canonical_submitter IS NULL OR NEW.submitted_by <> canonical_submitter THEN
                RAISE EXCEPTION 'decision submitter does not match authoritative item submitter';
            END IF;
            IF NEW.reviewer_id = canonical_submitter THEN
                RAISE EXCEPTION USING
                    ERRCODE = '42501',
                    MESSAGE = 'submitter cannot approve their own safety case';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, public
        """
    )
    op.execute("REVOKE ALL ON FUNCTION reject_safety_case_self_approval() FROM PUBLIC")

    for table_name in (
        "event_item_decision",
        "event_relation_decision",
        "claim_field_decision",
        "claim_conflict_decision",
    ):
        op.execute(
            f"""
            CREATE TRIGGER trg_{table_name}_duties
            BEFORE INSERT ON {table_name}
            FOR EACH ROW EXECUTE FUNCTION reject_safety_case_self_approval()
            """
        )

    op.execute(
        """
        CREATE FUNCTION validate_event_item_projection() RETURNS trigger AS $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM event_item_candidate AS candidate
                JOIN event_item_decision AS decision
                  ON decision.candidate_id = candidate.id
                 AND decision.action = 'ACCEPT'
                 AND decision.reviewer_id = NEW.confirmed_by
                 AND decision.created_at = NEW.confirmed_at
                JOIN intelligence_item AS item
                  ON item.id = candidate.item_id
                 AND item.item_type = 'SAFETY_CASE'
                JOIN safety_case_profile AS profile ON profile.item_id = item.id
                WHERE candidate.id = NEW.candidate_id
                  AND candidate.event_id = NEW.event_id
                  AND candidate.item_id = NEW.item_id
            ) THEN
                RAISE EXCEPTION
                    'event membership requires its accepted candidate decision';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, public
        """
    )
    op.execute("REVOKE ALL ON FUNCTION validate_event_item_projection() FROM PUBLIC")
    op.execute(
        """
        CREATE TRIGGER trg_event_item_projection
        BEFORE INSERT ON event_item
        FOR EACH ROW EXECUTE FUNCTION validate_event_item_projection()
        """
    )

    op.execute(
        """
        CREATE FUNCTION validate_event_relation_projection() RETURNS trigger AS $$
        DECLARE
            source_stage text;
            target_stage text;
            source_order_at timestamptz;
            target_order_at timestamptz;
        BEGIN
            SELECT source_profile.report_stage, target_profile.report_stage,
                   COALESCE(source_item.source_published_at,
                            source_item.first_discovered_at),
                   COALESCE(target_item.source_published_at,
                            target_item.first_discovered_at)
            INTO source_stage, target_stage, source_order_at, target_order_at
            FROM event_relation_candidate AS candidate
            JOIN event_relation_decision AS decision
              ON decision.candidate_id = candidate.id
             AND decision.action = 'ACCEPT'
             AND decision.reviewer_id = NEW.confirmed_by
             AND decision.created_at = NEW.confirmed_at
            JOIN event_item AS source_membership
              ON source_membership.event_id = candidate.event_id
             AND source_membership.item_id = candidate.source_item_id
            JOIN event_item AS target_membership
              ON target_membership.event_id = candidate.event_id
             AND target_membership.item_id = candidate.target_item_id
            JOIN intelligence_item AS source_item
              ON source_item.id = candidate.source_item_id
             AND source_item.item_type = 'SAFETY_CASE'
            JOIN intelligence_item AS target_item
              ON target_item.id = candidate.target_item_id
             AND target_item.item_type = 'SAFETY_CASE'
            JOIN safety_case_profile AS source_profile
              ON source_profile.item_id = source_item.id
            JOIN safety_case_profile AS target_profile
              ON target_profile.item_id = target_item.id
            WHERE candidate.id = NEW.candidate_id
              AND candidate.event_id = NEW.event_id
              AND candidate.source_item_id = NEW.source_item_id
              AND candidate.target_item_id = NEW.target_item_id
              AND candidate.relation_type = NEW.relation_type;

            IF source_stage IS NULL OR target_stage IS NULL THEN
                RAISE EXCEPTION
                    'event relation endpoints must be confirmed members of its event';
            END IF;
            IF NEW.relation_type = 'CORRECTS'
               AND (source_order_at IS NULL OR target_order_at IS NULL
                    OR source_order_at <= target_order_at) THEN
                RAISE EXCEPTION
                    'correction source must be strictly later than its target';
            END IF;
            IF NOT (
                (NEW.relation_type = 'FOLLOW_UP'
                 AND source_stage = 'FOLLOW_UP_REPORT'
                 AND target_stage IN ('INITIAL_REPORT','FOLLOW_UP_REPORT'))
                OR (NEW.relation_type = 'INVESTIGATES'
                    AND source_stage = 'FINAL_INVESTIGATION'
                    AND target_stage IN ('INITIAL_REPORT','FOLLOW_UP_REPORT'))
                OR (NEW.relation_type = 'PENALIZES'
                    AND source_stage = 'ENFORCEMENT'
                    AND target_stage = 'FINAL_INVESTIGATION')
                OR (NEW.relation_type = 'RECTIFIES'
                    AND source_stage = 'RECTIFICATION'
                    AND target_stage IN ('FINAL_INVESTIGATION','ENFORCEMENT'))
                OR (NEW.relation_type = 'CORRECTS'
                    AND source_order_at > target_order_at)
            ) THEN
                RAISE EXCEPTION 'event relation stage semantics are invalid';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, public
        """
    )
    op.execute("REVOKE ALL ON FUNCTION validate_event_relation_projection() FROM PUBLIC")
    op.execute(
        """
        CREATE TRIGGER trg_event_relation_projection
        BEFORE INSERT ON event_relation
        FOR EACH ROW EXECUTE FUNCTION validate_event_relation_projection()
        """
    )

    op.execute(
        """
        CREATE FUNCTION safety_case_claim_value_is_accepted(
            target_item_id uuid, target_field text, target_value jsonb
        ) RETURNS boolean AS $$
            SELECT EXISTS (
                SELECT 1
                FROM claim
                JOIN LATERAL (
                    SELECT decision.action
                    FROM claim_field_decision AS decision
                    WHERE decision.claim_id = claim.id
                    ORDER BY decision.created_at DESC, decision.id DESC
                    LIMIT 1
                ) AS latest ON latest.action = 'ACCEPT'
                WHERE claim.item_id = target_item_id
                  AND claim.claim_type = target_field
                  AND claim.literal_value = target_value
            )
        $$ LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, public
        """
    )
    op.execute(
        "REVOKE ALL ON FUNCTION safety_case_claim_value_is_accepted(uuid,text,jsonb) FROM PUBLIC"
    )

    op.execute(
        """
        CREATE FUNCTION validate_claim_field_decision() RETURNS trigger AS $$
        DECLARE
            actual_authority text;
            actual_stage text;
            actual_role text;
            actual_field text;
            actual_item uuid;
        BEGIN
            SELECT source.authority_level, profile.report_stage,
                   evidence.evidence_role, claim.claim_type, item.id
            INTO actual_authority, actual_stage, actual_role, actual_field, actual_item
            FROM claim
            JOIN intelligence_item AS item ON item.id = claim.item_id
            JOIN source ON source.id = item.source_id
            JOIN safety_case_profile AS profile ON profile.item_id = item.id
            JOIN claim_evidence AS evidence
              ON evidence.id = NEW.evidence_id AND evidence.claim_id = claim.id
            WHERE claim.id = NEW.claim_id;

            IF actual_authority IS NULL THEN
                RAISE EXCEPTION 'claim decision requires evidence for a safety-case item';
            END IF;
            IF actual_field <> NEW.field_name THEN
                RAISE EXCEPTION 'claim field does not match decision field';
            END IF;
            IF NEW.action IN ('ACCEPT','REJECT') AND EXISTS (
                SELECT 1 FROM claim_field_decision AS prior
                WHERE prior.claim_id = NEW.claim_id
            ) THEN
                RAISE EXCEPTION 'protected claim decision is final';
            END IF;
            IF NEW.evidence_authority_level <> actual_authority
               OR NEW.evidence_report_stage <> actual_stage
               OR NEW.evidence_role <> actual_role THEN
                RAISE EXCEPTION
                    'evidence qualification snapshot does not match authoritative facts';
            END IF;
            IF NEW.action = 'ACCEPT' AND (
                actual_authority NOT IN ('A0','A1')
                OR actual_role <> 'PRIMARY_OFFICIAL'
            ) THEN
                RAISE EXCEPTION 'accepted protected facts require A0/A1 primary official evidence';
            END IF;
            IF NEW.action = 'ACCEPT' AND NOT EXISTS (
                SELECT 1 FROM event_item AS membership
                WHERE membership.item_id = actual_item
            ) THEN
                RAISE EXCEPTION
                    'accepted protected claim requires confirmed event membership';
            END IF;
            IF NEW.action = 'ACCEPT'
               AND NEW.field_name IN ('official_direct_causes','responsibility_findings')
               AND actual_stage NOT IN ('FINAL_INVESTIGATION','ENFORCEMENT') THEN
                RAISE EXCEPTION 'causes and responsibility require formal evidence';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, public
        """
    )
    op.execute("REVOKE ALL ON FUNCTION validate_claim_field_decision() FROM PUBLIC")
    op.execute(
        """
        CREATE TRIGGER trg_claim_field_decision_evidence
        BEFORE INSERT ON claim_field_decision
        FOR EACH ROW EXECUTE FUNCTION validate_claim_field_decision()
        """
    )

    op.execute(
        """
        CREATE FUNCTION validate_claim_conflict() RETURNS trigger AS $$
        DECLARE
            current_field text;
            candidate_field text;
            current_value jsonb;
            candidate_value jsonb;
            current_item uuid;
            candidate_item uuid;
            current_accepted boolean;
            candidate_accepted boolean;
        BEGIN
            SELECT claim_type, literal_value, item_id
            INTO current_field, current_value, current_item
            FROM claim WHERE id = NEW.current_claim_id;
            SELECT claim_type, literal_value, item_id
            INTO candidate_field, candidate_value, candidate_item
            FROM claim WHERE id = NEW.candidate_claim_id;

            IF current_field IS DISTINCT FROM NEW.field_name
               OR candidate_field IS DISTINCT FROM NEW.field_name THEN
                RAISE EXCEPTION 'conflicting claims must use the declared protected field';
            END IF;
            IF current_value IS DISTINCT FROM NEW.current_value_snapshot
               OR candidate_value IS DISTINCT FROM NEW.candidate_value_snapshot THEN
                RAISE EXCEPTION 'conflict snapshots must match authoritative claim values';
            END IF;
            IF current_value = candidate_value THEN
                RAISE EXCEPTION 'equal claim values do not form a conflict';
            END IF;
            SELECT safety_case_claim_value_is_accepted(
                current_item, current_field, current_value
            ) INTO current_accepted;
            SELECT safety_case_claim_value_is_accepted(
                candidate_item, candidate_field, candidate_value
            ) INTO candidate_accepted;
            IF NOT current_accepted OR NOT candidate_accepted THEN
                RAISE EXCEPTION 'only accepted official claims may open a conflict';
            END IF;
            IF NOT EXISTS (
                SELECT 1 FROM event_item
                WHERE event_id = NEW.event_id AND item_id = current_item
            ) OR NOT EXISTS (
                SELECT 1 FROM event_item
                WHERE event_id = NEW.event_id AND item_id = candidate_item
            ) THEN
                RAISE EXCEPTION 'conflicting claims must belong to the confirmed event';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, public
        """
    )
    op.execute("REVOKE ALL ON FUNCTION validate_claim_conflict() FROM PUBLIC")
    op.execute(
        """
        CREATE TRIGGER trg_claim_conflict_validate
        BEFORE INSERT ON claim_conflict
        FOR EACH ROW EXECUTE FUNCTION validate_claim_conflict()
        """
    )

    op.execute(
        """
        CREATE FUNCTION hide_conflicting_safety_case_field() RETURNS trigger AS $$
        DECLARE
            affected_item uuid;
        BEGIN
            SELECT item_id INTO affected_item FROM claim WHERE id = NEW.current_claim_id;
            IF NEW.field_name = 'deaths' THEN
                UPDATE safety_case_profile SET deaths = NULL, updated_at = NEW.detected_at
                WHERE item_id = affected_item;
            ELSIF NEW.field_name = 'injuries' THEN
                UPDATE safety_case_profile SET injuries = NULL, updated_at = NEW.detected_at
                WHERE item_id = affected_item;
            ELSIF NEW.field_name = 'loss_amount_minor' THEN
                UPDATE safety_case_profile
                SET loss_amount_minor = NULL, loss_currency = NULL, updated_at = NEW.detected_at
                WHERE item_id = affected_item;
            ELSIF NEW.field_name = 'official_direct_causes' THEN
                UPDATE safety_case_profile
                SET official_direct_causes = NULL, updated_at = NEW.detected_at
                WHERE item_id = affected_item;
            ELSIF NEW.field_name = 'responsibility_findings' THEN
                UPDATE safety_case_profile
                SET responsibility_findings = NULL, updated_at = NEW.detected_at
                WHERE item_id = affected_item;
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, public
        """
    )
    op.execute("REVOKE ALL ON FUNCTION hide_conflicting_safety_case_field() FROM PUBLIC")
    op.execute(
        """
        CREATE TRIGGER trg_claim_conflict_hide_public_value
        AFTER INSERT ON claim_conflict
        FOR EACH ROW EXECUTE FUNCTION hide_conflicting_safety_case_field()
        """
    )

    immutable_tables = (
        "event_item_candidate",
        "event_item_decision",
        "event_item",
        "event_relation_candidate",
        "event_relation_decision",
        "event_relation",
        "claim_field_decision",
        "claim_conflict_decision",
        "safety_case_audit_event",
    )
    for table_name in immutable_tables:
        op.execute(
            f"""
            CREATE TRIGGER trg_{table_name}_immutable
            BEFORE UPDATE OR DELETE ON {table_name}
            FOR EACH ROW EXECUTE FUNCTION reject_immutable_source_vault_change()
            """
        )


def _create_safe_projection_views() -> None:
    op.execute(
        """
        CREATE VIEW public_safety_case_accepted_claim
        WITH (security_barrier = true) AS
        SELECT membership.event_id,
               claim.item_id AS source_item_id,
               claim.id AS claim_id,
               decision.field_name,
               claim.literal_value,
               decision.evidence_id,
               decision.created_at AS reviewed_at,
               profile.loss_currency
        FROM claim
        JOIN event_item AS membership ON membership.item_id = claim.item_id
        JOIN intelligence_item AS item ON item.id = claim.item_id
        JOIN safety_case_profile AS profile ON profile.item_id = item.id
        JOIN publication ON publication.item_id = item.id
          AND publication.status = 'PUBLISHED'
        JOIN LATERAL (
            SELECT latest.field_name, latest.evidence_id, latest.action,
                   latest.created_at, latest.id
            FROM claim_field_decision AS latest
            WHERE latest.claim_id = claim.id
            ORDER BY latest.created_at DESC, latest.id DESC
            LIMIT 1
        ) AS decision ON decision.action = 'ACCEPT'
        JOIN claim_evidence AS evidence
          ON evidence.id = decision.evidence_id
         AND evidence.claim_id = claim.id
        WHERE item.item_type = 'SAFETY_CASE'
          AND item.risk_level = 'R3'
          AND item.review_status = 'APPROVED'
          AND NOT EXISTS (
              SELECT 1 FROM claim_conflict AS pending
              WHERE pending.event_id = membership.event_id
                AND pending.field_name = decision.field_name
                AND pending.status = 'PENDING_REVIEW'
          )
          AND NOT EXISTS (
              SELECT 1
              FROM claim_conflict AS resolved
              JOIN LATERAL (
                  SELECT resolution.chosen_claim_id
                  FROM claim_conflict_decision AS resolution
                  WHERE resolution.conflict_id = resolved.id
                  ORDER BY resolution.created_at DESC, resolution.id DESC
                  LIMIT 1
              ) AS resolution ON true
              WHERE resolved.event_id = membership.event_id
                AND resolved.field_name = decision.field_name
                AND resolved.status = 'RESOLVED'
                AND claim.id IN (
                    resolved.current_claim_id,
                    resolved.candidate_claim_id
                )
                AND resolution.chosen_claim_id <> claim.id
          )
        """
    )
    op.execute(
        """
        CREATE VIEW public_safety_case_conflict
        WITH (security_barrier = true) AS
        SELECT conflict.event_id,
               current_claim.item_id AS source_item_id,
               conflict.id AS conflict_id,
               conflict.field_name,
               conflict.detected_at
        FROM claim_conflict AS conflict
        JOIN claim AS current_claim ON current_claim.id = conflict.current_claim_id
        JOIN event_item AS membership
          ON membership.item_id = current_claim.item_id
         AND membership.event_id = conflict.event_id
        JOIN intelligence_item AS item ON item.id = current_claim.item_id
        JOIN publication ON publication.item_id = current_claim.item_id
          AND publication.status = 'PUBLISHED'
        WHERE conflict.status = 'PENDING_REVIEW'
          AND item.item_type = 'SAFETY_CASE'
          AND item.risk_level = 'R3'
          AND item.review_status = 'APPROVED'
        """
    )
    op.execute("REVOKE ALL ON public_safety_case_accepted_claim FROM PUBLIC")
    op.execute("REVOKE ALL ON public_safety_case_conflict FROM PUBLIC")


def _configure_roles_and_rls() -> None:
    public_read_tables = "safety_case_profile, event, event_item, event_relation"
    candidate_tables = "event_item_candidate, event_relation_candidate"
    publisher_tables = (
        "event_item_decision, event_item, event_relation_decision, event_relation, "
        "claim_field_decision, claim_conflict_decision, safety_case_audit_event"
    )

    op.execute(f"GRANT SELECT ON {public_read_tables} TO srbg_runtime, srbg_publication_writer")
    op.execute(f"GRANT SELECT ON {candidate_tables} TO srbg_runtime, srbg_publication_writer")
    op.execute("GRANT INSERT ON safety_case_profile, event TO srbg_runtime")
    op.execute(f"GRANT INSERT ON {candidate_tables} TO srbg_runtime")
    op.execute("GRANT SELECT, UPDATE ON safety_case_profile, event TO srbg_publication_writer")
    op.execute(f"GRANT SELECT, INSERT ON {publisher_tables} TO srbg_publication_writer")
    op.execute("GRANT SELECT, INSERT, UPDATE ON claim_conflict TO srbg_publication_writer")

    op.execute("REVOKE UPDATE, DELETE ON safety_case_profile, event FROM srbg_runtime")
    op.execute(f"REVOKE UPDATE, DELETE ON {candidate_tables} FROM srbg_runtime")
    op.execute("REVOKE SELECT, INSERT, UPDATE, DELETE ON claim_conflict FROM srbg_runtime")
    op.execute("REVOKE INSERT, UPDATE, DELETE ON claim_field_decision FROM srbg_runtime")
    op.execute(
        "REVOKE SELECT ON claim_field_decision, claim_conflict_decision, "
        "event_item_decision FROM srbg_runtime"
    )
    op.execute(
        "REVOKE INSERT, UPDATE, DELETE ON event_item_decision, event_item, "
        "event_relation_decision, event_relation, claim_conflict_decision, "
        "safety_case_audit_event FROM srbg_runtime"
    )
    op.execute("GRANT SELECT, INSERT ON claim_field_decision TO srbg_publication_writer")
    op.execute(
        "GRANT SELECT (id, claim_id, evidence_id, field_name, action, created_at) "
        "ON claim_field_decision TO srbg_runtime"
    )
    op.execute(
        "GRANT SELECT (id, conflict_id, action, created_at) "
        "ON claim_conflict_decision TO srbg_runtime"
    )
    op.execute(
        "GRANT SELECT (id, candidate_id, action, created_at) ON event_item_decision TO srbg_runtime"
    )

    op.execute("ALTER TABLE claim_conflict ENABLE ROW LEVEL SECURITY")
    op.execute(
        "GRANT SELECT "
        "(id, event_id, field_name, status, detected_at) "
        "ON claim_conflict TO srbg_runtime"
    )
    op.execute(
        "GRANT SELECT ON public_safety_case_accepted_claim, "
        "public_safety_case_conflict TO srbg_runtime"
    )
    op.execute(
        "CREATE POLICY claim_conflict_runtime_safe_select ON claim_conflict "
        "FOR SELECT TO srbg_runtime USING (true)"
    )
    op.execute(
        "CREATE POLICY claim_conflict_publisher_all ON claim_conflict "
        "TO srbg_publication_writer USING (true) WITH CHECK (true)"
    )


def downgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM intelligence_item WHERE item_type = 'SAFETY_CASE') THEN
                RAISE EXCEPTION
                    'refusing Round04 downgrade while SAFETY_CASE data exists; export it first';
            END IF;
            IF EXISTS (
                SELECT 1
                FROM document
                JOIN source ON source.id = document.source_id
                WHERE source.registry_code IN ('GOV-019','GOV-020','GOV-021','GOV-022')
            ) THEN
                RAISE EXCEPTION
                    'refusing Round04 downgrade while Round04 source documents exist';
            END IF;
        END
        $$
        """
    )

    op.execute("DROP VIEW IF EXISTS public_safety_case_accepted_claim")
    op.execute("DROP VIEW IF EXISTS public_safety_case_conflict")
    op.execute("DROP TRIGGER IF EXISTS trg_claim_evidence_provenance ON claim_evidence")

    for table_name in reversed(ROUND04_TABLES):
        op.drop_table(table_name)

    op.execute("DROP FUNCTION IF EXISTS hide_conflicting_safety_case_field()")
    op.execute("DROP FUNCTION IF EXISTS validate_claim_conflict()")
    op.execute("DROP FUNCTION IF EXISTS validate_claim_field_decision()")
    op.execute("DROP FUNCTION IF EXISTS validate_event_relation_projection()")
    op.execute("DROP FUNCTION IF EXISTS validate_event_item_projection()")
    op.execute("DROP FUNCTION IF EXISTS reject_safety_case_self_approval()")
    op.execute("DROP FUNCTION IF EXISTS validate_safety_case_candidate_submitter()")
    op.execute("DROP FUNCTION IF EXISTS validate_claim_evidence_provenance()")
    op.execute("DROP FUNCTION IF EXISTS enforce_pending_event_insert()")
    op.execute("DROP FUNCTION IF EXISTS validate_safety_case_profile_projection()")
    op.execute("DROP FUNCTION IF EXISTS safety_case_claim_value_is_accepted(uuid,text,jsonb)")
    op.execute(
        "DELETE FROM source WHERE registry_code IN ('GOV-019','GOV-020','GOV-021','GOV-022')"
    )

    op.drop_constraint("ck_round04_review_risk", "review_task", type_="check")
    op.drop_constraint("ck_round04_item_risk", "intelligence_item", type_="check")
    op.drop_constraint("ck_round04_item_type", "intelligence_item", type_="check")
    op.create_check_constraint(
        "ck_review_risk_level",
        "review_task",
        "risk_level = 'R3'",
    )
    op.create_check_constraint(
        "ck_round02_item_risk",
        "intelligence_item",
        "risk_level = 'R3'",
    )
    op.create_check_constraint(
        "ck_round02_item_type",
        "intelligence_item",
        "item_type = 'SAFETY_REGULATION'",
    )
