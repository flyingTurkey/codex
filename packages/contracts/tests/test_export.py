import json
from pathlib import Path

import srbg_contracts.export as contract_export


def test_exported_json_schemas_are_deterministic(tmp_path: Path) -> None:
    assert hasattr(contract_export, "write_schemas")

    contract_export.write_schemas(tmp_path)

    expected_names = {
        "claim-view.schema.json",
        "create-source-request.schema.json",
        "cursor-page.schema.json",
        "document-detail.schema.json",
        "document-page-view.schema.json",
        "evidence-view.schema.json",
        "feed-notice.schema.json",
        "feed-page.schema.json",
        "fixture-upload-response.schema.json",
        "liveness-response.schema.json",
        "item-detail.schema.json",
        "item-summary.schema.json",
        "me-response.schema.json",
        "problem-details.schema.json",
        "readiness-response.schema.json",
        "review-decision-request.schema.json",
        "review-decision-response.schema.json",
        "review-candidate-decision-request.schema.json",
        "review-task-detail.schema.json",
        "review-task-summary.schema.json",
        "source-action-request.schema.json",
        "source-detail.schema.json",
        "source-onboarding-submission.schema.json",
        "source-policy-submission.schema.json",
        "source-summary.schema.json",
        "source-transition-request.schema.json",
        "type-summary.schema.json",
        "version-diff-response.schema.json",
        "version-change-escalation-request.schema.json",
        "version-response.schema.json",
        "version-timeline-response.schema.json",
    }
    assert {path.name for path in tmp_path.glob("*.json")} == expected_names
    version_schema = json.loads((tmp_path / "version-response.schema.json").read_text())
    assert version_schema["properties"]["api_version"]["const"] == "v1"
    assert version_schema["properties"]["content_schema_version"]["const"] == "1.0.0"


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
    assert "export type { ReadinessResponse }" in generated_types
    assert "export type { VersionResponse }" in generated_types
    assert "export type Status" not in generated_types
    assert (types_path.parent / "liveness-response.schema.d.ts").is_file()
    assert (types_path.parent / "readiness-response.schema.d.ts").is_file()
