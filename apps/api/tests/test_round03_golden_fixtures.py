import base64
import json
import os
from hashlib import sha256
from pathlib import Path

import pytest
from srbg_api.pdf_processing.ocr import OcrPageResult, OcrWord, TesseractOcrAdapter
from srbg_api.pdf_processing.parser import PdfDocumentParser
from srbg_api.pdf_processing.security import (
    FileSecurityPolicy,
    SecurityViolation,
    inspect_pdf_bytes,
    inspect_zip_bytes,
)

ROOT = Path(__file__).parent / "fixtures" / "round03"
POLICY = FileSecurityPolicy(
    max_file_bytes=50 * 1024 * 1024,
    max_pdf_pages=1000,
    max_ocr_pages=200,
    max_zip_entries=100,
    max_uncompressed_bytes=200 * 1024 * 1024,
    max_compression_ratio=100,
    max_page_pixels=40_000_000,
)


class StableLowConfidenceOcr:
    def recognize(self, png_bytes: bytes, *, page_number: int) -> OcrPageResult:
        assert png_bytes.startswith(b"\x89PNG")
        return OcrPageResult(
            words=(
                OcrWord(
                    text=f"TEST-ONLY-OCR-{page_number}",
                    x0_px=20,
                    y0_px=20,
                    x1_px=240,
                    y1_px=60,
                    confidence_bps=9200,
                ),
            ),
            image_width_px=1190,
            image_height_px=1684,
            engine_version="test-double-1.0",
        )


def _bytes(name: str) -> bytes:
    return base64.b64decode((ROOT / f"{name}.b64").read_text(encoding="ascii"))


def test_round03_manifest_hashes_every_test_only_golden_artifact() -> None:
    manifest = json.loads((ROOT / "round03-golden-manifest.json").read_text(encoding="utf-8"))

    assert manifest["fixture_notice"].startswith("TEST ONLY")
    assert len(manifest["files"]) >= 11
    for entry in manifest["files"]:
        content = base64.b64decode((ROOT / entry["file"]).read_text(encoding="ascii"))
        assert len(content) == entry["decoded_bytes"]
        assert sha256(content).hexdigest() == entry["decoded_sha256"]


def test_native_and_scanned_goldens_produce_stable_pages_and_ocr_confidence() -> None:
    parser = PdfDocumentParser(ocr_adapter=StableLowConfidenceOcr())

    native = parser.parse(_bytes("lifecycle-v1.pdf"))
    scanned = parser.parse(_bytes("scanned.pdf"))

    assert len(native.pages) == 3
    assert native.ocr_page_count == 0
    assert len(scanned.pages) == 3
    assert scanned.ocr_page_count == 3
    assert scanned.ocr_usable_page_count == 3
    assert scanned.low_confidence_critical_count == 3
    assert all(page.text_source == "OCR" for page in scanned.pages)


@pytest.mark.skipif(
    os.environ.get("SRBG_RUN_REAL_OCR") != "1",
    reason="run in the fixed parser image through make pdf-ocr-test",
)
def test_scanned_golden_is_usable_with_fixed_tesseract_languages() -> None:
    scanned = PdfDocumentParser(
        ocr_adapter=TesseractOcrAdapter(timeout_seconds=30),
    ).parse(_bytes("scanned.pdf"))

    assert scanned.ocr_page_count == 3
    assert scanned.ocr_usable_page_count == 3
    assert len(scanned.semantic_body.replace(" ", "")) >= 30


@pytest.mark.parametrize(
    ("name", "declared_mime", "code"),
    [
        ("wrong-mime.pdf", "text/html", "MIME_MISMATCH"),
        ("active-actions.pdf", "application/pdf", "PDF_ACTIVE_ACTION"),
        ("oversized-page.pdf", "application/pdf", "PDF_PAGE_PIXEL_LIMIT"),
    ],
)
def test_pdf_goldens_fail_closed(name: str, declared_mime: str, code: str) -> None:
    with pytest.raises(SecurityViolation, match=code):
        inspect_pdf_bytes(
            _bytes(name),
            filename=name,
            declared_mime=declared_mime,
            policy=POLICY,
        )


def test_flat_archive_is_atomic_and_compression_bomb_is_quarantined() -> None:
    safe = inspect_zip_bytes(
        _bytes("safe-flat.zip"),
        filename="safe-flat.zip",
        declared_mime="application/zip",
        policy=POLICY,
    )
    assert [(entry.normalized_path, entry.depth) for entry in safe.entries] == [
        ("notice.html", 0),
        ("files/rule.pdf", 1),
    ]

    with pytest.raises(SecurityViolation, match="ZIP_COMPRESSION_RATIO"):
        inspect_zip_bytes(
            _bytes("compression-bomb.zip"),
            filename="compression-bomb.zip",
            declared_mime="application/zip",
            policy=POLICY,
        )
