"""Fail when canonical contract generation changes the current generated tree."""

from __future__ import annotations

import hashlib
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GENERATED = ROOT / "packages" / "contracts" / "generated"


def _snapshot() -> dict[str, str]:
    return {
        path.relative_to(GENERATED).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(GENERATED.rglob("*"))
        if path.is_file()
    }


def main() -> int:
    before = _snapshot()
    subprocess.run(
        [sys.executable, "-m", "srbg_contracts.export"],
        cwd=ROOT,
        check=True,
    )
    pnpm = shutil.which("pnpm")
    if pnpm is None:
        raise RuntimeError("pnpm is required to verify generated TypeScript contracts")
    subprocess.run(  # noqa: S603 - executable is resolved from the controlled toolchain PATH.
        [pnpm, "contracts:generate"], cwd=ROOT, check=True
    )
    after = _snapshot()
    if before == after:
        print("Generated contracts are reproducible.")
        return 0

    changed = sorted(
        path for path in before.keys() | after.keys() if before.get(path) != after.get(path)
    )
    print("Generated contract drift detected:", file=sys.stderr)
    for path in changed:
        print(f"- {path}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
