import json
from pathlib import Path
from uuid import UUID

import pytest
from pydantic import ValidationError
from srbg_api.ai_pipeline.ai_judgments import (
    AiJudgmentInputRejected,
    AiJudgmentResultType,
    EvidenceFactInput,
    EvidenceSnippet,
    SummarizeOutput,
    VerificationOutput,
    build_summarize_prompt,
    classify_verification,
    validate_used_claim_ids,
)

CLAIM_1 = UUID("019b0000-0000-7000-8000-000000000101")
CLAIM_2 = UUID("019b0000-0000-7000-8000-000000000102")


def _summary() -> SummarizeOutput:
    return SummarizeOutput(
        why_worth_attention="该技术可能改变施工巡检方式。",
        potential_industry_impacts=["降低重复人工巡检工作量"],
        potential_engineering_scenarios=["桥梁日常巡检"],
        current_limitations=["尚无规模化应用证据"],
        questions_to_verify=["复杂天气下的识别准确率如何"],
        used_claim_ids=[CLAIM_1],
    )


def test_summarize_schema_has_only_the_authorized_fields() -> None:
    schema = json.loads(
        Path("docs/codex-kit/assets/schemas/summarize-output.schema.json").read_text(
            encoding="utf-8"
        )
    )
    expected = {
        "why_worth_attention",
        "potential_industry_impacts",
        "potential_engineering_scenarios",
        "current_limitations",
        "questions_to_verify",
        "used_claim_ids",
    }
    assert set(schema["properties"]) == expected
    assert set(schema["required"]) == expected
    assert schema["additionalProperties"] is False


def test_summary_rejects_authority_shaped_or_legacy_fields() -> None:
    with pytest.raises(ValidationError):
        SummarizeOutput.model_validate(
            {**_summary().model_dump(mode="json"), "one_sentence": "不得出现"}
        )


def test_summarize_prompt_contains_only_current_facts_and_short_evidence() -> None:
    prompt = build_summarize_prompt(
        facts=[
            EvidenceFactInput(
                claim_id=CLAIM_1,
                field_name="claimed_outcome",
                value="减少巡检时间",
                evidence=[
                    EvidenceSnippet(
                        evidence_id=UUID("019b0000-0000-7000-8000-000000000201"),
                        excerpt="企业称试点减少了巡检时间。",
                        attribution="某企业",
                    )
                ],
            )
        ]
    )
    assert "<evidence_facts>" in prompt
    assert "减少巡检时间" in prompt
    assert "企业称试点" in prompt
    assert "document" not in prompt.casefold()
    assert "publication_status" not in prompt


def test_used_claim_ids_must_be_current_fact_subset() -> None:
    validate_used_claim_ids(_summary().used_claim_ids, {CLAIM_1, CLAIM_2})
    with pytest.raises(AiJudgmentInputRejected, match="CURRENT_EVIDENCE_FACT_SUBSET"):
        validate_used_claim_ids([UUID("019b0000-0000-7000-8000-000000000999")], {CLAIM_1})


def test_verification_classifies_pass_unverified_and_injection_failure() -> None:
    clean = VerificationOutput(candidate_decision="PASS_TO_SERVER_GATE")
    assert classify_verification(clean) is AiJudgmentResultType.AI_JUDGMENT

    unsupported = clean.model_copy(update={"unsupported_claims": ["缺少证据"]})
    assert classify_verification(unsupported) is AiJudgmentResultType.UNVERIFIED_AI

    injection = clean.model_copy(update={"prompt_injection_risk": True})
    assert classify_verification(injection) is AiJudgmentResultType.AI_PROCESSING_FAILED


def test_verify_contract_covers_all_six_checks() -> None:
    fields = set(VerificationOutput.model_fields)
    assert {
        "unsupported_claims",
        "number_or_date_conflicts",
        "legal_responsibility_or_causal_overreach",
        "enterprise_claims_missing_attribution",
        "stale_or_superseded_evidence",
        "prompt_injection_risk",
        "candidate_decision",
    } <= fields
