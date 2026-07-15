import logging
from datetime import UTC, datetime, timedelta
from uuid import UUID

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException
from jwt.algorithms import RSAAlgorithm
from srbg_api.auth import (
    Principal,
    decode_oidc_token,
    principal_has_step_up,
    require_roles,
)
from srbg_api.config import Settings
from srbg_contracts import UserRole


def _identity(
    *, nbf: datetime, auth_time: datetime, amr: list[str]
) -> tuple[str, dict[str, object], Settings]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwk = RSAAlgorithm.to_jwk(key.public_key(), as_dict=True)
    jwk.update({"kid": "round13", "use": "sig", "alg": "RS256"})
    now = datetime.now(UTC)
    token = jwt.encode(
        {
            "iss": "https://id.example.test",
            "aud": "srbg-platform",
            "exp": now + timedelta(minutes=5),
            "nbf": nbf,
            "iat": now,
            "auth_time": int(auth_time.timestamp()),
            "acr": "urn:srbg:mfa",
            "amr": amr,
            "srbg_user_id": str(UUID("019b0000-0000-7000-8000-000000001313")),
            "roles": ["reviewer"],
        },
        key,
        algorithm="RS256",
        headers={"kid": "round13"},
    )
    settings = Settings(
        environment="test",
        oidc_issuer="https://id.example.test",
        oidc_audience="srbg-platform",
        oidc_jwks_url="https://id.example.test/jwks",
        oidc_step_up_acr_values=["urn:srbg:mfa"],
    )
    return token, {"keys": [jwk]}, settings


def test_step_up_requires_mfa_and_fresh_authentication() -> None:
    now = datetime.now(UTC)
    token, jwks, settings = _identity(
        nbf=now - timedelta(seconds=1), auth_time=now, amr=["pwd", "mfa"]
    )
    principal = decode_oidc_token(token, jwks, settings)
    assert principal_has_step_up(principal, settings, now=now)


def test_oidc_requires_nbf_and_rejects_future_tokens() -> None:
    now = datetime.now(UTC)
    token, jwks, settings = _identity(nbf=now + timedelta(minutes=2), auth_time=now, amr=["mfa"])
    with pytest.raises(jwt.PyJWTError):
        decode_oidc_token(token, jwks, settings)


@pytest.mark.asyncio
async def test_role_denial_emits_privacy_safe_structured_log(
    caplog: pytest.LogCaptureFixture,
) -> None:
    principal = Principal(
        user_id=UUID("019b0000-0000-7000-8000-000000001399"),
        display_name="viewer",
        roles=frozenset({UserRole.VIEWER}),
        local_identity=False,
    )
    authorize = require_roles(UserRole.REVIEWER)

    with caplog.at_level(logging.WARNING, logger="srbg.auth"), pytest.raises(HTTPException):
        await authorize(principal)

    record = next(record for record in caplog.records if record.message == "authorization_denied")
    assert record.reason == "role"
    assert not hasattr(record, "user_id")
