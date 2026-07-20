from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

MIGRATION = Path("apps/api/migrations/versions/0026_automatic_evidence_facts.py")


def test_pers06_remains_in_the_single_head_chain_after_pers05() -> None:
    script = ScriptDirectory.from_config(Config("apps/api/alembic.ini"))
    assert script.get_current_head() == "0045_t12_media_delivery"
    revision = script.get_revision("0026_automatic_evidence_facts")
    assert revision is not None
    assert revision.down_revision == "0025_personal_source_discovery"


def test_pers06_persists_automatic_fact_provenance_and_ai_judgments() -> None:
    sql = MIGRATION.read_text(encoding="utf-8")
    for token in (
        "AUTOMATED_EVIDENCE_GATE",
        "automatic_evidence_acceptance",
        "automatic_evidence_fact_state_event",
        "rule_version",
        "input_document_version_id",
        "evidence_set_sha256",
        "system_actor_id",
        "ai_judgment",
        "ai_judgment_evidence",
        "EVIDENCE_GATING",
        "personal_content_outbox",
        "forbid_new_claim_review_task",
    ):
        assert token in sql


def test_pers06_lifecycle_is_idempotent_and_requeues_changed_documents() -> None:
    sql = MIGRATION.read_text(encoding="utf-8")
    for token in (
        "uq_personal_content_version_action",
        "ON CONFLICT(document_version_id,action) DO NOTHING",
        "DOCUMENT_VERSION_CHANGED",
        "NEW.state IN ('WITHDRAWN','SUPERSEDED')",
        "'DOCUMENT_'||NEW.state",
        "AFTER INSERT ON content_lifecycle_event",
        "source_content_outbox",
        "INVALIDATE",
    ):
        assert token in sql
