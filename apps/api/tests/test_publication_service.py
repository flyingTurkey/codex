import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from srbg_api.publication.gate import PublicationGate
from srbg_api.publication.service import PublicationDenied, PublicationService
from srbg_contracts import DigitalCaseReviewPatch, ReviewDecisionResponse, ScoreDimension

POLICY = Path("docs/codex-kit/assets/validation/publication_gate.json")
SCHEMA = Path("docs/codex-kit/assets/validation/publication_evaluation.schema.json")
REVIEW_TASK_ID = UUID("019b0000-0000-7000-8000-000000005001")
SUBMITTER_ID = UUID("019b0000-0000-7000-8000-000000005002")
REVIEWER_ID = UUID("019b0000-0000-7000-8000-000000005003")
CANDIDATE_ID = UUID("019b0000-0000-7000-8000-000000005004")
TARGET_DOCUMENT_ID = UUID("019b0000-0000-7000-8000-000000005005")
VERSION_CHANGE_ID = UUID("019b0000-0000-7000-8000-000000005006")
SAFETY_CASE_CANDIDATE_ID = UUID("019b0000-0000-7000-8000-000000005007")
CLAIM_CONFLICT_ID = UUID("019b0000-0000-7000-8000-000000005008")


def _context(*, source_status: str = "ACTIVE", duties_separated: bool = True) -> dict[str, Any]:
    return {
        "evaluation_id": "019b0000-0000-7000-8000-000000005010",
        "policy_version": "2.1.0",
        "policy_sha256": sha256(POLICY.read_bytes()).hexdigest(),
        "evaluated_at": "2026-07-14T02:00:00Z",
        "item": {
            "item_id": "019b0000-0000-7000-8000-000000005011",
            "item_type": "SAFETY_REGULATION",
            "is_demo": False,
            "publishable": True,
            "regulation_status": "UNKNOWN",
        },
        "server": {
            "source": {
                "source_id": "019b0000-0000-7000-8000-000000005012",
                "status": source_status,
                "authority_level": "A1",
                "policy_version": "fixture-v1",
                "policy_status": "VALID",
                "excerpt_policy_pass": True,
                "attribution_policy_pass": True,
            },
            "document": {
                "document_id": "019b0000-0000-7000-8000-000000005013",
                "document_version_id": "019b0000-0000-7000-800000005014",
                "content_sha256": "b" * 64,
                "is_current": True,
                "lifecycle_status": "ACTIVE",
                "hash_verified": True,
                "url_policy_pass": True,
                "execution_domain": "PRODUCTION",
                "processing_state": "READY",
                "raw_security_status": "CLEAN",
            },
            "evidence_integrity": {
                "claim_count": 4,
                "evidence_count": 4,
                "bidirectional_refs_valid": True,
                "locators_verified": True,
                "excerpts_match_source": True,
                "accepted_critical_claim_coverage_percent": 100,
                "unresolved_conflict_count": 0,
                "minimum_critical_ocr_confidence_bps": 10000,
                "validator_version": "1.0.0",
            },
            "security": {
                "prompt_injection_detected": False,
                "resolution_status": "NONE",
                "resolution_id": None,
                "scanner_version": "rules-1.0.0",
                "input_sha256": "b" * 64,
            },
            "privacy": {
                "status": "CLEAR",
                "scanner_version": "rules-1.0.0",
                "reputational_risk_reviewed": True,
            },
            "review": {
                "risk_level": "R3",
                "required": True,
                "decision_status": "APPROVED",
                "decision_id": str(REVIEW_TASK_ID),
                "submitted_by": str(SUBMITTER_ID),
                "decided_by": str(REVIEWER_ID),
                "duties_separated": duties_separated,
                "decision_reason": "已逐项核对原文、证据与关键字段",
            },
            "pipeline": {
                "candidate_schema_valid": True,
                "semantic_safety_scan_pass": True,
                "candidate_schema_version": "safety-regulation-parser-1.0.0",
                "ai_status": "NOT_RUN_DEGRADED",
                "four_steps_completed": False,
                "accepted_summary_claim_refs_valid": False,
                "unauthorized_candidate_field_count": 0,
            },
            "round03": {
                "unresolved_relation_candidate_count": 0,
                "unreviewed_regulation_status_candidate_count": 0,
                "unsafe_attachment_count": 0,
                "summary_claim_refs_valid": True,
                "official_status_evidence": False,
                "status_reviewer_decision": False,
            },
        },
    }


class FakeTransaction:
    def __init__(self, context: dict[str, Any]) -> None:
        self.context = context
        self.published = False
        self.revision_id: UUID | None = None
        self.digital_case_patch: DigitalCaseReviewPatch | None = None

    async def apply_digital_case_patch(self, patch: DigitalCaseReviewPatch) -> None:
        self.digital_case_patch = patch

    async def authoritative_context(
        self,
        *,
        evaluation_id: UUID,
        policy_version: str,
        policy_sha256: str,
        evaluated_at: datetime,
    ) -> dict[str, Any]:
        context = self.context | {
            "evaluation_id": str(evaluation_id),
            "policy_version": policy_version,
            "policy_sha256": policy_sha256,
            "evaluated_at": evaluated_at.isoformat().replace("+00:00", "Z"),
        }
        return context

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
    ) -> ReviewDecisionResponse:
        assert action == "PUBLISH"
        assert evaluation["policy_version"] == "2.1.0"
        assert len(evaluation_sha256) == 64
        assert reviewer_id == REVIEWER_ID
        assert reason
        assert decided_at.tzinfo is not None
        self.published = True
        self.revision_id = revision_id
        return ReviewDecisionResponse(
            review_task_id=REVIEW_TASK_ID,
            status="APPROVED",
            publication_revision_id=revision_id,
        )


class FakeRepository:
    def __init__(self, context: dict[str, Any]) -> None:
        self.transaction = FakeTransaction(context)
        self.rejected = False
        self.candidate_decisions: list[dict[str, Any]] = []
        self.escalations: list[dict[str, Any]] = []
        self.conflict_decisions: list[dict[str, Any]] = []
        self.cluster_decisions: list[dict[str, Any]] = []
        self.score_overrides: list[dict[str, Any]] = []

    @asynccontextmanager
    async def approval_transaction(
        self,
        *,
        review_task_id: UUID,
        reviewer_id: UUID,
        reason: str,
        decided_at: datetime,
    ) -> AsyncIterator[FakeTransaction]:
        assert review_task_id == REVIEW_TASK_ID
        assert reviewer_id == REVIEWER_ID
        assert reason
        assert decided_at.tzinfo is not None
        yield self.transaction

    async def reject(
        self,
        *,
        review_task_id: UUID,
        reviewer_id: UUID,
        reason: str,
        decided_at: datetime,
    ) -> ReviewDecisionResponse:
        self.rejected = True
        return ReviewDecisionResponse(
            review_task_id=review_task_id,
            status="REJECTED",
            publication_revision_id=None,
        )

    async def decide_candidate(self, **values: Any) -> None:
        self.candidate_decisions.append(values)

    async def escalate_version_change(self, **values: Any) -> None:
        self.escalations.append(values)

    async def resolve_claim_conflict(self, **values: Any) -> None:
        self.conflict_decisions.append(values)

    async def decide_cluster(self, **values: Any) -> None:
        self.cluster_decisions.append(values)

    async def override_score(self, **values: Any) -> None:
        self.score_overrides.append(values)


def _service(repository: FakeRepository) -> PublicationService:
    return PublicationService(
        repository=repository,
        gate=PublicationGate.from_files(POLICY, SCHEMA),
        now=lambda: datetime(2026, 7, 14, 2, 0, tzinfo=UTC),
    )


def test_approval_uses_authoritative_context_and_binds_new_revision() -> None:
    repository = FakeRepository(_context())

    response = asyncio.run(
        _service(repository).decide_review(
            REVIEW_TASK_ID,
            action="APPROVE",
            reason="字段与原文证据一致",
            reviewer_id=REVIEWER_ID,
        )
    )

    assert response.status == "APPROVED"
    assert response.publication_revision_id is not None
    assert response.publication_revision_id.version == 7
    assert repository.transaction.published is True


def test_digital_case_review_patch_is_applied_inside_the_publication_transaction() -> None:
    repository = FakeRepository(_context())
    patch = DigitalCaseReviewPatch(
        engineering_domains=["BRIDGE"],
        lifecycle_stages=["CONSTRUCTION"],
        technology_tags=["BIM"],
        application_scenarios=["QUALITY_CONTROL"],
        maturity_level="PILOT",
        maturity_evidence_ids=[],
        outcome_attributions=[],
    )

    asyncio.run(
        _service(repository).decide_review(
            REVIEW_TASK_ID,
            action="APPROVE",
            reason="分类、成熟度和归因均已核对证据",
            reviewer_id=REVIEWER_ID,
            digital_case_patch=patch,
        )
    )

    assert repository.transaction.digital_case_patch == patch


def test_inactive_authoritative_source_denies_even_without_candidate_input() -> None:
    repository = FakeRepository(_context(source_status="CANDIDATE"))

    with pytest.raises(PublicationDenied, match="SOURCE_NOT_ACTIVE"):
        asyncio.run(
            _service(repository).decide_review(
                REVIEW_TASK_ID,
                action="APPROVE",
                reason="candidate payload cannot override database",
                reviewer_id=REVIEWER_ID,
            )
        )
    assert repository.transaction.published is False


def test_non_production_document_domain_denies_before_publication_write() -> None:
    context = _context()
    context["server"]["document"]["execution_domain"] = "TRIAL"
    repository = FakeRepository(context)

    with pytest.raises(PublicationDenied, match="NON_PRODUCTION_EXECUTION_DOMAIN"):
        asyncio.run(
            _service(repository).decide_review(
                REVIEW_TASK_ID,
                action="APPROVE",
                reason="trial evidence must never enter the production projection",
                reviewer_id=REVIEWER_ID,
            )
        )

    assert repository.transaction.published is False


def test_duties_separation_is_default_deny() -> None:
    repository = FakeRepository(_context(duties_separated=False))

    with pytest.raises(PublicationDenied, match="DUTIES_NOT_SEPARATED"):
        asyncio.run(
            _service(repository).decide_review(
                REVIEW_TASK_ID,
                action="APPROVE",
                reason="self approval must fail",
                reviewer_id=REVIEWER_ID,
            )
        )


def test_rejection_uses_service_but_creates_no_publication_revision() -> None:
    repository = FakeRepository(_context())

    response = asyncio.run(
        _service(repository).decide_review(
            REVIEW_TASK_ID,
            action="REJECT",
            reason="文号证据不完整",
            reviewer_id=REVIEWER_ID,
        )
    )

    assert response.status == "REJECTED"
    assert response.publication_revision_id is None
    assert repository.rejected is True
    assert repository.transaction.published is False


def test_relation_and_regulation_candidates_require_reviewer_service_decisions() -> None:
    repository = FakeRepository(_context())
    service = _service(repository)

    asyncio.run(
        service.decide_candidate(
            "RELATION",
            CANDIDATE_ID,
            action="ACCEPT",
            target_document_id=TARGET_DOCUMENT_ID,
            reason="官方证据明确修订目标",
            reviewer_id=REVIEWER_ID,
        )
    )
    asyncio.run(
        service.decide_candidate(
            "REGULATION_STATUS",
            CANDIDATE_ID,
            action="REJECT",
            target_document_id=None,
            reason="证据不足、不能认定 REPEALED",
            reviewer_id=REVIEWER_ID,
        )
    )

    assert [value["candidate_kind"] for value in repository.candidate_decisions] == [
        "RELATION",
        "REGULATION_STATUS",
    ]


def test_metadata_change_can_only_be_escalated_through_publication_service() -> None:
    repository = FakeRepository(_context())

    asyncio.run(
        _service(repository).escalate_version_change(
            VERSION_CHANGE_ID,
            reason="重锚证据存在歧义、升级为实质复核",
            reviewer_id=REVIEWER_ID,
        )
    )

    assert repository.escalations == [
        {
            "version_change_id": VERSION_CHANGE_ID,
            "reason": "重锚证据存在歧义、升级为实质复核",
            "reviewer_id": REVIEWER_ID,
            "decided_at": datetime(2026, 7, 14, 2, 0, tzinfo=UTC),
        }
    ]


def test_event_claim_and_conflict_decisions_use_the_single_publication_service() -> None:
    repository = FakeRepository(_context())
    service = _service(repository)

    asyncio.run(
        service.decide_candidate(
            "EVENT_LINK",
            SAFETY_CASE_CANDIDATE_ID,
            action="ACCEPT",
            target_document_id=None,
            reason="日期、地区和项目均指向同一事故",
            reviewer_id=REVIEWER_ID,
        )
    )
    asyncio.run(
        service.resolve_claim_conflict(
            CLAIM_CONFLICT_ID,
            action="ACCEPT_CANDIDATE",
            reason="正式调查报告为更新的有权机关证据",
            reviewer_id=REVIEWER_ID,
        )
    )

    assert repository.candidate_decisions[-1]["candidate_kind"] == "EVENT_LINK"
    assert repository.conflict_decisions == [
        {
            "conflict_id": CLAIM_CONFLICT_ID,
            "action": "ACCEPT_CANDIDATE",
            "reason": "正式调查报告为更新的有权机关证据",
            "reviewer_id": REVIEWER_ID,
            "decided_at": datetime(2026, 7, 14, 2, 0, tzinfo=UTC),
        }
    ]


def test_round08_cluster_and_score_decisions_use_the_single_publication_service() -> None:
    repository = FakeRepository(_context())
    service = _service(repository)
    other_item = UUID("019b0000-0000-7000-8000-000000005099")

    asyncio.run(
        service.decide_cluster(
            CANDIDATE_ID,
            candidate_kind="DUPLICATE",
            action="MERGE",
            member_ids=[TARGET_DOCUMENT_ID, other_item],
            relation_type=None,
            reviewer_id=REVIEWER_ID,
            reason="身份字段与证据一致",
        )
    )
    asyncio.run(
        service.override_score(
            TARGET_DOCUMENT_ID,
            dimension=ScoreDimension.IMPACT,
            score=70,
            reviewer_id=REVIEWER_ID,
            reason="正式文件确认影响范围",
        )
    )

    assert repository.cluster_decisions[0]["action"] == "MERGE"
    assert repository.cluster_decisions[0]["decided_at"].tzinfo is not None
    assert repository.score_overrides[0]["score"] == 70
    assert repository.score_overrides[0]["reason"] == "正式文件确认影响范围"


def test_round08_cluster_actions_are_scoped_to_candidate_kind() -> None:
    repository = FakeRepository(_context())
    service = _service(repository)
    other_item = UUID("019b0000-0000-7000-8000-000000005099")

    with pytest.raises(PublicationDenied, match="CLUSTER_ACTION_KIND_MISMATCH"):
        asyncio.run(
            service.decide_cluster(
                CANDIDATE_ID,
                candidate_kind="DUPLICATE",
                action="SPLIT",
                member_ids=[TARGET_DOCUMENT_ID, other_item],
                relation_type=None,
                reviewer_id=REVIEWER_ID,
                reason="动作类型不适用",
            )
        )

    with pytest.raises(PublicationDenied, match="CLUSTER_ACTION_KIND_MISMATCH"):
        asyncio.run(
            service.decide_cluster(
                CANDIDATE_ID,
                candidate_kind="RELATION",
                action="MERGE",
                member_ids=[TARGET_DOCUMENT_ID, other_item],
                relation_type=None,
                reviewer_id=REVIEWER_ID,
                reason="关系不能按重复合并",
            )
        )
