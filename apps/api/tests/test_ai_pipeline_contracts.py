import json
from pathlib import Path

import pytest
from pydantic import ValidationError
from srbg_api.ai_pipeline.contracts import (
    ClassificationOutput,
    ExtractionOutput,
    SummaryOutput,
    VerificationOutput,
)
from srbg_contracts import AutonomousClassificationCandidate

SCHEMA_ROOT = Path("docs/codex-kit/assets/schemas")


@pytest.mark.parametrize(
    ("model", "schema_file"),
    [
        (ClassificationOutput, "classify-output.schema.json"),
        (ExtractionOutput, "extract-output.schema.json"),
        (SummaryOutput, "summarize-output.schema.json"),
        (VerificationOutput, "verify-output.schema.json"),
        (
            AutonomousClassificationCandidate,
            "autonomous-classify-output.schema.json",
        ),
    ],
)
def test_step_models_reject_every_schema_extra_field(model: type, schema_file: str) -> None:
    schema = json.loads((SCHEMA_ROOT / schema_file).read_text(encoding="utf-8"))
    assert schema["additionalProperties"] is False
    with pytest.raises(ValidationError):
        model.model_validate({"forged_review_status": "APPROVED"})


def test_summary_requires_accepted_claim_references() -> None:
    with pytest.raises(ValidationError):
        SummaryOutput.model_validate(
            {
                "why_worth_attention": "相关性",
                "potential_industry_impacts": [],
                "potential_engineering_scenarios": [],
                "current_limitations": [],
                "questions_to_verify": [],
                "used_claim_ids": [],
            }
        )
