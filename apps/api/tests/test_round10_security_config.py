from __future__ import annotations

import pytest
from pydantic import SecretStr, ValidationError
from srbg_api.config import Settings


def test_production_rejects_demo_cursor_signing_key() -> None:
    with pytest.raises(ValidationError, match="cursor signing key"):
        Settings(environment="production")


def test_production_accepts_an_explicit_high_entropy_cursor_signing_key() -> None:
    settings = Settings(
        environment="production",
        cursor_signing_key=SecretStr("9d4a4b4dafde2f7ab473d7732aa31f796aa76dde95e90f22"),
    )

    assert len(settings.cursor_signing_key.get_secret_value()) >= 48
