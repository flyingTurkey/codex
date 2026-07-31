import ipaddress
import socket
import ssl
from collections.abc import Iterable
from typing import Any

import dns.message
import dns.rdatatype
import dns.rrset
import httpcore2
import pytest
from srbg_api.acquisition.live import (
    IndependentDohResolver,
    Rfc8484DohLookup,
    _Socks5ProxyBackend,
)


class RecordingDohLookup:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, float]] = []

    async def resolve(
        self,
        hostname: str,
        record_type: str,
        *,
        timeout_seconds: float,
    ) -> tuple[str, ...]:
        self.calls.append((hostname, record_type, timeout_seconds))
        if record_type == "A":
            return ("93.184.216.34",)
        return ("2606:2800:220:1:248:1893:25c8:1946",)


class UnavailableDohLookup:
    async def resolve(
        self,
        hostname: str,
        record_type: str,
        *,
        timeout_seconds: float,
    ) -> tuple[str, ...]:
        del hostname, record_type, timeout_seconds
        raise TimeoutError("resolver unavailable")


@pytest.mark.asyncio
async def test_independent_doh_resolver_ignores_vpn_synthetic_system_dns(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def synthetic_system_dns(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("source resolution must not use VPN-controlled system DNS")

    monkeypatch.setattr(socket, "getaddrinfo", synthetic_system_dns)
    lookup = RecordingDohLookup()
    resolver = IndependentDohResolver(lookup=lookup)

    addresses = await resolver.resolve("source.example.test", timeout_seconds=2.5)

    assert addresses == (
        "2606:2800:220:1:248:1893:25c8:1946",
        "93.184.216.34",
    )
    assert set(lookup.calls) == {
        ("source.example.test", "A", 2.5),
        ("source.example.test", "AAAA", 2.5),
    }


@pytest.mark.asyncio
async def test_independent_doh_resolver_fails_closed_without_system_dns_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def synthetic_system_dns(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("fail-closed resolution must not consult system DNS")

    monkeypatch.setattr(socket, "getaddrinfo", synthetic_system_dns)
    resolver = IndependentDohResolver(lookup=UnavailableDohLookup())

    with pytest.raises(OSError, match="trusted DNS resolution failed"):
        await resolver.resolve("source.example.test", timeout_seconds=2.5)


@pytest.mark.asyncio
async def test_rfc8484_lookup_uses_authenticated_wire_messages() -> None:
    class RecordingWireSender:
        def __init__(self) -> None:
            self.calls: list[tuple[str, str, float]] = []

        async def exchange(
            self,
            endpoint_url: str,
            bootstrap_address: str,
            query_wire: bytes,
            *,
            timeout_seconds: float,
        ) -> bytes:
            self.calls.append((endpoint_url, bootstrap_address, timeout_seconds))
            query = dns.message.from_wire(query_wire)
            response = dns.message.make_response(query)
            question = query.question[0]
            if question.rdtype == dns.rdatatype.A:
                response.answer.append(
                    dns.rrset.from_text(
                        question.name.to_text(),
                        60,
                        "IN",
                        "A",
                        "93.184.216.34",
                    )
                )
            return response.to_wire()

    sender = RecordingWireSender()
    lookup = Rfc8484DohLookup(
        endpoint_url="https://dns.alidns.com/dns-query",
        bootstrap_address="223.5.5.5",
        sender=sender,
    )
    resolver = IndependentDohResolver(lookup=lookup)

    addresses = await resolver.resolve("source.example.test", timeout_seconds=2.5)

    assert addresses == ("93.184.216.34",)
    assert sender.calls == [
        ("https://dns.alidns.com/dns-query", "223.5.5.5", 2.5),
        ("https://dns.alidns.com/dns-query", "223.5.5.5", 2.5),
    ]


class ScriptedProxyStream(httpcore2.AsyncNetworkStream):
    def __init__(self, reads: list[bytes]) -> None:
        self.reads = reads
        self.writes: list[bytes] = []
        self.closed = False
        self.tls_server_names: list[str | None] = []

    async def read(
        self,
        max_bytes: int,
        timeout: float | None = None,  # noqa: ASYNC109 - fake httpcore stream
    ) -> bytes:
        del max_bytes, timeout
        return self.reads.pop(0)

    async def write(
        self,
        buffer: bytes,
        timeout: float | None = None,  # noqa: ASYNC109 - fake httpcore stream
    ) -> None:
        del timeout
        self.writes.append(buffer)

    async def aclose(self) -> None:
        self.closed = True

    async def start_tls(
        self,
        ssl_context: ssl.SSLContext,
        server_hostname: str | None = None,
        timeout: float | None = None,  # noqa: ASYNC109 - fake httpcore stream
    ) -> httpcore2.AsyncNetworkStream:
        del ssl_context, timeout
        self.tls_server_names.append(server_hostname)
        return self

    def get_extra_info(self, info: str) -> Any:
        if info == "server_addr":
            return ("127.0.0.1", 7890)
        return None


class RecordingProxyConnector(httpcore2.AsyncNetworkBackend):
    def __init__(self, stream: ScriptedProxyStream) -> None:
        self.stream = stream
        self.calls: list[tuple[str, int]] = []

    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,  # noqa: ASYNC109 - fake httpcore backend
        local_address: str | None = None,
        socket_options: Iterable[httpcore2.SOCKET_OPTION] | None = None,
    ) -> httpcore2.AsyncNetworkStream:
        del timeout, local_address, socket_options
        self.calls.append((host, port))
        return self.stream

    async def connect_unix_socket(
        self,
        path: str,
        timeout: float | None = None,  # noqa: ASYNC109 - fake httpcore backend
        socket_options: Iterable[httpcore2.SOCKET_OPTION] | None = None,
    ) -> httpcore2.AsyncNetworkStream:
        del path, timeout, socket_options
        raise AssertionError("SOCKS acquisition must not use a Unix socket")

    async def sleep(self, seconds: float) -> None:
        del seconds


@pytest.mark.asyncio
async def test_loopback_socks5_connects_only_to_the_doh_pinned_target_ip() -> None:
    stream = ScriptedProxyStream(
        [
            b"\x05\x00",
            b"\x05\x00\x00\x01",
            b"\x7f\x00\x00\x01\x1e\xd2",
        ]
    )
    connector = RecordingProxyConnector(stream)
    backend = _Socks5ProxyBackend(
        "socks5://127.0.0.1:7890",
        delegate=connector,
    )

    tunnel = await backend.connect_tcp("93.184.216.34", 443, timeout=2.0)
    await tunnel.start_tls(ssl.create_default_context(), "source.example.test", 2.0)

    assert connector.calls == [("127.0.0.1", 7890)]
    assert stream.writes == [
        b"\x05\x01\x00",
        b"\x05\x01\x00\x01" + ipaddress.ip_address("93.184.216.34").packed + b"\x01\xbb",
    ]
    assert b"source.example.test" not in b"".join(stream.writes)
    assert tunnel.get_extra_info("server_addr") == ("93.184.216.34", 443)
    assert stream.tls_server_names == ["source.example.test"]


@pytest.mark.parametrize(
    "proxy_url",
    [
        "socks5://proxy.example.test:7890",
        "socks5://192.168.1.2:7890",
        "socks5://user:secret@127.0.0.1:7890",
        "http://127.0.0.1:7890",
    ],
)
def test_acquisition_socks5_proxy_is_loopback_only_and_has_no_credentials(
    proxy_url: str,
) -> None:
    with pytest.raises(ValueError, match="loopback SOCKS5"):
        _Socks5ProxyBackend(proxy_url)
