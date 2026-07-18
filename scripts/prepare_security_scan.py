"""Stage Git-deliverable files for a deterministic Trivy filesystem scan."""

from __future__ import annotations

import json
import shutil
import subprocess
from collections.abc import Iterable
from pathlib import Path


def _is_inside(path: Path, parent: Path) -> bool:
    return path == parent or parent in path.parents


def prepare_scan_workspace(
    repository: Path,
    destination: Path,
    delivery_paths: Iterable[Path],
) -> int:
    """Copy declared repository files to a clean, repository-local scan directory."""
    repository = repository.resolve(strict=True)
    destination = destination.resolve(strict=False)
    if destination == repository or not _is_inside(destination, repository):
        raise ValueError("scan destination must be inside the repository")

    if destination.exists():
        shutil.rmtree(destination)
    destination.mkdir(parents=True)

    copied = 0
    for relative_path in delivery_paths:
        if relative_path.anchor or ".." in relative_path.parts:
            raise ValueError(f"delivery path escapes repository: {relative_path}")
        candidate = repository / relative_path
        # A staged deletion is part of the Git delivery set but has no bytes to
        # scan. Its prior content must not make retirement gates fail.
        if not candidate.exists():
            continue
        source = candidate.resolve(strict=True)
        if not _is_inside(source, repository) or not source.is_file():
            raise ValueError(f"delivery path is not a repository file: {relative_path}")
        target = destination / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        copied += 1
    return copied


def git_delivery_paths(repository: Path) -> tuple[Path, ...]:
    """List tracked and unignored untracked files that could be committed."""
    git_executable = shutil.which("git")
    if git_executable is None:
        raise RuntimeError("Git executable is required to prepare the security scan")
    # The executable is resolved to an absolute path and every argument is constant.
    result = subprocess.run(  # noqa: S603
        [
            git_executable,
            "ls-files",
            "--cached",
            "--others",
            "--exclude-standard",
            "-z",
        ],
        cwd=repository,
        check=True,
        stdout=subprocess.PIPE,
    )
    return tuple(
        Path(item.decode("utf-8"))
        for item in result.stdout.split(b"\0")
        if item
    )


def main() -> None:
    repository = Path(__file__).resolve().parents[1]
    destination = repository / ".cache" / "trivy-input"
    copied = prepare_scan_workspace(
        repository,
        destination,
        git_delivery_paths(repository),
    )
    print(json.dumps({"destination": str(destination), "files": copied}))


if __name__ == "__main__":
    main()
