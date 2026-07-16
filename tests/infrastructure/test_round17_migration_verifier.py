from __future__ import annotations

from pathlib import Path

import pytest

from scripts.run_isolated_integration import IntegrationConfig, _migration_command
from scripts.verify_round17_migration import (
    EXPECTED_CONSTRAINTS,
    EXPECTED_FUNCTION_SIGNATURES,
    EXPECTED_TABLES,
    validate_disposable_database_url,
)


def _config() -> IntegrationConfig:
    return IntegrationConfig(
        python_executable="python",
        postgres_host="127.0.0.1",
        postgres_port=5432,
        postgres_admin_user="admin",
        postgres_admin_password="synthetic-secret",  # noqa: S106
        postgres_admin_database="srbg",
        s3_endpoint_url="http://127.0.0.1:9000",
        s3_access_key="synthetic-access",
        s3_secret_key="synthetic-secret",  # noqa: S106
        s3_region="us-east-1",
        shared_s3_bucket="srbg-raw",
    )


def test_round17_verifier_is_allowlisted_by_isolated_runner() -> None:
    assert _migration_command(_config(), "verify_round17_migration.py") == (
        "python",
        "scripts/verify_round17_migration.py",
    )


def test_round17_verifier_accepts_only_disposable_loopback_database() -> None:
    database = "srbg_it_0123456789abcdef01234567"

    assert (
        validate_disposable_database_url(
            f"postgresql+asyncpg://admin:secret@127.0.0.1:5432/{database}"
        )
        == database
    )
    assert (
        validate_disposable_database_url(
            f"postgresql+asyncpg://admin:secret@localhost:5432/{database}"
        )
        == database
    )


@pytest.mark.parametrize(
    "database_url",
    (
        "postgresql+asyncpg://admin:secret@db.internal:5432/srbg_it_0123456789abcdef01234567",
        "postgresql+asyncpg://admin:secret@127.0.0.1:5432/srbg",
        "postgresql+asyncpg://admin:secret@127.0.0.1:5432/srbg_it_too_short",
        "postgresql+asyncpg://admin:secret@127.0.0.1:5432/srbg_it_0123456789abcdef01234567/extra",
    ),
)
def test_round17_verifier_rejects_non_disposable_database(database_url: str) -> None:
    with pytest.raises(RuntimeError, match="isolated loopback"):
        validate_disposable_database_url(database_url)


def test_round17_verifier_covers_tables_constraints_functions_and_roles() -> None:
    assert set(EXPECTED_TABLES) >= {
        "source_governance_scheme_assignment",
        "round17_pilot_window",
        "round17_eventization_readiness",
        "round17_pilot_window_source",
        "round17_gold_annotation",
        "round17_metric_snapshot",
    }
    assert set(EXPECTED_CONSTRAINTS) >= {
        "ck_source_governance_scheme_round17",
        "ck_round17_window_duration",
        "ck_round17_window_exact_period",
        "ck_fetch_run_origin",
        "ck_round17_staff_not_local",
        "uq_round17_window_source_segment",
        "uq_round17_window_source_code_segment",
        "ck_round17_source_schedule_pins",
        "ck_round17_source_pause_fact",
        "ck_round17_source_resume_fact",
        "ck_round17_work_correction_separation",
        "ck_round17_eventization_status",
        "ck_round17_eventization_profile_hashes",
        "ck_round17_eventization_manifest_ref",
    }
    assert set(EXPECTED_FUNCTION_SIGNATURES) >= {
        "assign_round17_two_person_governance(uuid,uuid,text,uuid,text,text,uuid,timestamptz)",
        "record_scheduled_source_raw(uuid,uuid,uuid,uuid,text,text,text,text,bigint,text,text,text,text,text,text,jsonb,integer,text,text,timestamptz)",
        "record_scheduled_source_document(uuid,uuid,uuid,uuid,uuid,uuid,uuid,uuid,uuid,text,text,text,text,text,timestamptz)",
        "protect_round17_source_segment_pins()",
        "pause_round17_segments_on_source_change()",
        "pause_round17_segments_on_schedule_change()",
        "pause_round17_segments_on_anomaly()",
        "validate_round17_work_correction()",
    }
    source = Path("scripts/verify_round17_migration.py").read_text(encoding="utf-8")
    for role in ("srbg_api_role", "srbg_worker_role", "srbg_projection_reader", "PUBLIC"):
        assert role in source
    assert "0017B_DOWNGRADE_BLOCKED" in source
    assert "0016_scheduling_health_replay" in source
    assert "0017b_round17_pilot" in source
    assert "expired lease accepted a backdated raw capture" in source
    assert "paused source segment accepted raw capture" in source
    assert "expired lease accepted document materialization" in source
    assert "paused source segment accepted document materialization" in source
    assert "window completed before its immutable ends_at" in source
    assert "resumed segment accepted without a paused predecessor" in source
    assert "self-correction of yinzi operator evidence was accepted" in source


def test_round17_make_target_uses_dynamic_isolated_migration_verifier() -> None:
    makefile = Path("Makefile").read_text(encoding="utf-8")
    recipe = makefile.split("phase2-round17-test:", 1)[1].split("phase2-round17-eval:", 1)[0]

    assert "scripts/run_isolated_integration.py" in recipe
    assert "--migration-verifier verify_round17_migration.py" in recipe
    assert "python -m pytest" not in recipe
