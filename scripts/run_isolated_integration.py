"""Run integration pytest suites against disposable PostgreSQL and MinIO resources."""

from __future__ import annotations

import argparse
import asyncio
import ipaddress
import os
import re
import secrets
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol
from urllib.parse import urlsplit
from uuid import uuid4

import aioboto3
import asyncpg
from botocore.config import Config as BotoConfig
from botocore.exceptions import ClientError
from sqlalchemy.engine import URL

ROOT = Path(__file__).resolve().parents[1]
CLEANUP_FAILURE_EXIT_CODE = 1
SETUP_FAILURE_EXIT_CODE = 1
_DATABASE_NAME = re.compile(r"srbg_it_[0-9a-f]{24}\Z")
_BUCKET_NAME = re.compile(r"srbg-it-[0-9a-f]{24}\Z")
_ROLE_NAME = re.compile(r"srbg_it_(?:api|pub|worker|reader)_[0-9a-f]{24}\Z")
_BOOTSTRAP_CREDENTIAL_KEYS = frozenset(
    {
        "POSTGRES_PASSWORD",
        "PGPASSWORD",
        "PGPASSFILE",
        "PGSERVICE",
        "PGSERVICEFILE",
        "MINIO_ROOT_USER",
        "MINIO_ROOT_PASSWORD",
        "SRBG_API_DB_PASSWORD",
        "SRBG_WORKER_DB_PASSWORD",
        "SRBG_PUBLISHER_DB_PASSWORD",
        "ANCHOR_MINIO_ROOT_USER",
        "ANCHOR_MINIO_ROOT_PASSWORD",
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
        "AWS_SESSION_TOKEN",
        "AWS_PROFILE",
        "AWS_DEFAULT_PROFILE",
        "DATABASE_URL",
        "SRBG_ADMIN_DATABASE_URL",
        "SRBG_WORKER_DATABASE_URL",
        "SRBG_TEST_ADMIN_DATABASE_URL",
    }
)


@dataclass(frozen=True)
class IntegrationConfig:
    """Local service coordinates and credentials, loaded without logging their values."""

    python_executable: str
    postgres_host: str
    postgres_port: int
    postgres_admin_user: str
    postgres_admin_password: str = field(repr=False)
    postgres_admin_database: str
    s3_endpoint_url: str
    s3_access_key: str = field(repr=False)
    s3_secret_key: str = field(repr=False)
    s3_region: str
    shared_s3_bucket: str
    external_io_timeout_seconds: float = 5.0
    allow_remote_integration: bool = False

    def __post_init__(self) -> None:
        endpoint = urlsplit(self.s3_endpoint_url)
        if endpoint.scheme not in {"http", "https"} or endpoint.hostname is None:
            raise ValueError("s3_endpoint_url must be an absolute HTTP(S) URL")
        if self.allow_remote_integration:
            return
        if not _is_loopback_host(self.postgres_host) or not _is_loopback_host(endpoint.hostname):
            raise ValueError(
                "isolated integration services must use loopback addresses; "
                "set SRBG_ALLOW_REMOTE_INTEGRATION=1 only for an explicitly approved remote stack"
            )

    @classmethod
    def from_environment(cls) -> IntegrationConfig:
        postgres_port = _environment_port("POSTGRES_PORT", 5432)
        minio_port = _environment_port("MINIO_PORT", 9000)
        return cls(
            python_executable=sys.executable,
            postgres_host=os.environ.get("POSTGRES_HOST", "127.0.0.1"),
            postgres_port=postgres_port,
            postgres_admin_user=os.environ.get("POSTGRES_USER", "srbg"),
            postgres_admin_password=os.environ.get("POSTGRES_PASSWORD", "srbg_local_only"),
            postgres_admin_database=os.environ.get("POSTGRES_DB", "srbg"),
            s3_endpoint_url=os.environ.get(
                "SRBG_ISOLATED_S3_ENDPOINT_URL", f"http://127.0.0.1:{minio_port}"
            ),
            s3_access_key=os.environ.get("MINIO_ROOT_USER", "srbg_local"),
            s3_secret_key=os.environ.get("MINIO_ROOT_PASSWORD", "srbg_local_storage_only"),
            s3_region=os.environ.get("SRBG_S3_REGION", "us-east-1"),
            shared_s3_bucket=os.environ.get("SRBG_S3_BUCKET", "srbg-raw"),
            external_io_timeout_seconds=_environment_timeout(
                "SRBG_EXTERNAL_IO_TIMEOUT_SECONDS", 5.0
            ),
            allow_remote_integration=_environment_flag("SRBG_ALLOW_REMOTE_INTEGRATION"),
        )

    def database_url(self, user: str, password: str, database: str) -> str:
        return URL.create(
            "postgresql+asyncpg",
            username=user,
            password=password,
            host=self.postgres_host,
            port=self.postgres_port,
            database=database,
        ).render_as_string(hide_password=False)


@dataclass(frozen=True)
class TemporaryResources:
    database: str
    bucket: str
    runtime_role: str
    runtime_password: str = field(repr=False)
    publication_role: str
    publication_password: str = field(repr=False)
    worker_role: str
    worker_password: str = field(repr=False)
    projection_reader_role: str
    projection_reader_password: str = field(repr=False)

    @classmethod
    def generate(
        cls,
        token_factory: Callable[[], str] | None = None,
        password_factory: Callable[[], str] | None = None,
    ) -> TemporaryResources:
        factory = token_factory or (lambda: uuid4().hex)
        new_password = password_factory or (lambda: secrets.token_urlsafe(32))
        token = factory().lower().replace("-", "")
        if re.fullmatch(r"[0-9a-f]{32}", token) is None:
            raise ValueError("temporary resource token must contain 32 hexadecimal characters")
        suffix = token[:24]
        runtime_password = new_password()
        publication_password = new_password()
        worker_password = new_password()
        projection_reader_password = new_password()
        if not all(
            (
                runtime_password,
                publication_password,
                worker_password,
                projection_reader_password,
            )
        ):
            raise ValueError("temporary role passwords must not be empty")
        return cls(
            database=f"srbg_it_{suffix}",
            bucket=f"srbg-it-{suffix}",
            runtime_role=f"srbg_it_api_{suffix}",
            runtime_password=runtime_password,
            publication_role=f"srbg_it_pub_{suffix}",
            publication_password=publication_password,
            worker_role=f"srbg_it_worker_{suffix}",
            worker_password=worker_password,
            projection_reader_role=f"srbg_it_reader_{suffix}",
            projection_reader_password=projection_reader_password,
        )


class ResourceBackend(Protocol):
    def create_database(self, name: str) -> None: ...

    def create_private_bucket(self, name: str) -> None: ...

    def create_login_roles(self, resources: TemporaryResources) -> None: ...

    def empty_and_delete_bucket(self, name: str) -> None: ...

    def drop_database(self, name: str) -> None: ...

    def drop_login_roles(self, resources: TemporaryResources) -> None: ...


class ProcessRunner(Protocol):
    def __call__(self, command: Sequence[str], environment: Mapping[str, str]) -> int: ...


class LocalResourceBackend:
    """Create and destroy only names that match the disposable-resource namespace."""

    def __init__(self, config: IntegrationConfig) -> None:
        self._config = config

    def create_database(self, name: str) -> None:
        self._require_disposable_database(name)
        asyncio.run(self._create_database(name))

    def create_private_bucket(self, name: str) -> None:
        self._require_disposable_bucket(name)
        asyncio.run(self._create_private_bucket(name))

    def create_login_roles(self, resources: TemporaryResources) -> None:
        self._require_disposable_role(resources.runtime_role)
        self._require_disposable_role(resources.publication_role)
        self._require_disposable_role(resources.worker_role)
        self._require_disposable_role(resources.projection_reader_role)
        asyncio.run(self._create_login_roles(resources))

    def empty_and_delete_bucket(self, name: str) -> None:
        self._require_disposable_bucket(name)
        asyncio.run(self._empty_and_delete_bucket(name))

    def drop_database(self, name: str) -> None:
        self._require_disposable_database(name)
        asyncio.run(self._drop_database(name))

    def drop_login_roles(self, resources: TemporaryResources) -> None:
        self._require_disposable_role(resources.runtime_role)
        self._require_disposable_role(resources.publication_role)
        self._require_disposable_role(resources.worker_role)
        self._require_disposable_role(resources.projection_reader_role)
        asyncio.run(self._drop_login_roles(resources))

    def _require_disposable_database(self, name: str) -> None:
        if name == self._config.postgres_admin_database or _DATABASE_NAME.fullmatch(name) is None:
            raise ValueError("refusing to operate on a non-temporary database")

    def _require_disposable_bucket(self, name: str) -> None:
        if name == self._config.shared_s3_bucket or _BUCKET_NAME.fullmatch(name) is None:
            raise ValueError("refusing to operate on a non-temporary bucket")

    @staticmethod
    def _require_disposable_role(name: str) -> None:
        if _ROLE_NAME.fullmatch(name) is None:
            raise ValueError("refusing to operate on a non-temporary database role")

    async def _admin_connection(self) -> asyncpg.Connection:
        return await asyncpg.connect(
            host=self._config.postgres_host,
            port=self._config.postgres_port,
            user=self._config.postgres_admin_user,
            password=self._config.postgres_admin_password,
            database=self._config.postgres_admin_database,
            timeout=self._config.external_io_timeout_seconds,
            command_timeout=self._config.external_io_timeout_seconds,
        )

    async def _create_database(self, name: str) -> None:
        connection = await self._admin_connection()
        try:
            await connection.execute(f'CREATE DATABASE "{name}"')
        finally:
            await connection.close()

    async def _drop_database(self, name: str) -> None:
        connection = await self._admin_connection()
        try:
            await connection.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
        finally:
            await connection.close()

    async def _create_login_roles(self, resources: TemporaryResources) -> None:
        connection = await self._admin_connection()
        try:
            async with connection.transaction():
                runtime_create = await connection.fetchval(
                    "SELECT format('CREATE ROLE %I LOGIN PASSWORD %L', $1::text, $2::text)",
                    resources.runtime_role,
                    resources.runtime_password,
                )
                publication_create = await connection.fetchval(
                    "SELECT format('CREATE ROLE %I LOGIN PASSWORD %L', $1::text, $2::text)",
                    resources.publication_role,
                    resources.publication_password,
                )
                worker_create = await connection.fetchval(
                    "SELECT format('CREATE ROLE %I LOGIN PASSWORD %L', $1::text, $2::text)",
                    resources.worker_role,
                    resources.worker_password,
                )
                projection_reader_create = await connection.fetchval(
                    "SELECT format('CREATE ROLE %I LOGIN PASSWORD %L', $1::text, $2::text)",
                    resources.projection_reader_role,
                    resources.projection_reader_password,
                )
                runtime_grant = await connection.fetchval(
                    "SELECT format('GRANT srbg_api_role TO %I', $1::text)",
                    resources.runtime_role,
                )
                publication_grant = await connection.fetchval(
                    "SELECT format('GRANT srbg_publication_writer TO %I', $1::text)",
                    resources.publication_role,
                )
                worker_grant = await connection.fetchval(
                    "SELECT format('GRANT srbg_worker_role TO %I', $1::text)",
                    resources.worker_role,
                )
                projection_reader_grant = await connection.fetchval(
                    "SELECT format('GRANT srbg_projection_reader TO %I', $1::text)",
                    resources.projection_reader_role,
                )
                for statement in (
                    runtime_create,
                    publication_create,
                    worker_create,
                    projection_reader_create,
                    runtime_grant,
                    publication_grant,
                    worker_grant,
                    projection_reader_grant,
                ):
                    await connection.execute(statement)
        finally:
            await connection.close()

    async def _drop_login_roles(self, resources: TemporaryResources) -> None:
        connection = await self._admin_connection()
        try:
            statement = await connection.fetchval(
                "SELECT format('DROP ROLE IF EXISTS %I, %I, %I, %I', "
                "$1::text, $2::text, $3::text, $4::text)",
                resources.runtime_role,
                resources.publication_role,
                resources.worker_role,
                resources.projection_reader_role,
            )
            await connection.execute(statement)
        finally:
            await connection.close()

    def _s3_client(self) -> object:
        timeout = self._config.external_io_timeout_seconds
        return aioboto3.Session().client(
            "s3",
            endpoint_url=self._config.s3_endpoint_url,
            aws_access_key_id=self._config.s3_access_key,
            aws_secret_access_key=self._config.s3_secret_key,
            region_name=self._config.s3_region,
            config=BotoConfig(
                connect_timeout=timeout,
                read_timeout=timeout,
                retries={"max_attempts": 2, "mode": "standard"},
            ),
        )

    async def _create_private_bucket(self, name: str) -> None:
        async with self._s3_client() as client:  # type: ignore[attr-defined]
            arguments: dict[str, object] = {"Bucket": name, "ACL": "private"}
            if self._config.s3_region != "us-east-1":
                arguments["CreateBucketConfiguration"] = {
                    "LocationConstraint": self._config.s3_region
                }
            await client.create_bucket(**arguments)

    async def _empty_and_delete_bucket(self, name: str) -> None:
        try:
            async with self._s3_client() as client:  # type: ignore[attr-defined]
                while True:
                    response = await client.list_objects_v2(Bucket=name)
                    objects = [
                        {"Key": item["Key"]}
                        for item in response.get("Contents", ())
                        if "Key" in item
                    ]
                    if not objects:
                        break
                    deleted = await client.delete_objects(
                        Bucket=name,
                        Delete={"Objects": objects, "Quiet": True},
                    )
                    if deleted.get("Errors"):
                        raise RuntimeError("temporary bucket object cleanup failed")
                await client.delete_bucket(Bucket=name)
        except ClientError as error:
            if error.response.get("Error", {}).get("Code") != "NoSuchBucket":
                raise


def run_isolated_integration(
    pytest_args: Sequence[str],
    *,
    config: IntegrationConfig,
    backend: ResourceBackend,
    process_runner: ProcessRunner,
    token_factory: Callable[[], str] | None = None,
    password_factory: Callable[[], str] | None = None,
    migration_verifier: str = "verify_round11_migration.py",
) -> int:
    """Provision, run migrations and pytest, then clean up without masking test failures."""
    if not pytest_args:
        raise ValueError("at least one pytest argument is required")

    resources = TemporaryResources.generate(token_factory, password_factory)
    database_created = False
    bucket_created = False
    login_roles_created = False
    cleanup_failed = False
    exit_code = 0
    try:
        print(
            f"Creating isolated integration resources "
            f"database={resources.database} bucket={resources.bucket}"
        )
        backend.create_database(resources.database)
        database_created = True
        backend.create_private_bucket(resources.bucket)
        bucket_created = True

        migration_environment = _migration_environment(config, resources)
        exit_code = process_runner(
            _migration_command(config, migration_verifier), migration_environment
        )
        if exit_code == 0:
            backend.create_login_roles(resources)
            login_roles_created = True
            suite_environment = _suite_environment(config, resources)
            exit_code = process_runner(
                (
                    config.python_executable,
                    "-m",
                    "pytest",
                    *pytest_args,
                ),
                suite_environment,
            )
    finally:
        if bucket_created:
            try:
                backend.empty_and_delete_bucket(resources.bucket)
            except Exception:
                cleanup_failed = True
                print("Cleanup failed for temporary bucket; details redacted.", file=sys.stderr)
        if database_created:
            try:
                backend.drop_database(resources.database)
            except Exception:
                cleanup_failed = True
                print("Cleanup failed for temporary database; details redacted.", file=sys.stderr)
        if login_roles_created:
            try:
                backend.drop_login_roles(resources)
            except Exception:
                cleanup_failed = True
                print(
                    "Cleanup failed for temporary login roles; details redacted.",
                    file=sys.stderr,
                )

    if exit_code == 0 and cleanup_failed:
        return CLEANUP_FAILURE_EXIT_CODE
    return exit_code


def _migration_command(
    config: IntegrationConfig, verifier: str = "verify_round11_migration.py"
) -> tuple[str, ...]:
    if verifier not in {
        "verify_round08_migration.py",
        "verify_round09_migration.py",
        "verify_round10_migration.py",
        "verify_round11_migration.py",
        "verify_round13_migration.py",
        "verify_round14_migration.py",
        "verify_round15_migration.py",
        "verify_round16_migration.py",
        "verify_round17_migration.py",
        "verify_ai01_migration.py",
        "verify_pers01_migration.py",
        "verify_pers02_migration.py",
        "verify_pers03_migration.py",
        "verify_pers04_migration.py",
        "verify_pers05_migration.py",
        "verify_pers06_migration.py",
        "verify_pers07_migration.py",
        "verify_pers08_migration.py",
        "verify_pers10_migration.py",
        "verify_controlled_runs_migration.py",
        "verify_t05_migration.py",
        "verify_t06_migration.py",
        "verify_t07_migration.py",
        "verify_t09_migration.py",
        "verify_t11_migration.py",
        "verify_t12_migration.py",
        "verify_autonomous_policy_migration.py",
        "verify_phase3_trustworthy_event_migration.py",
        "verify_phase4_controlled_handoff_migration.py",
        "verify_phase5_formal_reconciliation_migration.py",
    }:
        raise ValueError("migration verifier is not approved")
    return (
        config.python_executable,
        f"scripts/{verifier}",
    )


def _migration_environment(
    config: IntegrationConfig, resources: TemporaryResources
) -> dict[str, str]:
    environment = dict(os.environ)
    environment["SRBG_DATABASE_URL"] = config.database_url(
        config.postgres_admin_user,
        config.postgres_admin_password,
        resources.database,
    )
    return environment


def _suite_environment(config: IntegrationConfig, resources: TemporaryResources) -> dict[str, str]:
    environment = dict(os.environ)
    for name in _BOOTSTRAP_CREDENTIAL_KEYS:
        environment.pop(name, None)
    environment.update(
        {
            "SRBG_RUN_SAFETY_INTEGRATION": "1",
            "SRBG_RUN_ROUND13_INTEGRATION": "1",
            "SRBG_RUN_SOURCE_INTEGRATION": "1",
            "SRBG_DATABASE_URL": config.database_url(
                resources.runtime_role, resources.runtime_password, resources.database
            ),
            "SRBG_TEST_ADMIN_DATABASE_URL": config.database_url(
                config.postgres_admin_user,
                config.postgres_admin_password,
                resources.database,
            ),
            "SRBG_PUBLICATION_DATABASE_URL": config.database_url(
                resources.publication_role,
                resources.publication_password,
                resources.database,
            ),
            "SRBG_WORKER_DATABASE_URL": config.database_url(
                resources.worker_role,
                resources.worker_password,
                resources.database,
            ),
            "SRBG_REDIS_URL": (
                f"redis://127.0.0.1:{_environment_port('REDIS_PORT', 6379)}/0"
            ),
            "SRBG_PROJECTION_DATABASE_URL": config.database_url(
                resources.projection_reader_role,
                resources.projection_reader_password,
                resources.database,
            ),
            "SRBG_S3_ENDPOINT_URL": config.s3_endpoint_url,
            "SRBG_S3_ACCESS_KEY": config.s3_access_key,
            "SRBG_S3_SECRET_KEY": config.s3_secret_key,
            "SRBG_S3_BUCKET": resources.bucket,
            "SRBG_S3_REGION": config.s3_region,
            "SRBG_BACKUP_S3_ENDPOINT_URL": (
                f"http://127.0.0.1:{_environment_port('ANCHOR_MINIO_PORT', 9002)}"
            ),
            "SRBG_BACKUP_S3_BUCKET": os.environ.get("SRBG_BACKUP_S3_BUCKET", "srbg-audit-anchors"),
            "SRBG_BACKUP_S3_ACCESS_KEY": os.environ.get(
                "ANCHOR_MINIO_ROOT_USER", "srbg_anchor_local"
            ),
            "SRBG_BACKUP_S3_SECRET_KEY": os.environ.get(
                "ANCHOR_MINIO_ROOT_PASSWORD", "srbg_anchor_storage_only"
            ),
        }
    )
    return environment


def _run_process(command: Sequence[str], environment: Mapping[str, str]) -> int:
    completed = subprocess.run(  # noqa: S603 - executable is the current Python interpreter.
        list(command),
        cwd=ROOT,
        env=dict(environment),
        check=False,
    )
    return completed.returncode


def _environment_port(name: str, default: int) -> int:
    configured = os.environ.get(name)
    value = int(configured) if configured else default
    if not 1 <= value <= 65535:
        raise ValueError(f"{name} must be between 1 and 65535")
    return value


def _environment_timeout(name: str, default: float) -> float:
    value = float(os.environ.get(name, str(default)))
    if not 0 < value <= 30:
        raise ValueError(f"{name} must be greater than 0 and at most 30")
    return value


def _environment_flag(name: str) -> bool:
    value = os.environ.get(name, "0")
    if value not in {"0", "1"}:
        raise ValueError(f"{name} must be 0 or 1")
    return value == "1"


def _is_loopback_host(host: str) -> bool:
    normalized = host.rstrip(".").lower()
    if normalized == "localhost":
        return True
    try:
        return ipaddress.ip_address(normalized).is_loopback
    except ValueError:
        return False


def _parse_args(arguments: Sequence[str] | None) -> tuple[str, tuple[str, ...]]:
    parser = argparse.ArgumentParser(
        description="Run pytest with a disposable PostgreSQL database and MinIO bucket."
    )
    parser.add_argument(
        "--migration-verifier",
        choices=(
            "verify_round08_migration.py",
            "verify_round09_migration.py",
            "verify_round10_migration.py",
            "verify_round11_migration.py",
            "verify_round13_migration.py",
            "verify_round14_migration.py",
            "verify_round15_migration.py",
            "verify_round16_migration.py",
            "verify_round17_migration.py",
            "verify_ai01_migration.py",
            "verify_pers01_migration.py",
            "verify_pers02_migration.py",
            "verify_pers03_migration.py",
            "verify_pers04_migration.py",
            "verify_pers05_migration.py",
            "verify_pers06_migration.py",
            "verify_pers07_migration.py",
            "verify_pers08_migration.py",
            "verify_pers10_migration.py",
            "verify_controlled_runs_migration.py",
            "verify_t05_migration.py",
            "verify_t06_migration.py",
            "verify_t07_migration.py",
            "verify_t09_migration.py",
            "verify_t11_migration.py",
            "verify_t12_migration.py",
            "verify_autonomous_policy_migration.py",
            "verify_phase3_trustworthy_event_migration.py",
            "verify_phase4_controlled_handoff_migration.py",
            "verify_phase5_formal_reconciliation_migration.py",
        ),
        default="verify_round11_migration.py",
    )
    parser.add_argument("pytest_args", nargs=argparse.REMAINDER)
    namespace = parser.parse_args(arguments)
    pytest_args = tuple(namespace.pytest_args)
    if pytest_args[:1] == ("--",):
        pytest_args = pytest_args[1:]
    if not pytest_args:
        parser.error("pytest arguments are required after --")
    return namespace.migration_verifier, pytest_args


def main(arguments: Sequence[str] | None = None) -> int:
    migration_verifier, pytest_args = _parse_args(arguments)
    try:
        config = IntegrationConfig.from_environment()
        return run_isolated_integration(
            pytest_args,
            config=config,
            backend=LocalResourceBackend(config),
            process_runner=_run_process,
            migration_verifier=migration_verifier,
        )
    except Exception:
        if os.environ.get("SRBG_DEBUG_ISOLATED_SETUP") == "1":
            raise
        print("Isolated integration setup failed; details redacted.", file=sys.stderr)
        return SETUP_FAILURE_EXIT_CODE


if __name__ == "__main__":
    raise SystemExit(main())
