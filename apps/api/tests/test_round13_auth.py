from datetime import UTC, datetime, timedelta
from uuid import UUID

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm
from srbg_api.auth import decode_oidc_token, principal_has_step_up
from srbg_api.config import Settings


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
