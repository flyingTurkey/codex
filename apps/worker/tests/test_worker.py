import srbg_worker.app as worker


def test_worker_registers_health_task() -> None:
    assert hasattr(worker, "celery_app")
    assert "srbg.system.health" in worker.celery_app.tasks

    result = worker.celery_app.tasks["srbg.system.health"].run()

    assert result == {"status": "ok", "service": "worker"}


def test_worker_uses_utc_and_json_serialization() -> None:
    assert hasattr(worker, "celery_app")

    assert worker.celery_app.conf.timezone == "UTC"
    assert worker.celery_app.conf.enable_utc is True
    assert worker.celery_app.conf.task_serializer == "json"
