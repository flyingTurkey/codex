"""Verify executable runbook coverage without performing production actions."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def runbook_scenarios() -> tuple[str, ...]:
    return (
        "release",
        "rollback",
        "withdrawal",
        "source_failure",
        "model_anomaly",
        "redis_rebuild",
    )


def main() -> None:
    runbook = (ROOT / "docs/operations/runbooks.md").read_text(encoding="utf-8")
    missing = [scenario for scenario in runbook_scenarios() if f"`{scenario}`" not in runbook]
    if missing:
        raise SystemExit(f"runbook scenarios missing: {', '.join(missing)}")
    print(f"Verified {len(runbook_scenarios())} executable runbook scenarios.")


if __name__ == "__main__":
    main()
