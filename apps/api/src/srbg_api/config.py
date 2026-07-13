"""Environment-backed configuration with safe local defaults."""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="SRBG_",
        extra="ignore",
    )

    environment: str = "demo"
    database_url: str = "postgresql+asyncpg://srbg:srbg_demo@postgres:5432/srbg"
    redis_url: str = "redis://redis:6379/0"
    s3_endpoint_url: str = "http://minio:9000"
    s3_access_key: str = "srbg_demo"
    s3_secret_key: str = Field(default_factory=lambda: "development-only")
    s3_bucket: str = "srbg-raw"
    s3_region: str = "us-east-1"
    external_io_timeout_seconds: float = Field(default=2.0, gt=0, le=30)


@lru_cache
def get_settings() -> Settings:
    return Settings()
