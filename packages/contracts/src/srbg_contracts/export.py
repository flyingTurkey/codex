"""Generate deterministic JSON Schema artifacts from canonical models."""

import json
from pathlib import Path

from pydantic import BaseModel

from srbg_contracts.models import (
    AiSummaryV2,
    AutomaticRelationshipView,
    AutonomousClassificationCandidate,
    ClaimView,
    CollectionCreateRequest,
    CollectionPatchRequest,
    CollectionSummary,
    ConfirmedFact,
    CursorPage,
    DailyReport,
    DigitalCaseDetail,
    DiscoveryDailyUsageView,
    DiscoverySettingPatchRequest,
    DiscoverySettingView,
    DiscoveryTopicPatchRequest,
    DiscoveryTopicView,
    DocumentDetail,
    DocumentPageView,
    EventAppendixV2,
    EventAutomaticResultView,
    EventDetail,
    EventFullProjectionV2,
    EventItem,
    EventMetadataProjectionV2,
    EventRelationView,
    EventTimeline,
    EvidenceView,
    FeedbackRequest,
    FeedNotice,
    FeedPage,
    FeedPageV2,
    FeedSuppressionCommand,
    FeedSuppressionRuleView,
    FingerprintResponse,
    FixtureUploadResponse,
    HotspotCandidateV2,
    HotTopicPage,
    ItemDetail,
    ItemSummary,
    LivenessResponse,
    MeResponse,
    MetricSample,
    OwnerExceptionCommand,
    OwnerExceptionEventView,
    OwnerExceptionView,
    OwnerRelationshipCorrectionRequest,
    OwnerRelationshipCorrectionResponse,
    PaperDetail,
    PersonalSourceActivityPage,
    PersonalSourceCreateRequest,
    PersonalSourcePatchRequest,
    PersonalSourceReprobeRequest,
    PersonalSourceStreamView,
    PersonalSourceView,
    PolicyEvaluationSummary,
    ProblemDetails,
    PublishedEventDetailV1,
    PublishedEventSummaryV1,
    QuarantineProjectionV2,
    ReadinessResponse,
    ReviewCaseV2,
    ReviewDecisionCommandV2,
    ReviewDecisionReceiptV2,
    SaveItemRequest,
    ScoreSummary,
    SearchContext,
    ShadowDecisionView,
    SourceAutoScoreDetailView,
    SourceAutoScoreSummaryView,
    SourceComparison,
    SourceProfileModelOutput,
    SourceProfileOverrideRequest,
    SourceProfileView,
    StreamProbeRunView,
    TechnologyProductDetail,
    TypeSummary,
    UnverifiedFact,
    VersionDiffResponse,
    VersionResponse,
    VersionTimelineResponse,
)

SCHEMA_MODELS: dict[str, type[BaseModel]] = {
    "autonomous-classify-output.schema.json": AutonomousClassificationCandidate,
    "feed-suppression-command.schema.json": FeedSuppressionCommand,
    "feed-suppression-rule-view.schema.json": FeedSuppressionRuleView,
    "owner-exception-command.schema.json": OwnerExceptionCommand,
    "owner-exception-event-view.schema.json": OwnerExceptionEventView,
    "owner-exception-view.schema.json": OwnerExceptionView,
    "policy-evaluation-summary.schema.json": PolicyEvaluationSummary,
    "shadow-decision-view.schema.json": ShadowDecisionView,
    "ai-summary-v2.schema.json": AiSummaryV2,
    "event-appendix-v2.schema.json": EventAppendixV2,
    "event-full-projection-v2.schema.json": EventFullProjectionV2,
    "event-metadata-projection-v2.schema.json": EventMetadataProjectionV2,
    "feed-page-v2.schema.json": FeedPageV2,
    "review-decision-command-v2.schema.json": ReviewDecisionCommandV2,
    "review-decision-receipt-v2.schema.json": ReviewDecisionReceiptV2,
    "review-case-v2.schema.json": ReviewCaseV2,
    "quarantine-projection-v2.schema.json": QuarantineProjectionV2,
    "hotspot-candidate-v2.schema.json": HotspotCandidateV2,
    "feedback-request.schema.json": FeedbackRequest,
    "metric-sample.schema.json": MetricSample,
    "personal-source-patch-request.schema.json": PersonalSourcePatchRequest,
    "personal-source-create-request.schema.json": PersonalSourceCreateRequest,
    "personal-source-reprobe-request.schema.json": PersonalSourceReprobeRequest,
    "personal-source-stream-view.schema.json": PersonalSourceStreamView,
    "stream-probe-run-view.schema.json": StreamProbeRunView,
    "personal-source-view.schema.json": PersonalSourceView,
    "personal-source-activity-page.schema.json": PersonalSourceActivityPage,
    "discovery-setting-patch-request.schema.json": DiscoverySettingPatchRequest,
    "discovery-setting-view.schema.json": DiscoverySettingView,
    "discovery-topic-patch-request.schema.json": DiscoveryTopicPatchRequest,
    "discovery-topic-view.schema.json": DiscoveryTopicView,
    "discovery-daily-usage-view.schema.json": DiscoveryDailyUsageView,
    "source-auto-score-summary-view.schema.json": SourceAutoScoreSummaryView,
    "source-auto-score-detail-view.schema.json": SourceAutoScoreDetailView,
    "source-profile-model-output.schema.json": SourceProfileModelOutput,
    "source-profile-override-request.schema.json": SourceProfileOverrideRequest,
    "source-profile-view.schema.json": SourceProfileView,
    "collection-create-request.schema.json": CollectionCreateRequest,
    "collection-patch-request.schema.json": CollectionPatchRequest,
    "collection-summary.schema.json": CollectionSummary,
    "cursor-page.schema.json": CursorPage[dict[str, str | int | bool | None]],
    "digital-case-detail.schema.json": DigitalCaseDetail,
    "daily-report.schema.json": DailyReport,
    "paper-detail.schema.json": PaperDetail,
    "technology-product-detail.schema.json": TechnologyProductDetail,
    "claim-view.schema.json": ClaimView,
    "confirmed-fact.schema.json": ConfirmedFact,
    "document-detail.schema.json": DocumentDetail,
    "document-page-view.schema.json": DocumentPageView,
    "feed-notice.schema.json": FeedNotice,
    "feed-page.schema.json": FeedPage,
    "fingerprint-response.schema.json": FingerprintResponse,
    "hot-topic-page.schema.json": HotTopicPage,
    "evidence-view.schema.json": EvidenceView,
    "event-detail.schema.json": EventDetail,
    "event-automatic-result-view.schema.json": EventAutomaticResultView,
    "automatic-relationship-view.schema.json": AutomaticRelationshipView,
    "owner-relationship-correction-request.schema.json": OwnerRelationshipCorrectionRequest,
    "owner-relationship-correction-response.schema.json": OwnerRelationshipCorrectionResponse,
    "event-item.schema.json": EventItem,
    "event-relation-view.schema.json": EventRelationView,
    "event-timeline.schema.json": EventTimeline,
    "fixture-upload-response.schema.json": FixtureUploadResponse,
    "liveness-response.schema.json": LivenessResponse,
    "item-summary.schema.json": ItemSummary,
    "item-detail.schema.json": ItemDetail,
    "me-response.schema.json": MeResponse,
    "problem-details.schema.json": ProblemDetails,
    "published-event-summary-v1.schema.json": PublishedEventSummaryV1,
    "published-event-detail-v1.schema.json": PublishedEventDetailV1,
    "score-summary.schema.json": ScoreSummary,
    "save-item-request.schema.json": SaveItemRequest,
    "search-context.schema.json": SearchContext,
    "readiness-response.schema.json": ReadinessResponse,
    "source-comparison.schema.json": SourceComparison,
    "type-summary.schema.json": TypeSummary,
    "unverified-fact.schema.json": UnverifiedFact,
    "version-diff-response.schema.json": VersionDiffResponse,
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
    expected = set(SCHEMA_MODELS)
    for existing in output_dir.glob("*.schema.json"):
        if existing.name not in expected:
            existing.unlink()
    for filename, content in render_schemas().items():
        (output_dir / filename).write_text(content, encoding="utf-8", newline="\n")


def main() -> None:
    repository_root = Path(__file__).resolve().parents[4]
    write_schemas(repository_root / "packages/contracts/generated/json-schema")


if __name__ == "__main__":
    main()
