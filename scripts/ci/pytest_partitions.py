"""Verify that pytest partitions preserve the legacy collection exactly once."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

UNIT_PATHS = ("apps/api/tests", "apps/worker/tests", "tests/infrastructure")
CONTRACT_PATHS = ("packages/contracts/tests", "tests/contract")
LIVE_PATHS = ("tests/live",)


def compare_node_id_sets(
    *,
    old: set[str],
    partitions: Mapping[str, set[str]],
) -> None:
    """Raise when partitions overlap or do not equal the legacy collection."""
    seen: set[str] = set()
    overlaps: set[str] = set()
    for node_ids in partitions.values():
        overlaps.update(seen & node_ids)
        seen.update(node_ids)
    if overlaps:
        raise ValueError(f"pytest partitions overlap: {sorted(overlaps)}")

    missing = old - seen
    unexpected = seen - old
    if missing or unexpected:
        raise ValueError(
            "pytest partition union differs from legacy collection: "
            f"missing={sorted(missing)}, unexpected={sorted(unexpected)}"
        )


def _collect(repository: Path, paths: Sequence[str]) -> set[str]:
    command = [
        sys.executable,
        "-m",
        "pytest",
        "--collect-only",
        "-q",
        *paths,
    ]
    completed = subprocess.run(  # noqa: S603
        command,
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    )
    return {
        line.strip()
        for line in completed.stdout.splitlines()
        if "::" in line and not line.startswith(("=", "ERROR"))
    }


def verify(repository: Path) -> dict[str, int]:
    old = _collect(repository, ())
    partitions = {
        "unit": _collect(repository, UNIT_PATHS),
        "contract": _collect(repository, CONTRACT_PATHS),
        "live": _collect(repository, LIVE_PATHS),
    }
    compare_node_id_sets(old=old, partitions=partitions)
    return {
        "legacy": len(old),
        **{name: len(node_ids) for name, node_ids in partitions.items()},
    }


def main(arguments: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", type=Path, default=Path.cwd())
    namespace = parser.parse_args(arguments)
    print(json.dumps(verify(namespace.repository.resolve()), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
