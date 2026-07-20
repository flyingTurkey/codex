from pathlib import Path

MIGRATION = Path("apps/api/migrations/versions/0041_t06_ai_runtime_projection.py")


def test_t06_migration_persists_only_real_content_success_and_durable_projection_handoff() -> None:
    source = MIGRATION.read_text(encoding="utf-8")

    for token in (
        'down_revision = "0040_t05_reader_projection"',
        '"ai_approved_content_success_v2"',
        '"source_excerpt_version_v2"',
        '"ai_summary_state_event_v2"',
        '"ai_projection_refresh_outbox_v2"',
        "t06-content-summary-v1",
        "summarize-v2-output-1.0.0",
        "APPROVED_CONTENT",
        "NOT_GENERATED",
        "PROCESSING",
        "TEMPORARILY_UNAVAILABLE",
        "SCHEMA_REJECTED",
        "INSUFFICIENT_EVIDENCE",
        "SUCCEEDED",
        "STALE",
        "prevent_t06_append_only_mutation",
        'sa.Column("reason_code", sa.String(80), nullable=False)',
    ):
        assert token in source

    assert "mock" not in source.casefold()


def test_t06_migration_keeps_publication_writes_behind_publication_role() -> None:
    source = MIGRATION.read_text(encoding="utf-8")

    assert "GRANT UPDATE ON ai_projection_refresh_outbox_v2 TO srbg_publication_writer" in source
    assert "GRANT INSERT,UPDATE ON ai_projection_refresh_outbox_v2" not in source
    assert "GRANT INSERT ON intelligence_projection_v2 TO srbg_worker_role" not in source
    assert "GRANT UPDATE ON intelligence_projection_v2 TO srbg_worker_role" not in source
