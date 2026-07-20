# ruff: noqa: RUF001
from uuid import UUID

import pytest
from pydantic import ValidationError
from srbg_api.intelligence_v2.content_candidates import (
    AcceptedClaimInput,
    ClaimEvidenceInput,
    ContentCandidateRejected,
    StructuredSummaryCandidate,
    SummaryFactParagraph,
    SummaryJudgmentParagraph,
    build_content_candidate,
    build_source_excerpt,
)

VERSION_ID = UUID("019f8100-0000-7000-8000-000000000001")
CLAIM_ID = UUID("019f8100-0000-7000-8000-000000000002")
OTHER_CLAIM_ID = UUID("019f8100-0000-7000-8000-000000000003")


def _claim(
    *,
    claim_id: UUID = CLAIM_ID,
    field_name: str = "capability",
    basis: str = "PROJECT_FIRST_PARTY_RECORD",
    active: bool = True,
    version_id: UUID = VERSION_ID,
    authority_original: bool = False,
    excerpt: str = "该铁路隧道已部署连续瓦斯监测，并记录报警后的现场处置。",
) -> AcceptedClaimInput:
    return AcceptedClaimInput(
        claim_id=claim_id,
        document_version_id=version_id,
        field_name=field_name,
        value="铁路隧道部署连续瓦斯监测",
        basis=basis,
        active=active,
        evidence=(
            ClaimEvidenceInput(
                evidence_id=UUID("019f8100-0000-7000-8000-000000000010"),
                document_version_id=version_id,
                document_block_id=UUID("019f8100-0000-7000-8000-000000000020"),
                locator="pdf:page=8&block=3",
                excerpt=excerpt,
                char_start=12,
                char_end=12 + len(excerpt),
                authority_original=authority_original,
            ),
        ),
    )


def _summary() -> StructuredSummaryCandidate:
    impact = (
        "该记录说明监测已进入现场连续运行环节。对类似交通隧道而言，"
        "可重点评估传感器布点、报警阈值、联动处置和班组响应记录之间是否形成闭环；"
        "这些内容属于工程影响解读，不代表原文已经证明可复制效果或降低事故率。"
        "还需要结合施工组织、通风条件、供电与通信可靠性、报警确认流程以及人员培训情况，"
        "分别判断系统对现场决策速度和风险暴露控制的实际贡献。"
    )
    limits = (
        "当前证据仅支持该项目已经部署并记录处置，尚未给出设备校准周期、误报漏报、"
        "长期稳定性、独立检测结果或不同地质条件下的表现。后续应跟踪有权材料、"
        "项目复核数据和独立验证，不能据此推断事故原因、责任、处罚或最终整改结论。"
        "若原文后续更正、撤回，或任一引用 claim 失效，本候选也必须失效并重新复核；"
        "在取得新的当前版本证据前，不应把旧摘要回填为当前结论。"
    )
    fact = (
        "发生了什么：项目第一方记录显示，该铁路隧道已部署连续瓦斯监测，"
        "并记录报警后的现场处置。"
    )
    return StructuredSummaryCandidate(
        paragraphs=(
            SummaryFactParagraph(
                section="WHAT_HAPPENED",
                text=fact,
                claim_ids=(CLAIM_ID,),
            ),
            SummaryJudgmentParagraph(
                section="ENGINEERING_IMPACT",
                text=impact,
                judgment_type="ENGINEERING_SIGNIFICANCE",
            ),
            SummaryJudgmentParagraph(
                section="LIMITATIONS_AND_FOLLOW_UP",
                text=limits,
                judgment_type="LIMITATION_AND_FOLLOW_UP",
            ),
        )
    )


def test_active_current_evidence_claim_builds_one_contiguous_excerpt() -> None:
    excerpt = build_source_excerpt([_claim()], current_document_version_id=VERSION_ID)

    assert excerpt.text == "该铁路隧道已部署连续瓦斯监测，并记录报警后的现场处置。"
    assert excerpt.claim_ids == (CLAIM_ID,)
    assert excerpt.evidence_locators == ("pdf:page=8&block=3",)
    assert len(excerpt.text) <= 500


@pytest.mark.parametrize(
    "claim",
    [
        _claim(active=False),
        _claim(version_id=UUID("019f8100-0000-7000-8000-000000000099")),
    ],
)
def test_inactive_or_old_version_claims_cannot_enter_content_candidate(
    claim: AcceptedClaimInput,
) -> None:
    with pytest.raises(ContentCandidateRejected, match="CURRENT_ACTIVE_ACCEPTED_CLAIM"):
        build_source_excerpt([claim], current_document_version_id=VERSION_ID)


def test_authority_reserved_claim_requires_competent_authority_original() -> None:
    with pytest.raises(ContentCandidateRejected, match="AUTHORITY_ORIGINAL_REQUIRED"):
        build_source_excerpt(
            [
                _claim(
                    field_name="incident_cause",
                    basis="AUTHORITY_FINDING",
                    authority_original=False,
                )
            ],
            current_document_version_id=VERSION_ID,
        )

    excerpt = build_source_excerpt(
        [
            _claim(
                field_name="incident_cause",
                basis="AUTHORITY_FINDING",
                authority_original=True,
            )
        ],
        current_document_version_id=VERSION_ID,
    )
    assert excerpt.claim_ids == (CLAIM_ID,)


def test_structured_summary_covers_required_sections_and_claim_roles() -> None:
    candidate = build_content_candidate(
        claims=[_claim()],
        current_document_version_id=VERSION_ID,
        summary=_summary(),
    )

    assert 300 <= candidate.summary.visible_character_count <= 500
    assert [paragraph.kind for paragraph in candidate.summary.paragraphs] == [
        "FACT",
        "JUDGMENT",
        "JUDGMENT",
    ]
    assert candidate.summary.paragraphs[0].claim_ids == (CLAIM_ID,)
    assert candidate.summary.paragraphs[1].judgment_type == "ENGINEERING_SIGNIFICANCE"
    assert candidate.claim_references[0].basis == "PROJECT_FIRST_PARTY_RECORD"
    assert candidate.claim_references[0].evidence_locators == (
        "pdf:page=8&block=3",
    )
    assert candidate.status == "CURRENT"


def test_fact_paragraph_cannot_reference_unknown_or_stale_claim() -> None:
    summary = _summary().model_copy(
        update={
            "paragraphs": (
                SummaryFactParagraph(
                    section="WHAT_HAPPENED",
                    text="发生了什么：该事实没有当前证据引用。",
                    claim_ids=(OTHER_CLAIM_ID,),
                ),
                *_summary().paragraphs[1:],
            )
        }
    )

    with pytest.raises(ContentCandidateRejected, match="FACT_CLAIM_NOT_CURRENT"):
        build_content_candidate(
            claims=[_claim()],
            current_document_version_id=VERSION_ID,
            summary=summary,
        )


def test_paragraph_role_is_discriminated_not_inferred_from_text() -> None:
    with pytest.raises(ValidationError):
        StructuredSummaryCandidate.model_validate(
            {
                "paragraphs": [
                    {
                        "text": "这是看起来像判断的自由文本，但没有明确角色。",
                        "section": "ENGINEERING_IMPACT",
                    }
                ]
            }
        )


def test_dependency_change_appends_stale_view_without_current_backfill() -> None:
    candidate = build_content_candidate(
        claims=[_claim()],
        current_document_version_id=VERSION_ID,
        summary=_summary(),
    )

    stale = candidate.invalidate("ACCEPTED_CLAIMS_CHANGED")

    assert stale.status == "STALE"
    assert stale.invalidation_reason == "ACCEPTED_CLAIMS_CHANGED"
    assert stale.current_source_excerpt is None
    assert stale.current_summary is None
    assert stale.source_excerpt == candidate.source_excerpt
    assert stale.summary == candidate.summary


def test_sensitive_claim_value_is_rejected_before_model_input() -> None:
    sensitive = _claim().model_copy(update={"value": "Authorization: Bearer test-secret"})
    with pytest.raises(ContentCandidateRejected, match="SENSITIVE_MODEL_INPUT"):
        build_content_candidate(
            claims=[sensitive],
            current_document_version_id=VERSION_ID,
            summary=_summary(),
        )
