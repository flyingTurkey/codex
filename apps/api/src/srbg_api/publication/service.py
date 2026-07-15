"""The sole application entry point for review and publication state changes."""

import json
from collections.abc import Callable, Mapping
from contextlib import AbstractAsyncContextManager
from datetime import UTC, datetime
from hashlib import sha256
from typing import Any, Literal, Protocol
from uuid import UUID

from srbg_contracts import (
    ClaimConflict,
    ClaimConflictDecisionResponse,
    DigitalCaseReviewPatch,
    ReviewDecisionResponse,
)

from srbg_api.identifiers import uuid7
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

    async def list_claim_conflicts(self) -> list[ClaimConflict]:
        return await self._repository.list_claim_conflicts()

    async def decide_review(
        self,
        review_task_id: UUID,
        *,
        action: Literal["APPROVE", "REJECT"],
        reason: str,
        reviewer_id: UUID,
        digital_case_patch: DigitalCaseReviewPatch | None = None,
    ) -> ReviewDecisionResponse:
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
