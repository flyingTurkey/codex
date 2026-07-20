from __future__ import annotations

from contextlib import asynccontextmanager
from uuid import UUID

import pytest
from srbg_api.intelligence_v2.service import (
    MediaDeliveryUnavailable,
    PostgresV2IntelligenceService,
    ProjectionNotFound,
)

pytestmark = pytest.mark.asyncio

MEDIA_ID = UUID("019f7c00-0000-7000-8000-000000001211")


class _MappedRow:
    def __init__(self, row: dict[str, object] | None) -> None:
        self._row = row

    def mappings(self) -> _MappedRow:
        return self

    def one_or_none(self) -> dict[str, object] | None:
        return self._row


class _Connection:
    def __init__(self, row: dict[str, object] | None) -> None:
        self._row = row

    async def execute(self, _statement: object, _parameters: object) -> _MappedRow:
        return _MappedRow(self._row)


class _Engine:
    def __init__(self, row: dict[str, object] | None) -> None:
        self._row = row

    @asynccontextmanager
    async def connect(self):
        yield _Connection(self._row)

    async def dispose(self) -> None:
        pass


class _Objects:
    def __init__(self, *, exists: bool = True, failure: OSError | None = None) -> None:
        self.exists = exists
        self.failure = failure
        self.read_keys: list[str] = []
        self.signed_keys: list[tuple[str, int]] = []

    async def get_bytes(self, key: str, *, max_bytes: int | None = None) -> bytes:
        self.read_keys.append(key)
        if self.failure is not None:
            raise self.failure
        assert max_bytes == 10_000_000
        return b"safe-derived-png"

    async def object_exists(self, key: str) -> bool:
        if self.failure is not None:
            raise self.failure
        return self.exists

    async def presigned_get(self, key: str, *, max_age_seconds: int) -> str:
        self.signed_keys.append((key, max_age_seconds))
        if self.failure is not None:
            raise self.failure
        return "https://objects.example/private?expires=300"


def _row(**overrides: object) -> dict[str, object]:
    return {
        "object_key": "sha256/aa/raw",
        "mime_type": "application/pdf",
        "rights_basis": "EXPLICIT_LICENSE",
        "redistribution_allowed": True,
        "scan_status": "CLEAN",
        "attachment_scan_status": "CLEAN",
        "raw_scan_status": "CLEAN",
        "preview_object_key": "sha256/bb/preview",
        "preview_mime_type": "image/png",
    } | overrides


def _service(row: dict[str, object], objects: _Objects) -> PostgresV2IntelligenceService:
    engine = _Engine(row)
    return PostgresV2IntelligenceService(  # type: ignore[arg-type]
        engine,
        engine,
        objects,
    )


async def test_preview_reads_only_the_server_derived_object() -> None:
    objects = _Objects()
    service = _service(_row(), objects)

    content, mime = await service.media_preview(MEDIA_ID)

    assert (content, mime) == (b"safe-derived-png", "image/png")
    assert objects.read_keys == ["sha256/bb/preview"]


@pytest.mark.parametrize(
    "override",
    [
        {"rights_basis": None},
        {"scan_status": "PENDING"},
        {"attachment_scan_status": "QUARANTINED"},
        {"raw_scan_status": "REJECTED"},
        {"redistribution_allowed": False},
    ],
)
async def test_download_rechecks_current_rights_and_every_scan_boundary(
    override: dict[str, object],
) -> None:
    objects = _Objects()
    service = _service(_row(**override), objects)

    with pytest.raises(ProjectionNotFound):
        await service.media_download(MEDIA_ID, max_age_seconds=300)

    assert objects.signed_keys == []


async def test_download_fails_as_not_found_when_private_object_no_longer_exists() -> None:
    service = _service(_row(), _Objects(exists=False))

    with pytest.raises(ProjectionNotFound):
        await service.media_download(MEDIA_ID, max_age_seconds=300)


async def test_storage_request_failure_is_a_deterministic_unavailable_state() -> None:
    service = _service(_row(), _Objects(failure=OSError("object store timeout")))

    with pytest.raises(MediaDeliveryUnavailable):
        await service.media_preview(MEDIA_ID)
    with pytest.raises(MediaDeliveryUnavailable):
        await service.media_download(MEDIA_ID, max_age_seconds=300)
