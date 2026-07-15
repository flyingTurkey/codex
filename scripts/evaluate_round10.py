"""Measure the deployed Round 10 search path against its documented SLO."""

from __future__ import annotations

import argparse
import http.client
import json
from statistics import quantiles
from time import perf_counter
from urllib.parse import quote, urlsplit


def _request(base_url: str, query: str, *, etag: str | None = None) -> tuple[int, str | None]:
    target = urlsplit(base_url)
    if target.hostname is None:
        raise ValueError("base URL must include a hostname")
    connection_class = (
        http.client.HTTPSConnection if target.scheme == "https" else http.client.HTTPConnection
    )
    connection = connection_class(target.hostname, target.port, timeout=5)
    headers = {
        "X-Local-Roles": "viewer",
        "X-Local-User": "round10-slo-eval",
    }
    if etag is not None:
        headers["If-None-Match"] = etag
    try:
        connection.request("GET", f"/api/v1/search?q={quote(query)}", headers=headers)
        response = connection.getresponse()
        response.read()
        return response.status, response.getheader("ETag")
    finally:
        connection.close()


def evaluate(base_url: str, *, samples: int = 40) -> dict[str, object]:
    queries = ("隧道+监测预警+四川", "川交规\u30142026\u301510号")
    for query in queries:
        status, _ = _request(base_url, query)
        if status != 200:
            raise RuntimeError(f"search warm-up failed with HTTP {status}")

    durations: list[float] = []
    first_etag: str | None = None
    for index in range(samples):
        started = perf_counter()
        status, etag = _request(base_url, queries[index % len(queries)])
        durations.append((perf_counter() - started) * 1000)
        if status != 200:
            raise RuntimeError(f"search sample failed with HTTP {status}")
        first_etag = first_etag or etag

    if first_etag is None:
        raise RuntimeError("search response did not include an ETag")
    conditional_status, _ = _request(base_url, queries[0], etag=first_etag)
    if conditional_status != 304:
        raise RuntimeError(f"conditional search expected HTTP 304, got {conditional_status}")

    p95 = quantiles(durations, n=100, method="inclusive")[94]
    return {
        "base_url": base_url,
        "conditional_get_status": conditional_status,
        "p95_latency_ms": round(p95, 2),
        "samples": samples,
        "search_slo_ms": 800,
        "semantic_search_required": False,
        "passed": p95 <= 800,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--samples", default=40, type=int)
    args = parser.parse_args()
    report = evaluate(args.base_url.rstrip("/"), samples=args.samples)
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    if report["passed"] is not True:
        raise SystemExit("Round10 search P95 exceeded 800ms")


if __name__ == "__main__":
    main()
