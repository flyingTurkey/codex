"""Guard and execute the one-shot phase-4 real event acceptance profile."""

from __future__ import annotations

import os
import secrets
import shutil
import socket
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROFILE = "phase4-real-event"
CONFIRMATION = "I_UNDERSTAND"
SOURCE_STREAM_ID = "019fb870-06f4-7227-a03e-a6b11dcbf91e"


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
        raise RuntimeError("LIVE_ACCEPTANCE_PROFILE must be phase4-real-event")
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


def _load_key() -> str:
    source_volume = os.environ.get(
        "SRBG_PHASE4_SECRET_SOURCE_VOLUME",
        "srbg-intelligence_ai-secrets",
    )
    inspected = _run(["docker", "volume", "inspect", source_volume], capture=True)
    if inspected.returncode:
        raise RuntimeError("approved DeepSeek secret volume is unavailable")
    result = _run(
        [
            "docker",
            "run",
            "--rm",
            "--network",
            "none",
            "--volume",
            f"{source_volume}:/run/approved-secret:ro",
            "alpine:3.21",
            "sh",
            "-c",
            "test -s /run/approved-secret/deepseek.key && "
            "cat /run/approved-secret/deepseek.key",
        ],
        capture=True,
    )
    key = result.stdout
    if result.returncode or not 20 <= len(key) <= 4096 or any(
        character in key for character in "\r\n\x00"
    ):
        raise RuntimeError("approved DeepSeek secret is invalid")
    return key


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
            "SRBG_AI_PROVIDER": "deepseek",
            "SRBG_AI_ENVIRONMENT": "acceptance",
            "SRBG_AI_TIMEOUT_SECONDS": "30",
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
        environment["SRBG_AI_API_KEY"] = _load_key()
        network_route = (
            "PINNED_LOCAL_SOCKS5"
            if environment.get("SRBG_ACQUISITION_SOCKS5_PROXY_URL")
            else "PINNED_DIRECT"
        )
        print(
            "phase4_preflight_ok "
            f"sha={release_sha} profile={PROFILE} project={project} "
            f"source_stream_id={SOURCE_STREAM_ID} "
            "source_stream_key=sany-construction-cases "
            "budget_microusd=50000 deadline_seconds=1500 max_model_calls=8 "
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
            "test_one_controlled_real_industry_update",
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
        environment.pop("SRBG_AI_API_KEY", None)
        _run([*compose, "down", "--volumes", "--remove-orphans"], environment=environment)
        _validated_cleanup(run_root)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
