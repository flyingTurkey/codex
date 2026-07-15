from uuid import UUID

from srbg_api.operations.failures import failure_record
from srbg_worker.app import celery_app


def test_worker_uses_late_ack_priority_and_bounded_redelivery() -> None:
    assert celery_app.conf.task_acks_late is True
    assert celery_app.conf.task_reject_on_worker_lost is True
    assert celery_app.conf.task_default_priority == 5
    assert celery_app.conf.broker_transport_options["priority_steps"] == list(range(10))


def test_failure_record_ignores_payload_and_exposes_no_body_hash_or_exception() -> None:
    record = failure_record(
        task_name="srbg.ai.generate",
        task_id="019b0000-0000-7000-8000-000000000001",
        args=({"document": "sensitive body"},),
        kwargs={"api_key": "secret"},
        exception=RuntimeError("provider leaked detail"),
    )
    assert record.execution_id == UUID("019b0000-0000-7000-8000-000000000001")
    assert record.task_kind == "AI"
    assert record.replayable is False
    assert record.error_code == "RUNTIMEERROR"
    assert "sensitive" not in repr(record)
    assert "secret" not in repr(record)
    assert "provider leaked detail" not in repr(record)
    assert "sha256" not in repr(record).lower()


def test_only_database_reconstructable_task_kinds_are_replayable() -> None:
    safe = failure_record(
        task_name="srbg.publication.outbox",
        task_id="019b0000-0000-7000-8000-000000000002",
        args=(),
        kwargs={},
        exception=RuntimeError("bounded"),
    )
    unsafe = failure_record(
        task_name="srbg.ai.generate",
        task_id="019b0000-0000-7000-8000-000000000003",
        args=({"model_input": "never persist"},),
        kwargs={},
        exception=RuntimeError("bounded"),
    )
    assert safe.replayable is True
    assert unsafe.replayable is False


def test_manual_replays_are_polled_on_the_priority_publisher_queue() -> None:
    schedule = celery_app.conf.beat_schedule["execute-priority-replays"]
    assert schedule["task"] == "srbg.operations.replay"
    assert schedule["options"] == {"queue": "publisher", "priority": 9}
    assert celery_app.conf.task_routes["srbg.operations.replay"] == {"queue": "publisher"}
