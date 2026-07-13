"""Fail-closed request identity and role authorization.

Round 01 only supplies an explicitly labelled local identity provider for demo and
test environments. Production rejects these headers until the OIDC adapter lands.
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, Request, status
from srbg_contracts import UserRole

from srbg_api.config import get_settings

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
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="OIDC authentication is required",
        )

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

    return Principal(
        user_id=LOCAL_USER_ID,
        display_name=request.headers.get("X-SRBG-Local-User", "本地来源管理员"),
        roles=roles,
        local_identity=True,
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
