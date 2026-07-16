from pathlib import Path

SCRIPT = Path("scripts/round17_install_approval.py")


def test_install_approval_is_atomic_fail_closed_and_does_not_print_secrets() -> None:
    source = SCRIPT.read_text(encoding="utf-8")

    assert "0017c_round17_flat_pilot" in source
    assert "_round17_signed_approval_is_trusted" in source
    assert "INSERT INTO round17_staff_binding" in source
    assert "INSERT INTO round17_signed_approval" in source
    assert "INSERT INTO source" in source
    assert "NRA-001" in source
    assert "ROUND17_SIGNED_ROSTER_SOURCE_REGISTERED" in source
    assert "lifecycle_state" in source
    assert "'CANDIDATE'" in source
    assert "enabled" in source
    assert "false" in source
    assert "ROUND17_SIGNED_ROSTER_INCOMPLETE" in source
    assert source.index("ROUND17_ATOMIC_AUTHORITY_INSTALLED") < source.index(
        "ROUND17_SIGNED_ROSTER_SOURCE_REGISTERED"
    )
    assert "async with engine.begin()" in source
    assert "ON CONFLICT DO NOTHING" not in source
    assert "private_key" not in source
    assert "approval_signature" not in source.split("def main", 1)[-1]
