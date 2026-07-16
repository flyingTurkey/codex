"""Production DNS, clock, and HTTP transport implementations."""

import asyncio
import socket
from collections.abc import Iterable
from datetime import UTC, datetime
from time import monotonic
from typing import Any
from urllib.parse import urlsplit

import httpcore2
import httpx2 as httpx

from srbg_api.acquisition.http import (
    MAX_VALIDATED_DNS_ADDRESSES,
    HttpResponse,
    ResponseTooLarge,
    read_bounded_body,
)


class SystemResolver:
    async def resolve(
        self,
        hostname: str,
        *,
        timeout_seconds: float,
    ) -> tuple[str, ...]:
        loop = asyncio.get_running_loop()
        results = await asyncio.wait_for(
            loop.getaddrinfo(
                hostname,
                443,
                family=socket.AF_UNSPEC,
                type=socket.SOCK_STREAM,
            ),
            timeout=timeout_seconds,
        )
        addresses = tuple(sorted({str(result[4][0]) for result in results}))
        if len(addresses) > MAX_VALIDATED_DNS_ADDRESSES:
            raise OSError("source hostname returned too many DNS addresses")
        return addresses


class SystemClock:
    def monotonic(self) -> float:
        return monotonic()

    async def sleep(self, seconds: float) -> None:
        await asyncio.sleep(seconds)

    def now(self) -> datetime:
        return datetime.now(UTC)


class HttpxTransport:
    async def request(
        self,
        url: str,
        *,
        headers: dict[str, str],
        timeout_seconds: float,
        max_response_bytes: int,
        validated_ips: frozenset[str],
    ) -> HttpResponse:
        hostname = urlsplit(url).hostname
        if hostname is None:
            raise OSError("HTTP transport requires a validated hostname")
        network_backend = _PinnedNetworkBackend(
            expected_hostname=hostname,
            validated_ips=validated_ips,
        )
        transport = _PinnedHttpxTransport(network_backend)
        try:
            async with httpx.AsyncClient(
                transport=transport,
                follow_redirects=False,
                trust_env=False,
            ) as client:
                async with client.stream(
                    "GET", url, headers=headers, timeout=timeout_seconds
                ) as response:
                    peer_ip = _peer_ip(response.extensions)
                    if peer_ip is None:
                        raise OSError("HTTP transport could not verify the connected peer address")
                    content = await read_bounded_body(
                        response.aiter_bytes(),
                        content_length=response.headers.get("content-length"),
                        max_response_bytes=max_response_bytes,
                    )
                    return HttpResponse(
                        status_code=response.status_code,
                        headers=dict(response.headers),
                        content=content,
                        peer_ip=peer_ip,
                    )
        except ResponseTooLarge:
            raise
        except httpx.HTTPError as exc:
            raise OSError("source HTTP request failed") from exc

    async def close(self) -> None:
        return None


class _PinnedHttpxTransport(httpx.AsyncHTTPTransport):
    """HTTPX transport whose TCP backend never performs independent DNS resolution."""

    def __init__(self, network_backend: httpcore2.AsyncNetworkBackend) -> None:
        super().__init__(trust_env=False)
        self._pool._network_backend = network_backend


class _PinnedNetworkBackend(httpcore2.AsyncNetworkBackend):
    """Connect the original HTTP origin only through its prevalidated IP set.

    HTTP Core still retains the original origin hostname for the Host header,
    certificate verification, and TLS SNI. Only the TCP destination is replaced.
    """

    def __init__(
        self,
        *,
        expected_hostname: str,
        validated_ips: frozenset[str],
        delegate: httpcore2.AsyncNetworkBackend | None = None,
    ) -> None:
        if not validated_ips or len(validated_ips) > MAX_VALIDATED_DNS_ADDRESSES:
            raise ValueError("a pinned transport requires a bounded validated IP set")
        self._expected_hostname = expected_hostname.rstrip(".").casefold()
        self._validated_ips = tuple(sorted(validated_ips))
        self._delegate = delegate or httpcore2.AnyIOBackend()

    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,  # noqa: ASYNC109 - httpcore backend protocol
        local_address: str | None = None,
        socket_options: Iterable[httpcore2.SOCKET_OPTION] | None = None,
    ) -> httpcore2.AsyncNetworkStream:
        if host.rstrip(".").casefold() != self._expected_hostname:
            raise httpcore2.ConnectError("HTTP transport refused an unvalidated hostname")
        last_error: httpcore2.ConnectError | httpcore2.ConnectTimeout | None = None
        started_at = monotonic()
        for address in self._validated_ips:
            remaining_timeout = timeout
            if timeout is not None:
                remaining_timeout = timeout - (monotonic() - started_at)
                if remaining_timeout <= 0:
                    raise httpcore2.ConnectTimeout(
                        "HTTP transport exhausted its bounded connection deadline"
                    )
            try:
                return await self._delegate.connect_tcp(
                    address,
                    port,
                    timeout=remaining_timeout,
                    local_address=local_address,
                    socket_options=socket_options,
                )
            except (httpcore2.ConnectError, httpcore2.ConnectTimeout) as exc:
                last_error = exc
        if last_error is None:  # pragma: no cover - constructor rejects an empty set.
            raise httpcore2.ConnectError("HTTP transport has no validated destination")
        raise last_error

    async def connect_unix_socket(
        self,
        path: str,
        timeout: float | None = None,  # noqa: ASYNC109 - httpcore backend protocol
        socket_options: Iterable[httpcore2.SOCKET_OPTION] | None = None,
    ) -> httpcore2.AsyncNetworkStream:
        del path, timeout, socket_options
        raise httpcore2.ConnectError("Unix sockets are forbidden for source acquisition")

    async def sleep(self, seconds: float) -> None:
        await self._delegate.sleep(seconds)


def _peer_ip(extensions: dict[str, Any]) -> str | None:
    stream = extensions.get("network_stream")
    get_extra_info = getattr(stream, "get_extra_info", None)
    if get_extra_info is None:
        return None
    server_addr = get_extra_info("server_addr")
    if isinstance(server_addr, tuple) and server_addr:
        return str(server_addr[0])
    return None
