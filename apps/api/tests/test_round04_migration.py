from __future__ import annotations

import asyncio
import os
import runpy
from pathlib import Path
from urllib.parse import urlsplit

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from srbg_api.config import get_settings

REQUIRED_TABLES = {
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
}


def test_round04_migration_follows_round03_and_declares_lifecycle_tables() -> None:
    script = ScriptDirectory.from_config(Config("apps/api/alembic.ini"))

    assert script.get_current_head() == "0009_dedup_events_scoring"
    revision = script.get_revision("0005_safety_case_lifecycle")
    assert revision.down_revision == "0004_pdf_ocr_versioning"

    migration_path = Path("apps/api/migrations/versions/0005_safety_case_lifecycle.py")
    migration = runpy.run_path(str(migration_path))
    assert set(migration["ROUND04_TABLES"]) == REQUIRED_TABLES


def test_round04_migration_enforces_evidence_duties_and_append_only_audit() -> None:
    source = Path("apps/api/migrations/versions/0005_safety_case_lifecycle.py").read_text(
        encoding="utf-8"
    )

    assert "INITIAL_REPORT" in source
    assert "FINAL_INVESTIGATION" in source
    assert "official_direct_causes" in source
    assert "responsibility_findings" in source
    assert "rectification_has_open_issues" in source
    assert "ck_safety_case_rectification_issues_stage" in source
    assert "loss_amount_minor >= 0" in source
    assert "reviewer_id <> submitted_by" in source
    assert "reject_safety_case_self_approval" in source
    assert "validate_safety_case_candidate_submitter" in source
    assert "trg_event_item_candidate_submitter" in source
    assert "trg_event_relation_candidate_submitter" in source
    assert "candidate submitter does not match authoritative item submitter" in source
    assert "target_item.submitted_by" in source
    assert "validate_claim_evidence_provenance" in source
    assert "claim evidence version must match claim version" in source
    assert "PDF evidence block must belong to the claim version and page" in source
    assert "HTML evidence locator must resolve in the claim version processing run" in source
    assert "PRIMARY_OFFICIAL evidence requires an A0/A1 item source" in source
    assert "validate_safety_case_profile_projection" in source
    assert "validate_claim_conflict" in source
    assert "validate_event_item_projection" in source
    assert "validate_event_relation_projection" in source
    assert "accepted protected claim requires confirmed event membership" in source
    assert "protected claim decision is final" in source
    assert "event membership requires its accepted candidate decision" in source
    assert "event relation endpoints must be confirmed members of its event" in source
    assert "event relation stage semantics are invalid" in source
    assert "correction source must be strictly later than its target" in source
    assert "trg_event_relation_projection" in source
    assert "only accepted official claims may open a conflict" in source
    assert "hide_conflicting_safety_case_field" in source
    assert "CREATE TRIGGER" in source
    assert "reject_immutable_source_vault_change" in source
    assert "REVOKE INSERT, UPDATE, DELETE ON claim_field_decision FROM srbg_runtime" in source
    assert "REVOKE SELECT, INSERT, UPDATE, DELETE ON claim_conflict FROM srbg_runtime" in source
    assert "claim_conflict_runtime_safe_select" in source
    assert "public_safety_case_accepted_claim" in source
    assert "public_safety_case_conflict" in source
    assert (
        "current_value_snapshot"
        not in source.split("ON claim_conflict TO srbg_runtime", maxsplit=1)[0].rsplit(
            "GRANT SELECT", maxsplit=1
        )[-1]
    )
    assert "GRANT SELECT, INSERT ON claim_field_decision TO srbg_publication_writer" in source
    assert "ON claim_field_decision TO srbg_runtime" in source
    assert "ON claim_conflict_decision TO srbg_runtime" in source
    assert "ON event_item_decision TO srbg_runtime" in source
    assert "ENABLE ROW LEVEL SECURITY" in source


def test_round04_migration_has_reversible_constraint_changes() -> None:
    source = Path("apps/api/migrations/versions/0005_safety_case_lifecycle.py").read_text(
        encoding="utf-8"
    )

    assert "ck_round04_item_type" in source
    assert "ck_round04_item_risk" in source
    assert "ck_round04_review_risk" in source
    assert "ck_round02_item_type" in source
    assert "ck_round02_item_risk" in source
    assert "ck_review_risk_level" in source
    assert "refusing Round04 downgrade while SAFETY_CASE data exists" in source


@pytest.mark.skipif(
    not os.environ.get("SRBG_ROUND04_MIGRATION_DATABASE_URL"),
    reason="requires a dedicated disposable PostgreSQL database",
)
def test_round04_upgrade_downgrade_upgrade_on_disposable_database(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_url = os.environ["SRBG_ROUND04_MIGRATION_DATABASE_URL"]
    parsed = urlsplit(database_url.replace("postgresql+asyncpg", "postgresql", 1))
    if parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError("migration replay is restricted to loopback PostgreSQL")
    if not (parsed.path.removeprefix("/").startswith("srbg_it_") or "round04" in parsed.path):
        raise ValueError("migration replay requires an explicitly disposable database")

    config = Config("apps/api/alembic.ini")
    config.set_main_option("sqlalchemy.url", database_url)
    monkeypatch.setenv("SRBG_DATABASE_URL", database_url)
    get_settings.cache_clear()
    try:
        command.upgrade(config, "0004_pdf_ocr_versioning")
        command.upgrade(config, "0005_safety_case_lifecycle")
        command.downgrade(config, "0004_pdf_ocr_versioning")
        command.upgrade(config, "0005_safety_case_lifecycle")
        asyncio.run(_assert_runtime_conflict_column_boundary(database_url))
    finally:
        get_settings.cache_clear()


async def _assert_runtime_conflict_column_boundary(database_url: str) -> None:
    engine = create_async_engine(database_url)
    try:
        async with engine.connect() as connection:
            assert await connection.scalar(
                text(
                    "SELECT has_column_privilege("
                    "'srbg_runtime','claim_conflict','field_name','SELECT')"
                )
            )
            assert not await connection.scalar(
                text(
                    "SELECT has_column_privilege("
                    "'srbg_runtime','claim_conflict','current_value_snapshot','SELECT')"
                )
            )
            assert not await connection.scalar(
                text(
                    "SELECT has_column_privilege("
                    "'srbg_runtime','claim_conflict','candidate_value_snapshot','SELECT')"
                )
            )
            assert not await connection.scalar(
                text(
                    "SELECT has_column_privilege("
                    "'srbg_runtime','claim_conflict','current_claim_id','SELECT')"
                )
            )
            assert not await connection.scalar(
                text(
                    "SELECT has_column_privilege("
                    "'srbg_runtime','claim_conflict','candidate_claim_id','SELECT')"
                )
            )
            assert await connection.scalar(
                text(
                    "SELECT has_column_privilege("
                    "'srbg_runtime','claim_field_decision','action','SELECT')"
                )
            )
            assert not await connection.scalar(
                text(
                    "SELECT has_column_privilege("
                    "'srbg_runtime','claim_field_decision','reason','SELECT')"
                )
            )
            assert not await connection.scalar(
                text(
                    "SELECT has_column_privilege("
                    "'srbg_runtime','claim_conflict_decision','chosen_claim_id','SELECT')"
                )
            )
            assert not await connection.scalar(
                text(
                    "SELECT has_column_privilege("
                    "'srbg_runtime','claim_conflict_decision','reason','SELECT')"
                )
            )
            assert await connection.scalar(
                text(
                    "SELECT has_column_privilege("
                    "'srbg_runtime','event_item_decision','candidate_id','SELECT')"
                )
            )
            assert not await connection.scalar(
                text(
                    "SELECT has_column_privilege("
                    "'srbg_runtime','event_item_decision','reason','SELECT')"
                )
            )
            assert await connection.scalar(
                text(
                    "SELECT has_table_privilege("
                    "'srbg_runtime','public_safety_case_accepted_claim','SELECT')"
                )
            )
            assert await connection.scalar(
                text(
                    "SELECT has_table_privilege("
                    "'srbg_runtime','public_safety_case_conflict','SELECT')"
                )
            )
    finally:
        await engine.dispose()
