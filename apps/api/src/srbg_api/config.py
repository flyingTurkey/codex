"""Environment-backed configuration with safe local defaults."""

from __future__ import annotations

from base64 import b64decode
from binascii import Error as BinasciiError
from datetime import UTC, datetime
from functools import lru_cache
from hashlib import sha256
from pathlib import Path
from urllib.parse import urlsplit
from uuid import UUID

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from pydantic import Field, SecretStr, StrictInt, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="SRBG_",
        extra="ignore",
    )

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
    pdf_max_page_pixels: int = Field(default=40_000_000, ge=1)
    pdf_parser_timeout_seconds: float = Field(default=120.0, gt=0, le=600)
    ocr_timeout_seconds: float = Field(default=30.0, gt=0, le=300)
    external_io_timeout_seconds: float = Field(default=2.0, gt=0, le=30)
    ai_secret_dir: Path = Path(".secrets/ai")
    openalex_api_key: SecretStr | None = None
    academic_contact: str = Field(default="data-platform@srbg.local", min_length=3, max_length=320)
    pgvector_recall_enabled: bool = False
    cursor_signing_key: SecretStr = Field(
        default_factory=lambda: SecretStr("demo-only-round10-cursor-signing-key")
    )
    semantic_search_enabled: bool = False
    semantic_search_timeout_seconds: float = Field(default=0.3, gt=0, le=2)
    source_discovery_enabled: bool = False
    source_qualification_enabled: bool = False
    baidu_search_enabled: bool = False
    baidu_search_api_url: str = "https://qianfan.baidubce.com/v2/ai_search"
    baidu_search_api_key: SecretStr | None = None
    baidu_search_timeout_seconds: float = Field(default=2.0, gt=0, le=10)
    baidu_search_monthly_cap_micrormb: int = Field(default=200_000_000, ge=1, le=10_000_000_000)
    baidu_search_cost_per_call_micrormb: int = Field(default=36_000, ge=0, le=10_000_000)
    baidu_search_free_calls_per_month: int = Field(default=1_500, ge=0, le=1_000_000)
    baidu_search_budget_alert_bps: int = Field(default=8_000, ge=1, le=9_999)
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
    round17_baseline_commit_attestation: str | None = None
    round17_config_version_attestation: str | None = None
    round17_roster_source_codes: list[str] | None = None
    round17_source_schedule_attestations: dict[str, tuple[StrictInt, StrictInt]] | None = None
    round17_leo_approver_actor_id: UUID | None = None
    round17_authority_mode: str = "OIDC"
    round17_leo_signing_private_key_base64: SecretStr | None = None
    round17_leo_signing_public_key_base64: str | None = None
    round17_leo_signing_public_key_sha256: str | None = None
    round17_eventization_trusted_public_key_base64: str | None = None
    round17_eventization_trusted_public_key_sha256: str | None = None
    backup_s3_endpoint_url: str | None = None
    backup_s3_bucket: str | None = None
    backup_s3_access_key: str | None = None
    backup_s3_secret_key: SecretStr | None = None
    item_api_deprecation_at: datetime = datetime(2026, 7, 15, tzinfo=UTC)
    item_api_sunset_at: datetime | None = None

    @model_validator(mode="after")
    def reject_demo_cursor_key_in_production(self) -> Settings:
        baidu_endpoint = urlsplit(self.baidu_search_api_url)
        if (
            baidu_endpoint.scheme != "https"
            or baidu_endpoint.hostname != "qianfan.baidubce.com"
            or baidu_endpoint.path != "/v2/ai_search"
            or baidu_endpoint.port is not None
            or baidu_endpoint.username is not None
            or baidu_endpoint.password is not None
            or baidu_endpoint.query
            or baidu_endpoint.fragment
        ):
            raise ValueError("Baidu search endpoint must use the pinned Qianfan HTTPS origin")
        baidu_api_key = self.baidu_search_api_key
        if self.baidu_search_enabled and (
            baidu_api_key is None or not baidu_api_key.get_secret_value()
        ):
            raise ValueError("Baidu search requires an API key when enabled")
        if self.baidu_search_enabled and not self.source_discovery_enabled:
            raise ValueError("Baidu search requires automated source discovery to be enabled")
        if self.source_discovery_enabled and not self.source_qualification_enabled:
            raise ValueError(
                "Automated source discovery requires source qualification to be enabled"
            )
        if (
            self.baidu_search_monthly_cap_micrormb,
            self.baidu_search_cost_per_call_micrormb,
            self.baidu_search_free_calls_per_month,
            self.baidu_search_budget_alert_bps,
        ) != (200_000_000, 36_000, 1_500, 8_000):
            raise ValueError("Baidu search budget policy is database-pinned")
        if self.baidu_search_cost_per_call_micrormb > self.baidu_search_monthly_cap_micrormb:
            raise ValueError("Baidu search per-call cost cannot exceed the monthly cap")
        if self.round17_authority_mode not in {"OIDC", "SIGNED_LOCAL_PILOT"}:
            raise ValueError("Round 17 authority mode is invalid")
        signing_values = (
            self.round17_leo_signing_private_key_base64,
            self.round17_leo_signing_public_key_base64,
            self.round17_leo_signing_public_key_sha256,
        )
        if self.round17_authority_mode == "SIGNED_LOCAL_PILOT":
            if self.environment.lower() != "test":
                raise ValueError("SIGNED_LOCAL_PILOT is permitted in test environments only")
            if self.round17_leo_approver_actor_id is None:
                raise ValueError("SIGNED_LOCAL_PILOT requires the frozen LEO actor")
            if any(value is None for value in signing_values):
                raise ValueError("SIGNED_LOCAL_PILOT requires a complete Ed25519 key pair")
            private_key = self.round17_leo_signing_private_key_base64
            public_key = self.round17_leo_signing_public_key_base64
            public_key_sha256 = self.round17_leo_signing_public_key_sha256
            if private_key is None or public_key is None or public_key_sha256 is None:
                raise ValueError("SIGNED_LOCAL_PILOT requires a complete Ed25519 key pair")
            try:
                private_bytes = b64decode(
                    private_key.get_secret_value(),
                    validate=True,
                )
                public_bytes = b64decode(public_key, validate=True)
                derived_public = (
                    Ed25519PrivateKey.from_private_bytes(private_bytes)
                    .public_key()
                    .public_bytes(
                        serialization.Encoding.Raw,
                        serialization.PublicFormat.Raw,
                    )
                )
            except (BinasciiError, ValueError) as error:
                raise ValueError("SIGNED_LOCAL_PILOT key material is invalid") from error
            if (
                len(private_bytes) != 32
                or len(public_bytes) != 32
                or derived_public != public_bytes
                or sha256(public_bytes).hexdigest() != public_key_sha256
            ):
                raise ValueError("SIGNED_LOCAL_PILOT key pair mismatch")
        elif any(value is not None for value in signing_values):
            raise ValueError("Round 17 local signing keys require SIGNED_LOCAL_PILOT mode")
        eventization_key_values = (
            self.round17_eventization_trusted_public_key_base64,
            self.round17_eventization_trusted_public_key_sha256,
        )
        if any(value is not None for value in eventization_key_values):
            if any(value is None for value in eventization_key_values):
                raise ValueError(
                    "Round 17 eventization trust key and fingerprint must be configured together"
                )
            eventization_public_key = self.round17_eventization_trusted_public_key_base64
            eventization_public_key_sha256 = self.round17_eventization_trusted_public_key_sha256
            if eventization_public_key is None or eventization_public_key_sha256 is None:
                raise ValueError(
                    "Round 17 eventization trust key and fingerprint must be configured together"
                )
            try:
                eventization_public_bytes = b64decode(eventization_public_key, validate=True)
            except (BinasciiError, ValueError) as error:
                raise ValueError("Round 17 eventization trust key is not valid base64") from error
            if (
                len(eventization_public_bytes) != 32
                or sha256(eventization_public_bytes).hexdigest() != eventization_public_key_sha256
            ):
                raise ValueError("Round 17 eventization trust key fingerprint mismatch")
        if (
            self.round17_leo_approver_actor_id is not None
            and self.round17_leo_approver_actor_id.version != 7
        ):
            raise ValueError("Round 17 LEO actor must be UUIDv7")
        schedule_attestations = self.round17_source_schedule_attestations
        if schedule_attestations is not None:
            if len(schedule_attestations) != 20:
                raise ValueError(
                    "Round 17 schedule attestation requires exactly 20 source schedules"
                )
            if any(not code or code.strip() != code for code in schedule_attestations):
                raise ValueError("Round 17 schedule attestation source codes are invalid")
            for interval_seconds, freshness_slo_seconds in schedule_attestations.values():
                if not 60 <= interval_seconds <= 604_800:
                    raise ValueError(
                        "Round 17 schedule interval seconds must be between 60 and 604800"
                    )
                if interval_seconds % 60:
                    raise ValueError("Round 17 schedule interval seconds must be whole minutes")
                if not 60 <= freshness_slo_seconds <= 604_800:
                    raise ValueError("Round 17 schedule SLO seconds must be between 60 and 604800")
                if freshness_slo_seconds % 60:
                    raise ValueError("Round 17 schedule SLO seconds must be whole minutes")
            if self.round17_roster_source_codes is not None and (
                len(self.round17_roster_source_codes) != 20
                or len(set(self.round17_roster_source_codes)) != 20
                or set(schedule_attestations) != set(self.round17_roster_source_codes)
            ):
                raise ValueError("Round 17 schedule attestation must exactly match the roster")
        if any("*" in origin for origin in self.cors_allowed_origins):
            raise ValueError("CORS origins must be an exact allowlist without wildcards")
        key = self.cursor_signing_key.get_secret_value()
        if self.environment.lower() == "production" and (
            key.startswith("demo-only-") or len(key) < 48
        ):
            raise ValueError(
                "production cursor signing key must be explicit and at least 48 characters"
            )
        controlled = self.environment.lower() in {
            "staging",
            "preproduction",
            "production",
        }
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
            missing = sorted(name for name, value in required.items() if value is None)
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
