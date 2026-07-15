"""Environment-backed configuration with safe local defaults."""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field, SecretStr, model_validator
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

    @model_validator(mode="after")
    def reject_demo_cursor_key_in_production(self) -> Settings:
        key = self.cursor_signing_key.get_secret_value()
        if self.environment.lower() == "production" and (
            key.startswith("demo-only-") or len(key) < 48
        ):
            raise ValueError(
                "production cursor signing key must be explicit and at least 48 characters"
            )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
