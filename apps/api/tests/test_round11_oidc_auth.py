from datetime import UTC, datetime, timedelta
from uuid import UUID

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm
from srbg_api.auth import decode_oidc_token
from srbg_api.config import Settings
from srbg_contracts import UserRole


def test_oidc_token_requires_approved_audience_issuer_roles_and_uuid7() -> None:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_jwk = RSAAlgorithm.to_jwk(key.public_key(), as_dict=True)
    public_jwk.update({'kid': 'round11-key', 'use': 'sig', 'alg': 'RS256'})
    now = datetime.now(UTC)
    user_id = UUID('019b0000-0000-7000-8000-000000000011')
    token = jwt.encode(
        {
            'iss': 'https://id.example.test',
            'aud': 'srbg-platform',
            'exp': now + timedelta(minutes=5),
            'iat': now,
            'srbg_user_id': str(user_id),
            'name': '内测用户',
            'roles': ['viewer', 'platform_admin'],
        },
        key,
        algorithm='RS256',
        headers={'kid': 'round11-key'},
    )
    settings = Settings(
        environment='test',
        oidc_issuer='https://id.example.test',
        oidc_audience='srbg-platform',
        oidc_jwks_url='https://id.example.test/.well-known/jwks.json',
    )
    principal = decode_oidc_token(token, {'keys': [public_jwk]}, settings)
    assert principal.user_id == user_id
    assert principal.roles == frozenset({UserRole.VIEWER, UserRole.PLATFORM_ADMIN})
    assert principal.local_identity is False


@pytest.mark.parametrize(
    ("claim", "value"),
    [
        ("iss", "https://wrong.example.test"),
        ("aud", "wrong-audience"),
        ("srbg_user_id", "019b0000-0000-6000-8000-000000000011"),
        ("roles", ["unknown-role"]),
    ],
)
def test_oidc_rejects_unapproved_identity_claims(claim: str, value: object) -> None:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_jwk = RSAAlgorithm.to_jwk(key.public_key(), as_dict=True)
    public_jwk.update({"kid": "round11-key", "use": "sig", "alg": "RS256"})
    now = datetime.now(UTC)
    claims: dict[str, object] = {
        "iss": "https://id.example.test",
        "aud": "srbg-platform",
        "exp": now + timedelta(minutes=5),
        "iat": now,
        "srbg_user_id": "019b0000-0000-7000-8000-000000000011",
        "roles": ["viewer"],
    }
    claims[claim] = value
    token = jwt.encode(
        claims,
        key,
        algorithm="RS256",
        headers={"kid": "round11-key"},
    )
    settings = Settings(
        environment="test",
        oidc_issuer="https://id.example.test",
        oidc_audience="srbg-platform",
        oidc_jwks_url="https://id.example.test/.well-known/jwks.json",
    )
    with pytest.raises((ValueError, jwt.PyJWTError)):
        decode_oidc_token(token, {"keys": [public_jwk]}, settings)


def test_oidc_rejects_unknown_key_and_non_rs256_algorithm() -> None:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    now = datetime.now(UTC)
    claims = {
        "iss": "https://id.example.test",
        "aud": "srbg-platform",
        "exp": now + timedelta(minutes=5),
        "iat": now,
        "srbg_user_id": "019b0000-0000-7000-8000-000000000011",
        "roles": ["viewer"],
    }
    token = jwt.encode(claims, key, algorithm="RS256", headers={"kid": "missing"})
    settings = Settings(
        environment="test",
        oidc_issuer="https://id.example.test",
        oidc_audience="srbg-platform",
        oidc_jwks_url="https://id.example.test/.well-known/jwks.json",
    )
    with pytest.raises(ValueError, match="no approved signing key"):
        decode_oidc_token(token, {"keys": []}, settings)
