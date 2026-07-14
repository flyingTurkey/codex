"""Production DNS, clock, and HTTP transport implementations."""

import asyncio
import socket
from datetime import UTC, datetime
from time import monotonic
from typing import Any

import httpx2 as httpx

from srbg_api.acquisition.http import HttpResponse


class SystemResolver:
    async def resolve(self, hostname: str) -> tuple[str, ...]:
        loop = asyncio.get_running_loop()
        results = await loop.getaddrinfo(
            hostname,
            443,
            family=socket.AF_UNSPEC,
            type=socket.SOCK_STREAM,
        )
        return tuple(sorted({str(result[4][0]) for result in results}))


class SystemClock:
    def monotonic(self) -> float:
        return monotonic()

    async def sleep(self, seconds: float) -> None:
        await asyncio.sleep(seconds)

    def now(self) -> datetime:
        return datetime.now(UTC)


class HttpxTransport:
    def __init__(self) -> None:
        self._client = httpx.AsyncClient(follow_redirects=False, trust_env=False)

    async def request(
        self,
        url: str,
        *,
        headers: dict[str, str],
        timeout_seconds: float,
    ) -> HttpResponse:
        try:
            response = await self._client.get(
                url,
                headers=headers,
                timeout=timeout_seconds,
            )
        except httpx.HTTPError as exc:
            raise OSError("source HTTP request failed") from exc
        peer_ip = _peer_ip(response.extensions)
        if peer_ip is None:
            raise OSError("HTTP transport could not verify the connected peer address")
        return HttpResponse(
            status_code=response.status_code,
            headers=dict(response.headers),
            content=response.content,
            peer_ip=peer_ip,
        )

    async def close(self) -> None:
        await self._client.aclose()


def _peer_ip(extensions: dict[str, Any]) -> str | None:
    stream = extensions.get("network_stream")
    get_extra_info = getattr(stream, "get_extra_info", None)
    if get_extra_info is None:
        return None
    server_addr = get_extra_info("server_addr")
    if isinstance(server_addr, tuple) and server_addr:
        return str(server_addr[0])
    return None
