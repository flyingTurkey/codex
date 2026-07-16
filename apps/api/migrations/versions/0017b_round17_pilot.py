"""Round 17 immutable pilot, human-gold, work, and runtime provenance facts.

Revision ID: 0017b_round17_pilot
Revises: 0017_round17_governance
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0017b_round17_pilot"
down_revision: str | Sequence[str] | None = "0017_round17_governance"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_JSON = postgresql.JSONB(astext_type=sa.Text())
_TEXT_ARRAY = postgresql.ARRAY(sa.Text())


def _uuid() -> postgresql.UUID:
    return postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    _add_fetch_run_provenance()
    _add_health_shape_facts()
    _create_staff_and_window_tables()
    _create_gold_tables()
    _create_work_and_metric_tables()
    _create_append_only_boundaries()
    _create_window_binding_boundary()
    _create_scheduled_runtime_boundaries()
    _configure_roles()


def _add_fetch_run_provenance() -> None:
    op.add_column(
        "fetch_run",
        sa.Column("run_origin", sa.String(20), nullable=False, server_default="SCHEDULED"),
    )
    op.add_column("fetch_run", sa.Column("replayed_from_run_id", _uuid()))
    op.add_column(
        "fetch_run",
        sa.Column("request_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "fetch_run",
        sa.Column("response_bytes", sa.BigInteger(), nullable=False, server_default="0"),
    )
    op.create_foreign_key(
        "fk_fetch_run_replayed_from",
        "fetch_run",
        "fetch_run",
        ["replayed_from_run_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_check_constraint(
        "ck_fetch_run_origin",
        "fetch_run",
        "run_origin IN ('SCHEDULED','REPLAY','BACKFILL','DRILL')",
    )
    op.create_check_constraint(
        "ck_fetch_run_request_count", "fetch_run", "request_count >= 0"
    )
    op.create_check_constraint(
        "ck_fetch_run_response_bytes", "fetch_run", "response_bytes >= 0"
    )
    op.execute(
        """
        UPDATE fetch_run SET run_origin=CASE
          WHEN trigger='SCHEDULED' THEN 'SCHEDULED'
          WHEN trigger='FIXTURE' THEN 'DRILL'
          ELSE 'BACKFILL' END
        """
    )
    op.create_index("ix_fetch_run_origin_started", "fetch_run", ["run_origin", "started_at"])


def _add_health_shape_facts() -> None:
    op.add_column(
        "source_health_snapshot",
        sa.Column("discovery_body_bytes", sa.BigInteger()),
    )
    op.add_column(
        "source_health_snapshot",
        sa.Column("structure_fingerprint_sha256", sa.String(64)),
    )
    op.create_check_constraint(
        "ck_round17_health_body_bytes",
        "source_health_snapshot",
        "discovery_body_bytes IS NULL OR discovery_body_bytes >= 0",
    )
    op.create_check_constraint(
        "ck_round17_health_structure_hash",
        "source_health_snapshot",
        "structure_fingerprint_sha256 IS NULL OR "
        "structure_fingerprint_sha256 ~ '^[0-9a-f]{64}$'",
    )


def _create_staff_and_window_tables() -> None:
    op.create_table(
        "round17_staff_binding",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("actor_id", _uuid(), nullable=False),
        sa.Column("display_name", sa.String(200), nullable=False),
        sa.Column("responsibility", sa.String(40), nullable=False),
        sa.Column("oidc_issuer_sha256", sa.String(64), nullable=False),
        sa.Column("oidc_subject_sha256", sa.String(64), nullable=False),
        sa.Column("local_identity", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("bound_by", _uuid(), nullable=False),
        sa.Column("bound_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("actor_id", "responsibility", name="uq_round17_staff_responsibility"),
        sa.UniqueConstraint(
            "actor_id",
            "display_name",
            "responsibility",
            name="uq_round17_staff_attested_identity",
        ),
        sa.CheckConstraint(
            "responsibility IN ('SOURCE_OPERATOR','SOURCE_APPROVER','PUBLICATION_APPROVER',"
            "'SAFETY_ANNOTATOR_A','SAFETY_ANNOTATOR_B','DIGITAL_PRIMARY','DIGITAL_SECONDARY',"
            "'GOLD_ARBITRATOR')",
            name="ck_round17_staff_responsibility",
        ),
        sa.CheckConstraint(
            "oidc_issuer_sha256 ~ '^[0-9a-f]{64}$' AND oidc_subject_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_round17_staff_oidc_hashes",
        ),
        sa.CheckConstraint("local_identity IS FALSE", name="ck_round17_staff_not_local"),
    )
    op.create_table(
        "round17_eventization_readiness",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column(
            "source_id", _uuid(), sa.ForeignKey("source.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column(
            "policy_version_id",
            _uuid(),
            sa.ForeignKey("source_policy_version.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "connector_config_version_id",
            _uuid(),
            sa.ForeignKey("connector_config_version.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "trial_run_id",
            _uuid(),
            sa.ForeignKey("source_trial_run.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "production_decision_id",
            _uuid(),
            sa.ForeignKey("source_governance_decision.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("business_parser_profile_version", sa.String(100), nullable=False),
        sa.Column("business_parser_profile_sha256", sa.String(64), nullable=False),
        sa.Column("claim_evidence_profile_version", sa.String(100), nullable=False),
        sa.Column("claim_evidence_profile_sha256", sa.String(64), nullable=False),
        sa.Column("event_identity_profile_version", sa.String(100), nullable=False),
        sa.Column("event_identity_profile_sha256", sa.String(64), nullable=False),
        sa.Column("publication_projection_profile_version", sa.String(100), nullable=False),
        sa.Column("publication_projection_profile_sha256", sa.String(64), nullable=False),
        sa.Column("verification_manifest_ref", sa.String(140), nullable=False),
        sa.Column("verification_manifest", _JSON, nullable=False),
        sa.Column("verification_manifest_sha256", sa.String(64), nullable=False),
        sa.Column("verification_signature", sa.String(88), nullable=False),
        sa.Column("signer_public_key_sha256", sa.String(64), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("verified_by", _uuid(), nullable=False),
        sa.Column(
            "verified_by_display_name", sa.String(200), nullable=False, server_default="LEO"
        ),
        sa.Column(
            "verified_by_responsibility",
            sa.String(40),
            nullable=False,
            server_default="SOURCE_APPROVER",
        ),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["verified_by", "verified_by_display_name", "verified_by_responsibility"],
            [
                "round17_staff_binding.actor_id",
                "round17_staff_binding.display_name",
                "round17_staff_binding.responsibility",
            ],
            ondelete="RESTRICT",
            name="fk_round17_eventization_verified_staff",
        ),
        sa.UniqueConstraint(
            "source_id",
            "policy_version_id",
            "connector_config_version_id",
            "trial_run_id",
            "production_decision_id",
            name="uq_round17_eventization_authority_chain",
        ),
        sa.CheckConstraint("status='PASSED'", name="ck_round17_eventization_status"),
        sa.CheckConstraint(
            "business_parser_profile_sha256 ~ '^[0-9a-f]{64}$' AND "
            "claim_evidence_profile_sha256 ~ '^[0-9a-f]{64}$' AND "
            "event_identity_profile_sha256 ~ '^[0-9a-f]{64}$' AND "
            "publication_projection_profile_sha256 ~ '^[0-9a-f]{64}$' AND "
            "verification_manifest_sha256 ~ '^[0-9a-f]{64}$' AND "
            "signer_public_key_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_round17_eventization_profile_hashes",
        ),
        sa.CheckConstraint(
            "length(business_parser_profile_version) BETWEEN 1 AND 100 AND "
            "length(claim_evidence_profile_version) BETWEEN 1 AND 100 AND "
            "length(event_identity_profile_version) BETWEEN 1 AND 100 AND "
            "length(publication_projection_profile_version) BETWEEN 1 AND 100",
            name="ck_round17_eventization_profile_versions",
        ),
        sa.CheckConstraint(
            "verification_manifest_ref ~ "
            "'^urn:srbg:round17-eventization-manifest:[0-9a-f-]{36}$'",
            name="ck_round17_eventization_manifest_ref",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(verification_manifest)='object' AND "
            "verification_manifest->>'schema_version'="
            "'round17-eventization-manifest-v1' AND "
            "verification_manifest->>'outcome'='PASSED'",
            name="ck_round17_eventization_manifest_shape",
        ),
        sa.CheckConstraint(
            "verification_signature ~ '^[A-Za-z0-9+/]{86}==$'",
            name="ck_round17_eventization_signature",
        ),
        sa.CheckConstraint(
            "verified_by_display_name='LEO' AND "
            "verified_by_responsibility='SOURCE_APPROVER'",
            name="ck_round17_eventization_verifier_role",
        ),
    )
    op.create_table(
        "round17_pilot_window",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("roster_version", sa.String(80), nullable=False),
        sa.Column("metric_definition_version", sa.String(80), nullable=False),
        sa.Column("gold_definition_version", sa.String(80), nullable=False),
        sa.Column("baseline_commit", sa.String(40), nullable=False),
        sa.Column("config_version", sa.String(80), nullable=False),
        sa.Column("database_revision", sa.String(80), nullable=False),
        sa.Column("environment", sa.String(20), nullable=False),
        sa.Column("duration_hours", sa.SmallInteger(), nullable=False, server_default="168"),
        sa.Column("state", sa.String(20), nullable=False, server_default="PREPARING"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("blocker_codes", _TEXT_ARRAY, nullable=False, server_default="{}"),
        sa.Column("prepared_by", _uuid(), nullable=False),
        sa.Column("prepared_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_by", _uuid()),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("ends_at", sa.DateTime(timezone=True)),
        sa.Column("idempotency_key", sa.String(128), nullable=False, unique=True),
        sa.CheckConstraint("environment='PREPRODUCTION'", name="ck_round17_window_environment"),
        sa.CheckConstraint("duration_hours=168", name="ck_round17_window_duration"),
        sa.CheckConstraint(
            "state IN ('PREPARING','READY','RUNNING','COMPLETED','BLOCKED')",
            name="ck_round17_window_state",
        ),
        sa.CheckConstraint(
            "(state IN ('PREPARING','READY') AND started_by IS NULL "
            "AND started_at IS NULL AND ends_at IS NULL) OR "
            "(state='BLOCKED' AND ((started_by IS NULL AND started_at IS NULL "
            "AND ends_at IS NULL) OR (started_by IS NOT NULL AND started_at IS NOT NULL "
            "AND ends_at=started_at + interval '168 hours'))) OR "
            "(state IN ('RUNNING','COMPLETED') AND started_by IS NOT NULL "
            "AND started_at IS NOT NULL AND ends_at=started_at + interval '168 hours')",
            name="ck_round17_window_exact_period",
        ),
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_round17_single_running_window "
        "ON round17_pilot_window ((1)) WHERE state='RUNNING'"
    )
    op.create_table(
        "round17_pilot_window_source",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column(
            "window_id",
            _uuid(),
            sa.ForeignKey("round17_pilot_window.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "source_id", _uuid(), sa.ForeignKey("source.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column("source_code", sa.String(30), nullable=False),
        sa.Column(
            "policy_version_id",
            _uuid(),
            sa.ForeignKey("source_policy_version.id", ondelete="RESTRICT"),
        ),
        sa.Column(
            "connector_config_version_id",
            _uuid(),
            sa.ForeignKey("connector_config_version.id", ondelete="RESTRICT"),
        ),
        sa.Column("schedule_id", _uuid(), sa.ForeignKey("fetch_schedule.id", ondelete="RESTRICT")),
        sa.Column("schedule_version", sa.Integer()),
        sa.Column("interval_seconds", sa.Integer()),
        sa.Column("freshness_slo_seconds", sa.Integer()),
        sa.Column(
            "trial_run_id", _uuid(), sa.ForeignKey("source_trial_run.id", ondelete="RESTRICT")
        ),
        sa.Column(
            "production_decision_id",
            _uuid(),
            sa.ForeignKey("source_governance_decision.id", ondelete="RESTRICT"),
        ),
        sa.Column("eventization_readiness_id", _uuid(),
                  sa.ForeignKey("round17_eventization_readiness.id", ondelete="RESTRICT")),
        sa.Column("segment_number", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(20), nullable=False, server_default="PREPARING"),
        sa.Column("segment_started_at", sa.DateTime(timezone=True)),
        sa.Column("segment_ends_at", sa.DateTime(timezone=True)),
        sa.Column("paused_at", sa.DateTime(timezone=True)),
        sa.Column("pause_reason", sa.String(80)),
        sa.Column("resumed_by", _uuid()),
        sa.Column("resume_reason", sa.Text()),
        sa.Column("resume_request_id", sa.String(128), unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "window_id",
            "source_id",
            "segment_number",
            name="uq_round17_window_source_segment",
        ),
        sa.UniqueConstraint(
            "window_id",
            "source_code",
            "segment_number",
            name="uq_round17_window_source_code_segment",
        ),
        sa.CheckConstraint("segment_number > 0", name="ck_round17_source_segment_positive"),
        sa.CheckConstraint(
            "(schedule_id IS NULL AND schedule_version IS NULL "
            "AND interval_seconds IS NULL AND freshness_slo_seconds IS NULL) OR "
            "(schedule_id IS NOT NULL AND schedule_version > 0 "
            "AND interval_seconds > 0 AND freshness_slo_seconds > 0)",
            name="ck_round17_source_schedule_pins",
        ),
        sa.CheckConstraint(
            "status IN ('PREPARING','RUNNING','COMPLETED','PAUSED','FAILED')",
            name="ck_round17_source_status",
        ),
        sa.CheckConstraint(
            "(segment_started_at IS NULL AND segment_ends_at IS NULL) OR "
            "(segment_started_at IS NOT NULL AND segment_ends_at IS NOT NULL "
            "AND segment_started_at<segment_ends_at)",
            name="ck_round17_source_exact_period",
        ),
        sa.CheckConstraint(
            "(status='PAUSED' AND paused_at IS NOT NULL AND pause_reason IS NOT NULL) OR "
            "(status<>'PAUSED' AND paused_at IS NULL AND pause_reason IS NULL)",
            name="ck_round17_source_pause_fact",
        ),
        sa.CheckConstraint(
            "(segment_number=1 AND resumed_by IS NULL AND resume_reason IS NULL "
            "AND resume_request_id IS NULL) OR "
            "(segment_number>1 AND resumed_by IS NOT NULL "
            "AND source_v2_safe_audit_reason(resume_reason) IS TRUE "
            "AND length(resume_request_id) BETWEEN 8 AND 128 "
            "AND resume_request_id !~ '[[:cntrl:]]')",
            name="ck_round17_source_resume_fact",
        ),
    )
    op.add_column("fetch_run", sa.Column("pilot_window_source_id", _uuid()))
    op.create_foreign_key(
        "fk_fetch_run_round17_window_source",
        "fetch_run",
        "round17_pilot_window_source",
        ["pilot_window_source_id"],
        ["id"],
        ondelete="RESTRICT",
    )


def _create_gold_tables() -> None:
    op.create_table(
        "round17_gold_task",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column(
            "source_id",
            _uuid(),
            sa.ForeignKey("source.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("source_code", sa.String(30), nullable=False),
        sa.Column("domain", sa.String(10), nullable=False),
        sa.Column("roster_version", sa.String(80), nullable=False),
        sa.Column("gold_definition_version", sa.String(80), nullable=False),
        sa.Column(
            "production_decision_id",
            _uuid(),
            sa.ForeignKey("source_governance_decision.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("sample_kind", sa.String(30), nullable=False),
        sa.Column("sample_ref", sa.String(500), nullable=False),
        sa.Column("sample_ref_sha256", sa.String(64), nullable=False),
        sa.Column("critical_safety", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "secondary_review_required", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column("blinding_key_sha256", sa.String(64), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="ASSIGNED"),
        sa.Column("created_by", _uuid(), nullable=False),
        sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "sample_kind IN ('DOCUMENT','PAIR','EVENT','CLAIM_EVIDENCE','SEARCH_QUESTION')",
            name="ck_round17_gold_kind",
        ),
        sa.CheckConstraint(
            "status IN ('ASSIGNED','SUBMITTED','DISAGREEMENT','ARBITRATED','FROZEN')",
            name="ck_round17_gold_task_status",
        ),
        sa.CheckConstraint(
            "sample_ref_sha256 ~ '^[0-9a-f]{64}$' AND blinding_key_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_round17_gold_task_hashes",
        ),
        sa.CheckConstraint(
            "source_code ~ '^[A-Z]{3}-[0-9]{3}$'",
            name="ck_round17_gold_source_code",
        ),
        sa.CheckConstraint("domain IN ('DIGITAL','SAFETY')", name="ck_round17_gold_domain"),
        sa.CheckConstraint(
            "roster_version='r17-sources-v0.1'",
            name="ck_round17_gold_task_roster_version",
        ),
        sa.CheckConstraint(
            "gold_definition_version='phase2-round17-gold-v1.0.0'",
            name="ck_round17_gold_task_definition_version",
        ),
        sa.CheckConstraint(
            "sample_ref ~ '^urn:srbg:(document|pair|event|claim-evidence|search-question):'",
            name="ck_round17_gold_sample_ref",
        ),
        sa.CheckConstraint(
            "critical_safety IS FALSE OR (domain='SAFETY' AND secondary_review_required)",
            name="ck_round17_gold_critical_double",
        ),
        sa.UniqueConstraint(
            "sample_kind",
            "sample_ref_sha256",
            "production_decision_id",
            "gold_definition_version",
            name="uq_round17_gold_authoritative_sample",
        ),
    )
    op.create_table(
        "round17_gold_assignment",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column(
            "task_id",
            _uuid(),
            sa.ForeignKey("round17_gold_task.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("annotator_id", _uuid(), nullable=False),
        sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("task_id", "annotator_id", name="uq_round17_gold_assignment"),
    )
    op.create_table(
        "round17_gold_annotation",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column(
            "task_id",
            _uuid(),
            sa.ForeignKey("round17_gold_task.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("annotator_id", _uuid(), nullable=False),
        sa.Column("sample_kind", sa.String(30), nullable=False),
        sa.Column("decision_code", sa.String(80), nullable=False),
        sa.Column("label_value", sa.String(2000)),
        sa.Column("evidence_ids", postgresql.ARRAY(_uuid()), nullable=False, server_default="{}"),
        sa.Column("related_sample_refs", _TEXT_ARRAY, nullable=False, server_default="{}"),
        sa.Column("status", sa.String(20), nullable=False, server_default="SUBMITTED"),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("task_id", "annotator_id", name="uq_round17_gold_annotation"),
        sa.UniqueConstraint("id", "task_id", name="uq_round17_gold_annotation_task"),
        sa.CheckConstraint(
            "decision_code ~ '^[A-Z][A-Z0-9_]{1,79}$'", name="ck_round17_gold_decision"
        ),
        sa.CheckConstraint(
            "status IN ('SUBMITTED','SUPERSEDED')", name="ck_round17_annotation_status"
        ),
    )
    op.create_table(
        "round17_gold_arbitration",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column(
            "task_id",
            _uuid(),
            sa.ForeignKey("round17_gold_task.id", ondelete="RESTRICT"),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "selected_annotation_id",
            _uuid(),
            nullable=False,
        ),
        sa.Column("arbitrator_id", _uuid(), nullable=False),
        sa.Column("reason", sa.String(500), nullable=False),
        sa.Column("arbitrated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["selected_annotation_id", "task_id"],
            ["round17_gold_annotation.id", "round17_gold_annotation.task_id"],
            ondelete="RESTRICT",
            name="fk_round17_arbitration_selected_task",
        ),
    )
    op.create_table(
        "round17_gold_release",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("version", sa.String(80), nullable=False, unique=True),
        sa.Column("roster_version", sa.String(80), nullable=False),
        sa.Column("gold_definition_version", sa.String(80), nullable=False),
        sa.Column("source_codes", _TEXT_ARRAY, nullable=False),
        sa.Column("manifest_sha256", sa.String(64), nullable=False, unique=True),
        sa.Column("sample_counts", _JSON, nullable=False),
        sa.Column("agreement_metrics", _JSON, nullable=False),
        sa.Column("frozen_by", _uuid(), nullable=False),
        sa.Column("frozen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="FROZEN"),
        sa.CheckConstraint(
            "manifest_sha256 ~ '^[0-9a-f]{64}$'", name="ck_round17_gold_release_hash"
        ),
        sa.CheckConstraint(
            "roster_version='r17-sources-v0.1'",
            name="ck_round17_gold_release_roster_version",
        ),
        sa.CheckConstraint(
            "gold_definition_version='phase2-round17-gold-v1.0.0' "
            "AND version=gold_definition_version",
            name="ck_round17_gold_release_definition_version",
        ),
        sa.CheckConstraint(
            "cardinality(source_codes) BETWEEN 1 AND 20 "
            "AND array_position(source_codes,NULL) IS NULL "
            "AND array_to_string(source_codes,',') ~ "
            "'^[A-Z]{3}-[0-9]{3}(,[A-Z]{3}-[0-9]{3}){0,19}$'",
            name="ck_round17_gold_release_source_codes",
        ),
        sa.CheckConstraint("status='FROZEN'", name="ck_round17_gold_release_status"),
    )


def _create_work_and_metric_tables() -> None:
    op.create_table(
        "round17_operator_task",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column(
            "window_id",
            _uuid(),
            sa.ForeignKey("round17_pilot_window.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "source_id",
            _uuid(),
            sa.ForeignKey("source.id", ondelete="RESTRICT"),
        ),
        sa.Column("category", sa.String(40), nullable=False),
        sa.Column("assigned_to", _uuid(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="PENDING"),
        sa.Column("created_by", _uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_by", _uuid()),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.CheckConstraint(
            "category IN ('SOURCE_MAINTENANCE','EXCEPTION_HANDLING',"
            "'R3_REVIEW','COPYRIGHT_CORRECTION')",
            name="ck_round17_operator_task_category",
        ),
        sa.CheckConstraint(
            "status IN ('PENDING','IN_PROGRESS','COMPLETED')",
            name="ck_round17_operator_task_status",
        ),
        sa.CheckConstraint("version >= 1", name="ck_round17_operator_task_version"),
        sa.CheckConstraint(
            "assigned_to<>created_by AND "
            "(completed_by IS NULL OR assigned_to<>completed_by)",
            name="ck_round17_operator_task_separation",
        ),
    )
    op.create_index(
        "ix_round17_operator_task_window_status",
        "round17_operator_task",
        ["window_id", "status", "created_at"],
    )
    op.create_table(
        "round17_operator_work_session",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column(
            "task_id",
            _uuid(),
            sa.ForeignKey("round17_operator_task.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "window_id",
            _uuid(),
            sa.ForeignKey("round17_pilot_window.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("actor_id", _uuid(), nullable=False),
        sa.Column("category", sa.String(40), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_activity_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("stopped_at", sa.DateTime(timezone=True)),
        sa.Column("accrued_seconds", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("active_seconds", sa.Integer()),
        sa.Column("corrected", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.CheckConstraint(
            "category IN ('SOURCE_MAINTENANCE','EXCEPTION_HANDLING',"
            "'R3_REVIEW','COPYRIGHT_CORRECTION')",
            name="ck_round17_work_category",
        ),
        sa.CheckConstraint(
            "accrued_seconds BETWEEN 0 AND 43200 AND "
            "(active_seconds IS NULL OR active_seconds BETWEEN 0 AND 43200)",
            name="ck_round17_work_seconds",
        ),
        sa.CheckConstraint(
            "last_activity_at >= started_at AND "
            "(stopped_at IS NULL OR stopped_at >= last_activity_at)",
            name="ck_round17_work_order",
        ),
        sa.UniqueConstraint("task_id", name="uq_round17_work_session_task"),
    )
    op.create_index(
        "uq_round17_work_actor_open",
        "round17_operator_work_session",
        ["actor_id"],
        unique=True,
        postgresql_where=sa.text("stopped_at IS NULL"),
    )
    op.create_table(
        "round17_operator_work_correction",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column(
            "session_id",
            _uuid(),
            sa.ForeignKey("round17_operator_work_session.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("actor_id", _uuid(), nullable=False),
        sa.Column("corrected_by", _uuid(), nullable=False),
        sa.Column("previous_seconds", sa.Integer(), nullable=False),
        sa.Column("corrected_seconds", sa.Integer(), nullable=False),
        sa.Column("reason_code", sa.String(40), nullable=False),
        sa.Column("corrected_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "previous_seconds BETWEEN 0 AND 43200 AND corrected_seconds BETWEEN 0 AND 43200",
            name="ck_round17_work_correction_seconds",
        ),
        sa.CheckConstraint(
            "actor_id<>corrected_by",
            name="ck_round17_work_correction_separation",
        ),
        sa.CheckConstraint(
            "reason_code IN ('TIMER_INTERRUPTED','MISSED_STOP','DUPLICATE_SESSION',"
            "'ADMINISTRATIVE_CORRECTION')",
            name="ck_round17_work_correction_reason",
        ),
    )
    op.create_table(
        "round17_metric_snapshot",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column(
            "window_id",
            _uuid(),
            sa.ForeignKey("round17_pilot_window.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "gold_release_id",
            _uuid(),
            sa.ForeignKey("round17_gold_release.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("definition_version", sa.String(80), nullable=False),
        sa.Column("snapshot", _JSON, nullable=False),
        sa.Column("snapshot_sha256", sa.String(64), nullable=False, unique=True),
        sa.Column("created_by", _uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("snapshot_sha256 ~ '^[0-9a-f]{64}$'", name="ck_round17_metric_hash"),
    )


def _create_append_only_boundaries() -> None:
    for table in (
        "round17_staff_binding",
        "round17_eventization_readiness",
        "round17_gold_assignment",
        "round17_gold_annotation",
        "round17_gold_arbitration",
        "round17_gold_release",
        "round17_operator_work_correction",
        "round17_metric_snapshot",
    ):
        op.execute(
            f"""
            CREATE TRIGGER trg_{table}_immutable
            BEFORE UPDATE OR DELETE ON {table}
            FOR EACH ROW EXECUTE FUNCTION reject_immutable_source_vault_change()
            """
        )
    op.execute(
        """
        CREATE FUNCTION validate_round17_operator_task() RETURNS trigger
        LANGUAGE plpgsql SECURITY DEFINER
        SET search_path=pg_catalog,public AS $$
        BEGIN
          IF TG_OP='DELETE' THEN
            RAISE EXCEPTION 'round17 operator tasks cannot be deleted';
          END IF;
          IF TG_OP='INSERT' THEN
            IF NEW.status<>'PENDING' OR NEW.version<>1
               OR NEW.started_at IS NOT NULL OR NEW.completed_at IS NOT NULL
               OR NEW.completed_by IS NOT NULL THEN
              RAISE EXCEPTION 'round17 operator task must begin pending';
            END IF;
            IF NOT EXISTS (
              SELECT 1 FROM round17_staff_binding leo
               WHERE leo.actor_id=NEW.created_by
                 AND leo.display_name='LEO'
                 AND leo.responsibility='SOURCE_APPROVER'
                 AND leo.local_identity=false
            ) OR NOT EXISTS (
              SELECT 1 FROM round17_staff_binding operator_binding
               WHERE operator_binding.actor_id=NEW.assigned_to
                 AND operator_binding.display_name='yinzi'
                 AND operator_binding.responsibility='SOURCE_OPERATOR'
                 AND operator_binding.local_identity=false
            ) THEN
              RAISE EXCEPTION 'round17 operator task requires LEO control and yinzi assignment';
            END IF;
            IF NOT EXISTS (
              SELECT 1 FROM round17_pilot_window window_row
               WHERE window_row.id=NEW.window_id
                 AND window_row.state='RUNNING'
                 AND NEW.created_at>=window_row.started_at
                 AND NEW.created_at<window_row.ends_at
            ) OR (
              NEW.source_id IS NOT NULL AND NOT EXISTS (
                SELECT 1 FROM round17_pilot_window_source segment
                 WHERE segment.window_id=NEW.window_id
                   AND segment.source_id=NEW.source_id
              )
            ) THEN
              RAISE EXCEPTION 'round17 operator task is outside its authoritative window';
            END IF;
            RETURN NEW;
          END IF;
          IF NEW.id IS DISTINCT FROM OLD.id
             OR NEW.window_id IS DISTINCT FROM OLD.window_id
             OR NEW.source_id IS DISTINCT FROM OLD.source_id
             OR NEW.category IS DISTINCT FROM OLD.category
             OR NEW.assigned_to IS DISTINCT FROM OLD.assigned_to
             OR NEW.created_by IS DISTINCT FROM OLD.created_by
             OR NEW.created_at IS DISTINCT FROM OLD.created_at
             OR NEW.version<>OLD.version+1 THEN
            RAISE EXCEPTION 'round17 operator task authority is immutable';
          END IF;
          IF OLD.status='PENDING' AND NEW.status='IN_PROGRESS' THEN
            IF OLD.started_at IS NOT NULL OR NEW.started_at IS NULL
               OR NEW.completed_by IS NOT NULL OR NEW.completed_at IS NOT NULL THEN
              RAISE EXCEPTION 'round17 operator task start transition is invalid';
            END IF;
          ELSIF OLD.status='IN_PROGRESS' AND NEW.status='COMPLETED' THEN
            IF NEW.started_at IS DISTINCT FROM OLD.started_at
               OR NEW.completed_by IS NULL OR NEW.completed_at IS NULL
               OR NEW.completed_at<NEW.started_at
               OR NOT EXISTS (
                 SELECT 1 FROM round17_staff_binding leo
                  WHERE leo.actor_id=NEW.completed_by
                    AND leo.display_name='LEO'
                    AND leo.responsibility='SOURCE_APPROVER'
                    AND leo.local_identity=false
               ) OR NOT EXISTS (
                 SELECT 1 FROM round17_operator_work_session session
                  WHERE session.task_id=NEW.id
                    AND session.actor_id=NEW.assigned_to
                    AND session.stopped_at IS NOT NULL
                    AND session.active_seconds>0
               ) THEN
              RAISE EXCEPTION 'round17 operator task completion requires stopped yinzi work';
            END IF;
          ELSE
            RAISE EXCEPTION 'round17 operator task status transition is invalid';
          END IF;
          RETURN NEW;
        END $$
        """
    )
    op.execute(
        "CREATE TRIGGER trg_round17_operator_task_guard "
        "BEFORE INSERT OR UPDATE OR DELETE ON round17_operator_task "
        "FOR EACH ROW EXECUTE FUNCTION validate_round17_operator_task()"
    )
    op.execute(
        """
        CREATE FUNCTION validate_round17_work_session() RETURNS trigger
        LANGUAGE plpgsql SECURITY DEFINER
        SET search_path=pg_catalog,public AS $$
        BEGIN
          IF TG_OP='DELETE' THEN
            RAISE EXCEPTION 'round17 operator work sessions cannot be deleted';
          END IF;
          IF TG_OP='INSERT' THEN
            IF NEW.stopped_at IS NOT NULL OR NEW.active_seconds IS NOT NULL
               OR NEW.accrued_seconds<>0 OR NEW.corrected OR NEW.version<>1
               OR NOT EXISTS (
                 SELECT 1 FROM round17_operator_task task
                  WHERE task.id=NEW.task_id
                    AND task.window_id=NEW.window_id
                    AND task.assigned_to=NEW.actor_id
                    AND task.category=NEW.category
                    AND task.status='IN_PROGRESS'
                    AND task.started_at=NEW.started_at
               ) THEN
              RAISE EXCEPTION 'operator task/session authority mismatch';
            END IF;
            IF EXISTS (
              SELECT 1 FROM round17_operator_work_session existing
               WHERE existing.task_id=NEW.task_id
            ) THEN
              RAISE EXCEPTION 'operator task may have exactly one execution session';
            END IF;
            RETURN NEW;
          END IF;
          IF NEW.id IS DISTINCT FROM OLD.id
             OR NEW.task_id IS DISTINCT FROM OLD.task_id
             OR NEW.window_id IS DISTINCT FROM OLD.window_id
             OR NEW.actor_id IS DISTINCT FROM OLD.actor_id
             OR NEW.category IS DISTINCT FROM OLD.category
             OR NEW.started_at IS DISTINCT FROM OLD.started_at
             OR NEW.version<>OLD.version+1
             OR NEW.last_activity_at<OLD.last_activity_at
             OR OLD.stopped_at IS NOT NULL AND NEW.stopped_at IS DISTINCT FROM OLD.stopped_at
             OR NOT EXISTS (
               SELECT 1 FROM round17_operator_task task
                WHERE task.id=NEW.task_id
                  AND task.window_id=NEW.window_id
                  AND task.assigned_to=NEW.actor_id
                  AND task.category=NEW.category
                  AND task.status='IN_PROGRESS'
             ) THEN
            RAISE EXCEPTION 'operator task/session authority mismatch';
          END IF;
          RETURN NEW;
        END $$
        """
    )
    op.execute(
        "CREATE TRIGGER trg_round17_work_session_guard "
        "BEFORE INSERT OR UPDATE OR DELETE ON round17_operator_work_session "
        "FOR EACH ROW EXECUTE FUNCTION validate_round17_work_session()"
    )
    op.execute(
        """
        CREATE FUNCTION start_round17_operator_task(
          p_task_id uuid,p_session_id uuid,p_actor_id uuid,p_started_at timestamptz
        ) RETURNS uuid
        LANGUAGE plpgsql SECURITY DEFINER
        SET search_path=pg_catalog,public AS $$
        DECLARE v_task round17_operator_task%ROWTYPE;
        BEGIN
          SELECT * INTO v_task FROM round17_operator_task
           WHERE id=p_task_id FOR UPDATE;
          IF NOT FOUND OR v_task.status<>'PENDING'
             OR v_task.assigned_to<>p_actor_id
             OR EXISTS (
               SELECT 1 FROM round17_operator_work_session session
                WHERE session.task_id=p_task_id
             ) OR NOT EXISTS (
               SELECT 1 FROM round17_pilot_window window_row
                WHERE window_row.id=v_task.window_id
                  AND window_row.state='RUNNING'
                  AND p_started_at>=window_row.started_at
                  AND p_started_at<window_row.ends_at
             ) THEN
            RAISE EXCEPTION 'operator task may have exactly one execution session';
          END IF;
          UPDATE round17_operator_task
             SET status='IN_PROGRESS',started_at=p_started_at,version=version+1
           WHERE id=p_task_id;
          INSERT INTO round17_operator_work_session(
            id,task_id,window_id,actor_id,category,started_at,last_activity_at,
            accrued_seconds,corrected,version
          ) VALUES (
            p_session_id,p_task_id,v_task.window_id,p_actor_id,v_task.category,
            p_started_at,p_started_at,0,false,1
          );
          RETURN p_session_id;
        END $$
        """
    )
    op.execute(
        """
        CREATE FUNCTION complete_round17_operator_task(
          p_task_id uuid,p_expected_version integer,p_completed_by uuid,
          p_completed_at timestamptz
        ) RETURNS uuid
        LANGUAGE plpgsql SECURITY DEFINER
        SET search_path=pg_catalog,public AS $$
        DECLARE v_task round17_operator_task%ROWTYPE;
        BEGIN
          SELECT * INTO v_task FROM round17_operator_task
           WHERE id=p_task_id FOR UPDATE;
          IF NOT FOUND OR v_task.status<>'IN_PROGRESS'
             OR v_task.version<>p_expected_version
             OR NOT EXISTS (
               SELECT 1 FROM round17_operator_work_session session
                WHERE session.task_id=p_task_id
                  AND session.actor_id=v_task.assigned_to
                  AND session.stopped_at IS NOT NULL
                  AND session.active_seconds>0
             ) THEN
            RAISE EXCEPTION 'round17 operator task is not ready for completion';
          END IF;
          UPDATE round17_operator_task
             SET status='COMPLETED',completed_by=p_completed_by,
                 completed_at=p_completed_at,version=version+1
           WHERE id=p_task_id;
          RETURN p_task_id;
        END $$
        """
    )
    op.execute(
        """
        CREATE FUNCTION validate_round17_work_correction() RETURNS trigger
        LANGUAGE plpgsql SECURITY DEFINER
        SET search_path=pg_catalog,public AS $$
        BEGIN
          IF NOT EXISTS (
            SELECT 1
              FROM round17_operator_work_session session
              JOIN round17_staff_binding operator_binding
                ON operator_binding.actor_id=session.actor_id
               AND operator_binding.display_name='yinzi'
               AND operator_binding.responsibility='SOURCE_OPERATOR'
               AND operator_binding.local_identity=false
              JOIN round17_staff_binding leo_binding
                ON leo_binding.actor_id=NEW.corrected_by
               AND leo_binding.display_name='LEO'
               AND leo_binding.responsibility='SOURCE_APPROVER'
               AND leo_binding.local_identity=false
             WHERE session.id=NEW.session_id
               AND session.actor_id=NEW.actor_id
               AND session.actor_id<>NEW.corrected_by
               AND session.stopped_at IS NOT NULL
               AND session.active_seconds=NEW.previous_seconds
          ) THEN
            RAISE EXCEPTION
              'round17 work correction requires LEO review of yinzi evidence';
          END IF;
          RETURN NEW;
        END $$
        """
    )
    op.execute(
        "CREATE TRIGGER trg_round17_work_correction_guard "
        "BEFORE INSERT ON round17_operator_work_correction "
        "FOR EACH ROW EXECUTE FUNCTION validate_round17_work_correction()"
    )
    op.execute(
        """
        CREATE FUNCTION protect_round17_source_segment_pins() RETURNS trigger
        LANGUAGE plpgsql SECURITY DEFINER
        SET search_path=pg_catalog,public AS $$
        DECLARE
          v_window round17_pilot_window%ROWTYPE;
          v_previous round17_pilot_window_source%ROWTYPE;
        BEGIN
          IF TG_OP='DELETE' THEN
            RAISE EXCEPTION 'round17 source segments cannot be deleted';
          END IF;
          IF TG_OP='INSERT' THEN
            IF NEW.segment_number=1 THEN
              IF NEW.status<>'PREPARING'
                 OR NEW.segment_started_at IS NOT NULL
                 OR NEW.segment_ends_at IS NOT NULL
                 OR NEW.resumed_by IS NOT NULL
                 OR NEW.resume_reason IS NOT NULL
                 OR NEW.resume_request_id IS NOT NULL THEN
                RAISE EXCEPTION 'initial source segment must begin in PREPARING state';
              END IF;
              RETURN NEW;
            END IF;
            SELECT * INTO v_window
              FROM round17_pilot_window
             WHERE id=NEW.window_id FOR UPDATE;
            SELECT * INTO v_previous
              FROM round17_pilot_window_source
             WHERE window_id=NEW.window_id AND source_id=NEW.source_id
               AND source_code=NEW.source_code
               AND segment_number=NEW.segment_number-1
             FOR UPDATE;
            IF NOT FOUND OR v_previous.status<>'PAUSED'
               OR EXISTS (
                 SELECT 1 FROM round17_pilot_window_source later
                  WHERE later.window_id=NEW.window_id
                    AND later.source_id=NEW.source_id
                    AND later.segment_number>=NEW.segment_number
               ) THEN
              RAISE EXCEPTION 'previous source segment must be PAUSED';
            END IF;
            IF v_window.state<>'RUNNING'
               OR statement_timestamp()<v_window.started_at
               OR statement_timestamp()>=v_window.ends_at
               OR NEW.status<>'RUNNING'
               OR NEW.segment_started_at IS NULL
               OR NEW.segment_started_at<statement_timestamp()-interval '5 minutes'
               OR NEW.segment_started_at>statement_timestamp()+interval '5 minutes'
               OR NEW.segment_started_at>=v_window.ends_at
               OR NEW.segment_ends_at IS DISTINCT FROM v_window.ends_at
               OR v_previous.pause_reason NOT IN (
                    'SOURCE_AUTHORITY_CHANGED','SOURCE_SCHEDULE_CHANGED',
                    'SOURCE_RUNTIME_ANOMALY'
                  ) THEN
              RAISE EXCEPTION 'resumed source segment is outside its immutable window';
            END IF;
            IF NOT EXISTS (
              SELECT 1
                FROM source source_row
                JOIN source_policy_version policy
                  ON policy.id=source_row.current_policy_version_id
                 AND policy.id=NEW.policy_version_id
                 AND policy.source_id=source_row.id
                JOIN connector_config_version config
                  ON config.id=source_row.current_connector_config_version_id
                 AND config.id=NEW.connector_config_version_id
                 AND config.source_id=source_row.id
                 AND config.policy_version_id=policy.id
                JOIN fetch_schedule schedule
                  ON schedule.source_id=source_row.id
                 AND schedule.id=NEW.schedule_id
                 AND schedule.version=NEW.schedule_version
                 AND schedule.interval_seconds=NEW.interval_seconds
                 AND schedule.freshness_slo_seconds=NEW.freshness_slo_seconds
                JOIN source_trial_run trial
                  ON trial.id=source_row.current_trial_run_id
                 AND trial.id=NEW.trial_run_id
                 AND trial.source_id=source_row.id
                 AND trial.policy_version_id=policy.id
                 AND trial.connector_config_version_id=config.id
                JOIN source_trial_run_result result ON result.trial_run_id=trial.id
                JOIN source_governance_decision decision
                  ON decision.id=NEW.production_decision_id
                 AND decision.source_id=source_row.id
                 AND decision.policy_version_id=policy.id
                 AND decision.connector_config_version_id=config.id
                 AND decision.trial_run_id=trial.id
                JOIN source_governance_scheme_assignment assignment
                  ON assignment.source_id=source_row.id
                JOIN round17_staff_binding leo
                  ON leo.actor_id=NEW.resumed_by
                 AND leo.display_name='LEO'
                 AND leo.responsibility='SOURCE_APPROVER'
                 AND leo.local_identity=false
                JOIN round17_eventization_readiness readiness
                  ON readiness.id=NEW.eventization_readiness_id
                 AND readiness.source_id=source_row.id
                 AND readiness.policy_version_id=policy.id
                 AND readiness.connector_config_version_id=config.id
                 AND readiness.trial_run_id=trial.id
                 AND readiness.production_decision_id=decision.id
               WHERE source_row.id=NEW.source_id
                 AND source_row.registry_code=NEW.source_code
                 AND source_row.lifecycle_state='ACTIVE'
                 AND policy.status='APPROVED'
                 AND policy.valid_from<=statement_timestamp()
                 AND policy.valid_until>=v_window.ends_at
                 AND policy.document->>'storage_policy'='RAW_EVIDENCE_ALLOWED'
                 AND config.validation_status='VALID'
                 AND schedule.status='ACTIVE'
                 AND trial.kind='LIVE_TRIAL' AND trial.execution_domain='TRIAL'
                 AND result.status='SUCCEEDED'
                 AND decision.decision_type='PRODUCTION_APPROVAL'
                 AND decision.outcome='APPROVED'
                 AND decision.decided_by=NEW.resumed_by
                 AND (decision.valid_until IS NULL
                      OR decision.valid_until>=v_window.ends_at)
                 AND decision.id=(
                   SELECT current_decision.id
                     FROM source_governance_decision current_decision
                    WHERE current_decision.source_id=source_row.id
                      AND current_decision.decision_type='PRODUCTION_APPROVAL'
                    ORDER BY current_decision.created_at DESC,current_decision.id DESC
                    LIMIT 1
                 )
                 AND assignment.scheme='R17_TWO_PERSON_MAKER_CHECKER_V1'
                 AND assignment.cohort_key=v_window.roster_version
                 AND assignment.assigned_by=NEW.resumed_by
                 AND readiness.status='PASSED'
                 AND source_v2_policy_compliance_approved(
                       source_row.id,policy.id,statement_timestamp()
                     ) IS TRUE
                 AND (
                   v_previous.pause_reason<>'SOURCE_RUNTIME_ANOMALY'
                   OR NOT EXISTS (
                     SELECT 1 FROM source_anomaly anomaly
                      WHERE anomaly.source_id=source_row.id
                        AND (
                          anomaly.severity='CRITICAL'
                          OR anomaly.code IN (
                            'ZERO_DISCOVERY_STREAK','BODY_LENGTH_SHIFT',
                            'REQUIRED_FIELDS_MISSING','DOM_FINGERPRINT_CHANGED'
                          )
                        )
                        AND (
                          anomaly.status<>'RESOLVED' OR anomaly.resolved_at IS NULL
                        )
                   )
                 )
            ) THEN
              RAISE EXCEPTION 'current source authority is not eligible for resume';
            END IF;
            UPDATE round17_pilot_window window_row
               SET version=version+1,
                   blocker_codes=CASE
                     WHEN EXISTS (
                       SELECT 1 FROM round17_pilot_window_source blocked
                        WHERE blocked.window_id=NEW.window_id
                          AND blocked.source_id<>NEW.source_id
                          AND blocked.status='PAUSED'
                          AND blocked.pause_reason=v_previous.pause_reason
                          AND NOT EXISTS (
                            SELECT 1 FROM round17_pilot_window_source later
                             WHERE later.window_id=blocked.window_id
                               AND later.source_id=blocked.source_id
                               AND later.segment_number>blocked.segment_number
                          )
                     ) THEN blocker_codes
                     ELSE array_remove(blocker_codes,v_previous.pause_reason)
                   END
             WHERE window_row.id=NEW.window_id;
            RETURN NEW;
          END IF;
          IF OLD.window_id<>NEW.window_id OR OLD.source_id<>NEW.source_id
             OR OLD.source_code<>NEW.source_code
             OR OLD.policy_version_id IS DISTINCT FROM NEW.policy_version_id
             OR OLD.connector_config_version_id
                  IS DISTINCT FROM NEW.connector_config_version_id
             OR OLD.schedule_id IS DISTINCT FROM NEW.schedule_id
             OR OLD.schedule_version IS DISTINCT FROM NEW.schedule_version
             OR OLD.interval_seconds IS DISTINCT FROM NEW.interval_seconds
             OR OLD.freshness_slo_seconds IS DISTINCT FROM NEW.freshness_slo_seconds
             OR OLD.trial_run_id IS DISTINCT FROM NEW.trial_run_id
             OR OLD.production_decision_id
                  IS DISTINCT FROM NEW.production_decision_id
             OR OLD.eventization_readiness_id
                  IS DISTINCT FROM NEW.eventization_readiness_id
             OR OLD.segment_number<>NEW.segment_number
             OR (OLD.segment_started_at IS NOT NULL AND OLD.segment_started_at
                   IS DISTINCT FROM NEW.segment_started_at)
             OR (OLD.segment_ends_at IS NOT NULL AND OLD.segment_ends_at
                   IS DISTINCT FROM NEW.segment_ends_at)
             OR (OLD.paused_at IS NOT NULL AND OLD.paused_at
                   IS DISTINCT FROM NEW.paused_at)
             OR (OLD.pause_reason IS NOT NULL AND OLD.pause_reason
                   IS DISTINCT FROM NEW.pause_reason)
             OR OLD.resumed_by IS DISTINCT FROM NEW.resumed_by
             OR OLD.resume_reason IS DISTINCT FROM NEW.resume_reason
             OR OLD.resume_request_id IS DISTINCT FROM NEW.resume_request_id
             OR OLD.created_at<>NEW.created_at THEN
            RAISE EXCEPTION 'round17 source segment pins are immutable';
          END IF;
          IF NOT (
               (OLD.status='PREPARING' AND NEW.status IN ('PREPARING','RUNNING','FAILED'))
               OR (OLD.status='RUNNING'
                   AND NEW.status IN ('RUNNING','PAUSED','COMPLETED','FAILED'))
               OR OLD.status=NEW.status
             ) THEN
            RAISE EXCEPTION 'round17 source segment status transition is invalid';
          END IF;
          IF OLD.status='RUNNING' AND NEW.status='COMPLETED'
             AND statement_timestamp()<OLD.segment_ends_at THEN
            RAISE EXCEPTION 'source segment cannot complete before segment_ends_at';
          END IF;
          RETURN NEW;
        END $$
        """
    )
    op.execute(
        "CREATE TRIGGER trg_round17_source_segment_pins "
        "BEFORE INSERT OR UPDATE OR DELETE ON round17_pilot_window_source "
        "FOR EACH ROW EXECUTE FUNCTION protect_round17_source_segment_pins()"
    )
    op.execute(
        """
        CREATE FUNCTION protect_round17_window_pins() RETURNS trigger
        LANGUAGE plpgsql AS $$
        DECLARE
          v_latest_count integer;
          v_invalid_count integer;
        BEGIN
          IF TG_OP='INSERT' THEN
            IF NEW.state<>'PREPARING' OR NEW.version<>1
               OR NEW.started_by IS NOT NULL OR NEW.started_at IS NOT NULL
               OR NEW.ends_at IS NOT NULL THEN
              RAISE EXCEPTION 'round17 pilot windows must begin in PREPARING state';
            END IF;
            RETURN NEW;
          END IF;
          IF OLD.roster_version<>NEW.roster_version
             OR OLD.metric_definition_version<>NEW.metric_definition_version
             OR OLD.gold_definition_version<>NEW.gold_definition_version
             OR OLD.baseline_commit<>NEW.baseline_commit
             OR OLD.config_version<>NEW.config_version
             OR OLD.database_revision<>NEW.database_revision
             OR OLD.environment<>NEW.environment
             OR OLD.duration_hours<>NEW.duration_hours
             OR OLD.prepared_by<>NEW.prepared_by OR OLD.prepared_at<>NEW.prepared_at THEN
            RAISE EXCEPTION 'round17 pilot window pinned versions are immutable';
          END IF;
          IF (OLD.started_by IS NOT NULL AND OLD.started_by IS DISTINCT FROM NEW.started_by)
             OR (OLD.started_at IS NOT NULL AND OLD.started_at IS DISTINCT FROM NEW.started_at)
             OR (OLD.ends_at IS NOT NULL AND OLD.ends_at IS DISTINCT FROM NEW.ends_at) THEN
            RAISE EXCEPTION 'round17 pilot window start facts are immutable';
          END IF;
          IF OLD.state='RUNNING' AND NEW.state='COMPLETED' THEN
            IF statement_timestamp()<OLD.ends_at THEN
              RAISE EXCEPTION 'pilot window cannot complete before ends_at';
            END IF;
            WITH latest AS (
              SELECT DISTINCT ON (source_id) source_id,source_code,status
                FROM round17_pilot_window_source
               WHERE window_id=OLD.id
               ORDER BY source_id,segment_number DESC
            )
            SELECT count(*),count(*) FILTER (
                     WHERE status NOT IN ('COMPLETED','PAUSED','FAILED')
                   )
              INTO v_latest_count,v_invalid_count FROM latest;
            IF v_latest_count<>20 OR v_invalid_count<>0 OR (
                 SELECT count(DISTINCT source_code)
                   FROM (
                     SELECT DISTINCT ON (source_id) source_id,source_code
                       FROM round17_pilot_window_source
                      WHERE window_id=OLD.id
                      ORDER BY source_id,segment_number DESC
                   ) latest_codes
               )<>20 THEN
              RAISE EXCEPTION 'pilot window requires 20 honest final source states';
            END IF;
          END IF;
          IF NOT (
               (OLD.state='PREPARING'
                 AND NEW.state IN ('PREPARING','READY','BLOCKED'))
               OR (OLD.state='READY' AND NEW.state IN ('READY','RUNNING','BLOCKED'))
               OR (OLD.state='BLOCKED' AND OLD.started_at IS NULL
                 AND NEW.state IN ('BLOCKED','RUNNING'))
               OR (OLD.state='RUNNING'
                 AND NEW.state IN ('RUNNING','COMPLETED','BLOCKED'))
               OR (OLD.state='BLOCKED' AND OLD.started_at IS NOT NULL
                 AND NEW.state='BLOCKED')
               OR (OLD.state='COMPLETED' AND NEW.state='COMPLETED')
             ) THEN
            RAISE EXCEPTION 'round17 pilot window status transition is invalid';
          END IF;
          IF NEW.version < OLD.version OR NEW.version > OLD.version + 1 THEN
            RAISE EXCEPTION 'round17 pilot window version transition is invalid';
          END IF;
          IF (OLD.state IS DISTINCT FROM NEW.state
              OR OLD.blocker_codes IS DISTINCT FROM NEW.blocker_codes
              OR OLD.started_by IS DISTINCT FROM NEW.started_by
              OR OLD.started_at IS DISTINCT FROM NEW.started_at
              OR OLD.ends_at IS DISTINCT FROM NEW.ends_at)
             AND NEW.version<>OLD.version+1 THEN
            RAISE EXCEPTION 'round17 pilot window fact changes require a new version';
          END IF;
          RETURN NEW;
        END $$
        """
    )
    op.execute(
        "CREATE TRIGGER trg_round17_window_pins BEFORE INSERT OR UPDATE "
        "ON round17_pilot_window "
        "FOR EACH ROW EXECUTE FUNCTION protect_round17_window_pins()"
    )
    op.execute(
        """
        CREATE FUNCTION protect_fetch_run_origin() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
          IF OLD.run_origin<>NEW.run_origin
             OR OLD.replayed_from_run_id IS DISTINCT FROM NEW.replayed_from_run_id
             OR OLD.pilot_window_source_id IS DISTINCT FROM NEW.pilot_window_source_id THEN
            RAISE EXCEPTION 'fetch run provenance is immutable';
          END IF;
          RETURN NEW;
        END $$
        """
    )
    op.execute(
        "CREATE TRIGGER trg_fetch_run_origin_immutable BEFORE UPDATE ON fetch_run "
        "FOR EACH ROW EXECUTE FUNCTION protect_fetch_run_origin()"
    )


def _create_window_binding_boundary() -> None:
    op.execute(
        """
        CREATE FUNCTION bind_round17_fetch_run() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
          IF NEW.run_origin='SCHEDULED' AND NEW.execution_domain='PRODUCTION'
             AND NEW.source_id IS NOT NULL THEN
            SELECT segment.id INTO NEW.pilot_window_source_id
              FROM round17_pilot_window_source segment
              JOIN round17_pilot_window window_row ON window_row.id=segment.window_id
              JOIN fetch_schedule pinned_schedule ON pinned_schedule.id=segment.schedule_id
             WHERE segment.source_id=NEW.source_id
               AND segment.status='RUNNING' AND window_row.state='RUNNING'
               AND NEW.policy_version_id=segment.policy_version_id
               AND NEW.connector_config_version_id=segment.connector_config_version_id
               AND NEW.schedule_id=segment.schedule_id
               AND pinned_schedule.version=segment.schedule_version
               AND pinned_schedule.interval_seconds=segment.interval_seconds
               AND pinned_schedule.freshness_slo_seconds=segment.freshness_slo_seconds
               AND NEW.started_at>=segment.segment_started_at
               AND NEW.started_at<segment.segment_ends_at
             ORDER BY segment.segment_number DESC LIMIT 1;
          END IF;
          RETURN NEW;
        END $$
        """
    )
    op.execute(
        "CREATE TRIGGER trg_fetch_run_bind_round17 BEFORE INSERT ON fetch_run "
        "FOR EACH ROW EXECUTE FUNCTION bind_round17_fetch_run()"
    )
    op.execute(
        """
        CREATE FUNCTION pause_round17_segments_on_source_change() RETURNS trigger
        LANGUAGE plpgsql SECURITY DEFINER
        SET search_path=pg_catalog,public AS $$
        BEGIN
          IF OLD.lifecycle_state IS DISTINCT FROM NEW.lifecycle_state
             OR OLD.current_policy_version_id
                  IS DISTINCT FROM NEW.current_policy_version_id
             OR OLD.current_connector_config_version_id
                  IS DISTINCT FROM NEW.current_connector_config_version_id
             OR OLD.current_trial_run_id IS DISTINCT FROM NEW.current_trial_run_id THEN
            UPDATE round17_pilot_window_source segment
               SET status='PAUSED',paused_at=statement_timestamp(),
                   pause_reason='SOURCE_AUTHORITY_CHANGED'
             WHERE segment.source_id=NEW.id AND segment.status='RUNNING'
               AND EXISTS (
                 SELECT 1 FROM round17_pilot_window window_row
                  WHERE window_row.id=segment.window_id AND window_row.state='RUNNING'
               );
            IF FOUND THEN
              UPDATE round17_pilot_window window_row
               SET version=version+1,
                   blocker_codes=CASE
                     WHEN 'SOURCE_AUTHORITY_CHANGED'=ANY(blocker_codes)
                       THEN blocker_codes
                     ELSE array_append(blocker_codes,'SOURCE_AUTHORITY_CHANGED') END
             WHERE window_row.state='RUNNING' AND EXISTS (
               SELECT 1 FROM round17_pilot_window_source segment
                WHERE segment.window_id=window_row.id AND segment.source_id=NEW.id
                  AND segment.status='PAUSED'
                  AND segment.pause_reason='SOURCE_AUTHORITY_CHANGED'
             );
            END IF;
          END IF;
          RETURN NEW;
        END $$
        """
    )
    op.execute(
        "CREATE TRIGGER trg_round17_source_authority_change "
        "AFTER UPDATE ON source FOR EACH ROW "
        "EXECUTE FUNCTION pause_round17_segments_on_source_change()"
    )
    op.execute(
        """
        CREATE FUNCTION pause_round17_segments_on_schedule_change() RETURNS trigger
        LANGUAGE plpgsql SECURITY DEFINER
        SET search_path=pg_catalog,public AS $$
        BEGIN
          IF OLD.status IS DISTINCT FROM NEW.status
             OR OLD.version IS DISTINCT FROM NEW.version
             OR OLD.interval_seconds IS DISTINCT FROM NEW.interval_seconds
             OR OLD.freshness_slo_seconds IS DISTINCT FROM NEW.freshness_slo_seconds THEN
            UPDATE round17_pilot_window_source segment
               SET status='PAUSED',paused_at=statement_timestamp(),
                   pause_reason='SOURCE_SCHEDULE_CHANGED'
             WHERE segment.schedule_id=NEW.id AND segment.status='RUNNING'
               AND EXISTS (
                 SELECT 1 FROM round17_pilot_window window_row
                  WHERE window_row.id=segment.window_id AND window_row.state='RUNNING'
               );
            IF FOUND THEN
              UPDATE round17_pilot_window window_row
               SET version=version+1,
                   blocker_codes=CASE
                     WHEN 'SOURCE_SCHEDULE_CHANGED'=ANY(blocker_codes)
                       THEN blocker_codes
                     ELSE array_append(blocker_codes,'SOURCE_SCHEDULE_CHANGED') END
             WHERE window_row.state='RUNNING' AND EXISTS (
               SELECT 1 FROM round17_pilot_window_source segment
                WHERE segment.window_id=window_row.id AND segment.schedule_id=NEW.id
                  AND segment.status='PAUSED'
                  AND segment.pause_reason='SOURCE_SCHEDULE_CHANGED'
             );
            END IF;
          END IF;
          RETURN NEW;
        END $$
        """
    )
    op.execute(
        "CREATE TRIGGER trg_round17_schedule_change "
        "AFTER UPDATE ON fetch_schedule FOR EACH ROW "
        "EXECUTE FUNCTION pause_round17_segments_on_schedule_change()"
    )
    op.execute(
        """
        CREATE FUNCTION pause_round17_segments_on_anomaly() RETURNS trigger
        LANGUAGE plpgsql SECURITY DEFINER
        SET search_path=pg_catalog,public AS $$
        BEGIN
          IF NEW.status='OPEN' AND (
               NEW.severity='CRITICAL'
               OR NEW.code IN (
                 'ZERO_DISCOVERY_STREAK','BODY_LENGTH_SHIFT',
                 'REQUIRED_FIELDS_MISSING','DOM_FINGERPRINT_CHANGED'
               )
             ) THEN
            UPDATE round17_pilot_window_source segment
               SET status='PAUSED',paused_at=NEW.detected_at,
                   pause_reason='SOURCE_RUNTIME_ANOMALY'
             WHERE segment.source_id=NEW.source_id AND segment.status='RUNNING'
               AND EXISTS (
                 SELECT 1 FROM round17_pilot_window window_row
                  WHERE window_row.id=segment.window_id AND window_row.state='RUNNING'
               );
            IF FOUND THEN
              UPDATE round17_pilot_window window_row
               SET version=version+1,
                   blocker_codes=CASE
                     WHEN 'SOURCE_RUNTIME_ANOMALY'=ANY(blocker_codes)
                       THEN blocker_codes
                     ELSE array_append(blocker_codes,'SOURCE_RUNTIME_ANOMALY') END
             WHERE window_row.state='RUNNING' AND EXISTS (
               SELECT 1 FROM round17_pilot_window_source segment
                WHERE segment.window_id=window_row.id AND segment.source_id=NEW.source_id
                  AND segment.status='PAUSED'
                  AND segment.pause_reason='SOURCE_RUNTIME_ANOMALY'
             );
            END IF;
          END IF;
          RETURN NEW;
        END $$
        """
    )
    op.execute(
        "CREATE TRIGGER trg_round17_source_anomaly "
        "AFTER INSERT ON source_anomaly FOR EACH ROW "
        "EXECUTE FUNCTION pause_round17_segments_on_anomaly()"
    )


def _create_scheduled_runtime_boundaries() -> None:
    op.execute(
        r"""
        CREATE FUNCTION record_scheduled_source_raw(
          p_raw_object_id uuid,p_capture_id uuid,p_source_id uuid,p_fetch_run_id uuid,
          p_content_sha256 text,p_response_sha256 text,p_object_key text,
          p_storage_etag text,p_byte_size bigint,p_declared_mime text,
          p_detected_mime text,p_security_status text,p_security_reason text,
          p_requested_url text,p_final_url text,p_redirect_chain jsonb,
          p_http_status integer,p_etag text,p_last_modified text,
          p_captured_at timestamptz
        ) RETURNS TABLE(raw_object_id uuid,capture_id uuid)
        LANGUAGE plpgsql SECURITY DEFINER
        SET search_path=pg_catalog,public AS $$
        DECLARE
          v_allowed_hosts text[];
          v_raw_id uuid;
          v_requested_host text;
          v_final_host text;
          v_security_status text;
          v_now timestamptz := statement_timestamp();
        BEGIN
          SELECT config.allowed_hosts INTO v_allowed_hosts
            FROM fetch_run run
            JOIN source source_row ON source_row.id=run.source_id
            JOIN source_policy_version policy ON policy.id=source_row.current_policy_version_id
            JOIN connector_config_version config
              ON config.id=source_row.current_connector_config_version_id
            JOIN fetch_schedule schedule ON schedule.id=run.schedule_id
            JOIN round17_pilot_window_source segment
              ON segment.id=run.pilot_window_source_id
            JOIN round17_pilot_window window_row ON window_row.id=segment.window_id
            JOIN source_governance_decision decision
              ON decision.id=segment.production_decision_id
           WHERE run.id=p_fetch_run_id AND run.source_id=p_source_id
             AND run.run_origin='SCHEDULED' AND run.trigger='SCHEDULED'
             AND run.execution_domain='PRODUCTION'
             AND run.status='RUNNING'
             AND run.execution_lease_token IS NOT NULL
             AND run.execution_lease_until>v_now
             AND run.execution_lease_until>=p_captured_at
             AND run.policy_version_id=policy.id
             AND run.connector_config_version_id=config.id
             AND source_row.lifecycle_state='ACTIVE'
             AND policy.status='APPROVED' AND policy.valid_from<=v_now
             AND policy.valid_until>v_now
             AND policy.valid_from<=p_captured_at AND policy.valid_until>p_captured_at
             AND policy.document->>'storage_policy'='RAW_EVIDENCE_ALLOWED'
             AND config.validation_status='VALID' AND schedule.status='ACTIVE'
             AND schedule.version=segment.schedule_version
             AND schedule.interval_seconds=segment.interval_seconds
             AND schedule.freshness_slo_seconds=segment.freshness_slo_seconds
             AND segment.source_id=source_row.id AND segment.status='RUNNING'
             AND segment.policy_version_id=policy.id
             AND segment.connector_config_version_id=config.id
             AND segment.schedule_id=schedule.id
             AND segment.trial_run_id=source_row.current_trial_run_id
             AND window_row.state='RUNNING'
             AND v_now>=segment.segment_started_at
             AND v_now<segment.segment_ends_at
             AND v_now>=window_row.started_at AND v_now<window_row.ends_at
             AND run.started_at<=p_captured_at AND p_captured_at<=v_now
             AND p_captured_at>=segment.segment_started_at
             AND p_captured_at<segment.segment_ends_at
             AND decision.source_id=source_row.id
             AND decision.policy_version_id=policy.id
             AND decision.connector_config_version_id=config.id
             AND decision.trial_run_id=source_row.current_trial_run_id
             AND decision.decision_type='PRODUCTION_APPROVAL'
             AND decision.outcome='APPROVED'
             AND (decision.valid_until IS NULL OR decision.valid_until>v_now)
             AND (decision.valid_until IS NULL OR decision.valid_until>p_captured_at)
           FOR UPDATE OF run,source_row,segment,window_row,schedule,decision;
          v_requested_host := regexp_replace(
            split_part(split_part(p_requested_url,'://',2),'/',1),':[0-9]+$',''
          );
          v_final_host := regexp_replace(
            split_part(split_part(p_final_url,'://',2),'/',1),':[0-9]+$',''
          );
          IF NOT FOUND
             OR p_content_sha256 !~ '^[0-9a-f]{64}$'
             OR p_response_sha256 !~ '^[0-9a-f]{64}$'
             OR p_byte_size NOT BETWEEN 0 AND 52428800
             OR p_object_key <> 'sha256/' || substring(p_content_sha256,1,2)
                                || '/' || p_content_sha256
             OR length(p_storage_etag) NOT BETWEEN 1 AND 200
             OR length(p_declared_mime) NOT BETWEEN 1 AND 100
             OR length(p_detected_mime) NOT BETWEEN 1 AND 100
             OR p_security_status NOT IN ('CLEAN','REJECTED')
             OR (p_security_status='CLEAN' AND p_security_reason IS NOT NULL)
             OR (p_security_status='REJECTED' AND (
                  p_security_reason IS NULL
                  OR p_security_reason !~ '^[A-Z0-9_:-]{1,100}$'
                ))
             OR p_http_status NOT BETWEEN 100 AND 599
             OR jsonb_typeof(p_redirect_chain) IS DISTINCT FROM 'array'
             OR jsonb_array_length(p_redirect_chain)>10
             OR source_v2_safe_http_url(p_requested_url,v_allowed_hosts) IS DISTINCT FROM true
             OR source_v2_safe_http_url(p_final_url,v_allowed_hosts) IS DISTINCT FROM true
             OR v_requested_host<>v_final_host
             OR EXISTS (
               SELECT 1 FROM jsonb_array_elements(p_redirect_chain) entry
                WHERE jsonb_typeof(entry)<>'string'
                   OR source_v2_safe_http_url(entry #>> '{}',v_allowed_hosts) IS DISTINCT FROM true
                   OR regexp_replace(
                        split_part(split_part(entry #>> '{}','://',2),'/',1),
                        ':[0-9]+$',''
                      )<>v_requested_host
             ) THEN
            RAISE EXCEPTION 'scheduled source raw capture is not authorized';
          END IF;
          INSERT INTO raw_object(
            id,sha256,object_key,byte_size,declared_mime,detected_mime,
            scan_status,storage_etag,created_at
          ) VALUES (
            p_raw_object_id,p_content_sha256,p_object_key,p_byte_size,p_declared_mime,
            p_detected_mime,p_security_status,p_storage_etag,p_captured_at
          ) ON CONFLICT (sha256) DO NOTHING;
          SELECT id INTO v_raw_id FROM raw_object
           WHERE sha256=p_content_sha256
             AND object_key=p_object_key
             AND byte_size=p_byte_size
             AND detected_mime=p_detected_mime;
          IF v_raw_id IS NULL THEN
            RAISE EXCEPTION 'scheduled source raw object identity is inconsistent';
          END IF;
          INSERT INTO raw_object_security_fact(
            id,raw_object_id,status,detected_mime,rule_version,reason_code,created_at
          ) VALUES (
            p_raw_object_id,v_raw_id,p_security_status,p_detected_mime,
            'round17-runtime-security-v1.0.0',
            COALESCE(p_security_reason,'SCHEDULED_CAPTURE_CLEAN'),p_captured_at
          ) ON CONFLICT ON CONSTRAINT uq_raw_security_object_rule DO NOTHING;
          SELECT fact.status INTO v_security_status
            FROM raw_object_security_fact fact
           WHERE fact.raw_object_id=v_raw_id
             AND fact.rule_version='round17-runtime-security-v1.0.0';
          IF v_security_status IS DISTINCT FROM p_security_status THEN
            RAISE EXCEPTION 'scheduled source raw security fact is inconsistent';
          END IF;
          INSERT INTO raw_object_capture(
            id,raw_object_id,source_id,fetch_run_id,trial_run_id,execution_domain,
            requested_url,final_url,redirect_chain,http_status,etag,last_modified,
            response_sha256,arrived_after_close,captured_at
          ) VALUES (
            p_capture_id,v_raw_id,p_source_id,p_fetch_run_id,NULL,'PRODUCTION',
            p_requested_url,p_final_url,p_redirect_chain,p_http_status,p_etag,
            p_last_modified,p_response_sha256,false,p_captured_at
          );
          raw_object_id := v_raw_id;
          capture_id := p_capture_id;
          RETURN NEXT;
        END $$
        """
    )
    raw_signature = (
        "record_scheduled_source_raw(uuid,uuid,uuid,uuid,text,text,text,text,bigint,text,"
        "text,text,text,text,text,jsonb,integer,text,text,timestamptz)"
    )
    op.execute(f"REVOKE ALL ON FUNCTION {raw_signature} FROM PUBLIC")
    op.execute(f"GRANT EXECUTE ON FUNCTION {raw_signature} TO srbg_worker_role")
    op.execute(
        """
        CREATE FUNCTION record_scheduled_source_document(
          p_document_id uuid,p_version_id uuid,p_received_event_id uuid,
          p_security_event_id uuid,p_ready_event_id uuid,p_source_id uuid,
          p_fetch_run_id uuid,p_raw_object_id uuid,p_capture_id uuid,
          p_canonical_url text,p_document_kind text,p_content_hash text,
          p_original_filename text,p_title text,p_acquired_at timestamptz
        ) RETURNS uuid
        LANGUAGE plpgsql SECURITY DEFINER
        SET search_path=pg_catalog,public AS $$
        DECLARE v_document_id uuid; v_raw_id uuid; v_hash text; v_existing uuid;
                v_version integer; v_allowed_hosts text[];
                v_captured_at timestamptz; v_detected_mime text;
                v_now timestamptz := statement_timestamp();
        BEGIN
          SELECT capture.raw_object_id,raw.sha256,config.allowed_hosts,
                 capture.captured_at,raw.detected_mime
            INTO v_raw_id,v_hash,v_allowed_hosts,v_captured_at,v_detected_mime
            FROM raw_object_capture capture
            JOIN raw_object raw ON raw.id=capture.raw_object_id
            JOIN fetch_run run ON run.id=capture.fetch_run_id
            JOIN source source_row ON source_row.id=capture.source_id
            JOIN source_policy_version policy
              ON policy.id=source_row.current_policy_version_id
            JOIN connector_config_version config
              ON config.id=source_row.current_connector_config_version_id
            JOIN fetch_schedule schedule ON schedule.id=run.schedule_id
            JOIN round17_pilot_window_source segment
              ON segment.id=run.pilot_window_source_id
            JOIN round17_pilot_window window_row ON window_row.id=segment.window_id
            JOIN source_governance_decision decision
              ON decision.id=segment.production_decision_id
           WHERE capture.id=p_capture_id AND capture.source_id=p_source_id
             AND capture.fetch_run_id=p_fetch_run_id
             AND capture.raw_object_id=p_raw_object_id
             AND capture.execution_domain='PRODUCTION'
             AND run.run_origin='SCHEDULED' AND run.execution_domain='PRODUCTION'
             AND run.status='RUNNING' AND run.execution_lease_token IS NOT NULL
             AND run.execution_lease_until>v_now
             AND run.source_id=p_source_id
             AND run.policy_version_id=policy.id
             AND run.connector_config_version_id=config.id
             AND source_row.lifecycle_state='ACTIVE'
             AND policy.status='APPROVED'
             AND policy.valid_from<=v_now AND policy.valid_until>v_now
             AND policy.valid_from<=p_acquired_at AND policy.valid_until>p_acquired_at
             AND policy.document->>'storage_policy'='RAW_EVIDENCE_ALLOWED'
             AND config.validation_status='VALID' AND schedule.status='ACTIVE'
             AND schedule.version=segment.schedule_version
             AND schedule.interval_seconds=segment.interval_seconds
             AND schedule.freshness_slo_seconds=segment.freshness_slo_seconds
             AND segment.source_id=source_row.id AND segment.status='RUNNING'
             AND segment.policy_version_id=policy.id
             AND segment.connector_config_version_id=config.id
             AND segment.schedule_id=schedule.id
             AND segment.trial_run_id=source_row.current_trial_run_id
             AND window_row.state='RUNNING'
             AND v_now>=segment.segment_started_at
             AND v_now<segment.segment_ends_at
             AND v_now>=window_row.started_at AND v_now<window_row.ends_at
             AND p_acquired_at<=v_now
             AND capture.captured_at>=segment.segment_started_at
             AND capture.captured_at<segment.segment_ends_at
             AND decision.source_id=source_row.id
             AND decision.policy_version_id=policy.id
             AND decision.connector_config_version_id=config.id
             AND decision.trial_run_id=source_row.current_trial_run_id
             AND decision.decision_type='PRODUCTION_APPROVAL'
             AND decision.outcome='APPROVED'
             AND (decision.valid_until IS NULL OR decision.valid_until>v_now)
             AND (decision.valid_until IS NULL OR decision.valid_until>p_acquired_at)
             AND EXISTS (
               SELECT 1 FROM raw_object_security_fact fact
                WHERE fact.raw_object_id=raw.id AND fact.status='CLEAN'
             )
             AND NOT EXISTS (
               SELECT 1 FROM raw_object_security_fact fact
                WHERE fact.raw_object_id=raw.id AND fact.status IN ('REJECTED','QUARANTINED')
             )
           FOR UPDATE OF run,source_row,segment,window_row,schedule,decision;
          IF NOT FOUND
             OR p_content_hash IS DISTINCT FROM v_hash
             OR p_content_hash !~ '^[0-9a-f]{64}$'
             OR p_document_kind NOT IN ('HTML','PDF','DISCOVERY_XML','DISCOVERY_JSON')
             OR length(p_original_filename) NOT BETWEEN 1 AND 255
             OR length(p_title) NOT BETWEEN 1 AND 500
             OR p_acquired_at<v_captured_at
             OR source_v2_safe_http_url(p_canonical_url,v_allowed_hosts) IS DISTINCT FROM true
             OR (p_document_kind='HTML' AND v_detected_mime<>'text/html')
             OR (p_document_kind='PDF' AND v_detected_mime<>'application/pdf')
             OR (p_document_kind='DISCOVERY_XML'
                 AND v_detected_mime<>'application/xml')
             OR (p_document_kind='DISCOVERY_JSON'
                 AND v_detected_mime<>'application/json') THEN
            RAISE EXCEPTION 'scheduled source document is not authorized';
          END IF;
          INSERT INTO document(
            id,source_id,canonical_url,document_kind,first_discovered_at,
            current_version_id,admission_fixture
          ) VALUES (
            p_document_id,p_source_id,p_canonical_url,p_document_kind,p_acquired_at,NULL,false
          ) ON CONFLICT (source_id,canonical_url) DO NOTHING;
          SELECT id INTO v_document_id FROM document
           WHERE source_id=p_source_id AND canonical_url=p_canonical_url FOR UPDATE;
          SELECT id INTO v_existing FROM document_version
           WHERE document_id=v_document_id AND content_hash=v_hash;
          IF v_existing IS NOT NULL THEN RETURN v_existing; END IF;
          SELECT COALESCE(max(version_number),0)+1 INTO v_version
            FROM document_version WHERE document_id=v_document_id;
          INSERT INTO document_version(
            id,document_id,raw_object_id,version_number,content_hash,
            original_filename,title,acquired_at,execution_domain,raw_object_capture_id
          ) VALUES (
            p_version_id,v_document_id,v_raw_id,v_version,v_hash,
            p_original_filename,p_title,p_acquired_at,'PRODUCTION',p_capture_id
          );
          INSERT INTO document_version_state_event(
            id,document_version_id,state,reason_code,actor_type,created_at
          ) VALUES
            (p_received_event_id,p_version_id,'RECEIVED','SCHEDULED_CAPTURE','WORKER',p_acquired_at),
            (p_security_event_id,p_version_id,'SECURITY_PASSED','RAW_SECURITY_CLEAN','WORKER',p_acquired_at),
            (p_ready_event_id,p_version_id,'READY','DETERMINISTIC_PARSE_READY','WORKER',p_acquired_at);
          UPDATE document SET current_version_id=p_version_id WHERE id=v_document_id;
          RETURN p_version_id;
        END $$
        """
    )
    document_signature = (
        "record_scheduled_source_document(uuid,uuid,uuid,uuid,uuid,uuid,uuid,uuid,uuid,"
        "text,text,text,text,text,timestamptz)"
    )
    op.execute(f"REVOKE ALL ON FUNCTION {document_signature} FROM PUBLIC")
    op.execute(f"GRANT EXECUTE ON FUNCTION {document_signature} TO srbg_worker_role")


def _configure_roles() -> None:
    tables = (
        "round17_staff_binding,round17_eventization_readiness,"
        "round17_pilot_window,round17_pilot_window_source,"
        "round17_gold_task,round17_gold_assignment,round17_gold_annotation,"
        "round17_gold_arbitration,round17_gold_release,round17_operator_task,"
        "round17_operator_work_session,round17_operator_work_correction,"
        "round17_metric_snapshot"
    )
    op.execute(f"REVOKE ALL ON {tables} FROM PUBLIC")
    op.execute(f"REVOKE ALL ON {tables} FROM srbg_projection_reader")
    op.execute(f"GRANT SELECT ON {tables} TO srbg_api_role")
    op.execute(
        "GRANT INSERT ON round17_pilot_window,round17_pilot_window_source,"
        "round17_gold_task,round17_gold_assignment,"
        "round17_gold_annotation,round17_gold_arbitration,round17_gold_release,"
        "round17_operator_task,round17_operator_work_correction,"
        "round17_metric_snapshot TO srbg_api_role"
    )
    op.execute(
        "GRANT UPDATE (state,version,blocker_codes,started_by,started_at,ends_at) "
        "ON round17_pilot_window TO srbg_api_role"
    )
    op.execute(
        "GRANT UPDATE (status,segment_started_at,segment_ends_at,paused_at,pause_reason) "
        "ON round17_pilot_window_source TO srbg_api_role"
    )
    op.execute("GRANT UPDATE (status) ON round17_gold_task TO srbg_api_role")
    op.execute(
        "GRANT UPDATE (last_activity_at,stopped_at,accrued_seconds,active_seconds,"
        "corrected,version) "
        "ON round17_operator_work_session TO srbg_api_role"
    )
    for signature in (
        "start_round17_operator_task(uuid,uuid,uuid,timestamptz)",
        "complete_round17_operator_task(uuid,integer,uuid,timestamptz)",
    ):
        op.execute(f"REVOKE ALL ON FUNCTION {signature} FROM PUBLIC")
        op.execute(f"GRANT EXECUTE ON FUNCTION {signature} TO srbg_api_role")
    op.execute(
        "GRANT SELECT ON round17_pilot_window,round17_pilot_window_source TO srbg_worker_role"
    )
    for signature in (
        "protect_round17_source_segment_pins()",
        "validate_round17_operator_task()",
        "validate_round17_work_session()",
        "validate_round17_work_correction()",
        "pause_round17_segments_on_source_change()",
        "pause_round17_segments_on_schedule_change()",
        "pause_round17_segments_on_anomaly()",
    ):
        op.execute(f"REVOKE ALL ON FUNCTION {signature} FROM PUBLIC")


def downgrade() -> None:
    connection = op.get_bind()
    count = connection.execute(
        sa.text(
            """SELECT
              (SELECT count(*) FROM round17_staff_binding)+
              (SELECT count(*) FROM round17_eventization_readiness)+
              (SELECT count(*) FROM round17_pilot_window)+
              (SELECT count(*) FROM round17_gold_task)+
              (SELECT count(*) FROM round17_operator_task)+
              (SELECT count(*) FROM round17_operator_work_session)+
              (SELECT count(*) FROM round17_metric_snapshot)+
              (SELECT count(*) FROM fetch_run
                WHERE run_origin<>'SCHEDULED' OR replayed_from_run_id IS NOT NULL
                   OR request_count<>0 OR response_bytes<>0)+
              (SELECT count(*) FROM source_health_snapshot
                WHERE discovery_body_bytes IS NOT NULL
                   OR structure_fingerprint_sha256 IS NOT NULL)"""
        )
    ).scalar_one()
    if count:
        raise RuntimeError("0017B_DOWNGRADE_BLOCKED: Round 17 evidence exists")

    for signature in (
        "complete_round17_operator_task(uuid,integer,uuid,timestamptz)",
        "start_round17_operator_task(uuid,uuid,uuid,timestamptz)",
        "record_scheduled_source_document(uuid,uuid,uuid,uuid,uuid,uuid,uuid,uuid,uuid,text,text,text,text,text,timestamptz)",
        "record_scheduled_source_raw(uuid,uuid,uuid,uuid,text,text,text,text,bigint,text,text,text,text,text,text,jsonb,integer,text,text,timestamptz)",
    ):
        op.execute(f"DROP FUNCTION IF EXISTS {signature}")
    op.execute("DROP TRIGGER IF EXISTS trg_round17_source_anomaly ON source_anomaly")
    op.execute("DROP TRIGGER IF EXISTS trg_round17_schedule_change ON fetch_schedule")
    op.execute("DROP TRIGGER IF EXISTS trg_round17_source_authority_change ON source")
    for signature in (
        "pause_round17_segments_on_anomaly()",
        "pause_round17_segments_on_schedule_change()",
        "pause_round17_segments_on_source_change()",
    ):
        op.execute(f"DROP FUNCTION IF EXISTS {signature}")
    op.execute("DROP TRIGGER IF EXISTS trg_fetch_run_bind_round17 ON fetch_run")
    op.execute("DROP FUNCTION IF EXISTS bind_round17_fetch_run()")
    op.execute("DROP TRIGGER IF EXISTS trg_fetch_run_origin_immutable ON fetch_run")
    op.execute("DROP FUNCTION IF EXISTS protect_fetch_run_origin()")
    op.execute("DROP TRIGGER IF EXISTS trg_round17_window_pins ON round17_pilot_window")
    op.execute("DROP FUNCTION IF EXISTS protect_round17_window_pins()")
    op.execute(
        "DROP TRIGGER IF EXISTS trg_round17_source_segment_pins ON round17_pilot_window_source"
    )
    op.execute("DROP FUNCTION IF EXISTS protect_round17_source_segment_pins()")
    op.execute(
        "DROP TRIGGER IF EXISTS trg_round17_work_correction_guard "
        "ON round17_operator_work_correction"
    )
    op.execute("DROP FUNCTION IF EXISTS validate_round17_work_correction()")
    op.execute(
        "DROP TRIGGER IF EXISTS trg_round17_work_session_guard "
        "ON round17_operator_work_session"
    )
    op.execute("DROP FUNCTION IF EXISTS validate_round17_work_session()")
    op.execute(
        "DROP TRIGGER IF EXISTS trg_round17_operator_task_guard "
        "ON round17_operator_task"
    )
    op.execute("DROP FUNCTION IF EXISTS validate_round17_operator_task()")
    for table in (
        "round17_staff_binding",
        "round17_eventization_readiness",
        "round17_gold_assignment",
        "round17_gold_annotation",
        "round17_gold_arbitration",
        "round17_gold_release",
        "round17_operator_work_correction",
        "round17_metric_snapshot",
    ):
        op.execute(f"DROP TRIGGER IF EXISTS trg_{table}_immutable ON {table}")
    for table in (
        "round17_metric_snapshot",
        "round17_operator_work_correction",
        "round17_operator_work_session",
        "round17_operator_task",
        "round17_gold_release",
        "round17_gold_arbitration",
        "round17_gold_annotation",
        "round17_gold_assignment",
        "round17_gold_task",
    ):
        op.drop_table(table)
    op.drop_constraint("fk_fetch_run_round17_window_source", "fetch_run", type_="foreignkey")
    op.drop_column("fetch_run", "pilot_window_source_id")
    op.drop_table("round17_pilot_window_source")
    op.drop_table("round17_pilot_window")
    op.drop_table("round17_eventization_readiness")
    op.drop_table("round17_staff_binding")
    op.drop_constraint(
        "ck_round17_health_structure_hash", "source_health_snapshot", type_="check"
    )
    op.drop_constraint(
        "ck_round17_health_body_bytes", "source_health_snapshot", type_="check"
    )
    op.drop_column("source_health_snapshot", "structure_fingerprint_sha256")
    op.drop_column("source_health_snapshot", "discovery_body_bytes")
    op.drop_index("ix_fetch_run_origin_started", table_name="fetch_run")
    op.drop_constraint("ck_fetch_run_response_bytes", "fetch_run", type_="check")
    op.drop_constraint("ck_fetch_run_request_count", "fetch_run", type_="check")
    op.drop_constraint("ck_fetch_run_origin", "fetch_run", type_="check")
    op.drop_constraint("fk_fetch_run_replayed_from", "fetch_run", type_="foreignkey")
    op.drop_column("fetch_run", "replayed_from_run_id")
    op.drop_column("fetch_run", "response_bytes")
    op.drop_column("fetch_run", "request_count")
    op.drop_column("fetch_run", "run_origin")
