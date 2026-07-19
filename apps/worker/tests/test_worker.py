import srbg_worker.app as worker
from srbg_worker.ai_content_preparation import _INSERT_STEP_SQL, _MODEL_PROFILE_VERSION
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
    assert worker.celery_app.conf.task_routes["srbg.ai.generate_attempt"] == {
        "queue": "ai"
    }
    assert _MODEL_PROFILE_VERSION == "ai01-deepseek-deepseek-v4-flash-v1"
    assert _INSERT_STEP_SQL.count("CAST(:status AS varchar)") == 2


def test_v2_review_reprocessing_is_dispatched_by_outbox_id() -> None:
    schedule = worker.celery_app.conf.beat_schedule["reprocess-v2-owner-review"]

    assert schedule["task"] == "srbg.intelligence_v2.review_dispatch"
    assert schedule["options"] == {"queue": "publisher"}
    assert worker.celery_app.conf.task_routes["srbg.intelligence_v2.review_reprocess"] == {
        "queue": "publisher"
    }


def test_ai_runtime_probe_runs_every_thirty_seconds_with_api_callback() -> None:
    schedule = worker.celery_app.conf.beat_schedule["observe-ai-runtime"]

    assert schedule["task"] == "srbg.ai.runtime_probe_dispatch"
    assert schedule["schedule"] == 30.0
    assert worker.celery_app.conf.task_routes["srbg.ai.runtime_observation"] == {
        "queue": "celery"
    }


def test_real_schema_canary_is_scheduled_every_six_hours_and_stays_on_ai_queue() -> None:
    schedule = worker.celery_app.conf.beat_schedule["run-ai-v2-fixed-canary"]

    assert schedule["task"] == "srbg.ai.v2_canary_dispatch"
    assert schedule["schedule"] == 21600.0
    assert worker.celery_app.conf.task_routes["srbg.ai.v2_canary_result"] == {
        "queue": "celery"
    }


def test_fixed_canary_refuses_unapproved_environment_before_database_access(monkeypatch) -> None:
    monkeypatch.setattr(
        worker,
        "settings",
        worker.settings.model_copy(update={"environment": "demo"}),
    )
    monkeypatch.setattr(
        worker,
        "_ai_repository",
        lambda: (_ for _ in ()).throw(AssertionError("database must not be opened")),
    )

    result = worker.celery_app.tasks["srbg.ai.v2_canary_dispatch"].run()

    assert result == {
        "dispatched": 0,
        "reason": "AI_CANARY_ENVIRONMENT_NOT_AUTHORIZED",
    }


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
    assert "srbg.sources.qualify" not in worker.celery_app.conf.task_routes
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
            update={
                "source_discovery_enabled": True,
                "baidu_search_enabled": True,
                "baidu_search_api_key": worker.settings.baidu_search_api_key,
            }
        ),
    )

    def record(name: str, **values: object) -> None:
        sent.append((name, values))

    monkeypatch.setattr(worker.celery_app, "send_task", record)  # type: ignore[attr-defined]

    result = worker.celery_app.tasks["srbg.sources.discovery.dispatch"].run()

    assert result["disabled"] is False
    assert result["dispatched"] == 1
    assert set(result) == {"disabled", "dispatched", "discovery_run_id"}
    assert len(sent) == 1
    assert sent[0][0] == "srbg.sources.discovery.personal_cycle"
    assert sent[0][1]["queue"] == "discovery"
    for name, values in sent[1:]:
        assert name == "srbg.sources.discovery.query"
        assert set(values) == {"kwargs", "queue"}
        assert values["queue"] == "discovery"
        kwargs = values["kwargs"]
        assert isinstance(kwargs, dict)
        assert set(kwargs) == {"query_code", "discovery_run_id"}
        assert kwargs["query_code"] in QUERY_CATALOG
        serialized = repr(values)
        assert all(spec.query not in serialized for spec in QUERY_CATALOG.values())
