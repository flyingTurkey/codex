import re
from pathlib import Path

from scripts.resilience_test import COMPOSE

ROOT = Path(__file__).parents[2]

PROFILED_SERVICES = {
    "automation": (
        "worker",
        "parser",
        "personal-source-worker",
        "publisher",
        "scheduler",
    ),
    "discovery": ("source-discovery",),
    "ai": ("ai-worker",),
    "observability": (
        "prometheus",
        "alertmanager",
        "grafana",
        "otel-collector",
    ),
}


def _compose_service_section(compose: str, service: str) -> str:
    marker = f"  {service}:\n"
    start = compose.index(marker)
    tail = compose[start + len(marker) :]
    next_service = re.search(r"^  [a-z0-9][a-z0-9-]*:\n", tail, flags=re.MULTILINE)
    end = next_service.start() if next_service else len(tail)
    return marker + tail[:end]


def _make_variable_words(makefile: str, name: str) -> tuple[str, ...]:
    lines = makefile.splitlines()
    prefix = f"{name} = "
    for index, line in enumerate(lines):
        if not line.startswith(prefix):
            continue
        value = line.removeprefix(prefix)
        while value.endswith("\\"):
            index += 1
            value = f"{value[:-1].strip()} {lines[index].strip()}"
        return tuple(value.split())
    raise AssertionError(f"missing Make variable: {name}")


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


def test_healthchecks_poll_fast_only_during_startup() -> None:
    compose = (ROOT / "infra/compose/compose.yaml").read_text(encoding="utf-8")

    for service in (
        "postgres",
        "redis",
        "minio",
        "anchor-minio",
        "api",
        "worker",
        "ai-worker",
        "web",
    ):
        section = _compose_service_section(compose, service)
        assert "      interval: 30s" in section
        assert "      start_interval: 3s" in section
        assert "      start_period: 30s" in section
        assert "      retries: 4" in section


def test_long_running_services_rotate_local_json_logs() -> None:
    compose = (ROOT / "infra/compose/compose.yaml").read_text(encoding="utf-8")
    example = (ROOT / ".env.example").read_text(encoding="utf-8")
    runtime_services = (
        "postgres",
        "redis",
        "clamav",
        "minio",
        "anchor-minio",
        "api",
        "worker",
        "parser",
        "source-discovery",
        "personal-source-worker",
        "ai-worker",
        "publisher",
        "scheduler",
        "web",
        "prometheus",
        "alertmanager",
        "grafana",
        "otel-collector",
    )

    assert "x-runtime-logging: &runtime-logging" in compose
    assert 'max-size: "${SRBG_DOCKER_LOG_MAX_SIZE:-10m}"' in compose
    assert 'max-file: "${SRBG_DOCKER_LOG_MAX_FILES:-3}"' in compose
    for service in runtime_services:
        assert "    logging: *runtime-logging" in _compose_service_section(
            compose, service
        )
    assert "SRBG_DOCKER_LOG_MAX_SIZE=10m" in example
    assert "SRBG_DOCKER_LOG_MAX_FILES=3" in example


def test_primary_worker_defaults_to_single_task_slot_concurrency() -> None:
    compose = (ROOT / "infra/compose/compose.yaml").read_text(encoding="utf-8")
    example = (ROOT / ".env.example").read_text(encoding="utf-8")
    worker_section = compose.split("  worker:\n", 1)[1].split("  parser:\n", 1)[0]

    assert "--concurrency=${SRBG_WORKER_CONCURRENCY:-1}" in worker_section
    assert "SRBG_WORKER_CONCURRENCY=1" in example


def test_compose_profiles_keep_core_small_and_capabilities_explicit() -> None:
    compose = (ROOT / "infra/compose/compose.yaml").read_text(encoding="utf-8")
    core_services = (
        "postgres",
        "redis",
        "clamav",
        "minio",
        "minio-init",
        "anchor-minio",
        "anchor-minio-init",
        "migrate",
        "role-init",
        "api",
        "web",
    )

    for profile, services in PROFILED_SERVICES.items():
        for service in services:
            assert f"profiles: [{profile}]" in _compose_service_section(
                compose, service
            )
    configured_profiled_services = {
        service
        for service in re.findall(r"^  ([a-z0-9][a-z0-9-]*):$", compose, re.MULTILINE)
        if "profiles:" in _compose_service_section(compose, service)
    }
    assert configured_profiled_services == {
        service
        for services in PROFILED_SERVICES.values()
        for service in services
    }
    for service in core_services:
        assert "profiles:" not in _compose_service_section(compose, service)


def test_makefile_offers_lite_runtime_without_disabling_execution_plane() -> None:
    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
    expected_lite_disabled_services = {
        service
        for profile, services in PROFILED_SERVICES.items()
        if profile != "automation"
        for service in services
    }

    assert (
        "COMPOSE_WORKFLOW_PROFILES = "
        "--profile automation --profile discovery --profile ai"
    ) in makefile
    assert (
        "COMPOSE_FULL_PROFILES = "
        "$(COMPOSE_WORKFLOW_PROFILES) --profile observability"
    ) in makefile
    assert "COMPOSE_LITE_PROFILES = --profile automation" in makefile
    assert set(
        _make_variable_words(makefile, "COMPOSE_LITE_DISABLED_SERVICES")
    ) == expected_lite_disabled_services
    assert (
        "setup:\n"
        "\t$(UV) sync --frozen --all-packages\n"
        "\t$(PNPM) install --frozen-lockfile"
    ) in makefile
    assert "\t$(COMPOSE) $(COMPOSE_FULL_PROFILES) build" in makefile
    assert "dev-lite: personal-data-ready" in makefile
    assert (
        "$(COMPOSE) $(COMPOSE_FULL_PROFILES) stop "
        "$(COMPOSE_LITE_DISABLED_SERVICES)"
        in makefile
    )
    assert (
        "$(COMPOSE) $(COMPOSE_LITE_PROFILES) up --build --detach --wait"
        in makefile
    )
    dev_lite_recipe = makefile.split("dev-lite: personal-data-ready\n", 1)[1].split(
        "\nruntime-ready:", 1
    )[0]
    assert dev_lite_recipe.count(" up ") == 1
    assert "$(COMPOSE_LITE_PROFILES) up" in dev_lite_recipe
    assert (
        "dev: personal-data-ready\n"
        "\t$(COMPOSE) $(COMPOSE_FULL_PROFILES) up --build --detach --wait"
        in makefile
    )
    assert (
        "runtime-ready: personal-data-ready\n"
        "\t$(COMPOSE) $(COMPOSE_FULL_PROFILES) up --detach --wait"
        in makefile
    )
    assert (
        "down:\n\t$(COMPOSE) $(COMPOSE_FULL_PROFILES) down --remove-orphans"
        in makefile
    )


def test_makefile_bounds_compose_parallelism_for_shared_docker_desktop() -> None:
    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")

    assert _make_variable_words(makefile, "COMPOSE") == (
        "docker",
        "compose",
        "--parallel",
        "1",
        "--project-directory",
        ".",
        "-f",
        "infra/compose/compose.yaml",
    )


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


def test_role_tasks_do_not_allocate_anonymous_postgres_data_volumes() -> None:
    compose = (ROOT / "infra/compose/compose.yaml").read_text(encoding="utf-8")

    for service in ("role-bootstrap", "role-init"):
        section = _compose_service_section(compose, service)
        assert "    tmpfs:\n      - /var/lib/postgresql/data" in section


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


def test_ci_uses_the_current_autonomous_content_integration_gate() -> None:
    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
    workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    target = makefile.split("autonomous-content-integration-test:\n", 1)[1].split(
        "\ndigital-case-test:", 1
    )[0]

    assert "safety-case-test:" not in makefile
    assert "$(COMPOSE) up --detach --wait postgres minio" in target
    assert "$(COMPOSE) run --rm --no-deps role-bootstrap" in target
    assert "verify_phase4_controlled_handoff_migration.py" in target
    assert "tests/integration/t41_autonomous_content_integration.py" in target
    assert (
        "migration-test: migration-head-check phase5-formal-migration-test "
        "autonomous-content-integration-test"
        in makefile
    )
    assert "make check-pr" in workflow
    assert "make safety-case-test" not in workflow


def test_makefile_assigns_service_defaults_before_exporting_them() -> None:
    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")

    export_groups = {
        "export WEB_PORT API_PORT": (
            "WEB_PORT ?= 3000",
            "API_PORT ?= 8000",
        ),
        "export POSTGRES_PORT MINIO_PORT ANCHOR_MINIO_PORT": (
            "POSTGRES_PORT ?= 5432",
            "MINIO_PORT ?= 9000",
            "ANCHOR_MINIO_PORT ?= 9002",
        ),
        "export POSTGRES_USER POSTGRES_PASSWORD POSTGRES_DB": (
            "POSTGRES_USER ?= srbg",
            "POSTGRES_PASSWORD ?= srbg_local_only",
            "POSTGRES_DB ?= srbg",
        ),
        "export MINIO_ROOT_USER MINIO_ROOT_PASSWORD": (
            "MINIO_ROOT_USER ?= srbg_local",
            "MINIO_ROOT_PASSWORD ?= srbg_local_storage_only",
        ),
        "export SRBG_API_DB_PASSWORD SRBG_PUBLISHER_DB_PASSWORD SRBG_PROJECTION_DB_PASSWORD": (
            "SRBG_API_DB_PASSWORD ?= srbg_api_local_only",
            "SRBG_PUBLISHER_DB_PASSWORD ?= srbg_publisher_local_only",
            "SRBG_PROJECTION_DB_PASSWORD ?= srbg_projection_local_only",
        ),
        "export SRBG_S3_BUCKET SRBG_S3_REGION SRBG_EXTERNAL_IO_TIMEOUT_SECONDS": (
            "SRBG_S3_BUCKET ?= srbg-raw",
            "SRBG_S3_REGION ?= us-east-1",
            "SRBG_EXTERNAL_IO_TIMEOUT_SECONDS ?= 2",
        ),
    }
    for export, assignments in export_groups.items():
        export_index = makefile.index(export)
        assert all(makefile.index(assignment) < export_index for assignment in assignments)


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


def test_ci_pins_actions_and_delegates_to_the_risk_based_entry() -> None:
    workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")

    assert "actions/checkout@93cb6efe18208431cddfb8368fd83d5badbf9bfd" in workflow
    assert "actions/setup-python@ece7cb06caefa5fff74198d8649806c4678c61a1" in workflow
    assert "actions/setup-node@48b55a011bda9f5d6aeb4c2d9c7362e8dae4041e" in workflow
    assert "PLAYWRIGHT_BROWSERS_PATH: ${{ github.workspace }}/.cache/ms-playwright" in workflow
    assert "make check-pr" in workflow
    assert "scripts/ci/risk_matrix.py classify" in workflow
    assert workflow.count("uv sync --frozen --all-packages") == 1
    assert workflow.count("pnpm install --frozen-lockfile") == 1
    assert "make security-check" not in workflow


def test_round04_fixed_fixtures_remain_in_the_offline_replay_gate() -> None:
    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")

    assert "apps/api/tests/test_round04_official_fixtures.py" in makefile


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
    compose_words = _make_variable_words(makefile, "COMPOSE")

    assert compose_words[-4:] == (
        "--project-directory",
        ".",
        "-f",
        "infra/compose/compose.yaml",
    )
    assert "-include .env" in makefile
    assert "export WEB_PORT API_PORT" in makefile
    assert COMPOSE[:5] == ["docker", "compose", "--project-directory", ".", "-f"]
    assert compose.count("context: .\n") == 11
    assert "  parser:" in compose
    assert "  publisher:" in compose
    assert "context: ../.." not in compose


def test_phase4_live_runner_uses_project_scoped_ephemeral_volumes() -> None:
    runner = (ROOT / "scripts/run_phase4_real_event_acceptance.py").read_text(
        encoding="utf-8"
    )
    override = (ROOT / "infra/compose/compose.phase4.yaml").read_text(
        encoding="utf-8"
    )

    assert 'str(ROOT / "infra" / "compose" / "compose.phase4.yaml")' in runner
    for service, target in (
        ("phase4-postgres", "/var/lib/postgresql/data"),
        ("phase4-postgres-wal", "/wal-archive"),
        ("phase4-redis", "/data"),
        ("phase4-minio", "/data"),
    ):
        assert f"- {service}:{target}" in override
        assert f"  {service}:" in override
    assert "${SRBG_DATA_ROOT" not in override
    assert '"down", "--volumes", "--remove-orphans"' in runner


def test_phase4_live_runner_isolates_the_minio_console_port_from_dotenv() -> None:
    runner = (ROOT / "scripts/run_phase4_real_event_acceptance.py").read_text(
        encoding="utf-8"
    )

    assert '"MINIO_CONSOLE_PORT": _free_port()' in runner


def test_phase4_live_evidence_is_unique_per_run_and_never_overwritten() -> None:
    runner = (ROOT / "scripts/run_phase4_real_event_acceptance.py").read_text(
        encoding="utf-8"
    )
    live_test = (
        ROOT / "tests/live/test_phase4_real_event_acceptance.py"
    ).read_text(encoding="utf-8")

    assert 'f"{release_sha}-{token}.json"' in runner
    assert 'f"{release_sha}.json"' not in runner
    assert 'path.open("x", encoding="utf-8")' in live_test


def test_phase4_live_runner_bootstraps_roles_before_fresh_database_migration() -> None:
    runner = (ROOT / "scripts/run_phase4_real_event_acceptance.py").read_text(
        encoding="utf-8"
    )

    infrastructure_ready = (
        '[*compose, "up", "--detach", "--wait", "postgres", "redis", "minio"]'
    )
    role_bootstrap = '[*compose, "run", "--rm", "--no-deps", "role-bootstrap"]'
    migration_verifier = '"verify_phase4_controlled_handoff_migration.py"'

    assert role_bootstrap in runner
    assert runner.index(infrastructure_ready) < runner.index(role_bootstrap)
    assert runner.index(role_bootstrap) < runner.index(migration_verifier)


def test_phase4_live_stream_keeps_host_and_path_authority_in_their_schema_fields() -> None:
    live_test = (
        ROOT / "tests/live/test_phase4_real_event_acceptance.py"
    ).read_text(encoding="utf-8")

    assert '"boundary": SOURCE_HOST' in live_test
    assert '"path": SOURCE_PATH_PREFIX' in live_test
    assert '"boundary": f"{SOURCE_HOST}{SOURCE_PATH_PREFIX}"' not in live_test


def test_phase4_live_replacement_source_and_document_are_fixed_before_network_io() -> None:
    runner = (ROOT / "scripts/run_phase4_real_event_acceptance.py").read_text(
        encoding="utf-8"
    )
    live_test = (
        ROOT / "tests/live/test_phase4_real_event_acceptance.py"
    ).read_text(encoding="utf-8")

    assert 'SOURCE_STREAM_ID = "019fbbb0-b1f6-7e3f-97c0-20e4c16616c5"' in runner
    assert "source_stream_key=CJHT_CURRENT_ISSUE" in runner
    assert '"SRBG_PHASE4_SOURCE_STREAM_ID": SOURCE_STREAM_ID' in runner
    assert 'fixed_stream_id = UUID(os.environ["SRBG_PHASE4_SOURCE_STREAM_ID"])' in live_test
    assert "if stream_id != fixed_stream_id:" in live_test
    assert 'raise RuntimeError("SOURCE_STREAM_ID_NOT_FIXED")' in live_test
    assert 'COLLECTION_URL = "https://zgglxb.chd.edu.cn/CN/current"' in live_test
    assert (
        'FIXED_DOCUMENT_URL = "https://zgglxb.chd.edu.cn/CN/'
        '10.19721/j.cnki.1001-7372.2026.07.016"' in live_test
    )
    assert 'raise RuntimeError("FIXED_DOCUMENT_NOT_DISCOVERED")' in live_test
    assert '"item_selector": "#art5465"' in live_test
    assert '"link_selector": "a"' in live_test
    assert '"title_selector": "a"' in live_test
    assert 'SOURCE_PATH_PREFIX = "/CN/"' in live_test
    assert "2026-08-01-phase-4-high-signal-replacement-source.md" in live_test


def test_phase4_live_stop_closes_stream_authority_before_drain() -> None:
    live_test = (
        ROOT / "tests/live/test_phase4_real_event_acceptance.py"
    ).read_text(encoding="utf-8")
    stop = live_test.split("async def _stop_and_drain(", 1)[1].split(
        "async def test_one_controlled_source_display", 1
    )[0]

    assert "record_owner_intent(" in stop
    assert "desired_enabled=False" in stop
    assert 'request_id=f"phase4-stop-{controlled_run_id or stream_id}"' in stop
    assert "patch_personal_source" not in stop
    assert "UPDATE fetch_schedule SET status='PAUSED'" in stop
    assert "UPDATE source SET runtime_state='STOPPED',enabled=false" in stop
    assert "cancel_ineligible(" in stop
    assert "fetch_run_id" in stop


def test_browser_gates_reuse_the_ready_runtime_without_forced_rebuilds() -> None:
    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")

    assert (
        "runtime-ready: personal-data-ready\n"
        "\t$(COMPOSE) $(COMPOSE_FULL_PROFILES) up --detach --wait"
    ) in makefile
    assert (
        "playwright-browser-ready:\n"
        "\t$(PNPM) --filter @srbg/web exec playwright install chromium"
    ) in makefile
    assert "web-e2e: runtime-ready playwright-browser-ready" in makefile
    assert "web-a11y: runtime-ready playwright-browser-ready" in makefile


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


def test_phase4_live_transport_accounts_requests_in_the_authoritative_schedule() -> None:
    live = (ROOT / "tests/live/test_phase4_real_event_acceptance.py").read_text(
        encoding="utf-8"
    )

    assert "before_request=lambda url: gateway.reserve_request(binding, url=url)" in live
    assert "gateway.record_response_bytes(" in live
    assert 'report["fetch_failure_reason"]' in live


def test_phase4_live_document_lookup_uses_personal_stream_authority() -> None:
    live = (ROOT / "tests/live/test_phase4_real_event_acceptance.py").read_text(
        encoding="utf-8"
    )

    assert "JOIN document_version version" in live
    assert "JOIN source_content_outbox outbox" in live
    assert "JOIN fetch_record record" not in live


def test_phase4_live_uses_sources_projection_without_content_publication() -> None:
    runner = (ROOT / "scripts/run_phase4_real_event_acceptance.py").read_text(
        encoding="utf-8"
    )
    live = (ROOT / "tests/live/test_phase4_real_event_acceptance.py").read_text(
        encoding="utf-8"
    )

    assert "SourceRegistryService(" in live
    assert "await source_registry.list_personal_sources()" in live
    assert "await source_registry.get_personal_source_activity(" in live
    assert 'report["sources_projection"]' in live
    assert "_generate_attempt" not in live
    assert "PublicationService" not in live
    assert "PostgresV2IntelligenceService" not in live
    assert "SRBG_AI_API_KEY" not in runner
    assert "model_calls=0 ai_cost_microusd=0" in runner


def test_phase4_live_does_not_create_an_ai_pipeline_or_source_handoff() -> None:
    live = (ROOT / "tests/live/test_phase4_real_event_acceptance.py").read_text(
        encoding="utf-8"
    )

    assert "SourceContentOutboxExecutor" not in live
    assert "ai_pipeline_run" not in live
    assert "reserve_controlled_ai_budget" not in live


def test_phase4_live_records_zero_model_calls_and_cost() -> None:
    live = (ROOT / "tests/live/test_phase4_real_event_acceptance.py").read_text(
        encoding="utf-8"
    )

    assert '"model_calls": 0' in live
    assert '"ai_cost_microusd": 0' in live
    assert '"ai_required": False' in live
    assert "pipeline_status" not in live


def test_phase4_live_evidence_excludes_source_body_and_model_output() -> None:
    live = (ROOT / "tests/live/test_phase4_real_event_acceptance.py").read_text(encoding="utf-8")

    assert "response.text" not in live
    assert "response.content" not in live
    assert "model_candidate" not in live
    assert "source_excerpt" not in live


def test_web_image_keeps_versioned_esbuild_binaries_isolated_and_cached() -> None:
    workspace = (ROOT / "pnpm-workspace.yaml").read_text(encoding="utf-8")
    dockerfile = (ROOT / "infra/compose/Dockerfile.web").read_text(encoding="utf-8")

    assert "hoistPattern:\n  - '*'\n  - '!@esbuild/*'" in workspace
    assert "target=/workspace/.pnpm-store" in dockerfile
    assert "--store-dir /workspace/.pnpm-store" in dockerfile


def test_web_image_install_uses_the_reviewed_frozen_lockfile() -> None:
    dockerfile = (ROOT / "infra/compose/Dockerfile.web").read_text(encoding="utf-8")

    assert "pnpm install --frozen-lockfile --trust-lockfile" in dockerfile
    assert "pnpm install --offline" not in dockerfile


def test_security_scan_uses_only_git_delivery_files() -> None:
    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")

    assert "$(UV) run python scripts/prepare_security_scan.py" in makefile
    assert '-v "$(CURDIR)/.cache/trivy-input:/workspace:ro"' in makefile
    assert "--scanners secret,misconfig --parallel 1 --exit-code 1" in makefile
    assert "--severity HIGH,CRITICAL" in makefile
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
