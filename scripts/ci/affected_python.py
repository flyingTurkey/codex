"""Run offline Python checks scoped to changed paths."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _run(*arguments: str) -> None:
    subprocess.run(  # noqa: S603
        [sys.executable, "-m", *arguments],
        cwd=ROOT,
        check=True,
    )


def main() -> int:
    paths = tuple(json.loads(os.environ.get("SRBG_CHANGED_PATHS", "[]")))
    python_paths = [path for path in paths if path.endswith(".py") and (ROOT / path).exists()]
    if python_paths:
        _run("ruff", "check", *python_paths)

    test_paths: set[str] = set()
    mypy_packages: set[str] = set()
    for path in python_paths:
        if path.startswith(("packages/contracts/tests/", "tests/contract/")):
            continue
        if "/tests/" in path or path.startswith("tests/infrastructure/"):
            if not path.startswith("tests/integration/"):
                test_paths.add(path)
        elif path.startswith("apps/api/"):
            test_paths.add("apps/api/tests")
            mypy_packages.add("srbg_api")
        elif path.startswith("apps/worker/"):
            test_paths.add("apps/worker/tests")
            mypy_packages.add("srbg_worker")
        elif path.startswith("scripts/"):
            candidate = f"tests/infrastructure/test_{Path(path).stem}.py"
            if (ROOT / candidate).exists():
                test_paths.add(candidate)

    if test_paths:
        _run("pytest", "-q", *sorted(test_paths))
    for package in sorted(mypy_packages):
        _run("mypy", "-p", package)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
