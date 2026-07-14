"""Fail-closed structural checks for untrusted PDF and flat ZIP artifacts."""

from __future__ import annotations

import posixpath
import stat
from dataclasses import dataclass
from io import BytesIO
from pathlib import PurePosixPath
from zipfile import BadZipFile, ZipFile

import pymupdf  # type: ignore[import-untyped]


class SecurityViolation(ValueError):
    """A stable quarantine reason safe to persist without original content."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class FileSecurityPolicy:
    max_file_bytes: int
    max_pdf_pages: int
    max_ocr_pages: int
    max_zip_entries: int
    max_uncompressed_bytes: int
    max_compression_ratio: int
    max_page_pixels: int
    render_dpi: int = 144


@dataclass(frozen=True, slots=True)
class PdfInspection:
    page_count: int
    detected_mime: str = "application/pdf"


@dataclass(frozen=True, slots=True)
class InspectedZipEntry:
    normalized_path: str
    depth: int
    detected_mime: str
    byte_size: int
    content: bytes


@dataclass(frozen=True, slots=True)
class ZipInspection:
    entries: tuple[InspectedZipEntry, ...]
    total_uncompressed_bytes: int


def inspect_pdf_bytes(
    content: bytes,
    *,
    filename: str,
    declared_mime: str,
    policy: FileSecurityPolicy,
) -> PdfInspection:
    if len(content) > policy.max_file_bytes:
        raise SecurityViolation("FILE_SIZE_LIMIT")
    if declared_mime != "application/pdf" or not filename.casefold().endswith(".pdf"):
        raise SecurityViolation("MIME_MISMATCH")
    if not content.startswith(b"%PDF-"):
        raise SecurityViolation("MIME_MISMATCH")

    _reject_active_pdf_markers(content)
    try:
        document = pymupdf.open(stream=content, filetype="pdf")
    except (RuntimeError, ValueError) as error:
        raise SecurityViolation("PDF_MALFORMED") from error
    try:
        if document.needs_pass:
            raise SecurityViolation("PDF_ENCRYPTED")
        page_count = document.page_count
        if page_count < 1 or page_count > policy.max_pdf_pages:
            raise SecurityViolation("PDF_PAGE_LIMIT")
        pixels_per_point = policy.render_dpi / 72
        for page in document:
            pixels = int(page.rect.width * pixels_per_point) * int(
                page.rect.height * pixels_per_point
            )
            if pixels > policy.max_page_pixels:
                raise SecurityViolation("PDF_PAGE_PIXEL_LIMIT")
        for xref in range(1, document.xref_length()):
            try:
                raw_object = document.xref_object(xref, compressed=False).encode(
                    "latin-1", errors="ignore"
                )
            except RuntimeError:
                continue
            _reject_active_pdf_markers(raw_object)
    finally:
        document.close()
    return PdfInspection(page_count=page_count)


def _reject_active_pdf_markers(content: bytes) -> None:
    if b"/EmbeddedFiles" in content or b"/EmbeddedFile" in content:
        raise SecurityViolation("PDF_EMBEDDED_FILE")
    if b"/Encrypt" in content:
        raise SecurityViolation("PDF_ENCRYPTED")
    if b"/Launch" in content or b"/GoToR" in content:
        raise SecurityViolation("PDF_EXTERNAL_LAUNCH")
    active_markers = (b"/JavaScript", b"/JS", b"/OpenAction", b"/AA")
    if any(marker in content for marker in active_markers):
        raise SecurityViolation("PDF_ACTIVE_ACTION")


def inspect_zip_bytes(
    content: bytes,
    *,
    filename: str,
    declared_mime: str,
    policy: FileSecurityPolicy,
) -> ZipInspection:
    if len(content) > policy.max_file_bytes:
        raise SecurityViolation("FILE_SIZE_LIMIT")
    if declared_mime not in {"application/zip", "application/x-zip-compressed"}:
        raise SecurityViolation("MIME_MISMATCH")
    if not filename.casefold().endswith(".zip") or not content.startswith(b"PK"):
        raise SecurityViolation("MIME_MISMATCH")
    try:
        archive = ZipFile(BytesIO(content))
    except BadZipFile as error:
        raise SecurityViolation("ZIP_MALFORMED") from error
    with archive:
        infos = archive.infolist()
        if not infos or len(infos) > policy.max_zip_entries:
            raise SecurityViolation("ZIP_ENTRY_LIMIT")
        result: list[InspectedZipEntry] = []
        normalized_names: set[str] = set()
        total_uncompressed = 0
        for info in infos:
            if info.is_dir():
                continue
            if info.flag_bits & 0x1:
                raise SecurityViolation("ZIP_ENCRYPTED_ENTRY")
            file_mode = info.external_attr >> 16
            if stat.S_IFMT(file_mode) == stat.S_IFLNK:
                raise SecurityViolation("ZIP_SYMLINK")
            normalized_path = _normalized_zip_path(info.filename)
            normalized_key = normalized_path.casefold()
            if normalized_key in normalized_names:
                raise SecurityViolation("ZIP_DUPLICATE_PATH")
            normalized_names.add(normalized_key)
            depth = len(PurePosixPath(normalized_path).parts) - 1
            if depth > 1:
                raise SecurityViolation("ZIP_DEPTH_LIMIT")
            if normalized_path.casefold().endswith((".zip", ".7z", ".rar", ".tar", ".gz")):
                raise SecurityViolation("ZIP_NESTED_ARCHIVE")
            total_uncompressed += info.file_size
            if total_uncompressed > policy.max_uncompressed_bytes:
                raise SecurityViolation("ZIP_UNCOMPRESSED_LIMIT")
            if info.file_size and (
                info.compress_size == 0
                or info.file_size / info.compress_size > policy.max_compression_ratio
            ):
                raise SecurityViolation("ZIP_COMPRESSION_RATIO")
            entry_content = archive.read(info)
            detected_mime = _detect_allowed_entry_mime(normalized_path, entry_content)
            result.append(
                InspectedZipEntry(
                    normalized_path=normalized_path,
                    depth=depth,
                    detected_mime=detected_mime,
                    byte_size=len(entry_content),
                    content=entry_content,
                )
            )
    if not result:
        raise SecurityViolation("ZIP_EMPTY")
    return ZipInspection(entries=tuple(result), total_uncompressed_bytes=total_uncompressed)


def _normalized_zip_path(value: str) -> str:
    portable = value.replace("\\", "/")
    if portable.startswith("/") or ":" in portable.split("/", maxsplit=1)[0]:
        raise SecurityViolation("ZIP_PATH_TRAVERSAL")
    parts = PurePosixPath(portable).parts
    if ".." in parts:
        raise SecurityViolation("ZIP_PATH_TRAVERSAL")
    normalized = posixpath.normpath(portable)
    if normalized in {"", "."} or normalized.startswith("../"):
        raise SecurityViolation("ZIP_PATH_TRAVERSAL")
    return normalized


def _detect_allowed_entry_mime(filename: str, content: bytes) -> str:
    lowered = filename.casefold()
    if lowered.endswith(".pdf") and content.startswith(b"%PDF-"):
        return "application/pdf"
    html_prefix = content[:512].lstrip().lower()
    if lowered.endswith((".html", ".htm")) and (
        html_prefix.startswith(b"<!doctype html") or b"<html" in html_prefix
    ):
        return "text/html"
    raise SecurityViolation("ZIP_MIME_NOT_ALLOWED")
