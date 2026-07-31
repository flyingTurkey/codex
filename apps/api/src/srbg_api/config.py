"""Environment-backed configuration with safe local defaults."""

from __future__ import annotations

import ipaddress
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="SRBG_", extra="ignore")
    environment: str = "demo"
    database_url: str = "postgresql+asyncpg://srbg:srbg_demo@postgres:5432/srbg"
    publication_database_url: str = (
        "postgresql+asyncpg://srbg_publisher_login:development-only@postgres:5432/srbg"
    )
    projection_database_url: str = (
        "postgresql+asyncpg://srbg_projection_reader_login:development-only@postgres:5432/srbg"
    )
    redis_url: str = "redis://redis:6379/0"
    s3_endpoint_url: str = "http://minio:9000"
    s3_access_key: str = "srbg_demo"
    s3_secret_key: str = Field(default_factory=lambda: "development-only")
    s3_bucket: str = "srbg-raw"
    s3_region: str = "us-east-1"
    clamav_host: str = "clamav"
    clamav_port: int = Field(default=3310, ge=1, le=65535)
    fixture_max_bytes: int = Field(default=50 * 1024 * 1024, ge=1)
    fixture_max_pdf_pages: int = Field(default=1000, ge=1, le=10000)
    pdf_max_ocr_pages: int = Field(default=200, ge=1, le=1000)
    attachment_max_entries: int = Field(default=100, ge=1, le=1000)
    attachment_max_uncompressed_bytes: int = Field(default=200 * 1024 * 1024, ge=1)
    attachment_max_compression_ratio: int = Field(default=100, ge=1, le=10000)
    pdf_max_page_pixels: int = Field(default=40000000, ge=1)
    pdf_parser_timeout_seconds: float = Field(default=120.0, gt=0, le=600)
    ocr_timeout_seconds: float = Field(default=30.0, gt=0, le=300)
    external_io_timeout_seconds: float = Field(default=2.0, gt=0, le=30)
    acquisition_doh_url: str = "https://dns.alidns.com/dns-query"
    acquisition_doh_bootstrap_address: str = "223.5.5.5"
    acquisition_socks5_proxy_url: str | None = None
    ai_secret_dir: Path = Path(".secrets/ai")
    openalex_api_key: SecretStr | None = None
    academic_contact: str = Field(default="data-platform@srbg.local", min_length=3, max_length=320)
    pgvector_recall_enabled: bool = False
    cursor_signing_key: SecretStr = Field(
        default_factory=lambda: SecretStr("demo-only-round10-cursor-signing-key")
    )
    semantic_search_enabled: bool = False
    semantic_search_timeout_seconds: float = Field(default=0.3, gt=0, le=2)
    source_discovery_enabled: bool = True
    baidu_search_enabled: bool = False
    baidu_search_api_url: str = "https://qianfan.baidubce.com/v2/ai_search"
    baidu_search_api_key: SecretStr | None = None
    baidu_search_timeout_seconds: float = Field(default=2.0, gt=0, le=10)
    baidu_search_monthly_cap_micrormb: int = Field(default=200000000, ge=1, le=10000000000)
    baidu_search_cost_per_call_micrormb: int = Field(default=36000, ge=0, le=10000000)
    baidu_search_free_calls_per_month: int = Field(default=1500, ge=0, le=1000000)
    baidu_search_budget_alert_bps: int = Field(default=8000, ge=1, le=9999)
    metrics_bearer_token: SecretStr | None = None
    otel_exporter_otlp_endpoint: str | None = None
    sentry_dsn: SecretStr | None = None
    oidc_issuer: str | None = None
    oidc_audience: str | None = None
    oidc_jwks_url: str | None = None
    oidc_step_up_acr_values: list[str] = Field(default_factory=list)
    oidc_step_up_max_age_seconds: int = Field(default=900, ge=60, le=3600)
    cors_allowed_origins: list[str] = Field(default_factory=list)
    alert_webhook_url: SecretStr | None = None
    backup_s3_endpoint_url: str | None = None
    backup_s3_bucket: str | None = None
    backup_s3_access_key: str | None = None
    backup_s3_secret_key: SecretStr | None = None
    item_api_deprecation_at: datetime = datetime(2026, 7, 15, tzinfo=UTC)
    item_api_sunset_at: datetime | None = None

    @field_validator("acquisition_socks5_proxy_url", mode="before")
    @classmethod
    def empty_acquisition_proxy_is_disabled(cls, value: object) -> object:
        return None if value == "" else value

    @model_validator(mode="after")
    def reject_demo_cursor_key_in_production(self) -> Settings:
        doh_endpoint = urlsplit(self.acquisition_doh_url)
        if (
            doh_endpoint.scheme != "https"
            or doh_endpoint.hostname is None
            or doh_endpoint.path != "/dns-query"
            or doh_endpoint.port not in {None, 443}
            or doh_endpoint.username is not None
            or doh_endpoint.password is not None
            or doh_endpoint.query
            or doh_endpoint.fragment
        ):
            raise ValueError("trusted DNS endpoint must be an exact HTTPS /dns-query URL")
        try:
            doh_bootstrap = ipaddress.ip_address(self.acquisition_doh_bootstrap_address)
        except ValueError as error:
            raise ValueError("trusted DNS bootstrap address must be a public IP") from error
        if (
            not doh_bootstrap.is_global
            or doh_bootstrap.is_multicast
            or doh_bootstrap.is_reserved
        ):
            raise ValueError("trusted DNS bootstrap address must be a direct public IP")
        if self.acquisition_socks5_proxy_url is not None:
            try:
                proxy = urlsplit(self.acquisition_socks5_proxy_url)
                proxy_port = proxy.port
                proxy_hostname = (proxy.hostname or "").casefold()
                proxy_is_local = proxy_hostname == "host.docker.internal"
                if not proxy_is_local:
                    proxy_is_local = ipaddress.ip_address(proxy_hostname).is_loopback
            except ValueError as error:
                raise ValueError(
                    "acquisition proxy must be an exact loopback SOCKS5 URL or Docker host gateway"
                ) from error
            if (
                proxy.scheme != "socks5"
                or not proxy_is_local
                or proxy_port is None
                or proxy.username is not None
                or proxy.password is not None
                or proxy.path not in {"", "/"}
                or proxy.query
                or proxy.fragment
            ):
                raise ValueError(
                    "acquisition proxy must be an exact loopback SOCKS5 URL or Docker host gateway"
                )
        baidu_endpoint = urlsplit(self.baidu_search_api_url)
        if (
            baidu_endpoint.scheme != "https"
            or baidu_endpoint.hostname != "qianfan.baidubce.com"
            or baidu_endpoint.path != "/v2/ai_search"
            or (baidu_endpoint.port is not None)
            or (baidu_endpoint.username is not None)
            or (baidu_endpoint.password is not None)
            or baidu_endpoint.query
            or baidu_endpoint.fragment
        ):
            raise ValueError("Baidu search endpoint must use the pinned Qianfan HTTPS origin")
        if self.baidu_search_enabled and (not self.source_discovery_enabled):
            raise ValueError("Baidu search requires automated source discovery to be enabled")
        if (
            self.baidu_search_monthly_cap_micrormb,
            self.baidu_search_cost_per_call_micrormb,
            self.baidu_search_free_calls_per_month,
            self.baidu_search_budget_alert_bps,
        ) != (200000000, 36000, 1500, 8000):
            raise ValueError("Baidu search budget policy is database-pinned")
        if self.baidu_search_cost_per_call_micrormb > self.baidu_search_monthly_cap_micrormb:
            raise ValueError("Baidu search per-call cost cannot exceed the monthly cap")
        if any("*" in origin for origin in self.cors_allowed_origins):
            raise ValueError("CORS origins must be an exact allowlist without wildcards")
        key = self.cursor_signing_key.get_secret_value()
        if self.environment.lower() == "production" and (
            key.startswith("demo-only-") or len(key) < 48
        ):
            raise ValueError(
                "production cursor signing key must be explicit and at least 48 characters"
            )
        controlled = self.environment.lower() in {"staging", "preproduction", "production"}
        if controlled:
            oidc_values = (self.oidc_issuer, self.oidc_audience, self.oidc_jwks_url)
            if any(value is None for value in oidc_values):
                raise ValueError("controlled environments require complete OIDC configuration")
            if not str(self.oidc_issuer).startswith("https://") or not str(
                self.oidc_jwks_url
            ).startswith("https://"):
                raise ValueError("controlled environment OIDC endpoints must use HTTPS")
        if self.environment.lower() == "production":
            required = {
                "metrics_bearer_token": self.metrics_bearer_token,
                "otel_exporter_otlp_endpoint": self.otel_exporter_otlp_endpoint,
                "sentry_dsn": self.sentry_dsn,
                "oidc_issuer": self.oidc_issuer,
                "oidc_audience": self.oidc_audience,
                "oidc_jwks_url": self.oidc_jwks_url,
                "alert_webhook_url": self.alert_webhook_url,
                "backup_s3_endpoint_url": self.backup_s3_endpoint_url,
                "backup_s3_bucket": self.backup_s3_bucket,
                "backup_s3_access_key": self.backup_s3_access_key,
                "backup_s3_secret_key": self.backup_s3_secret_key,
            }
            missing = sorted((name for name, value in required.items() if value is None))
            if missing:
                raise ValueError(
                    f"production operations configuration missing: {', '.join(missing)}"
                )
            if self.backup_s3_endpoint_url == self.s3_endpoint_url:
                raise ValueError("production backup storage must use an independent endpoint")
            metrics_token = self.metrics_bearer_token
            metrics_value = metrics_token.get_secret_value() if metrics_token is not None else ""
            if len(metrics_value) < 32 or metrics_value.startswith("demo-only-"):
                raise ValueError("production metrics bearer token must be at least 32 characters")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
