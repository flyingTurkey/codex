"""Validate Round 11 evidence integrity without promoting a BLOCKED decision."""

from pathlib import Path

from evaluate_readiness import ROOT, validate_readiness


def main() -> None:
    path = ROOT / "docs/acceptance/round-11-readiness-evidence.json"
    validate_readiness(path)
    print(f"Round 11 evidence integrity passed: {path.relative_to(Path.cwd())}")


if __name__ == "__main__":
    main()
