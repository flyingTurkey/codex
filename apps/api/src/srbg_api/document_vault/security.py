"""Bounded, non-rendering validation for manually uploaded fixtures."""

import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path, PurePath


class UploadRejected(ValueError):
    """Raised before untrusted bytes enter object storage."""


@dataclass(frozen=True, slots=True)
class InspectedFixture:
    detected_mime: str
    document_kind: str
    title: str | None
    byte_size: int


_ACTIVE_PDF_MARKERS = (
    b"/JavaScript",
    b"/JS",
    b"/OpenAction",
    b"/Launch",
    b"/EmbeddedFile",
    b"/AA",
)
_WINDOWS_RESERVED = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}


def validate_filename(filename: str) -> str:
    normalized = unicodedata.normalize("NFC", filename)
    if not normalized or len(normalized) > 255 or normalized != PurePath(normalized).name:
        raise UploadRejected("invalid filename")
    if any(char in normalized for char in ("/", "\\", "\x00")):
        raise UploadRejected("invalid filename")
    if any(ord(char) < 32 for char in normalized):
        raise UploadRejected("invalid filename")
    path = Path(normalized)
    if path.stem.upper() in _WINDOWS_RESERVED:
        raise UploadRejected("invalid filename")
    if path.suffix.lower() not in {".html", ".htm", ".pdf"}:
        raise UploadRejected("unsupported filename extension")
    return normalized


def _html_title(data: bytes) -> str | None:
    match = re.search(rb"<title[^>]*>(.*?)</title\s*>", data[:131072], re.IGNORECASE | re.DOTALL)
    if match is None:
        return None
    title = re.sub(rb"\s+", b" ", match.group(1)).decode("utf-8", errors="replace").strip()
    return title[:300] or None


def inspect_fixture(
    path: Path,
    filename: str,
    declared_mime: str,
    *,
    max_bytes: int,
    max_pdf_pages: int,
) -> InspectedFixture:
    size = path.stat().st_size
    if size > max_bytes:
        raise UploadRejected("file too large")
    return inspect_fixture_bytes(
        path.read_bytes(),
        filename,
        declared_mime,
        max_bytes=max_bytes,
        max_pdf_pages=max_pdf_pages,
    )


def inspect_fixture_bytes(
    data: bytes,
    filename: str,
    declared_mime: str,
    *,
    max_bytes: int,
    max_pdf_pages: int,
) -> InspectedFixture:
    safe_name = validate_filename(filename)
    size = len(data)
    if size > max_bytes:
        raise UploadRejected("file too large")
    suffix = Path(safe_name).suffix.lower()
    is_pdf = data.startswith(b"%PDF-") and data.rstrip().endswith(b"%%EOF")
    is_html = bool(re.search(rb"<(?:!doctype\s+html|html)(?:\s|>)", data[:65536], re.IGNORECASE))
    if suffix == ".pdf":
        if declared_mime != "application/pdf" or not is_pdf:
            raise UploadRejected("declared MIME does not match file bytes")
        if any(marker in data for marker in _ACTIVE_PDF_MARKERS):
            raise UploadRejected("PDF active content is not allowed")
        if b"/Encrypt" in data:
            raise UploadRejected("encrypted PDF is not allowed")
        page_count = len(re.findall(rb"/Type\s*/Page(?!s)\b", data))
        if page_count > max_pdf_pages:
            raise UploadRejected("PDF has too many pages")
        return InspectedFixture("application/pdf", "PDF", None, size)
    if suffix in {".html", ".htm"}:
        if declared_mime != "text/html" or not is_html or is_pdf:
            raise UploadRejected("declared MIME does not match file bytes")
        return InspectedFixture("text/html", "HTML", _html_title(data), size)
    raise UploadRejected("unsupported file type")
