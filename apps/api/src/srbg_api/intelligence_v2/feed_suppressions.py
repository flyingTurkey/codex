"""Owner commands for append-only Feed suppression preferences."""

import re
import unicodedata
from typing import Annotated, Protocol, cast
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from srbg_contracts import (
    FeedSuppressionAction,
    FeedSuppressionCommand,
    FeedSuppressionFeedbackReason,
    FeedSuppressionRuleView,
)

from srbg_api.auth import Principal, require_local_owner


class FeedSuppressionService(Protocol):
    async def list_feed_suppressions(
        self, *, active_only: bool
    ) -> list[FeedSuppressionRuleView]: ...

    async def command_feed_suppression(
        self,
        *,
        command: FeedSuppressionCommand,
        owner_id: UUID,
        idempotency_key: UUID,
        expected_rule_id: UUID | None,
    ) -> FeedSuppressionRuleView: ...


class FeedSuppressionConflict(RuntimeError):
    """The requested append conflicts with current suppression facts."""


class InvalidFeedSuppressionTarget(ValueError):
    """The target key is not canonical for its requested scope."""


_CUSTOM_TOPIC_SPACES = re.compile(r"\s+")


def canonical_custom_topic(value: str) -> str:
    normalized = _CUSTOM_TOPIC_SPACES.sub(
        "-", unicodedata.normalize("NFKC", value.strip()).casefold()
    )
    if (
        not normalized
        or len(normalized) > 300
        or any(unicodedata.category(char) == "Cc" for char in normalized)
    ):
        raise InvalidFeedSuppressionTarget("invalid CUSTOM_TOPIC target")
    return normalized


OwnerPrincipal = Annotated[Principal, Depends(require_local_owner)]
router = APIRouter(prefix="/api/v2/owner/suppressions", tags=["owner-feed-suppressions"])


def _service(request: Request) -> FeedSuppressionService:
    value = getattr(request.app.state, "publication_service", None)
    if value is None or not hasattr(value, "command_feed_suppression"):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "FEED_SUPPRESSION_SERVICE_UNAVAILABLE",
                "title": "Feed suppression service unavailable",
            },
        )
    return cast(FeedSuppressionService, value)


@router.get("", response_model=list[FeedSuppressionRuleView])
async def list_feed_suppressions(
    request: Request,
    _: OwnerPrincipal,
    active_only: bool = Query(default=True),
) -> list[FeedSuppressionRuleView]:
    return await _service(request).list_feed_suppressions(active_only=active_only)


@router.post("", response_model=FeedSuppressionRuleView, status_code=status.HTTP_201_CREATED)
async def command_feed_suppression(
    payload: FeedSuppressionCommand,
    request: Request,
    principal: OwnerPrincipal,
    idempotency_key: Annotated[UUID, Header(alias="Idempotency-Key")],
    if_match: Annotated[str | None, Header(alias="If-Match")] = None,
) -> FeedSuppressionRuleView:
    if payload.feedback_reason is FeedSuppressionFeedbackReason.SAFETY_DENIAL:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "SAFETY_SUPPRESSION_UNSUPPORTED",
                "title": "Safety allow or deny is outside Feed suppression",
            },
        )
    expected_rule_id: UUID | None = None
    if payload.action is FeedSuppressionAction.REVOKE:
        if if_match is None:
            raise HTTPException(
                status_code=status.HTTP_428_PRECONDITION_REQUIRED,
                detail={"code": "IF_MATCH_REQUIRED", "title": "If-Match is required"},
            )
        expected = f'"{payload.supersedes_rule_id}"'
        if if_match != expected:
            raise HTTPException(
                status_code=status.HTTP_412_PRECONDITION_FAILED,
                detail={
                    "code": "SUPPRESSION_VERSION_MISMATCH",
                    "title": "Suppression has changed",
                },
            )
        expected_rule_id = payload.supersedes_rule_id
    elif if_match is not None:
        raise HTTPException(
            status_code=422,
            detail={"code": "IF_MATCH_NOT_ALLOWED", "title": "Activation has no prior version"},
        )
    try:
        return await _service(request).command_feed_suppression(
            command=payload,
            owner_id=principal.user_id,
            idempotency_key=idempotency_key,
            expected_rule_id=expected_rule_id,
        )
    except InvalidFeedSuppressionTarget as exc:
        raise HTTPException(
            status_code=422,
            detail={"code": "INVALID_SUPPRESSION_TARGET", "title": str(exc)},
        ) from exc
    except FeedSuppressionConflict as exc:
        raise HTTPException(
            status_code=status.HTTP_412_PRECONDITION_FAILED,
            detail={"code": "SUPPRESSION_CONFLICT", "title": str(exc)},
        ) from exc
