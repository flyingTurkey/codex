"""Private SHA-256 addressed S3-compatible object storage."""

from typing import Any

import aioboto3
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

    def _client(self) -> Any:
        return self._session.client(
            "s3",
            endpoint_url=self._endpoint_url,
            aws_access_key_id=self._access_key,
            aws_secret_access_key=self._secret_key,
            region_name=self._region,
        )

    async def put_if_absent(self, key: str, content: bytes, content_type: str) -> str:
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

    async def get_bytes(self, key: str) -> bytes:
        async with self._client() as client:
            result = await client.get_object(Bucket=self._bucket, Key=key)
            body = result["Body"]
            return bytes(await body.read())
