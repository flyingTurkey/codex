import asyncio
import inspect
from datetime import UTC, datetime

import srbg_worker.app as worker
from srbg_api.publication.repository import PostgresPublicationRepository
from srbg_api.publication.service import PublicationService
from srbg_worker.ai_content_preparation import _INSERT_ITEM_SQL, PostgresAiPreparationRepository

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
