from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

MIGRATION = Path("apps/api/migrations/versions/0029_legacy_governance_retirement.py")
REPAIR_MIGRATION = Path("apps/api/migrations/versions/0030_pers10_role_archive_repair.py")


def test_pers10_role_repair_is_the_single_head() -> None:
    script = ScriptDirectory.from_config(Config("apps/api/alembic.ini"))
    assert script.get_current_head() == "0031_controlled_personal_runs"
    revision = script.get_revision("0029_legacy_governance_retirement")
    assert revision is not None
    assert revision.down_revision == "0028_automatic_relationships"
    repair = script.get_revision("0030_pers10_role_archive_repair")
    assert repair is not None
    assert repair.down_revision == "0029_legacy_governance_retirement"


def test_pers10_role_repair_archives_all_enterprise_roles_and_fails_closed() -> None:
    sql = REPAIR_MIGRATION.read_text(encoding="utf-8")
    for token in (
        "srbg_admin_role",
        "srbg_model_role",
        "srbg_source_governance_writer",
        "reconstructed_from_revision",
        "0028_automatic_relationships",
        "PERS10_ROLE_ARCHIVE_CORRUPT",
        "PERS10_ROLE_STATE_UNEXPECTED",
        "PERS10_ROLE_EXTERNAL_DEPENDENCIES",
        "PERS10_ROLE_ARCHIVE_COUNT_MISMATCH",
        "PERS10_ROLE_ARCHIVE_HASH_MISMATCH",
        "DROP OWNED BY",
        "DROP ROLE",
        "trg_pers10_archive_read_only",
    ):
        assert token in sql


def test_pers10_role_repair_downgrade_restores_only_source_writer() -> None:
    sql = REPAIR_MIGRATION.read_text(encoding="utf-8")
    downgrade = sql[sql.index("def downgrade()") :]
    assert "_verify_complete_role_archive()" in downgrade
    assert "_restore_source_governance_writer()" in downgrade
    assert "_restore_0029_role_manifest()" in downgrade
    assert downgrade.index("_verify_complete_role_archive()") < downgrade.index(
        "_restore_source_governance_writer()"
    )


def test_pers10_archives_required_governance_classes_with_hashes() -> None:
    sql = MIGRATION.read_text(encoding="utf-8")
    for token in (
        "legacy_governance_archive",
        "legacy_governance_archive_record",
        "legacy_governance_archive_manifest",
        "normalized_payload",
        "row_sha256",
        "aggregate_sha256",
        "original_count",
        "archive_count",
        "0029_legacy_governance_retirement",
        "source_candidate",
        "source_qualification_run",
        "source_qualification_bundle",
        "source_candidate_decision",
        "source_authority_assessment",
        "source_independence_assessment",
        "source_policy_version",
        "connector_config_version",
        "source_trial_run",
        "source_governance_decision",
        "review_task",
        "ai_claim_review_decision",
        "duplicate_decision",
        "event_item_decision",
        "event_relation_decision",
        "cluster_decision",
        "product_normalization_candidate",
    ):
        assert token in sql


def test_pers10_fails_closed_for_incomplete_or_corrupt_archives() -> None:
    sql = MIGRATION.read_text(encoding="utf-8")
    for reason in (
        "PERS10_REPLACEMENT_INCOMPLETE",
        "PERS10_ARCHIVE_COUNT_MISMATCH",
        "PERS10_ARCHIVE_HASH_MISMATCH",
        "PERS10_ARCHIVE_CORRUPT",
    ):
        assert reason in sql
    assert "transaction_timestamp()" in sql
    assert "REVOKE ALL ON SCHEMA legacy_governance_archive FROM PUBLIC" in sql


def test_pers10_downgrade_restores_archived_relations_only_after_verification() -> None:
    sql = MIGRATION.read_text(encoding="utf-8")
    assert sql.index("PERS10_ARCHIVE_CORRUPT") < sql.index("SET SCHEMA public")
    assert "ENABLE TRIGGER" in sql
    assert "def _install_pre_retirement_claim_function()" in sql
    assert sql.index("SET SCHEMA public") < sql.index(
        "_install_pre_retirement_claim_function()", sql.index("def downgrade()")
    )
    assert "schedule.authority_mode='LEGACY_GOVERNED'" in sql
    assert "GRANT USAGE ON SCHEMA public TO srbg_projection_reader" in sql
    assert "REVOKE USAGE ON SCHEMA public FROM srbg_projection_reader" in sql
    assert "GRANT INSERT ON public.event_identity_binding TO srbg_worker_role" in sql
    assert "REVOKE INSERT ON public.event_identity_binding FROM srbg_worker_role" in sql
    assert "public.automatic_evidence_fact_state_event TO srbg_publication_writer" in sql
    assert "public.automatic_evidence_fact_state_event FROM srbg_publication_writer" in sql
    assert "GRANT UPDATE ON public.ai_judgment_version TO srbg_publication_writer" in sql
    assert "REVOKE UPDATE ON public.ai_judgment_version FROM srbg_publication_writer" in sql
    assert "DROP SCHEMA legacy_governance_archive" in sql


def test_pers10_retires_old_database_roles_and_downgrade_recreates_them() -> None:
    sql = MIGRATION.read_text(encoding="utf-8")
    upgrade = sql[sql.index("def upgrade()") : sql.index("def downgrade()")]
    downgrade = sql[sql.index("def downgrade()") :]
    assert 'LEGACY_DATABASE_ROLES: tuple[str, ...] = ("srbg_admin_role", "srbg_model_role")' in sql
    assert 'f"DROP ROLE {role}"' in sql
    assert 'f"CREATE ROLE {quote(role)} NOLOGIN INHERIT NOSUPERUSER NOCREATEDB "' in sql
    assert "_archive_database_roles(archived_at)" in upgrade
    assert "_retire_legacy_database_roles()" in upgrade
    assert "_restore_legacy_database_roles()" in downgrade


def test_pers10_retires_event_reviewer_trigger_and_restores_it_on_downgrade() -> None:
    sql = MIGRATION.read_text(encoding="utf-8")
    assert '"trg_event_pending_insert"' in sql
    assert "enforce_pending_event_insert()" in sql
    assert "for relation, trigger_name, _ in RETIRED_CORE_TRIGGERS" in sql
    assert "for _, _, trigger_ddl in RETIRED_CORE_TRIGGERS" in sql
