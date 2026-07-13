"""Generate deterministic JSON Schema artifacts from canonical models."""

import json
from pathlib import Path

from pydantic import BaseModel

from srbg_contracts.models import (
    CreateSourceRequest,
    CursorPage,
    DocumentDetail,
    FixtureUploadResponse,
    LivenessResponse,
    MeResponse,
    ProblemDetails,
    ReadinessResponse,
    SourceActionRequest,
    SourceDetail,
    SourceOnboardingSubmission,
    SourcePolicySubmission,
    SourceSummary,
    SourceTransitionRequest,
    VersionResponse,
)

SCHEMA_MODELS: dict[str, type[BaseModel]] = {
    "cursor-page.schema.json": CursorPage[dict[str, str | int | bool | None]],
    "create-source-request.schema.json": CreateSourceRequest,
    "document-detail.schema.json": DocumentDetail,
    "fixture-upload-response.schema.json": FixtureUploadResponse,
    "liveness-response.schema.json": LivenessResponse,
    "me-response.schema.json": MeResponse,
    "problem-details.schema.json": ProblemDetails,
    "readiness-response.schema.json": ReadinessResponse,
    "source-action-request.schema.json": SourceActionRequest,
    "source-detail.schema.json": SourceDetail,
    "source-onboarding-submission.schema.json": SourceOnboardingSubmission,
    "source-policy-submission.schema.json": SourcePolicySubmission,
    "source-summary.schema.json": SourceSummary,
    "source-transition-request.schema.json": SourceTransitionRequest,
    "version-response.schema.json": VersionResponse,
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
