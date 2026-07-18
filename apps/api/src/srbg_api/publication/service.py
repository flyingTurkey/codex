from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any, Protocol
from uuid import UUID

from srbg_contracts import (
    OwnerRelationshipCorrectionRequest,
    OwnerRelationshipCorrectionResponse,
)

from srbg_api.observability import PERSONAL_RELATIONSHIP_CORRECTIONS
from srbg_api.publication.gate import PublicationGate


class PublicationDenied(PermissionError):
    def __init__(self, reasons: tuple[str, ...]) -> None:
        super().__init__(", ".join(reasons))
        self.reasons = reasons


class PublicationRepository(Protocol):
    async def close(self) -> None: ...

    async def build_internal_projection(self, *, actor_id: UUID, generated_at: datetime) -> Any: ...

    async def internal_projection_metrics(self) -> dict[str, float]: ...

    async def process_personal_content_once(self, *, processed_at: datetime) -> bool: ...

    async def correct_automatic_relationship(
        self,
        *,
        event_id: UUID,
        payload: OwnerRelationshipCorrectionRequest,
        owner_id: UUID,
        corrected_at: datetime,
    ) -> OwnerRelationshipCorrectionResponse: ...

    async def process_projection_invalidation_once(
        self,
        *,
        processed_at: datetime,
        cache_generation: Callable[[UUID, int, bool], Awaitable[None]],
        search_projection: Callable[[UUID, int, bool], Awaitable[None]] | None,
        daily_digest: Callable[[UUID, int, bool], Awaitable[None]] | None,
    ) -> bool: ...


class PublicationService:
    """Reviewers and lifecycle callers cannot write publication tables directly."""

    def __init__(
        self,
        *,
        repository: PublicationRepository,
        gate: PublicationGate,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._repository = repository
        self._gate = gate
        self._now = now or (lambda: datetime.now(UTC))

    async def close(self) -> None:
        await self._repository.close()

    async def build_internal_projection(self, *, actor_id: UUID) -> Any:
        """Build the shadow projection only through the sole publication boundary."""
        return await self._repository.build_internal_projection(
            actor_id=actor_id, generated_at=self._now()
        )

    async def internal_projection_metrics(self) -> dict[str, float]:
        return await self._repository.internal_projection_metrics()

    async def process_personal_content_once(self) -> bool:
        """Write the minimal personal projection through the sole publisher boundary."""
        return await self._repository.process_personal_content_once(processed_at=self._now())

    async def correct_automatic_relationship(
        self, event_id: UUID, *, payload: OwnerRelationshipCorrectionRequest, owner_id: UUID
    ) -> OwnerRelationshipCorrectionResponse:
        """Apply the local Owner's highest-priority correction at the publication boundary."""
        try:
            return await self._repository.correct_automatic_relationship(
                event_id=event_id, payload=payload, owner_id=owner_id, corrected_at=self._now()
            )
        except Exception:
            PERSONAL_RELATIONSHIP_CORRECTIONS.labels(action=payload.action, outcome="failed").inc()
            raise

    async def process_projection_invalidation_once(
        self,
        *,
        cache_generation: Callable[[UUID, int, bool], Awaitable[None]],
        search_projection: Callable[[UUID, int, bool], Awaitable[None]] | None = None,
        daily_digest: Callable[[UUID, int, bool], Awaitable[None]] | None = None,
    ) -> bool:
        """Apply one search/cache/digest projection event under the publisher role."""
        return await self._repository.process_projection_invalidation_once(
            processed_at=self._now(),
            cache_generation=cache_generation,
            search_projection=search_projection,
            daily_digest=daily_digest,
        )
