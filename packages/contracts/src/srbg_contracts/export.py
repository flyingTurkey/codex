"""Generate deterministic JSON Schema artifacts from canonical models."""

import json
from pathlib import Path

from pydantic import BaseModel

from srbg_contracts.models import (
    ClaimView,
    CreateSourceRequest,
    CursorPage,
    DocumentDetail,
    DocumentPageView,
    EvidenceView,
    FeedNotice,
    FeedPage,
    FixtureUploadResponse,
    ItemDetail,
    ItemSummary,
    LivenessResponse,
    MeResponse,
    ProblemDetails,
    ReadinessResponse,
    ReviewCandidateDecisionRequest,
    ReviewDecisionRequest,
    ReviewDecisionResponse,
    ReviewTaskDetail,
    ReviewTaskSummary,
    SourceActionRequest,
    SourceDetail,
    SourceOnboardingSubmission,
    SourcePolicySubmission,
    SourceSummary,
    SourceTransitionRequest,
    TypeSummary,
    VersionChangeEscalationRequest,
    VersionDiffResponse,
    VersionResponse,
    VersionTimelineResponse,
)

SCHEMA_MODELS: dict[str, type[BaseModel]] = {
    "cursor-page.schema.json": CursorPage[dict[str, str | int | bool | None]],
    "create-source-request.schema.json": CreateSourceRequest,
    "claim-view.schema.json": ClaimView,
    "document-detail.schema.json": DocumentDetail,
    "document-page-view.schema.json": DocumentPageView,
    "feed-notice.schema.json": FeedNotice,
    "feed-page.schema.json": FeedPage,
    "evidence-view.schema.json": EvidenceView,
    "fixture-upload-response.schema.json": FixtureUploadResponse,
    "liveness-response.schema.json": LivenessResponse,
    "item-summary.schema.json": ItemSummary,
    "item-detail.schema.json": ItemDetail,
    "me-response.schema.json": MeResponse,
    "problem-details.schema.json": ProblemDetails,
    "readiness-response.schema.json": ReadinessResponse,
    "review-decision-request.schema.json": ReviewDecisionRequest,
    "review-decision-response.schema.json": ReviewDecisionResponse,
    "review-candidate-decision-request.schema.json": ReviewCandidateDecisionRequest,
    "review-task-detail.schema.json": ReviewTaskDetail,
    "review-task-summary.schema.json": ReviewTaskSummary,
    "source-action-request.schema.json": SourceActionRequest,
    "source-detail.schema.json": SourceDetail,
    "source-onboarding-submission.schema.json": SourceOnboardingSubmission,
    "source-policy-submission.schema.json": SourcePolicySubmission,
    "source-summary.schema.json": SourceSummary,
    "source-transition-request.schema.json": SourceTransitionRequest,
    "type-summary.schema.json": TypeSummary,
    "version-diff-response.schema.json": VersionDiffResponse,
    "version-change-escalation-request.schema.json": VersionChangeEscalationRequest,
    "version-response.schema.json": VersionResponse,
    "version-timeline-response.schema.json": VersionTimelineResponse,
}


def render_schemas() -> dict[str, str]:
    return {
        filename: json.dumps(
            model.model_json_schema(), ensure_ascii=False, indent=2, sort_keys=True
        )
        + "\n"
        for filename, model in SCHEMA_MODELS.items()
    }


def write_schemas(output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for filename, content in render_schemas().items():
        (output_dir / filename).write_text(content, encoding="utf-8", newline="\n")


def main() -> None:
    repository_root = Path(__file__).resolve().parents[4]
    write_schemas(repository_root / "packages/contracts/generated/json-schema")


if __name__ == "__main__":
    main()
