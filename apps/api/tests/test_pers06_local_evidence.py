from srbg_api.ai_pipeline.local_evidence import extract_local_evidence_candidates
from srbg_api.ai_pipeline.preparation import DocumentBlock


def test_local_fallback_extracts_only_bibliography_and_explicit_scalars() -> None:
    candidates = extract_local_evidence_candidates(
        title="养护数字化案例",
        source_name="四川路桥",
        blocks=(
            DocumentBlock(
                block_id="019d0000-0000-7000-8000-000000002610",
                page_number=1,
                text=(
                    "四川路桥于2026年7月18日发布养护数字化案例,"
                    "文号:川路桥数智2026-18号,产品型号:SRBG-AI-2,投入金额100万元。"
                ),
                locator_value="page=1",
            ),
        ),
    )
    values = {candidate.field: candidate.value for candidate in candidates}
    assert values == {
        "title": "养护数字化案例",
        "publisher": "四川路桥",
        "document_no": "川路桥数智2026-18号",
        "model_no": "SRBG-AI-2",
        "published_at": "2026-07-18",
        "direct_loss": "100万元",
    }
    assert "summary" not in values
    assert "incident_cause" not in values
