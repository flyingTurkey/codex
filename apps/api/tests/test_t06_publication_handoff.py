import asyncio
import inspect
from datetime import UTC, datetime

import srbg_worker.app as worker
from srbg_api.publication.repository import PostgresPublicationRepository
from srbg_api.publication.service import PublicationService
from srbg_worker.ai_content_preparation import (
    _AUTHORIZE_PERSONAL_SQL,
    _DOCUMENT_SQL,
    _INSERT_ITEM_SQL,
    PostgresAiPreparationRepository,
    _legacy_storage_class_for_primary_type,
)

NOW = datetime(2026, 7, 20, 9, 0, tzinfo=UTC)


class FakeRepository:
    def __init__(self) -> None:
        self.processed_at: datetime | None = None

    async def process_ai_projection_refresh_once(self, *, processed_at: datetime) -> bool:
        self.processed_at = processed_at
        return True


def test_ai_result_reaches_reader_only_through_publication_service() -> None:
    repository = FakeRepository()
    service = PublicationService(
        repository=repository,  # type: ignore[arg-type]
        gate=None,  # type: ignore[arg-type]
        now=lambda: NOW,
    )

    processed = asyncio.run(service.process_ai_projection_refresh_once())

    assert processed is True
    assert repository.processed_at == NOW


def test_projection_refresh_replay_does_not_duplicate_publication_decisions() -> None:
    source = inspect.getsource(PostgresPublicationRepository._record_v2_publication_decision)

    assert "pg_advisory_xact_lock" in source
    assert "WHERE NOT EXISTS" in source
    assert "projection_sha256 IS NOT DISTINCT FROM :hash" in source


def test_reader_revalidates_exact_accepted_claim_fingerprint_before_projection() -> None:
    source = inspect.getsource(PostgresPublicationRepository.refresh_v2_projection)

    assert 'row["raw_security_clean"]' in source
    assert "accepted_claim_set_sha256(current_claims)" in source
    assert 'row["accepted_claim_set_sha256"] != current_claim_hash' in source


def test_automatic_acceptance_is_machine_unreviewed_and_not_forced_to_r3() -> None:
    materialize = inspect.getsource(PostgresAiPreparationRepository.materialize)

    assert "owner_review_case_v2" not in materialize
    assert "'R1'" in _INSERT_ITEM_SQL
    assert "'R3'" not in _INSERT_ITEM_SQL


def test_filtered_decisions_have_no_publication_materialization_path() -> None:
    callback = inspect.getsource(worker._handle_ai_content_result)

    terminal = callback.index("trace.disposition is not AutomatedDisposition.AUTO_ACCEPTED")
    extraction = callback.index('transition(run_id, "EXTRACTING")')
    assert terminal < extraction
    assert "queue_qualification_review" not in callback


def test_live_source_bridge_remains_live_through_authoritative_preparation() -> None:
    assert "SET mode='SHADOW'" not in _AUTHORIZE_PERSONAL_SQL
    assert "run.mode IN ('LIVE','SHADOW')" in _DOCUMENT_SQL
    assert "run.mode='LIVE' AND run.status IN" in _AUTHORIZE_PERSONAL_SQL


def test_worker_semantic_recheck_renders_the_shared_full_prompt() -> None:
    callback = inspect.getsource(worker._handle_ai_content_result)
    dispatcher = inspect.getsource(worker._dispatch_ai_attempt)

    assert "<semantic_recheck>" not in callback
    assert "semantic_recheck=semantic_recheck" in dispatcher


def test_worker_separates_shadow_facts_from_production_decisions() -> None:
    callback = inspect.getsource(worker._handle_ai_content_result)
    repository = inspect.getsource(PostgresAiPreparationRepository.append_shadow_decision)

    assert "append_shadow_decision" in callback
    assert "qualification_shadow_decision_v2" in repository
    assert "affects_production" in repository


def test_ai_projection_outbox_projects_accepted_content_into_the_v2_reader() -> None:
    source = inspect.getsource(PostgresPublicationRepository.process_ai_projection_refresh_once)
    worker_source = inspect.getsource(worker._handle_ai_content_result)

    assert "refresh_v2_projection" in source
    assert "append_summary_state" in worker_source
    assert "process_ai_projection_refresh_once" in inspect.getsource(
        worker._drain_publication_projections
    )


def test_industry_update_keeps_an_independent_storage_type_and_channel() -> None:
    assert _legacy_storage_class_for_primary_type("INDUSTRY_UPDATE") == (
        "INDUSTRY_UPDATE",
        "INDUSTRY",
    )
