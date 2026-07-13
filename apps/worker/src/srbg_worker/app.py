"""Celery application and process health task."""

from celery import Celery
from srbg_api.config import get_settings
from srbg_api.logging import configure_logging

configure_logging()
settings = get_settings()
celery_app = Celery("srbg-worker", broker=settings.redis_url, backend=settings.redis_url)
celery_app.conf.update(
    enable_utc=True,
    timezone="UTC",
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    broker_connection_retry_on_startup=True,
)


@celery_app.task(name="srbg.system.health")  # type: ignore[untyped-decorator]
def health() -> dict[str, str]:
    return {"status": "ok", "service": "worker"}
