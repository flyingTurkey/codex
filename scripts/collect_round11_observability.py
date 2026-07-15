"""Collect fresh local Round 11 observability runtime evidence."""

from __future__ import annotations

import argparse
import base64
import json
import os
import shutil
import subprocess
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
DOCKER = shutil.which("docker")
if DOCKER is None:
    raise RuntimeError("docker is required to collect observability evidence")


def _json(url: str, authorization: str | None = None) -> Any:
    headers = {"Authorization": authorization} if authorization else {}
    with urlopen(Request(url, headers=headers), timeout=5) as response:  # noqa: S310
        return json.load(response)


def _sha(relative: str) -> str:
    return sha256((ROOT / relative).read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    prometheus = _json("http://127.0.0.1:9090/api/v1/targets")
    rules = _json("http://127.0.0.1:9090/api/v1/rules")
    grafana_health = _json("http://127.0.0.1:3001/api/health")
    password = os.environ.get("GRAFANA_ADMIN_PASSWORD", "demo-only-grafana-password")
    basic = base64.b64encode(f"admin:{password}".encode()).decode()
    datasources = _json("http://127.0.0.1:3001/api/datasources", f"Basic {basic}")
    alertmanager = _json("http://127.0.0.1:9093/api/v2/status")
    compose = subprocess.run(  # noqa: S603 - resolved executable with fixed local arguments.
        [
            DOCKER,
            "compose",
            "--project-directory",
            ".",
            "-f",
            "infra/compose/compose.yaml",
            "ps",
            "otel-collector",
            "--format",
            "json",
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    otel = json.loads(compose.stdout)
    targets = prometheus["data"]["activeTargets"]
    api_target = next(item for item in targets if item["labels"].get("job") == "srbg-api")
    rule_rows = [
        {"name": item["name"], "health": item["health"]}
        for group in rules["data"]["groups"]
        for item in group["rules"]
    ]
    datasource = next(item for item in datasources if item["type"] == "prometheus")
    report = {
        "command": "python scripts/collect_round11_observability.py",
        "executed_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "executed_by": {"kind": "AGENT", "id": "Codex"},
        "environment": "TEST",
        "prometheus": {
            "target": api_target["scrapeUrl"],
            "health": api_target["health"],
            "last_error": api_target["lastError"],
            "rules": rule_rows,
        },
        "grafana": {
            "database": grafana_health["database"],
            "version": grafana_health["version"],
            "datasource": {
                "name": datasource["name"],
                "type": datasource["type"],
                "url": datasource["url"],
            },
        },
        "alertmanager": {
            "cluster_status": alertmanager["cluster"]["status"],
            "receiver": "unconfigured",
            "production_route_verified": False,
        },
        "opentelemetry_collector": {
            "image": otel["Image"],
            "container_state": otel["State"].lower(),
        },
        "configuration_hashes": {
            "compose": _sha("infra/compose/compose.yaml"),
            "prometheus_rules": _sha("infra/observability/prometheus/rules.yml"),
            "alertmanager": _sha("infra/observability/alertmanager/alertmanager.yml"),
        },
        "continuous_window_claim": False,
    }
    rendered = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    args.output.write_bytes(rendered.encode("utf-8"))
    print(rendered, end="")


if __name__ == "__main__":
    main()
