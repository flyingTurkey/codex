import json
from pathlib import Path

import srbg_contracts.export as contract_export


def test_exported_json_schemas_are_deterministic(tmp_path: Path) -> None:
    assert hasattr(contract_export, "write_schemas")

    contract_export.write_schemas(tmp_path)

    expected_names = {
        "automatic-relationship-view.schema.json",
        "cluster-candidate-view.schema.json",
        "cluster-decision-request.schema.json",
        "claim-view.schema.json",
        "claim-conflict.schema.json",
        "claim-conflict-decision-request.schema.json",
        "claim-conflict-decision-response.schema.json",
        "confirmed-fact.schema.json",
        "collection-create-request.schema.json",
        "collection-patch-request.schema.json",
        "collection-summary.schema.json",
        "connector-config-preview.schema.json",
        "connector-config-preview-request.schema.json",
        "connector-config-request.schema.json",
        "connector-config-version.schema.json",
        "connector-definition.schema.json",
        "create-source-request.schema.json",
        "cursor-page.schema.json",
        "digital-case-detail.schema.json",
        "digital-case-review-patch.schema.json",
        "daily-draft-request.schema.json",
        "daily-report.schema.json",
        "document-detail.schema.json",
        "document-page-view.schema.json",
        "evidence-view.schema.json",
        "event-candidate-generation-response.schema.json",
        "event-detail.schema.json",
        "event-item.schema.json",
        "event-relation-view.schema.json",
        "event-timeline.schema.json",
        "feed-notice.schema.json",
        "feed-page.schema.json",
        "fingerprint-response.schema.json",
        "feedback-request.schema.json",
        "gold-annotation-request.schema.json",
        "gold-annotation-view.schema.json",
        "gold-arbitration-packet.schema.json",
        "gold-arbitration-request.schema.json",
        "gold-release-request.schema.json",
        "gold-release-view.schema.json",
        "gold-task-create-request.schema.json",
        "gold-task-view.schema.json",
        "fetch-schedule-update.schema.json",
        "fetch-schedule-view.schema.json",
        "hot-topic-page.schema.json",
        "fixture-upload-response.schema.json",
        "liveness-response.schema.json",
        "item-detail.schema.json",
        "item-summary.schema.json",
        "me-response.schema.json",
        "metric-sample.schema.json",
        "operations-overview.schema.json",
        "owner-relationship-correction-request.schema.json",
        "owner-relationship-correction-response.schema.json",
        "operator-task-complete-request.schema.json",
        "operator-task-create-request.schema.json",
        "operator-task-view.schema.json",
        "operator-work-session-correction-request.schema.json",
        "operator-work-session-heartbeat-request.schema.json",
        "operator-work-session-start.schema.json",
        "operator-work-session-stop-request.schema.json",
        "operator-work-session-view.schema.json",
        "paper-detail.schema.json",
        "personal-source-patch-request.schema.json",
        "personal-source-create-request.schema.json",
        "personal-source-reprobe-request.schema.json",
        "personal-source-stream-view.schema.json",
        "personal-source-view.schema.json",
        "stream-probe-run-view.schema.json",
        "product-normalization-candidate.schema.json",
        "product-normalization-decision-request.schema.json",
        "problem-details.schema.json",
        "pilot-metrics.schema.json",
        "pilot-source-resume-request.schema.json",
        "pilot-window-complete-request.schema.json",
        "pilot-window-create-request.schema.json",
        "pilot-window-start-request.schema.json",
        "pilot-window-view.schema.json",
        "publication-revision-request.schema.json",
        "publication-withdrawal-request.schema.json",
        "published-event-summary-v1.schema.json",
        "published-event-detail-v1.schema.json",
        "readiness-response.schema.json",
        "qualification-run.schema.json",
        "replay-request.schema.json",
        "replay-result.schema.json",
        "replay-task-view.schema.json",
        "review-decision-request.schema.json",
        "review-decision-response.schema.json",
        "review-candidate-decision-request.schema.json",
        "review-task-detail.schema.json",
        "review-task-summary.schema.json",
        "score-override-request.schema.json",
        "score-summary.schema.json",
        "save-item-request.schema.json",
        "search-context.schema.json",
        "source-action-request.schema.json",
        "source-assessment-submission.schema.json",
        "source-attention-page.schema.json",
        "source-audit-event.schema.json",
        "source-candidate-batch-decision-request.schema.json",
        "source-candidate-batch-decision-result.schema.json",
        "source-candidate-create-request.schema.json",
        "source-candidate-decision-request.schema.json",
        "source-candidate-decision-result.schema.json",
        "source-candidate-detail.schema.json",
        "source-candidate-page.schema.json",
        "source-candidate-qualification-request.schema.json",
        "source-comparison.schema.json",
        "source-coverage-matrix.schema.json",
        "source-detail.schema.json",
        "source-governance-metadata-update.schema.json",
        "source-health-view.schema.json",
        "source-lifecycle-action-request.schema.json",
        "source-lifecycle-event.schema.json",
        "source-onboarding-submission.schema.json",
        "source-policy-decision-request.schema.json",
        "source-policy-submission.schema.json",
        "source-policy-v2-submission.schema.json",
        "source-policy-version.schema.json",
        "source-production-approval-request.schema.json",
        "source-profile-model-output.schema.json",
        "source-profile-override-request.schema.json",
        "source-profile-view.schema.json",
        "source-summary.schema.json",
        "source-stream-page.schema.json",
        "source-trial-quality-summary.schema.json",
        "source-trial-run-request.schema.json",
        "source-trial-run.schema.json",
        "source-transition-request.schema.json",
        "technology-product-detail.schema.json",
        "type-summary.schema.json",
        "unverified-fact.schema.json",
        "version-diff-response.schema.json",
        "version-change-escalation-request.schema.json",
        "version-response.schema.json",
        "version-timeline-response.schema.json",
        "discovery-daily-usage-view.schema.json",
        "discovery-setting-patch-request.schema.json",
        "discovery-setting-view.schema.json",
        "discovery-topic-patch-request.schema.json",
        "discovery-topic-view.schema.json",
        "source-auto-score-detail-view.schema.json",
        "source-auto-score-summary-view.schema.json",
    }
    assert {path.name for path in tmp_path.glob("*.json")} == expected_names
    version_schema = json.loads((tmp_path / "version-response.schema.json").read_text())
    assert version_schema["properties"]["api_version"]["const"] == "v1"
    assert version_schema["properties"]["content_schema_version"]["const"] == "1.1.0"


def test_committed_schemas_match_canonical_models(tmp_path: Path) -> None:
    assert hasattr(contract_export, "write_schemas")

    contract_export.write_schemas(tmp_path)
    generated_dir = Path("packages/contracts/generated/json-schema")

    assert generated_dir.is_dir()
    for generated in sorted(tmp_path.glob("*.json")):
        assert (generated_dir / generated.name).read_text(encoding="utf-8") == generated.read_text(
            encoding="utf-8"
        )


def test_generated_types_expose_health_and_version_contracts() -> None:
    types_path = Path("packages/contracts/generated/types/index.d.ts")

    assert types_path.is_file()
    generated_types = types_path.read_text(encoding="utf-8")
    assert "export type { LivenessResponse }" in generated_types
    assert "export type { ProblemDetails }" in generated_types
    assert "export type { FeedPage }" in generated_types
    assert "export type { ItemSummary }" in generated_types
    assert "export type { TypeSummary }" in generated_types
    assert "export type { SafetyCaseTypeSummary }" in generated_types
    assert "export type { EventDetail }" in generated_types
    assert "export type { ScoreSummary }" in generated_types
    assert "export type { HotTopicPage }" in generated_types
    assert "export type { ClaimConflict }" in generated_types
    assert "export type { PilotWindowView }" in generated_types
    assert "export type { GoldTaskView }" in generated_types
    assert "export type { OperatorWorkSessionView }" in generated_types
    assert "export type { OperatorTaskView }" in generated_types
    assert "export type { ClaimConflictDecisionRequest }" in generated_types
    assert "export type { ReadinessResponse }" in generated_types
    assert "export type { VersionResponse }" in generated_types
    assert "export type Status" not in generated_types
    assert (types_path.parent / "liveness-response.schema.d.ts").is_file()
    assert (types_path.parent / "readiness-response.schema.d.ts").is_file()
