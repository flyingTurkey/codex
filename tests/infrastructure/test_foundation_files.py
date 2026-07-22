from pathlib import Path

from scripts.resilience_test import COMPOSE

ROOT = Path(__file__).parents[2]


def test_compose_uses_pinned_services_and_loopback_ports() -> None:
    compose = (ROOT / "infra/compose/compose.yaml").read_text(encoding="utf-8")

    postgres_dockerfile = (ROOT / "infra/compose/Dockerfile.postgres").read_text(
        encoding="utf-8"
    )
    assert "postgres:17.10-bookworm" in postgres_dockerfile
    assert "pgvector/pgvector:0.8.2-pg17-bookworm" in postgres_dockerfile
    assert "redis:7.4.7-alpine3.21" in compose
    assert "minio/minio:RELEASE.2025-09-07T16-13-09Z" in compose
    assert (
        "clamav/clamav:1.5.2-debian13-slim"
        "@sha256:14e2e0805c6a5ff6728ea591c05565e0f0954d93e8701919012c3a8c44e20674"
        in compose
    )
    assert ":latest" not in compose
    assert "127.0.0.1:${WEB_PORT:-3000}:3000" in compose
    assert "127.0.0.1:${API_PORT:-8000}:8000" in compose
    assert "service_completed_successfully" in compose


def test_primary_worker_healthcheck_has_bounded_startup_margin() -> None:
    compose = (ROOT / "infra/compose/compose.yaml").read_text(encoding="utf-8")
    worker_section = compose.split("  worker:\n", 1)[1].split("  parser:\n", 1)[0]

    assert "celery@worker --timeout 2" in worker_section
    assert "      timeout: 8s" in worker_section


def test_source_upload_runtime_requires_private_healthy_clamav() -> None:
    compose = (ROOT / "infra/compose/compose.yaml").read_text(encoding="utf-8")

    assert "SRBG_CLAMAV_HOST: ${SRBG_CLAMAV_HOST:-clamav}" in compose
    assert "SRBG_CLAMAV_PORT: ${SRBG_CLAMAV_PORT:-3310}" in compose
    assert "  clamav:\n" in compose
    assert '      - "3310"' in compose
    assert '127.0.0.1:${CLAMAV_PORT' not in compose
    assert "      clamav:\n        condition: service_healthy" in compose
    assert "  clamav-db:\n" in compose


def test_clean_database_bootstraps_login_roles_before_migrations() -> None:
    compose = (ROOT / "infra/compose/compose.yaml").read_text(encoding="utf-8")

    bootstrap = compose.split("  role-bootstrap:\n", 1)[1].split("  migrate:\n", 1)[0]
    migrate = compose.split("  migrate:\n", 1)[1].split("  role-init:\n", 1)[0]
    role_init = compose.split("  role-init:\n", 1)[1].split("  api:\n", 1)[0]
    for role in (
        "srbg_api_login",
        "srbg_worker_login",
        "srbg_publisher_login",
        "srbg_projection_reader_login",
    ):
        assert f"CREATE ROLE {role} LOGIN" in bootstrap
    assert "postgres:\n        condition: service_healthy" in bootstrap
    assert "role-bootstrap:\n        condition: service_completed_successfully" in migrate
    assert "migrate:\n        condition: service_completed_successfully" in role_init


def test_makefile_exposes_required_quality_and_runtime_targets() -> None:
    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")

    for target in (
        "setup",
        "dev",
        "runtime-ready",
        "down",
        "lint",
        "typecheck",
        "test",
        "contract-test",
        "security-check",
        "smoke",
        "resilience-test",
        "fixture-replay",
        "quality-gate",
        "web-e2e",
        "web-a11y",
    ):
        assert f"{target}:" in makefile
    assert "$(UV) run python scripts/check_contract_generation.py" in makefile


def test_makefile_assigns_external_io_timeout_before_exporting_it() -> None:
    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")

    assignment = "SRBG_EXTERNAL_IO_TIMEOUT_SECONDS ?= 2"
    export = "export SRBG_S3_BUCKET SRBG_S3_REGION SRBG_EXTERNAL_IO_TIMEOUT_SECONDS"
    assert makefile.index(assignment) < makefile.index(export)


def test_environment_example_is_demo_only_and_documents_timeouts() -> None:
    example = (ROOT / ".env.example").read_text(encoding="utf-8")

    assert "DEVELOPMENT-ONLY" in example
    assert "SRBG_EXTERNAL_IO_TIMEOUT_SECONDS=2" in example
    assert "SRBG_ENVIRONMENT=demo" in example
    assert "changeme" not in example.lower()


def test_runtime_images_define_non_root_application_users() -> None:
    python_image = (ROOT / "infra/compose/Dockerfile.python").read_text(encoding="utf-8")
    web_image = (ROOT / "infra/compose/Dockerfile.web").read_text(encoding="utf-8")

    assert "USER app" in python_image
    assert "USER node" in web_image


def test_runtime_build_context_excludes_repository_only_material() -> None:
    dockerignore = (ROOT / ".dockerignore").read_text(encoding="utf-8")

    for pattern in (
        "docs",
        "tests",
        "**/tests",
        "**/test-results",
        "**/playwright-report",
        "README*.md",
        "CHANGELOG.md",
        "AGENTS.md",
        "VALIDATION.md",
        "Makefile",
    ):
        assert pattern in dockerignore.splitlines()


def test_runtime_build_context_includes_authoritative_publication_gate_assets() -> None:
    dockerignore = (ROOT / ".dockerignore").read_text(encoding="utf-8")

    included_assets = {
        "!docs/codex-kit/assets/schemas/autonomous-classify-output.schema.json",
        "!docs/codex-kit/assets/validation/publication_gate.json",
        "!docs/codex-kit/assets/validation/publication_evaluation.schema.json",
        "!docs/codex-kit/assets/validation/publication_gate_v3.json",
        "!docs/codex-kit/assets/validation/publication_evaluation_v3.schema.json",
        "!docs/codex-kit/assets/validation/publication_gate_v4.json",
        "!docs/codex-kit/assets/validation/publication_evaluation_v4.schema.json",
        "!docs/codex-kit/assets/validation/publication_gate_v5.json",
        "!docs/codex-kit/assets/validation/publication_evaluation_v5.schema.json",
        "!docs/codex-kit/assets/validation/publication_gate_v6.json",
        "!docs/codex-kit/assets/validation/publication_evaluation_v6.schema.json",
        "!docs/codex-kit/assets/validation/publication_gate_v7.json",
        "!docs/codex-kit/assets/validation/publication_evaluation_v7.schema.json",
    }

    assert included_assets <= set(dockerignore.splitlines())


def test_ci_pins_actions_and_runs_all_round_zero_gates() -> None:
    workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")

    assert "actions/checkout@93cb6efe18208431cddfb8368fd83d5badbf9bfd" in workflow
    assert "actions/setup-python@ece7cb06caefa5fff74198d8649806c4678c61a1" in workflow
    assert "actions/setup-node@48b55a011bda9f5d6aeb4c2d9c7362e8dae4041e" in workflow
    for command in (
        "make lint",
        "make typecheck",
        "make test",
        "make contract-test",
        "make security-check",
        "make smoke",
        "make resilience-test",
        "make web-e2e",
        "make web-a11y",
    ):
        assert command in workflow


def test_round04_fixed_fixture_and_isolated_integration_gates_are_wired() -> None:
    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
    workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")

    assert "safety-case-test:" in makefile
    assert "scripts/run_isolated_integration.py" in makefile
    assert "apps/api/tests/test_safety_case_integration.py" in makefile
    assert "apps/api/tests/test_round04_official_fixtures.py" in makefile
    assert "make safety-case-test" in workflow


def test_project_tool_caches_are_kept_inside_the_workspace() -> None:
    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    environment_script = (ROOT / "scripts/use-local-toolchain.ps1").read_text(encoding="utf-8")

    assert "UV_CACHE_DIR ?= $(CURDIR)/.cache/uv" in makefile
    assert "UV_PYTHON_INSTALL_DIR ?= $(CURDIR)/.tools/python" in makefile
    assert "PLAYWRIGHT_BROWSERS_PATH ?= $(CURDIR)/.cache/ms-playwright" in makefile
    assert "UV ?= $(CURDIR)/.tools/uv/uv.exe" in makefile
    assert "PNPM ?= $(CURDIR)/.tools/node/pnpm.cmd" in makefile
    assert "export PATH := $(CURDIR)/.tools/node;$(PATH)" in makefile
    assert ".tools/" in gitignore
    assert ".cache/" in gitignore
    assert "~$*" in gitignore
    assert ".tools\\node" in environment_script
    assert ".tools\\uv" in environment_script
    assert ".tools\\make\\tools\\install\\bin" in environment_script


def test_compose_commands_use_repository_as_project_directory() -> None:
    compose = (ROOT / "infra/compose/compose.yaml").read_text(encoding="utf-8")
    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")

    assert "docker compose --project-directory . -f infra/compose/compose.yaml" in makefile
    assert "-include .env" in makefile
    assert "export WEB_PORT API_PORT" in makefile
    assert COMPOSE[:5] == ["docker", "compose", "--project-directory", ".", "-f"]
    assert compose.count("context: .\n") == 11
    assert "  parser:" in compose
    assert "  publisher:" in compose
    assert "context: ../.." not in compose


def test_browser_gates_reuse_the_ready_runtime_without_forced_rebuilds() -> None:
    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")

    assert "runtime-ready: personal-data-ready\n\t$(COMPOSE) up --detach --wait" in makefile
    assert "web-e2e: runtime-ready" in makefile
    assert "web-a11y: runtime-ready" in makefile


def test_web_runtime_serves_prebuilt_nitro_output() -> None:
    dockerfile = (ROOT / "infra/compose/Dockerfile.web").read_text(encoding="utf-8")
    compose = (ROOT / "infra/compose/compose.yaml").read_text(encoding="utf-8")

    assert "pnpm --filter @srbg/web build" in dockerfile
    assert 'CMD ["node", "apps/web/.output/server/index.mjs"]' in dockerfile
    assert 'CMD ["pnpm", "--filter", "@srbg/web", "dev"]' not in dockerfile
    assert "NITRO_HOST: 0.0.0.0" in compose
    assert "NITRO_PORT: 3000" in compose


def test_web_e2e_gate_does_not_mutate_versioned_acceptance_assets() -> None:
    for spec in (ROOT / "apps/web/tests/e2e").glob("*.spec.ts"):
        content = spec.read_text(encoding="utf-8")
        assert "docs/acceptance/assets" not in content, (
            f"{spec.name} must keep the browser gate read-only"
        )


def test_web_image_keeps_versioned_esbuild_binaries_isolated_and_cached() -> None:
    workspace = (ROOT / "pnpm-workspace.yaml").read_text(encoding="utf-8")
    dockerfile = (ROOT / "infra/compose/Dockerfile.web").read_text(encoding="utf-8")

    assert "hoistPattern:\n  - '*'\n  - '!@esbuild/*'" in workspace
    assert "target=/home/node/.local/share/pnpm/store" in dockerfile


def test_security_scan_uses_only_git_delivery_files() -> None:
    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")

    assert "$(UV) run python scripts/prepare_security_scan.py" in makefile
    assert '-v "$(CURDIR)/.cache/trivy-input:/workspace:ro"' in makefile
    assert "TRIVY_SKIP_DIRS" not in makefile


def test_round_zero_documentation_is_present() -> None:
    required_content = {
        "README.md": ["make setup", "make dev", "D:\\SRBGData"],
        "CHANGELOG.md": ["Round 00", "工程基线"],
        "docs/adr/0001-modular-monolith.md": ["模块化单体", "SourceAdapter"],
        "docs/acceptance/round-00-foundation.md": [
            "Redis",
            "18000",
            "round-00-homepage-desktop.png",
        ],
    }

    for relative_path, snippets in required_content.items():
        content = (ROOT / relative_path).read_text(encoding="utf-8")
        for snippet in snippets:
            assert snippet in content
