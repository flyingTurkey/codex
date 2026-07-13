from __future__ import annotations

import pytest

from scripts.smoke import host_port


def test_host_port_uses_environment_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("API_PORT", "18000")

    assert host_port("API_PORT", 8000) == 18000


@pytest.mark.parametrize("value", ["0", "65536", "not-a-port"])
def test_host_port_rejects_invalid_values(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    monkeypatch.setenv("API_PORT", value)

    with pytest.raises(ValueError, match="API_PORT"):
        host_port("API_PORT", 8000)
