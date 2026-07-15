from inspect import getsource
from pathlib import Path

from srbg_api.publication.service import PublicationService
from srbg_worker import app as worker


def test_projection_invalidations_are_consumed_through_publication_service() -> None:
    service_source = getsource(PublicationService)
    worker_source = Path("apps/worker/src/srbg_worker/app.py").read_text(encoding="utf-8")

    assert "process_projection_invalidation_once" in service_source
    assert "await service.process_projection_invalidation_once" in worker_source
    assert "srbg.publication.projections" in worker.celery_app.tasks
    route = worker.celery_app.conf.task_routes["srbg.publication.projections"]
    assert route["queue"] == "publisher"


def test_cache_projection_uses_generation_pointer_and_visibility() -> None:
    worker_source = Path("apps/worker/src/srbg_worker/app.py").read_text(encoding="utf-8")

    assert "generation" in worker_source
    assert "visible" in worker_source
    assert "pipeline(transaction=True)" in worker_source
