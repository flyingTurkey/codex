"""Private SHA-256 addressed S3-compatible object storage."""

import asyncio
from typing import Any

import aioboto3
from botocore.config import Config
from botocore.exceptions import ClientError

from srbg_api.config import Settings


class S3ObjectStore:
    def __init__(self, settings: Settings) -> None:
        self._session = aioboto3.Session()
        self._endpoint_url = settings.s3_endpoint_url
        self._access_key = settings.s3_access_key
        self._secret_key = settings.s3_secret_key
        self._bucket = settings.s3_bucket
        self._region = settings.s3_region
        self._timeout_seconds = settings.external_io_timeout_seconds
        self._client_config = Config(
            connect_timeout=self._timeout_seconds,
            read_timeout=self._timeout_seconds,
            retries={"mode": "standard", "total_max_attempts": 3},
        )

    def _client(self) -> Any:
        return self._session.client(
            "s3",
            endpoint_url=self._endpoint_url,
            aws_access_key_id=self._access_key,
            aws_secret_access_key=self._secret_key,
            region_name=self._region,
            config=self._client_config,
        )

    async def put_if_absent(self, key: str, content: bytes, content_type: str) -> str:
        async with asyncio.timeout(self._timeout_seconds):
            async with self._client() as client:
                try:
                    result = await client.put_object(
                        Bucket=self._bucket,
                        Key=key,
                        Body=content,
                        ContentType=content_type,
                        IfNoneMatch="*",
                        Metadata={"sha256": key.rsplit("/", 1)[-1]},
                    )
                    return str(result.get("ETag", "")).strip('"')
                except ClientError as exc:
                    error = exc.response.get("Error", {})
                    if str(error.get("Code")) in {"PreconditionFailed", "412"}:
                        head = await client.head_object(Bucket=self._bucket, Key=key)
                        return str(head.get("ETag", "")).strip('"')
                    raise

    async def get_bytes(self, key: str, *, max_bytes: int | None = None) -> bytes:
        async with asyncio.timeout(self._timeout_seconds):
            async with self._client() as client:
                result = await client.get_object(Bucket=self._bucket, Key=key)
                content_length = result.get("ContentLength")
                if (
                    max_bytes is not None
                    and isinstance(content_length, int)
                    and content_length > max_bytes
                ):
                    raise OSError("object exceeds bounded read limit")
                body = result["Body"]
                content = bytes(
                    await body.read() if max_bytes is None else await body.read(max_bytes + 1)
                )
                if max_bytes is not None and len(content) > max_bytes:
                    raise OSError("object exceeds bounded read limit")
                return content

    async def erase(self, object_key: str) -> None:
        """Delete one content-addressed object under the bounded S3 policy."""
        async with asyncio.timeout(self._timeout_seconds):
            async with self._client() as client:
                await client.delete_object(Bucket=self._bucket, Key=object_key)
