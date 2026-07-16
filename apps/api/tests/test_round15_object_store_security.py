from __future__ import annotations

import asyncio
from types import TracebackType
from typing import Any

import pytest
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
