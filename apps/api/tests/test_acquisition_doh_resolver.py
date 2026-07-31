import socket

import dns.message
import dns.rdatatype
import dns.rrset
import pytest
from srbg_api.acquisition.live import IndependentDohResolver, Rfc8484DohLookup


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
