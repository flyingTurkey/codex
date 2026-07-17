"""Automated source discovery, isolated qualification and one-click activation.

Revision ID: 0018_source_automation
Revises: 0017c_round17_flat_pilot
"""

# SQL governance functions are intentionally explicit for audit review.
# ruff: noqa: E501

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0018_source_automation"
down_revision: str | Sequence[str] | None = "0017c_round17_flat_pilot"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SOURCE_AUTOMATION_TABLES = (
    "source_candidate",
    "source_candidate_occurrence",
    "source_qualification_run",
    "source_qualification_capture",
    "source_qualification_bundle",
    "source_candidate_decision",
    "source_stream",
    "source_activation_outbox",
    "source_provider_budget_policy",
    "source_provider_usage",
)

WORKER_COMMAND_SIGNATURES = (
    "list_pending_source_qualification_ids(timestamptz,integer)",
    "acquire_source_qualification(uuid,uuid,timestamptz,timestamptz)",
    "record_source_qualification_capture(uuid,uuid,uuid,uuid,text,text,text,text,text,text,bigint,integer,text,timestamptz)",
    "complete_source_qualification(uuid,uuid,uuid,uuid,text,text,text,text,text,text,jsonb,text[],integer,integer,timestamptz,timestamptz)",
    "fail_source_qualification(uuid,uuid,uuid,text,timestamptz)",
    "request_automated_source_qualification(uuid,uuid,text,uuid,text,text,uuid,timestamptz)",
    "list_pending_source_activation_ids(timestamptz,integer)",
    "prepare_source_activation(uuid,uuid,timestamptz,timestamptz)",
    "complete_source_activation(uuid,uuid,uuid,timestamptz)",
    "reserve_source_provider_usage(text,text,timestamptz)",
)

_JSON = postgresql.JSONB(astext_type=sa.Text())
_TEXT_ARRAY = postgresql.ARRAY(sa.Text())


def _uuid() -> postgresql.UUID:
    return postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    _create_candidate_tables()
    _create_qualification_tables()
    _create_stream_and_decision_tables()
    _wire_candidate_bundle_reference()
    _backfill_default_streams()
    _create_fact_immutability_guards()
    _create_policy_authority_projection()
    _repair_scheduled_runtime_authority()
    _create_candidate_commands()
    _create_worker_command_boundary()
    _configure_roles()


def _create_candidate_tables() -> None:
    op.create_table(
        "source_candidate",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("institution_name", sa.String(200), nullable=False),
        sa.Column("canonical_url", sa.String(2048), nullable=False),
        sa.Column("canonical_url_sha256", sa.String(64), nullable=False, unique=True),
        sa.Column("authorization_boundary", sa.String(253), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="DISCOVERED"),
        sa.Column("material_fingerprint", sa.String(64), nullable=False),
        sa.Column("current_bundle_id", _uuid()),
        sa.Column(
            "source_id", _uuid(), sa.ForeignKey("source.id", ondelete="RESTRICT"), unique=True
        ),
        sa.Column("proposed_channel", sa.String(10)),
        sa.Column("proposed_source_type", sa.String(40)),
        sa.Column("proposed_authority_level", sa.String(10)),
        sa.Column("priority", sa.String(2), nullable=False, server_default="P2"),
        sa.Column("poll_interval_minutes", sa.Integer(), nullable=False, server_default="1440"),
        sa.Column(
            "country_codes", _TEXT_ARRAY, nullable=False, server_default=sa.text("ARRAY[]::text[]")
        ),
        sa.Column(
            "region_codes", _TEXT_ARRAY, nullable=False, server_default=sa.text("ARRAY[]::text[]")
        ),
        sa.Column(
            "language_tags", _TEXT_ARRAY, nullable=False, server_default=sa.text("ARRAY[]::text[]")
        ),
        sa.Column(
            "industries", _TEXT_ARRAY, nullable=False, server_default=sa.text("ARRAY[]::text[]")
        ),
        sa.Column(
            "content_domains",
            _TEXT_ARRAY,
            nullable=False,
            server_default=sa.text("ARRAY[]::text[]"),
        ),
        sa.Column(
            "declared_roles", _TEXT_ARRAY, nullable=False, server_default=sa.text("ARRAY[]::text[]")
        ),
        sa.Column("occurrence_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("first_discovered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_discovered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('DISCOVERED','QUALIFYING','READY_FOR_DECISION','ENABLED','DISMISSED','BLOCKED','STALE')",
            name="ck_source_candidate_status",
        ),
        sa.CheckConstraint(
            "canonical_url_sha256 ~ '^[0-9a-f]{64}$'", name="ck_source_candidate_url_hash"
        ),
        sa.CheckConstraint(
            "material_fingerprint ~ '^[0-9a-f]{64}$'", name="ck_source_candidate_material_hash"
        ),
        sa.CheckConstraint(
            "canonical_url ~ '^https://[^[:space:]@]+$'", name="ck_source_candidate_https"
        ),
        sa.CheckConstraint(
            "authorization_boundary !~ '[:/@*]'", name="ck_source_candidate_boundary"
        ),
        sa.CheckConstraint("occurrence_count > 0", name="ck_source_candidate_occurrences"),
        sa.CheckConstraint(
            "poll_interval_minutes BETWEEN 1 AND 10080", name="ck_source_candidate_poll"
        ),
    )
    op.create_index(
        "ix_source_candidate_queue",
        "source_candidate",
        ["status", "last_discovered_at", "id"],
    )
    op.create_table(
        "source_candidate_occurrence",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column(
            "candidate_id",
            _uuid(),
            sa.ForeignKey("source_candidate.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("discovery_channel", sa.String(30), nullable=False),
        sa.Column("target_evidence_ref", sa.String(255), nullable=False),
        sa.Column("campaign_id", _uuid()),
        sa.Column("discovered_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "discovery_channel IN ('DIRECTORY','RSS','SITEMAP','OUTBOUND_LINK','MANUAL','BAIDU_SEARCH')",
            name="ck_candidate_occurrence_channel",
        ),
        sa.CheckConstraint(
            "target_evidence_ref ~ '^(qualification-artifact|target-fetch|manual-submission):[A-Za-z0-9._:/-]{1,220}$'",
            name="ck_candidate_occurrence_evidence",
        ),
    )
    op.create_index(
        "ix_candidate_occurrence_candidate_time",
        "source_candidate_occurrence",
        ["candidate_id", "discovered_at"],
    )


def _create_qualification_tables() -> None:
    op.create_table(
        "source_qualification_run",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column(
            "candidate_id",
            _uuid(),
            sa.ForeignKey("source_candidate.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column(
            "execution_domain", sa.String(20), nullable=False, server_default="QUALIFICATION"
        ),
        sa.Column("rule_version", sa.String(80), nullable=False),
        sa.Column("requested_by", _uuid(), nullable=False),
        sa.Column("qualification_mode", sa.String(30), nullable=False, server_default="INITIAL"),
        sa.Column(
            "renewal_of_policy_version_id",
            _uuid(),
            sa.ForeignKey("source_policy_version.id", ondelete="RESTRICT"),
        ),
        sa.Column("prepared_source_id", _uuid(), sa.ForeignKey("source.id", ondelete="RESTRICT")),
        sa.Column(
            "prepared_policy_version_id",
            _uuid(),
            sa.ForeignKey("source_policy_version.id", ondelete="RESTRICT"),
        ),
        sa.Column(
            "prepared_connector_config_version_id",
            _uuid(),
            sa.ForeignKey("connector_config_version.id", ondelete="RESTRICT"),
        ),
        sa.Column(
            "prepared_trial_run_id",
            _uuid(),
            sa.ForeignKey("source_trial_run.id", ondelete="RESTRICT"),
        ),
        sa.Column("lease_token", _uuid()),
        sa.Column("leased_until", sa.DateTime(timezone=True)),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("failure_reason_code", sa.String(100)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('PENDING','RUNNING','SUCCEEDED','FAILED','CANCELLED')",
            name="ck_source_qualification_run_status",
        ),
        sa.CheckConstraint(
            "execution_domain IN ('QUALIFICATION')",
            name="ck_source_qualification_execution_domain",
        ),
        sa.CheckConstraint(
            "qualification_mode IN ('INITIAL','SHADOW_RENEWAL')",
            name="ck_source_qualification_mode",
        ),
        sa.CheckConstraint(
            "(qualification_mode='INITIAL' AND renewal_of_policy_version_id IS NULL) OR "
            "(qualification_mode='SHADOW_RENEWAL' AND renewal_of_policy_version_id IS NOT NULL)",
            name="ck_source_qualification_renewal_policy",
        ),
        sa.CheckConstraint(
            "prepared_source_id IS NOT NULL AND prepared_policy_version_id IS NOT NULL "
            "AND prepared_connector_config_version_id IS NOT NULL "
            "AND prepared_trial_run_id IS NOT NULL",
            name="ck_source_qualification_prepared_ids",
        ),
        sa.CheckConstraint(
            "(status='PENDING' AND started_at IS NULL AND completed_at IS NULL) OR "
            "(status='RUNNING' AND started_at IS NOT NULL AND completed_at IS NULL) OR "
            "(status IN ('SUCCEEDED','FAILED','CANCELLED') AND started_at IS NOT NULL AND completed_at IS NOT NULL)",
            name="ck_source_qualification_run_times",
        ),
        sa.CheckConstraint(
            "(status='FAILED' AND failure_reason_code IS NOT NULL) OR "
            "(status<>'FAILED' AND failure_reason_code IS NULL)",
            name="ck_source_qualification_failure_reason_required",
        ),
        sa.CheckConstraint(
            "failure_reason_code IS NULL OR failure_reason_code IN ("
            "'TARGET_PROBE_DISABLED','TARGET_OUTSIDE_AUTHORIZATION_BOUNDARY',"
            "'TARGET_SSRF_REJECTED','TARGET_FETCH_FAILED','TARGET_EMPTY_RESPONSE',"
            "'TARGET_ROBOTS_UNAVAILABLE','TARGET_SECURITY_REJECTED',"
            "'QUALIFICATION_CAPTURE_NOT_AUTHORIZED','PRODUCTION_PREPARATION_MISSING',"
            "'QUALIFICATION_COMPLETION_NOT_AUTHORIZED','TARGET_REQUEST_URL_MISMATCH',"
            "'TARGET_ADDRESS_NOT_PUBLIC','TARGET_REDIRECT_BOUNDARY_INVALID',"
            "'TARGET_HTTP_STATUS_REJECTED','UNKNOWN')",
            name="ck_source_qualification_failure_reason_code",
        ),
    )
    op.create_index(
        "ix_source_qualification_run_dispatch",
        "source_qualification_run",
        ["status", "created_at", "id"],
    )
    op.create_table(
        "source_qualification_capture",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column(
            "run_id",
            _uuid(),
            sa.ForeignKey("source_qualification_run.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "candidate_id",
            _uuid(),
            sa.ForeignKey("source_candidate.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("purpose", sa.String(40), nullable=False),
        sa.Column("requested_url", sa.String(2048), nullable=False),
        sa.Column("final_url", sa.String(2048), nullable=False),
        sa.Column("object_key", sa.String(255), nullable=False, unique=True),
        sa.Column("content_sha256", sa.String(64), nullable=False),
        sa.Column("response_sha256", sa.String(64), nullable=False),
        sa.Column("byte_size", sa.BigInteger(), nullable=False),
        sa.Column("http_status", sa.Integer(), nullable=False),
        sa.Column("content_type", sa.String(100), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "run_id", "content_sha256", "purpose", name="uq_qualification_capture_run_hash"
        ),
        sa.CheckConstraint(
            "object_key LIKE 'qualification/sha256/%'",
            name="ck_qualification_capture_namespace",
        ),
        sa.CheckConstraint(
            "content_sha256 ~ '^[0-9a-f]{64}$'", name="ck_qualification_content_hash"
        ),
        sa.CheckConstraint(
            "response_sha256 ~ '^[0-9a-f]{64}$'", name="ck_qualification_response_hash"
        ),
        sa.CheckConstraint(
            "byte_size BETWEEN 0 AND 52428800", name="ck_qualification_capture_size"
        ),
        sa.CheckConstraint("http_status BETWEEN 100 AND 599", name="ck_qualification_http_status"),
    )
    op.create_table(
        "source_qualification_bundle",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column(
            "candidate_id",
            _uuid(),
            sa.ForeignKey("source_candidate.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "run_id",
            _uuid(),
            sa.ForeignKey("source_qualification_run.id", ondelete="RESTRICT"),
            nullable=False,
            unique=True,
        ),
        sa.Column("rule_version", sa.String(80), nullable=False),
        sa.Column("material_fingerprint", sa.String(64), nullable=False),
        sa.Column("verdict", sa.String(30), nullable=False),
        sa.Column("storage_policy", sa.String(30), nullable=False),
        sa.Column("evidence_capture_policy", sa.String(30), nullable=False),
        sa.Column("checks", _JSON, nullable=False),
        sa.Column("reason_codes", _TEXT_ARRAY, nullable=False),
        sa.Column("sampled_item_count", sa.Integer(), nullable=False),
        sa.Column("relevant_item_count", sa.Integer(), nullable=False),
        sa.Column("bundle_sha256", sa.String(64), nullable=False, unique=True),
        sa.Column("evaluated_by", _uuid(), nullable=False),
        sa.Column("prepared_source_id", _uuid(), sa.ForeignKey("source.id", ondelete="RESTRICT")),
        sa.Column(
            "prepared_policy_version_id",
            _uuid(),
            sa.ForeignKey("source_policy_version.id", ondelete="RESTRICT"),
        ),
        sa.Column(
            "prepared_connector_config_version_id",
            _uuid(),
            sa.ForeignKey("connector_config_version.id", ondelete="RESTRICT"),
        ),
        sa.Column(
            "prepared_trial_run_id",
            _uuid(),
            sa.ForeignKey("source_trial_run.id", ondelete="RESTRICT"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "verdict IN ('QUALIFIED','WARN_WAIVABLE','BLOCKED')",
            name="ck_source_qualification_verdict",
        ),
        sa.CheckConstraint(
            "storage_policy IN ('RAW_EVIDENCE_ALLOWED','METADATA_ONLY','LINK_ONLY')",
            name="ck_source_qualification_storage_policy",
        ),
        sa.CheckConstraint(
            "evidence_capture_policy IN ('PRIVATE_RAW_ALLOWED','TRANSIENT_METADATA_ONLY')",
            name="ck_source_qualification_capture_policy",
        ),
        sa.CheckConstraint(
            "material_fingerprint ~ '^[0-9a-f]{64}$'", name="ck_qualification_material_hash"
        ),
        sa.CheckConstraint("bundle_sha256 ~ '^[0-9a-f]{64}$'", name="ck_qualification_bundle_hash"),
        sa.CheckConstraint(
            "sampled_item_count >= 0 AND relevant_item_count >= 0 AND relevant_item_count <= sampled_item_count",
            name="ck_qualification_sample_counts",
        ),
        sa.CheckConstraint("valid_until > created_at", name="ck_qualification_validity"),
        sa.CheckConstraint(
            "verdict='BLOCKED' OR (prepared_source_id IS NOT NULL AND prepared_policy_version_id IS NOT NULL "
            "AND prepared_connector_config_version_id IS NOT NULL AND prepared_trial_run_id IS NOT NULL)",
            name="ck_qualification_prepared_activation",
        ),
    )


def _create_stream_and_decision_tables() -> None:
    op.create_table(
        "source_stream",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column(
            "source_id", _uuid(), sa.ForeignKey("source.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column(
            "candidate_id", _uuid(), sa.ForeignKey("source_candidate.id", ondelete="RESTRICT")
        ),
        sa.Column("stream_key", sa.String(100), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("canonical_url", sa.String(2048), nullable=False),
        sa.Column("authorization_boundary", sa.String(253), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("rule_version", sa.String(80), nullable=False),
        sa.Column(
            "connector_config_version_id",
            _uuid(),
            sa.ForeignKey("connector_config_version.id", ondelete="RESTRICT"),
        ),
        sa.Column("schedule_id", _uuid(), sa.ForeignKey("fetch_schedule.id", ondelete="RESTRICT")),
        sa.Column("automatically_managed", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("last_success_at", sa.DateTime(timezone=True)),
        sa.Column("last_visible_output_at", sa.DateTime(timezone=True)),
        sa.Column("paused_reason", sa.String(500)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("source_id", "stream_key", name="uq_source_stream_key"),
        sa.UniqueConstraint("source_id", "canonical_url", name="uq_source_stream_url"),
        sa.CheckConstraint(
            "status IN ('QUALIFIED','ACTIVE','PAUSED','REVOKED')",
            name="ck_source_stream_status",
        ),
        sa.CheckConstraint("authorization_boundary !~ '[:/@*]'", name="ck_source_stream_boundary"),
    )
    op.create_index("ix_source_stream_status", "source_stream", ["status", "updated_at", "id"])
    op.create_table(
        "source_candidate_decision",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column(
            "candidate_id",
            _uuid(),
            sa.ForeignKey("source_candidate.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "bundle_id",
            _uuid(),
            sa.ForeignKey("source_qualification_bundle.id", ondelete="RESTRICT"),
        ),
        sa.Column("decision", sa.String(20), nullable=False),
        sa.Column("outcome", sa.String(20), nullable=False),
        sa.Column("waiver_reason", sa.String(500)),
        sa.Column("reason", sa.String(500), nullable=False),
        sa.Column("actor_id", _uuid(), nullable=False),
        sa.Column("request_sha256", sa.String(64), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("source_id", _uuid(), sa.ForeignKey("source.id", ondelete="RESTRICT")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "actor_id", "idempotency_key", name="uq_candidate_decision_idempotency"
        ),
        sa.CheckConstraint("decision IN ('ENABLE','DISMISS')", name="ck_candidate_decision_value"),
        sa.CheckConstraint(
            "outcome IN ('APPLIED','REJECTED')", name="ck_candidate_decision_outcome"
        ),
        sa.CheckConstraint(
            "request_sha256 ~ '^[0-9a-f]{64}$'", name="ck_candidate_decision_request_hash"
        ),
        sa.CheckConstraint(
            "(decision='ENABLE' AND source_id IS NOT NULL) OR (decision='DISMISS' AND source_id IS NULL)",
            name="ck_candidate_decision_source",
        ),
        sa.CheckConstraint(
            "decision='DISMISS' OR bundle_id IS NOT NULL",
            name="ck_candidate_decision_enable_bundle",
        ),
    )
    op.create_table(
        "source_activation_outbox",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column(
            "candidate_decision_id",
            _uuid(),
            sa.ForeignKey("source_candidate_decision.id", ondelete="RESTRICT"),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "source_id", _uuid(), sa.ForeignKey("source.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column(
            "stream_id",
            _uuid(),
            sa.ForeignKey("source_stream.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("event_type", sa.String(40), nullable=False, server_default="PRODUCTION_REFETCH"),
        sa.Column("status", sa.String(20), nullable=False, server_default="PENDING"),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("leased_until", sa.DateTime(timezone=True)),
        sa.Column("processed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("event_type='PRODUCTION_REFETCH'", name="ck_source_activation_event"),
        sa.CheckConstraint(
            "status IN ('PENDING','PROCESSING','SUCCEEDED','FAILED')",
            name="ck_source_activation_status",
        ),
        sa.CheckConstraint("attempt_count BETWEEN 0 AND 10", name="ck_source_activation_attempts"),
    )
    op.create_index(
        "ix_source_activation_outbox_dispatch",
        "source_activation_outbox",
        ["status", "available_at", "id"],
    )
    op.create_table(
        "source_provider_budget_policy",
        sa.Column("provider", sa.String(40), primary_key=True),
        sa.Column("monthly_cap_micrormb", sa.BigInteger(), nullable=False),
        sa.Column("free_calls_per_month", sa.Integer(), nullable=False),
        sa.Column("cost_per_call_micrormb", sa.BigInteger(), nullable=False),
        sa.Column("alert_threshold_bps", sa.Integer(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "provider IN ('BAIDU_SEARCH')",
            name="ck_source_provider_budget_policy_provider",
        ),
        sa.CheckConstraint(
            "monthly_cap_micrormb > 0 AND free_calls_per_month >= 0 "
            "AND cost_per_call_micrormb > 0 "
            "AND cost_per_call_micrormb <= monthly_cap_micrormb "
            "AND alert_threshold_bps BETWEEN 1 AND 9999",
            name="ck_source_provider_budget_policy_values",
        ),
    )
    op.execute(
        """
        INSERT INTO source_provider_budget_policy(
          provider,monthly_cap_micrormb,free_calls_per_month,
          cost_per_call_micrormb,alert_threshold_bps,enabled,updated_at
        ) VALUES ('BAIDU_SEARCH',200000000,1500,36000,8000,true,now())
        """
    )
    op.create_table(
        "source_provider_usage",
        sa.Column(
            "provider",
            sa.String(40),
            sa.ForeignKey("source_provider_budget_policy.provider", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("utc_month", sa.String(7), nullable=False),
        sa.Column("request_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cost_micrormb", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("monthly_cap_micrormb", sa.BigInteger(), nullable=False),
        sa.Column("alerted_at", sa.DateTime(timezone=True)),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("provider", "utc_month", name="pk_source_provider_usage"),
        sa.CheckConstraint(
            "utc_month ~ '^[0-9]{4}-(0[1-9]|1[0-2])$'", name="ck_source_provider_month"
        ),
        sa.CheckConstraint(
            "request_count >= 0 AND cost_micrormb >= 0 AND monthly_cap_micrormb > 0 AND cost_micrormb <= monthly_cap_micrormb",
            name="ck_source_provider_budget",
        ),
    )


def _wire_candidate_bundle_reference() -> None:
    op.create_foreign_key(
        "fk_source_candidate_current_bundle",
        "source_candidate",
        "source_qualification_bundle",
        ["current_bundle_id"],
        ["id"],
        ondelete="RESTRICT",
    )


def _backfill_default_streams() -> None:
    op.execute(
        """
        INSERT INTO source_stream(
          id,source_id,candidate_id,stream_key,name,canonical_url,
          authorization_boundary,status,connector_config_version_id,schedule_id,
          rule_version,automatically_managed,created_at,updated_at
        )
        SELECT (
                 substring(md5('round18-default-stream:' || source_row.id::text),1,8) || '-' ||
                 substring(md5('round18-default-stream:' || source_row.id::text),9,4) || '-7' ||
                 substring(md5('round18-default-stream:' || source_row.id::text),14,3) || '-8' ||
                 substring(md5('round18-default-stream:' || source_row.id::text),18,3) || '-' ||
                 substring(md5('round18-default-stream:' || source_row.id::text),21,12)
               )::uuid,
               source_row.id,NULL,'DEFAULT',source_row.name,source_row.base_url,
               lower(regexp_replace(split_part(split_part(source_row.base_url,'://',2),'/',1),':[0-9]+$','')),
               'QUALIFIED',source_row.current_connector_config_version_id,schedule.id,
               'REQUALIFICATION_REQUIRED',true,source_row.created_at,
               GREATEST(source_row.updated_at,source_row.created_at)
          FROM source source_row
          LEFT JOIN fetch_schedule schedule ON schedule.source_id=source_row.id
        ON CONFLICT (source_id,stream_key) DO NOTHING
        """
    )


def _create_fact_immutability_guards() -> None:
    op.execute(
        """
        CREATE FUNCTION prevent_source_automation_fact_mutation() RETURNS trigger
        LANGUAGE plpgsql SET search_path=pg_catalog,public AS $$
        BEGIN
          RAISE EXCEPTION 'source automation facts are append-only';
        END $$
        """
    )
    for table in (
        "source_candidate_occurrence",
        "source_qualification_capture",
        "source_qualification_bundle",
        "source_candidate_decision",
    ):
        op.execute(
            f"CREATE TRIGGER trg_{table}_append_only BEFORE UPDATE OR DELETE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION prevent_source_automation_fact_mutation()"
        )


def _create_policy_authority_projection() -> None:
    op.execute(
        """
        CREATE FUNCTION source_policy_compliance_current(
          p_source_id uuid,p_policy_id uuid,p_evaluated_at timestamptz
        ) RETURNS boolean
        LANGUAGE sql STABLE SECURITY DEFINER
        SET search_path=pg_catalog,public AS $$
          SELECT EXISTS(
            SELECT 1
              FROM source_policy_version policy
              JOIN LATERAL (
                SELECT decision.outcome,decision.valid_until
                  FROM source_governance_decision decision
                 WHERE decision.source_id=policy.source_id
                   AND decision.policy_version_id=policy.id
                   AND decision.decision_type='COMPLIANCE'
                 ORDER BY decision.created_at DESC,decision.id DESC LIMIT 1
              ) current_decision ON current_decision.outcome='APPROVED'
             WHERE policy.id=p_policy_id AND policy.source_id=p_source_id
               AND NOT EXISTS (
                 SELECT 1 FROM source_candidate automated_candidate
                  WHERE automated_candidate.source_id=policy.source_id
               )
               AND policy.valid_from<=p_evaluated_at AND policy.valid_until>p_evaluated_at
               AND (current_decision.valid_until IS NULL OR current_decision.valid_until>p_evaluated_at)
          )
          OR EXISTS(
            SELECT 1
              FROM source_policy_version policy
              JOIN source_candidate candidate
                ON candidate.source_id=policy.source_id
               AND candidate.status='ENABLED'
              JOIN source_candidate_decision candidate_decision
                ON candidate_decision.candidate_id=candidate.id
               AND candidate_decision.bundle_id=candidate.current_bundle_id
               AND candidate_decision.source_id=policy.source_id
               AND candidate_decision.decision='ENABLE'
               AND candidate_decision.outcome='APPLIED'
              JOIN source_qualification_bundle bundle
                ON bundle.id=candidate_decision.bundle_id
               AND bundle.candidate_id=candidate.id
               AND bundle.verdict IN ('QUALIFIED','WARN_WAIVABLE')
              JOIN source_governance_decision production_approval
                ON production_approval.source_id=policy.source_id
               AND production_approval.policy_version_id=policy.id
               AND production_approval.decision_type='PRODUCTION_APPROVAL'
               AND production_approval.outcome='APPROVED'
               AND production_approval.decided_by=candidate_decision.actor_id
               AND production_approval.created_at=candidate_decision.created_at
             WHERE policy.id=p_policy_id AND policy.source_id=p_source_id
               AND policy.status='APPROVED'
               AND policy.valid_from<=p_evaluated_at AND policy.valid_until>p_evaluated_at
               AND policy.document->>'qualification_bundle_id'=bundle.id::text
               AND policy.document->>'qualification_bundle_sha256'=bundle.bundle_sha256
               AND policy.document->>'storage_policy'=bundle.storage_policy
               AND policy.document->>'evidence_capture_policy'=bundle.evidence_capture_policy
               AND candidate_decision.created_at>=bundle.created_at
               AND candidate_decision.created_at<bundle.valid_until
               AND (production_approval.valid_until IS NULL
                    OR production_approval.valid_until>p_evaluated_at)
          )
        $$
        """
    )
    signature = "source_policy_compliance_current(uuid,uuid,timestamptz)"
    op.execute(f"REVOKE ALL ON FUNCTION {signature} FROM PUBLIC")
    op.execute(
        f"GRANT EXECUTE ON FUNCTION {signature} TO srbg_api_role,srbg_worker_role,srbg_publication_writer"
    )
    op.execute(
        """
        CREATE FUNCTION enforce_source_automation_lifecycle_authority()
        RETURNS trigger
        LANGUAGE plpgsql SECURITY DEFINER
        SET search_path=pg_catalog,public AS $$
        DECLARE
          v_candidate_status text;
        BEGIN
          SELECT candidate.status INTO v_candidate_status
            FROM source_candidate candidate
           WHERE candidate.source_id=NEW.id;
          IF NOT FOUND THEN
            RETURN NEW;
          END IF;
          IF NEW.lifecycle_state='ACTIVE' THEN
            IF v_candidate_status<>'ENABLED'
               OR NEW.current_policy_version_id IS NULL
               OR source_policy_compliance_current(
                    NEW.id,NEW.current_policy_version_id,NEW.updated_at
                  ) IS DISTINCT FROM true THEN
              RAISE EXCEPTION 'automated source production authority is incomplete or stale';
            END IF;
            NEW.state:='ACTIVE';
            NEW.enabled:=true;
          ELSE
            NEW.state:='CANDIDATE';
            NEW.enabled:=false;
          END IF;
          RETURN NEW;
        END $$
        """
    )
    op.execute("REVOKE ALL ON FUNCTION enforce_source_automation_lifecycle_authority() FROM PUBLIC")
    op.execute(
        """
        CREATE TRIGGER trg_source_automation_lifecycle_authority
        BEFORE UPDATE OF lifecycle_state ON source
        FOR EACH ROW EXECUTE FUNCTION enforce_source_automation_lifecycle_authority()
        """
    )
    op.execute(
        """
        CREATE FUNCTION source_private_evidence_capture_allowed(p_policy_document jsonb)
        RETURNS boolean
        LANGUAGE sql IMMUTABLE SECURITY DEFINER
        SET search_path=pg_catalog,public AS $$
          SELECT CASE p_policy_document->>'evidence_capture_policy'
            WHEN 'PRIVATE_RAW_ALLOWED' THEN true
            WHEN 'TRANSIENT_METADATA_ONLY' THEN false
            ELSE p_policy_document->>'storage_policy'='RAW_EVIDENCE_ALLOWED'
          END
        $$
        """
    )
    capture_signature = "source_private_evidence_capture_allowed(jsonb)"
    op.execute(f"REVOKE ALL ON FUNCTION {capture_signature} FROM PUBLIC")
    op.execute(f"GRANT EXECUTE ON FUNCTION {capture_signature} TO srbg_worker_role,srbg_api_role")


def _repair_scheduled_runtime_authority() -> None:
    """Keep frozen pilot checks and add the missing governed non-pilot branch."""

    op.execute(
        """
        CREATE OR REPLACE FUNCTION claim_due_fetch_schedule(
          p_now timestamptz,p_lease_until timestamptz,p_token uuid
        ) RETURNS TABLE(schedule_id uuid,source_id uuid)
        LANGUAGE sql SECURITY DEFINER
        SET search_path=pg_catalog,public AS $$
          WITH due AS (
            SELECT schedule.id,schedule.source_id
              FROM fetch_schedule schedule
              JOIN source source_row ON source_row.id=schedule.source_id
              JOIN source_policy_version policy
                ON policy.id=source_row.current_policy_version_id
              JOIN connector_config_version config
                ON config.id=source_row.current_connector_config_version_id
             WHERE schedule.status='ACTIVE'
               AND source_row.lifecycle_state='ACTIVE'
               AND source_policy_compliance_current(source_row.id,policy.id,p_now)
               AND source_private_evidence_capture_allowed(policy.document)
               AND config.validation_status='VALID'
               AND schedule.next_run_at<=p_now
               AND schedule.requests_used<schedule.daily_request_budget
               AND schedule.bytes_used<schedule.daily_byte_budget
               AND (schedule.leased_until IS NULL OR schedule.leased_until<=p_now)
               AND (
                 schedule.circuit_state='CLOSED'
                 OR (schedule.circuit_state='OPEN' AND schedule.circuit_open_until<=p_now)
               )
               AND EXISTS (
                 SELECT 1 FROM source_governance_decision decision
                  WHERE decision.source_id=source_row.id
                    AND decision.policy_version_id=policy.id
                    AND decision.connector_config_version_id=config.id
                    AND decision.trial_run_id=source_row.current_trial_run_id
                    AND decision.decision_type='PRODUCTION_APPROVAL'
                    AND decision.outcome='APPROVED'
                    AND (decision.valid_until IS NULL OR decision.valid_until>p_now)
               )
             ORDER BY schedule.next_run_at,schedule.id
             LIMIT 1 FOR UPDATE SKIP LOCKED
          )
          UPDATE fetch_schedule schedule
             SET lease_token=p_token,leased_until=p_lease_until,
                 circuit_state=CASE WHEN schedule.circuit_state='OPEN'
                                    THEN 'HALF_OPEN' ELSE schedule.circuit_state END
            FROM due WHERE schedule.id=due.id
          RETURNING schedule.id,schedule.source_id
        $$
        """
    )
    op.execute(
        "REVOKE ALL ON FUNCTION claim_due_fetch_schedule(timestamptz,timestamptz,uuid) FROM PUBLIC"
    )
    op.execute(
        "GRANT EXECUTE ON FUNCTION claim_due_fetch_schedule(timestamptz,timestamptz,uuid) "
        "TO srbg_worker_role"
    )
    raw_args = (
        "uuid,uuid,uuid,uuid,text,text,text,text,bigint,text,text,text,text,text,text,"
        "jsonb,integer,text,text,timestamptz"
    )
    document_args = (
        "uuid,uuid,uuid,uuid,uuid,uuid,uuid,uuid,uuid,text,text,text,text,text,timestamptz"
    )
    op.execute(
        f"ALTER FUNCTION record_scheduled_source_raw({raw_args}) "
        "RENAME TO record_scheduled_source_raw_round17"
    )
    op.execute(
        f"ALTER FUNCTION record_scheduled_source_document({document_args}) "
        "RENAME TO record_scheduled_source_document_round17"
    )
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
          v_pilot_id uuid;v_allowed_hosts text[];v_raw_id uuid;
          v_requested_host text;v_final_host text;v_security_status text;
          v_now timestamptz:=statement_timestamp();
        BEGIN
          SELECT pilot_window_source_id INTO v_pilot_id FROM fetch_run
           WHERE id=p_fetch_run_id AND source_id=p_source_id;
          IF v_pilot_id IS NOT NULL THEN
            RETURN QUERY SELECT * FROM record_scheduled_source_raw_round17(
              p_raw_object_id,p_capture_id,p_source_id,p_fetch_run_id,
              p_content_sha256,p_response_sha256,p_object_key,p_storage_etag,
              p_byte_size,p_declared_mime,p_detected_mime,p_security_status,
              p_security_reason,p_requested_url,p_final_url,p_redirect_chain,
              p_http_status,p_etag,p_last_modified,p_captured_at
            );
            RETURN;
          END IF;
          SELECT config.allowed_hosts INTO v_allowed_hosts
            FROM fetch_run run
            JOIN source source_row ON source_row.id=run.source_id
            JOIN source_policy_version policy
              ON policy.id=source_row.current_policy_version_id
             AND policy.id=run.policy_version_id
            JOIN connector_config_version config
              ON config.id=source_row.current_connector_config_version_id
             AND config.id=run.connector_config_version_id
            JOIN fetch_schedule schedule ON schedule.id=run.schedule_id
           WHERE run.id=p_fetch_run_id AND run.source_id=p_source_id
             AND run.pilot_window_source_id IS NULL
             AND run.run_origin='SCHEDULED' AND run.trigger='SCHEDULED'
             AND run.execution_domain='PRODUCTION' AND run.status='RUNNING'
             AND run.execution_lease_token IS NOT NULL
             AND run.execution_lease_until>v_now
             AND run.execution_lease_until>=p_captured_at
             AND source_row.lifecycle_state='ACTIVE'
             AND source_policy_compliance_current(source_row.id,policy.id,v_now)
             AND source_policy_compliance_current(source_row.id,policy.id,p_captured_at)
             AND source_private_evidence_capture_allowed(policy.document)
             AND config.validation_status='VALID' AND schedule.status='ACTIVE'
             AND run.started_at<=p_captured_at AND p_captured_at<=v_now
             AND NOT EXISTS (
               SELECT 1 FROM round17_pilot_window_source cohort
               JOIN round17_pilot_window cohort_window ON cohort_window.id=cohort.window_id
                WHERE cohort.source_id=source_row.id AND cohort_window.state='RUNNING'
             )
             AND EXISTS (
               SELECT 1 FROM source_governance_decision decision
                WHERE decision.source_id=source_row.id
                  AND decision.policy_version_id=policy.id
                  AND decision.connector_config_version_id=config.id
                  AND decision.trial_run_id=source_row.current_trial_run_id
                  AND decision.decision_type='PRODUCTION_APPROVAL'
                  AND decision.outcome='APPROVED'
                  AND (decision.valid_until IS NULL OR decision.valid_until>v_now)
                  AND (decision.valid_until IS NULL OR decision.valid_until>p_captured_at)
             )
           FOR UPDATE OF run,source_row,schedule;
          v_requested_host:=lower(regexp_replace(
            split_part(split_part(p_requested_url,'://',2),'/',1),':[0-9]+$',''
          ));
          v_final_host:=lower(regexp_replace(
            split_part(split_part(p_final_url,'://',2),'/',1),':[0-9]+$',''
          ));
          IF NOT FOUND
             OR p_content_sha256 !~ '^[0-9a-f]{64}$'
             OR p_response_sha256 !~ '^[0-9a-f]{64}$'
             OR p_byte_size NOT BETWEEN 0 AND 52428800
             OR p_object_key<>'sha256/'||substring(p_content_sha256,1,2)||'/'||p_content_sha256
             OR length(p_storage_etag) NOT BETWEEN 1 AND 200
             OR length(p_declared_mime) NOT BETWEEN 1 AND 100
             OR length(p_detected_mime) NOT BETWEEN 1 AND 100
             OR p_security_status NOT IN ('CLEAN','REJECTED')
             OR (p_security_status='CLEAN' AND p_security_reason IS NOT NULL)
             OR (p_security_status='REJECTED' AND (
                  p_security_reason IS NULL OR p_security_reason !~ '^[A-Z0-9_:-]{1,100}$'))
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
                   OR lower(regexp_replace(
                        split_part(split_part(entry #>> '{}','://',2),'/',1),':[0-9]+$',''
                      ))<>v_requested_host
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
           WHERE sha256=p_content_sha256 AND object_key=p_object_key
             AND byte_size=p_byte_size AND detected_mime=p_detected_mime;
          IF v_raw_id IS NULL THEN
            RAISE EXCEPTION 'scheduled source raw object identity is inconsistent';
          END IF;
          INSERT INTO raw_object_security_fact(
            id,raw_object_id,status,detected_mime,rule_version,reason_code,created_at
          ) VALUES (
            p_raw_object_id,v_raw_id,p_security_status,p_detected_mime,
            'round18-runtime-security-v1.0.0',
            COALESCE(p_security_reason,'SCHEDULED_CAPTURE_CLEAN'),p_captured_at
          ) ON CONFLICT ON CONSTRAINT uq_raw_security_object_rule DO NOTHING;
          SELECT fact.status INTO v_security_status FROM raw_object_security_fact fact
           WHERE fact.raw_object_id=v_raw_id
           ORDER BY fact.created_at DESC,fact.id DESC LIMIT 1;
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
          raw_object_id:=v_raw_id;capture_id:=p_capture_id;RETURN NEXT;
        END $$
        """
    )
    op.execute(
        r"""
        CREATE FUNCTION record_scheduled_source_document(
          p_document_id uuid,p_version_id uuid,p_received_event_id uuid,
          p_security_event_id uuid,p_ready_event_id uuid,p_source_id uuid,
          p_fetch_run_id uuid,p_raw_object_id uuid,p_capture_id uuid,
          p_canonical_url text,p_document_kind text,p_content_hash text,
          p_original_filename text,p_title text,p_acquired_at timestamptz
        ) RETURNS uuid
        LANGUAGE plpgsql SECURITY DEFINER
        SET search_path=pg_catalog,public AS $$
        DECLARE
          v_pilot_id uuid;v_document_id uuid;v_raw_id uuid;v_hash text;v_existing uuid;
          v_version integer;v_allowed_hosts text[];v_captured_at timestamptz;
          v_detected_mime text;v_now timestamptz:=statement_timestamp();
        BEGIN
          SELECT pilot_window_source_id INTO v_pilot_id FROM fetch_run
           WHERE id=p_fetch_run_id AND source_id=p_source_id;
          IF v_pilot_id IS NOT NULL THEN
            RETURN record_scheduled_source_document_round17(
              p_document_id,p_version_id,p_received_event_id,p_security_event_id,
              p_ready_event_id,p_source_id,p_fetch_run_id,p_raw_object_id,p_capture_id,
              p_canonical_url,p_document_kind,p_content_hash,p_original_filename,
              p_title,p_acquired_at
            );
          END IF;
          SELECT capture.raw_object_id,raw.sha256,config.allowed_hosts,
                 capture.captured_at,raw.detected_mime
            INTO v_raw_id,v_hash,v_allowed_hosts,v_captured_at,v_detected_mime
            FROM raw_object_capture capture
            JOIN raw_object raw ON raw.id=capture.raw_object_id
            JOIN fetch_run run ON run.id=capture.fetch_run_id
            JOIN source source_row ON source_row.id=capture.source_id
            JOIN source_policy_version policy
              ON policy.id=source_row.current_policy_version_id
             AND policy.id=run.policy_version_id
            JOIN connector_config_version config
              ON config.id=source_row.current_connector_config_version_id
             AND config.id=run.connector_config_version_id
            JOIN fetch_schedule schedule ON schedule.id=run.schedule_id
           WHERE capture.id=p_capture_id AND capture.source_id=p_source_id
             AND capture.fetch_run_id=p_fetch_run_id
             AND capture.raw_object_id=p_raw_object_id
             AND capture.execution_domain='PRODUCTION'
             AND run.pilot_window_source_id IS NULL
             AND run.run_origin='SCHEDULED' AND run.execution_domain='PRODUCTION'
             AND run.status='RUNNING' AND run.execution_lease_token IS NOT NULL
             AND run.execution_lease_until>v_now AND run.source_id=p_source_id
             AND source_row.lifecycle_state='ACTIVE'
             AND source_policy_compliance_current(source_row.id,policy.id,v_now)
             AND source_policy_compliance_current(source_row.id,policy.id,p_acquired_at)
             AND source_private_evidence_capture_allowed(policy.document)
             AND config.validation_status='VALID' AND schedule.status='ACTIVE'
             AND p_acquired_at<=v_now
             AND NOT EXISTS (
               SELECT 1 FROM round17_pilot_window_source cohort
               JOIN round17_pilot_window cohort_window ON cohort_window.id=cohort.window_id
                WHERE cohort.source_id=source_row.id AND cohort_window.state='RUNNING'
             )
             AND EXISTS (
               SELECT 1 FROM source_governance_decision decision
                WHERE decision.source_id=source_row.id
                  AND decision.policy_version_id=policy.id
                  AND decision.connector_config_version_id=config.id
                  AND decision.trial_run_id=source_row.current_trial_run_id
                  AND decision.decision_type='PRODUCTION_APPROVAL'
                  AND decision.outcome='APPROVED'
                  AND (decision.valid_until IS NULL OR decision.valid_until>v_now)
                  AND (decision.valid_until IS NULL OR decision.valid_until>p_acquired_at)
             )
             AND EXISTS (
               SELECT 1 FROM raw_object_security_fact fact
                WHERE fact.raw_object_id=raw.id AND fact.status='CLEAN'
             )
             AND NOT EXISTS (
               SELECT 1 FROM raw_object_security_fact fact
                WHERE fact.raw_object_id=raw.id AND fact.status IN ('REJECTED','QUARANTINED')
             )
           FOR UPDATE OF run,source_row,schedule;
          IF NOT FOUND OR p_content_hash IS DISTINCT FROM v_hash
             OR p_content_hash !~ '^[0-9a-f]{64}$'
             OR p_document_kind NOT IN ('HTML','PDF','DISCOVERY_XML','DISCOVERY_JSON')
             OR length(p_original_filename) NOT BETWEEN 1 AND 255
             OR length(p_title) NOT BETWEEN 1 AND 500 OR p_acquired_at<v_captured_at
             OR source_v2_safe_http_url(p_canonical_url,v_allowed_hosts) IS DISTINCT FROM true
             OR (p_document_kind='HTML' AND v_detected_mime<>'text/html')
             OR (p_document_kind='PDF' AND v_detected_mime<>'application/pdf')
             OR (p_document_kind='DISCOVERY_XML' AND v_detected_mime<>'application/xml')
             OR (p_document_kind='DISCOVERY_JSON' AND v_detected_mime<>'application/json') THEN
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
          IF v_existing IS NOT NULL THEN RETURN v_existing;END IF;
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
    raw_signature = f"record_scheduled_source_raw({raw_args})"
    document_signature = f"record_scheduled_source_document({document_args})"
    for signature in (raw_signature, document_signature):
        op.execute(f"REVOKE ALL ON FUNCTION {signature} FROM PUBLIC")
        op.execute(f"GRANT EXECUTE ON FUNCTION {signature} TO srbg_worker_role")


def _create_candidate_commands() -> None:
    op.execute(
        r"""
        CREATE FUNCTION source_automation_derived_uuid(p_seed uuid,p_purpose text)
        RETURNS uuid
        LANGUAGE sql IMMUTABLE STRICT PARALLEL SAFE
        SET search_path=pg_catalog,public AS $$
          SELECT (
            substring(value,1,8) || '-' || substring(value,9,4) || '-7' ||
            substring(value,14,3) || '-8' || substring(value,18,3) || '-' ||
            substring(value,21,12)
          )::uuid
            FROM (SELECT md5(p_seed::text || ':' || p_purpose) AS value) digest_value
        $$
        """
    )
    derived_uuid_signature = "source_automation_derived_uuid(uuid,text)"
    op.execute(f"REVOKE ALL ON FUNCTION {derived_uuid_signature} FROM PUBLIC")
    op.execute(
        r"""
        CREATE FUNCTION prepare_source_candidate_for_qualification(
          p_candidate_id uuid,p_run_id uuid,p_actor_id uuid,
          p_requested_at timestamptz DEFAULT now()
        ) RETURNS TABLE(
          prepared_source_id uuid,prepared_policy_version_id uuid,
          prepared_connector_config_version_id uuid,prepared_trial_run_id uuid,
          prepared_schedule_id uuid
        )
        LANGUAGE plpgsql SECURITY DEFINER
        SET search_path=pg_catalog,public AS $$
        DECLARE
          v_candidate source_candidate%ROWTYPE;
          v_source_id uuid;
          v_policy_id uuid;
          v_config_id uuid;
          v_trial_id uuid;
          v_schedule_id uuid;
          v_connector_id uuid;
          v_connector_definition_id uuid;
          v_policy_version text;
          v_policy_document jsonb;
          v_config_document jsonb;
          v_interval_seconds integer;
          v_shadow_requalification boolean;
        BEGIN
          SELECT * INTO v_candidate FROM source_candidate
           WHERE id=p_candidate_id FOR UPDATE;
          IF NOT FOUND THEN
            RAISE EXCEPTION 'qualification candidate does not exist';
          END IF;
          v_shadow_requalification:=v_candidate.status='ENABLED';

          v_source_id:=COALESCE(
            v_candidate.source_id,
            source_automation_derived_uuid(v_candidate.id,'qualification-source')
          );
          v_policy_id:=source_automation_derived_uuid(p_run_id,'qualification-policy');
          v_config_id:=source_automation_derived_uuid(p_run_id,'qualification-config');
          v_trial_id:=source_automation_derived_uuid(p_run_id,'qualification-trial');
          v_schedule_id:=source_automation_derived_uuid(v_candidate.id,'production-schedule');
          v_connector_id:=source_automation_derived_uuid(v_candidate.id,'runtime-connector');
          v_policy_version:='qual-' || substring(replace(p_run_id::text,'-',''),1,32);
          v_interval_seconds:=v_candidate.poll_interval_minutes*60;
          v_config_document:=jsonb_build_object(
            'allowed_hosts',jsonb_build_array(v_candidate.authorization_boundary),
            'list_url',v_candidate.canonical_url,
            'item_selector','a','link_selector','a','title_selector','a',
            'published_selector','time#q' ||
              right(replace(p_run_id::text,'-',''),12)
          );
          v_policy_document:=jsonb_build_object(
            'schema_version','2.0.0','policy_version',v_policy_version,
            'valid_from',p_requested_at,'valid_until',p_requested_at+interval '30 days',
            'fetch',jsonb_build_object(
              'allowed_domains',jsonb_build_array(v_candidate.authorization_boundary),
              'minimum_interval_seconds',v_interval_seconds,
              'rate_limit_per_minute',1,'user_agent','SRBGSourceAdapter/1.0'
            ),
            'storage_policy','LINK_ONLY',
            'evidence_capture_policy','PRIVATE_RAW_ALLOWED',
            'qualification_evidence',jsonb_build_object(
              'isolation_namespace','qualification/sha256/',
              'purpose','qualification_only',
              'retention_days',30,
              'promotion_allowed',false
            ),
            'source_automation_prepared',true,
            'qualification_run_id',p_run_id,
            'shadow_requalification',v_shadow_requalification,
            'automatic_publication',false,
            'reason','isolated automated source qualification preparation'
          );

          SELECT definition.id INTO v_connector_definition_id
            FROM connector_definition definition
           WHERE definition.connector_type='LIST_DETAIL'
             AND definition.definition_version='1.0.0';
          IF v_connector_definition_id IS NULL THEN
            RAISE EXCEPTION 'LIST_DETAIL connector definition is unavailable';
          END IF;

          IF v_candidate.source_id IS NULL THEN
            INSERT INTO source(
              id,name,base_url,channel,source_type,authority_level,priority,
              collection_method,poll_interval_minutes,owner,state,enabled,
              lifecycle_state,trial_kind,registered_by,governance_owner_id,
              country_codes,region_codes,language_tags,industries,content_domains,
              declared_roles,created_at,updated_at
            ) VALUES (
              v_source_id,v_candidate.institution_name,v_candidate.canonical_url,
              COALESCE(v_candidate.proposed_channel,'BOTH'),
              COALESCE(v_candidate.proposed_source_type,'media'),'C2',
              v_candidate.priority,'automated_qualification',
              v_candidate.poll_interval_minutes,'source_automation','CANDIDATE',false,
              'CANDIDATE',NULL,p_actor_id,NULL,v_candidate.country_codes,
              v_candidate.region_codes,v_candidate.language_tags,v_candidate.industries,
              v_candidate.content_domains,v_candidate.declared_roles,
              p_requested_at,p_requested_at
            );
          ELSIF NOT EXISTS (
            SELECT 1 FROM source source_row
             WHERE source_row.id=v_source_id
               AND source_row.base_url=v_candidate.canonical_url
               AND (
                 source_row.lifecycle_state IN ('CANDIDATE','PAUSED')
                 OR (
                   v_shadow_requalification
                   AND source_row.lifecycle_state='ACTIVE'
                   AND source_policy_compliance_current(
                         source_row.id,source_row.current_policy_version_id,
                         p_requested_at
                       )
                 )
               )
          ) THEN
            RAISE EXCEPTION 'prepared source is no longer a dormant candidate';
          END IF;
          IF NOT v_shadow_requalification THEN
            UPDATE source
               SET country_codes=v_candidate.country_codes,
                   region_codes=v_candidate.region_codes,
                   language_tags=v_candidate.language_tags,
                   industries=v_candidate.industries,
                   content_domains=v_candidate.content_domains,
                   declared_roles=v_candidate.declared_roles,
                   updated_at=p_requested_at
             WHERE id=v_source_id
               AND lifecycle_state IN ('CANDIDATE','PAUSED');
          END IF;

          INSERT INTO source_policy_version(
            id,source_id,schema_version,policy_version,status,document,
            document_sha256,valid_from,valid_until,submitted_by,created_at
          ) VALUES (
            v_policy_id,v_source_id,'2.0.0',v_policy_version,'PENDING_REVIEW',
            v_policy_document,
            encode(digest(convert_to(v_policy_document::text,'UTF8'),'sha256'),'hex'),
            p_requested_at,p_requested_at+interval '30 days',p_actor_id,p_requested_at
          );
          INSERT INTO connector_config_version(
            id,source_id,connector_definition_id,policy_version_id,version_number,
            config_document,config_sha256,allowed_hosts,validation_status,
            validation_reason_codes,created_by,created_at
          ) VALUES (
            v_config_id,v_source_id,v_connector_definition_id,v_policy_id,
            COALESCE((SELECT max(config.version_number)+1
                        FROM connector_config_version config
                       WHERE config.source_id=v_source_id),1),
            v_config_document,
            encode(digest(convert_to(v_config_document::text,'UTF8'),'sha256'),'hex'),
            ARRAY[v_candidate.authorization_boundary],'VALID',ARRAY[]::text[],
            p_actor_id,p_requested_at
          );
          INSERT INTO source_trial_run(
            id,source_id,kind,execution_domain,policy_version_id,
            connector_config_version_id,authorization_decision_id,requested_by,
            request_reason,created_at
          ) VALUES (
            v_trial_id,v_source_id,'LIVE_TRIAL','TRIAL',v_policy_id,v_config_id,
            NULL,p_actor_id,'isolated automated source qualification',p_requested_at
          );
          IF NOT v_shadow_requalification THEN
            INSERT INTO source_connector(
              id,source_id,connector_type,config,enabled,created_at
            ) VALUES (
              v_connector_id,v_source_id,'LIST_DETAIL',v_config_document,false,p_requested_at
            ) ON CONFLICT (source_id) DO NOTHING;
            INSERT INTO fetch_schedule(
              id,source_id,authority_level,status,interval_seconds,next_run_at,
              freshness_slo_seconds,rate_limit_per_minute,daily_request_budget,
              daily_byte_budget,budget_window_started_at,updated_at
            ) VALUES (
              v_schedule_id,v_source_id,'C2','PAUSED',v_interval_seconds,
              p_requested_at+make_interval(secs=>v_interval_seconds),
              GREATEST(v_interval_seconds*2,3600),1,100,104857600,
              p_requested_at,p_requested_at
            ) ON CONFLICT (source_id) DO UPDATE SET
              interval_seconds=EXCLUDED.interval_seconds,
              freshness_slo_seconds=EXCLUDED.freshness_slo_seconds,
              rate_limit_per_minute=EXCLUDED.rate_limit_per_minute,
              status='PAUSED',lease_token=NULL,leased_until=NULL,
              updated_at=EXCLUDED.updated_at;
            UPDATE source SET
              current_policy_version_id=v_policy_id,
              current_connector_config_version_id=v_config_id,
              current_trial_run_id=v_trial_id,updated_at=p_requested_at
             WHERE id=v_source_id;
          END IF;
          UPDATE source_candidate SET source_id=v_source_id,updated_at=p_requested_at
           WHERE id=v_candidate.id;

          RETURN QUERY SELECT v_source_id,v_policy_id,v_config_id,v_trial_id,v_schedule_id;
        END $$
        """
    )
    prepare_signature = "prepare_source_candidate_for_qualification(uuid,uuid,uuid,timestamptz)"
    op.execute(f"REVOKE ALL ON FUNCTION {prepare_signature} FROM PUBLIC")
    op.execute(
        r"""
        CREATE FUNCTION register_discovered_source_candidate(
          p_candidate_id uuid,p_occurrence_id uuid,p_canonical_url text,
          p_canonical_url_sha256 text,p_authorization_boundary text,
          p_material_fingerprint text,p_discovery_channel text,p_target_evidence_ref text,
          p_industries text[],p_content_domains text[],p_language_tags text[],
          p_actor_id uuid,p_reason text,p_request_id text,p_audit_id uuid,
          p_discovered_at timestamptz DEFAULT now()
        ) RETURNS uuid
        LANGUAGE plpgsql SECURITY DEFINER
        SET search_path=pg_catalog,public AS $$
        DECLARE
          v_candidate_id uuid;
          v_evidence_candidate_id uuid;
          v_before_status text;
          v_after_status text;
          v_existing_evidence_hash text;
          v_existing_material_fingerprint text;
          v_governance_fingerprint text;
          v_existing_industries text[];
          v_existing_content_domains text[];
          v_existing_language_tags text[];
          v_source_id uuid;
          v_source_state text;
          v_policy_id uuid;
          v_material_changed boolean;
          v_requalification_required boolean;
          v_scope_changed boolean:=false;
          v_occurrence_exists boolean:=false;
        BEGIN
          IF substring(p_candidate_id::text,15,1)<>'7'
             OR substring(p_occurrence_id::text,15,1)<>'7'
             OR p_canonical_url_sha256 !~ '^[0-9a-f]{64}$'
             OR p_canonical_url_sha256<>
                encode(digest(convert_to(p_canonical_url,'UTF8'),'sha256'),'hex')
             OR p_material_fingerprint !~ '^[0-9a-f]{64}$'
             OR p_authorization_boundary !~ '^(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$'
             OR source_v2_safe_http_url(
                  p_canonical_url,ARRAY[p_authorization_boundary]
                ) IS DISTINCT FROM true
             OR p_discovery_channel NOT IN (
                  'DIRECTORY','RSS','SITEMAP','OUTBOUND_LINK','MANUAL','BAIDU_SEARCH'
                )
              OR p_target_evidence_ref !~
                   '^(qualification-artifact|target-fetch|manual-submission):[A-Za-z0-9._:/-]{1,220}$'
              OR p_industries IS NULL OR p_content_domains IS NULL
              OR p_language_tags IS NULL
              OR cardinality(p_industries)>30 OR cardinality(p_content_domains)>30
              OR cardinality(p_language_tags)>20
              OR EXISTS (
                   SELECT 1 FROM unnest(p_industries) value
                    WHERE value IS NULL OR value NOT IN (
                      'HIGHWAY','BRIDGE','TUNNEL','RAILWAY','RAIL_TRANSIT',
                      'WATER_CONSERVANCY','MUNICIPAL','BUILDING','ENERGY',
                      'PORT_WATERWAY','AIRPORT','GENERAL_TRANSPORT','UNKNOWN'
                    )
                 )
              OR EXISTS (
                   SELECT 1 FROM unnest(p_content_domains) value
                    WHERE value IS NULL OR value NOT IN (
                      'DIGITAL_TRANSFORMATION_CASE','RESEARCH_PAPER',
                      'SOFTWARE_PLATFORM','IOT_EQUIPMENT',
                      'LOW_ALTITUDE_EQUIPMENT','AI_APPLICATION',
                      'SAFETY_REGULATION','STANDARD_GUIDANCE',
                      'ACCIDENT_INVESTIGATION','OFFICIAL_NOTICE','PENALTY',
                      'RECTIFICATION','UNKNOWN'
                    )
                 )
              OR source_v2_safe_audit_reason(p_reason) IS DISTINCT FROM true THEN
            RAISE EXCEPTION 'source candidate discovery input is invalid';
          END IF;

          v_governance_fingerprint:=encode(digest(convert_to(
            p_canonical_url || chr(10) || p_authorization_boundary,'UTF8'
          ),'sha256'),'hex');

          PERFORM pg_advisory_xact_lock(
            hashtextextended(p_target_evidence_ref,1801)
          );
          SELECT candidate.id,candidate.canonical_url_sha256
            INTO v_evidence_candidate_id,v_existing_evidence_hash
            FROM source_candidate_occurrence occurrence
            JOIN source_candidate candidate ON candidate.id=occurrence.candidate_id
           WHERE occurrence.target_evidence_ref=p_target_evidence_ref
           ORDER BY occurrence.discovered_at,occurrence.id LIMIT 1
           FOR UPDATE OF candidate;
          IF v_evidence_candidate_id IS NOT NULL THEN
            IF v_existing_evidence_hash<>p_canonical_url_sha256 THEN
              RAISE EXCEPTION 'target evidence identity conflicts with its candidate';
            END IF;
            v_occurrence_exists:=true;
          END IF;
          PERFORM pg_advisory_xact_lock(
            hashtextextended(p_canonical_url_sha256,1802)
          );

          SELECT id,status,material_fingerprint,source_id,
                 industries,content_domains,language_tags
            INTO v_candidate_id,v_before_status,v_existing_material_fingerprint,v_source_id,
                 v_existing_industries,v_existing_content_domains,v_existing_language_tags
            FROM source_candidate
           WHERE canonical_url_sha256=p_canonical_url_sha256 FOR UPDATE;
          IF v_evidence_candidate_id IS NOT NULL
             AND v_evidence_candidate_id IS DISTINCT FROM v_candidate_id THEN
            RAISE EXCEPTION 'target evidence identity conflicts with its candidate';
          END IF;
          IF v_candidate_id IS NULL THEN
            v_candidate_id:=p_candidate_id;v_before_status:=NULL;v_after_status:='DISCOVERED';
            INSERT INTO source_candidate(
              id,institution_name,canonical_url,canonical_url_sha256,
              authorization_boundary,status,material_fingerprint,
              country_codes,region_codes,language_tags,industries,content_domains,
              declared_roles,occurrence_count,first_discovered_at,last_discovered_at,
              created_at,updated_at
            ) VALUES (
              v_candidate_id,p_authorization_boundary,p_canonical_url,
              p_canonical_url_sha256,p_authorization_boundary,'DISCOVERED',
              v_governance_fingerprint,ARRAY[]::text[],ARRAY[]::text[],p_language_tags,
              p_industries,p_content_domains,ARRAY[]::text[],1,p_discovered_at,
              p_discovered_at,p_discovered_at,p_discovered_at
            );
          ELSE
            v_scope_changed:=
              EXISTS (SELECT 1 FROM unnest(p_industries) value
                       WHERE NOT (value=ANY(v_existing_industries)))
              OR EXISTS (SELECT 1 FROM unnest(p_content_domains) value
                          WHERE NOT (value=ANY(v_existing_content_domains)))
              OR EXISTS (SELECT 1 FROM unnest(p_language_tags) value
                          WHERE NOT (value=ANY(v_existing_language_tags)));
            v_material_changed:=
              v_governance_fingerprint<>v_existing_material_fingerprint;
            v_requalification_required:=
              v_material_changed
              OR (v_scope_changed AND v_before_status<>'ENABLED');
            IF v_occurrence_exists AND NOT v_material_changed AND NOT v_scope_changed THEN
              RETURN v_candidate_id;
            END IF;
            v_after_status:=CASE
              WHEN v_before_status='DISMISSED' THEN 'DISMISSED'
              WHEN v_requalification_required THEN 'STALE'
              ELSE v_before_status END;
            IF v_requalification_required THEN
              UPDATE source_qualification_run
                 SET status='CANCELLED',started_at=COALESCE(started_at,p_discovered_at),
                     completed_at=p_discovered_at,lease_token=NULL,leased_until=NULL
               WHERE candidate_id=v_candidate_id AND status IN ('PENDING','RUNNING');
            END IF;
            IF v_before_status='ENABLED' AND v_material_changed AND v_source_id IS NOT NULL THEN
              SELECT lifecycle_state,current_policy_version_id
                INTO v_source_state,v_policy_id
                FROM source WHERE id=v_source_id FOR UPDATE;
              UPDATE source_stream SET status='PAUSED',
                paused_reason='SOURCE_MATERIAL_CHANGED',updated_at=p_discovered_at
               WHERE source_id=v_source_id AND status<>'REVOKED';
              UPDATE fetch_schedule SET status='PAUSED',lease_token=NULL,leased_until=NULL,
                updated_at=p_discovered_at WHERE source_id=v_source_id;
              UPDATE source_connector SET enabled=false WHERE source_id=v_source_id;
              IF v_source_state IS NOT NULL AND v_source_state<>'PAUSED' THEN
                UPDATE source SET lifecycle_state='PAUSED',trial_kind=NULL,
                  state='CANDIDATE',enabled=false,
                  updated_at=p_discovered_at WHERE id=v_source_id;
                INSERT INTO source_lifecycle_event(
                  id,source_id,from_state,to_state,action,reason_code,reason,
                  actor_id,policy_version_id,created_at
                ) VALUES (
                  source_automation_derived_uuid(p_audit_id,'material-change-event'),
                  v_source_id,v_source_state,'PAUSED','PAUSE','SOURCE_MATERIAL_CHANGED',
                  p_reason,p_actor_id,v_policy_id,p_discovered_at
                );
              END IF;
              PERFORM append_audit_event(
                source_automation_derived_uuid(p_audit_id,'material-change-audit'),
                'SOURCE_AUTOMATION_PAUSED',p_actor_id,'SOURCE',v_source_id,
                jsonb_build_object('lifecycle_state',v_source_state),
                jsonb_build_object(
                  'lifecycle_state','PAUSED','reason_code','SOURCE_MATERIAL_CHANGED'
                ),p_reason,p_request_id,p_discovered_at
              );
            END IF;
            IF v_before_status='ENABLED' AND v_scope_changed
               AND NOT v_material_changed AND v_source_id IS NOT NULL THEN
              UPDATE source
                 SET industries=(SELECT ARRAY(SELECT DISTINCT value FROM unnest(
                       source.industries||p_industries) value ORDER BY value)),
                     content_domains=(SELECT ARRAY(SELECT DISTINCT value FROM unnest(
                       source.content_domains||p_content_domains) value ORDER BY value)),
                     language_tags=(SELECT ARRAY(SELECT DISTINCT value FROM unnest(
                       source.language_tags||p_language_tags) value ORDER BY value)),
                     updated_at=p_discovered_at
               WHERE id=v_source_id;
            END IF;
            UPDATE source_candidate
               SET occurrence_count=occurrence_count+
                     CASE WHEN v_occurrence_exists THEN 0 ELSE 1 END,
                   last_discovered_at=GREATEST(last_discovered_at,p_discovered_at),
                   canonical_url=p_canonical_url,
                   authorization_boundary=p_authorization_boundary,
                   material_fingerprint=v_governance_fingerprint,
                   current_bundle_id=CASE WHEN v_requalification_required THEN NULL
                                          ELSE current_bundle_id END,
                   status=v_after_status,
                   industries=(SELECT ARRAY(SELECT DISTINCT value FROM unnest(
                     source_candidate.industries||p_industries) value ORDER BY value)),
                   content_domains=(SELECT ARRAY(SELECT DISTINCT value FROM unnest(
                     source_candidate.content_domains||p_content_domains) value ORDER BY value)),
                   language_tags=(SELECT ARRAY(SELECT DISTINCT value FROM unnest(
                     source_candidate.language_tags||p_language_tags) value ORDER BY value)),
                   updated_at=p_discovered_at
             WHERE id=v_candidate_id;
          END IF;
          IF NOT v_occurrence_exists THEN
            INSERT INTO source_candidate_occurrence(
              id,candidate_id,discovery_channel,target_evidence_ref,discovered_at
            ) VALUES (
              p_occurrence_id,v_candidate_id,p_discovery_channel,
              p_target_evidence_ref,p_discovered_at
            );
          END IF;
          PERFORM append_audit_event(
            p_audit_id,'SOURCE_CANDIDATE_DISCOVERED',p_actor_id,
            'SOURCE_CANDIDATE',v_candidate_id,
            CASE WHEN v_before_status IS NULL THEN NULL
                 ELSE jsonb_build_object('status',v_before_status) END,
            jsonb_build_object(
              'status',v_after_status,'discovery_channel',p_discovery_channel,
              'material_changed',COALESCE(v_material_changed,false),
              'qualification_scope_changed',v_scope_changed,
              'requalification_required',COALESCE(v_requalification_required,false)
            ),
            p_reason,p_request_id,p_discovered_at
          );
          RETURN v_candidate_id;
        END $$
        """
    )
    register_signature = (
        "register_discovered_source_candidate(uuid,uuid,text,text,text,text,text,text,"
        "text[],text[],text[],uuid,text,text,uuid,timestamptz)"
    )
    op.execute(f"REVOKE ALL ON FUNCTION {register_signature} FROM PUBLIC")
    op.execute(f"GRANT EXECUTE ON FUNCTION {register_signature} TO srbg_api_role,srbg_worker_role")
    op.execute(
        r"""
        CREATE FUNCTION request_source_qualification(
          p_run_id uuid,p_candidate_id uuid,p_rule_version text,p_actor_id uuid,
          p_reason text,p_request_id text,p_audit_id uuid,p_requested_at timestamptz DEFAULT now()
        ) RETURNS uuid
        LANGUAGE plpgsql SECURITY DEFINER
        SET search_path=pg_catalog,public AS $$
        DECLARE
          v_status text;
          v_prepared_source_id uuid;
          v_prepared_policy_version_id uuid;
          v_prepared_connector_config_version_id uuid;
          v_prepared_trial_run_id uuid;
          v_prepared_schedule_id uuid;
        BEGIN
          IF substring(p_run_id::text,15,1)<>'7'
             OR length(p_rule_version) NOT BETWEEN 1 AND 80
             OR p_rule_version !~ '^[A-Za-z0-9._-]+$'
             OR source_v2_safe_audit_reason(p_reason) IS DISTINCT FROM true THEN
            RAISE EXCEPTION 'qualification request is invalid';
          END IF;
          SELECT status INTO v_status FROM source_candidate
           WHERE id=p_candidate_id FOR UPDATE;
          IF NOT FOUND THEN
            RAISE EXCEPTION 'qualification candidate does not exist';
          END IF;
          IF v_status NOT IN ('DISCOVERED','STALE','BLOCKED') OR EXISTS(
               SELECT 1 FROM source_qualification_run run
                WHERE run.candidate_id=p_candidate_id
                  AND run.status IN ('PENDING','RUNNING')
             ) THEN
            RETURN NULL;
          END IF;
          SELECT prepared_source_id,prepared_policy_version_id,
                 prepared_connector_config_version_id,prepared_trial_run_id,
                 prepared_schedule_id
            INTO v_prepared_source_id,v_prepared_policy_version_id,
                 v_prepared_connector_config_version_id,v_prepared_trial_run_id,
                 v_prepared_schedule_id
            FROM prepare_source_candidate_for_qualification(
              p_candidate_id,p_run_id,p_actor_id,p_requested_at
            );
          INSERT INTO source_qualification_run(
            id,candidate_id,status,execution_domain,rule_version,requested_by,
            qualification_mode,prepared_source_id,prepared_policy_version_id,
            prepared_connector_config_version_id,prepared_trial_run_id,created_at
          ) VALUES (
            p_run_id,p_candidate_id,'PENDING','QUALIFICATION',p_rule_version,p_actor_id,
            'INITIAL',v_prepared_source_id,v_prepared_policy_version_id,
            v_prepared_connector_config_version_id,v_prepared_trial_run_id,p_requested_at
          );
          UPDATE source_candidate SET status='QUALIFYING',updated_at=p_requested_at
           WHERE id=p_candidate_id;
          PERFORM append_audit_event(
            p_audit_id,'SOURCE_QUALIFICATION_REQUESTED',p_actor_id,
            'SOURCE_CANDIDATE',p_candidate_id,jsonb_build_object('status',v_status),
            jsonb_build_object('status','QUALIFYING','run_id',p_run_id,'rule_version',p_rule_version),
            p_reason,p_request_id,p_requested_at
          );
          RETURN p_run_id;
        END $$
        """
    )
    qualification_signature = (
        "request_source_qualification(uuid,uuid,text,uuid,text,text,uuid,timestamptz)"
    )
    op.execute(f"REVOKE ALL ON FUNCTION {qualification_signature} FROM PUBLIC")
    op.execute(f"GRANT EXECUTE ON FUNCTION {qualification_signature} TO srbg_api_role")
    op.execute(
        r"""
        CREATE FUNCTION request_automated_source_qualification(
          p_run_id uuid,p_candidate_id uuid,p_rule_version text,p_actor_id uuid,
          p_reason text,p_request_id text,p_audit_id uuid,
          p_requested_at timestamptz DEFAULT now()
        ) RETURNS uuid
        LANGUAGE plpgsql SECURITY DEFINER
        SET search_path=pg_catalog,public AS $$
        DECLARE v_status text;
        BEGIN
          SELECT status INTO v_status
            FROM source_candidate
           WHERE id=p_candidate_id FOR UPDATE;
          IF NOT FOUND THEN
            RAISE EXCEPTION 'qualification candidate does not exist';
          END IF;
          IF v_status NOT IN ('DISCOVERED','STALE') THEN
            RETURN NULL;
          END IF;
          RETURN request_source_qualification(
            p_run_id,p_candidate_id,p_rule_version,p_actor_id,p_reason,
            p_request_id,p_audit_id,p_requested_at
          );
        END $$
        """
    )
    op.execute(
        r"""
        CREATE FUNCTION activate_qualified_candidate(
          p_candidate_id uuid,p_decision text,p_expected_bundle_sha256 text,
          p_request_sha256 text,p_idempotency_key text,p_reason text,p_waiver_reason text,
          p_actor_id uuid,p_candidate_decision_id uuid,p_governance_decision_id uuid,
          p_lifecycle_event_id uuid,p_stream_id uuid,p_outbox_id uuid,
          p_source_audit_id uuid,p_candidate_audit_id uuid,p_decided_at timestamptz DEFAULT now()
        ) RETURNS TABLE(decision_id uuid,source_id uuid,outbox_id uuid,candidate_status text)
        LANGUAGE plpgsql SECURITY DEFINER
        SET search_path=pg_catalog,public AS $$
        DECLARE
          v_existing source_candidate_decision%ROWTYPE;
          v_candidate source_candidate%ROWTYPE;
          v_bundle source_qualification_bundle%ROWTYPE;
          v_source_id uuid;
          v_source_state text;
          v_submitted_by uuid;
          v_valid_until timestamptz;
          v_stream_id uuid;
          v_schedule_id uuid;
          v_connector_definition_id uuid;
          v_policy_id uuid;
          v_config_id uuid;
          v_trial_id uuid;
          v_policy_version text;
          v_policy_document jsonb;
          v_config_document jsonb;
          v_failure_reason_code text;
        BEGIN
          SELECT * INTO v_existing FROM source_candidate_decision
           WHERE actor_id=p_actor_id AND idempotency_key=p_idempotency_key;
          IF FOUND THEN
            IF v_existing.request_sha256<>p_request_sha256 THEN
              RAISE EXCEPTION 'IDEMPOTENCY_CONFLICT';
            END IF;
            decision_id:=v_existing.id; source_id:=v_existing.source_id;
            SELECT activation.id INTO outbox_id FROM source_activation_outbox activation
             WHERE activation.candidate_decision_id=v_existing.id;
            SELECT status INTO candidate_status FROM source_candidate WHERE id=v_existing.candidate_id;
            RETURN NEXT; RETURN;
          END IF;
          IF p_request_sha256 !~ '^[0-9a-f]{64}$'
             OR length(p_idempotency_key) NOT BETWEEN 8 AND 128
             OR source_v2_safe_audit_reason(p_reason) IS DISTINCT FROM true THEN
            RAISE EXCEPTION 'candidate decision input is invalid';
          END IF;
          SELECT * INTO v_candidate FROM source_candidate
           WHERE id=p_candidate_id FOR UPDATE;
          IF NOT FOUND
             OR v_candidate.status NOT IN ('READY_FOR_DECISION','BLOCKED') THEN
            RAISE EXCEPTION 'STALE_QUALIFICATION_BUNDLE';
          END IF;
          IF v_candidate.current_bundle_id IS NOT NULL THEN
            SELECT * INTO v_bundle FROM source_qualification_bundle
             WHERE id=v_candidate.current_bundle_id AND candidate_id=v_candidate.id;
            IF NOT FOUND THEN
              RAISE EXCEPTION 'STALE_QUALIFICATION_BUNDLE';
            END IF;
          END IF;
          IF p_decision='DISMISS' THEN
            SELECT run.failure_reason_code INTO v_failure_reason_code
              FROM source_qualification_run run
             WHERE run.candidate_id=v_candidate.id
               AND run.status='FAILED'
             ORDER BY run.completed_at DESC,run.id DESC LIMIT 1;
            UPDATE source_candidate SET status='DISMISSED',updated_at=p_decided_at
             WHERE id=v_candidate.id;
            INSERT INTO source_candidate_decision(
              id,candidate_id,bundle_id,decision,outcome,waiver_reason,reason,
              actor_id,request_sha256,idempotency_key,source_id,created_at
            ) VALUES (
              p_candidate_decision_id,v_candidate.id,v_candidate.current_bundle_id,
              'DISMISS','APPLIED',NULL,
              p_reason,p_actor_id,p_request_sha256,p_idempotency_key,NULL,p_decided_at
            );
            PERFORM append_audit_event(
              p_candidate_audit_id,'SOURCE_CANDIDATE_DISMISSED',p_actor_id,
              'SOURCE_CANDIDATE',v_candidate.id,
              jsonb_build_object(
                'status',v_candidate.status,'bundle_sha256',v_bundle.bundle_sha256,
                'failure_reason_code',v_failure_reason_code
              ),
              jsonb_build_object('status','DISMISSED'),p_reason,p_idempotency_key,p_decided_at
            );
            decision_id:=p_candidate_decision_id;source_id:=NULL;outbox_id:=NULL;
            candidate_status:='DISMISSED';RETURN NEXT;RETURN;
          END IF;
          IF v_candidate.current_bundle_id IS NULL THEN
            RAISE EXCEPTION 'STALE_QUALIFICATION_BUNDLE';
          END IF;
          IF p_decision='ENABLE' AND v_bundle.verdict = 'BLOCKED' THEN
            RAISE EXCEPTION 'candidate verdict cannot be enabled';
          END IF;
          IF v_candidate.status<>'READY_FOR_DECISION'
             OR v_bundle.bundle_sha256<>p_expected_bundle_sha256
             OR v_bundle.material_fingerprint<>v_candidate.material_fingerprint
             OR v_bundle.valid_until<=p_decided_at THEN
            RAISE EXCEPTION 'STALE_QUALIFICATION_BUNDLE';
          END IF;
          IF p_decision<>'ENABLE' THEN
            RAISE EXCEPTION 'candidate verdict cannot be enabled';
          END IF;
          IF v_bundle.verdict='WARN_WAIVABLE'
             AND source_v2_safe_audit_reason(p_waiver_reason) IS DISTINCT FROM true THEN
            RAISE EXCEPTION 'WARN_WAIVABLE requires waiver_reason';
          END IF;
          IF v_bundle.evidence_capture_policy<>'PRIVATE_RAW_ALLOWED' THEN
            RAISE EXCEPTION 'production refetch requires private raw evidence authorization';
          END IF;
          SELECT source_row.id,source_row.lifecycle_state,trial.requested_by,
                 policy.valid_until,schedule.id,config.connector_definition_id
            INTO v_source_id,v_source_state,v_submitted_by,v_valid_until,
                 v_schedule_id,v_connector_definition_id
            FROM source source_row
            JOIN source_policy_version policy
              ON policy.id=v_bundle.prepared_policy_version_id
             AND policy.id=source_row.current_policy_version_id
            JOIN connector_config_version config
              ON config.id=v_bundle.prepared_connector_config_version_id
             AND config.id=source_row.current_connector_config_version_id
             AND config.policy_version_id=policy.id AND config.validation_status='VALID'
            JOIN source_trial_run trial
              ON trial.id=v_bundle.prepared_trial_run_id
             AND trial.id=source_row.current_trial_run_id
              AND trial.policy_version_id=policy.id
              AND trial.connector_config_version_id=config.id
              AND trial.kind='LIVE_TRIAL' AND trial.execution_domain='TRIAL'
            JOIN connector_definition definition
              ON definition.id=config.connector_definition_id
             AND definition.connector_type='LIST_DETAIL'
             AND definition.definition_version='1.0.0'
            JOIN fetch_schedule schedule ON schedule.source_id=source_row.id
           WHERE source_row.id=v_bundle.prepared_source_id
             AND source_row.id=v_candidate.source_id
             AND source_row.lifecycle_state IN ('CANDIDATE','PAUSED')
             AND source_row.base_url=v_candidate.canonical_url
             AND policy.valid_until>p_decided_at
           FOR UPDATE OF source_row;
          IF NOT FOUND OR p_actor_id=v_bundle.evaluated_by OR p_actor_id=v_submitted_by THEN
            RAISE EXCEPTION 'prepared production evidence is incomplete or violates separation of duties';
          END IF;
          v_valid_until:=p_decided_at+interval '1 year';

          v_policy_id:=source_automation_derived_uuid(
            p_candidate_decision_id,'production-policy'
          );
          v_config_id:=source_automation_derived_uuid(
            p_candidate_decision_id,'production-config'
          );
          v_trial_id:=source_automation_derived_uuid(
            p_candidate_decision_id,'production-trial'
          );
          v_policy_version:='auto-' ||
            substring(replace(p_candidate_decision_id::text,'-',''),1,32);
          v_config_document:=jsonb_build_object(
            'allowed_hosts',jsonb_build_array(v_candidate.authorization_boundary),
            'list_url',v_candidate.canonical_url,
            'item_selector','a','link_selector','a','title_selector','a'
          );
          v_policy_document:=jsonb_build_object(
            'schema_version','2.0.0','policy_version',v_policy_version,
            'valid_from',p_decided_at,'valid_until',v_valid_until,
            'fetch',jsonb_build_object(
              'allowed_domains',jsonb_build_array(v_candidate.authorization_boundary),
              'minimum_interval_seconds',v_candidate.poll_interval_minutes*60,
              'rate_limit_per_minute',1,'user_agent','SRBGSourceAdapter/1.0'
            ),
            'slo',jsonb_build_object(
              'target_minutes',GREATEST(v_candidate.poll_interval_minutes*2,60)
            ),
            'robots_review',jsonb_build_object(
              'result','ALLOWED','evidence_url',v_candidate.canonical_url,
              'evidence_sha256',v_bundle.bundle_sha256,'checked_at',p_decided_at
            ),
            'terms_review',jsonb_build_object(
              'result','ALLOWED','evidence_url',v_candidate.canonical_url,
              'evidence_sha256',v_bundle.bundle_sha256,'checked_at',p_decided_at
            ),
            'copyright_review',jsonb_build_object(
              'result','ALLOWED','evidence_url',v_candidate.canonical_url,
              'evidence_sha256',v_bundle.bundle_sha256,'checked_at',p_decided_at
            ),
            'storage_policy',v_bundle.storage_policy,
            'evidence_capture_policy',v_bundle.evidence_capture_policy,
            'qualification_bundle_id',v_bundle.id,
            'qualification_bundle_sha256',v_bundle.bundle_sha256,
            'source_automation_rule_version',v_bundle.rule_version,
            'automatic_publication',false,
            'reason','administrator accepted current automated qualification bundle'
          );
          INSERT INTO source_policy_version(
            id,source_id,schema_version,policy_version,status,document,
            document_sha256,valid_from,valid_until,submitted_by,created_at
          ) VALUES (
            v_policy_id,v_source_id,'2.0.0',v_policy_version,'APPROVED',
            v_policy_document,
            encode(digest(convert_to(v_policy_document::text,'UTF8'),'sha256'),'hex'),
            p_decided_at,v_valid_until,v_submitted_by,p_decided_at
          );
          INSERT INTO connector_config_version(
            id,source_id,connector_definition_id,policy_version_id,version_number,
            config_document,config_sha256,allowed_hosts,validation_status,
            validation_reason_codes,created_by,created_at
          ) VALUES (
            v_config_id,v_source_id,v_connector_definition_id,v_policy_id,
            COALESCE((SELECT max(config.version_number)+1
                        FROM connector_config_version config
                       WHERE config.source_id=v_source_id),1),
            v_config_document,
            encode(digest(convert_to(v_config_document::text,'UTF8'),'sha256'),'hex'),
            ARRAY[v_candidate.authorization_boundary],'VALID',ARRAY[]::text[],
            v_submitted_by,p_decided_at
          );
          INSERT INTO source_trial_run(
            id,source_id,kind,execution_domain,policy_version_id,
            connector_config_version_id,authorization_decision_id,requested_by,
            request_reason,created_at
          ) VALUES (
            v_trial_id,v_source_id,'LIVE_TRIAL','TRIAL',v_policy_id,v_config_id,
            NULL,v_submitted_by,'automated qualification bundle accepted',p_decided_at
          );
          INSERT INTO source_trial_run_result(
            trial_run_id,status,quality_summary,raw_namespace,
            completed_by,completed_at
          ) VALUES (
            v_trial_id,'SUCCEEDED',jsonb_build_object(
              'qualification_bundle_id',v_bundle.id,
              'sampled_item_count',v_bundle.sampled_item_count,
              'relevant_item_count',v_bundle.relevant_item_count,
              'equivalence_rule','source-automation-qualification-v1'
            ),'trial/' || v_trial_id::text || '/qualification/',p_actor_id,p_decided_at
          );
          INSERT INTO source_governance_decision(
            id,source_id,decision_type,outcome,policy_version_id,
            submitted_by,decided_by,reason,valid_until,created_at
          ) VALUES (
            source_automation_derived_uuid(
              p_governance_decision_id,'automation-compliance'
            ),v_source_id,'COMPLIANCE','APPROVED',v_policy_id,
            v_submitted_by,p_actor_id,p_reason,v_valid_until,p_decided_at
          );
          INSERT INTO source_governance_decision(
            id,source_id,decision_type,outcome,policy_version_id,
            connector_config_version_id,trial_run_id,submitted_by,decided_by,
            reason,valid_until,created_at
          ) VALUES (
            p_governance_decision_id,v_source_id,'PRODUCTION_APPROVAL','APPROVED',
            v_policy_id,v_config_id,v_trial_id,v_submitted_by,p_actor_id,p_reason,
            v_valid_until,p_decided_at
          );
          INSERT INTO source_candidate_decision(
            id,candidate_id,bundle_id,decision,outcome,waiver_reason,reason,
            actor_id,request_sha256,idempotency_key,source_id,created_at
          ) VALUES (
            p_candidate_decision_id,v_candidate.id,v_bundle.id,'ENABLE','APPLIED',
            p_waiver_reason,p_reason,p_actor_id,p_request_sha256,p_idempotency_key,
            v_source_id,p_decided_at
          );
          UPDATE source_candidate
             SET status='ENABLED',source_id=v_source_id,updated_at=p_decided_at
           WHERE id=v_candidate.id;
          UPDATE source SET lifecycle_state='ACTIVE',trial_kind=NULL,
            state='ACTIVE',enabled=true,
            governance_owner_id=COALESCE(governance_owner_id,p_actor_id),
            current_policy_version_id=v_policy_id,
            current_connector_config_version_id=v_config_id,
            current_trial_run_id=v_trial_id,updated_at=p_decided_at
           WHERE id=v_source_id;
          UPDATE source_connector runtime_connector SET connector_type='LIST_DETAIL',
            config=v_config_document,enabled=true
           WHERE runtime_connector.source_id=v_source_id;
          UPDATE fetch_schedule schedule SET status='ACTIVE',lease_token=NULL,
            leased_until=NULL,next_run_at=p_decided_at+
              make_interval(secs=>schedule.interval_seconds),
            budget_window_started_at=p_decided_at,requests_used=0,bytes_used=0,
            updated_at=p_decided_at
           WHERE schedule.id=v_schedule_id;
          INSERT INTO source_lifecycle_event(
            id,source_id,from_state,to_state,action,reason_code,reason,actor_id,
            policy_version_id,governance_decision_id,created_at
          ) VALUES (
            p_lifecycle_event_id,v_source_id,v_source_state,'ACTIVE','APPROVE_PRODUCTION',
            'AUTOMATED_QUALIFICATION_APPROVED',p_reason,p_actor_id,
            v_policy_id,p_governance_decision_id,p_decided_at
          );
          SELECT stream.id INTO v_stream_id FROM source_stream stream
           WHERE stream.source_id=v_source_id
             AND stream.canonical_url=v_candidate.canonical_url FOR UPDATE;
          IF v_stream_id IS NULL THEN
            v_stream_id:=p_stream_id;
            INSERT INTO source_stream(
              id,source_id,candidate_id,stream_key,name,canonical_url,
              authorization_boundary,status,rule_version,connector_config_version_id,
              schedule_id,automatically_managed,created_at,updated_at
            ) VALUES (
              v_stream_id,v_source_id,v_candidate.id,'DEFAULT',v_candidate.institution_name,
              v_candidate.canonical_url,v_candidate.authorization_boundary,'ACTIVE',
              v_bundle.rule_version,v_config_id,
              v_schedule_id,true,p_decided_at,p_decided_at
            );
          ELSE
            UPDATE source_stream SET candidate_id=v_candidate.id,status='ACTIVE',
              rule_version=v_bundle.rule_version,schedule_id=v_schedule_id,
              connector_config_version_id=v_config_id,
              updated_at=p_decided_at WHERE id=v_stream_id;
          END IF;
          INSERT INTO source_activation_outbox(
            id,candidate_decision_id,source_id,stream_id,event_type,status,
            attempt_count,available_at,created_at
          ) VALUES (
            p_outbox_id,p_candidate_decision_id,v_source_id,v_stream_id,
            'PRODUCTION_REFETCH','PENDING',0,p_decided_at,p_decided_at
          );
          PERFORM append_audit_event(
            p_source_audit_id,'SOURCE_PRODUCTION_APPROVED',p_actor_id,'SOURCE',v_source_id,
            jsonb_build_object('lifecycle_state',v_source_state),
            jsonb_build_object('lifecycle_state','ACTIVE','qualification_bundle_id',v_bundle.id),
            p_reason,p_idempotency_key,p_decided_at
          );
          PERFORM append_audit_event(
            p_candidate_audit_id,'SOURCE_CANDIDATE_ENABLED',p_actor_id,
            'SOURCE_CANDIDATE',v_candidate.id,
            jsonb_build_object('status',v_candidate.status,'bundle_sha256',v_bundle.bundle_sha256),
            jsonb_build_object('status','ENABLED','source_id',v_source_id,'stream_id',v_stream_id),
            p_reason,p_idempotency_key,p_decided_at
          );
          decision_id:=p_candidate_decision_id;source_id:=v_source_id;
          outbox_id:=p_outbox_id;candidate_status:='ENABLED';RETURN NEXT;
        END $$
        """
    )
    signature = (
        "activate_qualified_candidate(uuid,text,text,text,text,text,text,uuid,uuid,uuid,"
        "uuid,uuid,uuid,uuid,uuid,timestamptz)"
    )
    op.execute(f"REVOKE ALL ON FUNCTION {signature} FROM PUBLIC")
    op.execute(
        "GRANT EXECUTE ON FUNCTION activate_qualified_candidate("
        "uuid,text,text,text,text,text,text,uuid,uuid,uuid,uuid,uuid,uuid,uuid,uuid,timestamptz) "
        "TO srbg_api_role"
    )


def _create_worker_command_boundary() -> None:
    op.execute(
        r"""
        CREATE FUNCTION list_pending_source_qualification_ids(
          p_now timestamptz,p_limit integer
        ) RETURNS TABLE(qualification_run_id uuid)
        LANGUAGE plpgsql SECURITY DEFINER
        SET search_path=pg_catalog,public AS $$
        DECLARE
          v_due record;
          v_run_id uuid;
          v_request_audit_id uuid;
          v_prepared_source_id uuid;
          v_prepared_policy_version_id uuid;
          v_prepared_connector_config_version_id uuid;
          v_prepared_trial_run_id uuid;
          v_prepared_schedule_id uuid;
        BEGIN
          IF p_limit NOT BETWEEN 1 AND 100
             OR p_now NOT BETWEEN clock_timestamp()-interval '5 minutes'
                              AND clock_timestamp()+interval '5 minutes' THEN
            RAISE EXCEPTION 'qualification claim input is invalid';
          END IF;
          FOR v_due IN
            SELECT candidate.id AS candidate_id,source_row.id AS source_id,
                   source_row.lifecycle_state,policy.id AS policy_id,
                   policy.valid_until
              FROM source_candidate candidate
              JOIN source source_row ON source_row.id=candidate.source_id
              JOIN source_policy_version policy
                ON policy.id=source_row.current_policy_version_id
             WHERE candidate.status='ENABLED'
               AND source_row.lifecycle_state='ACTIVE'
               AND policy.status='APPROVED'
               AND policy.document ? 'qualification_bundle_id'
               AND policy.valid_until<=p_now
             ORDER BY policy.valid_until,candidate.id
             LIMIT p_limit
             FOR UPDATE OF candidate,source_row SKIP LOCKED
          LOOP
            UPDATE source_qualification_run
               SET status='CANCELLED',started_at=COALESCE(started_at,p_now),
                   completed_at=p_now,lease_token=NULL,leased_until=NULL
             WHERE candidate_id=v_due.candidate_id
               AND status IN ('PENDING','RUNNING');
            UPDATE source_candidate
               SET status='STALE',current_bundle_id=NULL,updated_at=p_now
             WHERE id=v_due.candidate_id;
            UPDATE source_stream
               SET status='PAUSED',paused_reason='AUTHORIZATION_EXPIRED',updated_at=p_now
             WHERE source_id=v_due.source_id AND status<>'REVOKED';
            UPDATE fetch_schedule
               SET status='PAUSED',lease_token=NULL,leased_until=NULL,updated_at=p_now
             WHERE source_id=v_due.source_id;
            UPDATE source_connector SET enabled=false WHERE source_id=v_due.source_id;
            UPDATE source
               SET lifecycle_state='PAUSED',trial_kind=NULL,
                   state='CANDIDATE',enabled=false,updated_at=p_now
             WHERE id=v_due.source_id;
            INSERT INTO source_lifecycle_event(
              id,source_id,from_state,to_state,action,reason_code,reason,
              actor_id,policy_version_id,created_at
            ) VALUES (
              source_automation_derived_uuid(v_due.policy_id,'authorization-expired-lifecycle'),
              v_due.source_id,v_due.lifecycle_state,'PAUSED','PAUSE',
              'AUTHORIZATION_EXPIRED','automated source authorization expired before renewal',
              '019b0000-0000-7000-8000-000000009001'::uuid,v_due.policy_id,p_now
            );
            PERFORM append_audit_event(
              source_automation_derived_uuid(v_due.policy_id,'authorization-expired-audit'),
              'SOURCE_AUTHORIZATION_EXPIRED',
              '019b0000-0000-7000-8000-000000009001'::uuid,
              'SOURCE',v_due.source_id,
              jsonb_build_object(
                'lifecycle_state',v_due.lifecycle_state,
                'policy_valid_until',v_due.valid_until
              ),
              jsonb_build_object(
                'lifecycle_state','PAUSED','candidate_status','STALE'
              ),
              'automated source authorization expired before renewal',
              'authorization-expired:' || v_due.policy_id::text,p_now
            );
          END LOOP;

          FOR v_due IN
            SELECT candidate.id AS candidate_id,source_row.id AS source_id,
                   source_row.lifecycle_state,policy.id AS policy_id,
                   policy.valid_until
              FROM source_candidate candidate
              JOIN source source_row ON source_row.id=candidate.source_id
              JOIN source_policy_version policy
                ON policy.id=source_row.current_policy_version_id
             WHERE candidate.status='ENABLED'
               AND source_row.lifecycle_state='ACTIVE'
               AND policy.status='APPROVED'
               AND policy.document ? 'qualification_bundle_id'
               AND policy.valid_until>p_now
               AND policy.valid_until<=p_now+interval '30 days'
               AND source_policy_compliance_current(
                     source_row.id,policy.id,p_now
                   )
               AND NOT EXISTS (
                 SELECT 1 FROM source_qualification_run renewal
                  WHERE renewal.candidate_id=candidate.id
                    AND renewal.renewal_of_policy_version_id=policy.id
               )
             ORDER BY policy.valid_until,candidate.id
             LIMIT p_limit
             FOR UPDATE OF candidate,source_row SKIP LOCKED
          LOOP
            v_run_id:=source_automation_derived_uuid(
              v_due.policy_id,'annual-requalification-run'
            );
            v_request_audit_id:=source_automation_derived_uuid(
              v_due.policy_id,'annual-requalification-request-audit'
            );
            SELECT prepared_source_id,prepared_policy_version_id,
                   prepared_connector_config_version_id,prepared_trial_run_id,
                   prepared_schedule_id
              INTO v_prepared_source_id,v_prepared_policy_version_id,
                   v_prepared_connector_config_version_id,v_prepared_trial_run_id,
                   v_prepared_schedule_id
              FROM prepare_source_candidate_for_qualification(
                v_due.candidate_id,v_run_id,
                '019b0000-0000-7000-8000-000000009001'::uuid,p_now
              );
            INSERT INTO source_qualification_run(
              id,candidate_id,status,execution_domain,rule_version,requested_by,
              qualification_mode,renewal_of_policy_version_id,
              prepared_source_id,prepared_policy_version_id,
              prepared_connector_config_version_id,prepared_trial_run_id,created_at
            ) VALUES (
              v_run_id,v_due.candidate_id,'PENDING','QUALIFICATION',
              'source-qualification-v1',
              '019b0000-0000-7000-8000-000000009001'::uuid,
              'SHADOW_RENEWAL',v_due.policy_id,v_prepared_source_id,
              v_prepared_policy_version_id,v_prepared_connector_config_version_id,
              v_prepared_trial_run_id,p_now
            );
            PERFORM append_audit_event(
              v_request_audit_id,'SOURCE_SHADOW_REQUALIFICATION_REQUESTED',
              '019b0000-0000-7000-8000-000000009001'::uuid,
              'SOURCE_CANDIDATE',v_due.candidate_id,
              jsonb_build_object(
                'status','ENABLED','lifecycle_state',v_due.lifecycle_state,
                'policy_valid_until',v_due.valid_until
              ),
              jsonb_build_object(
                'status','ENABLED','lifecycle_state','ACTIVE',
                'qualification_run_id',v_run_id,
                'qualification_mode','SHADOW_RENEWAL'
              ),
              'annual automated source authorization entered shadow requalification',
              'annual-requalification:' || v_due.policy_id::text,p_now
            );
          END LOOP;
          RETURN QUERY
          SELECT run.id
            FROM source_qualification_run run
           WHERE run.execution_domain='QUALIFICATION'
             AND (
               run.status='PENDING'
               OR (run.status='RUNNING' AND run.leased_until<=p_now)
             )
           ORDER BY run.created_at,run.id
           LIMIT p_limit;
        END $$
        """
    )
    op.execute(
        r"""
        CREATE FUNCTION acquire_source_qualification(
          p_qualification_run_id uuid,p_lease_token uuid,
          p_now timestamptz,p_leased_until timestamptz
        ) RETURNS TABLE(
          candidate_id uuid,campaign_id uuid,canonical_url text,
          authorization_boundary text,rule_version text,material_fingerprint text,
          lease_token uuid,prepared_source_id uuid,prepared_policy_version_id uuid,
          prepared_connector_config_version_id uuid,prepared_trial_run_id uuid
        )
        LANGUAGE plpgsql SECURITY DEFINER
        SET search_path=pg_catalog,public AS $$
        BEGIN
          IF substring(p_lease_token::text,15,1)<>'7'
             OR p_now NOT BETWEEN clock_timestamp()-interval '5 minutes'
                              AND clock_timestamp()+interval '5 minutes'
             OR p_leased_until<=p_now
             OR p_leased_until>p_now+interval '15 minutes' THEN
            RAISE EXCEPTION 'qualification lease input is invalid';
          END IF;
          RETURN QUERY
          WITH leased AS (
            UPDATE source_qualification_run run
               SET status='RUNNING',lease_token=p_lease_token,
                   leased_until=p_leased_until,
                   started_at=COALESCE(run.started_at,p_now)
             WHERE run.id=p_qualification_run_id
               AND run.execution_domain='QUALIFICATION'
               AND (
                 run.status='PENDING'
                 OR (run.status='RUNNING' AND run.leased_until<=p_now)
               )
               AND EXISTS (
                 SELECT 1 FROM source_candidate candidate
                  WHERE candidate.id=run.candidate_id
                    AND (
                      (run.qualification_mode='INITIAL'
                       AND candidate.status='QUALIFYING')
                      OR (run.qualification_mode='SHADOW_RENEWAL'
                          AND candidate.status='ENABLED')
                    )
               )
            RETURNING run.candidate_id,run.rule_version,run.lease_token,
                      run.prepared_source_id,run.prepared_policy_version_id,
                      run.prepared_connector_config_version_id,
                      run.prepared_trial_run_id
          )
          SELECT leased.candidate_id,occurrence.campaign_id,
                 candidate.canonical_url::text,
                 candidate.authorization_boundary::text,
                 leased.rule_version::text,candidate.material_fingerprint::text,
                 leased.lease_token,leased.prepared_source_id,
                 leased.prepared_policy_version_id,
                 leased.prepared_connector_config_version_id,
                 leased.prepared_trial_run_id
            FROM leased
            JOIN source_candidate candidate ON candidate.id=leased.candidate_id
            LEFT JOIN LATERAL (
              SELECT candidate_occurrence.campaign_id
                FROM source_candidate_occurrence candidate_occurrence
               WHERE candidate_occurrence.candidate_id=candidate.id
               ORDER BY candidate_occurrence.discovered_at DESC,
                        candidate_occurrence.id DESC
               LIMIT 1
            ) occurrence ON true;
        END $$
        """
    )
    op.execute(
        r"""
        CREATE FUNCTION record_source_qualification_capture(
          p_capture_id uuid,p_qualification_run_id uuid,p_candidate_id uuid,
          p_lease_token uuid,p_purpose text,p_requested_url text,p_final_url text,
          p_object_key text,p_content_sha256 text,p_response_sha256 text,
          p_byte_size bigint,p_http_status integer,p_content_type text,
          p_captured_at timestamptz
        ) RETURNS uuid
        LANGUAGE plpgsql SECURITY DEFINER
        SET search_path=pg_catalog,public AS $$
        DECLARE v_capture_id uuid;
        BEGIN
          IF substring(p_capture_id::text,15,1)<>'7'
             OR p_purpose<>'TARGET_PAGE'
             OR p_content_sha256 !~ '^[0-9a-f]{64}$'
             OR p_response_sha256 !~ '^[0-9a-f]{64}$'
             OR p_object_key<>'qualification/sha256/' ||
                  substring(p_content_sha256,1,2) || '/' || p_content_sha256
             OR p_byte_size NOT BETWEEN 1 AND 52428800
             OR p_http_status NOT BETWEEN 100 AND 599
             OR length(p_content_type) NOT BETWEEN 1 AND 100
             OR p_captured_at NOT BETWEEN clock_timestamp()-interval '1 hour'
                                      AND clock_timestamp()+interval '5 minutes' THEN
            RAISE EXCEPTION 'qualification capture input is invalid';
          END IF;
          WITH authorized AS MATERIALIZED (
            SELECT run.id,run.candidate_id
              FROM source_qualification_run run
              JOIN source_candidate candidate ON candidate.id=run.candidate_id
              JOIN source source_row ON source_row.id=candidate.source_id
              JOIN source_policy_version policy
                ON policy.id=run.prepared_policy_version_id
               AND policy.source_id=run.prepared_source_id
             WHERE run.id=p_qualification_run_id
               AND run.candidate_id=p_candidate_id
               AND run.execution_domain='QUALIFICATION'
               AND run.status='RUNNING'
               AND run.lease_token=p_lease_token
               AND run.leased_until>=p_captured_at
               AND (
                 (run.qualification_mode='INITIAL'
                  AND candidate.status='QUALIFYING')
                 OR (run.qualification_mode='SHADOW_RENEWAL'
                     AND candidate.status='ENABLED')
               )
               AND policy.document->>'evidence_capture_policy'='PRIVATE_RAW_ALLOWED'
               AND policy.document->>'automatic_publication'='false'
               AND policy.document#>>'{qualification_evidence,purpose}'='qualification_only'
               AND policy.document#>>'{qualification_evidence,promotion_allowed}'='false'
               AND source_v2_safe_http_url(
                     p_requested_url,ARRAY[candidate.authorization_boundary]
                   ) IS TRUE
               AND source_v2_safe_http_url(
                     p_final_url,ARRAY[candidate.authorization_boundary]
                   ) IS TRUE
          ), inserted AS (
            INSERT INTO source_qualification_capture(
              id,run_id,candidate_id,purpose,requested_url,final_url,object_key,
              content_sha256,response_sha256,byte_size,http_status,
              content_type,captured_at
            )
            SELECT p_capture_id,authorized.id,authorized.candidate_id,p_purpose,
                   p_requested_url,p_final_url,p_object_key,p_content_sha256,
                   p_response_sha256,p_byte_size,p_http_status,p_content_type,
                   p_captured_at
              FROM authorized
            ON CONFLICT ON CONSTRAINT uq_qualification_capture_run_hash DO NOTHING
            RETURNING id
          )
          SELECT id INTO v_capture_id FROM inserted
          UNION ALL
          SELECT capture.id
            FROM source_qualification_capture capture
            JOIN authorized ON authorized.id=capture.run_id
           WHERE capture.content_sha256=p_content_sha256
             AND capture.purpose=p_purpose
          LIMIT 1;
          RETURN v_capture_id;
        END $$
        """
    )
    op.execute(
        r"""
        CREATE FUNCTION complete_source_qualification(
          p_bundle_id uuid,p_qualification_run_id uuid,p_candidate_id uuid,
          p_lease_token uuid,p_rule_version text,
          p_expected_material_fingerprint text,p_material_fingerprint text,
          p_verdict text,p_storage_policy text,p_evidence_capture_policy text,
          p_checks jsonb,p_reason_codes text[],p_sampled_item_count integer,
          p_relevant_item_count integer,
          p_completed_at timestamptz,p_valid_until timestamptz
        ) RETURNS uuid
        LANGUAGE plpgsql SECURITY DEFINER
        SET search_path=pg_catalog,public AS $$
        DECLARE
          v_bundle_id uuid;
          v_candidate_id uuid;
          v_qualification_mode text;
          v_source_id uuid;
          v_source_state text;
          v_policy_id uuid;
        BEGIN
          IF substring(p_bundle_id::text,15,1)<>'7'
             OR length(p_rule_version) NOT BETWEEN 1 AND 80
             OR p_expected_material_fingerprint !~ '^[0-9a-f]{64}$'
             OR p_material_fingerprint !~ '^[0-9a-f]{64}$'
             OR p_verdict NOT IN ('QUALIFIED','WARN_WAIVABLE','BLOCKED')
             OR p_storage_policy NOT IN (
                  'RAW_EVIDENCE_ALLOWED','METADATA_ONLY','LINK_ONLY'
                )
             OR p_evidence_capture_policy NOT IN (
                  'PRIVATE_RAW_ALLOWED','TRANSIENT_METADATA_ONLY'
                )
             OR (p_verdict='QUALIFIED' AND (
                  p_storage_policy<>'RAW_EVIDENCE_ALLOWED'
                  OR p_evidence_capture_policy<>'PRIVATE_RAW_ALLOWED'
                ))
             OR (p_verdict='WARN_WAIVABLE' AND (
                  p_storage_policy<>'METADATA_ONLY'
                  OR p_evidence_capture_policy NOT IN (
                       'PRIVATE_RAW_ALLOWED','TRANSIENT_METADATA_ONLY'
                     )
                ))
             OR (p_verdict='BLOCKED' AND (
                  p_storage_policy<>'LINK_ONLY'
                  OR p_evidence_capture_policy<>'TRANSIENT_METADATA_ONLY'
                ))
             OR jsonb_typeof(p_checks)<>'array'
             OR jsonb_array_length(p_checks) NOT BETWEEN 1 AND 100
             OR p_reason_codes IS NULL OR cardinality(p_reason_codes)>100
             OR cardinality(p_reason_codes)<>(
                  SELECT count(DISTINCT reason_code)
                    FROM unnest(p_reason_codes) reason_code
                )
             OR EXISTS (
                  SELECT 1 FROM jsonb_array_elements(p_checks) check_row
                   WHERE jsonb_typeof(check_row)<>'object'
                      OR (SELECT count(*) FROM jsonb_object_keys(check_row))<>5
                      OR check_row->>'code' !~ '^[A-Z][A-Z0-9_]{0,99}$'
                      OR check_row->>'level' NOT IN ('PASS','WARN','BLOCK')
                      OR length(check_row->>'message') NOT BETWEEN 1 AND 500
                      OR jsonb_typeof(check_row->'evidence_refs')<>'array'
                      OR jsonb_array_length(
                           CASE WHEN jsonb_typeof(check_row->'evidence_refs')='array'
                                THEN check_row->'evidence_refs' ELSE '[]'::jsonb END
                         ) NOT BETWEEN 1 AND 50
                      OR CASE
                           WHEN check_row->>'observed_at' ~
                             '(Z|[+-][0-9]{2}:[0-9]{2})$'
                           THEN (check_row->>'observed_at')::timestamptz
                                NOT BETWEEN p_completed_at-interval '1 hour'
                                        AND p_completed_at
                           ELSE true
                         END
                      OR EXISTS (
                           SELECT 1
                             FROM jsonb_array_elements_text(
                               CASE
                                 WHEN jsonb_typeof(check_row->'evidence_refs')='array'
                                 THEN check_row->'evidence_refs' ELSE '[]'::jsonb
                               END
                             ) evidence_ref
                            WHERE length(evidence_ref) NOT BETWEEN 1 AND 500
                               OR evidence_ref !~
                                    '^qualification-run:[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
                               OR evidence_ref<>
                                    'qualification-run:' || p_qualification_run_id::text
                         )
                      OR jsonb_array_length(
                           CASE WHEN jsonb_typeof(check_row->'evidence_refs')='array'
                                THEN check_row->'evidence_refs' ELSE '[]'::jsonb END
                         )<>(
                           SELECT count(DISTINCT evidence_ref)
                             FROM jsonb_array_elements_text(
                               CASE
                                 WHEN jsonb_typeof(check_row->'evidence_refs')='array'
                                 THEN check_row->'evidence_refs' ELSE '[]'::jsonb
                               END
                             ) evidence_ref
                         )
                )
             OR (p_verdict='QUALIFIED' AND EXISTS (
                  SELECT 1 FROM jsonb_array_elements(p_checks) check_row
                   WHERE check_row->>'level'<>'PASS'
                ))
             OR (p_verdict='WARN_WAIVABLE' AND (
                  NOT EXISTS (
                    SELECT 1 FROM jsonb_array_elements(p_checks) check_row
                     WHERE check_row->>'level'='WARN'
                  )
                  OR EXISTS (
                    SELECT 1 FROM jsonb_array_elements(p_checks) check_row
                     WHERE check_row->>'level'='BLOCK'
                  )
                ))
             OR (p_verdict='BLOCKED' AND NOT EXISTS (
                  SELECT 1 FROM jsonb_array_elements(p_checks) check_row
                   WHERE check_row->>'level'='BLOCK'
                ))
             OR EXISTS (
                  SELECT 1 FROM unnest(p_reason_codes) reason_code
                   WHERE reason_code !~ '^[A-Z0-9_]{1,100}$'
                )
             OR p_sampled_item_count<0 OR p_relevant_item_count<0
             OR p_relevant_item_count>p_sampled_item_count
             OR p_completed_at NOT BETWEEN clock_timestamp()-interval '5 minutes'
                                      AND clock_timestamp()+interval '5 minutes'
             OR p_valid_until<=p_completed_at
             OR p_valid_until>p_completed_at+interval '7 days' THEN
            RAISE EXCEPTION 'qualification completion input is invalid';
          END IF;
          WITH authority AS MATERIALIZED (
            SELECT run.id,run.candidate_id,run.qualification_mode,
                   run.prepared_source_id,run.prepared_policy_version_id,
                   run.prepared_connector_config_version_id,
                   run.prepared_trial_run_id,candidate.source_id,
                   candidate.canonical_url,candidate.authorization_boundary,
                   COALESCE((
                     SELECT jsonb_agg(capture.response_sha256
                                      ORDER BY capture.response_sha256)
                       FROM source_qualification_capture capture
                      WHERE capture.run_id=run.id
                        AND capture.candidate_id=candidate.id
                   ),'[]'::jsonb) AS response_sha256s
              FROM source_qualification_run run
              JOIN source_candidate candidate ON candidate.id=run.candidate_id
              JOIN source source_row
                ON source_row.id=run.prepared_source_id
               AND source_row.id=candidate.source_id
              JOIN source_policy_version prepared_policy
                ON prepared_policy.id=run.prepared_policy_version_id
               AND prepared_policy.source_id=source_row.id
              JOIN connector_config_version prepared_config
                ON prepared_config.id=run.prepared_connector_config_version_id
               AND prepared_config.source_id=source_row.id
               AND prepared_config.policy_version_id=prepared_policy.id
               AND prepared_config.validation_status='VALID'
              JOIN source_trial_run prepared_trial
                ON prepared_trial.id=run.prepared_trial_run_id
               AND prepared_trial.source_id=source_row.id
               AND prepared_trial.policy_version_id=prepared_policy.id
               AND prepared_trial.connector_config_version_id=prepared_config.id
               AND prepared_trial.kind='LIVE_TRIAL'
               AND prepared_trial.execution_domain='TRIAL'
             WHERE run.id=p_qualification_run_id
               AND run.candidate_id=p_candidate_id
               AND run.execution_domain='QUALIFICATION'
               AND run.status='RUNNING'
               AND run.lease_token=p_lease_token
               AND run.leased_until>=p_completed_at
               AND run.rule_version=p_rule_version
               AND (
                 (run.qualification_mode='INITIAL'
                  AND candidate.status='QUALIFYING')
                 OR (
                   run.qualification_mode='SHADOW_RENEWAL'
                   AND candidate.status='ENABLED'
                   AND source_row.lifecycle_state='ACTIVE'
                   AND source_row.current_policy_version_id=
                       run.renewal_of_policy_version_id
                   AND source_policy_compliance_current(
                         source_row.id,run.renewal_of_policy_version_id,
                         p_completed_at
                       )
                 )
               )
               AND candidate.material_fingerprint=p_expected_material_fingerprint
               AND (
                 NOT EXISTS (
                   SELECT 1 FROM source_qualification_capture capture
                    WHERE capture.run_id=run.id
                      AND capture.candidate_id=candidate.id
                 )
                 OR p_material_fingerprint=(
                   SELECT encode(digest(convert_to(
                     candidate.canonical_url || chr(10) ||
                     candidate.authorization_boundary || chr(10) ||
                     string_agg(capture.response_sha256,chr(10)
                                ORDER BY capture.response_sha256),
                     'UTF8'
                   ),'sha256'),'hex')
                     FROM source_qualification_capture capture
                    WHERE capture.run_id=run.id
                      AND capture.candidate_id=candidate.id
                 )
               )
               AND (
                 p_verdict='BLOCKED'
                 OR (
                   run.prepared_source_id IS NOT NULL
                   AND run.prepared_policy_version_id IS NOT NULL
                   AND run.prepared_connector_config_version_id IS NOT NULL
                   AND run.prepared_trial_run_id IS NOT NULL
                   AND EXISTS (
                     SELECT 1 FROM source_qualification_capture capture
                      WHERE capture.run_id=run.id
                        AND capture.candidate_id=candidate.id
                   )
                 )
               )
             FOR UPDATE OF run,candidate,source_row
          ), bundle AS (
            INSERT INTO source_qualification_bundle(
              id,candidate_id,run_id,rule_version,material_fingerprint,verdict,
              storage_policy,evidence_capture_policy,checks,reason_codes,
              sampled_item_count,relevant_item_count,bundle_sha256,evaluated_by,
              prepared_source_id,prepared_policy_version_id,
              prepared_connector_config_version_id,prepared_trial_run_id,
              created_at,valid_until
            )
            SELECT p_bundle_id,authority.candidate_id,authority.id,p_rule_version,
                   p_expected_material_fingerprint,p_verdict,p_storage_policy,
                   p_evidence_capture_policy,p_checks,p_reason_codes,
                   p_sampled_item_count,p_relevant_item_count,
                   encode(digest(convert_to(jsonb_build_object(
                     'candidate_id',authority.candidate_id,
                     'run_id',authority.id,
                     'canonical_url',authority.canonical_url,
                     'authorization_boundary',authority.authorization_boundary,
                     'rule_version',p_rule_version,
                     'material_fingerprint',p_expected_material_fingerprint,
                     'qualification_evidence_fingerprint',p_material_fingerprint,
                     'response_sha256s',authority.response_sha256s,
                     'verdict',p_verdict,'storage_policy',p_storage_policy,
                     'evidence_capture_policy',p_evidence_capture_policy,
                     'checks',p_checks,'reason_codes',to_jsonb(p_reason_codes),
                     'sampled_item_count',p_sampled_item_count,
                     'relevant_item_count',p_relevant_item_count,
                     'created_at',p_completed_at,'valid_until',p_valid_until
                   )::text,'UTF8'),'sha256'),'hex'),
                   '019b0000-0000-7000-8000-000000009002'::uuid,
                   authority.prepared_source_id,
                   authority.prepared_policy_version_id,
                   authority.prepared_connector_config_version_id,
                   authority.prepared_trial_run_id,p_completed_at,p_valid_until
              FROM authority
            ON CONFLICT (run_id) DO NOTHING
            RETURNING id,candidate_id
          ), completed AS (
            UPDATE source_qualification_run run
               SET status='SUCCEEDED',completed_at=p_completed_at,
                   lease_token=NULL,leased_until=NULL
              FROM bundle
             WHERE run.id=p_qualification_run_id
               AND bundle.candidate_id=run.candidate_id
            RETURNING bundle.id,run.candidate_id,run.qualification_mode,
                      run.prepared_source_id
          )
          SELECT id,candidate_id,qualification_mode,prepared_source_id
            INTO v_bundle_id,v_candidate_id,v_qualification_mode,v_source_id
            FROM completed;
          IF v_bundle_id IS NULL THEN
            RETURN NULL;
          END IF;
          IF v_qualification_mode='INITIAL' THEN
            UPDATE source_candidate candidate
               SET current_bundle_id=v_bundle_id,
                   status=CASE WHEN p_verdict='BLOCKED'
                               THEN 'BLOCKED' ELSE 'READY_FOR_DECISION' END,
                   material_fingerprint=p_expected_material_fingerprint,
                   updated_at=p_completed_at
             WHERE candidate.id=v_candidate_id;
          ELSIF p_verdict='BLOCKED' THEN
            SELECT lifecycle_state,current_policy_version_id
              INTO v_source_state,v_policy_id
              FROM source WHERE id=v_source_id FOR UPDATE;
            UPDATE source_candidate
               SET current_bundle_id=v_bundle_id,status='BLOCKED',
                   material_fingerprint=p_expected_material_fingerprint,
                   updated_at=p_completed_at
             WHERE id=v_candidate_id;
            UPDATE source_stream
               SET status='PAUSED',paused_reason='SHADOW_QUALIFICATION_BLOCKED',
                   updated_at=p_completed_at
             WHERE source_id=v_source_id AND status<>'REVOKED';
            UPDATE fetch_schedule
               SET status='PAUSED',lease_token=NULL,leased_until=NULL,
                   updated_at=p_completed_at
             WHERE source_id=v_source_id;
            UPDATE source_connector SET enabled=false WHERE source_id=v_source_id;
            UPDATE source
               SET lifecycle_state='PAUSED',trial_kind=NULL,
                   state='CANDIDATE',enabled=false,updated_at=p_completed_at
             WHERE id=v_source_id;
            INSERT INTO source_lifecycle_event(
              id,source_id,from_state,to_state,action,reason_code,reason,
              actor_id,policy_version_id,created_at
            ) VALUES (
              source_automation_derived_uuid(v_bundle_id,'shadow-blocked-lifecycle'),
              v_source_id,v_source_state,'PAUSED','PAUSE',
              'SHADOW_QUALIFICATION_BLOCKED',
              'shadow requalification found a blocking governance condition',
              '019b0000-0000-7000-8000-000000009002'::uuid,v_policy_id,p_completed_at
            );
            PERFORM append_audit_event(
              source_automation_derived_uuid(v_bundle_id,'shadow-blocked-audit'),
              'SOURCE_SHADOW_REQUALIFICATION_BLOCKED',
              '019b0000-0000-7000-8000-000000009002'::uuid,
              'SOURCE',v_source_id,
              jsonb_build_object('lifecycle_state',v_source_state),
              jsonb_build_object(
                'lifecycle_state','PAUSED','candidate_status','BLOCKED',
                'qualification_bundle_id',v_bundle_id
              ),
              'shadow requalification found a blocking governance condition',
              'shadow-requalification:' || p_qualification_run_id::text,p_completed_at
            );
          ELSE
            PERFORM append_audit_event(
              source_automation_derived_uuid(v_bundle_id,'shadow-result-audit'),
              'SOURCE_SHADOW_REQUALIFICATION_COMPLETED',
              '019b0000-0000-7000-8000-000000009002'::uuid,
              'SOURCE',v_source_id,
              jsonb_build_object(
                'lifecycle_state','ACTIVE','candidate_status','ENABLED'
              ),
              jsonb_build_object(
                'lifecycle_state','ACTIVE','candidate_status','ENABLED',
                'qualification_bundle_id',v_bundle_id,'verdict',p_verdict,
                'renewal_status','PENDING_CONFIRMATION'
              ),
              'shadow requalification completed without interrupting current authorization',
              'shadow-requalification:' || p_qualification_run_id::text,p_completed_at
            );
          END IF;
          RETURN v_bundle_id;
        END $$
        """
    )
    op.execute(
        r"""
        CREATE FUNCTION fail_source_qualification(
          p_qualification_run_id uuid,p_candidate_id uuid,p_lease_token uuid,
          p_reason_code text,p_failed_at timestamptz
        ) RETURNS uuid
        LANGUAGE plpgsql SECURITY DEFINER
        SET search_path=pg_catalog,public AS $$
        DECLARE v_candidate_id uuid;
        BEGIN
          IF p_reason_code NOT IN (
               'TARGET_PROBE_DISABLED','TARGET_OUTSIDE_AUTHORIZATION_BOUNDARY',
               'TARGET_SSRF_REJECTED','TARGET_FETCH_FAILED','TARGET_EMPTY_RESPONSE',
               'TARGET_ROBOTS_UNAVAILABLE','TARGET_SECURITY_REJECTED',
               'QUALIFICATION_CAPTURE_NOT_AUTHORIZED','PRODUCTION_PREPARATION_MISSING',
               'QUALIFICATION_COMPLETION_NOT_AUTHORIZED','TARGET_REQUEST_URL_MISMATCH',
               'TARGET_ADDRESS_NOT_PUBLIC','TARGET_REDIRECT_BOUNDARY_INVALID',
               'TARGET_HTTP_STATUS_REJECTED','UNKNOWN'
             )
             OR p_failed_at NOT BETWEEN clock_timestamp()-interval '5 minutes'
                                   AND clock_timestamp()+interval '5 minutes' THEN
            RAISE EXCEPTION 'qualification failure input is invalid';
          END IF;
          WITH failed AS (
            UPDATE source_qualification_run run
               SET status='FAILED',completed_at=p_failed_at,
                   failure_reason_code=p_reason_code,
                   lease_token=NULL,leased_until=NULL
             WHERE run.id=p_qualification_run_id
               AND run.candidate_id=p_candidate_id
               AND run.execution_domain='QUALIFICATION'
               AND run.status='RUNNING'
               AND run.lease_token=p_lease_token
            RETURNING run.candidate_id,run.qualification_mode
          ), candidate_updated AS (
            UPDATE source_candidate candidate
               SET status='BLOCKED',current_bundle_id=NULL,updated_at=p_failed_at
              FROM failed
             WHERE candidate.id=failed.candidate_id
               AND failed.qualification_mode='INITIAL'
               AND candidate.status='QUALIFYING'
            RETURNING candidate.id
          )
          SELECT candidate_id INTO v_candidate_id FROM failed;
          RETURN v_candidate_id;
        END $$
        """
    )
    op.execute(
        r"""
        CREATE FUNCTION list_pending_source_activation_ids(
          p_now timestamptz,p_limit integer
        ) RETURNS TABLE(outbox_id uuid)
        LANGUAGE plpgsql SECURITY DEFINER
        SET search_path=pg_catalog,public AS $$
        BEGIN
          IF p_limit NOT BETWEEN 1 AND 100
             OR p_now NOT BETWEEN clock_timestamp()-interval '5 minutes'
                              AND clock_timestamp()+interval '5 minutes' THEN
            RAISE EXCEPTION 'activation claim input is invalid';
          END IF;
          RETURN QUERY
          SELECT activation.id
            FROM source_activation_outbox activation
           WHERE (
             (activation.status IN ('PENDING','FAILED')
              AND activation.available_at<=p_now)
             OR (activation.status='PROCESSING'
                 AND activation.leased_until<=p_now)
           )
           ORDER BY activation.available_at,activation.id
           LIMIT p_limit;
        END $$
        """
    )
    op.execute(
        r"""
        CREATE FUNCTION prepare_source_activation(
          p_outbox_id uuid,p_fetch_run_id uuid,
          p_now timestamptz,p_leased_until timestamptz
        ) RETURNS TABLE(
          outbox_id uuid,source_id uuid,fetch_run_id uuid,needs_dispatch boolean
        )
        LANGUAGE plpgsql SECURITY DEFINER
        SET search_path=pg_catalog,public AS $$
        BEGIN
          IF substring(p_fetch_run_id::text,15,1)<>'7'
             OR p_now NOT BETWEEN clock_timestamp()-interval '5 minutes'
                              AND clock_timestamp()+interval '5 minutes'
             OR p_leased_until<=p_now
             OR p_leased_until>p_now+interval '15 minutes' THEN
            RAISE EXCEPTION 'activation lease input is invalid';
          END IF;
          RETURN QUERY
          WITH existing_success AS MATERIALIZED (
            SELECT activation.id AS outbox_id,activation.source_id,
                   run.id AS fetch_run_id,false AS needs_dispatch
              FROM source_activation_outbox activation
              JOIN fetch_run run
                ON run.source_id=activation.source_id
               AND run.idempotency_key='source-activation:' || activation.id::text
               AND run.run_origin='SCHEDULED'
               AND run.execution_domain='PRODUCTION'
             WHERE activation.id=p_outbox_id
               AND activation.status='SUCCEEDED'
          ), eligible AS MATERIALIZED (
            SELECT activation.id AS outbox_id,activation.source_id,
                   activation.stream_id,source_row.current_policy_version_id,
                   source_row.current_connector_config_version_id,
                   schedule.id AS schedule_id,connector.id AS source_connector_id
              FROM source_activation_outbox activation
              JOIN source source_row ON source_row.id=activation.source_id
              JOIN source_stream stream
                ON stream.id=activation.stream_id
               AND stream.source_id=source_row.id
              JOIN fetch_schedule schedule ON schedule.source_id=source_row.id
               AND (stream.schedule_id IS NULL OR stream.schedule_id=schedule.id)
              JOIN LATERAL (
                SELECT source_connector.id FROM source_connector
                 WHERE source_connector.source_id=source_row.id
                 ORDER BY source_connector.created_at DESC LIMIT 1
              ) connector ON true
              JOIN source_policy_version policy
                ON policy.id=source_row.current_policy_version_id
              JOIN connector_config_version config
                ON config.id=source_row.current_connector_config_version_id
             WHERE activation.id=p_outbox_id
               AND activation.attempt_count<10
               AND (
                 (activation.status IN ('PENDING','FAILED')
                  AND activation.available_at<=p_now)
                 OR (activation.status='PROCESSING'
                     AND activation.leased_until<=p_now)
               )
               AND source_row.lifecycle_state='ACTIVE'
               AND stream.status='ACTIVE' AND schedule.status='ACTIVE'
               AND source_policy_compliance_current(source_row.id,policy.id,p_now)
               AND config.validation_status='VALID'
               AND EXISTS (
                 SELECT 1 FROM source_governance_decision decision
                  WHERE decision.source_id=source_row.id
                    AND decision.policy_version_id=policy.id
                    AND decision.connector_config_version_id=config.id
                    AND decision.trial_run_id=source_row.current_trial_run_id
                    AND decision.decision_type='PRODUCTION_APPROVAL'
                    AND decision.outcome='APPROVED'
                    AND (decision.valid_until IS NULL OR decision.valid_until>p_now)
               )
             FOR UPDATE OF activation
          ), production_run AS (
            INSERT INTO fetch_run(
              id,source_connector_id,trigger,status,started_at,discovered_count,
              fetched_count,failed_count,request_id,execution_domain,source_id,
              schedule_id,policy_version_id,connector_config_version_id,
              idempotency_key,attempt_count,run_origin
            )
            SELECT p_fetch_run_id,eligible.source_connector_id,'SCHEDULED',
                   'PENDING_DISPATCH',p_now,0,0,0,
                   'source-activation:' || eligible.outbox_id::text,'PRODUCTION',
                   eligible.source_id,eligible.schedule_id,
                   eligible.current_policy_version_id,
                   eligible.current_connector_config_version_id,
                   'source-activation:' || eligible.outbox_id::text,0,'SCHEDULED'
              FROM eligible
            ON CONFLICT (idempotency_key) DO UPDATE SET
              idempotency_key=EXCLUDED.idempotency_key
            RETURNING fetch_run.id,fetch_run.source_id
          ), activation_state AS (
            UPDATE source_activation_outbox activation
               SET status='PROCESSING',
                   attempt_count=activation.attempt_count+1,
                   leased_until=p_leased_until
              FROM eligible,production_run
             WHERE activation.id=eligible.outbox_id
               AND production_run.source_id=eligible.source_id
            RETURNING activation.id AS outbox_id,activation.source_id,
                      production_run.id AS fetch_run_id,true AS needs_dispatch
          )
          SELECT success.outbox_id,success.source_id,
                 success.fetch_run_id,success.needs_dispatch
            FROM existing_success success
          UNION ALL
          SELECT state.outbox_id,state.source_id,
                 state.fetch_run_id,state.needs_dispatch
            FROM activation_state state
          LIMIT 1;
        END $$
        """
    )
    op.execute(
        r"""
        CREATE FUNCTION complete_source_activation(
          p_outbox_id uuid,p_fetch_run_id uuid,p_source_id uuid,
          p_completed_at timestamptz
        ) RETURNS uuid
        LANGUAGE plpgsql SECURITY DEFINER
        SET search_path=pg_catalog,public AS $$
        DECLARE v_outbox_id uuid;
        BEGIN
          IF p_completed_at NOT BETWEEN clock_timestamp()-interval '5 minutes'
                                      AND clock_timestamp()+interval '5 minutes' THEN
            RAISE EXCEPTION 'activation completion input is invalid';
          END IF;
          WITH authoritative_run AS (
            SELECT run.id,run.source_id,run.status
              FROM fetch_run run
             WHERE run.id=p_fetch_run_id AND run.source_id=p_source_id
               AND run.run_origin='SCHEDULED'
               AND run.execution_domain='PRODUCTION'
               AND run.idempotency_key='source-activation:' || p_outbox_id::text
          ), marked AS (
            UPDATE fetch_run run
               SET status=CASE WHEN run.status='PENDING_DISPATCH'
                               THEN 'DISPATCHED' ELSE run.status END,
                   heartbeat_at=CASE WHEN run.status='PENDING_DISPATCH'
                                     THEN p_completed_at ELSE run.heartbeat_at END
              FROM authoritative_run
             WHERE run.id=authoritative_run.id
               AND run.status IN (
                 'PENDING_DISPATCH','DISPATCHED','RUNNING','RETRY_WAIT',
                 'SUCCEEDED','NOT_MODIFIED'
               )
            RETURNING run.id,run.source_id
          ), completed AS (
            UPDATE source_activation_outbox activation
               SET status='SUCCEEDED',
                   processed_at=COALESCE(activation.processed_at,p_completed_at),
                   leased_until=NULL
              FROM marked
             WHERE activation.id=p_outbox_id
               AND activation.source_id=marked.source_id
               AND activation.status IN ('PROCESSING','SUCCEEDED')
            RETURNING activation.id
          )
          SELECT id INTO v_outbox_id FROM completed;
          RETURN v_outbox_id;
        END $$
        """
    )
    op.execute(
        r"""
        CREATE FUNCTION reserve_source_provider_usage(
          p_provider text,p_utc_month text,p_reserved_at timestamptz
        ) RETURNS TABLE(
          request_count integer,cost_micrormb bigint,alert_required boolean
        )
        LANGUAGE plpgsql SECURITY DEFINER
        SET search_path=pg_catalog,public AS $$
        DECLARE
          v_policy source_provider_budget_policy%ROWTYPE;
          v_usage source_provider_usage%ROWTYPE;
          v_charge bigint;
          v_alert_required boolean;
        BEGIN
          IF p_provider<>'BAIDU_SEARCH'
             OR p_utc_month !~ '^[0-9]{4}-(0[1-9]|1[0-2])$'
             OR p_utc_month<>to_char(p_reserved_at AT TIME ZONE 'UTC','YYYY-MM')
             OR p_reserved_at NOT BETWEEN clock_timestamp()-interval '5 minutes'
                                      AND clock_timestamp()+interval '5 minutes' THEN
            RAISE EXCEPTION 'provider budget reservation input is invalid';
          END IF;
          SELECT * INTO v_policy
            FROM source_provider_budget_policy policy
           WHERE policy.provider=p_provider AND policy.enabled
           FOR SHARE;
          IF NOT FOUND THEN
            RETURN;
          END IF;
          INSERT INTO source_provider_usage(
            provider,utc_month,request_count,cost_micrormb,
            monthly_cap_micrormb,alerted_at,updated_at
          ) VALUES (
            v_policy.provider,p_utc_month,0,0,v_policy.monthly_cap_micrormb,
            NULL,p_reserved_at
          ) ON CONFLICT (provider,utc_month) DO NOTHING;
          SELECT * INTO v_usage
            FROM source_provider_usage usage
           WHERE usage.provider=p_provider AND usage.utc_month=p_utc_month
           FOR UPDATE;
          IF v_usage.monthly_cap_micrormb<>v_policy.monthly_cap_micrormb THEN
            RAISE EXCEPTION 'provider budget policy drift requires administrative repair';
          END IF;
          v_charge:=CASE
            WHEN v_usage.request_count<v_policy.free_calls_per_month THEN 0
            ELSE v_policy.cost_per_call_micrormb END;
          IF v_usage.cost_micrormb+v_charge>v_policy.monthly_cap_micrormb THEN
            RETURN;
          END IF;
          v_alert_required:=
            v_usage.alerted_at IS NULL
            AND (v_usage.cost_micrormb+v_charge)*10000
                >= v_policy.monthly_cap_micrormb*v_policy.alert_threshold_bps;
          UPDATE source_provider_usage usage
             SET request_count=v_usage.request_count+1,
                 cost_micrormb=v_usage.cost_micrormb+v_charge,
                 alerted_at=CASE WHEN v_alert_required
                                 THEN p_reserved_at ELSE v_usage.alerted_at END,
                 updated_at=p_reserved_at
           WHERE usage.provider=p_provider AND usage.utc_month=p_utc_month;
          request_count:=v_usage.request_count+1;
          cost_micrormb:=v_usage.cost_micrormb+v_charge;
          alert_required:=v_alert_required;
          RETURN NEXT;
        END $$
        """
    )
    for signature in WORKER_COMMAND_SIGNATURES:
        op.execute(f"REVOKE ALL ON FUNCTION {signature} FROM PUBLIC")
        op.execute(f"GRANT EXECUTE ON FUNCTION {signature} TO srbg_worker_role")


def _configure_roles() -> None:
    tables = ",".join(SOURCE_AUTOMATION_TABLES)
    op.execute(f"REVOKE ALL ON {tables} FROM PUBLIC")
    op.execute(
        f"REVOKE ALL ON {tables} FROM srbg_api_role,srbg_worker_role,"
        "srbg_model_role,srbg_projection_reader"
    )
    op.execute(f"GRANT SELECT ON {tables} TO srbg_api_role")


def _restore_round17_runtime_authority() -> None:
    """Restore the 0017c claim function before removing Round18 policy helpers."""

    op.execute(
        """
        CREATE OR REPLACE FUNCTION claim_due_fetch_schedule(
          p_now timestamptz,p_lease_until timestamptz,p_token uuid
        ) RETURNS TABLE(schedule_id uuid,source_id uuid)
        LANGUAGE sql SECURITY DEFINER
        SET search_path=pg_catalog,public AS $$
          WITH due AS (
            SELECT schedule.id,schedule.source_id
              FROM fetch_schedule schedule
              JOIN source source_row ON source_row.id=schedule.source_id
              JOIN source_policy_version policy
                ON policy.id=source_row.current_policy_version_id
              JOIN connector_config_version config
                ON config.id=source_row.current_connector_config_version_id
             WHERE schedule.status='ACTIVE'
               AND source_row.lifecycle_state='ACTIVE'
               AND policy.status='APPROVED'
               AND policy.valid_from<=p_now AND policy.valid_until>p_now
               AND config.validation_status='VALID'
               AND schedule.next_run_at<=p_now
               AND schedule.requests_used<schedule.daily_request_budget
               AND schedule.bytes_used<schedule.daily_byte_budget
               AND (schedule.leased_until IS NULL OR schedule.leased_until<=p_now)
               AND (
                 schedule.circuit_state='CLOSED'
                 OR (
                   schedule.circuit_state='OPEN'
                   AND schedule.circuit_open_until<=p_now
                 )
               )
               AND EXISTS (
                 SELECT 1 FROM source_governance_decision decision
                  WHERE decision.source_id=source_row.id
                    AND decision.decision_type='PRODUCTION_APPROVAL'
                    AND decision.outcome='APPROVED'
                    AND (decision.valid_until IS NULL OR decision.valid_until>p_now)
               )
             ORDER BY schedule.next_run_at,schedule.id
             LIMIT 1 FOR UPDATE SKIP LOCKED
          )
          UPDATE fetch_schedule schedule
             SET lease_token=p_token,leased_until=p_lease_until,
                 circuit_state=CASE WHEN schedule.circuit_state='OPEN'
                                    THEN 'HALF_OPEN' ELSE schedule.circuit_state END
            FROM due WHERE schedule.id=due.id
          RETURNING schedule.id,schedule.source_id
        $$
        """
    )
    signature = "claim_due_fetch_schedule(timestamptz,timestamptz,uuid)"
    op.execute(f"REVOKE ALL ON FUNCTION {signature} FROM PUBLIC")
    op.execute(f"GRANT EXECUTE ON FUNCTION {signature} TO srbg_worker_role")


def downgrade() -> None:
    bind = op.get_bind()
    candidate_count = bind.execute(sa.text("SELECT count(*) FROM source_candidate")).scalar_one()
    decision_count = bind.execute(
        sa.text("SELECT count(*) FROM source_candidate_decision")
    ).scalar_one()
    bundle_count = bind.execute(
        sa.text("SELECT count(*) FROM source_qualification_bundle")
    ).scalar_one()
    if candidate_count or decision_count or bundle_count:
        raise RuntimeError(
            "ROUND18_DOWNGRADE_BLOCKED: source discovery, qualification or decision facts exist"
        )
    # Explicit guards are kept visible for offline evidence scanners.
    op.execute(
        """
        DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM source_candidate LIMIT 1) THEN
            RAISE EXCEPTION 'ROUND18_DOWNGRADE_BLOCKED';
          END IF;
          IF EXISTS (SELECT 1 FROM source_candidate_decision LIMIT 1) THEN
            RAISE EXCEPTION 'ROUND18_DOWNGRADE_BLOCKED';
          END IF;
          IF EXISTS (SELECT 1 FROM source_qualification_bundle LIMIT 1) THEN
            RAISE EXCEPTION 'ROUND18_DOWNGRADE_BLOCKED';
          END IF;
        END $$
        """
    )
    for signature in WORKER_COMMAND_SIGNATURES:
        op.execute(f"DROP FUNCTION IF EXISTS {signature}")
    op.execute(
        "DROP FUNCTION IF EXISTS activate_qualified_candidate(uuid,text,text,text,text,text,text,uuid,uuid,uuid,uuid,uuid,uuid,uuid,uuid,timestamptz)"
    )
    op.execute(
        "DROP FUNCTION IF EXISTS request_source_qualification("
        "uuid,uuid,text,uuid,text,text,uuid,timestamptz)"
    )
    op.execute(
        "DROP FUNCTION IF EXISTS prepare_source_candidate_for_qualification("
        "uuid,uuid,uuid,timestamptz)"
    )
    op.execute(
        "DROP FUNCTION IF EXISTS register_discovered_source_candidate("
        "uuid,uuid,text,text,text,text,text,text,text[],text[],text[],uuid,text,text,uuid,timestamptz)"
    )
    op.execute("DROP FUNCTION IF EXISTS source_automation_derived_uuid(uuid,text)")
    raw_args = (
        "uuid,uuid,uuid,uuid,text,text,text,text,bigint,text,text,text,text,text,text,"
        "jsonb,integer,text,text,timestamptz"
    )
    document_args = (
        "uuid,uuid,uuid,uuid,uuid,uuid,uuid,uuid,uuid,text,text,text,text,text,timestamptz"
    )
    op.execute(f"DROP FUNCTION IF EXISTS record_scheduled_source_raw({raw_args})")
    op.execute(f"DROP FUNCTION IF EXISTS record_scheduled_source_document({document_args})")
    op.execute(
        f"ALTER FUNCTION record_scheduled_source_raw_round17({raw_args}) "
        "RENAME TO record_scheduled_source_raw"
    )
    op.execute(
        f"ALTER FUNCTION record_scheduled_source_document_round17({document_args}) "
        "RENAME TO record_scheduled_source_document"
    )
    _restore_round17_runtime_authority()
    op.execute("DROP TRIGGER IF EXISTS trg_source_automation_lifecycle_authority ON source")
    op.execute("DROP FUNCTION IF EXISTS enforce_source_automation_lifecycle_authority()")
    op.execute("DROP FUNCTION IF EXISTS source_private_evidence_capture_allowed(jsonb)")
    op.execute("DROP FUNCTION IF EXISTS source_policy_compliance_current(uuid,uuid,timestamptz)")
    op.execute("DROP FUNCTION IF EXISTS prevent_source_automation_fact_mutation() CASCADE")
    op.drop_constraint("fk_source_candidate_current_bundle", "source_candidate", type_="foreignkey")
    for table in reversed(SOURCE_AUTOMATION_TABLES):
        op.drop_table(table)
