from dataclasses import dataclass

import pymupdf
from srbg_api.pdf_processing.ocr import OcrPageResult, OcrWord
from srbg_api.pdf_processing.parser import PdfDocumentParser
from srbg_api.safety_regulations.pdf_parser import PdfSafetyRegulationParser


@dataclass(frozen=True)
class NeverOcr:
    def recognize(self, png_bytes: bytes, *, page_number: int) -> OcrPageResult:
        raise AssertionError("native text fixture must not invoke OCR")


def _regulation_pdf() -> bytes:
    document = pymupdf.open()
    page = document.new_page(width=595, height=842)
    lines = (
        "TEST-ONLY SAFETY REGULATION",
        "Issuing authority: Test Authority",
        "Document number: TEST-ORDER-1",
        "Published: 2026-07-01",
        "Effective: 2026-08-01",
        "This fixture is not a real regulation.",
    )
    for index, line in enumerate(lines):
        page.insert_text((72, 120 + index * 48), line, fontsize=12)
    payload = document.tobytes(garbage=4, deflate=True)
    document.close()
    return payload


def test_pdf_parser_builds_the_same_claim_model_with_page_evidence() -> None:
    parser = PdfSafetyRegulationParser(
        PdfDocumentParser(ocr_adapter=NeverOcr()),
    )

    parsed = parser.parse(
        _regulation_pdf(),
        document_version_id="019b0000-0000-7000-8000-000000006101",
        canonical_url="https://example.test/test-only-rule.pdf",
    )

    assert parsed.title == "TEST-ONLY SAFETY REGULATION"
    assert parsed.issuing_authority == "Test Authority"
    assert parsed.document_number == "TEST-ORDER-1"
    assert parsed.published_at.isoformat() == "2026-06-30T16:00:00+00:00"
    assert parsed.effective_at is not None
    assert {claim.claim_type for claim in parsed.claims} == {
        "title",
        "issuing_authority",
        "document_number",
        "published_at",
        "effective_at",
    }
    number = next(claim for claim in parsed.claims if claim.claim_type == "document_number")
    evidence = number.evidence[0]
    assert evidence.locator_type == "PDF_TEXT"
    assert evidence.page_number == 1
    assert evidence.block_index is not None
    assert evidence.bbox_mpt is not None
    assert evidence.paragraph_id is None
    assert parsed.pdf_document is not None


@dataclass(frozen=True)
class LowConfidenceOcr:
    def recognize(self, png_bytes: bytes, *, page_number: int) -> OcrPageResult:
        lines = (
            "TEST-ONLY SAFETY REGULATION",
            "Issuing authority: Test Authority",
            "Document number: TEST-ORDER-1",
            "Published: 2026-07-01",
        )
        return OcrPageResult(
            words=tuple(
                OcrWord(
                    text=line,
                    x0_px=10,
                    y0_px=20 + index * 60,
                    x1_px=500,
                    y1_px=60 + index * 60,
                    confidence_bps=9400,
                )
                for index, line in enumerate(lines)
            ),
            image_width_px=1190,
            image_height_px=1684,
            engine_version="test-low-confidence",
        )


def test_scanned_pdf_carries_low_critical_confidence_to_claims() -> None:
    document = pymupdf.open()
    document.new_page(width=595, height=842)
    payload = document.tobytes(garbage=4, deflate=True)
    document.close()
    parser = PdfSafetyRegulationParser(
        PdfDocumentParser(ocr_adapter=LowConfidenceOcr()),
    )

    parsed = parser.parse(
        payload,
        document_version_id="019b0000-0000-7000-8000-000000006102",
        canonical_url="https://example.test/test-only-scan.pdf",
    )

    assert parsed.pdf_document is not None
    assert parsed.pdf_document.ocr_page_count == 1
    assert all(claim.confidence_bps == 9400 for claim in parsed.claims)
    assert all(claim.evidence[0].locator_type == "PDF_OCR" for claim in parsed.claims)
