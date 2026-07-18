from pathlib import Path


def test_fontless_esbuild_is_pinned_to_the_patched_windows_dev_server_release() -> None:
    workspace = Path("pnpm-workspace.yaml").read_text(encoding="utf-8")
    assert "fontless>esbuild: 0.28.1" in workspace

    lock = Path("pnpm-lock.yaml").read_text(encoding="utf-8")
    assert "fontless>esbuild: 0.28.1" in lock
