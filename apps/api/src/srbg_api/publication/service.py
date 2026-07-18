"""The sole application entry point for review and publication state changes."""

import json
from collections.abc import Awaitable, Callable, Mapping
from contextlib import AbstractAsyncContextManager
from datetime import UTC, date, datetime
from hashlib import sha256
from typing import Any, Literal, Protocol
from uuid import UUID

from srbg_contracts import (
    ClaimConflict,
    ClaimConflictDecisionResponse,
    DailyReport,
    DigitalCaseReviewPatch,
    OwnerRelationshipCorrectionRequest,
    OwnerRelationshipCorrectionResponse,
    ReviewDecisionResponse,
    ScoreDimension,
)

from srbg_api.identifiers import uuid7
from srbg_api.observability import PERSONAL_RELATIONSHIP_CORRECTIONS
from srbg_api.publication.gate import PublicationGate


class PublicationDenied(PermissionError):
    def __init__(self, reasons: tuple[str, ...]) -> None:
        self.reasons = reasons
        super().__init__(", ".join(reasons))


class PublicationTransaction(Protocol):
    async def apply_digital_case_patch(self, patch: DigitalCaseReviewPatch) -> None: ...

    async def authoritative_context(
        self,
        *,
        evaluation_id: UUID,
        policy_version: str,
        policy_sha256: str,
        evaluated_at: datetime,
    ) -> dict[str, Any]: ...

    async def publish(
        self,
        *,
        action: str,
        revision_id: UUID,
        evaluation: dict[str, Any],
        evaluation_sha256: str,
        reviewer_id: UUID,
        reason: str,
        decided_at: datetime,
    ) -> ReviewDecisionResponse: ...


class PublicationRepository(Protocol):
    async def close(self) -> None: ...

    async def build_internal_projection(self, *, actor_id: UUID, generated_at: datetime) -> Any: ...

    async def internal_projection_metrics(self) -> dict[str, float]: ...

    async def request_event_identity_change(
        self,
        *,
        operation: Literal["MERGE", "SPLIT", "ROLLBACK"],
        event_ids: list[UUID],
        canonical_event_id: UUID | None,
        allocations: Mapping[UUID, UUID],
        submitted_by: UUID,
        reason: str,
        created_at: datetime,
    ) -> UUID: ...

    async def decide_event_identity_change(
        self,
        *,
        request_id: UUID,
        approve: bool,
        reviewer_id: UUID,
        reason: str,
        decided_at: datetime,
    ) -> None: ...

    async def create_daily_draft(
        self,
        *,
        report_date: date,
        actor_id: UUID,
        idempotency_key: str,
        created_at: datetime,
    ) -> DailyReport: ...

    async def publish_daily_report(
        self,
        *,
        report_id: UUID,
        reviewer_id: UUID,
        idempotency_key: str,
        published_at: datetime,
    ) -> DailyReport: ...

    async def list_claim_conflicts(self) -> list[ClaimConflict]: ...

    def approval_transaction(
        self,
        *,
        review_task_id: UUID,
        reviewer_id: UUID,
        reason: str,
        decided_at: datetime,
    ) -> AbstractAsyncContextManager[PublicationTransaction]: ...

    async def reject(
        self,
        *,
        review_task_id: UUID,
        reviewer_id: UUID,
        reason: str,
        decided_at: datetime,
    ) -> ReviewDecisionResponse: ...

    async def withdraw(
        self,
        *,
        publication_id: UUID,
        actor_id: UUID,
        evidence_id: UUID,
        reason: str,
        withdrawn_at: datetime,
    ) -> UUID: ...

    async def process_outbox_once(self, *, processed_at: datetime) -> bool: ...

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

    async def decide_product_normalization(
        self,
        *,
        candidate_id: UUID,
        action: Literal["MERGE_ALIAS", "LINK_AS_NEW_VERSION", "KEEP_DISTINCT"],
        reviewer_id: UUID,
        reason: str,
        decided_at: datetime,
    ) -> None: ...

    async def decide_candidate(
        self,
        *,
        candidate_kind: Literal[
            "RELATION",
            "REGULATION_STATUS",
            "EVENT_LINK",
            "EVENT_RELATION",
            "CLAIM",
            "PAPER_RELATION",
        ],
        candidate_id: UUID,
        action: Literal["ACCEPT", "REJECT", "CONFIRM_UNRESOLVED"],
        target_document_id: UUID | None,
        reviewer_id: UUID,
        reason: str,
        decided_at: datetime,
    ) -> None: ...

    async def escalate_version_change(
        self,
        *,
        version_change_id: UUID,
        reviewer_id: UUID,
        reason: str,
        decided_at: datetime,
    ) -> None: ...

    async def resolve_claim_conflict(
        self,
        *,
        conflict_id: UUID,
        action: Literal["ACCEPT_CANDIDATE", "KEEP_CURRENT", "MARK_UNRESOLVED"],
        reviewer_id: UUID,
        reason: str,
        decided_at: datetime,
    ) -> ClaimConflictDecisionResponse: ...

    async def decide_cluster(
        self,
        *,
        candidate_id: UUID,
        candidate_kind: Literal["DUPLICATE", "EVENT", "TOPIC", "RELATION"],
        action: Literal["MERGE", "SPLIT", "KEEP_DISTINCT", "LINK_RELATION"],
        member_ids: list[UUID],
        relation_type: str | None,
        reviewer_id: UUID,
        reason: str,
        decided_at: datetime,
    ) -> None: ...

    async def override_score(
        self,
        *,
        item_id: UUID,
        dimension: ScoreDimension,
        score: int,
        reviewer_id: UUID,
        reason: str,
        decided_at: datetime,
    ) -> None: ...


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
            actor_id=actor_id,
            generated_at=self._now(),
        )

    async def internal_projection_metrics(self) -> dict[str, float]:
        return await self._repository.internal_projection_metrics()

    async def request_event_identity_change(
        self,
        *,
        operation: Literal["MERGE", "SPLIT", "ROLLBACK"],
        event_ids: list[UUID],
        canonical_event_id: UUID | None,
        allocations: Mapping[UUID, UUID],
        submitted_by: UUID,
        reason: str,
    ) -> UUID:
        if len(set(event_ids)) != len(event_ids) or not event_ids:
            raise PublicationDenied(("EVENT_IDENTITY_TARGETS_INVALID",))
        if operation == "MERGE" and (len(event_ids) < 2 or canonical_event_id not in event_ids):
            raise PublicationDenied(("EVENT_MERGE_CANONICAL_INVALID",))
        if operation == "SPLIT" and (len(event_ids) < 2 or not allocations):
            raise PublicationDenied(("EVENT_SPLIT_ALLOCATION_REQUIRED",))
        if operation != "SPLIT" and allocations:
            raise PublicationDenied(("EVENT_ALLOCATION_ONLY_FOR_SPLIT",))
        if not reason.strip():
            raise PublicationDenied(("EVENT_IDENTITY_REASON_REQUIRED",))
        return await self._repository.request_event_identity_change(
            operation=operation,
            event_ids=event_ids,
            canonical_event_id=canonical_event_id,
            allocations=allocations,
            submitted_by=submitted_by,
            reason=reason.strip(),
            created_at=self._now(),
        )

    async def decide_event_identity_change(
        self,
        request_id: UUID,
        *,
        approve: bool,
        reviewer_id: UUID,
        reason: str,
    ) -> None:
        if not reason.strip():
            raise PublicationDenied(("EVENT_IDENTITY_DECISION_REASON_REQUIRED",))
        await self._repository.decide_event_identity_change(
            request_id=request_id,
            approve=approve,
            reviewer_id=reviewer_id,
            reason=reason.strip(),
            decided_at=self._now(),
        )

    async def create_daily_draft(
        self,
        *,
        report_date: date,
        actor_id: UUID,
        idempotency_key: str,
    ) -> DailyReport:
        return await self._repository.create_daily_draft(
            report_date=report_date,
            actor_id=actor_id,
            idempotency_key=idempotency_key,
            created_at=self._now(),
        )

    async def publish_daily_report(
        self,
        report_id: UUID,
        *,
        reviewer_id: UUID,
        idempotency_key: str,
    ) -> DailyReport:
        return await self._repository.publish_daily_report(
            report_id=report_id,
            reviewer_id=reviewer_id,
            idempotency_key=idempotency_key,
            published_at=self._now(),
        )

    async def list_claim_conflicts(self) -> list[ClaimConflict]:
        return await self._repository.list_claim_conflicts()

    async def decide_cluster(
        self,
        candidate_id: UUID,
        *,
        candidate_kind: Literal["DUPLICATE", "EVENT", "TOPIC", "RELATION"],
        action: Literal["MERGE", "SPLIT", "KEEP_DISTINCT", "LINK_RELATION"],
        member_ids: list[UUID],
        relation_type: str | None,
        reviewer_id: UUID,
        reason: str,
    ) -> None:
        if len(set(member_ids)) < 2:
            raise PublicationDenied(("CLUSTER_MEMBERS_INVALID",))
        allowed_actions = {
            "DUPLICATE": {"MERGE", "KEEP_DISTINCT"},
            "EVENT": {"MERGE", "SPLIT", "KEEP_DISTINCT"},
            "TOPIC": {"MERGE", "SPLIT", "KEEP_DISTINCT"},
            "RELATION": {"LINK_RELATION", "KEEP_DISTINCT"},
        }
        if action not in allowed_actions[candidate_kind]:
            raise PublicationDenied(("CLUSTER_ACTION_KIND_MISMATCH",))
        if action == "LINK_RELATION" and not relation_type:
            raise PublicationDenied(("RELATION_TYPE_REQUIRED",))
        await self._repository.decide_cluster(
            candidate_id=candidate_id,
            candidate_kind=candidate_kind,
            action=action,
            member_ids=member_ids,
            relation_type=relation_type,
            reviewer_id=reviewer_id,
            reason=reason,
            decided_at=self._now(),
        )

    async def override_score(
        self,
        item_id: UUID,
        *,
        dimension: ScoreDimension,
        score: int,
        reviewer_id: UUID,
        reason: str,
    ) -> None:
        await self._repository.override_score(
            item_id=item_id,
            dimension=dimension,
            score=score,
            reviewer_id=reviewer_id,
            reason=reason,
            decided_at=self._now(),
        )

    async def decide_review(
        self,
        review_task_id: UUID,
        *,
        action: Literal["APPROVE", "REJECT"],
        reason: str,
        reviewer_id: UUID,
        digital_case_patch: DigitalCaseReviewPatch | None = None,
    ) -> ReviewDecisionResponse:
        task_type_lookup = getattr(self._repository, "review_task_type", None)
        if task_type_lookup is not None:
            task_type = await task_type_lookup(review_task_id)
            if task_type == "CLAIM_REVIEW" and action == "APPROVE":
                raise PublicationDenied(("CLAIM_REVIEW_CANNOT_PUBLISH",))
        if action == "REJECT":
            return await self._repository.reject(
                review_task_id=review_task_id,
                reviewer_id=reviewer_id,
                reason=reason,
                decided_at=self._now(),
            )
        return await self._publish_revision(
            review_task_id=review_task_id,
            reviewer_id=reviewer_id,
            reason=reason,
            revision_action="PUBLISH",
            digital_case_patch=digital_case_patch,
        )

    async def revise(
        self,
        review_task_id: UUID,
        *,
        reason: str,
        reviewer_id: UUID,
    ) -> ReviewDecisionResponse:
        return await self._publish_revision(
            review_task_id=review_task_id,
            reviewer_id=reviewer_id,
            reason=reason,
            revision_action="REVISE",
        )

    async def republish(
        self,
        review_task_id: UUID,
        *,
        reason: str,
        reviewer_id: UUID,
    ) -> ReviewDecisionResponse:
        return await self._publish_revision(
            review_task_id=review_task_id,
            reviewer_id=reviewer_id,
            reason=reason,
            revision_action="REPUBLISH",
        )

    async def withdraw(
        self,
        publication_id: UUID,
        *,
        reason: str,
        actor_id: UUID,
        evidence_id: UUID,
    ) -> UUID:
        return await self._repository.withdraw(
            publication_id=publication_id,
            actor_id=actor_id,
            evidence_id=evidence_id,
            reason=reason,
            withdrawn_at=self._now(),
        )

    async def process_outbox_once(self) -> bool:
        """The publisher worker enters version lifecycle changes through this service only."""
        return await self._repository.process_outbox_once(processed_at=self._now())

    async def process_personal_content_once(self) -> bool:
        """Write the minimal personal projection through the sole publisher boundary."""

        return await self._repository.process_personal_content_once(processed_at=self._now())

    async def correct_automatic_relationship(
        self,
        event_id: UUID,
        *,
        payload: OwnerRelationshipCorrectionRequest,
        owner_id: UUID,
    ) -> OwnerRelationshipCorrectionResponse:
        """Apply the local Owner's highest-priority correction at the publication boundary."""

        try:
            return await self._repository.correct_automatic_relationship(
                event_id=event_id,
                payload=payload,
                owner_id=owner_id,
                corrected_at=self._now(),
            )
        except Exception:
            PERSONAL_RELATIONSHIP_CORRECTIONS.labels(
                action=payload.action, outcome="failed"
            ).inc()
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

    async def decide_product_normalization(
        self,
        candidate_id: UUID,
        *,
        action: Literal["MERGE_ALIAS", "LINK_AS_NEW_VERSION", "KEEP_DISTINCT"],
        reason: str,
        reviewer_id: UUID,
    ) -> None:
        await self._repository.decide_product_normalization(
            candidate_id=candidate_id,
            action=action,
            reason=reason,
            reviewer_id=reviewer_id,
            decided_at=self._now(),
        )

    async def decide_candidate(
        self,
        candidate_kind: Literal[
            "RELATION",
            "REGULATION_STATUS",
            "EVENT_LINK",
            "EVENT_RELATION",
            "CLAIM",
            "PAPER_RELATION",
        ],
        candidate_id: UUID,
        *,
        action: Literal["ACCEPT", "REJECT", "CONFIRM_UNRESOLVED"],
        target_document_id: UUID | None,
        reason: str,
        reviewer_id: UUID,
    ) -> None:
        if candidate_kind == "CLAIM":
            lookup = getattr(self._repository, "is_ai_claim_candidate", None)
            if lookup is not None and await lookup(candidate_id):
                raise PublicationDenied(("PERS06_LEGACY_CLAIM_READ_ONLY",))
        await self._repository.decide_candidate(
            candidate_kind=candidate_kind,
            candidate_id=candidate_id,
            action=action,
            target_document_id=target_document_id,
            reviewer_id=reviewer_id,
            reason=reason,
            decided_at=self._now(),
        )

    async def resolve_claim_conflict(
        self,
        conflict_id: UUID,
        *,
        action: Literal["ACCEPT_CANDIDATE", "KEEP_CURRENT", "MARK_UNRESOLVED"],
        reason: str,
        reviewer_id: UUID,
    ) -> ClaimConflictDecisionResponse:
        return await self._repository.resolve_claim_conflict(
            conflict_id=conflict_id,
            action=action,
            reviewer_id=reviewer_id,
            reason=reason,
            decided_at=self._now(),
        )

    async def escalate_version_change(
        self,
        version_change_id: UUID,
        *,
        reason: str,
        reviewer_id: UUID,
    ) -> None:
        await self._repository.escalate_version_change(
            version_change_id=version_change_id,
            reviewer_id=reviewer_id,
            reason=reason,
            decided_at=self._now(),
        )

    async def _publish_revision(
        self,
        *,
        review_task_id: UUID,
        reviewer_id: UUID,
        reason: str,
        revision_action: Literal["PUBLISH", "REVISE", "REPUBLISH"],
        digital_case_patch: DigitalCaseReviewPatch | None = None,
    ) -> ReviewDecisionResponse:
        decided_at = self._now()
        revision_id = uuid7()
        async with self._repository.approval_transaction(
            review_task_id=review_task_id,
            reviewer_id=reviewer_id,
            reason=reason,
            decided_at=decided_at,
        ) as transaction:
            if digital_case_patch is not None:
                await transaction.apply_digital_case_patch(digital_case_patch)
            evaluation = await transaction.authoritative_context(
                evaluation_id=uuid7(),
                policy_version=self._gate.policy_version,
                policy_sha256=self._gate.policy_sha256,
                evaluated_at=decided_at,
            )
            result = self._gate.evaluate(evaluation, action="PUBLISH")
            if not result.allowed:
                raise PublicationDenied(result.reasons)
            evaluation_sha256 = _canonical_json_hash(evaluation)
            return await transaction.publish(
                action=revision_action,
                revision_id=revision_id,
                evaluation=evaluation,
                evaluation_sha256=evaluation_sha256,
                reviewer_id=reviewer_id,
                reason=reason,
                decided_at=decided_at,
            )


def _canonical_json_hash(value: Mapping[str, Any]) -> str:
    serialized = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return sha256(serialized).hexdigest()
