# ruff: noqa: RUF001

from datetime import UTC, datetime, timedelta

from srbg_api.intelligence_resolution.domain import (
    DeduplicationDocument,
    SourceLineage,
    assess_duplicate,
    calculate_scores,
    count_independent_sources,
    exact_identity_matches,
)
from srbg_api.intelligence_resolution.recall import merge_rule_and_vector_recall

NOW = datetime(2026, 7, 15, tzinfo=UTC)


def _document(**changes: object) -> DeduplicationDocument:
    values: dict[str, object] = {
        "canonical_url": "https://example.com/reports/a?utm_source=x",
        "source_id": "source-a",
        "external_id": "A-001",
        "doi": None,
        "issuer": "四川省交通运输厅",
        "document_number": "川交规〔2026〕1号",
        "content_sha256": "a" * 64,
        "title": "G5 高速公路甲标段桥梁施工安全通报",
        "body": "四川 G5 高速公路甲标段桥梁施工现场发布安全通报。",
        "entities": ("G5高速公路", "甲标段"),
        "occurred_at": NOW,
        "region": "四川成都",
        "project": "G5高速公路",
        "contract_section": "甲标段",
        "model_no": None,
        "accident_stage": "INITIAL_REPORT",
    }
    values.update(changes)
    return DeduplicationDocument(**values)


def test_exact_identity_covers_url_external_id_doi_document_number_and_hash() -> None:
    left = _document(doi="10.1234/ABC")
    right = _document(
        canonical_url="https://EXAMPLE.com/reports/a",
        doi="https://doi.org/10.1234/abc",
    )

    assert exact_identity_matches(left, right) == {
        "CANONICAL_URL",
        "EXTERNAL_ID",
        "DOI",
        "DOCUMENT_NUMBER",
        "CONTENT_SHA256",
    }


def test_hard_identity_conflicts_block_text_and_vector_similarity() -> None:
    left = _document()
    for field, value in (
        ("project", "G6高速公路"),
        ("contract_section", "乙标段"),
        ("model_no", "M300"),
        ("document_number", "川交规〔2026〕2号"),
        ("accident_stage", "FINAL_REPORT"),
    ):
        left_for_case = _document(model_no="M200") if field == "model_no" else left
        right = _document(**{field: value, "content_sha256": "b" * 64})
        assessment = assess_duplicate(left_for_case, right, vector_similarity_bps=10_000)
        assert assessment.blocked is True
        assert assessment.recommendation == "KEEP_DISTINCT"
        assert field.upper() in assessment.hard_conflicts


def test_revision_and_follow_up_are_relations_not_duplicates() -> None:
    revised = assess_duplicate(
        _document(),
        _document(title="G5 高速公路甲标段桥梁施工安全通报（修订）", relation_hint="REVISION"),
    )
    assert revised.recommendation == "LINK_RELATION"
    assert revised.relation_type == "REVISION"


def test_reposts_do_not_increase_independent_source_count() -> None:
    lineages = [
        SourceLineage("s1", "org-a", "root-a", "ORIGINAL"),
        SourceLineage("s2", "org-b", "root-a", "REPRINT"),
        SourceLineage("s3", "org-a", "root-a", "MIRROR"),
        SourceLineage("s4", "org-c", "root-c", "INDEPENDENT_REPORT"),
    ]
    assert count_independent_sources(lineages) == 2


def test_heat_never_changes_confidence_and_scores_explain_their_features() -> None:
    base = dict(
        relevance_features=(70, 20, 10),
        authority_level="A1",
        impact_features=(30, 20, 15, 10),
        novelty_similarity_bps=2_000,
        published_at=NOW - timedelta(days=2),
        content_type="SAFETY_CASE",
        accepted_claim_coverage_bps=9_000,
        locator_integrity=True,
        primary_evidence=True,
        extraction_confidence_bps=8_000,
        cross_source_agreement_bps=7_500,
        human_reviewed=True,
        unresolved_conflicts=0,
        now=NOW,
    )
    low_heat = calculate_scores(**base, independent_source_count=1, event_activity_count=1)
    high_heat = calculate_scores(**base, independent_source_count=10, event_activity_count=20)

    assert low_heat["CONFIDENCE"].score == high_heat["CONFIDENCE"].score
    assert low_heat["HEAT"].score < high_heat["HEAT"].score
    assert all(score.rule_version == "scoring-v1.0.0" for score in high_heat.values())
    assert all(score.features for score in high_heat.values())


def test_rule_and_optional_pgvector_recall_share_the_same_hard_constraints() -> None:
    query = _document(model_no="M200")
    vector_match = _document(model_no="M300", content_sha256="b" * 64)
    recalled = merge_rule_and_vector_recall(
        query,
        rule_candidates=[],
        vector_candidates=[(vector_match, 10_000)],
    )

    assert recalled[0].recall_methods == ("PGVECTOR",)
    assert recalled[0].assessment.blocked is True
    assert recalled[0].assessment.recommendation == "KEEP_DISTINCT"
