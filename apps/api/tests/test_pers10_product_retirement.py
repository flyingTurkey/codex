from pathlib import Path

from srbg_api.main import create_app

ROOT = Path("apps/api/src/srbg_api")
MAIN = ROOT / "main.py"
AUTH = ROOT / "auth.py"
MODELS = Path("packages/contracts/src/srbg_contracts/models.py")
SOURCE_RUNTIME = tuple(
    Path(path)
    for path in (
        "apps/api/src/srbg_api/source_registry/api.py",
        "apps/api/src/srbg_api/source_registry/service.py",
        "apps/api/src/srbg_api/source_registry/repository.py",
        "apps/api/src/srbg_api/config.py",
    )
)
DOCKERIGNORE = Path(".dockerignore")
PUBLICATION_REPOSITORY = ROOT / "publication" / "repository.py"


def test_personal_product_has_no_admin_router_mounts() -> None:
    source = MAIN.read_text(encoding="utf-8")
    assert "source_automation_router" not in source
    assert "ai_admin_router" not in source
    paths = create_app(checkers={}).openapi()["paths"]
    assert not any(path.startswith("/api/v1/admin") for path in paths)
    assert "/api/v1/settings/ai/providers" in paths


def test_personal_product_exposes_only_owner_role() -> None:
    models = MODELS.read_text(encoding="utf-8")
    user_role = models[models.index("class UserRole"):models.index("class Channel")]
    assert 'OWNER = "owner"' in user_role
    for legacy in (
        "VIEWER",
        "EDITOR",
        "REVIEWER",
        "SOURCE_ADMIN",
        "PLATFORM_ADMIN",
        "AUDITOR",
        "GOLD_ANNOTATOR",
        "GOLD_ARBITRATOR",
    ):
        assert legacy not in user_role
    assert "def require_roles(" not in AUTH.read_text(encoding="utf-8")


def test_business_runtime_never_reads_legacy_archive() -> None:
    offenders = []
    for base in (Path("apps/api/src"), Path("apps/worker/src"), Path("apps/web/app")):
        for path in base.rglob("*"):
            if path.is_file() and path.suffix in {".py", ".ts", ".vue"}:
                if "legacy_governance_archive" in path.read_text(encoding="utf-8"):
                    offenders.append(str(path))
    assert offenders == []


def test_enterprise_governance_runtime_modules_are_physically_removed() -> None:
    assert not list((ROOT / "source_automation").glob("*.py"))
    assert not list((ROOT / "operations").glob("*.py"))
    assert not Path("apps/worker/src/srbg_worker/source_qualification.py").exists()


def test_shared_personal_source_runtime_contains_no_enterprise_branches() -> None:
    forbidden = (
        '"/admin/',
        "AdminSourceService",
        "round17_",
        "ROUND17_",
        "source_qualification_enabled",
        "PRODUCTION_APPROVAL",
        "SOURCE_QUALIFICATION",
    )
    offenders: dict[str, list[str]] = {}
    for path in SOURCE_RUNTIME:
        source = path.read_text(encoding="utf-8")
        matches = [token for token in forbidden if token in source]
        if matches:
            offenders[str(path)] = matches
    assert offenders == {}


def test_ai_runtime_schemas_are_included_in_container_context() -> None:
    dockerignore = DOCKERIGNORE.read_text(encoding="utf-8")
    for schema in ("classify", "extract", "summarize", "verify"):
        assert f"!docs/codex-kit/assets/schemas/{schema}-output.schema.json" in dockerignore


def test_personal_projection_uses_outbox_document_version_column() -> None:
    source = PUBLICATION_REPOSITORY.read_text(encoding="utf-8")
    assert 'event["version_id"]' not in source
    assert 'event["document_version_id"]' in source
