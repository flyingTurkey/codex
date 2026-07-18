from datetime import UTC, datetime
from uuid import UUID

from srbg_contracts import (
    AutomaticRelationshipView,
    OwnerRelationshipCorrectionRequest,
    SourceLineageRole,
)


def test_source_roles_keep_vendor_media_and_independent_verification_separate() -> None:
    assert SourceLineageRole.VENDOR_STATEMENT != SourceLineageRole.MEDIA_REPORT
    assert SourceLineageRole.MEDIA_REPORT != SourceLineageRole.INDEPENDENT_VERIFICATION


def test_automatic_relationship_exposes_version_and_explanation() -> None:
    view = AutomaticRelationshipView(
        id=UUID("019b0000-0000-7000-8000-000000008001"),
        relationship_key="duplicate:a:b",
        kind="DUPLICATE",
        source_item_id=UUID("019b0000-0000-7000-8000-000000008002"),
        target_item_id=UUID("019b0000-0000-7000-8000-000000008003"),
        status="ACTIVE",
        score_bps=9700,
        reason_codes=["HIGH_CONFIDENCE"],
        algorithm_version="pers08-relations-v1",
        model_version="pers08-model-v1",
        input_fingerprint_sha256="a" * 64,
        created_at=datetime(2026, 7, 18, tzinfo=UTC),
    )
    assert view.score_bps == 9700


def test_split_command_requires_complete_item_allocation() -> None:
    request = OwnerRelationshipCorrectionRequest.model_validate(
        {
            "command_id": "019b0000-0000-7000-8000-000000008010",
            "action": "SPLIT_EVENT",
            "reason": "two incidents were grouped together",
            "allocations": [
                {
                    "item_id": "019b0000-0000-7000-8000-000000008002",
                    "child_event_id": "019b0000-0000-7000-8000-000000008020",
                }
            ],
        }
    )
    assert request.action == "SPLIT_EVENT"
