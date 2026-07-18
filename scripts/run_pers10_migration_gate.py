"""Run the destructive PERS-10 role retirement replay in a disposable PG cluster."""

from __future__ import annotations

import os
import re
import secrets
import subprocess
import sys
import time
from collections.abc import Mapping, Sequence
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
IMAGE = "srbg-postgres:17.10-pgvector-0.8.2"
_CONTAINER = re.compile(r"srbg-pers10-pg-[0-9a-f]{24}\Z")
_PORT = re.compile(r"127\.0\.0\.1:(\d{1,5})\Z")


def _run(
    command: Sequence[str], *, environment: Mapping[str, str]
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 - every executable and argument is fixed or validated.
        list(command),
        cwd=ROOT,
        env=dict(environment),
        check=False,
        capture_output=True,
        text=True,
    )


def _validated_port(binding: str) -> int:
    match = _PORT.fullmatch(binding.strip())
    if match is None:
        raise RuntimeError("disposable PostgreSQL returned an invalid loopback binding")
    port = int(match.group(1))
    if not 1 <= port <= 65535:
        raise RuntimeError("disposable PostgreSQL returned an invalid port")
    return port


def main(arguments: Sequence[str] | None = None) -> int:
    pytest_args = tuple(arguments if arguments is not None else sys.argv[1:])
    if not pytest_args:
        raise ValueError("PERS-10 migration gate requires at least one pytest path")
    name = f"srbg-pers10-pg-{uuid4().hex[:24]}"
    if _CONTAINER.fullmatch(name) is None:
        raise RuntimeError("refusing an unsafe disposable container name")
    password = secrets.token_urlsafe(32)
    environment = dict(os.environ)
    environment["POSTGRES_PASSWORD"] = password
    started = False
    exit_code = 1
    try:
        result = _run(
            (
                "docker",
                "run",
                "--detach",
                "--rm",
                "--name",
                name,
                "--publish",
                "127.0.0.1::5432",
                "--env",
                "POSTGRES_PASSWORD",
                "--env",
                "POSTGRES_USER=srbg",
                "--env",
                "POSTGRES_DB=srbg",
                IMAGE,
            ),
            environment=environment,
        )
        if result.returncode != 0:
            raise RuntimeError("failed to start disposable PostgreSQL cluster")
        started = True
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            ready = _run(
                ("docker", "exec", name, "pg_isready", "-U", "srbg", "-d", "srbg"),
                environment=environment,
            )
            if ready.returncode == 0:
                break
            time.sleep(0.5)
        else:
            raise RuntimeError("disposable PostgreSQL did not become ready")
        bootstrap_command = (
            "docker",
            "exec",
            name,
            "psql",
            "--username",
            "srbg",
            "--dbname",
            "srbg",
            "--set",
            "ON_ERROR_STOP=1",
            "--command",
            "DO $bootstrap$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles "
            "WHERE rolname='srbg_publisher_login') THEN CREATE ROLE "
            "srbg_publisher_login NOLOGIN; END IF; END $bootstrap$",
        )
        while time.monotonic() < deadline:
            bootstrap = _run(bootstrap_command, environment=environment)
            if bootstrap.returncode == 0:
                break
            time.sleep(0.5)
        else:
            raise RuntimeError("failed to bootstrap the required internal migration principal")
        port_result = _run(("docker", "port", name, "5432/tcp"), environment=environment)
        if port_result.returncode != 0:
            raise RuntimeError("failed to inspect disposable PostgreSQL binding")
        environment.update(
            {
                "POSTGRES_HOST": "127.0.0.1",
                "POSTGRES_PORT": str(_validated_port(port_result.stdout)),
                "POSTGRES_USER": "srbg",
                "POSTGRES_DB": "srbg",
            }
        )
        completed = subprocess.run(  # noqa: S603
            (
                sys.executable,
                "scripts/run_isolated_integration.py",
                "--migration-verifier",
                "verify_pers10_migration.py",
                "--",
                *pytest_args,
            ),
            cwd=ROOT,
            env=environment,
            check=False,
        )
        exit_code = completed.returncode
    finally:
        environment.pop("POSTGRES_PASSWORD", None)
        if started:
            cleanup = _run(("docker", "rm", "--force", name), environment=environment)
            if cleanup.returncode != 0:
                print("Disposable PostgreSQL cleanup failed.", file=sys.stderr)
                exit_code = 1
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
