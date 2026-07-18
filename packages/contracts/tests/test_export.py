import json
from pathlib import Path

import srbg_contracts.export as contract_export


def test_exported_json_schemas_are_deterministic(tmp_path: Path) -> None:
    contract_export.write_schemas(tmp_path)

    assert {path.name for path in tmp_path.glob("*.json")} == set(contract_export.SCHEMA_MODELS)
    version_schema = json.loads((tmp_path / "version-response.schema.json").read_text())
    assert version_schema["properties"]["api_version"]["const"] == "v1"
    assert version_schema["properties"]["content_schema_version"]["const"] == "1.1.0"


def test_committed_schemas_match_canonical_models(tmp_path: Path) -> None:
    contract_export.write_schemas(tmp_path)
    generated_dir = Path("packages/contracts/generated/json-schema")

    assert generated_dir.is_dir()
    assert {path.name for path in generated_dir.glob("*.json")} == set(
        contract_export.SCHEMA_MODELS
    )
    for generated in sorted(tmp_path.glob("*.json")):
        assert (generated_dir / generated.name).read_text(encoding="utf-8") == generated.read_text(
            encoding="utf-8"
        )


def test_generated_types_expose_personal_read_contracts_only() -> None:
    types_path = Path("packages/contracts/generated/types/index.d.ts")
    generated_types = types_path.read_text(encoding="utf-8")

    for expected in (
        "LivenessResponse",
        "ProblemDetails",
        "FeedPage",
        "ItemSummary",
        "TypeSummary",
        "SafetyCaseTypeSummary",
        "EventDetail",
        "ScoreSummary",
        "HotTopicPage",
        "ReadinessResponse",
        "VersionResponse",
    ):
        assert f"export type {{ {expected} }}" in generated_types
    for retired in (
        "ClaimConflict",
        "PilotWindowView",
        "GoldTaskView",
        "OperatorWorkSessionView",
        "OperatorTaskView",
        "ReviewDecisionRequest",
        "SourcePolicySubmission",
    ):
        assert retired not in generated_types
