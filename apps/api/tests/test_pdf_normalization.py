from srbg_api.pdf_processing.change_detection import (
    ChangeDocument,
    CriticalFieldValues,
    classify_version_change,
)
from srbg_api.pdf_processing.normalization import PageTextBlock, normalize_document


def _pages(header: str, body_suffix: str = "") -> list[list[PageTextBlock]]:
    return [
        [
            PageTextBlock(text=header, y0_ratio=0.02, y1_ratio=0.05),
            PageTextBlock(
                text=f"【测试专用】施工安全管理规定正文第 {index} 条{body_suffix}",
                y0_ratio=0.2,
                y1_ratio=0.4,
            ),
            PageTextBlock(text=f"第 {index} 页", y0_ratio=0.95, y1_ratio=0.98),
        ]
        for index in range(1, 6)
    ]


def test_repeated_header_footer_is_preserved_but_excluded_from_semantic_hash() -> None:
    v1 = normalize_document(_pages("测试机关内部页眉 v1"), metadata={"producer": "fixture"})
    v2 = normalize_document(_pages("测试机关内部页眉 v2"), metadata={"producer": "fixture2"})

    assert v1.normalized_text_sha256 != v2.normalized_text_sha256
    assert v1.semantic_body_sha256 == v2.semantic_body_sha256
    assert v1.header_footer_blocks


def test_small_ordinary_change_uses_threshold_but_critical_change_always_material() -> None:
    body = " ".join(["ordinary"] * 2499 + ["baseline"])
    previous = ChangeDocument(
        normalized_body=body,
        semantic_body_sha256="a" * 64,
        metadata_sha256="b" * 64,
        critical_fields=CriticalFieldValues(
            document_number="测试令第1号",
            published_at="2026-07-01",
            effective_at="2026-08-01",
            legal_effect="UNKNOWN",
        ),
    )
    small = ChangeDocument(
        normalized_body=body.replace("baseline", "revision"),
        semantic_body_sha256="c" * 64,
        metadata_sha256="b" * 64,
        critical_fields=previous.critical_fields,
    )
    critical = ChangeDocument(
        normalized_body=small.normalized_body,
        semantic_body_sha256="d" * 64,
        metadata_sha256="b" * 64,
        critical_fields=CriticalFieldValues(
            document_number="测试令第2号",
            published_at="2026-07-01",
            effective_at="2026-08-01",
            legal_effect="UNKNOWN",
        ),
    )

    minor_result = classify_version_change(previous, small)
    critical_result = classify_version_change(previous, critical)

    assert minor_result.change_type == "CONTENT_UPDATE"
    assert minor_result.material is False
    assert critical_result.material is True
    assert critical_result.critical_fields[0].field == "document_number"


def test_ten_changed_words_or_half_percent_is_material() -> None:
    previous_text = " ".join(f"token-{index}" for index in range(3000))
    next_tokens = previous_text.split()
    for index in range(10):
        next_tokens[index] = f"changed-{index}"

    result = classify_version_change(
        ChangeDocument.from_text(previous_text),
        ChangeDocument.from_text(" ".join(next_tokens)),
    )

    assert result.changed_token_count >= 10
    assert result.material is True


def test_critical_field_change_is_material_even_when_semantic_body_is_identical() -> None:
    previous = ChangeDocument(
        normalized_body="same body",
        semantic_body_sha256="a" * 64,
        metadata_sha256="b" * 64,
        critical_fields=CriticalFieldValues(document_number="TEST-ONLY-1"),
    )
    current = ChangeDocument(
        normalized_body="same body",
        semantic_body_sha256="a" * 64,
        metadata_sha256="c" * 64,
        critical_fields=CriticalFieldValues(document_number="TEST-ONLY-2"),
    )

    result = classify_version_change(previous, current)

    assert result.change_type == "CONTENT_UPDATE"
    assert result.material is True
    assert result.critical_fields[0].field == "document_number"
