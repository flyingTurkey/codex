from datetime import UTC, datetime
from uuid import UUID

from fastapi.testclient import TestClient
from srbg_api.main import create_app
from srbg_contracts import (
    DocumentPageView,
    VersionDiffResponse,
    VersionTimelineEntry,
    VersionTimelineResponse,
)

ITEM_ID = UUID("019b0000-0000-7000-8000-000000007001")
V1 = UUID("019b0000-0000-7000-8000-000000007002")
V2 = UUID("019b0000-0000-7000-8000-000000007003")
CANDIDATE_ID = UUID("019b0000-0000-7000-8000-000000007004")
CHANGE_ID = UUID("019b0000-0000-7000-8000-000000007005")
NOW = datetime(2026, 7, 14, tzinfo=UTC)


class PdfQueryStub:
    restricted_flags: list[bool]

    def __init__(self) -> None:
        self.restricted_flags = []

    async def get_versions(
        self, item_id: UUID, *, include_restricted: bool
    ) -> VersionTimelineResponse:
        assert item_id == ITEM_ID
        self.restricted_flags.append(include_restricted)
        return VersionTimelineResponse(
            item_id=item_id,
            versions=[
                VersionTimelineEntry(
                    version_id=V2,
                    version_number=2,
                    processing_state="READY",
                    change_type="CONTENT_UPDATE",
                    material=True,
                    review_state="RE_REVIEW_PENDING",
                    acquired_at=NOW,
                    is_current=True,
                )
            ],
        )

    async def get_diff(self, item_id: UUID, **kwargs: object) -> VersionDiffResponse:
        assert item_id == ITEM_ID
        self.restricted_flags.append(bool(kwargs["include_restricted"]))
        return VersionDiffResponse(
            item_id=item_id,
            from_version_id=V1,
            to_version_id=V2,
            change_type="CONTENT_UPDATE",
            material=True,
            changed_token_count=12,
            changed_token_ratio_bps=50,
            pages=[],
            critical_fields=[],
        )

    async def get_document_page(
        self, document_version_id: UUID, page_number: int, *, include_restricted: bool
    ) -> DocumentPageView:
        self.restricted_flags.append(include_restricted)
        return DocumentPageView(
            document_version_id=document_version_id,
            page_number=page_number,
            page_count=3,
            width_mpt=595000,
            height_mpt=842000,
            rotation=0,
            text_source="OCR",
            preview_url=f"/api/v1/document-versions/{document_version_id}/pages/{page_number}/preview",
        )

    async def get_page_preview(
        self, document_version_id: UUID, page_number: int, *, include_restricted: bool
    ) -> tuple[bytes, str]:
        self.restricted_flags.append(include_restricted)
        return b"\x89PNG\r\n\x1a\nfixture", "a" * 64


class CandidateDecisionStub:
    def __init__(self) -> None:
        self.calls: list[tuple[str, UUID, str]] = []

    async def decide_candidate(self, kind: str, candidate_id: UUID, **values: object) -> None:
        self.calls.append((kind, candidate_id, str(values["action"])))

    async def escalate_version_change(self, change_id: UUID, **values: object) -> None:
        self.calls.append(("VERSION_CHANGE", change_id, str(values["reason"])))


def test_version_diff_and_preview_propagate_server_acl_projection() -> None:
    query = PdfQueryStub()
    app = create_app(
        checkers={},
        source_service=None,
        intelligence_service=query,
        publication_service=None,
    )
    client = TestClient(app, headers={"X-SRBG-Local-Step-Up": "true"})

    viewer = client.get(
        f"/api/v1/items/{ITEM_ID}/versions",
        headers={"X-SRBG-Local-Roles": "viewer"},
    )
    reviewer = client.get(
        f"/api/v1/items/{ITEM_ID}/diff?from={V1}&to={V2}",
        headers={"X-SRBG-Local-Roles": "reviewer"},
    )
    preview = client.get(
        f"/api/v1/document-versions/{V2}/pages/2/preview",
        headers={"X-SRBG-Local-Roles": "reviewer"},
    )

    assert viewer.status_code == 200
    assert reviewer.status_code == 200
    assert preview.status_code == 200
    assert preview.headers["content-type"] == "image/png"
    assert preview.headers["cache-control"] == "private, max-age=300"
    assert query.restricted_flags == [False, True, True]


def test_candidate_decisions_and_material_escalation_are_reviewer_only() -> None:
    publication = CandidateDecisionStub()
    app = create_app(
        checkers={},
        source_service=None,
        intelligence_service=PdfQueryStub(),
        publication_service=publication,
    )
    client = TestClient(app, headers={"X-SRBG-Local-Step-Up": "true"})

    forbidden = client.post(
        f"/api/v1/admin/review-candidates/RELATION/{CANDIDATE_ID}/decisions",
        headers={"X-SRBG-Local-Roles": "viewer"},
        json={"action": "CONFIRM_UNRESOLVED", "reason": "目标尚未唯一匹配"},
    )
    accepted = client.post(
        f"/api/v1/admin/review-candidates/RELATION/{CANDIDATE_ID}/decisions",
        headers={"X-SRBG-Local-Roles": "reviewer"},
        json={"action": "CONFIRM_UNRESOLVED", "reason": "目标尚未唯一匹配"},
    )
    escalated = client.post(
        f"/api/v1/admin/version-changes/{CHANGE_ID}/escalations",
        headers={"X-SRBG-Local-Roles": "reviewer"},
        json={"reason": "页码重锚不唯一"},
    )

    assert forbidden.status_code == 403
    assert accepted.status_code == 204
    assert escalated.status_code == 204
    assert publication.calls == [
        ("RELATION", CANDIDATE_ID, "CONFIRM_UNRESOLVED"),
        ("VERSION_CHANGE", CHANGE_ID, "页码重锚不唯一"),
    ]
