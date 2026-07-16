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


def test_worker_only_schedules_the_database_source_dispatcher() -> None:
    assert "srbg.safety_regulations.discover" in worker.celery_app.tasks
    schedule = worker.celery_app.conf.beat_schedule["dispatch-due-source-schedules"]

    assert schedule["task"] == "srbg.schedules.dispatch"
    assert schedule["schedule"] == 30.0
    assert all(
        entry["task"] != "srbg.safety_regulations.discover"
        for entry in worker.celery_app.conf.beat_schedule.values()
    )
