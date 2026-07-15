"""Emit an actual-window SLO and error-budget report from Prometheus."""

from __future__ import annotations

import argparse
import json
import math
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx2 as httpx


def error_budget(*, target_percent: float, observed_percent: float) -> dict[str, float]:
    allowed = max(0.0, 100.0 - target_percent)
    consumed = max(0.0, 100.0 - observed_percent)
    return {
        "allowed_unavailability_percent": round(allowed, 6),
        "consumed_unavailability_percent": round(consumed, 6),
        "remaining_percent_of_budget": round(
            max(0.0, 100.0 * (allowed - consumed) / allowed) if allowed else 0.0,
            2,
        ),
    }


def _query(client: httpx.Client, base_url: str, expression: str) -> float | None:
    response = client.get(f"{base_url.rstrip('/')}/api/v1/query", params={"query": expression})
    response.raise_for_status()
    payload: Any = response.json()
    result = payload.get("data", {}).get("result", [])
    if not result:
        return None
    value = float(result[0]["value"][1])
    return value if math.isfinite(value) else None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prometheus-url", default="http://127.0.0.1:9090")
    parser.add_argument("--days", type=int, default=7, choices=range(1, 15))
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    ended_at = datetime.now(UTC)
    started_at = ended_at - timedelta(days=args.days)
    window = f"{args.days}d"
    with httpx.Client(timeout=5.0, follow_redirects=False) as client:
        total = _query(
            client,
            args.prometheus_url,
            f"sum(increase(srbg_api_requests_total[{window}]))",
        )
        failures = _query(
            client,
            args.prometheus_url,
            f'sum(increase(srbg_api_requests_total{{status=~"5.."}}[{window}]))',
        )
        search_p95 = _query(
            client,
            args.prometheus_url,
            "histogram_quantile(0.95, sum by (le) "
            f"(rate(srbg_search_duration_seconds_bucket[{window}])))",
        )
    if total is not None and failures is None:
        failures = 0.0
    availability = None
    if total is not None and failures is not None and total > 0:
        availability = 100.0 * (total - failures) / total
    report = {
        "command": "python scripts/slo_weekly_report.py",
        "environment": "TEST",
        "executed_at": ended_at.isoformat().replace("+00:00", "Z"),
        "executed_by": {"kind": "AGENT", "id": "Codex"},
        "window": {
            "started_at": started_at.isoformat(),
            "ended_at": ended_at.isoformat(),
            "requested_duration_days": args.days,
            "continuous_data_coverage_verified": False,
        },
        "availability_percent": availability,
        "availability_error_budget": (
            error_budget(target_percent=99.5, observed_percent=availability)
            if availability is not None
            else None
        ),
        "search_p95_ms": search_p95 * 1000 if search_p95 is not None else None,
        "sampled_requests": total,
        "continuous_14_day_claim": False,
    }
    rendered = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output is not None:
        args.output.write_bytes(rendered.encode("utf-8"))
    print(rendered, end="")


if __name__ == "__main__":
    main()
