from uuid import UUID

import pytest
from srbg_api.ai_pipeline.gateway import ModelOutputRejected
from srbg_api.intelligence_v2.content_candidates import (
    AcceptedClaimInput,
    ClaimEvidenceInput,
)
from srbg_api.intelligence_v2.t06_content_summary import (
    build_content_summary_request,
    validate_content_summary_output,
)

VERSION_ID = UUID("019f8400-0000-7000-8000-000000000001")
CLAIM_ID = UUID("019f8400-0000-7000-8000-000000000002")


def _claims() -> list[AcceptedClaimInput]:
    return [
        AcceptedClaimInput(
            claim_id=CLAIM_ID,
            document_version_id=VERSION_ID,
            field_name="deployment_scope",
            value="铁路隧道安装了瓦斯监测系统并记录报警处置。",
            basis="PROJECT_FIRST_PARTY_RECORD",
            active=True,
            evidence=(
                ClaimEvidenceInput(
                    evidence_id=UUID("019f8400-0000-7000-8000-000000000003"),
                    document_version_id=VERSION_ID,
                    document_block_id=UUID("019f8400-0000-7000-8000-000000000004"),
                    locator="html:p:4",
                    excerpt="铁路隧道安装了瓦斯监测系统并记录报警处置。",
                    char_start=0,
                    char_end=24,
                ),
            ),
        )
    ]


def _output() -> dict[str, object]:
    return {
        "paragraphs": [
            {
                "kind": "FACT",
                "section": "WHAT_HAPPENED",
                "text": "事实" * 50,
                "claim_ids": [str(CLAIM_ID)],
            },
            {
                "kind": "JUDGMENT",
                "section": "ENGINEERING_IMPACT",
                "text": "影响" * 50,
                "judgment_type": "ENGINEERING_SIGNIFICANCE",
            },
            {
                "kind": "JUDGMENT",
                "section": "LIMITATIONS_AND_FOLLOW_UP",
                "text": "限制" * 50,
                "judgment_type": "LIMITATION_AND_FOLLOW_UP",
            },
        ]
    }


def test_real_content_request_uses_t04_schema_and_only_accepted_evidence_payload() -> None:
    request = build_content_summary_request(_claims(), current_document_version_id=VERSION_ID)

    assert request.step == "SUMMARIZE"
    assert request.prompt_version == "t06-content-summary-v1"
    assert request.schema_version == "summarize-v2-output-1.0.0"
    assert request.model_profile == "ai01-deepseek-deepseek-v4-flash-v1"
    assert set(request.parameters) == {"temperature", "max_tokens"}
    assert "accepted_claims" in request.user_prompt
    assert "source_excerpt" in request.user_prompt
    assert "authorization" not in request.user_prompt.casefold()


def test_real_content_output_is_locally_schema_validated_and_extra_authority_is_rejected() -> None:
    request = build_content_summary_request(_claims(), current_document_version_id=VERSION_ID)

    output = validate_content_summary_output(_output(), request=request)
    assert output.visible_character_count == 300

    with pytest.raises(ModelOutputRejected):
        validate_content_summary_output(
            _output() | {"publication_status": "PUBLISHED"}, request=request
        )
