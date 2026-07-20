from __future__ import annotations

from base64 import b64decode
from dataclasses import replace
from hashlib import sha256
from uuid import UUID

import pytest
from srbg_api.intelligence_v2.media import (
    CleanAttachmentAuthority,
    MediaDeliveryRecord,
    MediaDeliveryService,
    MediaRejected,
    MediaRightsFact,
    projectable_download,
    projectable_preview,
)

pytestmark = pytest.mark.asyncio

ATTACHMENT_ID = UUID("019f7c00-0000-7000-8000-000000001201")
VERSION_ID = UUID("019f7c00-0000-7000-8000-000000001202")
MEDIA_ID = UUID("019f7c00-0000-7000-8000-000000001203")
PNG = b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUB"
    "AScY42YAAAAASUVORK5CYII="
)


class FakeRepository:
    def __init__(self, authority: CleanAttachmentAuthority | None) -> None:
        self.authority = authority
        self.saved: MediaDeliveryRecord | None = None

    async def load_clean_attachment(
        self, *, attachment_id: UUID, canonical_url_sha256: str
    ) -> CleanAttachmentAuthority | None:
        assert attachment_id == ATTACHMENT_ID
        assert canonical_url_sha256 == sha256(
            b"https://example.gov.cn/material/figure.png"
        ).hexdigest()
        return self.authority

    async def save_delivery(self, record: MediaDeliveryRecord) -> None:
        self.saved = record


class FakeObjectStore:
    def __init__(self, content: bytes) -> None:
        self.content = content
        self.saved: list[tuple[str, bytes, str]] = []

    async def get_bytes(self, key: str, *, max_bytes: int | None = None) -> bytes:
        assert key.startswith("sha256/")
        assert max_bytes is not None
        return self.content

    async def put_if_absent(self, key: str, content: bytes, content_type: str) -> str:
        self.saved.append((key, content, content_type))
        return "etag"


def _authority() -> CleanAttachmentAuthority:
    digest = sha256(PNG).hexdigest()
    return CleanAttachmentAuthority(
        attachment_id=ATTACHMENT_ID,
        document_version_id=VERSION_ID,
        name="许可图片.png",
        object_key=f"sha256/{digest[:2]}/{digest}",
        content_sha256=digest,
        byte_size=len(PNG),
        detected_mime="image/png",
    )


def _rights() -> MediaRightsFact:
    return MediaRightsFact(
        media_id=MEDIA_ID,
        attachment_id=ATTACHMENT_ID,
        source_url="https://example.gov.cn/material/figure.png",
        rights_basis="SOURCE_AUTHORIZED",
        rights_evidence_ref="source-policy:copyright-review:2026-07-20",
        redistribution_allowed=True,
    )


async def test_clean_acquired_image_is_reencoded_to_a_content_addressed_safe_preview() -> None:
    repository = FakeRepository(_authority())
    objects = FakeObjectStore(PNG)

    record = await MediaDeliveryService(repository, objects).register(_rights())

    assert record.attachment_id == ATTACHMENT_ID
    assert record.object_key == _authority().object_key
    assert record.preview_mime_type == "image/png"
    assert record.preview_object_key == (
        f"sha256/{record.preview_sha256[:2]}/{record.preview_sha256}"
    )
    assert objects.saved == [
        (record.preview_object_key, objects.saved[0][1], "image/png")
    ]
    assert objects.saved[0][1].startswith(b"\x89PNG\r\n\x1a\n")
    assert repository.saved == record


async def test_registration_fails_closed_without_accepted_acquisition_url_evidence() -> None:
    service = MediaDeliveryService(FakeRepository(None), FakeObjectStore(PNG))

    with pytest.raises(MediaRejected, match="MEDIA_ATTACHMENT_NOT_AUTHORIZED"):
        await service.register(_rights())


async def test_registration_ignores_client_hashes_and_verifies_authoritative_object_bytes() -> None:
    authority = replace(_authority(), content_sha256="0" * 64)
    service = MediaDeliveryService(FakeRepository(authority), FakeObjectStore(PNG))

    with pytest.raises(MediaRejected, match="MEDIA_OBJECT_INTEGRITY_MISMATCH"):
        await service.register(_rights())


@pytest.mark.parametrize(
    ("source_url", "rights_basis", "rights_evidence_ref", "reason"),
    [
        (
            "http://127.0.0.1/private.png",
            "SOURCE_AUTHORIZED",
            "source-policy:1",
            "MEDIA_SOURCE_URL_UNSAFE",
        ),
        (
            "https://example.gov.cn/image.png",
            "ALL_RIGHTS_RESERVED",
            "source-policy:1",
            "MEDIA_RIGHTS_NOT_ALLOWED",
        ),
        (
            "https://example.gov.cn/image.png",
            "EXPLICIT_LICENSE",
            "",
            "MEDIA_RIGHTS_EVIDENCE_REQUIRED",
        ),
    ],
)
async def test_rights_and_public_source_url_are_fail_closed(
    source_url: str, rights_basis: str, rights_evidence_ref: str, reason: str
) -> None:
    service = MediaDeliveryService(FakeRepository(_authority()), FakeObjectStore(PNG))
    facts = replace(
        _rights(),
        source_url=source_url,
        rights_basis=rights_basis,
        rights_evidence_ref=rights_evidence_ref,
    )

    with pytest.raises(MediaRejected, match=reason):
        await service.register(facts)


async def test_reader_projection_requires_safe_derivative_and_all_current_scan_facts() -> None:
    common = {
        "rights_basis": "EXPLICIT_LICENSE",
        "scan_status": "CLEAN",
        "attachment_scan_status": "CLEAN",
        "raw_scan_status": "CLEAN",
    }

    assert projectable_preview(
        **common,
        preview_object_key="sha256/aa/" + "a" * 64,
        preview_mime_type="image/png",
    )
    assert not projectable_preview(
        **common,
        preview_object_key=None,
        preview_mime_type=None,
    )
    assert projectable_download(**common, redistribution_allowed=True, object_key="sha256/raw")
    assert not projectable_download(
        **(common | {"attachment_scan_status": "QUARANTINED"}),
        redistribution_allowed=True,
        object_key="sha256/raw",
    )
