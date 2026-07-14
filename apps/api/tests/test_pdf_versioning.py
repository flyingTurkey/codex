from srbg_api.pdf_processing.change_detection import CriticalFieldValues
from srbg_api.pdf_processing.versioning import VersionFacts, decide_version_change


def _facts(
    *,
    raw: str,
    normalized: str,
    semantic: str,
    metadata: str,
    number: str = "川安规\u30142026\u30151号",
    effective: str = "2026-08-01",
) -> VersionFacts:
    return VersionFacts(
        raw_sha256=raw * 64,
        normalized_text_sha256=normalized * 64,
        semantic_body_sha256=semantic * 64,
        metadata_sha256=metadata * 64,
        normalized_body="道路 桥梁 安全 规定 应当 执行",
        critical_fields=CriticalFieldValues(
            document_number=number,
            published_at="2026-07-01",
            effective_at=effective,
            legal_effect="UNKNOWN",
        ),
    )


def test_initial_and_metadata_only_versions_do_not_require_substantive_review() -> None:
    v1 = _facts(raw="a", normalized="b", semantic="c", metadata="d")
    initial = decide_version_change(None, v1)
    v2 = _facts(raw="e", normalized="f", semantic="c", metadata="g")
    metadata = decide_version_change(v1, v2)

    assert (initial.change_type, initial.review_state) == ("INITIAL", "RE_REVIEW_PENDING")
    assert (metadata.change_type, metadata.review_state, metadata.material) == (
        "METADATA_ONLY",
        "NO_REVIEW_REQUIRED",
        False,
    )


def test_critical_field_change_is_always_material() -> None:
    v1 = _facts(raw="a", normalized="b", semantic="c", metadata="d")
    v3 = _facts(
        raw="e",
        normalized="f",
        semantic="g",
        metadata="h",
        number="川安规\u30142026\u30152号",
    )

    result = decide_version_change(v1, v3)

    assert result.change_type == "CONTENT_UPDATE"
    assert result.material is True
    assert result.review_state == "RE_REVIEW_PENDING"
    assert result.critical_fields[0].field == "document_number"
