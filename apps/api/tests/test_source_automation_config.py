import pytest
from pydantic import SecretStr, ValidationError
from srbg_api.config import Settings


def test_search_discovery_is_disabled_by_default_and_budget_is_exact_integer_micrormb() -> None:
    settings = Settings()

    assert settings.source_discovery_enabled is False
    assert settings.source_qualification_enabled is False
    assert settings.baidu_search_enabled is False
    assert settings.baidu_search_api_key is None
    assert settings.baidu_search_monthly_cap_micrormb == 200_000_000
    assert settings.baidu_search_cost_per_call_micrormb == 36_000
    assert settings.baidu_search_free_calls_per_month == 1_500
    assert settings.baidu_search_budget_alert_bps == 8_000


def test_enabling_baidu_without_secret_or_with_untrusted_endpoint_fails_closed() -> None:
    with pytest.raises(ValidationError, match="API key"):
        Settings(baidu_search_enabled=True)

    with pytest.raises(ValidationError, match="API key"):
        Settings(baidu_search_enabled=True, baidu_search_api_key=SecretStr(""))

    with pytest.raises(ValidationError, match="source discovery"):
        Settings(
            baidu_search_enabled=True,
            baidu_search_api_key=SecretStr("not-logged-secret"),
            source_qualification_enabled=True,
        )

    with pytest.raises(ValidationError, match="endpoint"):
        Settings(
            baidu_search_enabled=True,
            baidu_search_api_key=SecretStr("not-logged-secret"),
            baidu_search_api_url="https://attacker.example/search",
            source_qualification_enabled=True,
        )

    with pytest.raises(ValidationError, match="endpoint"):
        Settings(
            baidu_search_enabled=True,
            baidu_search_api_key=SecretStr("not-logged-secret"),
            baidu_search_api_url="https://qianfan.baidubce.com/unapproved-path",
            source_qualification_enabled=True,
        )


def test_discovery_requires_qualification_but_qualification_can_run_independently() -> None:
    with pytest.raises(ValidationError, match="qualification"):
        Settings(source_discovery_enabled=True)

    settings = Settings(source_qualification_enabled=True)

    assert settings.source_qualification_enabled is True
    assert settings.source_discovery_enabled is False


def test_baidu_budget_authority_cannot_drift_from_database_pinned_policy() -> None:
    with pytest.raises(ValidationError, match="budget policy"):
        Settings(baidu_search_monthly_cap_micrormb=300_000_000)

    with pytest.raises(ValidationError, match="budget policy"):
        Settings(baidu_search_free_calls_per_month=2_000)
