from __future__ import annotations

import asyncio
from types import TracebackType
from typing import Any

import pytest
from botocore.exceptions import ClientError
from srbg_api.config import Settings
from srbg_api.document_vault import storage
from srbg_api.document_vault.storage import S3ObjectStore


class _SlowClient:
    async def __aenter__(self) -> _SlowClient:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        del exc_type, exc, traceback

    async def put_object(self, **kwargs: object) -> dict[str, str]:
        del kwargs
        await asyncio.sleep(1)
        return {"ETag": "late"}


class _RecordingSession:
    def __init__(self) -> None:
        self.client_kwargs: list[dict[str, Any]] = []

    def client(self, service: str, **kwargs: Any) -> _SlowClient:
        assert service == "s3"
        self.client_kwargs.append(kwargs)
        return _SlowClient()


class _CollisionClient:
    async def __aenter__(self) -> _CollisionClient:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        del exc_type, exc, traceback

    async def put_object(self, **kwargs: object) -> dict[str, str]:
        del kwargs
        raise ClientError(
            {"Error": {"Code": "PreconditionFailed", "Message": "exists"}},
            "PutObject",
        )

    async def head_object(self, **kwargs: object) -> dict[str, object]:
        del kwargs
        return {"ETag": '"wrong"', "ContentLength": 7}


class _CollisionSession:
    def client(self, service: str, **kwargs: Any) -> _CollisionClient:
        del kwargs
        assert service == "s3"
        return _CollisionClient()


class _ExistingChunkedClient(_CollisionClient):
    async def head_object(self, **kwargs: object) -> dict[str, object]:
        del kwargs
        return {"ETag": '"existing"', "ContentLength": 12}

    async def get_object(self, **kwargs: object) -> dict[str, object]:
        del kwargs
        return {"Body": _ChunkedBody((b"first", b"-", b"second"))}


class _ExistingChunkedSession:
    def client(self, service: str, **kwargs: Any) -> _ExistingChunkedClient:
        del kwargs
        assert service == "s3"
        return _ExistingChunkedClient()


class _ChunkedBody:
    def __init__(self, chunks: tuple[bytes, ...]) -> None:
        self._chunks = list(chunks)

    async def read(self, amount: int | None = None) -> bytes:
        del amount
        return self._chunks.pop(0) if self._chunks else b""


class _ChunkedReadClient:
    async def __aenter__(self) -> _ChunkedReadClient:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        del exc_type, exc, traceback

    async def get_object(self, **kwargs: object) -> dict[str, object]:
        del kwargs
        return {
            "ContentLength": 12,
            "Body": _ChunkedBody((b"first", b"-", b"second")),
        }


class _ChunkedReadSession:
    def client(self, service: str, **kwargs: Any) -> _ChunkedReadClient:
        del kwargs
        assert service == "s3"
        return _ChunkedReadClient()


async def test_s3_operations_have_connect_read_overall_and_retry_bounds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _RecordingSession()
    monkeypatch.setattr(storage.aioboto3, "Session", lambda: session)
    timeout = 0.01
    store = S3ObjectStore(Settings(_env_file=None, external_io_timeout_seconds=timeout))

    with pytest.raises(TimeoutError):
        await store.put_if_absent("sha256/aa/hash", b"evidence", "application/octet-stream")

    client_config = session.client_kwargs[0]["config"]
    assert client_config.connect_timeout == timeout
    assert client_config.read_timeout == timeout
    assert client_config.retries["total_max_attempts"] == 3


async def test_content_address_collision_is_rejected_instead_of_trusted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(storage.aioboto3, "Session", _CollisionSession)
    store = S3ObjectStore(Settings(_env_file=None, external_io_timeout_seconds=1))

    with pytest.raises(RuntimeError, match="RAW_OBJECT_HASH_MISMATCH"):
        await store.put_if_absent(
            "sha256/ed/ed7002b439e9ac845f22357d822bac14447364012a7fe1fc7dd8cb8d4a9c9f73",
            b"evidence",
            "application/octet-stream",
        )


async def test_existing_content_address_accepts_short_async_body_chunks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(storage.aioboto3, "Session", _ExistingChunkedSession)
    store = S3ObjectStore(Settings(_env_file=None, external_io_timeout_seconds=1))

    assert (
        await store.put_if_absent(
            "sha256/00/placeholder", b"first-second", "application/octet-stream"
        )
        == "existing"
    )


async def test_bounded_read_collects_short_async_body_chunks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(storage.aioboto3, "Session", _ChunkedReadSession)
    store = S3ObjectStore(Settings(_env_file=None, external_io_timeout_seconds=1))

    assert await store.get_bytes("sha256/aa/hash", max_bytes=12) == b"first-second"
