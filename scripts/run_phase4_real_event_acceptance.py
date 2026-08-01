"""Guard and execute the one-shot phase-4 source-display acceptance profile."""

from __future__ import annotations

import os
import secrets
import shutil
import socket
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROFILE = "phase4-source-display"
CONFIRMATION = "I_UNDERSTAND"
SOURCE_STREAM_ID = "019fbbb0-b1f6-7e3f-97c0-20e4c16616c5"


def require_source_display_projection(
    *,
    source_visible: bool,
    stream_visible: bool,
    normalized_url: str,
    expected_url: str,
    last_successful_fetch_at: object | None,
    last_content_discovered_at: object | None,
    discovered_count: int,
    fetched_count: int,
    failed_count: int,
) -> None:
    if not source_visible:
        raise RuntimeError("SOURCE_NOT_VISIBLE_ON_SOURCES")
    if not stream_visible or normalized_url != expected_url:
        raise RuntimeError("SOURCE_STREAM_NOT_VISIBLE_ON_SOURCES")
    if last_successful_fetch_at is None or last_content_discovered_at is None:
        raise RuntimeError("SOURCE_FETCH_NOT_VISIBLE_ON_SOURCES")
    if discovered_count != 1 or fetched_count != 1:
        raise RuntimeError("SOURCE_FETCH_NOT_VISIBLE_ON_SOURCES")
    if failed_count != 0:
        raise RuntimeError("SOURCE_FETCH_NOT_SUCCESSFUL_ON_SOURCES")


def _run(
    command: list[str],
    *,
    environment: dict[str, str] | None = None,
    capture: bool = False,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 - every executable and argument is locally fixed.
        command,
        cwd=ROOT,
        env=environment,
        check=False,
        text=True,
        capture_output=capture,
    )


def _required_preflight() -> str:
    if os.environ.get("LIVE_CONFIRM") != CONFIRMATION:
        raise RuntimeError("LIVE_CONFIRM must be I_UNDERSTAND")
    if os.environ.get("LIVE_ACCEPTANCE_PROFILE") != PROFILE:
        raise RuntimeError("LIVE_ACCEPTANCE_PROFILE must be phase4-source-display")
    expected = os.environ.get("RELEASE_CANDIDATE_SHA", "")
    actual = _run(["git", "rev-parse", "HEAD"], capture=True).stdout.strip()
    if len(expected) != 40 or expected != actual:
        raise RuntimeError("RELEASE_CANDIDATE_SHA must equal the checked-out HEAD")
    branch = _run(["git", "branch", "--show-current"], capture=True).stdout.strip()
    if branch != "codex/phase-4-real-event-acceptance":
        raise RuntimeError("phase-4 live acceptance requires the phase-4 branch")
    status = _run(["git", "status", "--porcelain"], capture=True).stdout.strip()
    if status:
        raise RuntimeError("phase-4 live acceptance requires a clean worktree")
    return actual


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def _validated_cleanup(path: Path) -> None:
    root = (ROOT / ".cache" / "phase4-runs").resolve()
    target = path.resolve()
    if target == root or root not in target.parents:
        raise RuntimeError("refusing to clean an unbounded phase-4 path")
    if target.exists():
        shutil.rmtree(target)


def main() -> int:
    release_sha = _required_preflight()
    token = secrets.token_hex(6)
    project = f"srbg-phase4-{token}"
    run_root = (ROOT / ".cache" / "phase4-runs" / token).resolve()
    data_root = run_root / "data"
    evidence = (
        ROOT / ".cache" / "phase4-evidence" / f"{release_sha}-{token}.json"
    ).resolve()
    data_root.mkdir(parents=True, exist_ok=False)
    evidence.parent.mkdir(parents=True, exist_ok=True)
    ports = {
        "POSTGRES_PORT": _free_port(),
        "REDIS_PORT": _free_port(),
        "MINIO_PORT": _free_port(),
        "MINIO_CONSOLE_PORT": _free_port(),
        "ANCHOR_MINIO_PORT": _free_port(),
    }
    environment = dict(os.environ)
    environment.update(
        {
            key: str(value) for key, value in ports.items()
        }
        | {
            "SRBG_DATA_ROOT": data_root.as_posix(),
            "POSTGRES_HOST": "127.0.0.1",
            "POSTGRES_DB": "srbg",
            "POSTGRES_USER": "srbg",
            "POSTGRES_PASSWORD": "srbg_phase4_local_only",
            "MINIO_ROOT_USER": "srbg_phase4",
            "MINIO_ROOT_PASSWORD": "srbg_phase4_storage_only",
            "SRBG_S3_BUCKET": "srbg-phase4-unused",
            "SRBG_EXTERNAL_IO_TIMEOUT_SECONDS": "10",
            "SRBG_PHASE4_LIVE_CONFIRM": CONFIRMATION,
            "SRBG_PHASE4_RELEASE_CANDIDATE_SHA": release_sha,
            "SRBG_PHASE4_SOURCE_STREAM_ID": SOURCE_STREAM_ID,
            "SRBG_PHASE4_EVIDENCE_OUTPUT": str(evidence),
        }
    )
    compose = [
        "docker",
        "compose",
        "--project-name",
        project,
        "--project-directory",
        str(ROOT),
        "--file",
        str(ROOT / "infra" / "compose" / "compose.yaml"),
        "--file",
        str(ROOT / "infra" / "compose" / "compose.phase4.yaml"),
    ]
    exit_code = 1
    try:
        network_route = (
            "PINNED_LOCAL_SOCKS5"
            if environment.get("SRBG_ACQUISITION_SOCKS5_PROXY_URL")
            else "PINNED_DIRECT"
        )
        print(
            "phase4_preflight_ok "
            f"sha={release_sha} profile={PROFILE} project={project} "
            f"source_stream_id={SOURCE_STREAM_ID} "
            "source_stream_key=CJHT_CURRENT_ISSUE "
            "deadline_seconds=600 model_calls=0 ai_cost_microusd=0 "
            f"network_route={network_route}"
        )
        started = _run(
            [*compose, "up", "--detach", "--wait", "postgres", "redis", "minio"],
            environment=environment,
        )
        if started.returncode:
            raise RuntimeError("isolated phase-4 infrastructure failed to start")
        bootstrapped = _run(
            [*compose, "run", "--rm", "--no-deps", "role-bootstrap"],
            environment=environment,
        )
        if bootstrapped.returncode:
            raise RuntimeError("isolated phase-4 database roles failed to bootstrap")
        command = [
            sys.executable,
            "scripts/run_isolated_integration.py",
            "--migration-verifier",
            "verify_phase4_controlled_handoff_migration.py",
            "--",
            "tests/live/test_phase4_real_event_acceptance.py::"
            "test_one_controlled_source_display",
            "-q",
            "-s",
        ]
        completed = _run(command, environment=environment)
        exit_code = completed.returncode
        print(
            f"phase4_live_complete exit_code={exit_code} evidence={evidence} "
            f"project={project}"
        )
    finally:
        _run([*compose, "down", "--volumes", "--remove-orphans"], environment=environment)
        _validated_cleanup(run_root)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
