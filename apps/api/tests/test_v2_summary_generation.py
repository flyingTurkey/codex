import pytest
from srbg_api.intelligence_v2.summaries import AcceptedEvidence, build_source_excerpt


def test_source_excerpt_is_contiguous_bounded_and_claim_linked() -> None:
    excerpt = build_source_excerpt(
        [
            AcceptedEvidence(
                claim_id="claim-1",
                locator="html:p:4",
                text="铁路隧道已安装瓦斯监测系统,并记录报警处置时间。",
            )
        ]
    )
    assert excerpt.text == "铁路隧道已安装瓦斯监测系统,并记录报警处置时间。"
    assert excerpt.claim_ids == ("claim-1",)


def test_excerpt_rejects_unaccepted_or_oversized_evidence() -> None:
    with pytest.raises(ValueError):
        build_source_excerpt([])
    with pytest.raises(ValueError):
        build_source_excerpt([AcceptedEvidence(claim_id="c", locator="p:1", text="工" * 501)])
