"""Fixed loopback-only identity for the single-owner personal product."""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, Request, status
from srbg_contracts import UserRole

from srbg_api.observability import AUTHORIZATION_DENIALS

LOCAL_USER_ID = UUID("019b0000-0000-7000-8000-000000009001")
LOGGER = logging.getLogger("srbg.auth")


def _record_authorization_denial(reason: str) -> None:
    AUTHORIZATION_DENIALS.labels(reason).inc()
    LOGGER.warning("authorization_denied", extra={"reason": reason})


@dataclass(frozen=True, slots=True)
class Principal:
    """The only interactive principal supported by personal mode."""

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
    """Return a fixed identity; request headers can never select identity or roles."""

    principal = Principal(
        user_id=LOCAL_USER_ID,
        display_name="本地个人 Owner",
        roles=frozenset({UserRole.OWNER}),
        local_identity=True,
        local_step_up=True,
    )
    request.state.principal = principal
    return principal


async def require_local_owner(
    principal: Annotated[Principal, Depends(get_current_principal)],
) -> Principal:
    if (
        not principal.local_identity
        or principal.user_id != LOCAL_USER_ID
        or principal.roles != frozenset({UserRole.OWNER})
    ):
        _record_authorization_denial("personal_owner")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="The local personal Owner is required",
        )
    return principal


async def require_step_up(
    principal: Annotated[Principal, Depends(require_local_owner)],
) -> Principal:
    """Compatibility dependency: local physical access is the personal-mode assurance."""

    return principal


def principal_has_step_up(principal: Principal, _settings: object, **_: object) -> bool:
    return (
        principal.local_identity
        and principal.user_id == LOCAL_USER_ID
        and principal.roles == frozenset({UserRole.OWNER})
    )
