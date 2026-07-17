import srbg_worker.app as worker
from srbg_worker.source_discovery import QUERY_CATALOG


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


def test_worker_periodically_dispatches_fixed_code_source_discovery() -> None:
    schedule = worker.celery_app.conf.beat_schedule["dispatch-automated-source-discovery"]

    assert schedule["task"] == "srbg.sources.discovery.dispatch"
    assert 300 <= schedule["schedule"] <= 86400
    assert worker.celery_app.conf.task_routes["srbg.sources.discovery.query"] == {
        "queue": "discovery"
    }
    assert worker.celery_app.conf.task_routes["srbg.sources.qualify"] == {
        "queue": "qualification"
    }
    assert worker.celery_app.conf.task_routes["srbg.source.fetch"] == {"queue": "parser"}


def test_disabled_discovery_dispatch_has_zero_messages(monkeypatch: object) -> None:
    sent: list[tuple[object, object]] = []
    monkeypatch.setattr(  # type: ignore[attr-defined]
        worker,
        "settings",
        worker.settings.model_copy(
            update={"source_discovery_enabled": False, "baidu_search_enabled": False}
        ),
    )
    monkeypatch.setattr(  # type: ignore[attr-defined]
        worker.celery_app,
        "send_task",
        lambda name, **values: sent.append((name, values)),
    )

    result = worker.celery_app.tasks["srbg.sources.discovery.dispatch"].run()

    assert result == {"disabled": True, "dispatched": 0, "discovery_run_id": None}
    assert sent == []


def test_disabled_discovery_query_creates_no_database_or_network_client(
    monkeypatch: object,
) -> None:
    monkeypatch.setattr(  # type: ignore[attr-defined]
        worker,
        "settings",
        worker.settings.model_copy(
            update={"source_discovery_enabled": False, "baidu_search_enabled": False}
        ),
    )

    def forbidden(*args: object, **kwargs: object) -> object:
        del args, kwargs
        raise AssertionError("disabled discovery must not construct external I/O")

    monkeypatch.setattr(worker, "create_database_engine", forbidden)  # type: ignore[attr-defined]
    result = worker.celery_app.tasks["srbg.sources.discovery.query"].run(
        query_code="HIGHWAY_SAFETY",
        discovery_run_id="019b0000-0000-7000-8000-000000009101",
    )

    assert result["disabled"] is True
    assert result["provider_calls"] == 0
    assert result["candidates_registered"] == 0


def test_enabled_dispatch_messages_contain_only_controlled_code_and_id(
    monkeypatch: object,
) -> None:
    sent: list[tuple[str, dict[str, object]]] = []
    monkeypatch.setattr(  # type: ignore[attr-defined]
        worker,
        "settings",
        worker.settings.model_copy(
            update={"source_discovery_enabled": True, "baidu_search_enabled": True}
        ),
    )

    def record(name: str, **values: object) -> None:
        sent.append((name, values))

    monkeypatch.setattr(worker.celery_app, "send_task", record)  # type: ignore[attr-defined]

    result = worker.celery_app.tasks["srbg.sources.discovery.dispatch"].run()

    assert result["disabled"] is False
    assert result["dispatched"] == len(QUERY_CATALOG)
    assert set(result) == {"disabled", "dispatched", "discovery_run_id"}
    assert len(sent) == len(QUERY_CATALOG)
    for name, values in sent:
        assert name == "srbg.sources.discovery.query"
        assert set(values) == {"kwargs", "queue"}
        assert values["queue"] == "discovery"
        kwargs = values["kwargs"]
        assert isinstance(kwargs, dict)
        assert set(kwargs) == {"query_code", "discovery_run_id"}
        assert kwargs["query_code"] in QUERY_CATALOG
        serialized = repr(values)
        assert all(spec.query not in serialized for spec in QUERY_CATALOG.values())
