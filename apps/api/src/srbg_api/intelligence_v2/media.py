"""Fail-closed registration and reader policy for licensed v2 media."""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass
from hashlib import sha256
from typing import Protocol
from urllib.parse import unquote, urlsplit
from uuid import UUID

import pymupdf  # type: ignore[import-untyped]

ALLOWED_RIGHTS = frozenset(
    {"PUBLIC_DOMAIN", "EXPLICIT_LICENSE", "SOURCE_AUTHORIZED", "OWNER_OWNED"}
)

_PREVIEW_SOURCE_MIMES = frozenset({"image/jpeg", "image/png", "image/webp"})
_MAX_PREVIEW_SOURCE_BYTES = 10_000_000
_MAX_PREVIEW_PIXELS = 25_000_000


class MediaRejected(ValueError):
    """A stable fail-closed reason safe to persist without source bytes."""


@dataclass(frozen=True, slots=True)
class MediaRightsFact:
    """Server-side rights decision; intentionally contains no client-supplied hash."""

    media_id: UUID
    attachment_id: UUID
    source_url: str
    rights_basis: str
    rights_evidence_ref: str
    redistribution_allowed: bool


@dataclass(frozen=True, slots=True)
class CleanAttachmentAuthority:
    """Immutable attachment facts loaded from the document-vault boundary."""

    attachment_id: UUID
    document_version_id: UUID
    name: str
    object_key: str
    content_sha256: str
    byte_size: int
    detected_mime: str


@dataclass(frozen=True, slots=True)
class MediaDeliveryRecord:
    media_id: UUID
    attachment_id: UUID
    document_version_id: UUID
    name: str
    object_key: str
    source_url: str
    mime_type: str
    rights_basis: str
    rights_evidence_ref: str
    redistribution_allowed: bool
    scan_status: str
    preview_object_key: str | None
    preview_sha256: str | None
    preview_mime_type: str | None
    preview_byte_size: int | None


class MediaDeliveryRepository(Protocol):
    async def load_clean_attachment(
        self, *, attachment_id: UUID, canonical_url_sha256: str
    ) -> CleanAttachmentAuthority | None: ...

    async def save_delivery(self, record: MediaDeliveryRecord) -> None: ...


class MediaObjectStore(Protocol):
    async def get_bytes(self, key: str, *, max_bytes: int | None = None) -> bytes: ...

    async def put_if_absent(self, key: str, content: bytes, content_type: str) -> str: ...


class MediaDeliveryService:
    """Bind rights only to already-acquired, CLEAN attachment evidence."""

    def __init__(self, repository: MediaDeliveryRepository, objects: MediaObjectStore) -> None:
        self._repository = repository
        self._objects = objects

    async def register(self, facts: MediaRightsFact) -> MediaDeliveryRecord:
        _validate_rights(facts)
        canonical_url_sha256 = sha256(facts.source_url.encode("utf-8")).hexdigest()
        authority = await self._repository.load_clean_attachment(
            attachment_id=facts.attachment_id,
            canonical_url_sha256=canonical_url_sha256,
        )
        if authority is None:
            raise MediaRejected("MEDIA_ATTACHMENT_NOT_AUTHORIZED")
        if authority.byte_size < 1 or authority.byte_size > 536_870_912:
            raise MediaRejected("MEDIA_FILE_SIZE_INVALID")
        content = await self._objects.get_bytes(
            authority.object_key,
            max_bytes=authority.byte_size,
        )
        if (
            len(content) != authority.byte_size
            or sha256(content).hexdigest() != authority.content_sha256
        ):
            raise MediaRejected("MEDIA_OBJECT_INTEGRITY_MISMATCH")

        preview_content = _safe_preview(content, authority.detected_mime)
        preview_key: str | None = None
        preview_sha256: str | None = None
        preview_mime: str | None = None
        preview_size: int | None = None
        if preview_content is not None:
            preview_sha256 = sha256(preview_content).hexdigest()
            preview_key = f"sha256/{preview_sha256[:2]}/{preview_sha256}"
            preview_mime = "image/png"
            preview_size = len(preview_content)
            await self._objects.put_if_absent(preview_key, preview_content, preview_mime)

        record = MediaDeliveryRecord(
            media_id=facts.media_id,
            attachment_id=authority.attachment_id,
            document_version_id=authority.document_version_id,
            name=authority.name,
            object_key=authority.object_key,
            source_url=facts.source_url,
            mime_type=authority.detected_mime,
            rights_basis=facts.rights_basis,
            rights_evidence_ref=facts.rights_evidence_ref,
            redistribution_allowed=facts.redistribution_allowed,
            scan_status="CLEAN",
            preview_object_key=preview_key,
            preview_sha256=preview_sha256,
            preview_mime_type=preview_mime,
            preview_byte_size=preview_size,
        )
        await self._repository.save_delivery(record)
        return record


def _validate_rights(facts: MediaRightsFact) -> None:
    if facts.rights_basis not in ALLOWED_RIGHTS:
        raise MediaRejected("MEDIA_RIGHTS_NOT_ALLOWED")
    if not facts.rights_evidence_ref.strip() or len(facts.rights_evidence_ref) > 500:
        raise MediaRejected("MEDIA_RIGHTS_EVIDENCE_REQUIRED")
    if not _safe_public_source_url(facts.source_url):
        raise MediaRejected("MEDIA_SOURCE_URL_UNSAFE")


def _safe_public_source_url(value: str) -> bool:
    if not value or len(value) > 2048:
        return False
    if any(ord(character) < 32 or ord(character) == 127 for character in unquote(value)):
        return False
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError:
        return False
    if (
        parsed.scheme.casefold() != "https"
        or parsed.hostname is None
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
        or port not in {None, 443}
    ):
        return False
    try:
        ipaddress.ip_address(parsed.hostname.rstrip("."))
    except ValueError:
        return True
    return False


def _safe_preview(content: bytes, detected_mime: str) -> bytes | None:
    if detected_mime not in _PREVIEW_SOURCE_MIMES:
        return None
    if not content or len(content) > _MAX_PREVIEW_SOURCE_BYTES:
        raise MediaRejected("MEDIA_PREVIEW_SIZE_LIMIT")
    filetype = detected_mime.removeprefix("image/")
    try:
        document = pymupdf.open(stream=content, filetype=filetype)
    except (RuntimeError, ValueError) as exc:
        raise MediaRejected("MEDIA_PREVIEW_MIME_MISMATCH") from exc
    try:
        if document.page_count != 1:
            raise MediaRejected("MEDIA_PREVIEW_PAGE_COUNT")
        page = document[0]
        pixmap = page.get_pixmap(alpha=False)
        pixel_count = pixmap.width * pixmap.height
        if pixel_count < 1 or pixel_count > _MAX_PREVIEW_PIXELS:
            raise MediaRejected("MEDIA_PREVIEW_PIXEL_LIMIT")
        return bytes(pixmap.tobytes("png"))
    except RuntimeError as exc:
        raise MediaRejected("MEDIA_PREVIEW_DECODE_FAILED") from exc
    finally:
        document.close()


def can_preview(*, rights_basis: str | None, scan_status: str) -> bool:
    return rights_basis in ALLOWED_RIGHTS and scan_status == "CLEAN"


def can_download(
    *, rights_basis: str | None, scan_status: str, redistribution_allowed: bool
) -> bool:
    return (
        can_preview(rights_basis=rights_basis, scan_status=scan_status) and redistribution_allowed
    )


def projectable_preview(
    *,
    rights_basis: str | None,
    scan_status: str,
    attachment_scan_status: str,
    raw_scan_status: str,
    preview_object_key: str | None,
    preview_mime_type: str | None,
) -> bool:
    return (
        can_preview(rights_basis=rights_basis, scan_status=scan_status)
        and attachment_scan_status == "CLEAN"
        and raw_scan_status == "CLEAN"
        and preview_object_key is not None
        and preview_mime_type == "image/png"
    )


def projectable_download(
    *,
    rights_basis: str | None,
    scan_status: str,
    attachment_scan_status: str,
    raw_scan_status: str,
    redistribution_allowed: bool,
    object_key: str | None,
) -> bool:
    return (
        can_download(
            rights_basis=rights_basis,
            scan_status=scan_status,
            redistribution_allowed=redistribution_allowed,
        )
        and attachment_scan_status == "CLEAN"
        and raw_scan_status == "CLEAN"
        and object_key is not None
    )


def bounded_signed_url_ttl(requested_seconds: int) -> int:
    if requested_seconds < 1:
        raise ValueError("signed URL TTL must be positive")
    return min(requested_seconds, 300)
