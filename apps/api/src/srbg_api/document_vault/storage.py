"""Private SHA-256 addressed S3-compatible object storage."""

import asyncio
import hmac
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
                        content_length = head.get("ContentLength")
                        if content_length != len(content):
                            raise RuntimeError("RAW_OBJECT_HASH_MISMATCH") from None
                        existing_result = await client.get_object(Bucket=self._bucket, Key=key)
                        body = existing_result["Body"]
                        existing = bytearray()
                        while len(existing) <= len(content):
                            chunk = bytes(await body.read(len(content) + 1 - len(existing)))
                            if not chunk:
                                break
                            existing.extend(chunk)
                        if not hmac.compare_digest(bytes(existing), content):
                            raise RuntimeError("RAW_OBJECT_HASH_MISMATCH") from None
                        return str(head.get("ETag", "")).strip('"')
                    raise

    async def get_bytes(self, key: str, *, max_bytes: int | None = None) -> bytes:
        async with asyncio.timeout(self._timeout_seconds):
            async with self._client() as client:
                try:
                    result = await client.get_object(Bucket=self._bucket, Key=key)
                except ClientError as exc:
                    error = exc.response.get("Error", {})
                    if str(error.get("Code")) in {"404", "NoSuchKey", "NotFound"}:
                        raise FileNotFoundError(key) from exc
                    raise OSError("private object read failed") from exc
                content_length = result.get("ContentLength")
                if (
                    max_bytes is not None
                    and isinstance(content_length, int)
                    and content_length > max_bytes
                ):
                    raise OSError("object exceeds bounded read limit")
                body = result["Body"]
                if max_bytes is None:
                    return bytes(await body.read())
                content = bytearray()
                while len(content) <= max_bytes:
                    chunk = bytes(await body.read(max_bytes + 1 - len(content)))
                    if not chunk:
                        return bytes(content)
                    content.extend(chunk)
                raise OSError("object exceeds bounded read limit")

    async def presigned_get(self, key: str, *, max_age_seconds: int) -> str:
        if max_age_seconds < 1 or max_age_seconds > 300:
            raise ValueError("signed download lifetime must be between 1 and 300 seconds")
        async with asyncio.timeout(self._timeout_seconds):
            async with self._client() as client:
                return str(
                    await client.generate_presigned_url(
                        "get_object",
                        Params={"Bucket": self._bucket, "Key": key},
                        ExpiresIn=max_age_seconds,
                    )
                )

    async def object_exists(self, key: str) -> bool:
        """Check the private object before issuing a signed redirect."""

        async with asyncio.timeout(self._timeout_seconds):
            async with self._client() as client:
                try:
                    await client.head_object(Bucket=self._bucket, Key=key)
                except ClientError as exc:
                    error = exc.response.get("Error", {})
                    if str(error.get("Code")) in {"404", "NoSuchKey", "NotFound"}:
                        return False
                    raise OSError("private object lookup failed") from exc
        return True

    async def erase(self, object_key: str) -> None:
        """Delete one content-addressed object under the bounded S3 policy."""
        async with asyncio.timeout(self._timeout_seconds):
            async with self._client() as client:
                await client.delete_object(Bucket=self._bucket, Key=object_key)
