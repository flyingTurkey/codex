from __future__ import annotations

import pytest
from pydantic import SecretStr, ValidationError
from srbg_api.config import Settings


def test_production_rejects_demo_cursor_signing_key() -> None:
    with pytest.raises(ValidationError, match="cursor signing key"):
        Settings(environment="production", _env_file=None)


def test_production_accepts_an_explicit_high_entropy_cursor_signing_key() -> None:
    settings = Settings(
        _env_file=None,
        environment="production",
        cursor_signing_key=SecretStr("9d4a4b4dafde2f7ab473d7732aa31f796aa76dde95e90f22"),
        metrics_bearer_token=SecretStr("m" * 32),
        otel_exporter_otlp_endpoint="https://otel.example.test",
        sentry_dsn=SecretStr("https://public@example.test/1"),
        oidc_issuer="https://id.example.test",
        oidc_audience="srbg-platform",
        oidc_jwks_url="https://id.example.test/.well-known/jwks.json",
        alert_webhook_url=SecretStr("https://alerts.example.test/hook"),
        backup_s3_endpoint_url="https://backup.example.test",
        backup_s3_bucket="srbg-production-backup",
        backup_s3_access_key="access-from-secret-manager",
        backup_s3_secret_key=SecretStr("secret-from-secret-manager"),
    )

    assert len(settings.cursor_signing_key.get_secret_value()) >= 48
