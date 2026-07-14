# ruff: noqa: RUF001

import asyncio
import base64
import html
import json
import os
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit
from uuid import UUID

import pymupdf  # type: ignore[import-untyped]
import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine
from srbg_api.config import get_settings
from srbg_api.database import create_database_engine, create_publication_engine
from srbg_api.document_vault.service import DocumentVaultService, SourceVaultMetrics
from srbg_api.document_vault.storage import S3ObjectStore
from srbg_api.identifiers import uuid7
from srbg_api.publication.gate import PublicationGate
from srbg_api.publication.repository import PostgresPublicationRepository
from srbg_api.publication.service import PublicationDenied, PublicationService
from srbg_api.safety_cases.candidates import (
    PostgresEventCandidateStore,
    SafetyEventCandidateService,
)
from srbg_api.safety_regulations.query import (
    PostgresIntelligenceQueryService,
)
from srbg_api.source_registry.admission import REQUIRED_ONBOARDING_CHECKS
from srbg_api.source_registry.repository import SourceVaultRepository
from srbg_api.source_registry.service import SourceRegistryService
from srbg_contracts import (
    OnboardingCheckEvidence,
    SourceOnboardingSubmission,
    SourcePolicySubmission,
    SourceState,
    SourceTransitionRequest,
)

pytestmark = pytest.mark.skipif(
    os.environ.get("SRBG_RUN_SAFETY_INTEGRATION") != "1",
    reason="run through scripts/run_isolated_integration.py",
)

FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "round04"
MANIFEST_PATH = FIXTURE_ROOT / "round04-official-manifest.json"
SUBMITTER = UUID("019b0000-0000-7000-8000-000000009401")
REVIEWER = UUID("019b0000-0000-7000-8000-000000009402")
PUBLISHER = UUID("019b0000-0000-7000-8000-000000009403")
SOURCE_IDS = {
    "GOV-019": UUID("019b0000-0000-7000-8000-000000004019"),
    "GOV-020": UUID("019b0000-0000-7000-8000-000000004020"),
    "GOV-021": UUID("019b0000-0000-7000-8000-000000004021"),
    "GOV-022": UUID("019b0000-0000-7000-8000-000000004022"),
}
STAGE_ITEMS = (
    "initial-report.html.b64",
    "follow-up-report.html.b64",
    "investigation-report.pdf.b64",
    "accountability.html.b64",
    "rectification-evaluation.html.b64",
)


class CleanScanner:
    async def scan(self, content: bytes) -> None:
        assert content


@dataclass(frozen=True, slots=True)
class Artifact:
    file_name: str
    source_url: str
    source_code: str
    authority_level: str
    report_stage: str
    declared_mime: str
    payload: bytes


@dataclass(frozen=True, slots=True)
class StoredArtifact:
    artifact: Artifact
    document_id: UUID
    document_version_id: UUID


@dataclass(frozen=True, slots=True)
class SeededCase:
    event_id: UUID
    item_ids: dict[str, UUID]
    event_link_candidate_ids: dict[str, UUID]
    relation_candidate_ids: dict[str, UUID]
    correction_candidate_id: UUID
    forged_relation_candidate_id: UUID
    claim_ids: dict[str, UUID]
    evidence_ids: dict[str, UUID]
    review_task_ids: dict[str, UUID]


def test_official_safety_case_fixture_to_publication_vertical_slice() -> None:
    asyncio.run(_vertical_slice())


async def _vertical_slice() -> None:
    get_settings.cache_clear()
    settings = get_settings()
    runtime_engine = create_database_engine(settings)
    object_store = S3ObjectStore(settings)
    vault_repository = SourceVaultRepository(runtime_engine)
    source_service = SourceRegistryService(
        vault_repository,
        DocumentVaultService(
            repository=vault_repository,
            object_store=object_store,
            malware_scanner=CleanScanner(),
            metrics=SourceVaultMetrics(),
        ),
    )
    query_service = PostgresIntelligenceQueryService(
        create_database_engine(settings),
        preview_object_reader=object_store,
    )
    candidate_service = SafetyEventCandidateService(PostgresEventCandidateStore(runtime_engine))
    publication_service = PublicationService(
        repository=PostgresPublicationRepository(
            publisher_engine := create_publication_engine(settings)
        ),
        gate=PublicationGate.from_files(
            Path("docs/codex-kit/assets/validation/publication_gate_v4.json"),
            Path("docs/codex-kit/assets/validation/publication_evaluation_v4.schema.json"),
        ),
    )
    try:
        artifacts = _artifacts()
        stored = await _store_official_artifacts(source_service, artifacts)
        seeded = await _seed_case(runtime_engine, stored)
        await _assert_round04_database_boundaries(runtime_engine, seeded, stored)
        initial_candidate_id = await candidate_service.generate_candidate(
            event_id=seeded.event_id,
            item_id=seeded.item_ids["INITIAL_REPORT"],
        )
        assert initial_candidate_id is not None
        seeded.event_link_candidate_ids["INITIAL_REPORT"] = initial_candidate_id
        assert (
            await candidate_service.generate_candidate(
                event_id=seeded.event_id,
                item_id=seeded.item_ids["INITIAL_REPORT"],
            )
            == initial_candidate_id
        )
        publication_revision_ids: dict[str, UUID] = {}
        final_review_task_id = seeded.review_task_ids["FINAL_INVESTIGATION"]
        reviewer_detail = await query_service.get_review_task(final_review_task_id)
        reviewer_claims = {claim.id: claim for claim in reviewer_detail.claims}
        final_claim_ids = {
            seeded.claim_ids[key]
            for key in (
                "final_deaths",
                "final_injuries",
                "final_causes",
                "final_responsibility",
            )
        }
        final_metadata_claim_ids = {
            claim_id
            for key, claim_id in seeded.claim_ids.items()
            if key.startswith("metadata:FINAL_INVESTIGATION:")
        }
        assert set(reviewer_claims) == final_claim_ids | final_metadata_claim_ids
        assert {
            reviewer_claims[claim_id].decision_status for claim_id in final_claim_ids
        } == {"PENDING"}
        assert {
            reviewer_claims[claim_id].decision_status for claim_id in final_metadata_claim_ids
        } == {"ACCEPTED"}
        assert {
            seeded.evidence_ids[key]
            for key in (
                "final_deaths",
                "final_injuries",
                "final_causes",
                "final_responsibility",
            )
        } <= {evidence.id for evidence in reviewer_detail.evidence}
        assert all(claim.evidence_ids for claim in reviewer_claims.values())

        with pytest.raises(PublicationDenied) as self_link:
            await _decide_candidate(
                publication_service,
                "EVENT_LINK",
                seeded.event_link_candidate_ids["INITIAL_REPORT"],
                reviewer_id=SUBMITTER,
            )
        assert "DUTIES_NOT_SEPARATED" in self_link.value.reasons

        await _decide_candidate(
            publication_service,
            "EVENT_LINK",
            seeded.event_link_candidate_ids["INITIAL_REPORT"],
            reviewer_id=REVIEWER,
        )
        async with runtime_engine.connect() as connection:
            initial_event = (
                (
                    await connection.execute(
                        text(
                            "SELECT incident_status, occurred_at, region_code, project_name, "
                            "accident_type, engineering_type FROM event WHERE id = :event_id"
                        ),
                        {"event_id": seeded.event_id},
                    )
                )
                .mappings()
                .one()
            )
        assert initial_event["incident_status"] == "INITIAL_OFFICIAL_REPORT"
        assert initial_event["occurred_at"] is None
        assert initial_event["region_code"] == "441422"
        assert initial_event["project_name"] == "梅大高速"
        assert initial_event["accident_type"] == "ROADBED_COLLAPSE"
        assert initial_event["engineering_type"] == "EXPRESSWAY"
        with pytest.raises(PublicationDenied) as media_cause:
            await _decide_candidate(
                publication_service,
                "CLAIM",
                seeded.claim_ids["initial_media_cause"],
                reviewer_id=REVIEWER,
            )
        assert "OFFICIAL_EVIDENCE_REQUIRED" in media_cause.value.reasons
        await _decide_candidate(
            publication_service,
            "CLAIM",
            seeded.claim_ids["initial_media_cause"],
            action="REJECT",
            reviewer_id=REVIEWER,
        )

        with pytest.raises(PublicationDenied) as self_claim:
            await _decide_candidate(
                publication_service,
                "CLAIM",
                seeded.claim_ids["initial_deaths"],
                reviewer_id=SUBMITTER,
            )
        assert "DUTIES_NOT_SEPARATED" in self_claim.value.reasons

        await _decide_candidate(
            publication_service,
            "CLAIM",
            seeded.claim_ids["initial_deaths"],
            reviewer_id=REVIEWER,
        )
        initial_publication = await publication_service.decide_review(
            seeded.review_task_ids["INITIAL_REPORT"],
            action="APPROVE",
            reason="初报伤亡事实及官方证据已经独立人工审核",
            reviewer_id=PUBLISHER,
        )
        assert initial_publication.publication_revision_id is not None
        publication_revision_ids["INITIAL_REPORT"] = (
            initial_publication.publication_revision_id
        )
        follow_up_candidate_id = await candidate_service.generate_candidate(
            event_id=seeded.event_id,
            item_id=seeded.item_ids["FOLLOW_UP_REPORT"],
        )
        assert follow_up_candidate_id is not None
        seeded.event_link_candidate_ids["FOLLOW_UP_REPORT"] = follow_up_candidate_id
        await _decide_candidate(
            publication_service,
            "EVENT_LINK",
            seeded.event_link_candidate_ids["FOLLOW_UP_REPORT"],
            reviewer_id=REVIEWER,
        )
        for relation_type in ("FOLLOW_UP", "CORRECTS"):
            await _decide_candidate(
                publication_service,
                "EVENT_RELATION",
                seeded.relation_candidate_ids[relation_type],
                reviewer_id=REVIEWER,
            )
        with pytest.raises(DBAPIError):
            async with publisher_engine.begin() as connection:
                forged_at = datetime.now(UTC)
                await connection.execute(
                    text(
                        "INSERT INTO event_relation_decision "
                        "(id, candidate_id, action, reviewer_id, submitted_by, reason, "
                        "created_at) VALUES (:id, :candidate_id, 'ACCEPT', :reviewer, "
                        ":submitter, 'negative correction-chronology check', :now)"
                    ),
                    {
                        "id": uuid7(),
                        "candidate_id": seeded.forged_relation_candidate_id,
                        "reviewer": REVIEWER,
                        "submitter": SUBMITTER,
                        "now": forged_at,
                    },
                )
                await connection.execute(
                    text(
                        "INSERT INTO event_relation "
                        "(id, candidate_id, event_id, source_item_id, target_item_id, "
                        "relation_type, confirmed_by, confirmed_at) VALUES "
                        "(:id, :candidate_id, :event_id, :forged_source_id, "
                        ":forged_target_id, 'CORRECTS', :reviewer, :now)"
                    ),
                    {
                        "id": uuid7(),
                        "candidate_id": seeded.forged_relation_candidate_id,
                        "event_id": seeded.event_id,
                        "forged_source_id": seeded.item_ids["INITIAL_REPORT"],
                        "forged_target_id": seeded.item_ids["FOLLOW_UP_REPORT"],
                        "reviewer": REVIEWER,
                        "now": forged_at,
                    },
                )
        await _decide_candidate(
            publication_service,
            "CLAIM",
            seeded.claim_ids["follow_up_deaths"],
            reviewer_id=REVIEWER,
        )
        first_conflict = _only_pending(await publication_service.list_claim_conflicts())
        assert {first_conflict.current_value, first_conflict.candidate_value} == {24, 48}
        conflict_safe_detail = await query_service.get_event(seeded.event_id)
        assert [item.report_stage.value for item in conflict_safe_detail.timeline.items] == [
            "INITIAL_REPORT"
        ]
        assert len(conflict_safe_detail.unverified_facts) == 1
        public_conflict = conflict_safe_detail.unverified_facts[0]
        assert public_conflict.source_item_id == seeded.item_ids["INITIAL_REPORT"]
        assert public_conflict.claim_id is None
        assert public_conflict.conflict_id == first_conflict.id
        assert public_conflict.field.value == "DEATH_COUNT"
        assert public_conflict.status == "CONFLICTING"
        assert public_conflict.display_value == "待核实"
        assert public_conflict.value is None
        assert public_conflict.evidence_ids == []
        assert all(
            fact.field.value != "DEATH_COUNT"
            for fact in conflict_safe_detail.confirmed_facts
        )
        await publication_service.resolve_claim_conflict(
            first_conflict.id,
            action="KEEP_CURRENT",
            reason="续报值暂不替代当前已确认伤亡事实，保留候选值供后续调查复核",
            reviewer_id=REVIEWER,
        )
        assert (await query_service.get_event(seeded.event_id)).unverified_facts == []
        async with publisher_engine.connect() as connection:
            assert await connection.scalar(
                text(
                    "SELECT deaths FROM safety_case_profile "
                    "WHERE item_id = :item_id"
                ),
                {"item_id": seeded.item_ids["FOLLOW_UP_REPORT"]},
            ) is None
        follow_up_publication = await publication_service.decide_review(
            seeded.review_task_ids["FOLLOW_UP_REPORT"],
            action="APPROVE",
            reason="续报伤亡冲突已完成人工处置并保留前值审计",
            reviewer_id=PUBLISHER,
        )
        assert follow_up_publication.publication_revision_id is not None
        publication_revision_ids["FOLLOW_UP_REPORT"] = (
            follow_up_publication.publication_revision_id
        )
        follow_up_detail = await query_service.get_item(
            seeded.item_ids["FOLLOW_UP_REPORT"]
        )
        assert seeded.claim_ids["follow_up_deaths"] not in {
            claim.id for claim in follow_up_detail.claims
        }
        assert seeded.evidence_ids["follow_up_deaths"] not in {
            evidence.id for evidence in follow_up_detail.evidence
        }
        async with runtime_engine.connect() as connection:
            assert await connection.scalar(
                text("SELECT incident_status FROM event WHERE id = :event_id"),
                {"event_id": seeded.event_id},
            ) == "UNDER_INVESTIGATION"
        investigating_detail = await query_service.get_event(seeded.event_id)
        assert investigating_detail.incident_status.value == "UNDER_INVESTIGATION"
        assert [
            item.report_stage.value for item in investigating_detail.timeline.items
        ] == ["INITIAL_REPORT", "FOLLOW_UP_REPORT"]

        final_candidate_id = await candidate_service.generate_candidate(
            event_id=seeded.event_id,
            item_id=seeded.item_ids["FINAL_INVESTIGATION"],
        )
        assert final_candidate_id is not None
        seeded.event_link_candidate_ids["FINAL_INVESTIGATION"] = final_candidate_id
        await _decide_candidate(
            publication_service,
            "EVENT_LINK",
            seeded.event_link_candidate_ids["FINAL_INVESTIGATION"],
            reviewer_id=REVIEWER,
        )
        await _decide_candidate(
            publication_service,
            "EVENT_RELATION",
            seeded.relation_candidate_ids["INVESTIGATES"],
            reviewer_id=REVIEWER,
        )

        await _decide_candidate(
            publication_service,
            "CLAIM",
            seeded.claim_ids["final_deaths"],
            reviewer_id=REVIEWER,
        )
        second_conflict = _only_pending(await publication_service.list_claim_conflicts())
        assert {second_conflict.current_value, second_conflict.candidate_value} == {24, 52}
        await publication_service.resolve_claim_conflict(
            second_conflict.id,
            action="ACCEPT_CANDIDATE",
            reason="正式调查报告为最终伤亡依据，采用正式报告值",
            reviewer_id=REVIEWER,
        )
        await _decide_candidate(
            publication_service,
            "CLAIM",
            seeded.claim_ids["final_injuries"],
            reviewer_id=REVIEWER,
        )
        await _decide_candidate(
            publication_service,
            "CLAIM",
            seeded.claim_ids["final_causes"],
            reviewer_id=REVIEWER,
        )

        async with publisher_engine.connect() as connection:
            assert await connection.scalar(
                text(
                    "SELECT responsibility_findings FROM safety_case_profile "
                    "WHERE item_id = :item_id"
                ),
                {"item_id": seeded.item_ids["FINAL_INVESTIGATION"]},
            ) is None
        partially_reviewed = await query_service.get_review_task(final_review_task_id)
        partially_reviewed_statuses = {
            claim.claim_type: claim.decision_status
            for claim in partially_reviewed.claims
            if claim.id in final_claim_ids
        }
        assert partially_reviewed_statuses == {
            "deaths": "ACCEPTED",
            "injuries": "ACCEPTED",
            "official_direct_causes": "ACCEPTED",
            "responsibility_findings": "PENDING",
        }

        with pytest.raises(PublicationDenied) as self_publish:
            await publication_service.decide_review(
                final_review_task_id,
                action="APPROVE",
                reason="提交人不得审批自己的安全案例",
                reviewer_id=SUBMITTER,
            )
        assert "DUTIES_NOT_SEPARATED" in self_publish.value.reasons

        with pytest.raises(PublicationDenied) as unreviewed_formal_fact:
            await publication_service.decide_review(
                final_review_task_id,
                action="APPROVE",
                reason="验证未审核责任字段会阻断发布",
                reviewer_id=PUBLISHER,
            )
        assert "SAFETY_CASE_CRITICAL_CLAIM_UNREVIEWED" in unreviewed_formal_fact.value.reasons

        await _decide_candidate(
            publication_service,
            "CLAIM",
            seeded.claim_ids["final_responsibility"],
            reviewer_id=REVIEWER,
        )
        fully_reviewed = await query_service.get_review_task(final_review_task_id)
        assert {claim.decision_status for claim in fully_reviewed.claims} == {"ACCEPTED"}
        decision = await publication_service.decide_review(
            final_review_task_id,
            action="APPROVE",
            reason="正式调查事实、事件关系、冲突处置及安全审核均完整",
            reviewer_id=PUBLISHER,
        )
        assert decision.publication_revision_id is not None
        publication_revision_ids["FINAL_INVESTIGATION"] = decision.publication_revision_id

        for stage, claim_key in (
            ("ENFORCEMENT", "enforcement_actions"),
            ("RECTIFICATION", "rectification_open_issues"),
        ):
            relation_type = {
                "ENFORCEMENT": "PENALIZES",
                "RECTIFICATION": "RECTIFIES",
            }[stage]
            stage_candidate_id = await candidate_service.generate_candidate(
                event_id=seeded.event_id,
                item_id=seeded.item_ids[stage],
            )
            assert stage_candidate_id is not None
            seeded.event_link_candidate_ids[stage] = stage_candidate_id
            await _decide_candidate(
                publication_service,
                "EVENT_LINK",
                seeded.event_link_candidate_ids[stage],
                reviewer_id=REVIEWER,
            )
            await _decide_candidate(
                publication_service,
                "EVENT_RELATION",
                seeded.relation_candidate_ids[relation_type],
                reviewer_id=REVIEWER,
            )
            stage_review = await query_service.get_review_task(
                seeded.review_task_ids[stage]
            )
            stage_claims = {claim.id: claim for claim in stage_review.claims}
            assert stage_claims[seeded.claim_ids[claim_key]].decision_status == "ACCEPTED"
            assert {
                claim.decision_status
                for claim_id, claim in stage_claims.items()
                if claim_id != seeded.claim_ids[claim_key]
            } == {"ACCEPTED"}
            assert seeded.evidence_ids[claim_key] in {
                evidence.id for evidence in stage_review.evidence
            }
            assert all(claim.evidence_ids for claim in stage_claims.values())
            stage_decision = await publication_service.decide_review(
                seeded.review_task_ids[stage],
                action="APPROVE",
                reason=f"{stage} 固定官方样本证据已经人工审核",
                reviewer_id=PUBLISHER,
            )
            assert stage_decision.publication_revision_id is not None
            publication_revision_ids[stage] = stage_decision.publication_revision_id

        async with runtime_engine.connect() as connection:
            advanced_event = (
                (
                    await connection.execute(
                        text(
                            "SELECT incident_status, occurred_at, region_code, project_name, "
                            "accident_type, engineering_type FROM event WHERE id = :event_id"
                        ),
                        {"event_id": seeded.event_id},
                    )
                )
                .mappings()
                .one()
            )
        assert advanced_event["incident_status"] == "RECTIFICATION_FOLLOW_UP"
        assert advanced_event["occurred_at"] == datetime(2024, 4, 30, 17, 57, tzinfo=UTC)
        assert advanced_event["region_code"] == "441422"
        assert advanced_event["project_name"] == "梅大高速"
        assert advanced_event["accident_type"] == "ROADBED_COLLAPSE"
        assert advanced_event["engineering_type"] == "EXPRESSWAY"

        assert set(publication_revision_ids) == set(seeded.item_ids)

        async with publisher_engine.connect() as connection:
            reviewed_tasks = list(
                (
                    await connection.execute(
                        text(
                            "SELECT status, submitted_by, decided_by FROM review_task "
                            "WHERE id = ANY(CAST(:task_ids AS uuid[])) ORDER BY id"
                        ),
                        {"task_ids": list(seeded.review_task_ids.values())},
                    )
                ).mappings()
            )
        assert len(reviewed_tasks) == 5
        assert all(
            row["status"] == "APPROVED"
            and row["decided_by"] == PUBLISHER
            and row["submitted_by"] != row["decided_by"]
            for row in reviewed_tasks
        )

        detail = await query_service.get_event(seeded.event_id)
        assert detail.occurred_at == datetime(2024, 4, 30, 17, 57, tzinfo=UTC)
        assert detail.region == "广东省"
        assert detail.project_name == "梅大高速"
        assert [item.report_stage.value for item in detail.timeline.items] == [
            "INITIAL_REPORT",
            "FOLLOW_UP_REPORT",
            "FINAL_INVESTIGATION",
            "ENFORCEMENT",
            "RECTIFICATION",
        ]
        assert [
            item.relation_type.value if item.relation_type is not None else None
            for item in detail.timeline.items
        ] == [None, "FOLLOW_UP", "INVESTIGATES", "PENALIZES", "RECTIFIES"]
        assert detail.unverified_facts == []
        assert len(detail.relations) == 5
        assert all(
            item.evidence_count and item.evidence_count > 0
            for item in detail.timeline.items
        )
        assert detail.rectification_has_open_issues is True
        deaths = [
            fact.value for fact in detail.confirmed_facts if fact.field.value == "DEATH_COUNT"
        ]
        assert deaths == [52]
        selected = await query_service.get_feed(
            mode="selected",
            domain="safety",
            content_type="SAFETY_CASE",
            sort="latest",
            cursor=None,
            limit=20,
        )
        assert selected.items == []

        async with publisher_engine.connect() as connection:
            assert await connection.scalar(
                text("SELECT count(*) FROM event_item WHERE event_id = :event_id"),
                {"event_id": seeded.event_id},
            ) == 5
            candidate_rows = list(
                (
                    await connection.execute(
                        text(
                            "SELECT score, matched_dimensions, algorithm_version "
                            "FROM event_item_candidate WHERE event_id = :event_id "
                            "ORDER BY created_at, id"
                        ),
                        {"event_id": seeded.event_id},
                    )
                ).mappings()
            )
            assert len(candidate_rows) == 5
            assert all(
                row["score"] == 75
                and row["matched_dimensions"]
                == {
                    "date": 0,
                    "region": 20,
                    "project": 30,
                    "subject": 15,
                    "accident_type": 10,
                }
                for row in candidate_rows
            )
            assert {row["algorithm_version"] for row in candidate_rows} == {
                "safety-event-match-v1"
            }
            assert await connection.scalar(
                text("SELECT count(*) FROM event_relation WHERE event_id = :event_id"),
                {"event_id": seeded.event_id},
            ) == 5
            assert await connection.scalar(
                text(
                    "SELECT count(*) FROM safety_case_audit_event "
                    "WHERE target_type = 'EVENT_RELATION' AND action = 'CORRECTED' "
                    "AND target_id = :target_id"
                ),
                {"target_id": seeded.correction_candidate_id},
            ) == 1
            publication = (
                (
                    await connection.execute(
                        text(
                            "SELECT id, current_revision_id, status FROM publication "
                            "WHERE item_id = :item_id"
                        ),
                        {"item_id": seeded.item_ids["FINAL_INVESTIGATION"]},
                    )
                )
                .mappings()
                .one()
            )
            evaluation = await connection.scalar(
                text(
                    "SELECT evaluation FROM publication_revision "
                    "WHERE id = :revision_id"
                ),
                {"revision_id": publication["current_revision_id"]},
            )
            assert publication["status"] == "PUBLISHED"
            assert evaluation["policy_version"] == "4.0.0"
            assert evaluation["server"]["round04"]["event_assignment_confirmed"] is True
            assert (
                evaluation["server"]["round04"][
                    "unresolved_casualty_loss_conflict_count"
                ]
                == 0
            )

        withdrawal_revision_id = await publication_service.withdraw(
            publication["id"],
            reason="官方证据触发撤回演练，保留原发布修订和证据链",
            actor_id=PUBLISHER,
            evidence_id=seeded.evidence_ids["final_causes"],
        )
        async with publisher_engine.connect() as connection:
            withdrawn = (
                (
                    await connection.execute(
                        text(
                            "SELECT status, current_revision_id FROM publication "
                            "WHERE id = :publication_id"
                        ),
                        {"publication_id": publication["id"]},
                    )
                )
                .mappings()
                .one()
            )
            assert withdrawn == {
                "status": "WITHDRAWN",
                "current_revision_id": withdrawal_revision_id,
            }
            assert list(
                await connection.scalars(
                    text(
                        "SELECT action FROM publication_revision "
                        "WHERE publication_id = :publication_id ORDER BY revision_number"
                    ),
                    {"publication_id": publication["id"]},
                )
            ) == ["PUBLISH", "WITHDRAW"]
            assert await connection.scalar(
                text(
                    "SELECT count(*) FROM safety_case_audit_event "
                    "WHERE item_id = :item_id AND action = 'WITHDRAWN'"
                ),
                {"item_id": seeded.item_ids["FINAL_INVESTIGATION"]},
            ) == 1
            assert await connection.scalar(
                text(
                    "SELECT count(*) FROM audit_log "
                    "WHERE target_id = :publication_id "
                    "AND event_type = 'PUBLICATION_WITHDRAWN'"
                ),
                {"publication_id": publication["id"]},
            ) == 1
        withdrawn_detail = await query_service.get_event(seeded.event_id)
        assert len(withdrawn_detail.timeline.items) == 5
        assert withdrawn_detail.occurred_at is None
        assert all(
            fact.source_item_id != seeded.item_ids["FINAL_INVESTIGATION"]
            for fact in withdrawn_detail.confirmed_facts
        )
        withdrawn_stage = next(
            item
            for item in withdrawn_detail.timeline.items
            if item.report_stage.value == "FINAL_INVESTIGATION"
        )
        assert withdrawn_stage.document_states is not None
        assert {state.value for state in withdrawn_stage.document_states} == {"WITHDRAWN"}
    finally:
        await publication_service.close()
        await query_service.close()
        await source_service.close()
        await runtime_engine.dispose()


async def _decide_candidate(
    service: PublicationService,
    kind: str,
    candidate_id: UUID,
    *,
    action: str = "ACCEPT",
    reviewer_id: UUID,
) -> None:
    await service.decide_candidate(
        kind,  # type: ignore[arg-type]
        candidate_id,
        action=action,  # type: ignore[arg-type]
        target_document_id=None,
        reason=f"Round04 fixed-fixture {kind.lower()} human decision",
        reviewer_id=reviewer_id,
    )


def _only_pending(conflicts: list[Any]) -> Any:
    pending = [conflict for conflict in conflicts if conflict.status == "PENDING_REVIEW"]
    assert len(pending) == 1
    return pending[0]


def _artifacts() -> dict[str, Artifact]:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    result: dict[str, Artifact] = {}
    for row in manifest["artifacts"]:
        payload = base64.b64decode(
            (FIXTURE_ROOT / row["file"]).read_text(encoding="ascii"),
            validate=True,
        )
        assert sha256(payload).hexdigest() == row["sha256"]
        result[row["file"]] = Artifact(
            file_name=row["file"],
            source_url=row["source_url"],
            source_code=row["source_code"],
            authority_level=row["authority_level"],
            report_stage=row["report_stage"],
            declared_mime=row["declared_mime"].split(";", 1)[0],
            payload=payload,
        )
    return result


async def _store_official_artifacts(
    service: SourceRegistryService,
    artifacts: dict[str, Artifact],
) -> dict[str, StoredArtifact]:
    now = datetime.now(UTC)
    grouped: dict[str, list[Artifact]] = {code: [] for code in SOURCE_IDS}
    for artifact in artifacts.values():
        grouped[artifact.source_code].append(artifact)

    for source_code, source_id in SOURCE_IDS.items():
        domains = sorted(
            {
                str(urlsplit(artifact.source_url).hostname)
                for artifact in grouped[source_code]
            }
        )
        await service.transition(
            source_id,
            SourceTransitionRequest(
                target_state=SourceState.COMPLIANCE_REVIEW,
                reason="Round04 固定官方样本合规审核",
            ),
            actor_id=SUBMITTER,
            request_id=f"round04-compliance-{source_code}",
        )
        await service.save_policy(
            source_id,
            SourcePolicySubmission.model_validate(
                {
                    "policy_version": f"round04-{source_code.lower()}",
                    "status": "VALID",
                    "robots_review": {
                        "result": "ALLOWED",
                        "evidence_url": f"https://{domains[0]}/robots.txt",
                        "checked_at": now.isoformat(),
                    },
                    "terms_review": {
                        "result": "NOT_PRESENT",
                        "evidence_url": f"https://{domains[0]}/terms-review",
                        "checked_at": now.isoformat(),
                    },
                    "copyright": {
                        "storage_policy": "RAW_EVIDENCE_ALLOWED",
                        "display_policy": "METADATA_EXCERPT_LINK",
                        "fulltext_allowed": False,
                        "image_allowed": False,
                        "excerpt_max_chars": 300,
                        "attribution_template": "来源：{source_name}",
                    },
                    "access": {
                        "allowed_domains": domains,
                        "requires_auth": False,
                        "rate_limit_per_minute": 5,
                        "user_agent": "SRBGSourceAdapter/1.0",
                    },
                    "review": {
                        "valid_until": (now + timedelta(days=30)).isoformat(),
                        "approval_id": f"round04-{source_code.lower()}",
                    },
                }
            ),
            actor_id=SUBMITTER,
            request_id=f"round04-policy-{source_code}",
        )
        await service.transition(
            source_id,
            SourceTransitionRequest(
                target_state=SourceState.FIXTURE_TEST,
                reason="离线固定样本开始回放",
            ),
            actor_id=SUBMITTER,
            request_id=f"round04-fixture-state-{source_code}",
        )

    stored: dict[str, StoredArtifact] = {}
    for artifact in artifacts.values():
        response = await service.upload_fixture(
            SOURCE_IDS[artifact.source_code],
            content=artifact.payload,
            filename=artifact.file_name.removesuffix(".b64"),
            declared_mime=artifact.declared_mime,
            canonical_url=artifact.source_url,
            actor_id=SUBMITTER,
            request_id=f"round04-artifact-{artifact.file_name}",
        )
        stored[artifact.file_name] = StoredArtifact(
            artifact=artifact,
            document_id=response.document.id,
            document_version_id=response.document.current_version.id,
        )

    for source_code, source_id in SOURCE_IDS.items():
        domain = str(urlsplit(grouped[source_code][0].source_url).hostname)
        generic_fixture_count = 30 - len(grouped[source_code])
        for index in range(generic_fixture_count):
            content = (
                "<!doctype html><html><body>"
                f"Round04 {source_code} admission fixture {index:02d}"
                "</body></html>"
            ).encode()
            await service.upload_fixture(
                source_id,
                content=content,
                filename=f"{source_code.lower()}-admission-{index:02d}.html",
                declared_mime="text/html",
                canonical_url=(
                    f"https://{domain}/round04-offline-admission/"
                    f"{source_code.lower()}-{index:02d}.html"
                ),
                actor_id=SUBMITTER,
                request_id=f"round04-admission-{source_code}-{index:02d}",
            )
        await service.save_onboarding(
            source_id,
            SourceOnboardingSubmission(
                checks=[
                    OnboardingCheckEvidence(
                        code=code,
                        evidence_ref=f"https://{domain}/round04-evidence/{code}",
                    )
                    for code in sorted(REQUIRED_ONBOARDING_CHECKS)
                ],
                valid_until=now + timedelta(days=30),
            ),
            actor_id=SUBMITTER,
            request_id=f"round04-onboarding-{source_code}",
        )
        await service.transition(
            source_id,
            SourceTransitionRequest(
                target_state=SourceState.APPROVED,
                reason="30 个离线样本及合规证据已人工审核",
            ),
            actor_id=SUBMITTER,
            request_id=f"round04-approved-{source_code}",
        )
        active = await service.set_enabled(
            source_id,
            True,
            "启用 Round04 固定官方来源",
            actor_id=SUBMITTER,
            request_id=f"round04-active-{source_code}",
        )
        assert active.effective_active is True
    return stored


async def _seed_case(
    engine: AsyncEngine,
    stored: dict[str, StoredArtifact],
) -> SeededCase:
    event_id = uuid7()
    item_ids = {stage: uuid7() for stage in (
        "INITIAL_REPORT",
        "FOLLOW_UP_REPORT",
        "FINAL_INVESTIGATION",
        "ENFORCEMENT",
        "RECTIFICATION",
    )}
    selected = {
        "INITIAL_REPORT": stored["initial-report.html.b64"],
        "FOLLOW_UP_REPORT": stored["follow-up-report.html.b64"],
        "FINAL_INVESTIGATION": stored["investigation-report.pdf.b64"],
        "ENFORCEMENT": stored["accountability.html.b64"],
        "RECTIFICATION": stored["rectification-evaluation.html.b64"],
    }
    published_at = {
        "INITIAL_REPORT": datetime(2024, 5, 1, 12, 10, 42, tzinfo=UTC),
        "FOLLOW_UP_REPORT": datetime(2024, 5, 2, 12, 3, 56, tzinfo=UTC),
        "FINAL_INVESTIGATION": datetime(2025, 1, 22, 9, tzinfo=UTC),
        "ENFORCEMENT": datetime(2025, 1, 25, 4, tzinfo=UTC),
        "RECTIFICATION": datetime(2026, 3, 24, 6, 32, tzinfo=UTC),
    }
    occurred_at = {
        "INITIAL_REPORT": None,
        "FOLLOW_UP_REPORT": None,
        "FINAL_INVESTIGATION": datetime(2024, 4, 30, 17, 57, tzinfo=UTC),
        "ENFORCEMENT": None,
        "RECTIFICATION": None,
    }
    scenario_tags = {
        stage: ["HIGHWAY_OPERATION_GEOLOGICAL_RISK", "ROADBED_SLOPE_INSTABILITY"]
        for stage in (
            "INITIAL_REPORT",
            "FOLLOW_UP_REPORT",
            "FINAL_INVESTIGATION",
            "ENFORCEMENT",
            "RECTIFICATION",
        )
    }
    prevention_tags = {
        "INITIAL_REPORT": ["INSPECTION_AND_MAINTENANCE"],
        "FOLLOW_UP_REPORT": ["MONITORING_AND_EARLY_WARNING"],
        "FINAL_INVESTIGATION": [
            "MONITORING_AND_EARLY_WARNING",
            "INSPECTION_AND_MAINTENANCE",
            "RESPONSIBILITY_AND_OVERSIGHT",
        ],
        "ENFORCEMENT": [
            "INSPECTION_AND_MAINTENANCE",
            "RESPONSIBILITY_AND_OVERSIGHT",
        ],
        "RECTIFICATION": [
            "MONITORING_AND_EARLY_WARNING",
            "INSPECTION_AND_MAINTENANCE",
        ],
    }
    statuses = {
        "INITIAL_REPORT": "INITIAL_OFFICIAL_REPORT",
        "FOLLOW_UP_REPORT": "UNDER_INVESTIGATION",
        "FINAL_INVESTIGATION": "FINAL_INVESTIGATION_REPORT",
        "ENFORCEMENT": "ENFORCEMENT_DECISION",
        "RECTIFICATION": "RECTIFICATION_FOLLOW_UP",
    }
    titles = {
        "INITIAL_REPORT": "梅大高速茶阳路段塌方灾害初报",
        "FOLLOW_UP_REPORT": "梅大高速茶阳路段塌方灾害续报",
        "FINAL_INVESTIGATION": "梅大高速茶阳路段“5·1”塌方灾害调查评估报告",
        "ENFORCEMENT": "梅大高速塌方灾害责任追究通报",
        "RECTIFICATION": "梅大高速塌方灾害整改评估",
    }
    now = datetime.now(UTC)
    connector_ids = {code: uuid7() for code in SOURCE_IDS}
    paragraphs: dict[str, str] = {}
    pdf_blocks: dict[str, UUID] = {}
    pdf_page_texts: dict[int, str] = {}
    claim_ids: dict[str, UUID] = {}
    evidence_ids: dict[str, UUID] = {}
    event_link_ids: dict[str, UUID] = {}
    relation_ids: dict[str, UUID] = {}

    async with engine.begin() as connection:
        for source_code, connector_id in connector_ids.items():
            await connection.execute(
                text(
                    "INSERT INTO source_connector "
                    "(id, source_id, connector_type, config, enabled, created_at) "
                    "VALUES (:id, :source_id, 'ROUND04_FIXED_OFFICIAL', "
                    "'{}'::jsonb, true, :now)"
                ),
                {
                    "id": connector_id,
                    "source_id": SOURCE_IDS[source_code],
                    "now": now,
                },
            )

        for stage, value in selected.items():
            artifact = value.artifact
            fetch_run_id = uuid7()
            fetch_record_id = uuid7()
            await connection.execute(
                text(
                    "INSERT INTO fetch_run "
                    "(id, source_connector_id, trigger, status, started_at, completed_at, "
                    "discovered_count, fetched_count, failed_count, request_id) "
                    "VALUES (:id, :connector_id, 'FIXTURE', 'SUCCEEDED', :now, :now, "
                    "1, 1, 0, :request_id)"
                ),
                {
                    "id": fetch_run_id,
                    "connector_id": connector_ids[artifact.source_code],
                    "now": now,
                    "request_id": f"round04-{stage.lower()}",
                },
            )
            await connection.execute(
                text(
                    "INSERT INTO fetch_record "
                    "(id, fetch_run_id, source_connector_id, external_id, canonical_url, "
                    "discovered_title, discovered_at, status, http_status, attempt_count, "
                    "document_id, document_version_id, created_at, updated_at) "
                    "VALUES (:id, :run_id, :connector_id, :external_id, :url, :title, :now, "
                    "'FETCHED', 200, 1, :document_id, :version_id, :now, :now)"
                ),
                {
                    "id": fetch_record_id,
                    "run_id": fetch_run_id,
                    "connector_id": connector_ids[artifact.source_code],
                    "external_id": f"round04-{stage.lower()}",
                    "url": artifact.source_url,
                    "title": titles[stage],
                    "now": now,
                    "document_id": value.document_id,
                    "version_id": value.document_version_id,
                },
            )
            if artifact.declared_mime == "application/pdf":
                document = pymupdf.open(stream=artifact.payload, filetype="pdf")
                page_texts = {page: document[page - 1].get_text() for page in (4, 14, 23)}
                document.close()
                pdf_page_texts.update(page_texts)
                processing_paragraphs: list[dict[str, str]] = []
                for block_index, (page_number, page_text) in enumerate(page_texts.items()):
                    page_id = uuid7()
                    block_id = uuid7()
                    pdf_blocks[f"page_{page_number}"] = block_id
                    digest = sha256(page_text.encode()).hexdigest()
                    await connection.execute(
                        text(
                            "INSERT INTO document_page "
                            "(id, document_version_id, page_number, width_mpt, height_mpt, "
                            "rotation, text_source, normalized_text_sha256, preview_object_key, "
                            "preview_sha256, preview_mime, created_at) "
                            "VALUES (:id, :version_id, :page_number, 595000, 842000, 0, "
                            "'NATIVE', :digest, :preview_key, :preview_digest, 'image/png', :now)"
                        ),
                        {
                            "id": page_id,
                            "version_id": value.document_version_id,
                            "page_number": page_number,
                            "digest": digest,
                            "preview_key": f"round04/previews/{page_id}.png",
                            "preview_digest": sha256(f"preview-{page_id}".encode()).hexdigest(),
                            "now": now,
                        },
                    )
                    await connection.execute(
                        text(
                            "INSERT INTO document_text_block "
                            "(id, document_page_id, block_index, block_kind, text_source, text, "
                            "normalized_text, text_sha256, x0_mpt, y0_mpt, x1_mpt, y1_mpt, "
                            "confidence_bps, created_at) "
                            "VALUES (:id, :page_id, :block_index, 'BODY', 'NATIVE', :body, "
                            ":body, :digest, 0, 0, 595000, 842000, 10000, :now)"
                        ),
                        {
                            "id": block_id,
                            "page_id": page_id,
                            "block_index": block_index,
                            "body": page_text,
                            "digest": digest,
                            "now": now,
                        },
                    )
            else:
                normalized = _html_text(artifact.payload)
                paragraphs[stage] = normalized
                processing_paragraphs = [
                    {"paragraph_id": "html-p-0001", "text": normalized}
                ]
            await connection.execute(
                text(
                    "INSERT INTO processing_run "
                    "(id, fetch_record_id, document_version_id, parser_name, parser_version, "
                    "status, started_at, completed_at, paragraphs, semantic_safety_scan_pass, "
                    "prompt_injection_detected, security_resolution_status, "
                    "security_scanner_version, normalized_text_sha256, semantic_body_sha256, "
                    "metadata_sha256, page_count, ocr_page_count, ocr_usable_page_count, "
                    "low_confidence_critical_count) "
                    "VALUES (:id, :fetch_record_id, :version_id, 'round04-fixed-fixture', "
                    "'1.0.0', 'SUCCEEDED', :now, :now, CAST(:paragraphs AS jsonb), true, false, "
                    "'NONE', 'rules-1.0.0', :digest, :digest, :digest, :page_count, 0, 0, 0)"
                ),
                {
                    "id": uuid7(),
                    "fetch_record_id": fetch_record_id,
                    "version_id": value.document_version_id,
                    "now": now,
                    "paragraphs": _json(processing_paragraphs),
                    "digest": sha256(artifact.payload).hexdigest(),
                    "page_count": 31 if artifact.declared_mime == "application/pdf" else None,
                },
            )
            await connection.execute(
                text(
                    "INSERT INTO document_version_state_event "
                    "(id, document_version_id, state, reason_code, actor_type, created_at) "
                    "VALUES (:id, :version_id, 'READY', NULL, 'WORKER', :now)"
                ),
                {"id": uuid7(), "version_id": value.document_version_id, "now": now},
            )
            await connection.execute(
                text(
                    "INSERT INTO intelligence_item "
                    "(id, source_id, primary_document_id, current_document_version_id, "
                    "item_type, channel, risk_level, title, original_url, source_published_at, "
                    "first_discovered_at, activity_at, processing_status, review_status, "
                    "submitted_by, is_demo, publishable, created_at, updated_at) "
                    "VALUES (:id, :source_id, :document_id, :version_id, 'SAFETY_CASE', "
                    "'SAFETY', 'R3', :title, :url, :published_at, :now, :published_at, "
                    "'READY_FOR_REVIEW', 'PENDING', :submitted_by, false, true, :now, :now)"
                ),
                {
                    "id": item_ids[stage],
                    "source_id": SOURCE_IDS[artifact.source_code],
                    "document_id": value.document_id,
                    "version_id": value.document_version_id,
                    "title": titles[stage],
                    "url": artifact.source_url,
                    "published_at": published_at[stage],
                    "submitted_by": SUBMITTER,
                    "now": now,
                },
            )
            await connection.execute(
                text(
                    "INSERT INTO safety_case_profile "
                    "(item_id, report_stage, accident_type, engineering_type, occurred_at, "
                    "region_code, region_name, project_name, subject_names, deaths, injuries, "
                    "missing_count, loss_amount_minor, loss_currency, incident_status, "
                    "official_direct_causes, responsibility_findings, "
                    "rectification_has_open_issues, similar_scenario_tags, "
                    "prevention_measure_tags, privacy_status, privacy_reviewed_by, "
                    "privacy_reviewed_at, reputational_risk_reviewed, "
                    "reputational_reviewed_by, reputational_reviewed_at, created_at, updated_at) "
                    "VALUES (:item_id, :stage, 'ROADBED_COLLAPSE', 'EXPRESSWAY', :occurred_at, "
                    "'441422', '广东省', '梅大高速', "
                    "CAST(:subjects AS jsonb), NULL, NULL, NULL, NULL, NULL, :status, NULL, "
                    "NULL, :open_issues, CAST(:scenario_tags AS jsonb), "
                    "CAST(:prevention_tags AS jsonb), 'CLEAR', :reviewer, :now, true, "
                    ":reviewer, :now, :now, :now)"
                ),
                {
                    "item_id": item_ids[stage],
                    "stage": stage,
                    "occurred_at": occurred_at[stage],
                    "subjects": _json(["广东博大高速公路有限公司梅大分公司"]),
                    "status": statuses[stage],
                    "open_issues": True if stage == "RECTIFICATION" else None,
                    "scenario_tags": _json(scenario_tags[stage]),
                    "prevention_tags": _json(prevention_tags[stage]),
                    "reviewer": REVIEWER,
                    "now": now,
                },
            )

        await connection.execute(
            text(
                "INSERT INTO event "
                "(id, event_type, title, occurred_at, region_code, region_name, project_name, "
                "subject_names, accident_type, engineering_type, incident_status, "
                "confirmation_status, confirmed_by, confirmed_at, created_at, updated_at) "
                "VALUES (:id, 'SAFETY_INCIDENT', :title, NULL, NULL, NULL, NULL, "
                "'[]'::jsonb, NULL, NULL, 'UNVERIFIED_LEAD', "
                "'PENDING_REVIEW', NULL, NULL, :now, :now)"
            ),
            {
                "id": event_id,
                "title": "梅大高速茶阳路段“5·1”塌方灾害",
                "now": now,
            },
        )
        relations = [
            ("FOLLOW_UP_REPORT", "INITIAL_REPORT", "FOLLOW_UP"),
            ("FINAL_INVESTIGATION", "FOLLOW_UP_REPORT", "INVESTIGATES"),
            ("ENFORCEMENT", "FINAL_INVESTIGATION", "PENALIZES"),
            ("RECTIFICATION", "ENFORCEMENT", "RECTIFIES"),
            ("FOLLOW_UP_REPORT", "INITIAL_REPORT", "CORRECTS"),
        ]
        correction_candidate_id = UUID(int=0)
        for source_stage, target_stage, relation_type in relations:
            candidate_id = uuid7()
            relation_ids[relation_type] = candidate_id
            if relation_type == "CORRECTS":
                correction_candidate_id = candidate_id
            await connection.execute(
                text(
                    "INSERT INTO event_relation_candidate "
                    "(id, event_id, source_item_id, target_item_id, relation_type, "
                    "evidence_id, submitted_by, created_at) "
                    "VALUES (:id, :event_id, :source_id, :target_id, :relation_type, "
                    "NULL, :submitter, :now)"
                ),
                {
                    "id": candidate_id,
                    "event_id": event_id,
                    "source_id": item_ids[source_stage],
                    "target_id": item_ids[target_stage],
                    "relation_type": relation_type,
                    "submitter": SUBMITTER,
                    "now": now,
                },
            )

        forged_relation_candidate_id = uuid7()
        await connection.execute(
            text(
                "INSERT INTO event_relation_candidate "
                "(id, event_id, source_item_id, target_item_id, relation_type, "
                "evidence_id, submitted_by, created_at) "
                "VALUES (:id, :event_id, :source_id, :target_id, 'CORRECTS', "
                "NULL, :submitter, :now)"
            ),
            {
                "id": forged_relation_candidate_id,
                "event_id": event_id,
                "source_id": item_ids["INITIAL_REPORT"],
                "target_id": item_ids["FOLLOW_UP_REPORT"],
                "submitter": SUBMITTER,
                "now": now,
            },
        )

        async def insert_html_claim(
            key: str,
            stage: str,
            claim_type: str,
            value: object,
            needle: str,
            role: str = "PRIMARY_OFFICIAL",
            verification_status: str = "CANDIDATE",
            critical: bool = True,
        ) -> None:
            paragraph = paragraphs[stage]
            start = paragraph.index(needle)
            claim_id = uuid7()
            evidence_id = uuid7()
            claim_ids[key] = claim_id
            evidence_ids[key] = evidence_id
            selected_artifact = selected[stage]
            await _insert_claim(
                connection,
                claim_id=claim_id,
                evidence_id=evidence_id,
                item_id=item_ids[stage],
                version_id=selected_artifact.document_version_id,
                claim_type=claim_type,
                value=value,
                role=role,
                excerpt=needle,
                original_url=selected_artifact.artifact.source_url,
                now=now,
                paragraph_id="html-p-0001",
                char_start=start,
                char_end=start + len(needle),
                verification_status=verification_status,
                critical=critical,
            )

        profile_metadata_values: dict[str, dict[str, object]] = {}
        for stage in item_ids:
            profile_metadata_values[stage] = {
                "report_stage": stage,
                "incident_status": statuses[stage],
                "accident_type": "ROADBED_COLLAPSE",
                "engineering_type": "EXPRESSWAY",
                "region_name": "广东省",
                "project_name": "梅大高速",
                "similar_scenario_tags": scenario_tags[stage],
                "prevention_measure_tags": prevention_tags[stage],
            }
        profile_metadata_values["FINAL_INVESTIGATION"]["occurred_at"] = (
            "2024-05-01T01:57:00+08:00"
        )

        metadata_excerpts = {
            "INITIAL_REPORT": {
                "report_stage": "截至5月1日15时，经现场核查",
                "incident_status": "相关处置工作正在进行中",
                "accident_type": "梅大高速茶阳路段发生塌方灾害",
                "engineering_type": "梅大高速茶阳路段发生塌方灾害",
                "region_name": "广东省大埔县“5.1”路面塌陷灾害应急指挥部",
                "project_name": "梅大高速茶阳路段发生塌方灾害",
                "similar_scenario_tags": "梅大高速茶阳路段发生塌方灾害",
                "prevention_measure_tags": "进一步完善预案措施、排查风险隐患、加强安全防范",
            },
            "FOLLOW_UP_REPORT": {
                "report_stage": "梅州举行梅大高速茶阳路段塌方救援新闻发布会",
                "incident_status": "梅州举行梅大高速茶阳路段塌方救援新闻发布会",
                "accident_type": "5月1日2时01分许，梅大高速茶阳路段发生塌方灾害",
                "engineering_type": "5月1日2时01分许，梅大高速茶阳路段发生塌方灾害",
                "region_name": "广东省公安厅技术专家王小波表示",
                "project_name": "5月1日2时01分许，梅大高速茶阳路段发生塌方灾害",
                "similar_scenario_tags": "5月1日2时01分许，梅大高速茶阳路段发生塌方灾害",
                "prevention_measure_tags": "持续加强对大埔茶阳的气象监测和预报预警",
            },
            "ENFORCEMENT": {
                "report_stage": "对4个责任单位及32名公职人员进行了追责问责",
                "incident_status": "对4个责任单位及32名公职人员进行了追责问责",
                "accident_type": "梅大高速“5·1”塌方灾害",
                "engineering_type": "梅大高速“5·1”塌方灾害",
                "region_name": "广东省委批准",
                "project_name": "梅大高速“5·1”塌方灾害",
                "similar_scenario_tags": "梅大高速“5·1”塌方灾害",
                "prevention_measure_tags": (
                    "严格落实党政领导责任、部门监管责任、企业主体责任，"
                    "全链条排查管控各类安全风险"
                ),
            },
            "RECTIFICATION": {
                "report_stage": "整改措施落实情况的评估报告",
                "incident_status": "整改措施落实情况的评估报告",
                "accident_type": "梅大高速茶阳路段“5·1”塌方灾害",
                "engineering_type": "梅大高速茶阳路段“5·1”塌方灾害",
                "region_name": "广东省人民政府关于梅大高速",
                "project_name": "梅大高速茶阳路段“5·1”塌方灾害",
                "similar_scenario_tags": "梅大高速茶阳路段“5·1”塌方灾害",
                "prevention_measure_tags": (
                    "常态化推进交通风险隐患排查整治，从源头上防范化解重大风险，"
                    "特别是服役时间长、车流量大的重点路段要适当加密检查频次、加强动态监测"
                ),
            },
        }
        for stage, stage_excerpts in metadata_excerpts.items():
            for claim_type, claim_value in profile_metadata_values[stage].items():
                await insert_html_claim(
                    f"metadata:{stage}:{claim_type}",
                    stage,
                    claim_type,
                    claim_value,
                    stage_excerpts[claim_type],
                    verification_status="ACCEPTED",
                    critical=False,
                )

        await insert_html_claim(
            "initial_deaths", "INITIAL_REPORT", "deaths", 24, "确认死亡人数24人"
        )
        await insert_html_claim(
            "initial_media_cause",
            "INITIAL_REPORT",
            "official_direct_causes",
            ["媒体推测原因，不得进入正式原因字段"],
            "确认死亡人数24人",
            role="SECONDARY_REPORT",
        )
        await insert_html_claim(
            "follow_up_deaths", "FOLLOW_UP_REPORT", "deaths", 48, "48 人死亡"
        )
        await insert_html_claim(
            "enforcement_actions",
            "ENFORCEMENT",
            "enforcement_actions",
            ["4个责任单位及32名公职人员被追责问责"],
            "对4个责任单位及32名公职人员进行了追责问责",
            verification_status="ACCEPTED",
            critical=False,
        )
        await insert_html_claim(
            "rectification_open_issues",
            "RECTIFICATION",
            "rectification_has_open_issues",
            True,
            "仍然存在的薄弱环节",
            verification_status="ACCEPTED",
            critical=False,
        )

        final_value = selected["FINAL_INVESTIGATION"]
        final_page_text = pdf_page_texts[4]

        def final_sentence(needle: str) -> str:
            needle_start = final_page_text.index(needle)
            sentence_start = final_page_text.rfind("。", 0, needle_start) + 1
            sentence_end = final_page_text.find("。", needle_start)
            if sentence_end < 0:
                sentence_end = len(final_page_text) - 1
            return final_page_text[sentence_start : sentence_end + 1].strip()

        final_identity_excerpt = final_sentence("凌晨1 时57 分许")
        final_metadata_excerpts = {
            "report_stage": final_sentence("风险排查和调查评估"),
            "incident_status": final_sentence("风险排查和调查评估"),
            "accident_type": final_identity_excerpt,
            "engineering_type": final_identity_excerpt,
            "occurred_at": final_identity_excerpt,
            "region_name": final_sentence("广东省委、省政府"),
            "project_name": final_identity_excerpt,
            "similar_scenario_tags": final_identity_excerpt,
            "prevention_measure_tags": final_sentence("加强监测预警"),
        }
        for claim_type, claim_value in profile_metadata_values["FINAL_INVESTIGATION"].items():
            claim_key = f"metadata:FINAL_INVESTIGATION:{claim_type}"
            claim_id = uuid7()
            evidence_id = uuid7()
            claim_ids[claim_key] = claim_id
            evidence_ids[claim_key] = evidence_id
            await _insert_claim(
                connection,
                claim_id=claim_id,
                evidence_id=evidence_id,
                item_id=item_ids["FINAL_INVESTIGATION"],
                version_id=final_value.document_version_id,
                claim_type=claim_type,
                value=claim_value,
                role="PRIMARY_OFFICIAL",
                excerpt=final_metadata_excerpts[claim_type],
                original_url=final_value.artifact.source_url,
                now=now,
                locator_type="PDF_TEXT",
                page_number=4,
                block_id=pdf_blocks["page_4"],
                verification_status="ACCEPTED",
                critical=False,
            )
        pdf_claims = [
            (
                "final_deaths",
                "deaths",
                52,
                4,
                "造成52 人死亡，30 人受伤。",
            ),
            (
                "final_injuries",
                "injuries",
                30,
                4,
                "造成52 人死亡，30 人受伤。",
            ),
            (
                "final_causes",
                "official_direct_causes",
                ["长时间持续性降水与多种因素叠加耦合导致路堤塌方"],
                14,
                "长时间持续性降水与多种因素叠加耦合作用",
            ),
            (
                "final_responsibility",
                "responsibility_findings",
                ["相关责任人员问题线索移交有权机关处理"],
                23,
                "移交广东省纪委监委处理",
            ),
        ]
        for key, claim_type, claim_value, page_number, excerpt in pdf_claims:
            claim_id = uuid7()
            evidence_id = uuid7()
            claim_ids[key] = claim_id
            evidence_ids[key] = evidence_id
            await _insert_claim(
                connection,
                claim_id=claim_id,
                evidence_id=evidence_id,
                item_id=item_ids["FINAL_INVESTIGATION"],
                version_id=final_value.document_version_id,
                claim_type=claim_type,
                value=claim_value,
                role="PRIMARY_OFFICIAL",
                excerpt=excerpt,
                original_url=final_value.artifact.source_url,
                now=now,
                locator_type="PDF_TEXT",
                page_number=page_number,
                block_id=pdf_blocks[f"page_{page_number}"],
            )

        review_task_ids: dict[str, UUID] = {}
        for stage, stage_artifact in selected.items():
            source_policy_id = await connection.scalar(
                text(
                    "SELECT id FROM source_policy WHERE source_id = :source_id "
                    "ORDER BY created_at DESC, id DESC LIMIT 1"
                ),
                {"source_id": SOURCE_IDS[stage_artifact.artifact.source_code]},
            )
            assert isinstance(source_policy_id, UUID)
            review_task_id = uuid7()
            review_task_ids[stage] = review_task_id
            await connection.execute(
                text(
                    "INSERT INTO review_task "
                    "(id, item_id, document_version_id, source_policy_id, risk_level, status, "
                    "submitted_by, submitted_at, assigned_to, decided_by, decided_at, "
                    "decision_reason, created_at) VALUES (:id, :item_id, :version_id, "
                    ":policy_id, 'R3', 'PENDING', :submitter, :now, :publisher, NULL, NULL, "
                    "NULL, :now)"
                ),
                {
                    "id": review_task_id,
                    "item_id": item_ids[stage],
                    "version_id": stage_artifact.document_version_id,
                    "policy_id": source_policy_id,
                    "submitter": SUBMITTER,
                    "publisher": PUBLISHER,
                    "now": now,
                },
            )

    return SeededCase(
        event_id=event_id,
        item_ids=item_ids,
        event_link_candidate_ids=event_link_ids,
        relation_candidate_ids=relation_ids,
        correction_candidate_id=correction_candidate_id,
        forged_relation_candidate_id=forged_relation_candidate_id,
        claim_ids=claim_ids,
        evidence_ids=evidence_ids,
        review_task_ids=review_task_ids,
    )


async def _assert_round04_database_boundaries(
    engine: AsyncEngine,
    seeded: SeededCase,
    stored: dict[str, StoredArtifact],
) -> None:
    """Prove caller-supplied attribution and cross-document evidence fail at the DB boundary."""

    now = datetime.now(UTC)
    dimensions = _json(
        {"date": 0, "region": 20, "project": 30, "subject": 15, "accident_type": 10}
    )
    with pytest.raises(DBAPIError):
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "INSERT INTO event_item_candidate "
                    "(id, event_id, item_id, score, matched_dimensions, algorithm_version, "
                    "submitted_by, created_at) VALUES (:id, :event_id, :item_id, 75, "
                    "CAST(:dimensions AS jsonb), 'spoof-attribution-test', :spoofed_by, :now)"
                ),
                {
                    "id": uuid7(),
                    "event_id": seeded.event_id,
                    "item_id": seeded.item_ids["FOLLOW_UP_REPORT"],
                    "dimensions": dimensions,
                    "spoofed_by": REVIEWER,
                    "now": now,
                },
            )

    with pytest.raises(DBAPIError):
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "INSERT INTO event_relation_candidate "
                    "(id, event_id, source_item_id, target_item_id, relation_type, "
                    "evidence_id, submitted_by, created_at) VALUES "
                    "(:id, :event_id, :source_item_id, :target_item_id, 'PENALIZES', "
                    "NULL, :spoofed_by, :now)"
                ),
                {
                    "id": uuid7(),
                    "event_id": seeded.event_id,
                    "source_item_id": seeded.item_ids["INITIAL_REPORT"],
                    "target_item_id": seeded.item_ids["FOLLOW_UP_REPORT"],
                    "spoofed_by": REVIEWER,
                    "now": now,
                },
            )

    with pytest.raises(DBAPIError):
        async with engine.begin() as connection:
            target_submitter = UUID("019b0000-0000-7000-8000-000000009404")
            target_item_id = uuid7()
            relation_candidate_id = uuid7()
            follow_artifact = stored["follow-up-report.html.b64"]
            await connection.execute(
                text(
                    "INSERT INTO intelligence_item "
                    "(id, source_id, primary_document_id, current_document_version_id, "
                    "item_type, channel, risk_level, title, original_url, "
                    "source_published_at, first_discovered_at, activity_at, "
                    "processing_status, review_status, submitted_by, is_demo, publishable, "
                    "created_at, updated_at) VALUES "
                    "(:id, :source_id, :document_id, :version_id, 'SAFETY_CASE', 'SAFETY', "
                    "'R4', 'relation target submitter boundary', :url, :now, :now, :now, "
                    "'READY_FOR_REVIEW', 'PENDING', :submitter, true, false, :now, :now)"
                ),
                {
                    "id": target_item_id,
                    "source_id": SOURCE_IDS["GOV-019"],
                    "document_id": follow_artifact.document_id,
                    "version_id": follow_artifact.document_version_id,
                    "url": follow_artifact.artifact.source_url,
                    "submitter": target_submitter,
                    "now": now,
                },
            )
            await connection.execute(
                text(
                    "INSERT INTO event_relation_candidate "
                    "(id, event_id, source_item_id, target_item_id, relation_type, "
                    "evidence_id, submitted_by, created_at) VALUES "
                    "(:id, :event_id, :source_item_id, :target_item_id, 'PENALIZES', "
                    "NULL, :source_submitter, :now)"
                ),
                {
                    "id": relation_candidate_id,
                    "event_id": seeded.event_id,
                    "source_item_id": seeded.item_ids["INITIAL_REPORT"],
                    "target_item_id": target_item_id,
                    "source_submitter": SUBMITTER,
                    "now": now,
                },
            )
            await connection.execute(
                text(
                    "INSERT INTO event_relation_decision "
                    "(id, candidate_id, action, reviewer_id, submitted_by, reason, created_at) "
                    "VALUES (:id, :candidate_id, 'REJECT', :target_submitter, "
                    ":source_submitter, 'target submitter must not review relation', :now)"
                ),
                {
                    "id": uuid7(),
                    "candidate_id": relation_candidate_id,
                    "target_submitter": target_submitter,
                    "source_submitter": SUBMITTER,
                    "now": now,
                },
            )

    follow = stored["follow-up-report.html.b64"]
    follow_text = _html_text(follow.artifact.payload)
    follow_excerpt = "48 人死亡"
    follow_start = follow_text.index(follow_excerpt)
    with pytest.raises(DBAPIError):
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "INSERT INTO claim_evidence "
                    "(id, claim_id, document_version_id, evidence_role, paragraph_id, "
                    "char_start, char_end, excerpt, excerpt_sha256, original_url, "
                    "locator_type, confidence_bps, created_at) VALUES "
                    "(:id, :claim_id, :wrong_version_id, 'PRIMARY_OFFICIAL', "
                    "'html-p-0001', :char_start, :char_end, :excerpt, :digest, :url, "
                    "'HTML_PARAGRAPH', 10000, :now)"
                ),
                {
                    "id": uuid7(),
                    "claim_id": seeded.claim_ids["initial_deaths"],
                    "wrong_version_id": follow.document_version_id,
                    "char_start": follow_start,
                    "char_end": follow_start + len(follow_excerpt),
                    "excerpt": follow_excerpt,
                    "digest": sha256(follow_excerpt.encode()).hexdigest(),
                    "url": follow.artifact.source_url,
                    "now": now,
                },
            )

    final = stored["investigation-report.pdf.b64"]
    with pytest.raises(DBAPIError):
        async with engine.begin() as connection:
            wrong_page_id = uuid7()
            wrong_block_id = uuid7()
            wrong_text = "cross-version locator must be rejected"
            wrong_digest = sha256(wrong_text.encode()).hexdigest()
            await connection.execute(
                text(
                    "INSERT INTO document_page "
                    "(id, document_version_id, page_number, width_mpt, height_mpt, rotation, "
                    "text_source, normalized_text_sha256, created_at) VALUES "
                    "(:id, :version_id, 999, 595000, 842000, 0, 'NATIVE', :digest, :now)"
                ),
                {
                    "id": wrong_page_id,
                    "version_id": follow.document_version_id,
                    "digest": wrong_digest,
                    "now": now,
                },
            )
            await connection.execute(
                text(
                    "INSERT INTO document_text_block "
                    "(id, document_page_id, block_index, block_kind, text_source, text, "
                    "normalized_text, text_sha256, x0_mpt, y0_mpt, x1_mpt, y1_mpt, "
                    "confidence_bps, created_at) VALUES "
                    "(:id, :page_id, 0, 'BODY', 'NATIVE', :body, :body, :digest, "
                    "0, 0, 595000, 842000, 10000, :now)"
                ),
                {
                    "id": wrong_block_id,
                    "page_id": wrong_page_id,
                    "body": wrong_text,
                    "digest": wrong_digest,
                    "now": now,
                },
            )
            await connection.execute(
                text(
                    "INSERT INTO claim_evidence "
                    "(id, claim_id, document_version_id, evidence_role, excerpt, "
                    "excerpt_sha256, original_url, locator_type, page_number, "
                    "document_text_block_id, x0_mpt, y0_mpt, x1_mpt, y1_mpt, "
                    "confidence_bps, created_at) VALUES "
                    "(:id, :claim_id, :version_id, 'PRIMARY_OFFICIAL', :excerpt, :digest, "
                    ":url, 'PDF_TEXT', 999, :block_id, 0, 0, 595000, 842000, 10000, :now)"
                ),
                {
                    "id": uuid7(),
                    "claim_id": seeded.claim_ids["final_deaths"],
                    "version_id": final.document_version_id,
                    "excerpt": wrong_text,
                    "digest": wrong_digest,
                    "url": final.artifact.source_url,
                    "block_id": wrong_block_id,
                    "now": now,
                },
            )

    with pytest.raises(DBAPIError):
        async with engine.begin() as connection:
            external_claim_id = uuid7()
            await connection.execute(
                text(
                    "INSERT INTO claim "
                    "(id, item_id, document_version_id, claim_type, subject, predicate, "
                    "literal_value, verification_status, critical, confidence_bps, created_at) "
                    "VALUES (:id, :item_id, :external_version_id, 'ownership_probe', "
                    "'test', 'ownership_probe', CAST(:value AS jsonb), 'CANDIDATE', "
                    "false, 10000, :now)"
                ),
                {
                    "id": external_claim_id,
                    "item_id": seeded.item_ids["INITIAL_REPORT"],
                    "external_version_id": follow.document_version_id,
                    "value": _json("external"),
                    "now": now,
                },
            )
            await connection.execute(
                text(
                    "INSERT INTO claim_evidence "
                    "(id, claim_id, document_version_id, evidence_role, paragraph_id, "
                    "char_start, char_end, excerpt, excerpt_sha256, original_url, "
                    "locator_type, confidence_bps, created_at) VALUES "
                    "(:id, :claim_id, :version_id, 'PRIMARY_OFFICIAL', 'html-p-0001', "
                    ":char_start, :char_end, :excerpt, :digest, :url, "
                    "'HTML_PARAGRAPH', 10000, :now)"
                ),
                {
                    "id": uuid7(),
                    "claim_id": external_claim_id,
                    "version_id": follow.document_version_id,
                    "char_start": follow_start,
                    "char_end": follow_start + len(follow_excerpt),
                    "excerpt": follow_excerpt,
                    "digest": sha256(follow_excerpt.encode()).hexdigest(),
                    "url": follow.artifact.source_url,
                    "now": now,
                },
            )

    async with engine.connect() as connection:
        untrusted_source_id = await connection.scalar(
            text(
                "SELECT id FROM source WHERE authority_level NOT IN ('A0','A1') "
                "ORDER BY id LIMIT 1"
            )
        )
    assert isinstance(untrusted_source_id, UUID)
    with pytest.raises(DBAPIError):
        async with engine.begin() as connection:
            untrusted_raw_id = uuid7()
            untrusted_document_id = uuid7()
            untrusted_version_id = uuid7()
            untrusted_item_id = uuid7()
            untrusted_claim_id = uuid7()
            untrusted_page_id = uuid7()
            untrusted_block_id = uuid7()
            untrusted_text = "untrusted source cannot label itself PRIMARY_OFFICIAL"
            untrusted_digest = sha256(untrusted_text.encode()).hexdigest()
            untrusted_url = "https://example.invalid/round04/untrusted.pdf"
            await connection.execute(
                text(
                    "INSERT INTO raw_object "
                    "(id, sha256, object_key, byte_size, declared_mime, detected_mime, "
                    "scan_status, storage_etag, created_at) VALUES "
                    "(:id, :digest, :object_key, :byte_size, 'application/pdf', "
                    "'application/pdf', 'CLEAN', NULL, :now)"
                ),
                {
                    "id": untrusted_raw_id,
                    "digest": untrusted_digest,
                    "object_key": f"round04/untrusted/{untrusted_raw_id}",
                    "byte_size": len(untrusted_text.encode()),
                    "now": now,
                },
            )
            await connection.execute(
                text(
                    "INSERT INTO document "
                    "(id, source_id, canonical_url, document_kind, first_discovered_at, "
                    "current_version_id) VALUES "
                    "(:id, :source_id, :url, 'PDF', :now, NULL)"
                ),
                {
                    "id": untrusted_document_id,
                    "source_id": untrusted_source_id,
                    "url": untrusted_url,
                    "now": now,
                },
            )
            await connection.execute(
                text(
                    "INSERT INTO document_version "
                    "(id, document_id, raw_object_id, version_number, content_hash, "
                    "original_filename, title, acquired_at) VALUES "
                    "(:id, :document_id, :raw_id, 1, :digest, 'untrusted.pdf', "
                    "'untrusted evidence role test', :now)"
                ),
                {
                    "id": untrusted_version_id,
                    "document_id": untrusted_document_id,
                    "raw_id": untrusted_raw_id,
                    "digest": untrusted_digest,
                    "now": now,
                },
            )
            await connection.execute(
                text("UPDATE document SET current_version_id = :version_id WHERE id = :id"),
                {"version_id": untrusted_version_id, "id": untrusted_document_id},
            )
            await connection.execute(
                text(
                    "INSERT INTO intelligence_item "
                    "(id, source_id, primary_document_id, current_document_version_id, "
                    "item_type, channel, risk_level, title, original_url, "
                    "source_published_at, first_discovered_at, activity_at, "
                    "processing_status, review_status, submitted_by, is_demo, publishable, "
                    "created_at, updated_at) VALUES "
                    "(:id, :source_id, :document_id, :version_id, 'SAFETY_CASE', 'SAFETY', "
                    "'R4', 'untrusted evidence role test', :url, :now, :now, :now, "
                    "'READY_FOR_REVIEW', 'PENDING', :submitter, true, false, :now, :now)"
                ),
                {
                    "id": untrusted_item_id,
                    "source_id": untrusted_source_id,
                    "document_id": untrusted_document_id,
                    "version_id": untrusted_version_id,
                    "url": untrusted_url,
                    "submitter": SUBMITTER,
                    "now": now,
                },
            )
            await connection.execute(
                text(
                    "INSERT INTO claim "
                    "(id, item_id, document_version_id, claim_type, subject, predicate, "
                    "literal_value, verification_status, critical, confidence_bps, created_at) "
                    "VALUES (:id, :item_id, :version_id, 'region_name', 'test', "
                    "'region_name', CAST(:value AS jsonb), 'CANDIDATE', false, 10000, :now)"
                ),
                {
                    "id": untrusted_claim_id,
                    "item_id": untrusted_item_id,
                    "version_id": untrusted_version_id,
                    "value": _json("test"),
                    "now": now,
                },
            )
            await connection.execute(
                text(
                    "INSERT INTO document_page "
                    "(id, document_version_id, page_number, width_mpt, height_mpt, rotation, "
                    "text_source, normalized_text_sha256, created_at) VALUES "
                    "(:id, :version_id, 1, 595000, 842000, 0, 'NATIVE', :digest, :now)"
                ),
                {
                    "id": untrusted_page_id,
                    "version_id": untrusted_version_id,
                    "digest": untrusted_digest,
                    "now": now,
                },
            )
            await connection.execute(
                text(
                    "INSERT INTO document_text_block "
                    "(id, document_page_id, block_index, block_kind, text_source, text, "
                    "normalized_text, text_sha256, x0_mpt, y0_mpt, x1_mpt, y1_mpt, "
                    "confidence_bps, created_at) VALUES "
                    "(:id, :page_id, 0, 'BODY', 'NATIVE', :body, :body, :digest, "
                    "0, 0, 595000, 842000, 10000, :now)"
                ),
                {
                    "id": untrusted_block_id,
                    "page_id": untrusted_page_id,
                    "body": untrusted_text,
                    "digest": untrusted_digest,
                    "now": now,
                },
            )
            await connection.execute(
                text(
                    "INSERT INTO claim_evidence "
                    "(id, claim_id, document_version_id, evidence_role, excerpt, "
                    "excerpt_sha256, original_url, locator_type, page_number, "
                    "document_text_block_id, x0_mpt, y0_mpt, x1_mpt, y1_mpt, "
                    "confidence_bps, created_at) VALUES "
                    "(:id, :claim_id, :version_id, 'PRIMARY_OFFICIAL', :excerpt, :digest, "
                    ":url, 'PDF_TEXT', 1, :block_id, 0, 0, 595000, 842000, 10000, :now)"
                ),
                {
                    "id": uuid7(),
                    "claim_id": untrusted_claim_id,
                    "version_id": untrusted_version_id,
                    "excerpt": untrusted_text,
                    "digest": untrusted_digest,
                    "url": untrusted_url,
                    "block_id": untrusted_block_id,
                    "now": now,
                },
            )


async def _insert_claim(
    connection: Any,
    *,
    claim_id: UUID,
    evidence_id: UUID,
    item_id: UUID,
    version_id: UUID,
    claim_type: str,
    value: object,
    role: str,
    excerpt: str,
    original_url: str,
    now: datetime,
    paragraph_id: str | None = None,
    char_start: int | None = None,
    char_end: int | None = None,
    locator_type: str = "HTML_PARAGRAPH",
    page_number: int | None = None,
    block_id: UUID | None = None,
    verification_status: str = "CANDIDATE",
    critical: bool = True,
) -> None:
    await connection.execute(
        text(
            "INSERT INTO claim "
            "(id, item_id, document_version_id, claim_type, subject, predicate, "
            "literal_value, verification_status, critical, confidence_bps, created_at) "
            "VALUES (:id, :item_id, :version_id, :claim_type, '梅大高速塌方灾害', "
            ":claim_type, CAST(:value AS jsonb), :verification_status, :critical, "
            "10000, :now)"
        ),
        {
            "id": claim_id,
            "item_id": item_id,
            "version_id": version_id,
            "claim_type": claim_type,
            "value": _json(value),
            "verification_status": verification_status,
            "critical": critical,
            "now": now,
        },
    )
    await connection.execute(
        text(
            "INSERT INTO claim_evidence "
            "(id, claim_id, document_version_id, evidence_role, paragraph_id, char_start, "
            "char_end, excerpt, excerpt_sha256, original_url, locator_type, page_number, "
            "document_text_block_id, x0_mpt, y0_mpt, x1_mpt, y1_mpt, confidence_bps, "
            "created_at) VALUES (:id, :claim_id, :version_id, :role, :paragraph_id, "
            ":char_start, :char_end, :excerpt, :digest, :original_url, :locator_type, "
            ":page_number, :block_id, :x0, :y0, :x1, :y1, 10000, :now)"
        ),
        {
            "id": evidence_id,
            "claim_id": claim_id,
            "version_id": version_id,
            "role": role,
            "paragraph_id": paragraph_id,
            "char_start": char_start,
            "char_end": char_end,
            "excerpt": excerpt,
            "digest": sha256(excerpt.encode()).hexdigest(),
            "original_url": original_url,
            "locator_type": locator_type,
            "page_number": page_number,
            "block_id": block_id,
            "x0": 0 if block_id is not None else None,
            "y0": 0 if block_id is not None else None,
            "x1": 595000 if block_id is not None else None,
            "y1": 842000 if block_id is not None else None,
            "now": now,
        },
    )


def _html_text(payload: bytes) -> str:
    value = payload.decode("utf-8")
    value = re.sub(r"<script\b[^>]*>.*?</script>", " ", value, flags=re.I | re.S)
    value = re.sub(r"<style\b[^>]*>.*?</style>", " ", value, flags=re.I | re.S)
    value = html.unescape(re.sub(r"<[^>]+>", " ", value))
    return re.sub(r"\s+", " ", value).strip()


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
