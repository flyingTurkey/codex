"""Generate deterministic JSON Schema artifacts from canonical models."""

import json
from pathlib import Path

from pydantic import BaseModel

from srbg_contracts.models import (
    ClaimConflict,
    ClaimConflictDecisionRequest,
    ClaimConflictDecisionResponse,
    ClaimView,
    ClusterCandidateView,
    ClusterDecisionRequest,
    CollectionCreateRequest,
    CollectionPatchRequest,
    CollectionSummary,
    ConfirmedFact,
    CreateSourceRequest,
    CursorPage,
    DailyDraftRequest,
    DailyReport,
    DigitalCaseDetail,
    DigitalCaseReviewPatch,
    DocumentDetail,
    DocumentPageView,
    EventCandidateGenerationResponse,
    EventDetail,
    EventItem,
    EventRelationView,
    EventTimeline,
    EvidenceView,
    FeedbackRequest,
    FeedNotice,
    FeedPage,
    FingerprintResponse,
    FixtureUploadResponse,
    HotTopicPage,
    ItemDetail,
    ItemSummary,
    LivenessResponse,
    MeResponse,
    MetricSample,
    OperationsOverview,
    PaperDetail,
    PilotMetrics,
    ProblemDetails,
    ProductNormalizationCandidateView,
    ProductNormalizationDecisionRequest,
    PublicationRevisionRequest,
    PublicationWithdrawalRequest,
    ReadinessResponse,
    ReplayRequest,
    ReplayResult,
    ReviewCandidateDecisionRequest,
    ReviewDecisionRequest,
    ReviewDecisionResponse,
    ReviewTaskDetail,
    ReviewTaskSummary,
    SaveItemRequest,
    ScoreOverrideRequest,
    ScoreSummary,
    SearchContext,
    SourceActionRequest,
    SourceComparison,
    SourceDetail,
    SourceOnboardingSubmission,
    SourcePolicySubmission,
    SourceSummary,
    SourceTransitionRequest,
    TechnologyProductDetail,
    TypeSummary,
    UnverifiedFact,
    VersionChangeEscalationRequest,
    VersionDiffResponse,
    VersionResponse,
    VersionTimelineResponse,
)

SCHEMA_MODELS: dict[str, type[BaseModel]] = {
    "feedback-request.schema.json": FeedbackRequest,
    "metric-sample.schema.json": MetricSample,
    "operations-overview.schema.json": OperationsOverview,
    "pilot-metrics.schema.json": PilotMetrics,
    "replay-request.schema.json": ReplayRequest,
    "replay-result.schema.json": ReplayResult,
    "collection-create-request.schema.json": CollectionCreateRequest,
    "collection-patch-request.schema.json": CollectionPatchRequest,
    "collection-summary.schema.json": CollectionSummary,
    "cursor-page.schema.json": CursorPage[dict[str, str | int | bool | None]],
    "digital-case-detail.schema.json": DigitalCaseDetail,
    "digital-case-review-patch.schema.json": DigitalCaseReviewPatch,
    "daily-draft-request.schema.json": DailyDraftRequest,
    "daily-report.schema.json": DailyReport,
    "paper-detail.schema.json": PaperDetail,
    "technology-product-detail.schema.json": TechnologyProductDetail,
    "create-source-request.schema.json": CreateSourceRequest,
    "claim-view.schema.json": ClaimView,
    "claim-conflict.schema.json": ClaimConflict,
    "claim-conflict-decision-request.schema.json": ClaimConflictDecisionRequest,
    "claim-conflict-decision-response.schema.json": ClaimConflictDecisionResponse,
    "confirmed-fact.schema.json": ConfirmedFact,
    "document-detail.schema.json": DocumentDetail,
    "document-page-view.schema.json": DocumentPageView,
    "feed-notice.schema.json": FeedNotice,
    "feed-page.schema.json": FeedPage,
    "fingerprint-response.schema.json": FingerprintResponse,
    "hot-topic-page.schema.json": HotTopicPage,
    "evidence-view.schema.json": EvidenceView,
    "event-candidate-generation-response.schema.json": EventCandidateGenerationResponse,
    "event-detail.schema.json": EventDetail,
    "cluster-candidate-view.schema.json": ClusterCandidateView,
    "cluster-decision-request.schema.json": ClusterDecisionRequest,
    "event-item.schema.json": EventItem,
    "event-relation-view.schema.json": EventRelationView,
    "event-timeline.schema.json": EventTimeline,
    "fixture-upload-response.schema.json": FixtureUploadResponse,
    "liveness-response.schema.json": LivenessResponse,
    "item-summary.schema.json": ItemSummary,
    "item-detail.schema.json": ItemDetail,
    "me-response.schema.json": MeResponse,
    "problem-details.schema.json": ProblemDetails,
    "product-normalization-candidate.schema.json": ProductNormalizationCandidateView,
    "product-normalization-decision-request.schema.json": ProductNormalizationDecisionRequest,
    "publication-revision-request.schema.json": PublicationRevisionRequest,
    "publication-withdrawal-request.schema.json": PublicationWithdrawalRequest,
    "score-override-request.schema.json": ScoreOverrideRequest,
    "score-summary.schema.json": ScoreSummary,
    "save-item-request.schema.json": SaveItemRequest,
    "search-context.schema.json": SearchContext,
    "readiness-response.schema.json": ReadinessResponse,
    "review-decision-request.schema.json": ReviewDecisionRequest,
    "review-decision-response.schema.json": ReviewDecisionResponse,
    "review-candidate-decision-request.schema.json": ReviewCandidateDecisionRequest,
    "review-task-detail.schema.json": ReviewTaskDetail,
    "review-task-summary.schema.json": ReviewTaskSummary,
    "source-action-request.schema.json": SourceActionRequest,
    "source-comparison.schema.json": SourceComparison,
    "source-detail.schema.json": SourceDetail,
    "source-onboarding-submission.schema.json": SourceOnboardingSubmission,
    "source-policy-submission.schema.json": SourcePolicySubmission,
    "source-summary.schema.json": SourceSummary,
    "source-transition-request.schema.json": SourceTransitionRequest,
    "type-summary.schema.json": TypeSummary,
    "unverified-fact.schema.json": UnverifiedFact,
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
