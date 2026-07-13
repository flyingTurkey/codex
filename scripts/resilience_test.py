"""Verify Redis loss degrades readiness without breaking liveness."""

from __future__ import annotations

import json
import subprocess

from scripts.smoke import host_port, parse_object, require, wait_for_status

COMPOSE = [
    "docker",
    "compose",
    "--project-directory",
    ".",
    "-f",
    "infra/compose/compose.yaml",
]


def compose(*arguments: str) -> None:
    subprocess.run([*COMPOSE, *arguments], check=True)  # noqa: S603


def main() -> None:
    api_port = host_port("API_PORT", 8000)
    try:
        compose("stop", "redis")
        degraded = parse_object(
            wait_for_status(api_port, "/health/ready", 503, timeout=30)
        )
        require(degraded["status"] == "not_ready", "readiness did not degrade")
        require(degraded["checks"]["redis"]["status"] == "down", "Redis stayed up")

        liveness = parse_object(wait_for_status(api_port, "/health/live", 200))
        require(liveness["status"] == "ok", "liveness failed with Redis down")
        print(json.dumps({"status": "ok", "readiness": degraded}, ensure_ascii=False))
    finally:
        compose("start", "redis")
        restored = parse_object(
            wait_for_status(api_port, "/health/ready", 200, timeout=60)
        )
        require(restored["status"] == "ready", "readiness did not recover")


if __name__ == "__main__":
    main()
