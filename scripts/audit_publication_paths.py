"""Fail closed when application code bypasses the sole PublicationService repository."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WRITE_PATTERN = re.compile(
    r"\b(?:INSERT\s+INTO|UPDATE|DELETE\s+FROM)\s+(?:public\.)?"
    r"(?:publication|publication_revision)\b",
    re.IGNORECASE,
)
ALLOWED_WRITER = Path("apps/api/src/srbg_api/publication/repository.py")
# Migration verifiers run only against a validated loopback disposable database. Their
# deterministic fixtures are not application publication paths and cannot be imported by
# API/Worker runtime code.
NON_APPLICATION_FIXTURE_WRITERS = frozenset(
    {Path("scripts/verify_round17_migration.py")}
)
SCANNED_ROOTS = (
    Path("apps/api/src"),
    Path("apps/worker/src"),
    Path("scripts"),
)


def audit_publication_paths() -> list[str]:
    findings: list[str] = []
    for scanned_root in SCANNED_ROOTS:
        for path in (ROOT / scanned_root).rglob("*.py"):
            relative = path.relative_to(ROOT)
            if (
                relative == ALLOWED_WRITER
                or relative == Path("scripts/audit_publication_paths.py")
                or relative in NON_APPLICATION_FIXTURE_WRITERS
            ):
                continue
            content = path.read_text(encoding="utf-8")
            for match in WRITE_PATTERN.finditer(content):
                line = content.count("\n", 0, match.start()) + 1
                findings.append(f"{relative.as_posix()}:{line}:{match.group(0)}")
    return findings


def main() -> None:
    findings = audit_publication_paths()
    if findings:
        raise SystemExit("publication write bypasses found:\n" + "\n".join(findings))
    print("Publication path audit passed: all application writes use PublicationService")


if __name__ == "__main__":
    main()
