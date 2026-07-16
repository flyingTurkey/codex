import inspect
import runpy
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

MIGRATION_PATH = Path(
    "apps/api/migrations/versions/0017_round17_governance.py"
)


def _migration() -> dict[str, object]:
    return runpy.run_path(str(MIGRATION_PATH))


def test_round17_governance_revision_follows_round16_without_rewriting_history() -> None:
    script = ScriptDirectory.from_config(Config("apps/api/alembic.ini"))
    revision = script.get_revision("0017_round17_governance")

    assert revision.down_revision == "0016_scheduling_health_replay"


def test_round17_scheme_assignment_is_explicit_immutable_and_audited() -> None:
    migration = _migration()
    source = inspect.getsource(migration["_create_scheme_assignment"])

    for required in (
        '"source_governance_scheme_assignment"',
        '"source_id"',
        'sa.Column("scheme"',
        'sa.Column("cohort_key"',
        'sa.Column("assigned_by"',
        'sa.Column("reason"',
        'sa.Column("request_id"',
        'sa.Column("created_at"',
        "R17_TWO_PERSON_MAKER_CHECKER_V1",
        "r17-sources-v[0-9]+\\.[0-9]+",
        "trg_source_governance_scheme_assignment_immutable",
        "reject_immutable_source_vault_change",
        "assign_round17_two_person_governance",
        "source_v2_safe_audit_reason",
        "SOURCE_GOVERNANCE_SCHEME_ASSIGNED",
        "append_audit_event",
    ):
        assert required in source

    assert "GRANT INSERT" not in source
    assert "GRANT UPDATE" not in source
    assert "GRANT DELETE" not in source


def test_round17_wrappers_preserve_legacy_governance_and_relax_only_prior_approvers() -> None:
    migration = _migration()
    source = inspect.getsource(migration["_wrap_governance_boundaries"])
    maker_guard = inspect.getsource(migration["_create_round17_maker_guard"])

    for legacy_function in (
        "decide_source_policy_version_round15",
        "start_source_trial_run_round15",
        "approve_source_production_round15",
    ):
        assert legacy_function in source

    assert "source_v2_governance_scheme(p_source_id)" in source
    assert "R17_TWO_PERSON_MAKER_CHECKER_V1" in source
    assert "round17_source_actor_is_maker" in source
    assert source.count("assignment.assigned_by=p_actor_id") == 3
    assert source.count("round17 governance checker is not assigned") == 3
    assert "v_requested_by := v_config_submitter" in source
    assert "LIVE_TRIAL_AUTHORIZATION" in source
    assert "PRODUCTION_APPROVAL" in source
    assert "SOURCE_POLICY_" in source
    assert "SOURCE_TRIAL_STARTED" in source
    assert "SOURCE_PRODUCTION_APPROVED" in source

    for maker_fact in (
        "s.registered_by",
        "s.governance_owner_id",
        "p.submitted_by",
        "c.created_by",
        "r.requested_by",
        "FETCH_SCHEDULE_UPDATED",
        "audit_log",
    ):
        assert maker_fact in maker_guard
    assert "source_governance_decision" not in maker_guard


def test_round17_approval_evidence_stays_current_and_missing_facts_fail_closed() -> None:
    source = inspect.getsource(_migration()["_wrap_governance_boundaries"])
    normalized = "".join(source.split())

    for evidence_gate in (
        "p.valid_from <= p_decided_at",
        "p.valid_until > p_decided_at",
        "compliance.valid_until > p_created_at",
        "auth_decision.valid_until > p_approved_at",
        "p.valid_until > p_approved_at",
        "c.validation_status = 'VALID'",
        "rr.status = 'SUCCEEDED'",
        "s.governance_owner_id IS NOT NULL",
    ):
        assert "".join(evidence_gate.split()) in normalized


def test_round17_downgrade_restores_original_boundaries_or_blocks_on_real_facts() -> None:
    migration = _migration()
    guard = inspect.getsource(migration["_guard_round17_governance_downgrade"])
    restore = inspect.getsource(migration["_restore_governance_boundaries"])

    assert "ROUND17_GOVERNANCE_DOWNGRADE_BLOCKED" in guard
    assert "source_governance_scheme_assignment" in guard
    assert "DROP FUNCTION" in restore
    assert "RENAME TO decide_source_policy_version" in restore
    assert "RENAME TO start_source_trial_run" in restore
    assert "RENAME TO approve_source_production" in restore
