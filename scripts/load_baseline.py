"""Small reproducible API/search load and capacity baseline."""

from __future__ import annotations

import argparse
import http.client
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from statistics import quantiles
from time import perf_counter
from urllib.parse import urlsplit


def _sample(base_url: str, path: str) -> tuple[int, float]:
    target = urlsplit(base_url)
    started = perf_counter()
    connection = http.client.HTTPConnection(target.hostname, target.port, timeout=5)
    try:
        connection.request("GET", path)
        response = connection.getresponse()
        response.read()
        return response.status, (perf_counter() - started) * 1000
    finally:
        connection.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--samples", type=int, default=100)
    parser.add_argument("--concurrency", type=int, default=10)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    started_at = datetime.now(UTC)
    paths = ["/health/live", "/api/v1/search?q=%E9%9A%A7%E9%81%93"]
    with ThreadPoolExecutor(max_workers=args.concurrency) as executor:
        results = list(
            executor.map(
                lambda index: _sample(args.base_url, paths[index % len(paths)]),
                range(args.samples),
            )
        )
    durations = [duration for _, duration in results]
    errors = sum(status >= 400 for status, _ in results)
    p95 = quantiles(durations, n=100, method="inclusive")[94]
    report = {
        "command": "python scripts/load_baseline.py",
        "environment": "TEST",
        "executed_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "executed_by": {"kind": "AGENT", "id": "Codex"},
        "started_at": started_at.isoformat().replace("+00:00", "Z"),
        "samples": args.samples,
        "concurrency": args.concurrency,
        "p95_latency_ms": round(p95, 2),
        "errors": errors,
        "single_document_cost": {"provider": "mock", "microusd": 0, "production_baseline": False},
        "passed": errors == 0 and p95 <= 800,
    }
    rendered = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output is not None:
        args.output.write_bytes(rendered.encode("utf-8"))
    print(rendered, end="")
    if not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
