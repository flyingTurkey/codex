import inspect
import runpy
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from srbg_api.connectors.config import CONNECTOR_DEFINITIONS, ConnectorKind


def test_round15_migration_is_single_head_and_preserves_legacy_semantics() -> None:
    script = ScriptDirectory.from_config(Config("apps/api/alembic.ini"))
    assert script.get_current_head() == "0017b_round17_pilot"
    convergence = script.get_revision("0015b_source_center_convergence")
    assert convergence.down_revision == "0015_source_center_v2"
    revision = script.get_revision("0015_source_center_v2")
    assert revision.down_revision == "0014b_event_consumer_switch"

    migration = runpy.run_path("apps/api/migrations/versions/0015_source_center_v2.py")
    assert migration["ROUND15_MIGRATION_RULE_VERSION"] == "round15-lifecycle-v1"
    assert set(migration["ROUND15_TABLES"]) >= {
        "source_lifecycle_event",
        "source_migration_snapshot",
        "source_policy_version",
        "source_governance_decision",
        "source_trial_run",
        "source_fixture_replay_result",
        "document_attachment_attempt",
        "source_authority_assessment",
        "source_independence_assessment",
    }


def test_round15_convergence_revision_repairs_applied_schema_without_data_loss() -> None:
    source = Path(
        "apps/api/migrations/versions/0015b_source_center_convergence.py"
    ).read_text(encoding="utf-8")

    for required in (
        "source_fixture_replay_result",
        "_expand_fixture_document_kinds",
        "_create_source_command_boundary",
        "_create_document_version_execution_domain_boundary",
        "_configure_source_roles",
        "0015_SOURCE_SCHEMA_CONVERGENCE_BLOCKED",
        "credential_ref",
        "has_column_privilege",
    ):
        assert required in source
    assert "DROP TABLE source_fixture_replay_result" not in source
    assert "DELETE FROM source_" not in source


def test_round15_mapping_never_promotes_a_legacy_row_to_active() -> None:
    source = Path("apps/api/migrations/versions/0015_source_center_v2.py").read_text(
        encoding="utf-8"
    )
    migration = runpy.run_path("apps/api/migrations/versions/0015_source_center_v2.py")
    mapping_source = inspect.getsource(migration["_migrate_legacy_lifecycle"])

    assert "legacy state/enabled are retained" in source
    assert "V2_REAUTHORIZATION_REQUIRED" in source
    assert "LEGACY_UNVERIFIED" in source
    assert "FIXTURE_REPLAY" in source
    assert "SET enabled = false" in source
    assert "THEN 'ACTIVE'" not in mapping_source
    assert "source_trust_score" not in source


def test_round15_has_a_guarded_downgrade_and_default_deny_database_boundary() -> None:
    source = Path("apps/api/migrations/versions/0015_source_center_v2.py").read_text(
        encoding="utf-8"
    )

    assert "ROUND15_DOWNGRADE_BLOCKED" in source
    assert "srbg_source_governance_writer" in source
    assert "REVOKE UPDATE ON source FROM srbg_runtime" in source
    assert "GRANT UPDATE (state, enabled, updated_at)" not in source
    assert "REVOKE INSERT, UPDATE, DELETE" in source
    assert "append_document_attachment_attempt" in source
    assert "canonical_url_sha256" in source
    assert "enforce_document_version_execution_domain" in source
    assert "trg_document_version_execution_domain" in source
    assert "REVOKE SELECT (credential_ref)" in source


def test_policy_database_boundary_rejects_credentials_in_evidence_urls() -> None:
    migration = runpy.run_path("apps/api/migrations/versions/0015_source_center_v2.py")
    policy_boundary = inspect.getsource(migration["_create_policy_write_boundaries"])

    assert "review->>'evidence_url' ~ '://[^/[:space:]]+@'" in policy_boundary
    assert "api[_-]?key|access[_-]?key" in policy_boundary
    assert "client[_-]?secret|cookie|credential|password|secret|session" in policy_boundary


def test_round15_downgrade_guard_detects_governance_changes_on_migrated_sources() -> None:
    migration = runpy.run_path("apps/api/migrations/versions/0015_source_center_v2.py")
    guard_source = inspect.getsource(migration["_guard_round15_downgrade"])

    for guarded_fact in (
        "s.governance_owner_id IS NOT NULL",
        "cardinality(s.country_codes) <> 0",
        "cardinality(s.region_codes) <> 0",
        "cardinality(s.language_tags) <> 0",
        "cardinality(s.industries) <> 0",
        "cardinality(s.content_domains) <> 0",
        "cardinality(s.declared_roles) <> 0",
        "s.registered_by IS NOT NULL",
        "s.current_policy_version_id IS NOT NULL",
        "s.current_connector_config_version_id IS NOT NULL",
        "s.current_trial_run_id IS NOT NULL",
        "s.lifecycle_state IS DISTINCT FROM m.mapped_lifecycle_state",
        "s.trial_kind IS DISTINCT FROM m.mapped_trial_kind",
    ):
        assert guarded_fact in guard_source

    assert "EXISTS (SELECT 1 FROM source_fixture_replay_result)" in guard_source


def test_fixture_replay_result_is_an_immutable_database_derived_completion_gate() -> None:
    migration = runpy.run_path("apps/api/migrations/versions/0015_source_center_v2.py")
    governance_tables = inspect.getsource(migration["_create_governance_tables"])
    trial_boundaries = inspect.getsource(migration["_create_trial_write_boundaries"])
    drop_boundaries = inspect.getsource(migration["_drop_source_write_boundaries"])

    for required_table_fact in (
        '"source_fixture_replay_result"',
        'sa.Column("trial_run_id"',
        'sa.Column("source_id"',
        'sa.Column("connector_config_version_id"',
        'sa.Column("status"',
        'sa.Column("reason_code"',
        'sa.Column("raw_capture_count"',
        'sa.Column("document_count"',
        'sa.Column("transport_call_count"',
        'sa.Column("evaluated_by"',
        'sa.Column("created_at"',
        "status IN ('PASSED','FAILED')",
        "status <> 'PASSED' OR (raw_capture_count > 0 AND document_count > 0)",
        'name="fk_fixture_replay_trial_source"',
        'name="fk_fixture_replay_config_source"',
    ):
        assert required_table_fact in governance_tables

    for required_boundary_fact in (
        "CREATE FUNCTION record_source_fixture_replay_result(",
        "trial.kind='FIXTURE_REPLAY'",
        "trial.execution_domain='FIXTURE'",
        "source_row.current_trial_run_id=trial.id",
        "source_row.current_connector_config_version_id=trial.connector_config_version_id",
        "SELECT count(*)::integer INTO v_database_raw_capture_count",
        "FROM raw_object_capture",
        "v_database_raw_capture_count <> p_raw_capture_count",
        "p_status='PASSED' AND (p_raw_capture_count=0 OR p_document_count=0)",
        "INSERT INTO source_fixture_replay_result",
        "v_replay_status='FAILED' THEN 'FAILED'",
        "v_kind='FIXTURE_REPLAY' AND p_status<>'CANCELLED'",
        "v_replay_status IS NULL",
        "v_replay_status<>'PASSED'",
        "v_replay_status<>'FAILED'",
    ):
        assert required_boundary_fact in trial_boundaries

    signature = (
        "record_source_fixture_replay_result("
        "uuid,uuid,uuid,text,text,integer,integer,integer,uuid,timestamptz)"
    )
    assert signature in trial_boundaries
    assert signature in drop_boundaries


def test_round15_expands_and_reversibly_restores_structured_fixture_document_kinds() -> None:
    migration = runpy.run_path("apps/api/migrations/versions/0015_source_center_v2.py")
    expand = inspect.getsource(migration["_expand_fixture_document_kinds"])
    restore = inspect.getsource(migration["_restore_fixture_document_kinds"])

    assert "DISCOVERY_XML" in expand
    assert "DISCOVERY_JSON" in expand
    assert 'type_=sa.String(30)' in expand
    assert "ck_document_kind" in expand
    assert "document_kind IN ('HTML','PDF')" in restore
    assert 'type_=sa.String(10)' in restore


def test_migration_seeds_the_exact_reviewed_connector_schemas() -> None:
    migration = runpy.run_path("apps/api/migrations/versions/0015_source_center_v2.py")
    documents = migration["_connector_schema_documents"]()

    assert set(documents) == {kind.value for kind in ConnectorKind}
    for kind, definition in CONNECTOR_DEFINITIONS.items():
        assert documents[kind.value] == definition.schema
        assert len(definition.schema_sha256) == 64
