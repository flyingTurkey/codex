import pytest
from pydantic import SecretStr, ValidationError
from srbg_api.config import Settings


def _settings(**values: object) -> Settings:
    return Settings(_env_file=None, **values)  # type: ignore[call-arg,arg-type]


def test_free_discovery_is_enabled_by_default_and_baidu_is_opt_in() -> None:
    settings = _settings()

    assert settings.source_discovery_enabled is True
    assert not hasattr(settings, "source_qualification_enabled")
    assert settings.baidu_search_enabled is False
    assert settings.baidu_search_api_key is None
    assert settings.baidu_search_monthly_cap_micrormb == 200_000_000
    assert settings.baidu_search_cost_per_call_micrormb == 36_000
    assert settings.baidu_search_free_calls_per_month == 1_500
    assert settings.baidu_search_budget_alert_bps == 8_000


def test_acquisition_uses_one_platform_level_authenticated_doh_resolver() -> None:
    settings = _settings()

    assert settings.acquisition_doh_url == "https://dns.alidns.com/dns-query"
    assert settings.acquisition_doh_bootstrap_address == "223.5.5.5"

    with pytest.raises(ValidationError, match="trusted DNS endpoint"):
        _settings(acquisition_doh_url="http://dns.example.test/dns-query")
    with pytest.raises(ValidationError, match="trusted DNS endpoint"):
        _settings(acquisition_doh_url="https://dns.example.test/dns-query?name=source")
    with pytest.raises(ValidationError, match="bootstrap"):
        _settings(acquisition_doh_bootstrap_address="127.0.0.1")


def test_acquisition_proxy_is_explicit_optional_and_loopback_only() -> None:
    assert _settings().acquisition_socks5_proxy_url is None
    assert _settings(acquisition_socks5_proxy_url="").acquisition_socks5_proxy_url is None
    assert (
        _settings(
            acquisition_socks5_proxy_url="socks5://127.0.0.1:7890"
        ).acquisition_socks5_proxy_url
        == "socks5://127.0.0.1:7890"
    )
    assert (
        _settings(
            acquisition_socks5_proxy_url="socks5://host.docker.internal:7890"
        ).acquisition_socks5_proxy_url
        == "socks5://host.docker.internal:7890"
    )

    with pytest.raises(ValidationError, match="loopback SOCKS5"):
        _settings(acquisition_socks5_proxy_url="socks5://proxy.example.test:7890")
    with pytest.raises(ValidationError, match="loopback SOCKS5"):
        _settings(acquisition_socks5_proxy_url="socks5://user:secret@127.0.0.1:7890")


def test_baidu_without_secret_skips_search_but_endpoint_remains_pinned() -> None:
    assert _settings(baidu_search_enabled=True).baidu_search_api_key is None
    empty = _settings(baidu_search_enabled=True, baidu_search_api_key=SecretStr(""))
    assert empty.baidu_search_api_key is not None

    with pytest.raises(ValidationError, match="source discovery"):
        _settings(
            baidu_search_enabled=True,
            baidu_search_api_key=SecretStr("not-logged-secret"),
            source_discovery_enabled=False,
        )

    with pytest.raises(ValidationError, match="endpoint"):
        _settings(
            baidu_search_enabled=True,
            baidu_search_api_key=SecretStr("not-logged-secret"),
            baidu_search_api_url="https://attacker.example/search",
        )

    with pytest.raises(ValidationError, match="endpoint"):
        _settings(
            baidu_search_enabled=True,
            baidu_search_api_key=SecretStr("not-logged-secret"),
            baidu_search_api_url="https://qianfan.baidubce.com/unapproved-path",
        )


def test_personal_discovery_can_be_disabled_without_an_enterprise_qualification_toggle() -> None:
    settings = _settings(source_discovery_enabled=False)

    assert not hasattr(settings, "source_qualification_enabled")
    assert settings.source_discovery_enabled is False


def test_baidu_budget_authority_cannot_drift_from_database_pinned_policy() -> None:
    with pytest.raises(ValidationError, match="budget policy"):
        _settings(baidu_search_monthly_cap_micrormb=300_000_000)

    with pytest.raises(ValidationError, match="budget policy"):
        _settings(baidu_search_free_calls_per_month=2_000)
