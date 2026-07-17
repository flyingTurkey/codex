"""Fail-closed local and OIDC request identity with role authorization."""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

import httpx2 as httpx
import jwt
from fastapi import Depends, HTTPException, Request, status
from jwt import PyJWKSet
from srbg_contracts import UserRole

from srbg_api.config import Settings, get_settings
from srbg_api.observability import AUTHORIZATION_DENIALS

LOCAL_USER_ID = UUID("019b0000-0000-7000-8000-000000009001")
LOCAL_ENVIRONMENTS = frozenset({"demo", "development", "test"})
LOGGER = logging.getLogger("srbg.auth")


def _record_authorization_denial(reason: str) -> None:
    AUTHORIZATION_DENIALS.labels(reason).inc()
    LOGGER.warning("authorization_denied", extra={"reason": reason})


@dataclass(frozen=True, slots=True)
class Principal:
    user_id: UUID
    display_name: str
    roles: frozenset[UserRole]
    local_identity: bool
    acr: str | None = None
    amr: frozenset[str] = frozenset()
    authenticated_at: datetime | None = None
    local_step_up: bool = False
    oidc_issuer: str | None = None
    oidc_subject: str | None = None


async def get_current_principal(request: Request) -> Principal:
    settings = get_settings()
    if settings.environment not in LOCAL_ENVIRONMENTS:
        principal = await _oidc_principal(request, settings)
        request.state.principal = principal
        return principal

    raw_roles = request.headers.get(
        "X-SRBG-Local-Roles",
        f"{UserRole.OWNER.value},{UserRole.VIEWER.value}",
    )
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
        display_name=request.headers.get("X-SRBG-Local-User", "本地个人 Owner"),
        roles=roles,
        local_identity=True,
        local_step_up=request.headers.get("X-SRBG-Local-Step-Up", "false").lower() == "true",
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
        options={"require": ["exp", "nbf", "iat", "iss", "aud", "srbg_user_id", "roles"]},
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
    raw_acr = claims.get("acr")
    if raw_acr is not None and not isinstance(raw_acr, str):
        raise ValueError("OIDC acr is invalid")
    raw_amr = claims.get("amr", [])
    if not isinstance(raw_amr, list) or any(not isinstance(method, str) for method in raw_amr):
        raise ValueError("OIDC amr is invalid")
    raw_auth_time = claims.get("auth_time")
    authenticated_at = (
        datetime.fromtimestamp(raw_auth_time, tz=UTC)
        if isinstance(raw_auth_time, (int, float))
        else None
    )
    raw_issuer = claims.get("iss")
    if not isinstance(raw_issuer, str) or not raw_issuer or len(raw_issuer) > 2048:
        raise ValueError("OIDC issuer is invalid")
    raw_subject = claims.get("sub")
    if raw_subject is not None and (
        not isinstance(raw_subject, str) or not raw_subject or len(raw_subject) > 255
    ):
        raise ValueError("OIDC subject is invalid")
    return Principal(
        user_id=user_id,
        display_name=display_name,
        roles=roles,
        local_identity=False,
        acr=raw_acr,
        amr=frozenset(raw_amr),
        authenticated_at=authenticated_at,
        oidc_issuer=raw_issuer,
        oidc_subject=raw_subject,
    )


def principal_has_step_up(
    principal: Principal,
    settings: Settings,
    *,
    now: datetime | None = None,
) -> bool:
    """Verify recent MFA without treating an authorization role as authentication assurance."""

    if principal.local_identity:
        return settings.environment.lower() in LOCAL_ENVIRONMENTS and principal.local_step_up
    if (
        principal.acr not in settings.oidc_step_up_acr_values
        or "mfa" not in principal.amr
        or principal.authenticated_at is None
    ):
        return False
    checked_at = now or datetime.now(UTC)
    age_seconds = (checked_at - principal.authenticated_at).total_seconds()
    return 0 <= age_seconds <= settings.oidc_step_up_max_age_seconds


def require_step_up(
    principal: Annotated[Principal, Depends(get_current_principal)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> Principal:
    if not principal_has_step_up(principal, settings):
        _record_authorization_denial("step_up")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Recent multi-factor authentication is required",
        )
    return principal


def require_roles(*allowed: UserRole) -> Callable[[Principal], Awaitable[Principal]]:
    allowed_roles = frozenset(allowed)

    async def authorize(
        principal: Annotated[Principal, Depends(get_current_principal)],
    ) -> Principal:
        if principal.roles.isdisjoint(allowed_roles):
            _record_authorization_denial("role")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This role is not permitted to perform the operation",
            )
        return principal

    return authorize


async def require_local_owner(
    principal: Annotated[Principal, Depends(get_current_principal)],
) -> Principal:
    """Authorize the one fixed local Owner used by the PERS-01 product surface."""

    if (
        not principal.local_identity
        or principal.user_id != LOCAL_USER_ID
        or UserRole.OWNER not in principal.roles
    ):
        _record_authorization_denial("personal_owner")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="The local personal Owner is required",
        )
    return principal


def require_roles_with_step_up(
    *allowed: UserRole,
) -> Callable[[Principal, Settings], Awaitable[Principal]]:
    allowed_roles = frozenset(allowed)

    async def authorize(
        principal: Annotated[Principal, Depends(get_current_principal)],
        settings: Annotated[Settings, Depends(get_settings)],
    ) -> Principal:
        if principal.roles.isdisjoint(allowed_roles):
            _record_authorization_denial("role")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This role is not permitted to perform the operation",
            )
        if not principal_has_step_up(principal, settings):
            _record_authorization_denial("step_up")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Recent multi-factor authentication is required",
            )
        return principal

    return authorize
