"""Bounded, non-rendering validation for manually uploaded fixtures."""

import json
import re
import unicodedata
from dataclasses import dataclass
from html import unescape
from pathlib import Path, PurePath
from xml.etree import ElementTree

from defusedxml import ElementTree as DefusedElementTree  # type: ignore[import-untyped]
from defusedxml.common import DefusedXmlException  # type: ignore[import-untyped]


class UploadRejected(ValueError):
    """Raised before untrusted bytes can become CLEAN, READY, or otherwise usable."""


class MalwareDetected(UploadRejected):
    """A scanner definitively identified malware in these immutable bytes."""

    code = "MALWARE_DETECTED"


class MalwareScanInconclusive(UploadRejected):
    """The scanner could not establish a clean or infected result."""

    code = "MALWARE_SCAN_INCONCLUSIVE"


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
_ACTIVE_HTML_TAG = re.compile(
    rb"<\s*(?:script|iframe|object|embed|svg|math|form|link|style|base)\b",
    re.IGNORECASE,
)
_ACTIVE_HTML_HANDLER = re.compile(rb"\son[a-z0-9_-]+\s*=", re.IGNORECASE)
_ACTIVE_HTML_REFRESH = re.compile(
    rb"<\s*meta\b[^>]*\bhttp-equiv\s*=\s*['\"]?refresh\b",
    re.IGNORECASE,
)
_ACTIVE_HTML_URL = re.compile(
    rb"\b(?:href|src|action|formaction|xlink:href)\s*=\s*['\"]?\s*javascript\s*:",
    re.IGNORECASE,
)
_ACTIVE_HTML_CSS = re.compile(rb"(?:@import\b|url\s*\()", re.IGNORECASE)
_WINDOWS_RESERVED = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}
_STRUCTURED_NODE_LIMIT = 20_000
_STRUCTURED_DEPTH_LIMIT = 64
_XML_MIME_TYPES = {
    "application/atom+xml",
    "application/rss+xml",
    "application/xml",
    "text/xml",
}


def validate_filename(filename: str) -> str:
    normalized = unicodedata.normalize("NFC", filename)
    if not normalized or len(normalized) > 255 or normalized != PurePath(normalized).name:
        raise UploadRejected("invalid filename")
    if any(char in normalized for char in ("/", "\\", "\x00")):
        raise UploadRejected("invalid filename")
    if any(ord(char) < 32 or ord(char) == 127 for char in normalized):
        raise UploadRejected("invalid filename")
    path = Path(normalized)
    if path.stem.upper() in _WINDOWS_RESERVED:
        raise UploadRejected("invalid filename")
    if path.suffix.lower() not in {
        ".atom",
        ".htm",
        ".html",
        ".json",
        ".pdf",
        ".rss",
        ".xml",
    }:
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
        if has_active_html_content(data):
            raise UploadRejected("HTML active content is not allowed")
        return InspectedFixture("text/html", "HTML", _html_title(data), size)
    if suffix in {".atom", ".rss", ".xml"}:
        if declared_mime not in _XML_MIME_TYPES or is_pdf or is_html:
            raise UploadRejected("declared MIME does not match XML fixture bytes")
        try:
            root = DefusedElementTree.fromstring(
                data,
                forbid_dtd=True,
                forbid_entities=True,
                forbid_external=True,
            )
        except (ElementTree.ParseError, DefusedXmlException, ValueError) as error:
            raise UploadRejected("XML fixture is malformed or unsafe") from error
        pending = [(root, 1)]
        node_count = 0
        while pending:
            node, depth = pending.pop()
            node_count += 1
            if node_count > _STRUCTURED_NODE_LIMIT or depth > _STRUCTURED_DEPTH_LIMIT:
                raise UploadRejected("XML fixture exceeds structural limits")
            pending.extend((child, depth + 1) for child in node)
        return InspectedFixture("application/xml", "DISCOVERY_XML", None, size)
    if suffix == ".json":
        if declared_mime != "application/json" or is_pdf or is_html:
            raise UploadRejected("declared MIME does not match JSON fixture bytes")
        try:
            document: object = json.loads(data)
        except (UnicodeDecodeError, ValueError, RecursionError) as error:
            raise UploadRejected("JSON fixture is malformed") from error
        if not isinstance(document, (dict, list)):
            raise UploadRejected("JSON fixture must be an object or array")
        pending_json: list[tuple[object, int]] = [(document, 1)]
        node_count = 0
        while pending_json:
            value, depth = pending_json.pop()
            node_count += 1
            if node_count > _STRUCTURED_NODE_LIMIT or depth > _STRUCTURED_DEPTH_LIMIT:
                raise UploadRejected("JSON fixture exceeds structural limits")
            if isinstance(value, dict):
                pending_json.extend((item, depth + 1) for item in value.values())
            elif isinstance(value, list):
                pending_json.extend((item, depth + 1) for item in value)
        return InspectedFixture("application/json", "DISCOVERY_JSON", None, size)
    raise UploadRejected("unsupported file type")


def has_active_html_content(data: bytes) -> bool:
    """Use one case-insensitive active-content policy for uploads and ZIP entries."""

    normalized = unescape(data.decode("utf-8", errors="replace")).encode()
    return any(
        bool(
            _ACTIVE_HTML_TAG.search(candidate)
            or _ACTIVE_HTML_HANDLER.search(candidate)
            or _ACTIVE_HTML_REFRESH.search(candidate)
            or _ACTIVE_HTML_URL.search(candidate)
            or _ACTIVE_HTML_CSS.search(candidate)
        )
        for candidate in (data, normalized)
    )
