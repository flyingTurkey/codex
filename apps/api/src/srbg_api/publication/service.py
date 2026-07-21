from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any, Protocol
from uuid import UUID

from srbg_contracts import (
    HotspotCandidateV2,
    OwnerRelationshipCorrectionRequest,
    OwnerRelationshipCorrectionResponse,
)

from srbg_api.intelligence_v2.domain import EvaluatedHotspotAward
from srbg_api.intelligence_v2.gold_calibration import (
    AutoPassCalibrationGrant,
    exact_auto_pass_calibration,
)
from srbg_api.observability import PERSONAL_RELATIONSHIP_CORRECTIONS
from srbg_api.publication.gate import PublicationGate


class PublicationDenied(PermissionError):
    def __init__(self, reasons: tuple[str, ...]) -> None:
        super().__init__(", ".join(reasons))
        self.reasons = reasons


class PublicationRepository(Protocol):
    async def close(self) -> None: ...

    async def load_auto_pass_calibration(
        self, *, corpus_version: str, rule_version: str, model_id: str, prompt_version: str
    ) -> AutoPassCalibrationGrant | None: ...

    async def append_hotspot_candidate(
        self,
        *,
        event_id: UUID,
        document_version_id: UUID,
        candidate: HotspotCandidateV2,
        model: str,
        prompt_version: str,
        schema_version: str,
        input_sha256: str,
        created_at: datetime,
    ) -> UUID: ...

    async def evaluate_hotspot(
        self,
        *,
        event_id: UUID,
        document_version_id: UUID,
        evaluated_at: datetime,
    ) -> EvaluatedHotspotAward: ...

    async def build_internal_projection(self, *, actor_id: UUID, generated_at: datetime) -> Any: ...

    async def internal_projection_metrics(self) -> dict[str, float]: ...

    async def process_personal_content_once(self, *, processed_at: datetime) -> bool: ...

    async def refresh_v2_projection(
        self,
        *,
        event_id: UUID,
        document_version_id: UUID,
        projected_at: datetime,
    ) -> None: ...

    async def process_v2_review_reprocessing(
        self,
        *,
        outbox_id: UUID,
        processed_at: datetime,
    ) -> None: ...

    async def process_ai_projection_refresh_once(self, *, processed_at: datetime) -> bool: ...

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

    async def load_auto_pass_calibration(
        self, *, corpus_version: str, rule_version: str, model_id: str, prompt_version: str
    ) -> AutoPassCalibrationGrant | None:
        """Read the exact qualification grant without changing publication state."""

        grant = await self._repository.load_auto_pass_calibration(
            corpus_version=corpus_version,
            rule_version=rule_version,
            model_id=model_id,
            prompt_version=prompt_version,
        )
        return exact_auto_pass_calibration(
            grant,
            corpus_version=corpus_version,
            rule_version=rule_version,
            model_id=model_id,
            prompt_version=prompt_version,
        )

    async def append_hotspot_candidate(
        self,
        *,
        event_id: UUID,
        document_version_id: UUID,
        candidate: HotspotCandidateV2,
        model: str,
        prompt_version: str,
        schema_version: str,
        input_sha256: str,
    ) -> UUID:
        """Persist a non-authoritative, claim-bound model proposal."""

        return await self._repository.append_hotspot_candidate(
            event_id=event_id,
            document_version_id=document_version_id,
            candidate=candidate,
            model=model,
            prompt_version=prompt_version,
            schema_version=schema_version,
            input_sha256=input_sha256,
            created_at=self._now(),
        )

    async def evaluate_hotspot(
        self, *, event_id: UUID, document_version_id: UUID
    ) -> EvaluatedHotspotAward:
        """Derive and persist hotspot facts at the sole publication boundary."""

        evaluated_at = self._now()
        result = await self._repository.evaluate_hotspot(
            event_id=event_id,
            document_version_id=document_version_id,
            evaluated_at=evaluated_at,
        )
        if result.awarded:
            await self._repository.refresh_v2_projection(
                event_id=event_id,
                document_version_id=document_version_id,
                projected_at=evaluated_at,
            )
        return result

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

    async def refresh_v2_projection(
        self,
        *,
        event_id: UUID,
        document_version_id: UUID,
    ) -> None:
        """Rebuild a v2 projection from database facts at the sole write boundary."""

        await self._repository.refresh_v2_projection(
            event_id=event_id,
            document_version_id=document_version_id,
            projected_at=self._now(),
        )

    async def process_v2_review_reprocessing(self, *, outbox_id: UUID) -> None:
        """Apply one durable Owner decision identified only by its Outbox fact."""

        await self._repository.process_v2_review_reprocessing(
            outbox_id=outbox_id,
            processed_at=self._now(),
        )

    async def process_ai_projection_refresh_once(self) -> bool:
        """Consume one AI state handoff through the sole projection writer."""

        return await self._repository.process_ai_projection_refresh_once(processed_at=self._now())

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
