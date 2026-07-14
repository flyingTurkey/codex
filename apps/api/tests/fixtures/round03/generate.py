"""Generate deterministic test-only Round 03 golden artifacts and their hashes."""

from __future__ import annotations

import base64
import json
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import pymupdf  # type: ignore[import-untyped]

ROOT = Path(__file__).parent


def _pdf(
    *,
    header: str,
    number: str,
    effective: str,
    body: str,
    producer: str,
    scan: bool = False,
    table: bool = False,
    oversized_page: bool = False,
) -> bytes:
    source = pymupdf.open()
    source.set_metadata({"producer": producer, "title": "TEST ONLY - not a real regulation"})
    size = (4000, 4000) if oversized_page else (595, 842)
    for page_number in range(1, 4):
        page = source.new_page(width=size[0], height=size[1])
        page.insert_text((72, 32), header, fontsize=9)
        lines = (
            "TEST ONLY - Bridge Safety Regulation",
            "Issuing authority: Emergency Management Department",
            f"Document number: {number}",
            "Published: 2026-07-01",
            f"Effective: {effective}",
            body,
            f"TEST ONLY section {page_number}",
        )
        for index, value in enumerate(lines):
            page.insert_text((72, 100 + index * 42), value, fontsize=12)
        if table:
            for x in (72, 220, 370, 520):
                page.draw_line((x, 430), (x, 520))
            for y in (430, 475, 520):
                page.draw_line((72, y), (520, y))
            page.insert_text((90, 458), "Risk", fontsize=10)
            page.insert_text((240, 458), "Control", fontsize=10)
            page.insert_text((390, 458), "Owner", fontsize=10)
    if not scan:
        result = bytes(source.tobytes(garbage=4, deflate=True))
        source.close()
        return result
    scanned = pymupdf.open()
    scanned.set_metadata({"producer": producer, "title": "TEST ONLY scanned fixture"})
    for source_page in source:
        pixmap = source_page.get_pixmap(matrix=pymupdf.Matrix(1.5, 1.5), alpha=False)
        page = scanned.new_page(width=595, height=842)
        page.insert_image(page.rect, stream=pixmap.tobytes("png"))
    source.close()
    result = bytes(scanned.tobytes(garbage=4, deflate=True))
    scanned.close()
    return result


def _zip(entries: dict[str, bytes]) -> bytes:
    target = BytesIO()
    with ZipFile(target, "w", ZIP_DEFLATED) as archive:
        for name, content in entries.items():
            archive.writestr(name, content)
    return target.getvalue()


def main() -> None:
    v1 = _pdf(
        header="TEST ONLY controlled copy v1",
        number="TEST-ONLY-2026-03",
        effective="2026-08-01",
        body="Units shall inspect temporary structures before use.",
        producer="srbg-round03-v1",
    )
    artifacts: dict[str, tuple[bytes, str, str]] = {
        "lifecycle-v1.pdf": (v1, "application/pdf", "READY_INITIAL"),
        "lifecycle-v2-metadata.pdf": (
            _pdf(
                header="TEST ONLY controlled copy v2",
                number="TEST-ONLY-2026-03",
                effective="2026-08-01",
                body="Units shall inspect temporary structures before use.",
                producer="srbg-round03-v2",
            ),
            "application/pdf",
            "METADATA_ONLY",
        ),
        "lifecycle-v3-material.pdf": (
            _pdf(
                header="TEST ONLY controlled copy v3",
                number="TEST-ONLY-2026-04",
                effective="2026-09-01",
                body="Units must inspect and record every temporary structure before each shift.",
                producer="srbg-round03-v3",
            ),
            "application/pdf",
            "CONTENT_UPDATE",
        ),
        "native-table.pdf": (
            _pdf(
                header="TEST ONLY table",
                number="TEST-ONLY-TABLE",
                effective="2026-08-01",
                body="Native table candidate follows.",
                producer="srbg-round03-table",
                table=True,
            ),
            "application/pdf",
            "READY_TABLE",
        ),
        "scanned.pdf": (
            _pdf(
                header="TEST ONLY scan",
                number="TEST-ONLY-SCAN",
                effective="2026-08-01",
                body="Scanned OCR fixture with no native text.",
                producer="srbg-round03-scan",
                scan=True,
            ),
            "application/pdf",
            "OCR_REQUIRED",
        ),
        "wrong-mime.pdf": (v1, "text/html", "QUARANTINED_MIME_MISMATCH"),
        "active-actions.pdf": (
            b"%PDF-1.4\n1 0 obj<</Type/Catalog/OpenAction 2 0 R/JavaScript 3 0 R>>endobj\n%%EOF",
            "application/pdf",
            "QUARANTINED_PDF_ACTIVE_ACTION",
        ),
        "oversized-page.pdf": (
            _pdf(
                header="TEST ONLY oversized",
                number="TEST-ONLY-OVERSIZED",
                effective="2026-08-01",
                body="Pixel budget fixture.",
                producer="srbg-round03-oversized",
                oversized_page=True,
            ),
            "application/pdf",
            "QUARANTINED_PDF_PAGE_PIXEL_LIMIT",
        ),
        "safe-flat.zip": (
            _zip({"notice.html": b"<!doctype html><title>TEST ONLY</title>", "files/rule.pdf": v1}),
            "application/zip",
            "CLEAN_ATTACHMENT_TREE",
        ),
        "compression-bomb.zip": (
            _zip({"bomb.html": b"0" * 1_000_000}),
            "application/zip",
            "QUARANTINED_ZIP_COMPRESSION_RATIO",
        ),
        "withdrawal-evidence.html": (
            b"<!doctype html><title>TEST ONLY withdrawal</title><p>Official fixture withdrawn.</p>",
            "text/html",
            "WITHDRAWAL_OFFICIAL_EVIDENCE",
        ),
    }
    manifest = {
        "fixture_notice": "TEST ONLY - none of these artifacts is a real regulation",
        "files": [],
    }
    for name, (content, declared_mime, expected) in artifacts.items():
        encoded_name = f"{name}.b64"
        (ROOT / encoded_name).write_text(
            base64.b64encode(content).decode() + "\n", encoding="ascii"
        )
        manifest["files"].append(
            {
                "file": encoded_name,
                "decoded_sha256": sha256(content).hexdigest(),
                "decoded_bytes": len(content),
                "declared_mime": declared_mime,
                "expected": expected,
            }
        )
    (ROOT / "round03-golden-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
