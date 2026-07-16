"""Environment-backed configuration with safe local defaults."""

from __future__ import annotations

from base64 import b64decode
from binascii import Error as BinasciiError
from datetime import UTC, datetime
from functools import lru_cache
from hashlib import sha256
from uuid import UUID

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
    openalex_api_key: SecretStr | None = None
    academic_contact: str = Field(default="data-platform@srbg.local", min_length=3, max_length=320)
    pgvector_recall_enabled: bool = False
    cursor_signing_key: SecretStr = Field(
        default_factory=lambda: SecretStr("demo-only-round10-cursor-signing-key")
    )
    semantic_search_enabled: bool = False
    semantic_search_timeout_seconds: float = Field(default=0.3, gt=0, le=2)
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
    round17_source_schedule_attestations: dict[
        str, tuple[StrictInt, StrictInt]
    ] | None = None
    round17_leo_approver_actor_id: UUID | None = None
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
        eventization_key_values = (
            self.round17_eventization_trusted_public_key_base64,
            self.round17_eventization_trusted_public_key_sha256,
        )
        if any(value is not None for value in eventization_key_values):
            if any(value is None for value in eventization_key_values):
                raise ValueError(
                    "Round 17 eventization trust key and fingerprint must be configured together"
                )
            try:
                public_key = b64decode(
                    str(self.round17_eventization_trusted_public_key_base64),
                    validate=True,
                )
            except (BinasciiError, ValueError) as error:
                raise ValueError("Round 17 eventization trust key is not valid base64") from error
            if len(public_key) != 32 or sha256(public_key).hexdigest() != str(
                self.round17_eventization_trusted_public_key_sha256
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
                    raise ValueError(
                        "Round 17 schedule interval seconds must be whole minutes"
                    )
                if not 60 <= freshness_slo_seconds <= 604_800:
                    raise ValueError(
                        "Round 17 schedule SLO seconds must be between 60 and 604800"
                    )
                if freshness_slo_seconds % 60:
                    raise ValueError("Round 17 schedule SLO seconds must be whole minutes")
            if (
                self.round17_roster_source_codes is not None
                and (
                    len(self.round17_roster_source_codes) != 20
                    or len(set(self.round17_roster_source_codes)) != 20
                    or set(schedule_attestations)
                    != set(self.round17_roster_source_codes)
                )
            ):
                raise ValueError(
                    "Round 17 schedule attestation must exactly match the roster"
                )
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
