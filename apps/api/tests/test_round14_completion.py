from pathlib import Path

from srbg_contracts import PublishedEventDetailV1, PublishedEventSummaryV1

ROOT = Path(__file__).resolve().parents[3]


def test_published_contract_is_event_revision_keyed_and_complete() -> None:
    summary_fields = PublishedEventSummaryV1.model_fields
    detail_fields = PublishedEventDetailV1.model_fields

    assert summary_fields["projection_version"].annotation.__args__ == ("1.0.0", "1.1.0")
    assert "event_revision_id" in summary_fields
    assert "publication_revision_ids" in summary_fields
    assert {"documents", "source_comparison", "type_detail"} <= detail_fields.keys()


def test_default_ordinary_reads_are_wired_to_projection_reader_login() -> None:
    source = (ROOT / "apps/api/src/srbg_api/main.py").read_text(encoding="utf-8")

    assert "create_projection_reader_engine" in source
    assert "PublishedProjectionReader(create_projection_reader_engine(settings))" in source
    assert "public_intelligence_service=published_reader" in source


def test_event_writes_do_not_require_or_insert_a_representative_item() -> None:
    source = (ROOT / "apps/api/src/srbg_api/discovery/repository.py").read_text(encoding="utf-8")
    method = source.split("    async def save_event(", 1)[1].split(
        "    async def remove_saved_event(", 1
    )[0]

    assert "SELECT projection.item_id" not in method
    assert "(owner_id,event_id,saved_at)" in method
    assert "(collection_id,owner_id,event_id,added_at)" in method


def test_corrective_migration_finishes_event_keyed_consumers_and_switch() -> None:
    migration = ROOT / "apps/api/migrations/versions/0014b_event_consumer_switch.py"
    source = migration.read_text(encoding="utf-8")

    assert 'revision = "0014b_event_consumer_switch"' in source
    assert "event_consumer_switch" in source
    assert "ROLLBACK_READ_ONLY" in source
    assert "event_revision_id" in source
    assert "publication_revision_ids" in source
    assert "uq_saved_event" in source
    assert "uq_collection_event" in source
    assert "uq_feedback_actor_event" in source
    assert "DELETE FROM" not in source.upper()
