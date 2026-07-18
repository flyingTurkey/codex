from pathlib import Path

import pytest

from scripts.prepare_security_scan import git_delivery_paths, prepare_scan_workspace


def test_prepare_scan_workspace_copies_only_declared_delivery_files(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    (repository / "tracked.txt").write_text("tracked", encoding="utf-8")
    (repository / "nested").mkdir()
    (repository / "nested" / "new.bin").write_bytes(b"new")
    destination = repository / ".cache" / "trivy-input"
    destination.mkdir(parents=True)
    (destination / "stale.txt").write_text("stale", encoding="utf-8")

    copied = prepare_scan_workspace(
        repository,
        destination,
        (Path("tracked.txt"), Path("nested/new.bin")),
    )

    assert copied == 2
    assert (destination / "tracked.txt").read_text(encoding="utf-8") == "tracked"
    assert (destination / "nested" / "new.bin").read_bytes() == b"new"
    assert not (destination / "stale.txt").exists()


def test_prepare_scan_workspace_ignores_tracked_files_deleted_by_delivery(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    destination = repository / ".cache" / "scan"

    assert prepare_scan_workspace(repository, destination, (Path("retired.py"),)) == 0
    assert list(destination.iterdir()) == []


@pytest.mark.parametrize("unsafe_path", [Path("../outside.txt"), Path("/absolute.txt")])
def test_prepare_scan_workspace_rejects_paths_outside_repository(
    tmp_path: Path,
    unsafe_path: Path,
) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    destination = repository / ".cache" / "trivy-input"

    with pytest.raises(ValueError, match="delivery path"):
        prepare_scan_workspace(repository, destination, (unsafe_path,))


def test_prepare_scan_workspace_requires_destination_inside_repository(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()

    with pytest.raises(ValueError, match="scan destination"):
        prepare_scan_workspace(repository, tmp_path / "outside", ())


def test_git_delivery_paths_fails_clearly_when_git_is_unavailable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("scripts.prepare_security_scan.shutil.which", lambda _: None)

    with pytest.raises(RuntimeError, match="Git executable"):
        git_delivery_paths(tmp_path)
