"""Classify changed paths and execute risk-triggered test gates."""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import os
import shlex
import shutil
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

Mode = Literal["fast", "pr", "release", "live"]
ROOT = Path(__file__).resolve().parents[2]
MATRIX_PATH = Path(__file__).with_name("risk-matrix.json")

BASE_GATES = {
    "fast": ("diff-check", "docs-check", "risk-classifier-test"),
    "pr": (
        "diff-check",
        "docs-check",
        "risk-classifier-test",
        "lint",
        "typecheck",
        "python-unit-test",
        "web-unit-test",
        "pytest-partitions",
    ),
}

RISK_GATES = {
    "contract": ("contract-test",),
    "migration": ("migration-test",),
    "docker": ("orchestration-test", "compose-config", "compose-smoke"),
    "dependency": ("security-check",),
    "acquisition": ("fixture-replay", "acquisition-integration-test"),
    "content": ("fixture-replay", "isolated-integration-test"),
    "ai": ("fixture-replay", "ai-integration-test"),
    "publication": ("publication-adversarial",),
    "security": ("fixture-replay", "security-check"),
    "frontend": ("web-build", "web-e2e", "web-a11y"),
    "integration": ("isolated-integration-test",),
    "infrastructure": ("compose-config",),
    "orchestration": ("orchestration-test", "compose-config"),
}
ALL_RISK_GATES = tuple(dict.fromkeys(gate for gates in RISK_GATES.values() for gate in gates))
RELEASE_GATES = tuple(
    dict.fromkeys(
        (
            "diff-check",
            "docs-check",
            "lint",
            "typecheck",
            "python-unit-test",
            "web-unit-test",
            "pytest-partitions",
            "risk-classifier-test",
            *ALL_RISK_GATES,
        )
    )
)
FAST_CATEGORY_GATES = {
    "python": ("python-affected-test",),
    "contract": ("contract-fast",),
    "frontend": ("frontend-fast",),
}
FAST_FAIL_CLOSED_GATES = (
    "lint",
    "typecheck",
    "python-unit-test",
    "web-unit-test",
    "pytest-partitions",
    "contract-fast",
    "frontend-fast",
)


@dataclass(frozen=True)
class ChangeSet:
    sources: dict[str, frozenset[str]]

    @classmethod
    def from_paths(cls, paths: list[str]) -> ChangeSet:
        return cls({_normalize(path): frozenset({"explicit"}) for path in paths})

    @property
    def paths(self) -> tuple[str, ...]:
        return tuple(sorted(self.sources))


@dataclass(frozen=True)
class Classification:
    categories: tuple[str, ...]
    unknown_paths: tuple[str, ...]
    changes: ChangeSet


@dataclass(frozen=True)
class Plan:
    mode: Mode
    gates: tuple[str, ...]


def _normalize(path: str) -> str:
    return path.replace("\\", "/").removeprefix("./")


def _git(repository: Path, *arguments: str) -> list[str]:
    git = shutil.which("git")
    if git is None:
        raise RuntimeError("Git executable is required")
    completed = subprocess.run(  # noqa: S603
        [git, *arguments],
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    )
    return [_normalize(line) for line in completed.stdout.splitlines() if line.strip()]


def _try_git(repository: Path, *arguments: str) -> list[str]:
    try:
        return _git(repository, *arguments)
    except subprocess.CalledProcessError:
        return []


def resolve_base_ref(repository: Path, *, explicit: str | None) -> str:
    """Resolve a conservative comparison base without ever defaulting to HEAD."""
    if explicit:
        if explicit == "HEAD":
            raise ValueError("HEAD is not a safe default comparison base")
        resolved = _try_git(repository, "rev-parse", "--verify", f"{explicit}^{{commit}}")
        if not resolved:
            raise ValueError(f"comparison base is not a commit: {explicit}")
        return explicit

    current_branch = _try_git(repository, "branch", "--show-current")
    current = current_branch[0] if current_branch else ""
    candidates: list[str] = []
    candidates.extend(
        _try_git(
            repository,
            "rev-parse",
            "--abbrev-ref",
            "--symbolic-full-name",
            "@{upstream}",
        )
    )
    candidates.extend(("main", "origin/main", "master", "origin/master"))
    candidates.extend(
        _try_git(
            repository,
            "for-each-ref",
            "--format=%(refname:short)",
            "refs/heads",
            "refs/remotes",
        )
    )
    best: tuple[int, str] | None = None
    for candidate in dict.fromkeys(candidates):
        if candidate in {current, f"origin/{current}"}:
            continue
        resolved = _try_git(repository, "rev-parse", "--verify", f"{candidate}^{{commit}}")
        if not resolved:
            continue
        merge_base = _try_git(repository, "merge-base", "HEAD", candidate)
        if not merge_base:
            continue
        distance = _try_git(repository, "rev-list", "--count", merge_base[0])
        if not distance:
            continue
        scored = (int(distance[0]), merge_base[0])
        if best is None or scored[0] > best[0]:
            best = scored
    if best is not None:
        return best[1]

    roots = _git(repository, "rev-list", "--max-parents=0", "HEAD")
    if not roots:
        raise RuntimeError("unable to derive a safe comparison base")
    return roots[-1]


def collect_changes(repository: Path, *, base_ref: str | None) -> ChangeSet:
    """Collect branch, index, worktree and untracked paths without losing provenance."""
    resolved_base = resolve_base_ref(repository, explicit=base_ref)
    sources: dict[str, set[str]] = {}
    commands = {
        "branch": (
            "diff",
            "--name-only",
            "--diff-filter=ACMRD",
            f"{resolved_base}...HEAD",
        ),
        "staged": ("diff", "--cached", "--name-only", "--diff-filter=ACMRD"),
        "unstaged": ("diff", "--name-only", "--diff-filter=ACMRD"),
        "untracked": ("ls-files", "--others", "--exclude-standard"),
    }
    for source, arguments in commands.items():
        for path in _git(repository, *arguments):
            sources.setdefault(path, set()).add(source)
    return ChangeSet({path: frozenset(values) for path, values in sources.items()})


def _load_matrix() -> dict[str, tuple[str, ...]]:
    payload = json.loads(MATRIX_PATH.read_text(encoding="utf-8"))
    return {
        category: tuple(patterns)
        for category, patterns in payload["categories"].items()
    }


def classify_changes(changes: ChangeSet) -> Classification:
    matrix = _load_matrix()
    categories: set[str] = set()
    unknown: list[str] = []
    for path in changes.paths:
        matched = {
            category
            for category, patterns in matrix.items()
            if any(fnmatch.fnmatchcase(path, pattern) for pattern in patterns)
        }
        if not matched:
            unknown.append(path)
        categories.update(matched)
    return Classification(tuple(sorted(categories)), tuple(sorted(unknown)), changes)


def plan_for_mode(mode: Mode, classification: Classification) -> Plan:
    if mode == "release":
        return Plan(mode, RELEASE_GATES)
    if mode == "live":
        return Plan(mode, ("live-acceptance",))

    gates = list(BASE_GATES[mode])
    if mode == "fast":
        for category in classification.categories:
            gates.extend(FAST_CATEGORY_GATES.get(category, ()))
        if classification.unknown_paths:
            gates.extend(FAST_FAIL_CLOSED_GATES)
    else:
        for category in classification.categories:
            gates.extend(RISK_GATES.get(category, ()))
        if classification.unknown_paths:
            gates.extend(ALL_RISK_GATES)
    return Plan(mode, tuple(dict.fromkeys(gates)))


def _payload(classification: Classification, plan: Plan) -> dict[str, Any]:
    return {
        "mode": plan.mode,
        "paths": [
            {
                "path": path,
                "sources": sorted(classification.changes.sources[path]),
            }
            for path in classification.changes.paths
        ],
        "categories": list(classification.categories),
        "unknown_paths": list(classification.unknown_paths),
        "fail_closed": bool(classification.unknown_paths),
        "gates": list(plan.gates),
    }


def _is_clean(repository: Path) -> bool:
    return not _git(repository, "status", "--porcelain")


def _head(repository: Path) -> str:
    return _git(repository, "rev-parse", "HEAD")[0]


def _evidence_path(repository: Path, sha: str, gate: str) -> Path:
    return repository / ".cache" / "check-evidence" / sha / f"{gate}.json"


def _gate_fingerprint(gate: str) -> str:
    material = MATRIX_PATH.read_bytes() + Path(__file__).read_bytes() + gate.encode()
    return hashlib.sha256(material).hexdigest()


def _has_evidence(repository: Path, sha: str, gate: str) -> bool:
    path = _evidence_path(repository, sha, gate)
    if not path.exists():
        return False
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return (
        payload.get("sha") == sha
        and payload.get("gate") == gate
        and payload.get("status") == "passed"
        and payload.get("fingerprint") == _gate_fingerprint(gate)
    )


def _record_evidence(repository: Path, sha: str, gate: str) -> None:
    path = _evidence_path(repository, sha, gate)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "sha": sha,
                "gate": gate,
                "status": "passed",
                "fingerprint": _gate_fingerprint(gate),
                "finished_at": datetime.now(UTC).isoformat(),
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def _run_gate(repository: Path, gate: str, changes: ChangeSet) -> None:
    make_command = shlex.split(os.environ.get("CHECK_MAKE", "make"), posix=os.name != "nt")
    environment = os.environ.copy()
    environment["SRBG_CHANGED_PATHS"] = json.dumps(changes.paths)
    subprocess.run(  # noqa: S603
        [*make_command, gate],
        cwd=repository,
        check=True,
        env=environment,
    )


def execute(repository: Path, plan: Plan, classification: Classification) -> None:
    if plan.mode == "live" and os.environ.get("LIVE_CONFIRM") != "I_UNDERSTAND":
        raise SystemExit(
            "check-live requires LIVE_CONFIRM=I_UNDERSTAND; it may use real data, "
            "the full Docker stack and external sources"
        )
    if plan.mode == "release" and not _is_clean(repository):
        raise SystemExit("check-release requires a clean worktree for exact-SHA evidence")

    clean = _is_clean(repository)
    sha = _head(repository)
    for gate in plan.gates:
        if plan.mode == "release" and _has_evidence(repository, sha, gate):
            print(f"SKIP {gate}: exact-SHA evidence already passed")
            continue
        print(f"RUN {gate}")
        _run_gate(repository, gate, classification.changes)
        if clean:
            _record_evidence(repository, sha, gate)


def check_diffs(repository: Path, *, base_ref: str | None) -> None:
    """Run whitespace checks for committed, staged and unstaged tracked changes."""
    git = shutil.which("git")
    if git is None:
        raise RuntimeError("Git executable is required")
    resolved_base = resolve_base_ref(repository, explicit=base_ref)
    for arguments in (
        ("diff", "--check", f"{resolved_base}...HEAD"),
        ("diff", "--cached", "--check"),
        ("diff", "--check"),
    ):
        subprocess.run(  # noqa: S603
            [git, *arguments],
            cwd=repository,
            check=True,
        )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    classify = subparsers.add_parser("classify")
    classify.add_argument("--repository", type=Path, default=Path.cwd())
    classify.add_argument("--base-ref")
    classify.add_argument("--mode", choices=("fast", "pr", "release", "live"), required=True)
    classify.add_argument("--execute", action="store_true")

    diff_check = subparsers.add_parser("diff-check")
    diff_check.add_argument("--repository", type=Path, default=Path.cwd())
    diff_check.add_argument("--base-ref")

    paths = subparsers.add_parser("classify-paths")
    paths.add_argument("--mode", choices=("fast", "pr", "release", "live"), required=True)
    paths.add_argument("paths", nargs="+")
    return parser


def main(arguments: list[str] | None = None) -> int:
    namespace = _parser().parse_args(arguments)
    if namespace.command == "diff-check":
        check_diffs(namespace.repository.resolve(), base_ref=namespace.base_ref)
        return 0
    if namespace.command == "classify-paths":
        classification = classify_changes(ChangeSet.from_paths(namespace.paths))
        plan = plan_for_mode(namespace.mode, classification)
        print(json.dumps(_payload(classification, plan), sort_keys=True))
        return 0

    repository = namespace.repository.resolve()
    classification = classify_changes(
        collect_changes(repository, base_ref=namespace.base_ref)
    )
    plan = plan_for_mode(namespace.mode, classification)
    print(json.dumps(_payload(classification, plan), indent=2, sort_keys=True))
    if namespace.execute:
        execute(repository, plan, classification)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
