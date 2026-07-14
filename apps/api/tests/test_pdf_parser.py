from dataclasses import dataclass

import pymupdf
from srbg_api.pdf_processing.ocr import OcrPageResult, OcrWord
from srbg_api.pdf_processing.parser import PdfDocumentParser


def _text_pdf() -> bytes:
    document = pymupdf.open()
    for page_number in range(1, 4):
        page = document.new_page(width=595, height=842)
        page.insert_text((72, 50), "TEST-ONLY REPEATED HEADER")
        page.insert_text((72, 180), f"TEST-ONLY safety regulation page {page_number}")
        page.insert_text((72, 810), f"Page {page_number}")
    document.set_metadata({"title": "TEST ONLY", "producer": "srbg fixture"})
    payload = document.tobytes(garbage=4, deflate=True)
    document.close()
    return payload


@dataclass(frozen=True)
class FakeOcrAdapter:
    confidence_bps: int = 9700

    def recognize(self, png_bytes: bytes, *, page_number: int) -> OcrPageResult:
        assert png_bytes.startswith(b"\x89PNG")
        return OcrPageResult(
            words=(
                OcrWord(
                    text=f"TEST-ONLY OCR PAGE {page_number}",
                    x0_px=10,
                    y0_px=20,
                    x1_px=210,
                    y1_px=55,
                    confidence_bps=self.confidence_bps,
                ),
            ),
            image_width_px=1190,
            image_height_px=1684,
            engine_version="fake-1.0",
        )


def test_native_pdf_replay_has_stable_pages_blocks_hashes_and_coordinates() -> None:
    parser = PdfDocumentParser(ocr_adapter=FakeOcrAdapter())
    payload = _text_pdf()

    first = parser.parse(payload)
    second = parser.parse(payload)

    assert len(first.pages) == 3
    assert first == second
    assert first.pages[0].page_number == 1
    assert first.pages[0].preview_png.startswith(b"\x89PNG")
    assert all(block.text_sha256 for block in first.pages[0].blocks)
    assert any(block.kind == "HEADER" for block in first.pages[0].blocks)


def test_blank_scanned_page_uses_ocr_and_preserves_word_confidence() -> None:
    document = pymupdf.open()
    document.new_page(width=595, height=842)
    payload = document.tobytes(garbage=4, deflate=True)
    document.close()

    parsed = PdfDocumentParser(ocr_adapter=FakeOcrAdapter(confidence_bps=9420)).parse(payload)

    assert parsed.ocr_page_count == 1
    assert parsed.pages[0].text_source == "OCR"
    assert parsed.pages[0].blocks[0].confidence_bps == 9420
    assert parsed.low_confidence_critical_count == 1
