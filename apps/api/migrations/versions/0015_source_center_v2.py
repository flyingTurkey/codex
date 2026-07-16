"""Round 15 source center V2 governance and connector versioning.

Revision ID: 0015_source_center_v2
Revises: 0014b_event_consumer_switch

The V1 ``state`` and ``enabled`` columns are retained as read-only compatibility
projections.  They are never used to grant V2 production authorization.

In other words, legacy state/enabled are retained solely as migration evidence.
"""

# ruff: noqa: E501, S608 -- static policy DDL remains auditable inline.

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import UTC, datetime
from hashlib import sha256

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0015_source_center_v2"
down_revision: str | Sequence[str] | None = "0014b_event_consumer_switch"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ROUND15_MIGRATION_RULE_VERSION = "round15-lifecycle-v1"
ROUND15_TABLES = (
    "connector_definition",
    "connector_config_version",
    "source_policy_version",
    "source_governance_decision",
    "source_trial_run",
    "source_trial_run_result",
    "source_fixture_replay_result",
    "raw_object_capture",
    "source_trial_rejected_raw_attempt",
    "document_attachment_attempt",
    "source_authority_assessment",
    "source_independence_assessment",
    "source_lifecycle_event",
    "source_migration_snapshot",
)

_LIFECYCLE_STATES = "'CANDIDATE','COMPLIANCE_REVIEW','TRIAL','ACTIVE','PAUSED','RETIRED'"
_JSON = postgresql.JSONB(astext_type=sa.Text())
_TEXT_ARRAY = postgresql.ARRAY(sa.Text())


def _uuid() -> postgresql.UUID:
    return postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    _add_source_v2_columns()
    _create_connector_tables()
    _create_governance_tables()
    _add_execution_domain_boundaries()
    _expand_fixture_document_kinds()
    _create_rejected_trial_attempt_table()
    _create_attachment_attempt_table()
    _migrate_legacy_lifecycle()
    _create_immutable_boundaries()
    _create_raw_security_boundaries()
    _create_document_version_execution_domain_boundary()
    _create_source_command_boundary()
    _configure_source_roles()


def _add_source_v2_columns() -> None:
    op.add_column(
        "source",
        sa.Column("lifecycle_state", sa.String(30), nullable=False, server_default="CANDIDATE"),
    )
    op.add_column("source", sa.Column("trial_kind", sa.String(30)))
    op.add_column("source", sa.Column("registered_by", _uuid()))
    op.add_column("source", sa.Column("governance_owner_id", _uuid()))
    for name in (
        "country_codes",
        "region_codes",
        "language_tags",
        "industries",
        "content_domains",
        "declared_roles",
    ):
        op.add_column(
            "source",
            sa.Column(name, _TEXT_ARRAY, nullable=False, server_default=sa.text("ARRAY[]::text[]")),
        )
    op.add_column("source", sa.Column("current_policy_version_id", _uuid()))
    op.add_column("source", sa.Column("current_connector_config_version_id", _uuid()))
    op.add_column("source", sa.Column("current_trial_run_id", _uuid()))
    op.create_check_constraint(
        "ck_source_lifecycle_state_v2",
        "source",
        f"lifecycle_state IN ({_LIFECYCLE_STATES})",
    )
    op.create_check_constraint(
        "ck_source_trial_kind_v2",
        "source",
        "trial_kind IS NULL OR trial_kind IN ('FIXTURE_REPLAY','LIVE_TRIAL')",
    )
    op.create_check_constraint(
        "ck_source_non_trial_has_no_fixture_kind",
        "source",
        "lifecycle_state = 'TRIAL' OR trial_kind IS NULL",
    )
    op.create_index("ix_source_lifecycle_state_v2", "source", ["lifecycle_state"])


def _create_connector_tables() -> None:
    op.create_table(
        "connector_definition",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("connector_type", sa.String(40), nullable=False),
        sa.Column("definition_version", sa.String(30), nullable=False),
        sa.Column("schema_version", sa.String(30), nullable=False),
        sa.Column("schema_document", _JSON, nullable=False),
        sa.Column("schema_sha256", sa.String(64), nullable=False),
        sa.Column("executor_key", sa.String(100), nullable=False),
        sa.Column("capabilities", _TEXT_ARRAY, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "connector_type", "definition_version", name="uq_connector_definition_version"
        ),
        sa.UniqueConstraint("executor_key", name="uq_connector_definition_executor"),
        sa.CheckConstraint(
            "connector_type IN ('RSS_ATOM','JSON_API','SITEMAP','LIST_DETAIL','DIRECT_PDF','MANUAL_IMPORT')",
            name="ck_connector_definition_type",
        ),
        sa.CheckConstraint(
            "schema_sha256 ~ '^[0-9a-f]{64}$'", name="ck_connector_definition_schema_hash"
        ),
    )
    op.create_table(
        "connector_config_version",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column(
            "source_id", _uuid(), sa.ForeignKey("source.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column(
            "connector_definition_id",
            _uuid(),
            sa.ForeignKey("connector_definition.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("policy_version_id", _uuid(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("config_document", _JSON, nullable=False),
        sa.Column("config_sha256", sa.String(64), nullable=False),
        sa.Column("allowed_hosts", _TEXT_ARRAY, nullable=False),
        sa.Column("credential_ref", sa.String(255)),
        sa.Column("validation_status", sa.String(20), nullable=False),
        sa.Column("validation_reason_codes", _TEXT_ARRAY, nullable=False),
        sa.Column("supersedes_id", _uuid()),
        sa.Column("created_by", _uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("source_id", "version_number", name="uq_connector_config_version"),
        sa.UniqueConstraint("source_id", "config_sha256", name="uq_connector_config_hash"),
        sa.UniqueConstraint("id", "source_id", name="uq_connector_config_id_source"),
        sa.CheckConstraint("version_number > 0", name="ck_connector_config_version_positive"),
        sa.CheckConstraint("config_sha256 ~ '^[0-9a-f]{64}$'", name="ck_connector_config_hash"),
        sa.CheckConstraint(
            "validation_status IN ('VALID','INVALID')", name="ck_connector_config_validation"
        ),
        sa.CheckConstraint(
            "credential_ref IS NULL OR credential_ref ~ "
            "'^vault://source-connectors/[A-Za-z0-9][A-Za-z0-9/_-]{0,190}$'",
            name="ck_connector_config_credential_ref",
        ),
        sa.CheckConstraint(
            "NOT (config_document ? 'credential_ref')",
            name="ck_connector_config_secret_ref_separate",
        ),
    )
    op.create_foreign_key(
        "fk_connector_config_supersedes",
        "connector_config_version",
        "connector_config_version",
        ["supersedes_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    _seed_connector_definitions()


def _seed_connector_definitions() -> None:
    expected = {
        "RSS_ATOM": "4691b104889eeb16f6cb006d8284b6a8f5bb4b0c58ea2fd331ddf63f7eb2830d",
        "JSON_API": "73b72a68d11b0da0698871e34f80534b1386d6ce7500a27b57f3c3792ed38447",
        "SITEMAP": "7965a06972afb19af66f82ccbb5f21b7f4e88be33d64cc3548cff9cb62921ae5",
        "LIST_DETAIL": "d6c892a10eb61d372e44f1156f48676fdd549027dcd91b20aaff4e1f01938ef6",
        "DIRECT_PDF": "daa3e6ded77fd467da20f21961b84177eb6b84a2bd5e60adf45ab110012883b8",
        "MANUAL_IMPORT": "2abc649e1f15fbb452e27f452fca1eb27e5538bac2e7c07eaab42bd6345c860d",
    }
    capabilities = {
        "RSS_ATOM": ["DISCOVERY", "FETCH"],
        "JSON_API": ["DISCOVERY", "FETCH"],
        "SITEMAP": ["DISCOVERY", "FETCH"],
        "LIST_DETAIL": ["DISCOVERY", "FETCH"],
        "DIRECT_PDF": ["DIRECT_FETCH", "PDF"],
        "MANUAL_IMPORT": ["MANUAL_URL", "MANUAL_FILE"],
    }
    definitions = _connector_schema_documents()
    rows: list[dict[str, object]] = []
    for index, connector_type in enumerate(expected, 1):
        document = definitions[connector_type]
        digest = sha256(
            json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        if digest != expected[connector_type]:
            raise RuntimeError(f"connector definition hash drift: {connector_type}")
        rows.append(
            {
                "id": f"019b1500-0000-7000-8000-{index:012d}",
                "connector_type": connector_type,
                "definition_version": "1.0.0",
                "schema_version": "2020-12",
                "schema_document": document,
                "schema_sha256": digest,
                "executor_key": f"builtin:{connector_type.lower()}:v1",
                "capabilities": capabilities[connector_type],
            }
        )
    table = sa.table(
        "connector_definition",
        sa.column("id", _uuid()),
        sa.column("connector_type", sa.String()),
        sa.column("definition_version", sa.String()),
        sa.column("schema_version", sa.String()),
        sa.column("schema_document", _JSON),
        sa.column("schema_sha256", sa.String()),
        sa.column("executor_key", sa.String()),
        sa.column("capabilities", _TEXT_ARRAY),
        sa.column("created_at", sa.DateTime(timezone=True)),
    )
    op.bulk_insert(
        table,
        [row | {"created_at": datetime.now(UTC)} for row in rows],
        multiinsert=False,
    )


def _connector_schema_documents() -> dict[str, dict[str, object]]:
    schema_uri = "https://json-schema.org/draft/2020-12/schema"
    credential_pattern = r"^vault://source-connectors/[A-Za-z0-9][A-Za-z0-9/_-]{0,190}$"

    def url() -> dict[str, object]:
        return {"type": "string", "minLength": 8, "maxLength": 2048}

    def selector() -> dict[str, object]:
        return {"type": "string", "minLength": 1, "maxLength": 100}

    def pointer() -> dict[str, object]:
        return {"type": "string", "minLength": 1, "maxLength": 300}

    def object_schema(
        connector_type: str,
        properties: dict[str, object],
        required: list[str],
        all_of: list[dict[str, object]] | None = None,
    ) -> dict[str, object]:
        document: dict[str, object] = {
            "$schema": schema_uri,
            "$id": (f"https://schemas.srbg.local/connectors/{connector_type.lower()}/1.0.0"),
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "allowed_hosts": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": 32,
                    "uniqueItems": True,
                    "items": {"type": "string", "minLength": 1, "maxLength": 253},
                },
                "credential_ref": {
                    "type": "string",
                    "pattern": credential_pattern,
                    "maxLength": 220,
                },
            }
            | properties,
            "required": ["allowed_hosts", *required],
        }
        if all_of:
            document["allOf"] = all_of
        return document

    return {
        "RSS_ATOM": object_schema("RSS_ATOM", {"feed_url": url()}, ["feed_url"]),
        "JSON_API": object_schema(
            "JSON_API",
            {
                "endpoint_url": url(),
                "items_pointer": pointer(),
                "field_pointers": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "external_id": pointer(),
                        "url": pointer(),
                        "title": pointer(),
                        "published_at": pointer(),
                    },
                    "required": ["external_id", "url", "title"],
                },
                "pagination": {"const": "NONE"},
            },
            ["endpoint_url", "items_pointer", "field_pointers", "pagination"],
        ),
        "SITEMAP": object_schema("SITEMAP", {"sitemap_url": url()}, ["sitemap_url"]),
        "LIST_DETAIL": object_schema(
            "LIST_DETAIL",
            {
                "list_url": url(),
                "item_selector": selector(),
                "link_selector": selector(),
                "title_selector": selector(),
                "published_selector": selector(),
            },
            ["list_url", "item_selector", "link_selector", "title_selector"],
        ),
        "DIRECT_PDF": object_schema(
            "DIRECT_PDF",
            {
                "document_urls": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": 100,
                    "uniqueItems": True,
                    "items": url(),
                }
            },
            ["document_urls"],
        ),
        "MANUAL_IMPORT": object_schema(
            "MANUAL_IMPORT",
            {
                "url_import_enabled": {"type": "boolean"},
                "file_import_enabled": {"type": "boolean"},
                "allowed_file_types": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": 3,
                    "uniqueItems": True,
                    "items": {"enum": ["HTML", "PDF", "ZIP"]},
                },
            },
            ["url_import_enabled", "file_import_enabled", "allowed_file_types"],
            [
                {
                    "anyOf": [
                        {"properties": {"url_import_enabled": {"const": True}}},
                        {"properties": {"file_import_enabled": {"const": True}}},
                    ]
                }
            ],
        ),
    }


def _create_governance_tables() -> None:
    op.create_table(
        "source_policy_version",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column(
            "source_id", _uuid(), sa.ForeignKey("source.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column("schema_version", sa.String(20), nullable=False),
        sa.Column("policy_version", sa.String(50), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="PENDING_REVIEW"),
        sa.Column("document", _JSON, nullable=False),
        sa.Column("document_sha256", sa.String(64), nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=False),
        sa.Column("submitted_by", _uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("source_id", "policy_version", name="uq_source_policy_v2_version"),
        sa.UniqueConstraint("id", "source_id", name="uq_source_policy_v2_id_source"),
        sa.CheckConstraint(
            "status IN ('PENDING_REVIEW','APPROVED','REJECTED','EXPIRED','REVOKED')",
            name="ck_source_policy_v2_status",
        ),
        sa.CheckConstraint("document_sha256 ~ '^[0-9a-f]{64}$'", name="ck_source_policy_v2_hash"),
        sa.CheckConstraint("valid_until > valid_from", name="ck_source_policy_v2_window"),
    )
    op.create_foreign_key(
        "fk_connector_config_policy_version",
        "connector_config_version",
        "source_policy_version",
        ["policy_version_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_table(
        "source_trial_run",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column(
            "source_id", _uuid(), sa.ForeignKey("source.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column("kind", sa.String(30), nullable=False),
        sa.Column("execution_domain", sa.String(20), nullable=False),
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
        sa.Column("authorization_decision_id", _uuid()),
        sa.Column("requested_by", _uuid(), nullable=False),
        sa.Column("request_reason", sa.String(500), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("kind IN ('FIXTURE_REPLAY','LIVE_TRIAL')", name="ck_trial_run_kind"),
        sa.CheckConstraint("execution_domain IN ('FIXTURE','TRIAL')", name="ck_trial_run_domain"),
        sa.CheckConstraint(
            "(kind = 'FIXTURE_REPLAY' AND execution_domain = 'FIXTURE') OR "
            "(kind = 'LIVE_TRIAL' AND execution_domain = 'TRIAL')",
            name="ck_trial_run_isolation",
        ),
        sa.UniqueConstraint("id", "source_id", name="uq_source_trial_run_id_source"),
    )
    op.create_table(
        "source_trial_run_result",
        sa.Column(
            "trial_run_id",
            _uuid(),
            sa.ForeignKey("source_trial_run.id", ondelete="RESTRICT"),
            primary_key=True,
        ),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("quality_summary", _JSON, nullable=False),
        sa.Column("raw_namespace", sa.String(255), nullable=False),
        sa.Column("completed_by", _uuid(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('SUCCEEDED','FAILED','CANCELLED')", name="ck_trial_result_status"
        ),
        sa.CheckConstraint(
            "raw_namespace LIKE 'fixture/%' OR raw_namespace LIKE 'trial/%'",
            name="ck_trial_result_namespace",
        ),
    )
    op.create_table(
        "source_fixture_replay_result",
        sa.Column("trial_run_id", _uuid(), primary_key=True),
        sa.Column("source_id", _uuid(), nullable=False),
        sa.Column("connector_config_version_id", _uuid(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("reason_code", sa.String(100), nullable=False),
        sa.Column("raw_capture_count", sa.Integer(), nullable=False),
        sa.Column("document_count", sa.Integer(), nullable=False),
        sa.Column("transport_call_count", sa.Integer(), nullable=False),
        sa.Column("evaluated_by", _uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["trial_run_id", "source_id"],
            ["source_trial_run.id", "source_trial_run.source_id"],
            name="fk_fixture_replay_trial_source",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["connector_config_version_id", "source_id"],
            ["connector_config_version.id", "connector_config_version.source_id"],
            name="fk_fixture_replay_config_source",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "status IN ('PASSED','FAILED')", name="ck_fixture_replay_status"
        ),
        sa.CheckConstraint(
            "reason_code ~ '^[A-Z0-9_]{1,100}$'", name="ck_fixture_replay_reason_code"
        ),
        sa.CheckConstraint(
            "raw_capture_count >= 0 AND document_count >= 0 "
            "AND transport_call_count >= 0",
            name="ck_fixture_replay_counts_nonnegative",
        ),
        sa.CheckConstraint(
            "status <> 'PASSED' OR (raw_capture_count > 0 AND document_count > 0)",
            name="ck_fixture_replay_passed_has_output",
        ),
    )
    op.create_table(
        "source_governance_decision",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column(
            "source_id", _uuid(), sa.ForeignKey("source.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column("decision_type", sa.String(40), nullable=False),
        sa.Column("outcome", sa.String(20), nullable=False),
        sa.Column(
            "policy_version_id",
            _uuid(),
            sa.ForeignKey("source_policy_version.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("connector_config_version_id", _uuid()),
        sa.Column("trial_run_id", _uuid()),
        sa.Column("submitted_by", _uuid(), nullable=False),
        sa.Column("decided_by", _uuid(), nullable=False),
        sa.Column("reason", sa.String(500), nullable=False),
        sa.Column("valid_until", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "decision_type IN ('COMPLIANCE','LIVE_TRIAL_AUTHORIZATION','PRODUCTION_APPROVAL')",
            name="ck_source_governance_decision_type",
        ),
        sa.CheckConstraint("outcome IN ('APPROVED','REJECTED')", name="ck_governance_outcome"),
        sa.CheckConstraint("submitted_by <> decided_by", name="ck_governance_separation"),
        sa.CheckConstraint(
            "decision_type <> 'PRODUCTION_APPROVAL' OR "
            "(connector_config_version_id IS NOT NULL AND trial_run_id IS NOT NULL)",
            name="ck_production_decision_evidence",
        ),
        sa.UniqueConstraint("id", "source_id", name="uq_governance_decision_id_source"),
    )
    op.create_foreign_key(
        "fk_governance_connector_config",
        "source_governance_decision",
        "connector_config_version",
        ["connector_config_version_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_governance_trial_run",
        "source_governance_decision",
        "source_trial_run",
        ["trial_run_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_trial_authorization_decision",
        "source_trial_run",
        "source_governance_decision",
        ["authorization_decision_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    for name, source_table, referent_table, local_columns in (
        (
            "fk_connector_config_policy_same_source",
            "connector_config_version",
            "source_policy_version",
            ["policy_version_id", "source_id"],
        ),
        (
            "fk_trial_policy_same_source",
            "source_trial_run",
            "source_policy_version",
            ["policy_version_id", "source_id"],
        ),
        (
            "fk_trial_config_same_source",
            "source_trial_run",
            "connector_config_version",
            ["connector_config_version_id", "source_id"],
        ),
        (
            "fk_governance_policy_same_source",
            "source_governance_decision",
            "source_policy_version",
            ["policy_version_id", "source_id"],
        ),
        (
            "fk_governance_config_same_source",
            "source_governance_decision",
            "connector_config_version",
            ["connector_config_version_id", "source_id"],
        ),
        (
            "fk_governance_trial_same_source",
            "source_governance_decision",
            "source_trial_run",
            ["trial_run_id", "source_id"],
        ),
        (
            "fk_trial_authorization_same_source",
            "source_trial_run",
            "source_governance_decision",
            ["authorization_decision_id", "source_id"],
        ),
    ):
        op.create_foreign_key(
            name,
            source_table,
            referent_table,
            local_columns,
            ["id", "source_id"],
            ondelete="RESTRICT",
        )
    _create_source_assessment_tables()
    _create_source_history_tables()
    op.create_foreign_key(
        "fk_source_current_policy_v2",
        "source",
        "source_policy_version",
        ["current_policy_version_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_source_current_connector_config",
        "source",
        "connector_config_version",
        ["current_connector_config_version_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_source_current_trial_run",
        "source",
        "source_trial_run",
        ["current_trial_run_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    for table, columns in (
        ("source_policy_version", ["source_id", "created_at"]),
        ("connector_config_version", ["source_id", "created_at"]),
        ("source_trial_run", ["source_id", "created_at"]),
        ("source_governance_decision", ["source_id", "created_at"]),
    ):
        op.create_index(f"ix_{table}_source_created", table, columns)


def _create_source_assessment_tables() -> None:
    op.create_table(
        "source_authority_assessment",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column(
            "source_id", _uuid(), sa.ForeignKey("source.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column("authority_level", sa.String(10), nullable=False),
        sa.Column("rule_version", sa.String(50), nullable=False),
        sa.Column("reason_codes", _TEXT_ARRAY, nullable=False),
        sa.Column("evidence_refs", _TEXT_ARRAY, nullable=False),
        sa.Column("assessed_by", _uuid(), nullable=False),
        sa.Column("assessed_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "authority_level IN ('A0','A1','B1','B2','C1','C2','UNKNOWN')",
            name="ck_source_authority_level_v2",
        ),
    )


def _add_execution_domain_boundaries() -> None:
    op.add_column(
        "fetch_run",
        sa.Column("execution_domain", sa.String(20), nullable=False, server_default="LEGACY"),
    )
    op.add_column(
        "fetch_record",
        sa.Column("execution_domain", sa.String(20), nullable=False, server_default="LEGACY"),
    )
    op.add_column(
        "document_version",
        sa.Column("execution_domain", sa.String(20), nullable=False, server_default="LEGACY"),
    )
    for table_name in ("fetch_run", "fetch_record", "document_version"):
        op.create_check_constraint(
            f"ck_{table_name}_execution_domain",
            table_name,
            "execution_domain IN ('LEGACY','FIXTURE','TRIAL','PRODUCTION')",
        )
    op.execute(
        "UPDATE fetch_run SET execution_domain = CASE "
        "WHEN trigger = 'FIXTURE' THEN 'FIXTURE' ELSE 'LEGACY' END"
    )
    op.execute(
        """
        UPDATE fetch_record record
           SET execution_domain = run.execution_domain
          FROM fetch_run run WHERE run.id = record.fetch_run_id
        """
    )
    op.execute(
        "ALTER TABLE document_version DISABLE TRIGGER trg_document_version_immutable"
    )
    op.execute(
        """
        UPDATE document_version version
           SET execution_domain = CASE
             WHEN document.admission_fixture THEN 'FIXTURE' ELSE 'LEGACY' END
          FROM document WHERE document.id = version.document_id
        """
    )
    op.execute(
        "ALTER TABLE document_version ENABLE TRIGGER trg_document_version_immutable"
    )
    op.create_index("ix_fetch_run_execution_domain", "fetch_run", ["execution_domain"])
    op.create_index(
        "ix_document_version_execution_domain", "document_version", ["execution_domain"]
    )

    op.create_table(
        "raw_object_capture",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column(
            "raw_object_id",
            _uuid(),
            sa.ForeignKey("raw_object.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "source_id", _uuid(), sa.ForeignKey("source.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column("fetch_run_id", _uuid(), sa.ForeignKey("fetch_run.id", ondelete="RESTRICT")),
        sa.Column(
            "trial_run_id", _uuid(), sa.ForeignKey("source_trial_run.id", ondelete="RESTRICT")
        ),
        sa.Column("execution_domain", sa.String(20), nullable=False),
        sa.Column("requested_url", sa.String(2048), nullable=False),
        sa.Column("final_url", sa.String(2048), nullable=False),
        sa.Column("redirect_chain", _JSON, nullable=False),
        sa.Column("http_status", sa.Integer(), nullable=False),
        sa.Column("etag", sa.String(500)),
        sa.Column("last_modified", sa.String(500)),
        sa.Column("response_sha256", sa.String(64), nullable=False),
        sa.Column("arrived_after_close", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "execution_domain IN ('LEGACY','FIXTURE','TRIAL','PRODUCTION')",
            name="ck_raw_capture_execution_domain",
        ),
        sa.CheckConstraint(
            "response_sha256 ~ '^[0-9a-f]{64}$'", name="ck_raw_capture_response_hash"
        ),
        sa.CheckConstraint(
            "(execution_domain IN ('FIXTURE','TRIAL') AND trial_run_id IS NOT NULL) OR "
            "(execution_domain IN ('LEGACY','PRODUCTION') AND trial_run_id IS NULL)",
            name="ck_raw_capture_trial_isolation",
        ),
    )
    op.add_column("document_version", sa.Column("raw_object_capture_id", _uuid()))
    op.create_foreign_key(
        "fk_document_version_raw_capture",
        "document_version",
        "raw_object_capture",
        ["raw_object_capture_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_table(
        "source_independence_assessment",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column(
            "source_id", _uuid(), sa.ForeignKey("source.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column("independence_level", sa.String(40), nullable=False),
        sa.Column("rule_version", sa.String(50), nullable=False),
        sa.Column("reason_codes", _TEXT_ARRAY, nullable=False),
        sa.Column("evidence_refs", _TEXT_ARRAY, nullable=False),
        sa.Column("assessed_by", _uuid(), nullable=False),
        sa.Column("assessed_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "independence_level IN ('EDITORIALLY_INDEPENDENT','PARTIALLY_INDEPENDENT','NOT_INDEPENDENT','UNKNOWN')",
            name="ck_source_independence_level_v2",
        ),
    )
    op.create_foreign_key(
        "fk_raw_capture_trial_same_source",
        "raw_object_capture",
        "source_trial_run",
        ["trial_run_id", "source_id"],
        ["id", "source_id"],
        ondelete="RESTRICT",
    )


def _expand_fixture_document_kinds() -> None:
    op.drop_constraint("ck_document_kind", "document", type_="check")
    op.alter_column(
        "document",
        "document_kind",
        existing_type=sa.String(10),
        type_=sa.String(30),
        existing_nullable=False,
    )
    op.create_check_constraint(
        "ck_document_kind",
        "document",
        "document_kind IN ('HTML','PDF','DISCOVERY_XML','DISCOVERY_JSON')",
    )


def _restore_fixture_document_kinds() -> None:
    op.drop_constraint("ck_document_kind", "document", type_="check")
    op.alter_column(
        "document",
        "document_kind",
        existing_type=sa.String(30),
        type_=sa.String(10),
        existing_nullable=False,
    )
    op.create_check_constraint(
        "ck_document_kind",
        "document",
        "document_kind IN ('HTML','PDF')",
    )


def _create_rejected_trial_attempt_table() -> None:
    op.create_table(
        "source_trial_rejected_raw_attempt",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("source_id", _uuid(), nullable=False),
        sa.Column("trial_run_id", _uuid(), nullable=False),
        sa.Column(
            "raw_object_id",
            _uuid(),
            sa.ForeignKey("raw_object.id", ondelete="RESTRICT"),
        ),
        sa.Column("content_sha256", sa.String(64), nullable=False),
        sa.Column("object_key", sa.String(500), nullable=False),
        sa.Column("canonical_url", sa.String(2048), nullable=False),
        sa.Column("canonical_url_sha256", sa.String(64), nullable=False),
        sa.Column("reason_code", sa.String(100), nullable=False),
        sa.Column("arrived_after_close", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("actor_id", _uuid(), nullable=False),
        sa.Column("request_id", sa.String(100), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["trial_run_id", "source_id"],
            ["source_trial_run.id", "source_trial_run.source_id"],
            ondelete="RESTRICT",
            name="fk_rejected_raw_attempt_trial_source",
        ),
        sa.CheckConstraint(
            "canonical_url_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_rejected_raw_attempt_url_hash",
        ),
        sa.CheckConstraint(
            "content_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_rejected_raw_attempt_content_hash",
        ),
    )
    op.create_index(
        "ix_rejected_raw_attempt_source_created",
        "source_trial_rejected_raw_attempt",
        ["source_id", "occurred_at"],
    )


def _create_attachment_attempt_table() -> None:
    op.create_table(
        "document_attachment_attempt",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column(
            "document_version_id",
            _uuid(),
            sa.ForeignKey("document_version.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("content_sha256", sa.String(64), nullable=False),
        sa.Column("object_key", sa.String(500), nullable=False),
        sa.Column("storage_etag", sa.String(200)),
        sa.Column("byte_size", sa.BigInteger(), nullable=False),
        sa.Column("declared_mime", sa.String(100), nullable=False),
        sa.Column("detected_mime", sa.String(100), nullable=False),
        sa.Column("filename_sha256", sa.String(64), nullable=False),
        sa.Column("normalized_path_sha256", sa.String(64), nullable=False),
        sa.Column("canonical_url_sha256", sa.String(64), nullable=False),
        sa.Column("outcome", sa.String(40), nullable=False),
        sa.Column("reason_code", sa.String(100)),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "content_sha256 ~ '^[0-9a-f]{64}$' AND "
            "filename_sha256 ~ '^[0-9a-f]{64}$' AND "
            "normalized_path_sha256 ~ '^[0-9a-f]{64}$' AND "
            "canonical_url_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_attachment_attempt_hashes",
        ),
        sa.CheckConstraint(
            "byte_size BETWEEN 0 AND 536870912",
            name="ck_attachment_attempt_size",
        ),
        sa.CheckConstraint(
            "outcome IN ('RECEIVED','ACCEPTED','REJECTED_CONTEXTUAL',"
            "'QUARANTINED_INTRINSIC','INCONCLUSIVE','REJECTED_SECURITY_HISTORY')",
            name="ck_attachment_attempt_outcome",
        ),
        sa.CheckConstraint(
            "(outcome IN ('RECEIVED','ACCEPTED') AND reason_code IS NULL) OR "
            "(outcome NOT IN ('RECEIVED','ACCEPTED') AND "
            "reason_code ~ '^[A-Z0-9_]{1,100}$')",
            name="ck_attachment_attempt_reason",
        ),
    )
    op.create_index(
        "ix_attachment_attempt_document_created",
        "document_attachment_attempt",
        ["document_version_id", "occurred_at"],
    )
    _create_attachment_attempt_boundary()


def _create_attachment_attempt_boundary() -> None:
    op.execute(
        """
        CREATE FUNCTION append_document_attachment_attempt(
          p_attempt_id uuid,p_document_version_id uuid,p_content_sha256 text,
          p_object_key text,p_storage_etag text,p_byte_size bigint,
          p_declared_mime text,p_detected_mime text,p_filename_sha256 text,
          p_normalized_path_sha256 text,p_canonical_url_sha256 text,
          p_outcome text,p_reason_code text,p_occurred_at timestamptz DEFAULT now()
        ) RETURNS uuid
        LANGUAGE plpgsql SECURITY DEFINER
        SET search_path = pg_catalog, public AS $$
        BEGIN
          IF NOT EXISTS (
               SELECT 1 FROM document_version version
                WHERE version.id=p_document_version_id
             )
             OR p_content_sha256 !~ '^[0-9a-f]{64}$'
             OR p_object_key <> 'sha256/' || left(p_content_sha256,2) || '/'
                                || p_content_sha256
             OR p_storage_etag IS NOT NULL AND (
                  length(p_storage_etag) NOT BETWEEN 1 AND 200
                  OR p_storage_etag ~ '[[:cntrl:]]'
                )
             OR p_byte_size NOT BETWEEN 0 AND 536870912
             OR length(p_declared_mime) NOT BETWEEN 1 AND 100
             OR length(p_detected_mime) NOT BETWEEN 1 AND 100
             OR p_declared_mime ~ '[[:cntrl:]]'
             OR p_detected_mime ~ '[[:cntrl:]]'
             OR p_filename_sha256 !~ '^[0-9a-f]{64}$'
             OR p_normalized_path_sha256 !~ '^[0-9a-f]{64}$'
             OR p_canonical_url_sha256 !~ '^[0-9a-f]{64}$'
             OR p_outcome NOT IN (
                  'RECEIVED','ACCEPTED','REJECTED_CONTEXTUAL',
                  'QUARANTINED_INTRINSIC','INCONCLUSIVE',
                  'REJECTED_SECURITY_HISTORY'
                )
             OR (p_outcome IN ('RECEIVED','ACCEPTED') AND p_reason_code IS NOT NULL)
             OR (p_outcome NOT IN ('RECEIVED','ACCEPTED') AND (
                  p_reason_code IS NULL
                  OR p_reason_code !~ '^[A-Z0-9_]{1,100}$'
                )) THEN
            RAISE EXCEPTION 'document attachment attempt evidence is invalid';
          END IF;
          INSERT INTO document_attachment_attempt(
            id,document_version_id,content_sha256,object_key,storage_etag,
            byte_size,declared_mime,detected_mime,filename_sha256,
            normalized_path_sha256,canonical_url_sha256,outcome,reason_code,
            occurred_at
          ) VALUES (
            p_attempt_id,p_document_version_id,p_content_sha256,p_object_key,
            p_storage_etag,p_byte_size,p_declared_mime,p_detected_mime,
            p_filename_sha256,p_normalized_path_sha256,p_canonical_url_sha256,
            p_outcome,p_reason_code,p_occurred_at
          );
          RETURN p_attempt_id;
        END $$
        """
    )
    signature = (
        "append_document_attachment_attempt("
        "uuid,uuid,text,text,text,bigint,text,text,text,text,text,text,text,timestamptz)"
    )
    op.execute(f"REVOKE ALL ON FUNCTION {signature} FROM PUBLIC")
    op.execute(
        f"GRANT EXECUTE ON FUNCTION {signature} TO srbg_api_role, srbg_worker_role"
    )


def _create_document_version_execution_domain_boundary() -> None:
    op.execute(
        """
        CREATE FUNCTION enforce_document_version_execution_domain()
        RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER
        SET search_path = pg_catalog, public AS $$
        DECLARE
          v_document_source_id uuid;
          v_capture_source_id uuid;
          v_capture_raw_object_id uuid;
          v_capture_domain text;
          v_capture_trial_id uuid;
        BEGIN
          SELECT source_id INTO v_document_source_id
            FROM document WHERE id=NEW.document_id;
          IF NOT FOUND THEN
            RAISE EXCEPTION 'document version source is missing';
          END IF;

          IF NEW.execution_domain='LEGACY' THEN
            IF NEW.raw_object_capture_id IS NOT NULL THEN
              RAISE EXCEPTION 'legacy document version cannot claim governed capture';
            END IF;
            RETURN NEW;
          END IF;

          SELECT source_id,raw_object_id,execution_domain,trial_run_id
            INTO v_capture_source_id,v_capture_raw_object_id,
                 v_capture_domain,v_capture_trial_id
            FROM raw_object_capture WHERE id=NEW.raw_object_capture_id;
          IF NOT FOUND
             OR v_capture_source_id<>v_document_source_id
             OR v_capture_raw_object_id<>NEW.raw_object_id
             OR v_capture_domain<>NEW.execution_domain THEN
            RAISE EXCEPTION 'document version execution domain is not capture-bound';
          END IF;

          IF NEW.execution_domain IN ('FIXTURE','TRIAL') AND NOT EXISTS (
               SELECT 1 FROM source_trial_run trial
                WHERE trial.id=v_capture_trial_id
                  AND trial.source_id=v_capture_source_id
                  AND trial.execution_domain=NEW.execution_domain
                  AND (
                    (NEW.execution_domain='FIXTURE' AND trial.kind='FIXTURE_REPLAY')
                    OR (NEW.execution_domain='TRIAL' AND trial.kind='LIVE_TRIAL')
                  )
             ) THEN
            RAISE EXCEPTION 'document version trial domain is not authorized';
          END IF;

          IF NEW.execution_domain='PRODUCTION' AND (
               v_capture_trial_id IS NOT NULL
               OR NOT EXISTS (
                    SELECT 1 FROM source source_row
                     WHERE source_row.id=v_document_source_id
                       AND source_row.lifecycle_state='ACTIVE'
                  )
             ) THEN
            RAISE EXCEPTION 'document version production domain is not authorized';
          END IF;
          RETURN NEW;
        END $$
        """
    )
    op.execute(
        "REVOKE ALL ON FUNCTION enforce_document_version_execution_domain() FROM PUBLIC"
    )
    op.execute(
        """
        CREATE TRIGGER trg_document_version_execution_domain
        BEFORE INSERT ON document_version
        FOR EACH ROW EXECUTE FUNCTION enforce_document_version_execution_domain()
        """
    )


def _create_source_history_tables() -> None:
    op.create_table(
        "source_lifecycle_event",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column(
            "source_id", _uuid(), sa.ForeignKey("source.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column("from_state", sa.String(30)),
        sa.Column("to_state", sa.String(30), nullable=False),
        sa.Column("action", sa.String(40)),
        sa.Column("reason_code", sa.String(100), nullable=False),
        sa.Column("reason", sa.String(500), nullable=False),
        sa.Column("actor_id", _uuid()),
        sa.Column(
            "policy_version_id",
            _uuid(),
            sa.ForeignKey("source_policy_version.id", ondelete="RESTRICT"),
        ),
        sa.Column(
            "governance_decision_id",
            _uuid(),
            sa.ForeignKey("source_governance_decision.id", ondelete="RESTRICT"),
        ),
        sa.Column("migration_rule_version", sa.String(50)),
        sa.Column("legacy_snapshot", _JSON),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            f"from_state IS NULL OR from_state IN ({_LIFECYCLE_STATES})",
            name="ck_source_event_from_state",
        ),
        sa.CheckConstraint(f"to_state IN ({_LIFECYCLE_STATES})", name="ck_source_event_to_state"),
        sa.CheckConstraint(
            "action IS NULL OR action IN ('SUBMIT_COMPLIANCE','START_FIXTURE_TRIAL','START_LIVE_TRIAL','APPROVE_PRODUCTION','PAUSE','RESUME','RETIRE')",
            name="ck_source_event_action",
        ),
    )
    op.create_index(
        "ix_source_lifecycle_event_source_created",
        "source_lifecycle_event",
        ["source_id", "created_at"],
    )
    op.create_table(
        "source_migration_snapshot",
        sa.Column(
            "source_id",
            _uuid(),
            sa.ForeignKey("source.id", ondelete="RESTRICT"),
            primary_key=True,
        ),
        sa.Column("legacy_state", sa.String(30), nullable=False),
        sa.Column("legacy_enabled", sa.Boolean(), nullable=False),
        sa.Column("mapped_lifecycle_state", sa.String(30), nullable=False),
        sa.Column("mapped_trial_kind", sa.String(30)),
        sa.Column("mapping_reason", sa.String(100), nullable=False),
        sa.Column("migration_rule_version", sa.String(50), nullable=False),
        sa.Column("migrated_at", sa.DateTime(timezone=True), nullable=False),
    )


def _migrate_legacy_lifecycle() -> None:
    op.execute(
        f"""
        INSERT INTO source_migration_snapshot (
            source_id, legacy_state, legacy_enabled, mapped_lifecycle_state,
            mapped_trial_kind, mapping_reason, migration_rule_version, migrated_at
        )
        SELECT s.id, s.state, s.enabled,
          CASE
            WHEN s.state = 'CANDIDATE' THEN 'CANDIDATE'
            WHEN s.state = 'COMPLIANCE_REVIEW' THEN 'COMPLIANCE_REVIEW'
            WHEN s.state IN ('FIXTURE_TEST','APPROVED') THEN 'TRIAL'
            WHEN s.state = 'ACTIVE' AND s.enabled = false THEN 'PAUSED'
            WHEN s.state = 'ACTIVE' AND s.enabled = true
             AND EXISTS (
               SELECT 1 FROM source_onboarding_record o WHERE o.source_id = s.id
             ) THEN 'TRIAL'
            ELSE 'PAUSED'
          END,
          CASE
            WHEN s.state IN ('FIXTURE_TEST','APPROVED') THEN 'FIXTURE_REPLAY'
            WHEN s.state = 'ACTIVE' AND s.enabled = true
             AND EXISTS (
               SELECT 1 FROM source_onboarding_record o WHERE o.source_id = s.id
             ) THEN 'FIXTURE_REPLAY'
            ELSE NULL
          END,
          CASE
            WHEN s.state = 'FIXTURE_TEST' THEN 'LEGACY_FIXTURE_TEST'
            WHEN s.state = 'APPROVED' THEN 'LEGACY_UNVERIFIED'
            WHEN s.state = 'ACTIVE' AND s.enabled = false THEN 'LEGACY_DISABLED'
            WHEN s.state = 'ACTIVE' AND s.enabled = true
             AND EXISTS (
               SELECT 1 FROM source_onboarding_record o WHERE o.source_id = s.id
             ) THEN 'LEGACY_FIXTURE_ONLY'
            WHEN s.state = 'ACTIVE' THEN 'V2_REAUTHORIZATION_REQUIRED'
            ELSE 'LEGACY_STATE_PRESERVED'
          END,
          '{ROUND15_MIGRATION_RULE_VERSION}', now()
        FROM source s
        """
    )
    op.execute(
        """
        UPDATE source s
           SET lifecycle_state = snapshot.mapped_lifecycle_state,
               trial_kind = snapshot.mapped_trial_kind,
               updated_at = now()
          FROM source_migration_snapshot snapshot
         WHERE snapshot.source_id = s.id
        """
    )
    # V1 enabled is evidence only; all production authority must be re-established by V2.
    op.execute("UPDATE source SET enabled = false")
    op.execute(
        f"""
        INSERT INTO source_lifecycle_event (
          id, source_id, from_state, to_state, action, reason_code, reason,
          actor_id, migration_rule_version, legacy_snapshot, created_at
        )
        SELECT source_id, source_id, NULL, mapped_lifecycle_state, NULL, mapping_reason,
               'V1 source lifecycle migrated without granting production authorization',
               NULL, '{ROUND15_MIGRATION_RULE_VERSION}',
               jsonb_build_object(
                 'state', legacy_state, 'enabled', legacy_enabled,
                 'trial_kind', mapped_trial_kind
               ), migrated_at
          FROM source_migration_snapshot
        """
    )


def _create_immutable_boundaries() -> None:
    for table_name in ROUND15_TABLES:
        op.execute(
            f"""
            CREATE TRIGGER trg_{table_name}_immutable
            BEFORE UPDATE OR DELETE ON {table_name}
            FOR EACH ROW EXECUTE FUNCTION reject_immutable_source_vault_change()
            """
        )


def _create_raw_security_boundaries() -> None:
    # Attachments stay immutable except for the one-way security downgrade
    # caused by append-only negative raw evidence.
    op.execute(
        "DROP TRIGGER IF EXISTS trg_document_attachment_immutable ON document_attachment"
    )
    op.execute(
        """
        CREATE FUNCTION reject_nonsecurity_document_attachment_change()
        RETURNS trigger LANGUAGE plpgsql
        SET search_path = pg_catalog, public AS $$
        BEGIN
          IF TG_OP='UPDATE'
             AND OLD.security_status='CLEAN'
             AND NEW.security_status='QUARANTINED'
             AND (to_jsonb(NEW)-'security_status') =
                 (to_jsonb(OLD)-'security_status') THEN
            RETURN NEW;
          END IF;
          RAISE EXCEPTION 'document_attachment is immutable';
        END $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_document_attachment_immutable
        BEFORE UPDATE OR DELETE ON document_attachment
        FOR EACH ROW EXECUTE FUNCTION reject_nonsecurity_document_attachment_change()
        """
    )
    op.execute(
        """
        CREATE FUNCTION clear_current_document_for_negative_raw()
        RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER
        SET search_path = pg_catalog, public AS $$
        BEGIN
          IF NEW.status IN ('REJECTED','QUARANTINED') THEN
            UPDATE publication publication_row
               SET status='WITHDRAWN',
                   withdrawn_at=COALESCE(publication_row.withdrawn_at,NEW.created_at),
                   updated_at=GREATEST(publication_row.updated_at,NEW.created_at)
             WHERE publication_row.status='PUBLISHED'
               AND publication_row.item_id IN (
                 SELECT item.id FROM intelligence_item item
                  JOIN document_version version
                    ON version.id=item.current_document_version_id
                 WHERE version.raw_object_id=NEW.raw_object_id
               );
            UPDATE review_task task
               SET status='PENDING',decided_by=NULL,decided_at=NULL,
                   decision_reason=NULL
             WHERE task.document_version_id IN (
               SELECT version.id FROM document_version version
                WHERE version.raw_object_id=NEW.raw_object_id
             );
            UPDATE intelligence_item item
               SET publishable=false,review_status='PENDING',
                   processing_status='QUARANTINED',
                   updated_at=GREATEST(item.updated_at,NEW.created_at)
             WHERE item.current_document_version_id IN (
               SELECT version.id FROM document_version version
                WHERE version.raw_object_id=NEW.raw_object_id
             );
            UPDATE document document_row SET current_version_id=(
              SELECT candidate.id
                FROM document_version candidate
                JOIN raw_object candidate_raw ON candidate_raw.id=candidate.raw_object_id
               WHERE candidate.document_id=document_row.id
                 AND candidate.raw_object_id<>NEW.raw_object_id
                 AND candidate_raw.scan_status='CLEAN'
                 AND NOT EXISTS (
                   SELECT 1 FROM raw_object_security_fact negative
                    WHERE negative.raw_object_id=candidate_raw.id
                      AND negative.status IN ('REJECTED','QUARANTINED')
                 )
                 AND (
                   SELECT state.state FROM document_version_state_event state
                    WHERE state.document_version_id=candidate.id
                    ORDER BY state.created_at DESC,state.id DESC LIMIT 1
                 )='READY'
               ORDER BY candidate.version_number DESC,candidate.id DESC LIMIT 1
            )
             WHERE document_row.current_version_id IN (
               SELECT version.id FROM document_version version
                WHERE version.raw_object_id=NEW.raw_object_id
             );
            UPDATE document_attachment
               SET security_status='QUARANTINED'
             WHERE raw_object_id=NEW.raw_object_id
               AND security_status='CLEAN';
          END IF;
          RETURN NEW;
        END $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_raw_security_negative_clears_current
        AFTER INSERT ON raw_object_security_fact
        FOR EACH ROW EXECUTE FUNCTION clear_current_document_for_negative_raw()
        """
    )
    op.execute(
        """
        CREATE FUNCTION reject_negative_raw_as_document_current()
        RETURNS trigger LANGUAGE plpgsql
        SET search_path = pg_catalog, public AS $$
        BEGIN
          IF NEW.current_version_id IS NOT NULL AND EXISTS (
               SELECT 1
                 FROM document_version version
                 JOIN raw_object raw ON raw.id=version.raw_object_id
                WHERE version.id=NEW.current_version_id
                  AND (
                    raw.scan_status <> 'CLEAN'
                    OR EXISTS (
                      SELECT 1 FROM raw_object_security_fact security
                       WHERE security.raw_object_id=raw.id
                         AND security.status IN ('REJECTED','QUARANTINED')
                    )
                  )
             ) THEN
            RAISE EXCEPTION 'document current version has rejected raw history';
          END IF;
          RETURN NEW;
        END $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_document_reject_negative_raw_current
        BEFORE INSERT OR UPDATE OF current_version_id ON document
        FOR EACH ROW EXECUTE FUNCTION reject_negative_raw_as_document_current()
        """
    )
    op.execute(
        """
        CREATE FUNCTION reject_clean_attachment_with_negative_raw_history()
        RETURNS trigger LANGUAGE plpgsql
        SET search_path = pg_catalog, public AS $$
        BEGIN
          IF NEW.security_status='CLEAN' AND EXISTS (
               SELECT 1 FROM raw_object raw
                WHERE raw.id=NEW.raw_object_id
                  AND (
                    raw.scan_status <> 'CLEAN'
                    OR EXISTS (
                      SELECT 1 FROM raw_object_security_fact security
                       WHERE security.raw_object_id=raw.id
                         AND security.status IN ('REJECTED','QUARANTINED')
                    )
                  )
             ) THEN
            RAISE EXCEPTION 'attachment raw object has rejected security history';
          END IF;
          RETURN NEW;
        END $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_document_attachment_reject_negative_raw_history
        BEFORE INSERT OR UPDATE ON document_attachment
        FOR EACH ROW EXECUTE FUNCTION
          reject_clean_attachment_with_negative_raw_history()
        """
    )
    op.execute(
        """
        CREATE FUNCTION reject_closed_trial_version_promotion()
        RETURNS trigger LANGUAGE plpgsql
        SET search_path = pg_catalog, public AS $$
        BEGIN
          IF NEW.state='READY' AND EXISTS (
               SELECT 1 FROM document_version version
               JOIN raw_object_capture capture
                 ON capture.id=version.raw_object_capture_id
              WHERE version.id=NEW.document_version_id
                AND capture.arrived_after_close
             ) THEN
            RAISE EXCEPTION 'closed source trial capture cannot become ready';
          END IF;
          RETURN NEW;
        END $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_document_version_reject_closed_trial_ready
        BEFORE INSERT ON document_version_state_event
        FOR EACH ROW EXECUTE FUNCTION reject_closed_trial_version_promotion()
        """
    )
    op.execute(
        """
        CREATE FUNCTION reject_closed_trial_version_as_current()
        RETURNS trigger LANGUAGE plpgsql
        SET search_path = pg_catalog, public AS $$
        BEGIN
          IF NEW.current_version_id IS NOT NULL AND EXISTS (
               SELECT 1 FROM document_version version
               JOIN raw_object_capture capture
                 ON capture.id=version.raw_object_capture_id
              WHERE version.id=NEW.current_version_id
                AND capture.arrived_after_close
             ) THEN
            RAISE EXCEPTION 'closed source trial capture cannot become current';
          END IF;
          RETURN NEW;
        END $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_document_reject_closed_trial_current
        BEFORE INSERT OR UPDATE OF current_version_id ON document
        FOR EACH ROW EXECUTE FUNCTION reject_closed_trial_version_as_current()
        """
    )
    # Replay immutable negative history that predates Round 15. A later CLEAN
    # observation can never erase an earlier rejection or quarantine.
    unsafe_raw = """
      SELECT raw.id FROM raw_object raw
       WHERE raw.scan_status <> 'CLEAN'
          OR EXISTS (
            SELECT 1 FROM raw_object_security_fact negative
             WHERE negative.raw_object_id=raw.id
               AND negative.status IN ('REJECTED','QUARANTINED')
          )
    """
    op.execute(
        f"""
        UPDATE publication publication_row
           SET status='WITHDRAWN',
               withdrawn_at=COALESCE(publication_row.withdrawn_at,now()),
               updated_at=GREATEST(publication_row.updated_at,now())
         WHERE publication_row.status='PUBLISHED'
           AND publication_row.item_id IN (
             SELECT item.id FROM intelligence_item item
             JOIN document_version version
               ON version.id=item.current_document_version_id
            WHERE version.raw_object_id IN ({unsafe_raw})
           )
        """
    )
    op.execute(
        f"""
        UPDATE review_task task
           SET status='PENDING',decided_by=NULL,decided_at=NULL,decision_reason=NULL
         WHERE task.document_version_id IN (
           SELECT version.id FROM document_version version
            WHERE version.raw_object_id IN ({unsafe_raw})
         )
        """
    )
    op.execute(
        f"""
        UPDATE intelligence_item item
           SET publishable=false,review_status='PENDING',
               processing_status='QUARANTINED',updated_at=GREATEST(item.updated_at,now())
         WHERE item.current_document_version_id IN (
           SELECT version.id FROM document_version version
            WHERE version.raw_object_id IN ({unsafe_raw})
         )
        """
    )
    op.execute(
        f"""
        UPDATE document document_row SET current_version_id=(
          SELECT candidate.id
            FROM document_version candidate
            JOIN raw_object candidate_raw ON candidate_raw.id=candidate.raw_object_id
           WHERE candidate.document_id=document_row.id
             AND candidate.raw_object_id NOT IN ({unsafe_raw})
             AND candidate_raw.scan_status='CLEAN'
             AND (
               SELECT state.state FROM document_version_state_event state
                WHERE state.document_version_id=candidate.id
                ORDER BY state.created_at DESC,state.id DESC LIMIT 1
             )='READY'
           ORDER BY candidate.version_number DESC,candidate.id DESC LIMIT 1
        )
         WHERE document_row.current_version_id IN (
           SELECT version.id FROM document_version version
            WHERE version.raw_object_id IN ({unsafe_raw})
         )
        """
    )
    op.execute(
        f"""
        UPDATE document_attachment attachment SET security_status='QUARANTINED'
         WHERE attachment.security_status='CLEAN'
           AND attachment.raw_object_id IN ({unsafe_raw})
        """
    )


def _create_source_command_boundary() -> None:
    op.execute(
        """
        CREATE FUNCTION register_source_candidate(
          p_source_id uuid, p_name text, p_base_url text, p_channel text,
          p_source_type text, p_authority_level text, p_priority text,
          p_collection_method text, p_poll_interval_minutes integer, p_owner text,
          p_governance_owner_id uuid, p_country_codes text[], p_region_codes text[],
          p_language_tags text[], p_industries text[], p_content_domains text[],
          p_declared_roles text[], p_actor_id uuid, p_request_id text,
          p_audit_id uuid, p_created_at timestamptz DEFAULT now()
        ) RETURNS uuid
        LANGUAGE plpgsql SECURITY DEFINER
        SET search_path = pg_catalog, public AS $$
        BEGIN
          IF length(p_name) NOT BETWEEN 1 AND 200 OR p_name ~ '[[:cntrl:]]'
             OR length(p_base_url) NOT BETWEEN 8 AND 2048
             OR p_base_url !~ '^https?://[^[:space:]@?#]+(?:/[^[:space:]?#]*)?$'
             OR length(p_collection_method) NOT BETWEEN 1 AND 50
             OR p_collection_method ~ '[[:cntrl:]]'
             OR length(p_owner) NOT BETWEEN 1 AND 100 OR p_owner ~ '[[:cntrl:]]'
             OR p_poll_interval_minutes NOT BETWEEN 1 AND 10080
             OR p_country_codes IS NULL OR cardinality(p_country_codes) > 20
             OR p_region_codes IS NULL OR cardinality(p_region_codes) > 50
             OR p_language_tags IS NULL OR cardinality(p_language_tags) > 20
             OR p_industries IS NULL OR cardinality(p_industries) > 20
             OR p_content_domains IS NULL OR cardinality(p_content_domains) > 30
             OR p_declared_roles IS NULL OR cardinality(p_declared_roles) > 20
             OR EXISTS (SELECT 1 FROM unnest(p_country_codes) value
                         WHERE value IS NULL OR value !~ '^[A-Z]{2}$')
             OR EXISTS (SELECT 1 FROM unnest(p_region_codes) value
                         WHERE value IS NULL OR value !~ '^[A-Z0-9]{2,3}(-[A-Z0-9]{1,6})?$')
             OR EXISTS (SELECT 1 FROM unnest(p_language_tags) value
                         WHERE value IS NULL OR length(value) NOT BETWEEN 2 AND 35
                            OR value !~ '^[A-Za-z]{2,8}(-[A-Za-z0-9]{1,8})*$')
             OR EXISTS (SELECT 1 FROM unnest(
                          p_industries || p_content_domains || p_declared_roles
                        ) value
                         WHERE value IS NULL OR length(value) NOT BETWEEN 1 AND 50
                            OR value !~ '^[A-Z][A-Z0-9_]*$')
             OR cardinality(p_country_codes) <>
                  (SELECT count(DISTINCT value) FROM unnest(p_country_codes) value)
             OR cardinality(p_region_codes) <>
                  (SELECT count(DISTINCT value) FROM unnest(p_region_codes) value)
             OR cardinality(p_language_tags) <>
                  (SELECT count(DISTINCT value) FROM unnest(p_language_tags) value)
             OR cardinality(p_industries) <>
                  (SELECT count(DISTINCT value) FROM unnest(p_industries) value)
             OR cardinality(p_content_domains) <>
                  (SELECT count(DISTINCT value) FROM unnest(p_content_domains) value)
             OR cardinality(p_declared_roles) <>
                  (SELECT count(DISTINCT value) FROM unnest(p_declared_roles) value) THEN
            RAISE EXCEPTION 'source candidate input is invalid';
          END IF;
          INSERT INTO source (
            id, name, base_url, channel, source_type, authority_level, priority,
            collection_method, poll_interval_minutes, owner, state, enabled,
            lifecycle_state, trial_kind, registered_by, governance_owner_id,
            country_codes, region_codes, language_tags, industries, content_domains,
            declared_roles, created_at, updated_at
          ) VALUES (
            p_source_id, p_name, p_base_url, p_channel, p_source_type,
            p_authority_level, p_priority, p_collection_method,
            p_poll_interval_minutes, p_owner, 'CANDIDATE', false, 'CANDIDATE', NULL,
            p_actor_id, p_governance_owner_id, p_country_codes, p_region_codes,
            p_language_tags, p_industries, p_content_domains, p_declared_roles,
            p_created_at, p_created_at
          );
          PERFORM append_audit_event(
            p_audit_id, 'SOURCE_REGISTERED', p_actor_id, 'SOURCE', p_source_id,
            NULL, jsonb_build_object('lifecycle_state','CANDIDATE','enabled',false),
            'source candidate registered', p_request_id, p_created_at
          );
          RETURN p_source_id;
        END $$
        """
    )
    register_signature = "register_source_candidate(uuid,text,text,text,text,text,text,text,integer,text,uuid,text[],text[],text[],text[],text[],text[],uuid,text,uuid,timestamptz)"
    op.execute(f"REVOKE ALL ON FUNCTION {register_signature} FROM PUBLIC")
    op.execute(f"GRANT EXECUTE ON FUNCTION {register_signature} TO srbg_api_role")
    op.execute(
        """
        CREATE FUNCTION update_source_governance_metadata(
          p_source_id uuid, p_governance_owner_id uuid, p_country_codes text[],
          p_region_codes text[], p_language_tags text[], p_industries text[],
          p_content_domains text[], p_declared_roles text[], p_actor_id uuid,
          p_reason text, p_request_id text, p_audit_id uuid,
          p_updated_at timestamptz DEFAULT now()
        ) RETURNS uuid
        LANGUAGE plpgsql SECURITY DEFINER
        SET search_path = pg_catalog, public AS $$
        DECLARE v_before jsonb;
        BEGIN
          IF source_v2_safe_audit_reason(p_reason) IS DISTINCT FROM true THEN
            RAISE EXCEPTION 'source governance reason is invalid';
          END IF;
          IF p_governance_owner_id IS NULL
             OR cardinality(p_country_codes) = 0 OR cardinality(p_region_codes) = 0
             OR cardinality(p_language_tags) = 0 OR cardinality(p_industries) = 0
             OR cardinality(p_content_domains) = 0 OR cardinality(p_declared_roles) = 0
             OR array_position(p_country_codes,NULL) IS NOT NULL
             OR array_position(p_region_codes,NULL) IS NOT NULL
             OR array_position(p_language_tags,NULL) IS NOT NULL
             OR array_position(p_industries,NULL) IS NOT NULL
             OR array_position(p_content_domains,NULL) IS NOT NULL
             OR array_position(p_declared_roles,NULL) IS NOT NULL
             OR cardinality(p_country_codes) > 20
             OR cardinality(p_region_codes) > 50
             OR cardinality(p_language_tags) > 20
             OR cardinality(p_industries) > 20
             OR cardinality(p_content_domains) > 30
             OR cardinality(p_declared_roles) > 20
             OR EXISTS (SELECT 1 FROM unnest(p_country_codes) value
                         WHERE value !~ '^[A-Z]{2}$')
             OR EXISTS (SELECT 1 FROM unnest(p_region_codes) value
                         WHERE value !~ '^[A-Z0-9]{2,3}(-[A-Z0-9]{1,6})?$')
             OR EXISTS (SELECT 1 FROM unnest(p_language_tags) value
                         WHERE length(value) NOT BETWEEN 2 AND 35
                            OR value !~ '^[A-Za-z]{2,8}(-[A-Za-z0-9]{1,8})*$')
             OR EXISTS (SELECT 1 FROM unnest(
                          p_industries || p_content_domains || p_declared_roles
                        ) value
                         WHERE length(value) NOT BETWEEN 1 AND 50
                            OR value !~ '^[A-Z][A-Z0-9_]*$')
             OR cardinality(p_country_codes) <>
                  (SELECT count(DISTINCT value) FROM unnest(p_country_codes) value)
             OR cardinality(p_region_codes) <>
                  (SELECT count(DISTINCT value) FROM unnest(p_region_codes) value)
             OR cardinality(p_language_tags) <>
                  (SELECT count(DISTINCT value) FROM unnest(p_language_tags) value)
             OR cardinality(p_industries) <>
                  (SELECT count(DISTINCT value) FROM unnest(p_industries) value)
             OR cardinality(p_content_domains) <>
                  (SELECT count(DISTINCT value) FROM unnest(p_content_domains) value)
             OR cardinality(p_declared_roles) <>
                  (SELECT count(DISTINCT value) FROM unnest(p_declared_roles) value) THEN
            RAISE EXCEPTION 'source governance metadata is incomplete';
          END IF;
          SELECT jsonb_build_object(
                   'governance_owner_id',governance_owner_id,
                   'country_codes',country_codes,'region_codes',region_codes,
                   'language_tags',language_tags,'industries',industries,
                   'content_domains',content_domains,'declared_roles',declared_roles
                 ) INTO v_before
            FROM source WHERE id=p_source_id FOR UPDATE;
          IF NOT FOUND THEN RAISE EXCEPTION 'source does not exist'; END IF;
          UPDATE source SET governance_owner_id=p_governance_owner_id,
              country_codes=p_country_codes, region_codes=p_region_codes,
              language_tags=p_language_tags, industries=p_industries,
              content_domains=p_content_domains, declared_roles=p_declared_roles,
              updated_at=p_updated_at WHERE id=p_source_id;
          PERFORM append_audit_event(
            p_audit_id, 'SOURCE_GOVERNANCE_METADATA_UPDATED', p_actor_id,
            'SOURCE', p_source_id, v_before,
            jsonb_build_object(
              'governance_owner_id',p_governance_owner_id,
              'country_codes',p_country_codes,'region_codes',p_region_codes,
              'language_tags',p_language_tags,'industries',p_industries,
              'content_domains',p_content_domains,'declared_roles',p_declared_roles
            ), p_reason, p_request_id, p_updated_at
          );
          RETURN p_source_id;
        END $$
        """
    )
    metadata_signature = "update_source_governance_metadata(uuid,uuid,text[],text[],text[],text[],text[],text[],uuid,text,text,uuid,timestamptz)"
    op.execute(f"REVOKE ALL ON FUNCTION {metadata_signature} FROM PUBLIC")
    op.execute(f"GRANT EXECUTE ON FUNCTION {metadata_signature} TO srbg_api_role")
    op.execute(
        """
        CREATE FUNCTION append_source_assessments(
          p_source_id uuid, p_authority_id uuid, p_authority_level text,
          p_authority_rule_version text, p_authority_reason_codes text[],
          p_authority_evidence_refs text[], p_authority_assessed_at timestamptz,
          p_independence_id uuid, p_independence_level text,
          p_independence_rule_version text, p_independence_reason_codes text[],
          p_independence_evidence_refs text[], p_independence_assessed_at timestamptz,
          p_actor_id uuid, p_reason text, p_request_id text, p_audit_id uuid,
          p_created_at timestamptz DEFAULT now()
        ) RETURNS uuid
        LANGUAGE plpgsql SECURITY DEFINER
        SET search_path = pg_catalog, public AS $$
        BEGIN
          IF source_v2_safe_audit_reason(p_reason) IS DISTINCT FROM true THEN
            RAISE EXCEPTION 'source governance reason is invalid';
          END IF;
          PERFORM 1 FROM source WHERE id=p_source_id FOR UPDATE;
          IF NOT FOUND THEN RAISE EXCEPTION 'source does not exist'; END IF;
          IF p_authority_level NOT IN ('A0','A1','B1','B2','C1','C2','UNKNOWN')
             OR p_independence_level NOT IN (
               'EDITORIALLY_INDEPENDENT','PARTIALLY_INDEPENDENT',
               'NOT_INDEPENDENT','UNKNOWN'
             ) OR p_authority_reason_codes IS NULL
             OR p_independence_reason_codes IS NULL
             OR p_authority_evidence_refs IS NULL
             OR p_independence_evidence_refs IS NULL
             OR cardinality(p_authority_reason_codes)=0
             OR cardinality(p_independence_reason_codes)=0
             OR cardinality(p_authority_reason_codes) > 20
             OR cardinality(p_independence_reason_codes) > 20
             OR cardinality(p_authority_evidence_refs) > 50
             OR cardinality(p_independence_evidence_refs) > 50
             OR length(p_authority_rule_version) NOT BETWEEN 1 AND 50
             OR length(p_independence_rule_version) NOT BETWEEN 1 AND 50
             OR p_authority_rule_version ~ '[[:cntrl:]]'
             OR p_independence_rule_version ~ '[[:cntrl:]]'
             OR EXISTS (SELECT 1 FROM unnest(
                          p_authority_reason_codes || p_independence_reason_codes
                        ) value
                         WHERE value IS NULL
                            OR value !~ '^[A-Z][A-Z0-9_]{0,99}$')
             OR EXISTS (SELECT 1 FROM unnest(
                          p_authority_evidence_refs || p_independence_evidence_refs
                        ) value
                         WHERE value IS NULL OR length(value) NOT BETWEEN 1 AND 500
                            OR value ~ '[[:space:][:cntrl:]]'
                            OR value ~ '://[^/[:space:]]+@'
                            OR value ~* '[?&](api[_-]?key|access[_-]?key|auth(entication|orization|_token)?|bearer|client[_-]?secret|cookie|credential|password|secret|session|signature|token)=[^&]+')
             OR cardinality(p_authority_reason_codes) <>
                  (SELECT count(DISTINCT value)
                     FROM unnest(p_authority_reason_codes) value)
             OR cardinality(p_independence_reason_codes) <>
                  (SELECT count(DISTINCT value)
                     FROM unnest(p_independence_reason_codes) value)
             OR cardinality(p_authority_evidence_refs) <>
                  (SELECT count(DISTINCT value)
                     FROM unnest(p_authority_evidence_refs) value)
             OR cardinality(p_independence_evidence_refs) <>
                  (SELECT count(DISTINCT value)
                     FROM unnest(p_independence_evidence_refs) value)
             OR p_authority_assessed_at > p_created_at
             OR p_independence_assessed_at > p_created_at THEN
            RAISE EXCEPTION 'source assessment is invalid';
          END IF;
          INSERT INTO source_authority_assessment (
            id,source_id,authority_level,rule_version,reason_codes,evidence_refs,
            assessed_by,assessed_at
          ) VALUES (
            p_authority_id,p_source_id,p_authority_level,p_authority_rule_version,
            p_authority_reason_codes,p_authority_evidence_refs,p_actor_id,
            p_authority_assessed_at
          );
          INSERT INTO source_independence_assessment (
            id,source_id,independence_level,rule_version,reason_codes,evidence_refs,
            assessed_by,assessed_at
          ) VALUES (
            p_independence_id,p_source_id,p_independence_level,
            p_independence_rule_version,p_independence_reason_codes,
            p_independence_evidence_refs,p_actor_id,p_independence_assessed_at
          );
          PERFORM append_audit_event(
            p_audit_id, 'SOURCE_ASSESSMENTS_APPENDED', p_actor_id, 'SOURCE',
            p_source_id, NULL,
            jsonb_build_object(
              'authority_assessment_id',p_authority_id,
              'authority_level',p_authority_level,
              'authority_rule_version',p_authority_rule_version,
              'independence_assessment_id',p_independence_id,
              'independence_level',p_independence_level,
              'independence_rule_version',p_independence_rule_version
            ), p_reason, p_request_id, p_created_at
          );
          RETURN p_source_id;
        END $$
        """
    )
    assessment_signature = "append_source_assessments(uuid,uuid,text,text,text[],text[],timestamptz,uuid,text,text,text[],text[],timestamptz,uuid,text,text,uuid,timestamptz)"
    op.execute(f"REVOKE ALL ON FUNCTION {assessment_signature} FROM PUBLIC")
    op.execute(f"GRANT EXECUTE ON FUNCTION {assessment_signature} TO srbg_api_role")
    op.execute(
        """
        CREATE FUNCTION apply_source_lifecycle_command(
            p_source_id uuid, p_action text, p_actor_id uuid, p_reason text,
            p_request_id text, p_event_id uuid, p_occurred_at timestamptz DEFAULT now()
        ) RETURNS text
        LANGUAGE plpgsql SECURITY DEFINER
        SET search_path = pg_catalog, public AS $$
        DECLARE
          v_current text;
          v_target text;
          v_policy uuid;
          v_config uuid;
          v_decision uuid;
          v_trial uuid;
          v_trial_kind text;
        BEGIN
          IF source_v2_safe_audit_reason(p_reason) IS DISTINCT FROM true THEN
            RAISE EXCEPTION 'source lifecycle reason is invalid';
          END IF;
          SELECT lifecycle_state, current_policy_version_id,
                 current_connector_config_version_id, current_trial_run_id, trial_kind
            INTO v_current, v_policy, v_config, v_trial, v_trial_kind
            FROM source WHERE id = p_source_id FOR UPDATE;
          IF NOT FOUND THEN RAISE EXCEPTION 'source does not exist'; END IF;

          v_target := CASE
            WHEN v_current = 'CANDIDATE' AND p_action = 'SUBMIT_COMPLIANCE'
              THEN 'COMPLIANCE_REVIEW'
            WHEN v_current = 'ACTIVE' AND p_action = 'PAUSE' THEN 'PAUSED'
            WHEN v_current IN ('CANDIDATE','COMPLIANCE_REVIEW','TRIAL','PAUSED')
             AND p_action = 'RETIRE' THEN 'RETIRED'
            WHEN v_current = 'PAUSED' AND p_action = 'RESUME' THEN 'ACTIVE'
            ELSE NULL
          END;
          IF v_target IS NULL THEN
            RAISE EXCEPTION 'invalid source lifecycle command';
          END IF;
          IF p_action = 'RESUME' THEN
            SELECT d.id INTO v_decision
              FROM source_governance_decision d
              JOIN source_policy_version p ON p.id = d.policy_version_id
              JOIN connector_config_version c
                ON c.id=d.connector_config_version_id
               AND c.source_id=d.source_id AND c.policy_version_id=p.id
              JOIN source_trial_run r
                ON r.id = d.trial_run_id AND r.kind = 'LIVE_TRIAL'
               AND r.source_id=d.source_id AND r.policy_version_id=p.id
               AND r.connector_config_version_id=c.id
              JOIN source_trial_run_result rr ON rr.trial_run_id = r.id
             WHERE d.source_id = p_source_id
               AND d.decision_type = 'PRODUCTION_APPROVAL' AND d.outcome = 'APPROVED'
               AND d.policy_version_id = v_policy
               AND d.connector_config_version_id = v_config
               AND d.trial_run_id = v_trial
               AND p.source_id = p_source_id AND r.source_id = p_source_id
               AND (d.valid_until IS NULL OR d.valid_until > p_occurred_at)
               AND p.valid_from <= p_occurred_at
               AND p.valid_until > p_occurred_at AND rr.status = 'SUCCEEDED'
               AND c.validation_status='VALID'
               AND source_v2_policy_compliance_approved(
                     p_source_id,v_policy,p_occurred_at
                   ) IS TRUE
             ORDER BY d.created_at DESC, d.id DESC LIMIT 1;
            IF v_decision IS NULL THEN
              RAISE EXCEPTION 'current production evidence is incomplete or expired';
            END IF;
          END IF;

          UPDATE source SET lifecycle_state = v_target,
              trial_kind = CASE WHEN v_target = 'TRIAL' THEN trial_kind ELSE NULL END,
              updated_at = p_occurred_at WHERE id = p_source_id;
          INSERT INTO source_lifecycle_event (
            id, source_id, from_state, to_state, action, reason_code, reason,
            actor_id, policy_version_id, governance_decision_id, created_at
          ) VALUES (
            p_event_id, p_source_id, v_current, v_target, p_action,
            'COMMAND_' || p_action, p_reason, p_actor_id, v_policy, v_decision, p_occurred_at
          );
          PERFORM append_audit_event(
            p_event_id, 'SOURCE_' || p_action, p_actor_id, 'SOURCE', p_source_id,
            jsonb_build_object('lifecycle_state', v_current),
            jsonb_build_object('lifecycle_state', v_target),
            p_reason, p_request_id, p_occurred_at
          );
          RETURN v_target;
        END $$
        """
    )
    signature = "apply_source_lifecycle_command(uuid,text,uuid,text,text,uuid,timestamptz)"
    op.execute(f"REVOKE ALL ON FUNCTION {signature} FROM PUBLIC")
    op.execute(f"GRANT EXECUTE ON FUNCTION {signature} TO srbg_api_role")
    _create_source_validation_helpers()
    _create_policy_write_boundaries()
    _create_connector_config_write_boundary()
    _create_trial_write_boundaries()


def _create_source_validation_helpers() -> None:
    op.execute(
        """
        CREATE FUNCTION source_v2_safe_audit_reason(p_reason text) RETURNS boolean
        LANGUAGE sql IMMUTABLE STRICT PARALLEL SAFE
        SET search_path = pg_catalog, public AS $$
          SELECT length(p_reason) BETWEEN 1 AND 500
             AND p_reason !~ '[[:cntrl:]]'
             AND lower(p_reason) !~
               '(https?://|vault://|[^[:space:]]+@[^[:space:]]+|'
               '(^|[^a-z])(api[_-]?key|authorization|bearer|cookie|credential|'
               'password|secret|token|vault)([^a-z]|$))'
        $$
        """
    )
    op.execute(
        """
        CREATE FUNCTION source_v2_exact_dns_host(p_host text) RETURNS boolean
        LANGUAGE sql IMMUTABLE STRICT PARALLEL SAFE
        SET search_path = pg_catalog, public AS $$
          SELECT length(p_host) BETWEEN 4 AND 253
             AND p_host = lower(p_host)
             AND position('.' in p_host) > 1
             AND p_host NOT LIKE '%.%.'
             AND p_host NOT LIKE '%..%'
             AND reverse(split_part(reverse(p_host),'.',1)) ~ '^[a-z]{2,63}$'
             AND NOT EXISTS (
               SELECT 1 FROM unnest(string_to_array(p_host,'.')) label
                WHERE length(label) NOT BETWEEN 1 AND 63
                   OR label !~ '^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$'
             )
        $$
        """
    )
    op.execute(
        """
        CREATE FUNCTION source_v2_safe_http_url(
          p_url text, p_allowed_hosts text[]
        ) RETURNS boolean
        LANGUAGE plpgsql IMMUTABLE STRICT PARALLEL SAFE
        SET search_path = pg_catalog, public AS $$
        DECLARE
          v_scheme text;
          v_remainder text;
          v_authority text;
          v_host text;
          v_port text;
        BEGIN
          IF length(p_url) NOT BETWEEN 8 AND 2048
             OR p_url !~ '^https?://'
             OR p_url ~ '[[:space:]]'
             OR position('#' in p_url) > 0
             OR position('?' in p_url) > 0
             OR position('@' in p_url) > 0
             OR position(chr(92) in p_url) > 0
             OR p_url ~* '%(0[0-9a-f]|1[0-9a-f]|7f)' THEN
            RETURN false;
          END IF;
          v_scheme := split_part(p_url,'://',1);
          v_remainder := substring(p_url FROM length(v_scheme) + 4);
          v_authority := split_part(split_part(v_remainder,'/',1),'?',1);
          IF v_authority IS NULL OR v_authority = '' THEN RETURN false; END IF;
          IF v_authority ~ ':[0-9]+$' THEN
            v_host := regexp_replace(v_authority, ':[0-9]+$', '');
            v_port := substring(v_authority FROM ':([0-9]+)$');
          ELSE
            IF position(':' in v_authority) > 0 THEN RETURN false; END IF;
            v_host := v_authority;
            v_port := NULL;
          END IF;
          IF source_v2_exact_dns_host(v_host) IS DISTINCT FROM true
             OR NOT (v_host = ANY(p_allowed_hosts))
             OR (v_scheme='https' AND v_port IS NOT NULL AND v_port <> '443')
             OR (v_scheme='http' AND v_port IS NOT NULL AND v_port <> '80') THEN
            RETURN false;
          END IF;
          RETURN true;
        END $$
        """
    )
    op.execute(
        """
        CREATE FUNCTION source_v2_policy_compliance_approved(
          p_source_id uuid, p_policy_id uuid, p_at timestamptz
        ) RETURNS boolean
        LANGUAGE sql STABLE STRICT PARALLEL SAFE
        SET search_path = pg_catalog, public AS $$
          SELECT COALESCE((
            SELECT d.outcome = 'APPROVED'
                   AND (d.valid_until IS NULL OR d.valid_until > p_at)
              FROM source_governance_decision d
             WHERE d.source_id=p_source_id
               AND d.policy_version_id=p_policy_id
               AND d.decision_type='COMPLIANCE'
             ORDER BY d.created_at DESC, d.id DESC
             LIMIT 1
          ),false)
        $$
        """
    )
    for signature in (
        "source_v2_safe_audit_reason(text)",
        "source_v2_exact_dns_host(text)",
        "source_v2_safe_http_url(text,text[])",
        "source_v2_policy_compliance_approved(uuid,uuid,timestamptz)",
    ):
        op.execute(f"REVOKE ALL ON FUNCTION {signature} FROM PUBLIC")
    op.execute(
        "GRANT EXECUTE ON FUNCTION "
        "source_v2_policy_compliance_approved(uuid,uuid,timestamptz) TO "
        "srbg_runtime, srbg_api_role, srbg_worker_role, srbg_publication_writer"
    )


def _create_policy_write_boundaries() -> None:
    op.execute(
        """
        CREATE FUNCTION submit_source_policy_version(
          p_source_id uuid, p_policy_id uuid, p_schema_version text,
          p_policy_version text, p_document jsonb,
          p_valid_from timestamptz, p_valid_until timestamptz, p_actor_id uuid,
          p_reason text, p_request_id text, p_audit_id uuid,
          p_created_at timestamptz DEFAULT now()
        ) RETURNS uuid
        LANGUAGE plpgsql SECURITY DEFINER
        SET search_path = pg_catalog, public AS $$
        DECLARE
          v_state text;
          v_document_sha256 text;
          v_slo_applicability text;
        BEGIN
          SELECT lifecycle_state INTO v_state FROM source
           WHERE id = p_source_id FOR UPDATE;
          IF NOT FOUND OR v_state NOT IN ('COMPLIANCE_REVIEW','TRIAL','PAUSED') THEN
            RAISE EXCEPTION 'source is not accepting policy submissions';
          END IF;
          IF p_schema_version <> '2.0.0' OR p_valid_until <= p_valid_from
             OR length(p_policy_version) NOT BETWEEN 1 AND 50
             OR source_v2_safe_audit_reason(p_reason) IS DISTINCT FROM true THEN
            RAISE EXCEPTION 'source policy metadata is invalid';
          END IF;
          IF jsonb_typeof(p_document) IS DISTINCT FROM 'object'
             OR NOT p_document ?& ARRAY[
               'schema_version','policy_version','valid_from','valid_until',
               'robots_review','terms_review','copyright_review','fetch',
               'storage_policy','display_policy','download_policy','retention',
               'legal_hold_policy','automatic_publication','slo','reason'
             ]
             OR p_document - ARRAY[
               'schema_version','policy_version','valid_from','valid_until',
               'robots_review','terms_review','copyright_review','fetch',
               'storage_policy','display_policy','download_policy','retention',
               'legal_hold_policy','automatic_publication','slo','reason'
             ] <> '{}'::jsonb
             OR jsonb_typeof(p_document->'schema_version') <> 'string'
             OR jsonb_typeof(p_document->'policy_version') <> 'string'
             OR jsonb_typeof(p_document->'valid_from') <> 'string'
             OR jsonb_typeof(p_document->'valid_until') <> 'string'
             OR jsonb_typeof(p_document->'reason') <> 'string'
             OR p_document->>'schema_version' <> p_schema_version
             OR p_document->>'policy_version' <> p_policy_version
             OR p_document->>'reason' <> p_reason
             OR p_document->>'valid_from' !~ '(Z|[+-][0-9]{2}:[0-9]{2})$'
             OR p_document->>'valid_until' !~ '(Z|[+-][0-9]{2}:[0-9]{2})$'
             OR (p_document->>'valid_from')::timestamptz
                  IS DISTINCT FROM p_valid_from
             OR (p_document->>'valid_until')::timestamptz
                  IS DISTINCT FROM p_valid_until THEN
            RAISE EXCEPTION 'source policy document envelope is invalid';
          END IF;
          IF p_document #>> '{robots_review,result}' <> 'ALLOWED'
             OR p_document #>> '{terms_review,result}' <> 'ALLOWED'
             OR p_document #>> '{copyright_review,result}' <> 'ALLOWED'
             OR NOT (p_document ? 'fetch' AND p_document ? 'storage_policy'
                     AND p_document ? 'display_policy' AND p_document ? 'download_policy'
                     AND p_document ? 'retention' AND p_document ? 'legal_hold_policy'
                     AND p_document ? 'automatic_publication' AND p_document ? 'slo') THEN
            RAISE EXCEPTION 'source policy governance fields are incomplete';
          END IF;
          IF EXISTS (
               SELECT 1 FROM unnest(ARRAY[
                 p_document->'robots_review',p_document->'terms_review',
                 p_document->'copyright_review'
               ]) review
                WHERE jsonb_typeof(review) <> 'object'
                   OR NOT review ?& ARRAY[
                     'result','evidence_url','evidence_sha256','checked_at'
                   ]
                   OR review - ARRAY[
                     'result','evidence_url','evidence_sha256','checked_at'
                   ] <> '{}'::jsonb
                   OR jsonb_typeof(review->'result') <> 'string'
                   OR jsonb_typeof(review->'evidence_url') <> 'string'
                   OR jsonb_typeof(review->'evidence_sha256') <> 'string'
                   OR jsonb_typeof(review->'checked_at') <> 'string'
                   OR review->>'evidence_url' !~ '^https?://[^[:space:]]+$'
                   OR length(review->>'evidence_url') > 2048
                   OR review->>'evidence_sha256' !~ '^[0-9a-f]{64}$'
                   OR review->>'checked_at' !~ '(Z|[+-][0-9]{2}:[0-9]{2})$'
                   OR (review->>'checked_at')::timestamptz > p_created_at
                   OR review->>'evidence_url' ~ '://[^/[:space:]]+@'
                   OR review->>'evidence_url' ~* '[?&](api[_-]?key|access[_-]?key|auth(entication|orization|_token)?|bearer|client[_-]?secret|cookie|credential|password|secret|session|signature|token)=[^&]+'
             ) OR jsonb_typeof(p_document->'fetch') IS DISTINCT FROM 'object'
               OR NOT (p_document->'fetch') ?& ARRAY[
                 'allowed_domains','minimum_interval_seconds',
                 'rate_limit_per_minute','user_agent'
               ]
               OR (p_document->'fetch') - ARRAY[
                 'allowed_domains','minimum_interval_seconds',
                 'rate_limit_per_minute','user_agent'
               ] <> '{}'::jsonb
               OR jsonb_typeof(p_document #> '{fetch,allowed_domains}')
                    IS DISTINCT FROM 'array'
               OR jsonb_array_length(p_document #> '{fetch,allowed_domains}') = 0
               OR jsonb_typeof(p_document #> '{fetch,minimum_interval_seconds}')
                    IS DISTINCT FROM 'number'
               OR jsonb_typeof(p_document #> '{fetch,rate_limit_per_minute}')
                    IS DISTINCT FROM 'number'
               OR jsonb_typeof(p_document #> '{fetch,user_agent}')
                    IS DISTINCT FROM 'string'
               OR (p_document #>> '{fetch,minimum_interval_seconds}')::integer < 1
               OR (p_document #>> '{fetch,rate_limit_per_minute}')::integer < 1
               OR length(p_document #>> '{fetch,user_agent}') < 1 THEN
            RAISE EXCEPTION 'source policy evidence or fetch controls are invalid';
          END IF;
          IF jsonb_array_length(p_document #> '{fetch,allowed_domains}') > 100
             OR EXISTS (
               SELECT 1
                 FROM jsonb_array_elements(p_document #> '{fetch,allowed_domains}') item
                WHERE jsonb_typeof(item) <> 'string'
                   OR source_v2_exact_dns_host(item #>> '{}') IS DISTINCT FROM true
             )
             OR jsonb_array_length(p_document #> '{fetch,allowed_domains}') <>
                (SELECT count(DISTINCT item #>> '{}')
                   FROM jsonb_array_elements(
                     p_document #> '{fetch,allowed_domains}'
                   ) item)
             OR (p_document #>> '{fetch,minimum_interval_seconds}')
                  !~ '^[0-9]{1,6}$'
             OR (p_document #>> '{fetch,minimum_interval_seconds}')::integer
                  NOT BETWEEN 1 AND 604800
             OR (p_document #>> '{fetch,rate_limit_per_minute}')
                  !~ '^[0-9]{1,5}$'
             OR (p_document #>> '{fetch,rate_limit_per_minute}')::integer
                  NOT BETWEEN 1 AND 10000
             OR length(p_document #>> '{fetch,user_agent}') NOT BETWEEN 1 AND 300
             OR p_document #>> '{fetch,user_agent}' ~ '[[:cntrl:]]' THEN
            RAISE EXCEPTION 'source policy fetch allowlist is invalid';
          END IF;
          IF p_document->>'storage_policy' NOT IN (
               'RAW_EVIDENCE_ALLOWED','METADATA_ONLY','LINK_ONLY'
             )
             OR p_document->>'display_policy' NOT IN (
               'METADATA_EXCERPT_LINK','OFFICIAL_READER_LINK','LINK_ONLY'
             )
             OR p_document->>'download_policy' NOT IN (
               'DISABLED','ORIGINAL_LINK_ONLY','SIGNED_INTERNAL_COPY'
             )
             OR p_document->>'legal_hold_policy' NOT IN (
               'SUPPORTED','NOT_APPLICABLE'
             )
             OR p_document->>'automatic_publication' NOT IN (
               'DISABLED','PUBLICATION_GATE_ELIGIBLE'
             )
             OR jsonb_typeof(p_document->'retention') <> 'object'
             OR NOT (p_document->'retention') ?& ARRAY[
               'retention_days','delete_after_retention'
             ]
             OR (p_document->'retention') - ARRAY[
               'retention_days','delete_after_retention'
             ] <> '{}'::jsonb
             OR jsonb_typeof(p_document #> '{retention,retention_days}') <> 'number'
             OR (p_document #>> '{retention,retention_days}') !~ '^[0-9]{1,5}$'
             OR (p_document #>> '{retention,retention_days}')::integer
                  NOT BETWEEN 1 AND 36500
             OR jsonb_typeof(p_document #> '{retention,delete_after_retention}')
                  <> 'boolean' THEN
            RAISE EXCEPTION 'source policy storage and retention controls are invalid';
          END IF;
          IF jsonb_typeof(p_document->'slo') IS DISTINCT FROM 'object'
             OR NOT (p_document->'slo') ?& ARRAY[
               'applicability','target_minutes','reason',
               'authorization_confirmed','technical_conditions_confirmed'
             ]
             OR (p_document->'slo') - ARRAY[
               'applicability','target_minutes','reason',
               'authorization_confirmed','technical_conditions_confirmed'
             ] <> '{}'::jsonb
             OR jsonb_typeof(p_document #> '{slo,applicability}') <> 'string'
             OR jsonb_typeof(p_document #> '{slo,authorization_confirmed}')
                  IS DISTINCT FROM 'boolean'
             OR jsonb_typeof(p_document #> '{slo,technical_conditions_confirmed}')
                  IS DISTINCT FROM 'boolean' THEN
            RAISE EXCEPTION 'source policy SLO controls are invalid';
          END IF;
          v_slo_applicability := p_document #>> '{slo,applicability}';
          IF v_slo_applicability = 'APPLICABLE' THEN
            IF jsonb_typeof(p_document #> '{slo,target_minutes}')
                   IS DISTINCT FROM 'number'
               OR (p_document #>> '{slo,target_minutes}') !~ '^[0-9]{1,5}$'
               OR (p_document #>> '{slo,target_minutes}')::integer
                    NOT BETWEEN 1 AND 10080
               OR p_document #>> '{slo,authorization_confirmed}' <> 'true'
               OR p_document #>> '{slo,technical_conditions_confirmed}' <> 'true' THEN
              RAISE EXCEPTION 'applicable source SLO lacks authorized technical evidence';
            END IF;
          ELSIF v_slo_applicability = 'NOT_APPLICABLE' THEN
            IF (
                 p_document #> '{slo,target_minutes}' IS NOT NULL
                 AND jsonb_typeof(p_document #> '{slo,target_minutes}') <> 'null'
               )
               OR jsonb_typeof(p_document #> '{slo,reason}')
                    IS DISTINCT FROM 'string'
               OR length(p_document #>> '{slo,reason}') NOT BETWEEN 1 AND 500
               OR p_document #>> '{slo,authorization_confirmed}' <> 'false'
               OR p_document #>> '{slo,technical_conditions_confirmed}' <> 'false' THEN
              RAISE EXCEPTION 'non-applicable source SLO requires a reason and no target';
            END IF;
          ELSE
            RAISE EXCEPTION 'source policy SLO applicability is invalid';
          END IF;
          v_document_sha256 := encode(digest(convert_to(
            p_document::text, 'UTF8'), 'sha256'), 'hex');
          INSERT INTO source_policy_version (
            id, source_id, schema_version, policy_version, status, document,
            document_sha256, valid_from, valid_until, submitted_by, created_at
          ) VALUES (
            p_policy_id, p_source_id, p_schema_version, p_policy_version,
            'PENDING_REVIEW', p_document, v_document_sha256, p_valid_from,
            p_valid_until, p_actor_id, p_created_at
          );
          PERFORM append_audit_event(
            p_audit_id, 'SOURCE_POLICY_SUBMITTED', p_actor_id, 'SOURCE_POLICY_VERSION',
            p_policy_id, NULL,
            jsonb_build_object('source_id',p_source_id,'policy_version',p_policy_version,
                               'document_sha256',v_document_sha256),
            p_reason, p_request_id, p_created_at
          );
          RETURN p_policy_id;
        END $$
        """
    )
    op.execute(
        """
        CREATE FUNCTION decide_source_policy_version(
          p_source_id uuid, p_policy_id uuid, p_decision_id uuid, p_outcome text,
          p_actor_id uuid, p_reason text, p_request_id text, p_audit_id uuid,
          p_decided_at timestamptz DEFAULT now()
        ) RETURNS uuid
        LANGUAGE plpgsql SECURITY DEFINER
        SET search_path = pg_catalog, public AS $$
        DECLARE
          v_submitter uuid;
          v_registered uuid;
          v_valid_until timestamptz;
          v_state text;
        BEGIN
          SELECT p.submitted_by, s.registered_by, p.valid_until, s.lifecycle_state
            INTO v_submitter, v_registered, v_valid_until, v_state
            FROM source_policy_version p JOIN source s ON s.id = p.source_id
           WHERE p.id = p_policy_id AND p.source_id = p_source_id
             AND p.valid_from <= p_decided_at AND p.valid_until > p_decided_at
           FOR UPDATE OF s;
          IF NOT FOUND THEN RAISE EXCEPTION 'current source policy does not exist'; END IF;
          IF source_v2_safe_audit_reason(p_reason) IS DISTINCT FROM true THEN
            RAISE EXCEPTION 'source governance reason is invalid';
          END IF;
          IF v_state NOT IN ('COMPLIANCE_REVIEW','TRIAL','PAUSED') THEN
            RAISE EXCEPTION 'source is not accepting policy decisions';
          END IF;
          IF p_outcome NOT IN ('APPROVED','REJECTED') THEN
            RAISE EXCEPTION 'source policy decision is invalid';
          END IF;
          IF p_actor_id = v_submitter OR p_actor_id IS NOT DISTINCT FROM v_registered THEN
            RAISE EXCEPTION 'source policy decision violates separation of duties';
          END IF;
          INSERT INTO source_governance_decision (
            id, source_id, decision_type, outcome, policy_version_id,
            submitted_by, decided_by, reason, valid_until, created_at
          ) VALUES (
            p_decision_id, p_source_id, 'COMPLIANCE', p_outcome, p_policy_id,
            v_submitter, p_actor_id, p_reason, v_valid_until, p_decided_at
          );
          IF p_outcome = 'APPROVED' THEN
            UPDATE source SET current_policy_version_id = p_policy_id,
              updated_at = p_decided_at WHERE id = p_source_id;
          END IF;
          PERFORM append_audit_event(
            p_audit_id, 'SOURCE_POLICY_' || p_outcome, p_actor_id,
            'SOURCE_POLICY_VERSION', p_policy_id,
            jsonb_build_object('status','PENDING_REVIEW'),
            jsonb_build_object('decision',p_outcome,'decision_id',p_decision_id),
            p_reason, p_request_id, p_decided_at
          );
          RETURN p_decision_id;
        END $$
        """
    )
    signatures = (
        "submit_source_policy_version(uuid,uuid,text,text,jsonb,timestamptz,timestamptz,uuid,text,text,uuid,timestamptz)",
        "decide_source_policy_version(uuid,uuid,uuid,text,uuid,text,text,uuid,timestamptz)",
    )
    for signature in signatures:
        op.execute(f"REVOKE ALL ON FUNCTION {signature} FROM PUBLIC")
        op.execute(f"GRANT EXECUTE ON FUNCTION {signature} TO srbg_api_role")


def _create_connector_config_write_boundary() -> None:
    op.execute(
        """
        CREATE FUNCTION save_source_connector_config(
          p_source_id uuid, p_config_id uuid, p_definition_id uuid,
          p_version_number integer, p_config_document jsonb, p_credential_ref text,
          p_supersedes_id uuid, p_actor_id uuid, p_reason text, p_request_id text,
          p_audit_id uuid,
          p_created_at timestamptz DEFAULT now()
        ) RETURNS uuid
        LANGUAGE plpgsql SECURITY DEFINER
        SET search_path = pg_catalog, public AS $$
        DECLARE
          v_policy_hosts text[];
          v_allowed_hosts text[];
          v_state text;
          v_policy_id uuid;
          v_next_version integer;
          v_latest_config uuid;
          v_connector_type text;
          v_definition_version text;
          v_schema_sha256 text;
          v_executor_key text;
          v_config_sha256 text;
          v_allowed_keys text[];
        BEGIN
          IF source_v2_safe_audit_reason(p_reason) IS DISTINCT FROM true THEN
            RAISE EXCEPTION 'source governance reason is invalid';
          END IF;
          SELECT s.lifecycle_state, p.id, ARRAY(
              SELECT jsonb_array_elements_text(p.document #> '{fetch,allowed_domains}')
            ) INTO v_state, v_policy_id, v_policy_hosts
            FROM source s JOIN source_policy_version p
              ON p.id = s.current_policy_version_id
           WHERE s.id = p_source_id AND p.valid_from <= p_created_at
             AND p.valid_until > p_created_at
             AND source_v2_policy_compliance_approved(
                   s.id,p.id,p_created_at
                 ) IS TRUE FOR UPDATE OF s;
          IF v_state NOT IN ('COMPLIANCE_REVIEW','TRIAL','PAUSED') THEN
            RAISE EXCEPTION 'source is not accepting connector configuration';
          END IF;
          SELECT connector_type, definition_version, schema_sha256, executor_key
            INTO v_connector_type, v_definition_version, v_schema_sha256, v_executor_key
            FROM connector_definition WHERE id=p_definition_id;
          IF NOT FOUND OR v_definition_version <> '1.0.0'
             OR v_executor_key <> 'builtin:' || lower(v_connector_type) || ':' || 'v1'
             OR v_schema_sha256 <> (CASE v_connector_type
               WHEN 'RSS_ATOM' THEN '4691b104889eeb16f6cb006d8284b6a8f5bb4b0c58ea2fd331ddf63f7eb2830d'
               WHEN 'JSON_API' THEN '73b72a68d11b0da0698871e34f80534b1386d6ce7500a27b57f3c3792ed38447'
               WHEN 'SITEMAP' THEN '7965a06972afb19af66f82ccbb5f21b7f4e88be33d64cc3548cff9cb62921ae5'
               WHEN 'LIST_DETAIL' THEN 'd6c892a10eb61d372e44f1156f48676fdd549027dcd91b20aaff4e1f01938ef6'
               WHEN 'DIRECT_PDF' THEN 'daa3e6ded77fd467da20f21961b84177eb6b84a2bd5e60adf45ab110012883b8'
               WHEN 'MANUAL_IMPORT' THEN '2abc649e1f15fbb452e27f452fca1eb27e5538bac2e7c07eaab42bd6345c860d'
               ELSE NULL END) THEN
            RAISE EXCEPTION 'connector definition is not server-approved';
          END IF;
          IF jsonb_typeof(p_config_document) <> 'object'
             OR jsonb_typeof(p_config_document->'allowed_hosts') <> 'array' THEN
            RAISE EXCEPTION 'connector configuration is not declarative';
          END IF;
          IF jsonb_array_length(p_config_document->'allowed_hosts') NOT BETWEEN 1 AND 32
             OR EXISTS (
               SELECT 1 FROM jsonb_array_elements(
                 p_config_document->'allowed_hosts'
               ) item
                WHERE jsonb_typeof(item) <> 'string'
             ) THEN
            RAISE EXCEPTION 'connector allowed hosts are invalid';
          END IF;
          SELECT array_agg(host ORDER BY host) INTO v_allowed_hosts
            FROM jsonb_array_elements_text(p_config_document->'allowed_hosts') host;
          IF v_allowed_hosts IS NULL
             OR cardinality(v_allowed_hosts) <> (
               SELECT count(DISTINCT host)
                 FROM jsonb_array_elements_text(p_config_document->'allowed_hosts') host
             ) OR EXISTS (
               SELECT 1 FROM unnest(v_allowed_hosts) host
                WHERE source_v2_exact_dns_host(host) IS DISTINCT FROM true
             ) OR v_policy_hosts IS NULL OR NOT (v_allowed_hosts <@ v_policy_hosts) THEN
            RAISE EXCEPTION 'connector hosts exceed the current source policy';
          END IF;
          IF p_config_document ? 'credential_ref' THEN
            RAISE EXCEPTION 'credential reference must be stored separately';
          END IF;
          IF p_credential_ref IS NOT NULL AND p_credential_ref !~
             '^vault://source-connectors/[A-Za-z0-9][A-Za-z0-9/_-]{0,190}$' THEN
            RAISE EXCEPTION 'connector credential reference is invalid';
          END IF;
          v_allowed_keys := CASE v_connector_type
            WHEN 'RSS_ATOM' THEN ARRAY['allowed_hosts','feed_url']
            WHEN 'JSON_API' THEN ARRAY[
              'allowed_hosts','endpoint_url','items_pointer','field_pointers','pagination'
            ]
            WHEN 'SITEMAP' THEN ARRAY['allowed_hosts','sitemap_url']
            WHEN 'LIST_DETAIL' THEN ARRAY[
              'allowed_hosts','list_url','item_selector','link_selector',
              'title_selector','published_selector'
            ]
            WHEN 'DIRECT_PDF' THEN ARRAY['allowed_hosts','document_urls']
            WHEN 'MANUAL_IMPORT' THEN ARRAY[
              'allowed_hosts','url_import_enabled','file_import_enabled','allowed_file_types'
            ] END;
          IF EXISTS (
               SELECT 1
                 FROM jsonb_object_keys(p_config_document) keys(key_name)
                WHERE NOT (key_name = ANY(v_allowed_keys))
             ) THEN
            RAISE EXCEPTION 'connector configuration contains unknown fields';
          END IF;
          IF EXISTS (
               SELECT 1 FROM jsonb_path_query(
                 p_config_document,
                 'strict $.** ? (@.type() == "string")'
               ) strings(value)
                WHERE position('{{' in value #>> '{}') > 0
                   OR position('}}' in value #>> '{}') > 0
                   OR position('${' in value #>> '{}') > 0
                   OR position('{%' in value #>> '{}') > 0
                   OR position('%}' in value #>> '{}') > 0
                   OR position('<%' in value #>> '{}') > 0
                   OR position('%>' in value #>> '{}') > 0
                   OR lower(value #>> '{}') LIKE '%javascript:%'
                   OR lower(value #>> '{}') LIKE '%file:%'
                   OR lower(value #>> '{}') LIKE '%gopher:%'
             ) THEN
            RAISE EXCEPTION 'connector configuration contains executable fields';
          END IF;
          IF v_connector_type='RSS_ATOM' AND (
               jsonb_typeof(p_config_document->'feed_url') IS DISTINCT FROM 'string'
               OR source_v2_safe_http_url(
                    p_config_document->>'feed_url',v_allowed_hosts
                  ) IS DISTINCT FROM true
             ) THEN
            RAISE EXCEPTION 'RSS connector configuration is invalid';
          END IF;
          IF v_connector_type='SITEMAP' AND (
               jsonb_typeof(p_config_document->'sitemap_url')
                 IS DISTINCT FROM 'string'
               OR source_v2_safe_http_url(
                    p_config_document->>'sitemap_url',v_allowed_hosts
                  ) IS DISTINCT FROM true
             ) THEN
            RAISE EXCEPTION 'Sitemap connector configuration is invalid';
          END IF;
          IF v_connector_type='JSON_API' THEN
            IF jsonb_typeof(p_config_document->'endpoint_url')
                   IS DISTINCT FROM 'string'
               OR source_v2_safe_http_url(
                    p_config_document->>'endpoint_url',v_allowed_hosts
                  ) IS DISTINCT FROM true
               OR jsonb_typeof(p_config_document->'items_pointer')
                    IS DISTINCT FROM 'string'
               OR jsonb_typeof(p_config_document->'field_pointers')
                    IS DISTINCT FROM 'object'
               OR jsonb_typeof(p_config_document->'pagination')
                    IS DISTINCT FROM 'string'
               OR p_config_document->>'pagination' <> 'NONE'
               OR NOT ((p_config_document->'field_pointers') ?&
                    ARRAY['external_id','url','title']) THEN
              RAISE EXCEPTION 'JSON API configuration is not declarative';
            END IF;
            IF EXISTS (
                 SELECT 1
                   FROM jsonb_object_keys(p_config_document->'field_pointers') key
                  WHERE NOT key = ANY(ARRAY[
                    'external_id','url','title','published_at'
                  ])
               ) OR EXISTS (
                 SELECT 1 FROM (
                   SELECT p_config_document->'items_pointer' AS pointer
                   UNION ALL
                   SELECT value AS pointer
                     FROM jsonb_each(p_config_document->'field_pointers')
                 ) pointers
                  WHERE jsonb_typeof(pointer) <> 'string'
                     OR length(pointer #>> '{}') NOT BETWEEN 1 AND 300
                     OR pointer #>> '{}' !~ '^/'
                     OR pointer #>> '{}' ~ '~([^01]|$)'
               ) THEN
              RAISE EXCEPTION 'JSON API pointers are invalid';
            END IF;
          END IF;
          IF v_connector_type='LIST_DETAIL' THEN
            IF jsonb_typeof(p_config_document->'list_url')
                   IS DISTINCT FROM 'string'
               OR source_v2_safe_http_url(
                    p_config_document->>'list_url',v_allowed_hosts
                  ) IS DISTINCT FROM true
               OR NOT (p_config_document ? 'item_selector'
                       AND p_config_document ? 'link_selector'
                       AND p_config_document ? 'title_selector') THEN
              RAISE EXCEPTION 'list/detail connector configuration is incomplete';
            END IF;
            IF EXISTS (
                 SELECT 1 FROM jsonb_each(p_config_document) entry
                  WHERE entry.key = ANY(ARRAY[
                    'item_selector','link_selector','title_selector',
                    'published_selector'
                  ]) AND (
                    jsonb_typeof(entry.value) <> 'string'
                    OR length(entry.value #>> '{}') NOT BETWEEN 1 AND 100
                    OR entry.value #>> '{}' !~
                       '^([a-z][a-z0-9-]*)?([.#][A-Za-z_][A-Za-z0-9_-]*)?$'
                  )
               ) THEN
              RAISE EXCEPTION 'list/detail selectors are invalid';
            END IF;
          END IF;
          IF v_connector_type='DIRECT_PDF' THEN
            IF jsonb_typeof(p_config_document->'document_urls')
                   IS DISTINCT FROM 'array'
               OR jsonb_array_length(p_config_document->'document_urls')
                    NOT BETWEEN 1 AND 100 THEN
              RAISE EXCEPTION 'direct PDF URL list is invalid';
            END IF;
            IF EXISTS (
                 SELECT 1 FROM jsonb_array_elements(
                   p_config_document->'document_urls'
                 ) item
                  WHERE jsonb_typeof(item) <> 'string'
                     OR source_v2_safe_http_url(
                          item #>> '{}',v_allowed_hosts
                        ) IS DISTINCT FROM true
               ) OR jsonb_array_length(p_config_document->'document_urls') <>
                    (SELECT count(DISTINCT item #>> '{}')
                       FROM jsonb_array_elements(
                         p_config_document->'document_urls'
                       ) item) THEN
              RAISE EXCEPTION 'direct PDF URLs are invalid';
            END IF;
          END IF;
          IF v_connector_type='MANUAL_IMPORT' THEN
            IF jsonb_typeof(p_config_document->'url_import_enabled')
                   IS DISTINCT FROM 'boolean'
               OR jsonb_typeof(p_config_document->'file_import_enabled')
                    IS DISTINCT FROM 'boolean'
               OR jsonb_typeof(p_config_document->'allowed_file_types')
                    IS DISTINCT FROM 'array'
               OR jsonb_array_length(p_config_document->'allowed_file_types')
                    NOT BETWEEN 1 AND 3
               OR (
                    p_config_document->>'url_import_enabled' <> 'true'
                    AND p_config_document->>'file_import_enabled' <> 'true'
                  ) THEN
              RAISE EXCEPTION 'manual import configuration is invalid';
            END IF;
            IF EXISTS (
                 SELECT 1 FROM jsonb_array_elements(
                   p_config_document->'allowed_file_types'
                 ) item
                  WHERE jsonb_typeof(item) <> 'string'
                     OR NOT (item #>> '{}' = ANY(ARRAY['HTML','PDF','ZIP']))
               ) OR jsonb_array_length(p_config_document->'allowed_file_types') <>
                    (SELECT count(DISTINCT item #>> '{}')
                       FROM jsonb_array_elements(
                         p_config_document->'allowed_file_types'
                       ) item) THEN
              RAISE EXCEPTION 'manual import file types are invalid';
            END IF;
          END IF;
          SELECT COALESCE(max(version_number),0)+1,
                 (array_agg(id ORDER BY version_number DESC))[1]
            INTO v_next_version, v_latest_config
            FROM connector_config_version WHERE source_id = p_source_id;
          IF p_version_number <> v_next_version
             OR p_supersedes_id IS DISTINCT FROM v_latest_config THEN
            RAISE EXCEPTION 'connector configuration version is stale';
          END IF;
          v_config_sha256 := encode(digest(convert_to(
            jsonb_build_object(
              'connector_definition_id',p_definition_id,
              'schema_sha256',v_schema_sha256,
              'config',p_config_document,
              'credential_ref',p_credential_ref
            )::text, 'UTF8'), 'sha256'), 'hex');
          INSERT INTO connector_config_version (
            id, source_id, connector_definition_id, policy_version_id,
            version_number, config_document,
            config_sha256, allowed_hosts, credential_ref, validation_status,
            validation_reason_codes, supersedes_id, created_by, created_at
          ) VALUES (
            p_config_id, p_source_id, p_definition_id, v_policy_id, v_next_version,
            p_config_document, v_config_sha256, v_allowed_hosts, p_credential_ref,
            'VALID', ARRAY[]::text[], p_supersedes_id,
            p_actor_id, p_created_at
          );
          UPDATE source SET current_connector_config_version_id = p_config_id,
            updated_at = p_created_at WHERE id = p_source_id;
          PERFORM append_audit_event(
            p_audit_id, 'SOURCE_CONNECTOR_CONFIG_SAVED', p_actor_id,
            'CONNECTOR_CONFIG_VERSION', p_config_id, NULL,
            jsonb_build_object('source_id',p_source_id,'config_sha256',v_config_sha256,
                               'credential_configured',p_credential_ref IS NOT NULL),
            p_reason, p_request_id, p_created_at
          );
          RETURN p_config_id;
        END $$
        """
    )
    signature = "save_source_connector_config(uuid,uuid,uuid,integer,jsonb,text,uuid,uuid,text,text,uuid,timestamptz)"
    op.execute(f"REVOKE ALL ON FUNCTION {signature} FROM PUBLIC")
    op.execute(f"GRANT EXECUTE ON FUNCTION {signature} TO srbg_api_role")


def _create_trial_write_boundaries() -> None:
    op.execute(
        """
        CREATE FUNCTION append_source_trial_rejected_raw_attempt(
          p_attempt_id uuid,p_source_id uuid,p_trial_id uuid,p_raw_object_id uuid,
          p_content_sha256 text,p_object_key text,p_canonical_url text,
          p_reason_code text,p_actor_id uuid,p_request_id text,
          p_occurred_at timestamptz DEFAULT now()
        ) RETURNS uuid
        LANGUAGE plpgsql SECURITY DEFINER
        SET search_path = pg_catalog, public AS $$
        DECLARE
          v_allowed_hosts text[];
          v_arrived_after_close boolean;
        BEGIN
          SELECT config.allowed_hosts,
                 NOT (
                   source_row.lifecycle_state='TRIAL'
                   AND source_row.trial_kind='FIXTURE_REPLAY'
                   AND source_row.current_trial_run_id=trial.id
                   AND NOT EXISTS (
                     SELECT 1 FROM source_trial_run_result result
                      WHERE result.trial_run_id=trial.id
                   )
                 )
            INTO v_allowed_hosts,v_arrived_after_close
            FROM source source_row
            JOIN source_trial_run trial
              ON trial.id=p_trial_id AND trial.source_id=source_row.id
             AND trial.kind='FIXTURE_REPLAY' AND trial.execution_domain='FIXTURE'
            JOIN connector_config_version config
              ON config.id=trial.connector_config_version_id
             AND config.source_id=trial.source_id
           WHERE source_row.id=p_source_id
           FOR UPDATE OF source_row,trial;
          IF NOT FOUND
             OR p_content_sha256 !~ '^[0-9a-f]{64}$'
             OR p_object_key <> 'sha256/' || left(p_content_sha256,2) || '/'
                                || p_content_sha256
             OR source_v2_safe_http_url(
                  p_canonical_url,v_allowed_hosts
                ) IS DISTINCT FROM true
             OR p_reason_code !~ '^[A-Z0-9_]{1,100}$'
             OR length(p_request_id) NOT BETWEEN 1 AND 100 THEN
            RAISE EXCEPTION 'rejected fixture attempt evidence is invalid';
          END IF;
          IF p_raw_object_id IS NOT NULL AND NOT EXISTS (
               SELECT 1 FROM raw_object raw
                WHERE raw.id=p_raw_object_id AND raw.sha256=p_content_sha256
             ) THEN
            RAISE EXCEPTION 'rejected fixture raw identity is invalid';
          END IF;
          INSERT INTO source_trial_rejected_raw_attempt(
            id,source_id,trial_run_id,raw_object_id,content_sha256,object_key,
            canonical_url,canonical_url_sha256,reason_code,arrived_after_close,
            actor_id,request_id,occurred_at
          ) VALUES (
            p_attempt_id,p_source_id,p_trial_id,p_raw_object_id,p_content_sha256,
            p_object_key,p_canonical_url,
            encode(digest(convert_to(p_canonical_url,'UTF8'),'sha256'),'hex'),
            p_reason_code,v_arrived_after_close,p_actor_id,p_request_id,p_occurred_at
          );
          PERFORM append_audit_event(
            p_attempt_id,'SOURCE_TRIAL_RAW_REJECTED',p_actor_id,
            'SOURCE_TRIAL_REJECTED_RAW_ATTEMPT',p_attempt_id,NULL,
            jsonb_build_object(
              'source_id',p_source_id,'trial_run_id',p_trial_id,
              'raw_object_id',p_raw_object_id,
              'canonical_url_sha256',encode(digest(
                convert_to(p_canonical_url,'UTF8'),'sha256'),'hex'),
              'reason_code',p_reason_code,
              'arrived_after_close',v_arrived_after_close
            ),'fixture rejected by bounded security policy',p_request_id,
            p_occurred_at
          );
          RETURN p_attempt_id;
        END $$
        """
    )
    rejected_signature = (
        "append_source_trial_rejected_raw_attempt("
        "uuid,uuid,uuid,uuid,text,text,text,text,uuid,text,timestamptz)"
    )
    op.execute(f"REVOKE ALL ON FUNCTION {rejected_signature} FROM PUBLIC")
    op.execute(f"GRANT EXECUTE ON FUNCTION {rejected_signature} TO srbg_api_role")
    op.execute(
        """
        CREATE FUNCTION append_source_trial_raw_capture(
          p_capture_id uuid, p_raw_object_id uuid, p_source_id uuid,
          p_trial_id uuid, p_execution_domain text, p_requested_url text,
          p_final_url text, p_redirect_chain jsonb, p_http_status integer,
          p_etag text, p_last_modified text, p_response_sha256 text,
          p_captured_at timestamptz DEFAULT now()
        ) RETURNS uuid
        LANGUAGE plpgsql SECURITY DEFINER
        SET search_path = pg_catalog, public AS $$
        DECLARE
          v_trial_domain text;
          v_allowed_hosts text[];
          v_arrived_after_close boolean;
        BEGIN
          SELECT r.execution_domain, config.allowed_hosts,
                 NOT (
                   source_row.lifecycle_state='TRIAL'
                   AND source_row.current_trial_run_id=r.id
                   AND source_row.trial_kind=r.kind
                   AND NOT EXISTS (
                     SELECT 1 FROM source_trial_run_result result
                      WHERE result.trial_run_id=r.id
                   )
                 )
            INTO v_trial_domain, v_allowed_hosts, v_arrived_after_close
            FROM source source_row
            JOIN source_trial_run r
              ON r.id=p_trial_id AND r.source_id=source_row.id
            JOIN raw_object raw ON raw.id=p_raw_object_id
            JOIN connector_config_version config
              ON config.id=r.connector_config_version_id
             AND config.source_id=r.source_id
           WHERE source_row.id=p_source_id
             AND raw.scan_status='CLEAN'
             AND EXISTS (
               SELECT 1 FROM raw_object_security_fact security
                WHERE security.raw_object_id=raw.id AND security.status='CLEAN'
             )
             AND NOT EXISTS (
               SELECT 1 FROM raw_object_security_fact security
                WHERE security.raw_object_id=raw.id
                  AND security.status IN ('REJECTED','QUARANTINED')
             )
           FOR UPDATE OF source_row,r;
          IF NOT FOUND OR v_trial_domain <> p_execution_domain
             OR p_execution_domain NOT IN ('FIXTURE','TRIAL')
             OR p_response_sha256 !~ '^[0-9a-f]{64}$'
             OR p_http_status NOT BETWEEN 100 AND 599
             OR length(p_requested_url) NOT BETWEEN 8 AND 2048
             OR length(p_final_url) NOT BETWEEN 8 AND 2048
             OR source_v2_safe_http_url(
                  p_requested_url,v_allowed_hosts
                ) IS DISTINCT FROM true
             OR source_v2_safe_http_url(
                  p_final_url,v_allowed_hosts
                ) IS DISTINCT FROM true
             OR jsonb_typeof(p_redirect_chain) IS DISTINCT FROM 'array' THEN
            RAISE EXCEPTION 'source trial raw capture is invalid';
          END IF;
          IF jsonb_array_length(p_redirect_chain) > 10
             OR EXISTS (
               SELECT 1 FROM jsonb_array_elements(p_redirect_chain) item
                WHERE jsonb_typeof(item) <> 'string'
                   OR source_v2_safe_http_url(
                        item #>> '{}',v_allowed_hosts
                      ) IS DISTINCT FROM true
             ) THEN
            RAISE EXCEPTION 'source trial redirect evidence is invalid';
          END IF;
          INSERT INTO raw_object_capture (
            id,raw_object_id,source_id,fetch_run_id,trial_run_id,execution_domain,
            requested_url,final_url,redirect_chain,http_status,etag,last_modified,
            response_sha256,arrived_after_close,captured_at
          ) VALUES (
            p_capture_id,p_raw_object_id,p_source_id,NULL,p_trial_id,
            p_execution_domain,p_requested_url,p_final_url,p_redirect_chain,
            p_http_status,p_etag,p_last_modified,p_response_sha256,
            v_arrived_after_close,p_captured_at
          );
          RETURN p_capture_id;
        END $$
        """
    )
    capture_signature = "append_source_trial_raw_capture(uuid,uuid,uuid,uuid,text,text,text,jsonb,integer,text,text,text,timestamptz)"
    op.execute(f"REVOKE ALL ON FUNCTION {capture_signature} FROM PUBLIC")
    op.execute(f"GRANT EXECUTE ON FUNCTION {capture_signature} TO srbg_api_role, srbg_worker_role")
    op.execute(
        """
        CREATE FUNCTION start_source_trial_run(
          p_source_id uuid, p_trial_id uuid, p_kind text, p_policy_id uuid,
          p_config_id uuid, p_decision_id uuid, p_actor_id uuid, p_reason text,
          p_request_id text, p_event_id uuid, p_audit_id uuid,
          p_created_at timestamptz DEFAULT now()
        ) RETURNS uuid
        LANGUAGE plpgsql SECURITY DEFINER
        SET search_path = pg_catalog, public AS $$
        DECLARE
          v_state text;
          v_policy_submitter uuid;
          v_config_submitter uuid;
          v_registered uuid;
          v_compliance_approver uuid;
        BEGIN
          IF source_v2_safe_audit_reason(p_reason) IS DISTINCT FROM true THEN
            RAISE EXCEPTION 'source governance reason is invalid';
          END IF;
          SELECT s.lifecycle_state, s.registered_by, p.submitted_by, c.created_by,
                 compliance.decided_by
            INTO v_state, v_registered, v_policy_submitter, v_config_submitter,
                 v_compliance_approver
            FROM source s
            JOIN source_policy_version p ON p.id = s.current_policy_version_id
            JOIN connector_config_version c
              ON c.id = s.current_connector_config_version_id
             AND c.source_id=s.id AND c.policy_version_id=p.id
            JOIN LATERAL (
              SELECT d.decided_by,d.outcome,d.valid_until
                FROM source_governance_decision d
               WHERE d.source_id=s.id AND d.policy_version_id=p.id
                 AND d.decision_type='COMPLIANCE'
               ORDER BY d.created_at DESC,d.id DESC LIMIT 1
            ) compliance ON true
           WHERE s.id = p_source_id AND p.id = p_policy_id AND c.id = p_config_id
             AND p.source_id = s.id AND c.source_id = s.id
             AND p.valid_from <= p_created_at AND p.valid_until > p_created_at
             AND c.validation_status = 'VALID'
             AND s.governance_owner_id IS NOT NULL
             AND compliance.outcome='APPROVED'
             AND (compliance.valid_until IS NULL
                  OR compliance.valid_until > p_created_at)
             AND source_v2_policy_compliance_approved(
                   s.id,p.id,p_created_at
                 ) IS TRUE
           FOR UPDATE OF s;
          IF NOT FOUND OR v_state NOT IN ('COMPLIANCE_REVIEW','TRIAL','PAUSED') THEN
            RAISE EXCEPTION 'source is not ready for trial';
          END IF;
          IF v_state='TRIAL' AND EXISTS (
               SELECT 1 FROM source current_source
               JOIN source_trial_run current_run
                 ON current_run.id=current_source.current_trial_run_id
               LEFT JOIN source_trial_run_result current_result
                 ON current_result.trial_run_id=current_run.id
              WHERE current_source.id=p_source_id
                AND current_result.trial_run_id IS NULL
             ) THEN
            RAISE EXCEPTION 'current source trial is still pending';
          END IF;
          IF p_kind NOT IN ('FIXTURE_REPLAY','LIVE_TRIAL') THEN
            RAISE EXCEPTION 'source trial kind is invalid';
          END IF;
          IF p_kind = 'LIVE_TRIAL' THEN
            IF p_actor_id = v_policy_submitter OR p_actor_id = v_config_submitter
               OR p_actor_id = v_compliance_approver
               OR p_actor_id IS NOT DISTINCT FROM v_registered THEN
              RAISE EXCEPTION 'live trial authorization violates separation of duties';
            END IF;
            INSERT INTO source_governance_decision (
              id, source_id, decision_type, outcome, policy_version_id,
              connector_config_version_id, submitted_by, decided_by, reason,
              valid_until, created_at
            ) VALUES (
              p_decision_id, p_source_id, 'LIVE_TRIAL_AUTHORIZATION', 'APPROVED',
              p_policy_id, p_config_id, v_config_submitter, p_actor_id, p_reason,
              p_created_at + interval '7 days', p_created_at
            );
          END IF;
          INSERT INTO source_trial_run (
            id, source_id, kind, execution_domain, policy_version_id,
            connector_config_version_id, authorization_decision_id, requested_by,
            request_reason, created_at
          ) VALUES (
            p_trial_id, p_source_id, p_kind,
            CASE WHEN p_kind = 'FIXTURE_REPLAY' THEN 'FIXTURE' ELSE 'TRIAL' END,
            p_policy_id, p_config_id,
            CASE WHEN p_kind = 'LIVE_TRIAL' THEN p_decision_id ELSE NULL END,
            p_actor_id, p_reason, p_created_at
          );
          UPDATE source SET lifecycle_state = 'TRIAL', trial_kind = p_kind,
            current_trial_run_id = p_trial_id, updated_at = p_created_at
           WHERE id = p_source_id;
          INSERT INTO source_lifecycle_event (
            id, source_id, from_state, to_state, action, reason_code, reason,
            actor_id, policy_version_id, governance_decision_id, created_at
          ) VALUES (
            p_event_id, p_source_id, v_state, 'TRIAL',
            CASE WHEN p_kind = 'FIXTURE_REPLAY' THEN 'START_FIXTURE_TRIAL'
                 ELSE 'START_LIVE_TRIAL' END,
            'TRIAL_AUTHORIZED', p_reason, p_actor_id, p_policy_id,
            CASE WHEN p_kind = 'LIVE_TRIAL' THEN p_decision_id ELSE NULL END,
            p_created_at
          );
          PERFORM append_audit_event(
            p_audit_id, 'SOURCE_TRIAL_STARTED', p_actor_id, 'SOURCE_TRIAL_RUN',
            p_trial_id, jsonb_build_object('lifecycle_state',v_state),
            jsonb_build_object('lifecycle_state','TRIAL','trial_kind',p_kind),
            p_reason, p_request_id, p_created_at
          );
          RETURN p_trial_id;
        END $$
        """
    )
    op.execute(
        """
        CREATE FUNCTION record_source_fixture_replay_result(
          p_trial_id uuid, p_source_id uuid, p_connector_config_version_id uuid,
          p_status text, p_reason_code text, p_raw_capture_count integer,
          p_document_count integer, p_transport_call_count integer,
          p_evaluated_by uuid, p_created_at timestamptz DEFAULT now()
        ) RETURNS uuid
        LANGUAGE plpgsql SECURITY DEFINER
        SET search_path = pg_catalog, public AS $$
        DECLARE
          v_pending_trial_id uuid;
          v_database_raw_capture_count integer;
        BEGIN
          SELECT trial.id INTO v_pending_trial_id
            FROM source source_row
            JOIN source_trial_run trial
              ON trial.id=p_trial_id AND trial.source_id=source_row.id
            JOIN connector_config_version config
              ON config.id=trial.connector_config_version_id
             AND config.source_id=trial.source_id
           WHERE source_row.id=p_source_id
             AND source_row.lifecycle_state='TRIAL'
             AND source_row.trial_kind='FIXTURE_REPLAY'
             AND source_row.current_trial_run_id=trial.id
             AND source_row.current_connector_config_version_id=trial.connector_config_version_id
             AND trial.kind='FIXTURE_REPLAY'
             AND trial.execution_domain='FIXTURE'
             AND trial.connector_config_version_id=p_connector_config_version_id
             AND config.id=p_connector_config_version_id
             AND NOT EXISTS (
               SELECT 1 FROM source_trial_run_result completed
                WHERE completed.trial_run_id=trial.id
             )
             AND NOT EXISTS (
               SELECT 1 FROM source_fixture_replay_result existing
                WHERE existing.trial_run_id=trial.id
             )
           FOR UPDATE OF source_row,trial;
          IF NOT FOUND THEN
            RAISE EXCEPTION 'fixture replay result is not authorized for the current trial';
          END IF;
          IF p_status NOT IN ('PASSED','FAILED')
             OR p_reason_code !~ '^[A-Z0-9_]{1,100}$'
             OR p_raw_capture_count < 0 OR p_document_count < 0
             OR p_transport_call_count < 0 OR p_evaluated_by IS NULL
             OR p_created_at IS NULL
             OR (p_status='PASSED' AND (p_raw_capture_count=0 OR p_document_count=0)) THEN
            RAISE EXCEPTION 'fixture replay result is invalid';
          END IF;
          SELECT count(*)::integer INTO v_database_raw_capture_count
            FROM raw_object_capture
           WHERE trial_run_id=p_trial_id
             AND source_id=p_source_id
             AND execution_domain='FIXTURE'
             AND arrived_after_close=false;
          IF v_database_raw_capture_count <> p_raw_capture_count THEN
            RAISE EXCEPTION 'fixture replay raw capture count is not database-derived';
          END IF;
          INSERT INTO source_fixture_replay_result (
            trial_run_id,source_id,connector_config_version_id,status,reason_code,
            raw_capture_count,document_count,transport_call_count,evaluated_by,created_at
          ) VALUES (
            p_trial_id,p_source_id,p_connector_config_version_id,p_status,p_reason_code,
            p_raw_capture_count,p_document_count,p_transport_call_count,p_evaluated_by,
            p_created_at
          );
          RETURN p_trial_id;
        END $$
        """
    )
    op.execute(
        """
        CREATE FUNCTION source_trial_quality_summary(p_trial_id uuid)
        RETURNS jsonb
        LANGUAGE plpgsql STABLE SECURITY DEFINER
        SET search_path = pg_catalog, public AS $$
        DECLARE
          v_source_id uuid;
          v_domain text;
          v_document_raw_count integer;
          v_rejected_raw_attempt_count integer;
          v_ready_count integer;
          v_parse_failed_count integer;
          v_security_failed_count integer;
          v_ready_ratio_bps integer;
          v_replay_status text;
        BEGIN
          SELECT source_id,execution_domain INTO v_source_id,v_domain
            FROM source_trial_run WHERE id=p_trial_id;
          IF NOT FOUND THEN RAISE EXCEPTION 'source trial does not exist'; END IF;
          SELECT replay.status INTO v_replay_status
            FROM source_fixture_replay_result replay
           WHERE replay.trial_run_id=p_trial_id;
          WITH document_raw AS (
            SELECT DISTINCT capture.raw_object_id
              FROM raw_object_capture capture
             WHERE capture.trial_run_id=p_trial_id
               AND capture.source_id=v_source_id
               AND capture.execution_domain=v_domain
               AND EXISTS (
                 SELECT 1
                   FROM document_version version
                   JOIN document linked_document
                     ON linked_document.id=version.document_id
                    AND linked_document.source_id=v_source_id
                  WHERE version.raw_object_id=capture.raw_object_id
                    AND version.execution_domain=capture.execution_domain
               )
          ), latest_states AS (
            SELECT document_raw.raw_object_id,
                   CASE WHEN EXISTS (
                     SELECT 1 FROM raw_object raw
                      WHERE raw.id=document_raw.raw_object_id
                        AND (
                          raw.scan_status <> 'CLEAN'
                          OR EXISTS (
                            SELECT 1 FROM raw_object_security_fact negative
                             WHERE negative.raw_object_id=raw.id
                               AND negative.status IN ('REJECTED','QUARANTINED')
                          )
                        )
                   ) THEN 'QUARANTINED'
                     WHEN v_replay_status='FAILED' THEN 'FAILED'
                     ELSE (
                       SELECT event.state
                         FROM document_version version
                         JOIN document linked_document
                           ON linked_document.id=version.document_id
                          AND linked_document.source_id=v_source_id
                         JOIN document_version_state_event event
                           ON event.document_version_id=version.id
                        WHERE version.raw_object_id=document_raw.raw_object_id
                          AND version.execution_domain=v_domain
                        ORDER BY event.created_at DESC,event.id DESC
                        LIMIT 1
                     ) END AS state
              FROM document_raw
          )
          SELECT count(*)::integer,
                 count(*) FILTER (WHERE state='READY')::integer,
                 count(*) FILTER (WHERE state='FAILED')::integer,
                 count(*) FILTER (WHERE state='QUARANTINED')::integer
            INTO v_document_raw_count,v_ready_count,v_parse_failed_count,
                 v_security_failed_count
            FROM latest_states;
          SELECT count(*)::integer INTO v_rejected_raw_attempt_count
            FROM source_trial_rejected_raw_attempt rejected
           WHERE rejected.trial_run_id=p_trial_id
             AND rejected.source_id=v_source_id;
          v_security_failed_count :=
            v_security_failed_count + v_rejected_raw_attempt_count;
          v_ready_ratio_bps := CASE
            WHEN v_document_raw_count=0 THEN 0
            ELSE (
              (v_ready_count::bigint * 10000 + v_document_raw_count / 2)
              / v_document_raw_count
            )::integer
          END;
          RETURN jsonb_build_object(
            'raw_count',v_document_raw_count,
            'ready_count',v_ready_count,
            'parse_failed_count',v_parse_failed_count,
            'security_failed_count',v_security_failed_count,
            'rejected_raw_attempt_count',v_rejected_raw_attempt_count,
            'ready_ratio_bps',v_ready_ratio_bps
          );
        END $$
        """
    )
    op.execute(
        """
        CREATE FUNCTION complete_source_trial_run(
          p_trial_id uuid, p_status text, p_quality_summary jsonb,
          p_raw_namespace text, p_actor_id uuid,
          p_completed_at timestamptz DEFAULT now()
        ) RETURNS uuid
        LANGUAGE plpgsql SECURITY DEFINER
        SET search_path = pg_catalog, public AS $$
        DECLARE
          v_kind text;
          v_source_id uuid;
          v_domain text;
          v_authorization_id uuid;
          v_document_raw_count integer;
          v_rejected_raw_attempt_count integer;
          v_raw_count integer;
          v_ready_count integer;
          v_parse_failed_count integer;
          v_security_failed_count integer;
          v_ready_ratio_bps integer;
          v_quality_summary jsonb;
          v_replay_status text;
        BEGIN
          SELECT trial.kind,trial.source_id,trial.execution_domain,
                 trial.authorization_decision_id,replay.status
            INTO v_kind,v_source_id,v_domain,v_authorization_id,v_replay_status
            FROM source_trial_run trial
            LEFT JOIN source_fixture_replay_result replay
              ON replay.trial_run_id=trial.id
           WHERE trial.id = p_trial_id FOR UPDATE OF trial;
          IF NOT FOUND OR p_status NOT IN ('SUCCEEDED','FAILED','CANCELLED') THEN
            RAISE EXCEPTION 'source trial result is invalid';
          END IF;
          IF (v_kind = 'FIXTURE_REPLAY' AND p_raw_namespace NOT LIKE
                'fixture/' || p_trial_id::text || '/%')
             OR (v_kind = 'LIVE_TRIAL' AND p_raw_namespace NOT LIKE
                'trial/' || p_trial_id::text || '/%') THEN
            RAISE EXCEPTION 'source trial result namespace is invalid';
          END IF;
          IF p_status='SUCCEEDED' AND NOT EXISTS (
               SELECT 1 FROM raw_object_capture capture
                WHERE capture.source_id=v_source_id
                  AND capture.trial_run_id=p_trial_id
                  AND capture.execution_domain=v_domain
             ) THEN
            RAISE EXCEPTION 'successful source trial requires captured raw evidence';
          END IF;
          IF v_kind='LIVE_TRIAL' AND NOT EXISTS (
               SELECT 1 FROM source_governance_decision auth_decision
                WHERE auth_decision.id=v_authorization_id
                  AND auth_decision.source_id=v_source_id
                  AND auth_decision.decision_type='LIVE_TRIAL_AUTHORIZATION'
                  AND auth_decision.outcome='APPROVED'
                  AND (auth_decision.valid_until IS NULL
                       OR auth_decision.valid_until > p_completed_at)
             ) THEN
            RAISE EXCEPTION 'live trial authorization is absent or expired';
          END IF;
          IF v_kind='FIXTURE_REPLAY' AND p_status<>'CANCELLED'
             AND v_replay_status IS NULL THEN
            RAISE EXCEPTION 'fixture replay completion requires replay evidence';
          END IF;
          WITH document_raw AS (
            SELECT DISTINCT capture.raw_object_id
              FROM raw_object_capture capture
             WHERE capture.trial_run_id=p_trial_id
               AND capture.source_id=v_source_id
               AND capture.execution_domain=v_domain
               AND EXISTS (
                 SELECT 1
                   FROM document_version version
                   JOIN document linked_document
                     ON linked_document.id=version.document_id
                    AND linked_document.source_id=v_source_id
                  WHERE version.raw_object_id=capture.raw_object_id
                    AND version.execution_domain=capture.execution_domain
               )
          ), latest_states AS (
            SELECT document_raw.raw_object_id,
                   CASE WHEN EXISTS (
                     SELECT 1 FROM raw_object raw
                      WHERE raw.id=document_raw.raw_object_id
                        AND (
                          raw.scan_status <> 'CLEAN'
                          OR EXISTS (
                            SELECT 1 FROM raw_object_security_fact negative
                             WHERE negative.raw_object_id=raw.id
                               AND negative.status IN ('REJECTED','QUARANTINED')
                          )
                        )
                   ) THEN 'QUARANTINED'
                     WHEN v_replay_status='FAILED' THEN 'FAILED'
                     ELSE (
                       SELECT event.state
                         FROM document_version version
                         JOIN document linked_document
                           ON linked_document.id=version.document_id
                          AND linked_document.source_id=v_source_id
                         JOIN document_version_state_event event
                           ON event.document_version_id=version.id
                        WHERE version.raw_object_id=document_raw.raw_object_id
                          AND version.execution_domain=v_domain
                        ORDER BY event.created_at DESC,event.id DESC
                        LIMIT 1
                     ) END AS state
              FROM document_raw
          )
          SELECT count(*)::integer,
                 count(*) FILTER (WHERE state='READY')::integer,
                 count(*) FILTER (WHERE state='FAILED')::integer,
                 count(*) FILTER (WHERE state='QUARANTINED')::integer
            INTO v_document_raw_count,v_ready_count,v_parse_failed_count,
                 v_security_failed_count
            FROM latest_states;
          SELECT count(*)::integer INTO v_rejected_raw_attempt_count
            FROM source_trial_rejected_raw_attempt rejected
           WHERE rejected.trial_run_id=p_trial_id
             AND rejected.source_id=v_source_id;
          v_raw_count := v_document_raw_count;
          v_security_failed_count :=
            v_security_failed_count + v_rejected_raw_attempt_count;
          v_ready_ratio_bps := CASE
            WHEN v_raw_count=0 THEN 0
            ELSE (
              (v_ready_count::bigint * 10000 + v_raw_count / 2) / v_raw_count
            )::integer
          END;
          v_quality_summary := jsonb_build_object(
            'raw_count',v_raw_count,
            'ready_count',v_ready_count,
            'parse_failed_count',v_parse_failed_count,
            'security_failed_count',v_security_failed_count,
            'rejected_raw_attempt_count',v_rejected_raw_attempt_count,
            'ready_ratio_bps',v_ready_ratio_bps
          );
          IF jsonb_typeof(p_quality_summary) IS DISTINCT FROM 'object'
             OR p_quality_summary IS DISTINCT FROM v_quality_summary THEN
            RAISE EXCEPTION 'source trial quality summary is not database-derived';
          END IF;
          IF v_kind='FIXTURE_REPLAY' AND p_status='SUCCEEDED'
             AND (v_replay_status<>'PASSED' OR v_raw_count=0
                  OR v_ready_count<>v_raw_count OR v_parse_failed_count<>0
                  OR v_security_failed_count<>0
                  OR v_rejected_raw_attempt_count<>0) THEN
            RAISE EXCEPTION 'successful fixture replay requires PASSED all-READY evidence';
          END IF;
          IF v_kind='FIXTURE_REPLAY' AND p_status='FAILED'
             AND v_replay_status<>'FAILED' AND v_security_failed_count=0
             AND v_rejected_raw_attempt_count=0 THEN
            RAISE EXCEPTION 'failed fixture replay requires replay or security evidence';
          END IF;
          IF p_status='SUCCEEDED' AND (v_raw_count=0 OR v_ready_count=0) THEN
            RAISE EXCEPTION 'successful source trial requires READY evidence';
          END IF;
          INSERT INTO source_trial_run_result (
            trial_run_id, status, quality_summary, raw_namespace,
            completed_by, completed_at
          ) VALUES (
            p_trial_id, p_status, v_quality_summary, p_raw_namespace,
            p_actor_id, p_completed_at
          );
          RETURN p_trial_id;
        END $$
        """
    )
    op.execute(
        """
        CREATE FUNCTION complete_source_trial_run_with_audit(
          p_trial_id uuid, p_status text, p_quality_summary jsonb,
          p_raw_namespace text, p_actor_id uuid, p_reason text,
          p_request_id text, p_audit_id uuid,
          p_completed_at timestamptz DEFAULT now()
        ) RETURNS uuid
        LANGUAGE plpgsql SECURITY DEFINER
        SET search_path = pg_catalog, public AS $$
        DECLARE
          v_source_id uuid;
          v_kind text;
          v_stored_quality jsonb;
        BEGIN
          IF source_v2_safe_audit_reason(p_reason) IS DISTINCT FROM true
             OR length(p_request_id) NOT BETWEEN 1 AND 200
             OR p_request_id ~ '[[:cntrl:]]' THEN
            RAISE EXCEPTION 'source trial completion audit is invalid';
          END IF;
          SELECT source_id,kind INTO v_source_id,v_kind
            FROM source_trial_run WHERE id=p_trial_id;
          IF NOT FOUND THEN RAISE EXCEPTION 'source trial does not exist'; END IF;
          PERFORM complete_source_trial_run(
            p_trial_id,p_status,p_quality_summary,p_raw_namespace,
            p_actor_id,p_completed_at
          );
          SELECT quality_summary INTO v_stored_quality
            FROM source_trial_run_result WHERE trial_run_id=p_trial_id;
          PERFORM append_audit_event(
            p_audit_id, 'SOURCE_TRIAL_COMPLETED', p_actor_id,
            'SOURCE_TRIAL_RUN', p_trial_id,
            jsonb_build_object('status','PENDING','source_id',v_source_id),
            jsonb_build_object(
              'status',p_status,'kind',v_kind,'quality_summary',v_stored_quality
            ), p_reason, p_request_id, p_completed_at
          );
          RETURN p_trial_id;
        END $$
        """
    )
    op.execute(
        """
        CREATE FUNCTION approve_source_production(
          p_source_id uuid, p_policy_id uuid, p_config_id uuid, p_trial_id uuid,
          p_decision_id uuid, p_actor_id uuid, p_reason text, p_request_id text,
          p_event_id uuid, p_audit_id uuid, p_approved_at timestamptz DEFAULT now()
        ) RETURNS uuid
        LANGUAGE plpgsql SECURITY DEFINER
        SET search_path = pg_catalog, public AS $$
        DECLARE
          v_state text;
          v_registered uuid;
          v_policy_submitter uuid;
          v_config_submitter uuid;
          v_trial_requester uuid;
          v_compliance_approver uuid;
          v_trial_authorizer uuid;
          v_valid_until timestamptz;
        BEGIN
          IF source_v2_safe_audit_reason(p_reason) IS DISTINCT FROM true THEN
            RAISE EXCEPTION 'source governance reason is invalid';
          END IF;
          SELECT s.lifecycle_state, s.registered_by, p.submitted_by, c.created_by,
                 r.requested_by, compliance.decided_by, auth_decision.decided_by,
                 p.valid_until
            INTO v_state, v_registered, v_policy_submitter, v_config_submitter,
                 v_trial_requester, v_compliance_approver, v_trial_authorizer,
                 v_valid_until
            FROM source s
            JOIN source_policy_version p ON p.id = s.current_policy_version_id
            JOIN connector_config_version c
              ON c.id = s.current_connector_config_version_id
             AND c.source_id=s.id AND c.policy_version_id=p.id
            JOIN source_trial_run r ON r.id = s.current_trial_run_id
            JOIN source_trial_run_result rr ON rr.trial_run_id = r.id
            JOIN LATERAL (
              SELECT d.decided_by,d.outcome,d.valid_until
                FROM source_governance_decision d
               WHERE d.source_id=s.id AND d.policy_version_id=p.id
                 AND d.decision_type='COMPLIANCE'
               ORDER BY d.created_at DESC,d.id DESC LIMIT 1
            ) compliance ON compliance.outcome='APPROVED'
                         AND (compliance.valid_until IS NULL
                              OR compliance.valid_until > p_approved_at)
            JOIN source_governance_decision auth_decision
              ON auth_decision.id=r.authorization_decision_id
             AND auth_decision.source_id=s.id
             AND auth_decision.decision_type='LIVE_TRIAL_AUTHORIZATION'
             AND auth_decision.outcome='APPROVED'
             AND (auth_decision.valid_until IS NULL
                  OR auth_decision.valid_until > p_approved_at)
           WHERE s.id = p_source_id AND p.id = p_policy_id AND c.id = p_config_id
             AND r.id = p_trial_id AND p.source_id = s.id AND c.source_id = s.id
             AND r.source_id = s.id AND r.policy_version_id = p.id
             AND r.connector_config_version_id = c.id AND r.kind = 'LIVE_TRIAL'
             AND rr.status = 'SUCCEEDED' AND p.valid_from <= p_approved_at
             AND p.valid_until > p_approved_at AND c.validation_status = 'VALID'
             AND s.governance_owner_id IS NOT NULL
             AND source_v2_policy_compliance_approved(
                   s.id,p.id,p_approved_at
                 ) IS TRUE
           FOR UPDATE OF s;
          IF NOT FOUND OR v_state <> 'TRIAL' THEN
            RAISE EXCEPTION 'source production evidence is incomplete or expired';
          END IF;
          IF p_actor_id = v_policy_submitter OR p_actor_id = v_config_submitter
             OR p_actor_id = v_trial_requester
             OR p_actor_id = v_compliance_approver
             OR p_actor_id = v_trial_authorizer
             OR p_actor_id IS NOT DISTINCT FROM v_registered THEN
            RAISE EXCEPTION 'production approval violates separation of duties';
          END IF;
          INSERT INTO source_governance_decision (
            id, source_id, decision_type, outcome, policy_version_id,
            connector_config_version_id, trial_run_id, submitted_by, decided_by,
            reason, valid_until, created_at
          ) VALUES (
            p_decision_id, p_source_id, 'PRODUCTION_APPROVAL', 'APPROVED',
            p_policy_id, p_config_id, p_trial_id, v_trial_requester, p_actor_id,
            p_reason, v_valid_until, p_approved_at
          );
          UPDATE source SET lifecycle_state = 'ACTIVE', trial_kind = NULL,
            updated_at = p_approved_at WHERE id = p_source_id;
          INSERT INTO source_lifecycle_event (
            id, source_id, from_state, to_state, action, reason_code, reason,
            actor_id, policy_version_id, governance_decision_id, created_at
          ) VALUES (
            p_event_id, p_source_id, v_state, 'ACTIVE', 'APPROVE_PRODUCTION',
            'PRODUCTION_APPROVED', p_reason, p_actor_id, p_policy_id,
            p_decision_id, p_approved_at
          );
          PERFORM append_audit_event(
            p_audit_id, 'SOURCE_PRODUCTION_APPROVED', p_actor_id, 'SOURCE',
            p_source_id, jsonb_build_object('lifecycle_state',v_state),
            jsonb_build_object('lifecycle_state','ACTIVE',
                               'governance_decision_id',p_decision_id),
            p_reason, p_request_id, p_approved_at
          );
          RETURN p_decision_id;
        END $$
        """
    )
    api_signatures = (
        "start_source_trial_run(uuid,uuid,text,uuid,uuid,uuid,uuid,text,text,uuid,uuid,timestamptz)",
        "approve_source_production(uuid,uuid,uuid,uuid,uuid,uuid,text,text,uuid,uuid,timestamptz)",
    )
    quality_signature = "source_trial_quality_summary(uuid)"
    replay_signature = "record_source_fixture_replay_result(uuid,uuid,uuid,text,text,integer,integer,integer,uuid,timestamptz)"
    completion_signature = "complete_source_trial_run(uuid,text,jsonb,text,uuid,timestamptz)"
    worker_signature = "complete_source_trial_run_with_audit(uuid,text,jsonb,text,uuid,text,text,uuid,timestamptz)"
    for signature in api_signatures:
        op.execute(f"REVOKE ALL ON FUNCTION {signature} FROM PUBLIC")
        op.execute(f"GRANT EXECUTE ON FUNCTION {signature} TO srbg_api_role")
    op.execute(f"REVOKE ALL ON FUNCTION {quality_signature} FROM PUBLIC")
    op.execute(f"REVOKE ALL ON FUNCTION {replay_signature} FROM PUBLIC")
    op.execute(f"REVOKE ALL ON FUNCTION {completion_signature} FROM PUBLIC")
    op.execute(f"REVOKE ALL ON FUNCTION {worker_signature} FROM PUBLIC")
    op.execute(
        f"GRANT EXECUTE ON FUNCTION {quality_signature} TO srbg_api_role, srbg_worker_role"
    )
    op.execute(
        f"GRANT EXECUTE ON FUNCTION {replay_signature} TO srbg_api_role, srbg_worker_role"
    )
    op.execute(f"GRANT EXECUTE ON FUNCTION {worker_signature} TO srbg_api_role, srbg_worker_role")


def _configure_source_roles() -> None:
    op.execute(
        """
        DO $$ BEGIN
          IF NOT EXISTS (
            SELECT 1 FROM pg_roles WHERE rolname = 'srbg_source_governance_writer'
          ) THEN
            CREATE ROLE srbg_source_governance_writer NOLOGIN;
          END IF;
        END $$
        """
    )
    tables = ", ".join(ROUND15_TABLES)
    op.execute(f"REVOKE ALL ON {tables} FROM PUBLIC")
    op.execute(
        f"REVOKE INSERT, UPDATE, DELETE ON {tables} FROM "
        "srbg_runtime, srbg_api_role, srbg_worker_role, srbg_publication_writer, srbg_model_role"
    )
    op.execute(
        f"GRANT SELECT ON {tables} TO "
        "srbg_runtime, srbg_api_role, srbg_worker_role, srbg_publication_writer"
    )
    restricted_config_readers = (
        "srbg_runtime, srbg_worker_role, srbg_publication_writer"
    )
    op.execute(
        "REVOKE SELECT ON connector_config_version FROM "
        f"{restricted_config_readers}"
    )
    op.execute(
        "REVOKE SELECT (credential_ref) ON connector_config_version FROM "
        f"{restricted_config_readers}"
    )
    op.execute(
        "GRANT SELECT (id,source_id,connector_definition_id,policy_version_id,"
        "version_number,config_document,config_sha256,allowed_hosts,"
        "validation_status,validation_reason_codes,supersedes_id,created_by,created_at) "
        "ON connector_config_version TO "
        f"{restricted_config_readers}"
    )
    op.execute(f"GRANT SELECT ON {tables} TO srbg_source_governance_writer")
    # Both V1 compatibility fields and V2 authority fields are read-only to runtime roles.
    op.execute(
        "REVOKE INSERT, DELETE ON source FROM "
        "srbg_runtime, srbg_api_role, srbg_worker_role, srbg_model_role"
    )
    op.execute("REVOKE UPDATE ON source FROM srbg_runtime")
    op.execute("REVOKE UPDATE ON source FROM srbg_api_role, srbg_worker_role, srbg_model_role")


def downgrade() -> None:
    _guard_round15_downgrade()
    _drop_source_write_boundaries()
    for table_name in reversed(ROUND15_TABLES):
        op.execute(f"DROP TRIGGER IF EXISTS trg_{table_name}_immutable ON {table_name}")
    op.execute(
        """
        UPDATE source s
           SET state = snapshot.legacy_state,
               enabled = snapshot.legacy_enabled,
               updated_at = now()
          FROM source_migration_snapshot snapshot
         WHERE snapshot.source_id = s.id
        """
    )
    for constraint in (
        "fk_source_current_trial_run",
        "fk_source_current_connector_config",
        "fk_source_current_policy_v2",
    ):
        op.drop_constraint(constraint, "source", type_="foreignkey")
    op.drop_constraint("fk_trial_authorization_decision", "source_trial_run", type_="foreignkey")
    for constraint, table_name in (
        ("fk_raw_capture_trial_same_source", "raw_object_capture"),
        ("fk_trial_authorization_same_source", "source_trial_run"),
        ("fk_governance_trial_same_source", "source_governance_decision"),
        ("fk_governance_config_same_source", "source_governance_decision"),
        ("fk_governance_policy_same_source", "source_governance_decision"),
        ("fk_trial_config_same_source", "source_trial_run"),
        ("fk_trial_policy_same_source", "source_trial_run"),
        ("fk_connector_config_policy_same_source", "connector_config_version"),
    ):
        op.drop_constraint(constraint, table_name, type_="foreignkey")
    op.drop_constraint("fk_governance_trial_run", "source_governance_decision", type_="foreignkey")
    op.drop_constraint(
        "fk_governance_connector_config",
        "source_governance_decision",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_connector_config_supersedes", "connector_config_version", type_="foreignkey"
    )
    op.drop_constraint(
        "fk_connector_config_policy_version",
        "connector_config_version",
        type_="foreignkey",
    )
    op.drop_constraint("fk_document_version_raw_capture", "document_version", type_="foreignkey")
    op.drop_column("document_version", "raw_object_capture_id")
    for table_name in reversed(ROUND15_TABLES):
        op.drop_table(table_name)
    _restore_fixture_document_kinds()
    op.drop_index("ix_document_version_execution_domain", table_name="document_version")
    op.drop_index("ix_fetch_run_execution_domain", table_name="fetch_run")
    for table_name in ("document_version", "fetch_record", "fetch_run"):
        op.drop_constraint(f"ck_{table_name}_execution_domain", table_name, type_="check")
        op.drop_column(table_name, "execution_domain")
    op.drop_index("ix_source_lifecycle_state_v2", table_name="source")
    op.drop_constraint("ck_source_non_trial_has_no_fixture_kind", "source", type_="check")
    op.drop_constraint("ck_source_trial_kind_v2", "source", type_="check")
    op.drop_constraint("ck_source_lifecycle_state_v2", "source", type_="check")
    for column in (
        "current_trial_run_id",
        "current_connector_config_version_id",
        "current_policy_version_id",
        "declared_roles",
        "content_domains",
        "industries",
        "language_tags",
        "region_codes",
        "country_codes",
        "governance_owner_id",
        "registered_by",
        "trial_kind",
        "lifecycle_state",
    ):
        op.drop_column("source", column)
    op.execute("GRANT INSERT, UPDATE, DELETE ON source TO srbg_runtime")


def _drop_source_write_boundaries() -> None:
    op.execute(
        "DROP TRIGGER IF EXISTS trg_document_version_execution_domain ON document_version"
    )
    op.execute(
        "DROP TRIGGER IF EXISTS trg_document_version_reject_closed_trial_ready "
        "ON document_version_state_event"
    )
    op.execute("DROP TRIGGER IF EXISTS trg_document_reject_closed_trial_current ON document")
    op.execute(
        "DROP TRIGGER IF EXISTS trg_document_attachment_immutable ON document_attachment"
    )
    op.execute(
        """
        CREATE TRIGGER trg_document_attachment_immutable
        BEFORE UPDATE OR DELETE ON document_attachment
        FOR EACH ROW EXECUTE FUNCTION reject_immutable_source_vault_change()
        """
    )
    op.execute(
        "DROP TRIGGER IF EXISTS "
        "trg_document_attachment_reject_negative_raw_history ON document_attachment"
    )
    op.execute(
        "DROP TRIGGER IF EXISTS trg_raw_security_negative_clears_current "
        "ON raw_object_security_fact"
    )
    op.execute("DROP TRIGGER IF EXISTS trg_document_reject_negative_raw_current ON document")
    signatures = (
        "register_source_candidate(uuid,text,text,text,text,text,text,text,integer,text,uuid,text[],text[],text[],text[],text[],text[],uuid,text,uuid,timestamptz)",
        "update_source_governance_metadata(uuid,uuid,text[],text[],text[],text[],text[],text[],uuid,text,text,uuid,timestamptz)",
        "append_source_assessments(uuid,uuid,text,text,text[],text[],timestamptz,uuid,text,text,text[],text[],timestamptz,uuid,text,text,uuid,timestamptz)",
        "apply_source_lifecycle_command(uuid,text,uuid,text,text,uuid,timestamptz)",
        "submit_source_policy_version(uuid,uuid,text,text,jsonb,timestamptz,timestamptz,uuid,text,text,uuid,timestamptz)",
        "decide_source_policy_version(uuid,uuid,uuid,text,uuid,text,text,uuid,timestamptz)",
        "save_source_connector_config(uuid,uuid,uuid,integer,jsonb,text,uuid,uuid,text,text,uuid,timestamptz)",
        "append_source_trial_raw_capture(uuid,uuid,uuid,uuid,text,text,text,jsonb,integer,text,text,text,timestamptz)",
        "append_source_trial_rejected_raw_attempt(uuid,uuid,uuid,uuid,text,text,text,text,uuid,text,timestamptz)",
        "append_document_attachment_attempt(uuid,uuid,text,text,text,bigint,text,text,text,text,text,text,text,timestamptz)",
        "start_source_trial_run(uuid,uuid,text,uuid,uuid,uuid,uuid,text,text,uuid,uuid,timestamptz)",
        "complete_source_trial_run_with_audit(uuid,text,jsonb,text,uuid,text,text,uuid,timestamptz)",
        "complete_source_trial_run(uuid,text,jsonb,text,uuid,timestamptz)",
        "source_trial_quality_summary(uuid)",
        "record_source_fixture_replay_result(uuid,uuid,uuid,text,text,integer,integer,integer,uuid,timestamptz)",
        "approve_source_production(uuid,uuid,uuid,uuid,uuid,uuid,text,text,uuid,uuid,timestamptz)",
        "source_v2_policy_compliance_approved(uuid,uuid,timestamptz)",
        "source_v2_safe_http_url(text,text[])",
        "source_v2_exact_dns_host(text)",
        "source_v2_safe_audit_reason(text)",
        "reject_clean_attachment_with_negative_raw_history()",
        "clear_current_document_for_negative_raw()",
        "reject_negative_raw_as_document_current()",
        "reject_closed_trial_version_promotion()",
        "reject_closed_trial_version_as_current()",
        "reject_nonsecurity_document_attachment_change()",
        "enforce_document_version_execution_domain()",
    )
    for signature in signatures:
        op.execute(f"DROP FUNCTION IF EXISTS {signature}")


def _guard_round15_downgrade() -> None:
    op.execute(
        f"""
        DO $$
        BEGIN
          IF EXISTS (
            SELECT 1 FROM source s
             WHERE NOT EXISTS (
               SELECT 1 FROM source_migration_snapshot m WHERE m.source_id = s.id
             )
          ) OR EXISTS (
            SELECT 1
              FROM source s
              JOIN source_migration_snapshot m ON m.source_id = s.id
             WHERE s.governance_owner_id IS NOT NULL
                OR cardinality(s.country_codes) <> 0
                OR cardinality(s.region_codes) <> 0
                OR cardinality(s.language_tags) <> 0
                OR cardinality(s.industries) <> 0
                OR cardinality(s.content_domains) <> 0
                OR cardinality(s.declared_roles) <> 0
                OR s.registered_by IS NOT NULL
                OR s.current_policy_version_id IS NOT NULL
                OR s.current_connector_config_version_id IS NOT NULL
                OR s.current_trial_run_id IS NOT NULL
                OR s.lifecycle_state IS DISTINCT FROM m.mapped_lifecycle_state
                OR s.trial_kind IS DISTINCT FROM m.mapped_trial_kind
          ) OR EXISTS (SELECT 1 FROM connector_config_version)
             OR EXISTS (SELECT 1 FROM raw_object_capture)
             OR EXISTS (SELECT 1 FROM source_trial_rejected_raw_attempt)
             OR EXISTS (SELECT 1 FROM document_attachment_attempt)
             OR EXISTS (SELECT 1 FROM source_policy_version)
             OR EXISTS (SELECT 1 FROM source_governance_decision)
             OR EXISTS (SELECT 1 FROM source_trial_run)
             OR EXISTS (SELECT 1 FROM source_trial_run_result)
             OR EXISTS (SELECT 1 FROM source_fixture_replay_result)
             OR EXISTS (SELECT 1 FROM source_authority_assessment)
             OR EXISTS (SELECT 1 FROM source_independence_assessment)
             OR EXISTS (
               SELECT 1 FROM source_lifecycle_event
                WHERE migration_rule_version IS DISTINCT FROM '{ROUND15_MIGRATION_RULE_VERSION}'
             ) THEN
            RAISE EXCEPTION 'ROUND15_DOWNGRADE_BLOCKED: V2 governance facts exist';
          END IF;
        END $$
        """
    )
