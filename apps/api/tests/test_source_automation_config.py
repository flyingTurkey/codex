import pytest
from pydantic import SecretStr, ValidationError
from srbg_api.config import Settings


def test_free_discovery_is_enabled_by_default_and_baidu_is_opt_in() -> None:
    settings = Settings()

    assert settings.source_discovery_enabled is True
    assert not hasattr(settings, "source_qualification_enabled")
    assert settings.baidu_search_enabled is False
    assert settings.baidu_search_api_key is None
    assert settings.baidu_search_monthly_cap_micrormb == 200_000_000
    assert settings.baidu_search_cost_per_call_micrormb == 36_000
    assert settings.baidu_search_free_calls_per_month == 1_500
    assert settings.baidu_search_budget_alert_bps == 8_000


def test_baidu_without_secret_skips_search_but_endpoint_remains_pinned() -> None:
    assert Settings(baidu_search_enabled=True).baidu_search_api_key is None
    empty = Settings(baidu_search_enabled=True, baidu_search_api_key=SecretStr(""))
    assert empty.baidu_search_api_key is not None

    with pytest.raises(ValidationError, match="source discovery"):
        Settings(
            baidu_search_enabled=True,
            baidu_search_api_key=SecretStr("not-logged-secret"),
            source_discovery_enabled=False,
        )

    with pytest.raises(ValidationError, match="endpoint"):
        Settings(
            baidu_search_enabled=True,
            baidu_search_api_key=SecretStr("not-logged-secret"),
            baidu_search_api_url="https://attacker.example/search",
        )

    with pytest.raises(ValidationError, match="endpoint"):
        Settings(
            baidu_search_enabled=True,
            baidu_search_api_key=SecretStr("not-logged-secret"),
            baidu_search_api_url="https://qianfan.baidubce.com/unapproved-path",
        )


def test_personal_discovery_can_be_disabled_without_an_enterprise_qualification_toggle() -> None:
    settings = Settings(source_discovery_enabled=False)

    assert not hasattr(settings, "source_qualification_enabled")
    assert settings.source_discovery_enabled is False


def test_baidu_budget_authority_cannot_drift_from_database_pinned_policy() -> None:
    with pytest.raises(ValidationError, match="budget policy"):
        Settings(baidu_search_monthly_cap_micrormb=300_000_000)

    with pytest.raises(ValidationError, match="budget policy"):
        Settings(baidu_search_free_calls_per_month=2_000)
