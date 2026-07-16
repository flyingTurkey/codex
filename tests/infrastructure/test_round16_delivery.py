from pathlib import Path


def test_round16_runbook_and_acceptance_surface_required_recovery_paths() -> None:
    runbook = Path("docs/operations/runbooks.md").read_text(encoding="utf-8")
    for marker in (
        "source_false_success",
        "queue_backlog",
        "redis_rebuild",
        "object_storage_unavailable",
        "retention_mistake",
        "safe_replay",
    ):
        assert marker in runbook
    makefile = Path("Makefile").read_text(encoding="utf-8")
    assert "phase2-round16-test:" in makefile
    assert "verify_round16_migration.py" in makefile
