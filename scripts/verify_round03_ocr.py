"""Run a test-only real-Tesseract self-check inside the production parser image."""

import pymupdf  # type: ignore[import-untyped]
from srbg_api.pdf_processing.ocr import TesseractOcrAdapter
from srbg_api.pdf_processing.parser import PdfDocumentParser


def main() -> int:
    content = _test_only_scanned_pdf()
    parsed = PdfDocumentParser(
        ocr_adapter=TesseractOcrAdapter(timeout_seconds=30),
    ).parse(content)
    if parsed.ocr_page_count != 3:
        raise RuntimeError("ROUND03_OCR_PAGE_COUNT_MISMATCH")
    if parsed.ocr_usable_page_count != 3:
        raise RuntimeError("ROUND03_OCR_NOT_USABLE")
    if len(parsed.semantic_body.replace(" ", "")) < 30:
        raise RuntimeError("ROUND03_OCR_TEXT_TOO_SHORT")
    print(
        "Round 03 real OCR verified: "
        f"pages={parsed.ocr_page_count}, usable={parsed.ocr_usable_page_count}"
    )
    return 0


def _test_only_scanned_pdf() -> bytes:
    source = pymupdf.open()
    for page_number in range(1, 4):
        page = source.new_page(width=595, height=842)
        page.insert_text((72, 100), "TEST ONLY OCR SAFETY REGULATION", fontsize=16)
        page.insert_text(
            (72, 150),
            f"Page {page_number}: inspect bridge structures before every shift.",
            fontsize=13,
        )
    scanned = pymupdf.open()
    for source_page in source:
        pixmap = source_page.get_pixmap(matrix=pymupdf.Matrix(1.5, 1.5), alpha=False)
        page = scanned.new_page(width=595, height=842)
        page.insert_image(page.rect, stream=pixmap.tobytes("png"))
    source.close()
    content = bytes(scanned.tobytes(garbage=4, deflate=True))
    scanned.close()
    return content


if __name__ == "__main__":
    raise SystemExit(main())
