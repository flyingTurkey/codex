from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path

import pytest

from scripts.run_isolated_integration import (
    CLEANUP_FAILURE_EXIT_CODE,
    IntegrationConfig,
    TemporaryResources,
    _environment_port,
    run_isolated_integration,
)


@dataclass
class RecordingBackend:
    calls: list[tuple[str, str]] = field(default_factory=list)
    failures: dict[str, Exception] = field(default_factory=dict)

    def create_database(self, name: str) -> None:
        self._record("create_database", name)

    def create_private_bucket(self, name: str) -> None:
        self._record("create_private_bucket", name)

    def create_login_roles(self, resources: TemporaryResources) -> None:
        self._record("create_login_roles", resources.runtime_role)

    def empty_and_delete_bucket(self, name: str) -> None:
        self._record("empty_and_delete_bucket", name)

    def drop_database(self, name: str) -> None:
        self._record("drop_database", name)

    def drop_login_roles(self, resources: TemporaryResources) -> None:
        self._record("drop_login_roles", resources.runtime_role)

    def _record(self, action: str, name: str) -> None:
        self.calls.append((action, name))
        failure = self.failures.get(action)
        if failure is not None:
            raise failure


@dataclass
class RecordingProcessRunner:
    exit_codes: list[int | BaseException]
    calls: list[tuple[tuple[str, ...], dict[str, str]]] = field(default_factory=list)

    def __call__(self, command: Sequence[str], environment: Mapping[str, str]) -> int:
        self.calls.append((tuple(command), dict(environment)))
        outcome = self.exit_codes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


@pytest.fixture
def config() -> IntegrationConfig:
    return IntegrationConfig(
        python_executable="python",
        postgres_host="127.0.0.1",
        postgres_port=15432,
        postgres_admin_user="admin-user",
        postgres_admin_password="admin-secret",  # noqa: S106 - synthetic test credential
        postgres_admin_database="srbg",
        s3_endpoint_url="http://127.0.0.1:19000",
        s3_access_key="access-secret",
        s3_secret_key="storage-secret",  # noqa: S106 - synthetic test credential
        s3_region="us-east-1",
        shared_s3_bucket="srbg-raw",
    )


def test_empty_optional_port_uses_safe_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANCHOR_MINIO_PORT", "")

    assert _environment_port("ANCHOR_MINIO_PORT", 9002) == 9002


def test_suite_uses_only_unique_temporary_database_and_bucket(
    config: IntegrationConfig,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    shared_credentials = (
        "POSTGRES_PASSWORD",
        "PGPASSWORD",
        "MINIO_ROOT_USER",
        "MINIO_ROOT_PASSWORD",
        "SRBG_API_DB_PASSWORD",
        "SRBG_WORKER_DB_PASSWORD",
        "SRBG_PUBLISHER_DB_PASSWORD",
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
        "AWS_SESSION_TOKEN",
    )
    for name in shared_credentials:
        monkeypatch.setenv(name, "shared-bootstrap-secret")
    backend = RecordingBackend()
    processes = RecordingProcessRunner([0, 0])
    passwords = iter(("runtime-secret", "publication-secret", "worker-secret", "projection-secret"))

    result = run_isolated_integration(
        ("apps/api/tests/test_safety_regulation_integration.py", "-q"),
        config=config,
        backend=backend,
        process_runner=processes,
        token_factory=lambda: "0123456789abcdef0123456789abcdef",
        password_factory=lambda: next(passwords),
    )

    assert result == 0
    assert backend.calls == [
        ("create_database", "srbg_it_0123456789abcdef01234567"),
        ("create_private_bucket", "srbg-it-0123456789abcdef01234567"),
        ("create_login_roles", "srbg_it_api_0123456789abcdef01234567"),
        ("empty_and_delete_bucket", "srbg-it-0123456789abcdef01234567"),
        ("drop_database", "srbg_it_0123456789abcdef01234567"),
        ("drop_login_roles", "srbg_it_api_0123456789abcdef01234567"),
    ]
    assert len(processes.calls) == 2
    migration_command, migration_environment = processes.calls[0]
    suite_command, suite_environment = processes.calls[1]
    assert migration_command == (
        "python",
        "scripts/verify_round11_migration.py",
    )
    assert migration_environment["SRBG_DATABASE_URL"].endswith(
        "/srbg_it_0123456789abcdef01234567"
    )
    assert suite_command == (
        "python",
        "-m",
        "pytest",
        "apps/api/tests/test_safety_regulation_integration.py",
        "-q",
    )
    assert suite_environment["SRBG_RUN_SAFETY_INTEGRATION"] == "1"
    assert suite_environment["SRBG_S3_BUCKET"] == "srbg-it-0123456789abcdef01234567"
    assert suite_environment["SRBG_DATABASE_URL"].endswith(
        "/srbg_it_0123456789abcdef01234567"
    )
    assert suite_environment["SRBG_PUBLICATION_DATABASE_URL"].endswith(
        "/srbg_it_0123456789abcdef01234567"
    )
    assert "srbg_it_api_0123456789abcdef01234567" in suite_environment[
        "SRBG_DATABASE_URL"
    ]
    assert "srbg_it_pub_0123456789abcdef01234567" in suite_environment[
        "SRBG_PUBLICATION_DATABASE_URL"
    ]
    assert suite_environment["SRBG_S3_BUCKET"] != config.shared_s3_bucket
    assert all(name not in suite_environment for name in shared_credentials)


def test_default_runner_migrates_the_disposable_database_to_current_head(
    config: IntegrationConfig,
) -> None:
    backend = RecordingBackend()
    processes = RecordingProcessRunner([0, 0])

    result = run_isolated_integration(
        ("test_current_runtime.py",),
        config=config,
        backend=backend,
        process_runner=processes,
        token_factory=lambda: "5" * 32,
    )

    assert result == 0
    assert processes.calls[0][0] == (
        "python",
        "scripts/verify_round11_migration.py",
    )


def test_suite_failure_keeps_exit_code_and_still_cleans_every_resource(
    config: IntegrationConfig,
) -> None:
    backend = RecordingBackend()
    processes = RecordingProcessRunner([0, 23])
    passwords = iter(("runtime-secret", "publication-secret", "worker-secret", "projection-secret"))

    result = run_isolated_integration(
        ("test_failure.py",),
        config=config,
        backend=backend,
        process_runner=processes,
        token_factory=lambda: "a" * 32,
        password_factory=lambda: next(passwords),
    )

    assert result == 23
    assert [action for action, _ in backend.calls] == [
        "create_database",
        "create_private_bucket",
        "create_login_roles",
        "empty_and_delete_bucket",
        "drop_database",
        "drop_login_roles",
    ]


def test_suite_failure_keeps_exit_code_when_cleanup_also_fails(
    config: IntegrationConfig,
) -> None:
    backend = RecordingBackend(
        failures={"drop_database": RuntimeError("admin-secret must stay redacted")}
    )
    processes = RecordingProcessRunner([0, 23])

    result = run_isolated_integration(
        ("test_failure.py",),
        config=config,
        backend=backend,
        process_runner=processes,
        token_factory=lambda: "e" * 32,
    )

    assert result == 23
    assert [action for action, _ in backend.calls][-3:] == [
        "empty_and_delete_bucket",
        "drop_database",
        "drop_login_roles",
    ]


@pytest.mark.parametrize(
    "process_error",
    [RuntimeError("subprocess failed"), KeyboardInterrupt()],
    ids=("exception", "keyboard-interrupt"),
)
def test_process_exception_still_cleans_database_bucket_and_roles(
    config: IntegrationConfig,
    process_error: BaseException,
) -> None:
    backend = RecordingBackend()
    processes = RecordingProcessRunner([0, process_error])

    with pytest.raises(type(process_error)):
        run_isolated_integration(
            ("test_interrupted.py",),
            config=config,
            backend=backend,
            process_runner=processes,
            token_factory=lambda: "f" * 32,
        )

    assert [action for action, _ in backend.calls][-3:] == [
        "empty_and_delete_bucket",
        "drop_database",
        "drop_login_roles",
    ]


def test_cleanup_failure_fails_a_green_suite_without_logging_credentials(
    config: IntegrationConfig,
    capsys: pytest.CaptureFixture[str],
) -> None:
    backend = RecordingBackend(
        failures={
            "empty_and_delete_bucket": RuntimeError(
                "cleanup rejected storage-secret publication-secret"
            )
        }
    )
    processes = RecordingProcessRunner([0, 0])
    passwords = iter(("runtime-secret", "publication-secret", "worker-secret", "projection-secret"))

    result = run_isolated_integration(
        ("test_success.py",),
        config=config,
        backend=backend,
        process_runner=processes,
        token_factory=lambda: "b" * 32,
        password_factory=lambda: next(passwords),
    )

    captured = capsys.readouterr()
    assert result == CLEANUP_FAILURE_EXIT_CODE
    assert [action for action, _ in backend.calls][-3:] == [
        "empty_and_delete_bucket",
        "drop_database",
        "drop_login_roles",
    ]
    assert "cleanup failed" in captured.err.lower()
    assert "storage-secret" not in captured.err
    assert "publication-secret" not in captured.err


def test_migration_failure_keeps_exit_code_and_skips_pytest(
    config: IntegrationConfig,
) -> None:
    backend = RecordingBackend()
    processes = RecordingProcessRunner([17])

    result = run_isolated_integration(
        ("must_not_run.py",),
        config=config,
        backend=backend,
        process_runner=processes,
        token_factory=lambda: "c" * 32,
    )

    assert result == 17
    assert len(processes.calls) == 1
    assert [action for action, _ in backend.calls][-2:] == [
        "empty_and_delete_bucket",
        "drop_database",
    ]


def test_bucket_collision_does_not_delete_a_bucket_the_run_did_not_confirm_owning(
    config: IntegrationConfig,
) -> None:
    backend = RecordingBackend(
        failures={"create_private_bucket": RuntimeError("access-secret must stay private")}
    )

    with pytest.raises(RuntimeError, match="access-secret must stay private"):
        run_isolated_integration(
            ("must_not_run.py",),
            config=config,
            backend=backend,
            process_runner=RecordingProcessRunner([]),
            token_factory=lambda: "d" * 32,
        )

    assert backend.calls == [
        ("create_database", "srbg_it_dddddddddddddddddddddddd"),
        ("create_private_bucket", "srbg-it-dddddddddddddddddddddddd"),
        ("drop_database", "srbg_it_dddddddddddddddddddddddd"),
    ]


def test_database_collision_does_not_drop_a_database_the_run_did_not_confirm_owning(
    config: IntegrationConfig,
) -> None:
    backend = RecordingBackend(
        failures={"create_database": RuntimeError("temporary database already exists")}
    )

    with pytest.raises(RuntimeError, match="already exists"):
        run_isolated_integration(
            ("must_not_run.py",),
            config=config,
            backend=backend,
            process_runner=RecordingProcessRunner([]),
            token_factory=lambda: "3" * 32,
        )

    assert backend.calls == [("create_database", "srbg_it_333333333333333333333333")]


def test_role_collision_does_not_drop_roles_the_run_did_not_confirm_owning(
    config: IntegrationConfig,
) -> None:
    backend = RecordingBackend(
        failures={"create_login_roles": RuntimeError("temporary login role already exists")}
    )

    with pytest.raises(RuntimeError, match="already exists"):
        run_isolated_integration(
            ("must_not_run.py",),
            config=config,
            backend=backend,
            process_runner=RecordingProcessRunner([0]),
            token_factory=lambda: "4" * 32,
        )

    assert [action for action, _ in backend.calls] == [
        "create_database",
        "create_private_bucket",
        "create_login_roles",
        "empty_and_delete_bucket",
        "drop_database",
    ]


def test_temporary_resource_names_never_target_shared_resources() -> None:
    first = TemporaryResources.generate(lambda: "1" * 32)
    second = TemporaryResources.generate(lambda: "2" * 32)

    assert first != second
    assert first.database.startswith("srbg_it_")
    assert first.bucket.startswith("srbg-it-")
    assert first.database != "srbg"
    assert first.bucket != "srbg-raw"
    assert first.runtime_role.startswith("srbg_it_api_")
    assert first.publication_role.startswith("srbg_it_pub_")
    assert first.worker_role.startswith("srbg_it_worker_")
    assert first.runtime_role != "srbg_api_login"
    assert first.publication_role != "srbg_publisher_login"
    assert first.worker_role != "srbg_worker_login"


@pytest.mark.parametrize(
    ("field_name", "remote_value"),
    [
        ("postgres_host", "database.internal.example"),
        ("s3_endpoint_url", "https://objects.internal.example"),
    ],
)
def test_remote_services_require_explicit_dangerous_opt_in(
    config: IntegrationConfig,
    field_name: str,
    remote_value: str,
) -> None:
    with pytest.raises(ValueError, match="SRBG_ALLOW_REMOTE_INTEGRATION"):
        replace(config, **{field_name: remote_value})

    opted_in = replace(
        config,
        **{field_name: remote_value, "allow_remote_integration": True},
    )
    assert getattr(opted_in, field_name) == remote_value


def test_configuration_repr_never_contains_credentials(config: IntegrationConfig) -> None:
    rendered = repr(config)

    assert "admin-secret" not in rendered
    assert "access-secret" not in rendered
    assert "storage-secret" not in rendered


def test_remote_opt_in_environment_requires_exact_value_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("POSTGRES_HOST", "database.internal.example")
    monkeypatch.delenv("SRBG_ALLOW_REMOTE_INTEGRATION", raising=False)

    with pytest.raises(ValueError, match="SRBG_ALLOW_REMOTE_INTEGRATION"):
        IntegrationConfig.from_environment()

    monkeypatch.setenv("SRBG_ALLOW_REMOTE_INTEGRATION", "1")
    assert IntegrationConfig.from_environment().allow_remote_integration is True


def test_make_integration_targets_delegate_pytest_to_isolated_runner() -> None:
    makefile = Path("Makefile").read_text(encoding="utf-8")
    safety_target = makefile.split("safety-regulation-test:", 1)[1].split(
        "pdf-ocr-test:", 1
    )[0]
    pdf_target = makefile.split("pdf-ocr-test:", 1)[1].split("web-e2e:", 1)[0]

    for target in (safety_target, pdf_target):
        assert "scripts/run_isolated_integration.py" in target
        assert "$(SAFETY_TEST_ENV)" not in target
        assert "python -m pytest" not in target
        assert "run --rm migrate" not in target
        assert "role-init" not in target
        assert "minio-init" not in target
