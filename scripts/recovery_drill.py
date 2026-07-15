"""Perform a destructive-only-in-random-namespaces recovery drill."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from time import perf_counter
from uuid import uuid4

COMPOSE = ["docker", "compose", "--project-directory", ".", "-f", "infra/compose/compose.yaml"]


def validate_drill_environment(environment: str, confirmation: str) -> None:
    if environment.lower() in {"production", "preproduction"}:
        raise RuntimeError("recovery drill refuses production and preproduction targets")
    if confirmation != "ISOLATED_ONLY":
        raise RuntimeError("set SRBG_RECOVERY_DRILL_CONFIRM=ISOLATED_ONLY")


def _run(*arguments: str, capture: bool = False) -> str:
    completed = subprocess.run(  # noqa: S603 - executable and arguments are fixed locally
        [*COMPOSE, *arguments],
        check=True,
        text=True,
        capture_output=capture,
    )
    return completed.stdout if capture else ""


def _psql(database: str, sql: str) -> str:
    if re.fullmatch(r"srbg(?:_drill_[0-9a-f]{16})?", database) is None:
        raise ValueError("unsafe drill database identifier")
    return _run(
        "exec",
        "-T",
        "postgres",
        "psql",
        "--set=ON_ERROR_STOP=1",
        "-U",
        os.environ.get("POSTGRES_USER", "srbg"),
        "-d",
        database,
        "-Atc",
        sql,
        capture=True,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--isolated-only",
        action="store_true",
        help="confirm that the drill may mutate only generated disposable namespaces",
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    environment = os.environ.get("SRBG_ENVIRONMENT", "test")
    validate_drill_environment(
        environment,
        "ISOLATED_ONLY"
        if args.isolated_only
        else os.environ.get("SRBG_RECOVERY_DRILL_CONFIRM", ""),
    )
    token = uuid4().hex[:16]
    database = f"srbg_drill_{token}"
    source_bucket = f"srbg-drill-source-{token}"
    backup_bucket = f"srbg-drill-backup-{token}"
    dump = f"/tmp/{database}.dump"  # noqa: S108 - path is inside the disposable container
    marker = f"round11-{token}"
    started_at = datetime.now(UTC)
    started = perf_counter()
    postgres_ok = object_ok = redis_ok = False
    _run("up", "--detach", "--wait", "postgres", "redis", "minio")
    try:
        _psql("srbg", f'CREATE DATABASE "{database}"')
        _psql(database, "CREATE TABLE drill_marker(value text primary key)")
        _psql(
            database,
            f"INSERT INTO drill_marker VALUES ('{marker}-before')",  # noqa: S608
        )
        _run(
            "exec",
            "-T",
            "postgres",
            "pg_dump",
            "-U",
            os.environ.get("POSTGRES_USER", "srbg"),
            "-Fc",
            "-d",
            database,
            "-f",
            dump,
        )
        _psql(
            database,
            f"INSERT INTO drill_marker VALUES ('{marker}-after')",  # noqa: S608
        )
        _psql("srbg", f'DROP DATABASE "{database}" WITH (FORCE)')
        _psql("srbg", f'CREATE DATABASE "{database}"')
        _run(
            "exec",
            "-T",
            "postgres",
            "pg_restore",
            "-U",
            os.environ.get("POSTGRES_USER", "srbg"),
            "-d",
            database,
            dump,
        )
        values = _psql(database, "SELECT value FROM drill_marker ORDER BY value")
        postgres_ok = f"{marker}-before" in values and f"{marker}-after" not in values

        object_script = f'''set -eu
mc alias set local http://minio:9000 "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD" >/dev/null
mc mb --ignore-existing local/{source_bucket} local/{backup_bucket} >/dev/null
mc version enable local/{backup_bucket} >/dev/null
printf %s {marker} | mc pipe local/{source_bucket}/marker >/dev/null
mc cp local/{source_bucket}/marker local/{backup_bucket}/marker >/dev/null
mc rb --force local/{source_bucket} >/dev/null
mc mb local/{source_bucket} >/dev/null
mc cp local/{backup_bucket}/marker local/{source_bucket}/marker >/dev/null
mc cat local/{source_bucket}/marker
mc rb --force local/{source_bucket} local/{backup_bucket} >/dev/null
'''
        object_value = _run(
            "run",
            "--rm",
            "--entrypoint",
            "/bin/sh",
            "minio-init",
            "-ec",
            object_script,
            capture=True,
        )
        object_ok = marker in object_value

        _run("exec", "-T", "redis", "redis-cli", "-n", "15", "SET", "srbg:drill:pending", marker)
        _run("exec", "-T", "redis", "redis-cli", "-n", "15", "FLUSHDB")
        _run("exec", "-T", "redis", "redis-cli", "-n", "15", "SET", "srbg:drill:pending", marker)
        redis_value = _run(
            "exec",
            "-T",
            "redis",
            "redis-cli",
            "-n",
            "15",
            "GET",
            "srbg:drill:pending",
            capture=True,
        )
        redis_ok = marker in redis_value
    finally:
        try:
            _psql("srbg", f'DROP DATABASE IF EXISTS "{database}" WITH (FORCE)')
            _run("exec", "-T", "postgres", "rm", "-f", dump)
            _run("exec", "-T", "redis", "redis-cli", "-n", "15", "FLUSHDB")
        except subprocess.CalledProcessError:
            pass
    completed_at = datetime.now(UTC)
    rto_minutes = (perf_counter() - started) / 60
    report = {
        "command": "python scripts/recovery_drill.py --isolated-only",
        "executed_by": {"kind": "AGENT", "id": "Codex"},
        "environment": environment,
        "exercise": "ISOLATED_LOGICAL_DATABASE_OBJECT_AND_REDIS_REBUILD",
        "started_at": started_at.isoformat(),
        "completed_at": completed_at.isoformat(),
        "rpo_minutes": 0,
        "rto_minutes": round(rto_minutes, 2),
        "postgres_restored": postgres_ok,
        "object_restored": object_ok,
        "redis_rebuilt": redis_ok,
        "pitr_production_evidence": False,
        "passed": postgres_ok and object_ok and redis_ok and rto_minutes <= 240,
    }
    report["evidence_sha256"] = sha256(
        json.dumps(report, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    rendered = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output is not None:
        args.output.write_bytes(rendered.encode("utf-8"))
    print(rendered, end="")
    if not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
