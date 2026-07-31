"""Production DNS, clock, and HTTP transport implementations."""

import asyncio
import ipaddress
import socket
from collections.abc import Iterable
from datetime import UTC, datetime
from time import monotonic
from typing import Any, Protocol
from urllib.parse import urlsplit

import dns.exception
import dns.message
import dns.rcode
import dns.rdatatype
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


class _DohLookup(Protocol):
    async def resolve(
        self,
        hostname: str,
        record_type: str,
        *,
        timeout_seconds: float,
    ) -> tuple[str, ...]: ...


DEFAULT_ACQUISITION_DOH_URL = "https://dns.alidns.com/dns-query"
DEFAULT_ACQUISITION_DOH_BOOTSTRAP_ADDRESS = "223.5.5.5"
MAX_DNS_MESSAGE_BYTES = 65_535


class _DohWireSender(Protocol):
    async def exchange(
        self,
        endpoint_url: str,
        bootstrap_address: str,
        query_wire: bytes,
        *,
        timeout_seconds: float,
    ) -> bytes: ...


class _Httpx2DohWireSender:
    async def exchange(
        self,
        endpoint_url: str,
        bootstrap_address: str,
        query_wire: bytes,
        *,
        timeout_seconds: float,
    ) -> bytes:
        hostname = urlsplit(endpoint_url).hostname
        if hostname is None:
            raise OSError("trusted DNS endpoint has no hostname")
        validated_ips = frozenset({bootstrap_address})
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
                    "POST",
                    endpoint_url,
                    headers={
                        "Accept": "application/dns-message",
                        "Content-Type": "application/dns-message",
                    },
                    content=query_wire,
                    timeout=timeout_seconds,
                ) as response:
                    peer_ip = _peer_ip(response.extensions)
                    if peer_ip not in validated_ips:
                        raise OSError("trusted DNS peer did not match its bootstrap address")
                    content = await read_bounded_body(
                        response.aiter_bytes(),
                        content_length=response.headers.get("content-length"),
                        max_response_bytes=MAX_DNS_MESSAGE_BYTES,
                    )
                    content_type = response.headers.get("content-type", "").split(";", 1)[0]
                    if not 200 <= response.status_code < 300:
                        raise OSError("trusted DNS endpoint returned a rejected status")
                    if content_type.strip().casefold() != "application/dns-message":
                        raise OSError("trusted DNS endpoint returned an invalid content type")
                    return content
        except ResponseTooLarge:
            raise
        except httpx.HTTPError as error:
            raise OSError("trusted DNS HTTPS request failed") from error


class Rfc8484DohLookup:
    def __init__(
        self,
        *,
        endpoint_url: str,
        bootstrap_address: str,
        sender: _DohWireSender | None = None,
    ) -> None:
        endpoint = urlsplit(endpoint_url)
        if (
            endpoint.scheme != "https"
            or endpoint.hostname is None
            or endpoint.path != "/dns-query"
            or endpoint.port not in {None, 443}
            or endpoint.username is not None
            or endpoint.password is not None
            or endpoint.query
            or endpoint.fragment
        ):
            raise ValueError("trusted DNS endpoint must be an exact HTTPS /dns-query URL")
        bootstrap = ipaddress.ip_address(bootstrap_address)
        if not bootstrap.is_global or bootstrap.is_multicast or bootstrap.is_reserved:
            raise ValueError("trusted DNS bootstrap address must be a direct public IP")
        self._endpoint_url = endpoint_url
        self._bootstrap_address = str(bootstrap)
        self._sender = sender or _Httpx2DohWireSender()

    async def resolve(
        self,
        hostname: str,
        record_type: str,
        *,
        timeout_seconds: float,
    ) -> tuple[str, ...]:
        if record_type not in {"A", "AAAA"}:
            raise ValueError("trusted DNS record type is not allowed")
        query = dns.message.make_query(hostname, record_type)
        response_wire = await self._sender.exchange(
            self._endpoint_url,
            self._bootstrap_address,
            query.to_wire(),
            timeout_seconds=timeout_seconds,
        )
        try:
            response = dns.message.from_wire(response_wire)
        except dns.exception.DNSException as error:
            raise OSError("trusted DNS returned an invalid wire response") from error
        if not query.is_response(response):
            raise OSError("trusted DNS response did not match its query")
        response_code = response.rcode()
        if response_code == dns.rcode.NXDOMAIN:
            raise OSError("trusted DNS reported that the source hostname does not exist")
        if response_code != dns.rcode.NOERROR:
            raise OSError("trusted DNS returned a rejected response code")
        expected_type = dns.rdatatype.from_text(record_type)
        addresses: list[str] = []
        for answer in response.answer:
            if answer.rdtype != expected_type:
                continue
            for record in answer:
                address = getattr(record, "address", None)
                if isinstance(address, str):
                    addresses.append(address)
        return tuple(addresses)


class IndependentDohResolver:
    """Resolve acquisition origins without consulting VPN-controlled system DNS."""

    def __init__(
        self,
        *,
        lookup: _DohLookup | None = None,
        endpoint_url: str = DEFAULT_ACQUISITION_DOH_URL,
        bootstrap_address: str = DEFAULT_ACQUISITION_DOH_BOOTSTRAP_ADDRESS,
    ) -> None:
        self._lookup = lookup or Rfc8484DohLookup(
            endpoint_url=endpoint_url,
            bootstrap_address=bootstrap_address,
        )

    async def resolve(
        self,
        hostname: str,
        *,
        timeout_seconds: float,
    ) -> tuple[str, ...]:
        normalized = hostname.rstrip(".").casefold()
        try:
            ipv4, ipv6 = await asyncio.gather(
                self._lookup.resolve(normalized, "A", timeout_seconds=timeout_seconds),
                self._lookup.resolve(normalized, "AAAA", timeout_seconds=timeout_seconds),
            )
        except Exception as error:
            raise OSError("trusted DNS resolution failed") from error
        addresses = tuple(sorted(set((*ipv4, *ipv6))))
        if not addresses:
            raise OSError("trusted DNS returned no source addresses")
        if len(addresses) > MAX_VALIDATED_DNS_ADDRESSES:
            raise OSError("source hostname returned too many trusted DNS addresses")
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
