from pathlib import Path

from scripts.audit_publication_paths import audit_publication_paths


def test_no_application_publication_write_bypasses_unique_repository() -> None:
    assert audit_publication_paths() == []


def test_all_runtime_gate_loaders_use_canonical_v21_files() -> None:
    main = Path("apps/api/src/srbg_api/main.py").read_text(encoding="utf-8")
    worker = Path("apps/worker/src/srbg_worker/app.py").read_text(encoding="utf-8")
    for source in (main, worker):
        assert 'policy_root / "publication_gate.json"' in source
        assert 'policy_root / "publication_evaluation.schema.json"' in source
    assert "publication_gate_v7.json" not in main
    assert "publication_gate_v3.json" not in worker


def test_every_lifecycle_route_delegates_to_publication_service() -> None:
    source = Path("apps/api/src/srbg_api/publication/api.py").read_text(encoding="utf-8")
    for method in ("decide_review", "revise", "republish", "withdraw"):
        assert f"_publication_service(request).{method}(" in source
    for route in ("/decisions", "/revisions", "/republish", "/withdrawals"):
        assert route in source
