from inspect import getsource
from pathlib import Path

from srbg_api.publication.repository import PostgresPublicationRepository
from srbg_api.publication.service import PublicationService


def test_new_pipeline_never_creates_claim_review_tasks() -> None:
    source = Path("apps/worker/src/srbg_worker/ai_content_preparation.py").read_text(
        encoding="utf-8"
    )
    assert "INSERT INTO review_task" not in source
    assert "'CLAIM_REVIEW'" not in source
    assert "AUTOMATED_EVIDENCE_GATE" in source


def test_publication_service_is_the_only_personal_projection_writer() -> None:
    repository_source = getsource(PostgresPublicationRepository)
    service_source = getsource(PublicationService)
    assert "INSERT INTO personal_content_projection" in repository_source
    assert "process_personal_content_once" in service_source
    for root in (Path("apps/worker/src"), Path("apps/api/src")):
        for path in root.rglob("*.py"):
            if path.as_posix().endswith("publication/repository.py"):
                continue
            source = path.read_text(encoding="utf-8")
            assert "INSERT INTO personal_content_projection" not in source, path
