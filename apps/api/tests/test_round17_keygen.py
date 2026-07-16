from __future__ import annotations

from pathlib import Path

from scripts.round17_keygen import configure_signed_local_pilot


def test_keygen_preserves_existing_env_and_never_returns_private_material(
    tmp_path: Path,
) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text("EXISTING=value\n", encoding="utf-8")

    result = configure_signed_local_pilot(env_path)
    content = env_path.read_text(encoding="utf-8")

    assert "EXISTING=value" in content
    assert "SRBG_ENVIRONMENT=test" in content
    assert "SRBG_ROUND17_AUTHORITY_MODE=SIGNED_LOCAL_PILOT" in content
    assert (
        "SRBG_ROUND17_LEO_APPROVER_ACTOR_ID="
        "019f6b65-4cf5-71d1-b75c-a6c908912f58"
    ) in content
    assert "SRBG_ROUND17_LEO_SIGNING_PRIVATE_KEY_BASE64=" in content
    assert result == {
        "public_key_sha256": next(
            line.split("=", 1)[1]
            for line in content.splitlines()
            if line.startswith("SRBG_ROUND17_LEO_SIGNING_PUBLIC_KEY_SHA256=")
        )
    }
    assert "private" not in " ".join(result).lower()


def test_keygen_rotates_all_coupled_key_fields_atomically(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text(
        "SRBG_ROUND17_LEO_SIGNING_PRIVATE_KEY_BASE64=stale\n"
        "SRBG_ROUND17_LEO_SIGNING_PUBLIC_KEY_BASE64=stale\n"
        "SRBG_ROUND17_LEO_SIGNING_PUBLIC_KEY_SHA256=stale\n",
        encoding="utf-8",
    )

    configure_signed_local_pilot(env_path)

    lines = env_path.read_text(encoding="utf-8").splitlines()
    assert (
        sum(
            line.startswith("SRBG_ROUND17_LEO_SIGNING_PRIVATE_KEY_BASE64=")
            for line in lines
        )
        == 1
    )
    assert (
        sum(
            line.startswith("SRBG_ROUND17_LEO_SIGNING_PUBLIC_KEY_BASE64=")
            for line in lines
        )
        == 1
    )
    assert sum(
        line.startswith("SRBG_ROUND17_LEO_SIGNING_PUBLIC_KEY_SHA256=") for line in lines
    ) == 1
