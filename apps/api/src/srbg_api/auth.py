"""Fail-closed local and OIDC request identity with role authorization."""

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Annotated
from uuid import UUID

import httpx2 as httpx
import jwt
from fastapi import Depends, HTTPException, Request, status
from jwt import PyJWKSet
from srbg_contracts import UserRole

from srbg_api.config import Settings, get_settings

LOCAL_USER_ID = UUID("019b0000-0000-7000-8000-000000009001")
LOCAL_ENVIRONMENTS = frozenset({"demo", "development", "test"})


@dataclass(frozen=True, slots=True)
class Principal:
    user_id: UUID
    display_name: str
    roles: frozenset[UserRole]
    local_identity: bool


async def get_current_principal(request: Request) -> Principal:
    settings = get_settings()
    if settings.environment not in LOCAL_ENVIRONMENTS:
        principal = await _oidc_principal(request, settings)
        request.state.principal = principal
        return principal

    raw_roles = request.headers.get("X-SRBG-Local-Roles", UserRole.VIEWER.value)
    try:
        roles = frozenset(
            UserRole(value.strip()) for value in raw_roles.split(",") if value.strip()
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Local identity contains an unknown role",
        ) from exc
    if not roles:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="A role is required")

    raw_user_id = request.headers.get("X-SRBG-Local-User-ID")
    try:
        user_id = LOCAL_USER_ID if raw_user_id is None else UUID(raw_user_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Local identity contains an invalid user identifier",
        ) from exc
    if user_id.version != 7:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Local identity must use a UUIDv7 identifier",
        )

    principal = Principal(
        user_id=user_id,
        display_name=request.headers.get("X-SRBG-Local-User", "本地来源管理员"),
        roles=roles,
        local_identity=True,
    )
    request.state.principal = principal
    return principal


async def _oidc_principal(request: Request, settings: Settings) -> Principal:
    authorization = request.headers.get("Authorization", "")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="OIDC bearer authentication is required",
        )
    if settings.oidc_jwks_url is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="OIDC unavailable",
        )
    try:
        async with httpx.AsyncClient(
            timeout=settings.external_io_timeout_seconds,
            follow_redirects=False,
        ) as client:
            response = await client.get(settings.oidc_jwks_url)
            response.raise_for_status()
            jwks = response.json()
        return await asyncio.to_thread(decode_oidc_token, token, jwks, settings)
    except (httpx.HTTPError, ValueError, jwt.PyJWTError, KeyError, TypeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="OIDC token validation failed",
        ) from exc


def decode_oidc_token(token: str, jwks: object, settings: Settings) -> Principal:
    if not isinstance(jwks, dict):
        raise ValueError("invalid JWKS")
    keys = jwks.get("keys")
    if not isinstance(keys, list) or not keys:
        raise ValueError("no approved signing key or OIDC policy")
    header = jwt.get_unverified_header(token)
    kid = header.get("kid")
    if header.get("alg") != "RS256" or not isinstance(kid, str) or not kid:
        raise ValueError("no approved signing key or OIDC policy")
    signing_key = next((key for key in PyJWKSet.from_dict(jwks).keys if key.key_id == kid), None)
    if signing_key is None or settings.oidc_issuer is None or settings.oidc_audience is None:
        raise ValueError("no approved signing key or OIDC policy")
    claims = jwt.decode(
        token,
        signing_key.key,
        algorithms=["RS256"],
        audience=settings.oidc_audience,
        issuer=settings.oidc_issuer,
        options={"require": ["exp", "iat", "iss", "aud", "srbg_user_id", "roles"]},
    )
    user_id = UUID(str(claims["srbg_user_id"]))
    if user_id.version != 7:
        raise ValueError("OIDC srbg_user_id must be UUIDv7")
    raw_roles = claims["roles"]
    if not isinstance(raw_roles, list) or not raw_roles:
        raise ValueError("OIDC roles must be a non-empty list")
    roles = frozenset(UserRole(str(role)) for role in raw_roles)
    display_name = claims.get("name", "企业用户")
    if not isinstance(display_name, str) or not display_name or len(display_name) > 200:
        raise ValueError("OIDC display name is invalid")
    return Principal(
        user_id=user_id,
        display_name=display_name,
        roles=roles,
        local_identity=False,
    )


def require_roles(*allowed: UserRole) -> Callable[[Principal], Awaitable[Principal]]:
    allowed_roles = frozenset(allowed)

    async def authorize(
        principal: Annotated[Principal, Depends(get_current_principal)],
    ) -> Principal:
        if principal.roles.isdisjoint(allowed_roles):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This role is not permitted to perform the operation",
            )
        return principal

    return authorize
