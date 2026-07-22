from __future__ import annotations

import pytest

from scripts.smoke import (
    CURRENT_FEED_PATH,
    host_port,
    validate_homepage_contract,
    validate_version_contract,
)


def test_smoke_targets_the_current_v2_feed() -> None:
    assert CURRENT_FEED_PATH == "/api/v2/feed?limit=1"


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


def test_smoke_accepts_the_current_complete_version_contract() -> None:
    validate_version_contract(
        {
            "api_version": "v1",
            "content_schema_version": "1.1.0",
            "search_schema_version": "1.0.0",
            "semantic_search_enabled": False,
        }
    )


def test_smoke_rejects_an_incomplete_version_contract() -> None:
    with pytest.raises(RuntimeError, match="version contract"):
        validate_version_contract(
            {
                "api_version": "v1",
                "content_schema_version": "1.1.0",
            }
        )


def test_smoke_requires_the_empty_state_when_the_feed_is_empty() -> None:
    validate_homepage_contract(
        "四川路桥 智安情报 业务数据尚未接入",
        {"items": []},
    )

    with pytest.raises(RuntimeError, match="empty state"):
        validate_homepage_contract("四川路桥 智安情报", {"items": []})


def test_smoke_accepts_a_populated_feed_without_the_empty_state() -> None:
    validate_homepage_contract(
        "四川路桥 智安情报",
        {"items": [{"id": "test-only-item"}]},
    )
