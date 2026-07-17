import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime

import pytest
from srbg_api.acquisition.contracts import SourceCheckpoint
from srbg_api.acquisition.http import (
    CircuitOpen,
    FetchPolicy,
    HttpResponse,
    ResilientHttpClient,
    SsrfRejected,
)


class FakeResolver:
    def __init__(self, addresses: dict[str, tuple[str, ...]]) -> None:
        self.addresses = addresses

    async def resolve(
        self,
        hostname: str,
        *,
        timeout_seconds: float,
    ) -> tuple[str, ...]:
        assert timeout_seconds == 5.0
        return self.addresses[hostname]


class FakeTransport:
    def __init__(self, responses: list[HttpResponse]) -> None:
        self.responses = responses
        self.calls: list[tuple[str, dict[str, str], float]] = []

    async def request(
        self,
        url: str,
        *,
        headers: dict[str, str],
        timeout_seconds: float,
        max_response_bytes: int,
        validated_ips: frozenset[str],
    ) -> HttpResponse:
        del max_response_bytes, validated_ips
        self.calls.append((url, headers, timeout_seconds))
        return self.responses.pop(0)


@dataclass
class FakeClock:
    value: float = 100.0

    def monotonic(self) -> float:
        return self.value

    async def sleep(self, seconds: float) -> None:
        self.value += seconds

    def now(self) -> datetime:
        return datetime(2026, 7, 14, 1, 0, tzinfo=UTC)


def _policy(**overrides: object) -> FetchPolicy:
    values: dict[str, object] = {
        "allowed_hosts": ("www.mem.gov.cn",),
        "timeout_seconds": 5.0,
        "max_attempts": 2,
        "base_backoff_seconds": 0.1,
        "rate_limit_per_minute": 60,
        "minimum_interval_seconds": 1,
        "circuit_failure_threshold": 1,
        "circuit_reset_seconds": 30,
        "max_redirects": 2,
        "user_agent": "SRBGSourceAdapter/1.0",
    }
    values.update(overrides)
    return FetchPolicy(**values)


def test_private_dns_resolution_is_rejected_before_transport() -> None:
    transport = FakeTransport([])
    client = ResilientHttpClient(
        _policy(),
        resolver=FakeResolver({"www.mem.gov.cn": ("127.0.0.1",)}),
        transport=transport,
        clock=FakeClock(),
    )

    with pytest.raises(SsrfRejected, match="public"):
        asyncio.run(
            client.get(
                "https://www.mem.gov.cn/gk/list.shtml",
                checkpoint=SourceCheckpoint(),
            )
        )
    assert transport.calls == []


def test_redirect_target_is_revalidated_and_private_destination_is_not_requested() -> None:
    transport = FakeTransport(
        [
            HttpResponse(
                status_code=302,
                headers={"location": "http://127.0.0.1/admin"},
                peer_ip="8.8.8.8",
            )
        ]
    )
    client = ResilientHttpClient(
        _policy(),
        resolver=FakeResolver({"www.mem.gov.cn": ("8.8.8.8",)}),
        transport=transport,
        clock=FakeClock(),
    )

    with pytest.raises(SsrfRejected):
        asyncio.run(
            client.get(
                "https://www.mem.gov.cn/gk/list.shtml",
                checkpoint=SourceCheckpoint(),
            )
        )
    assert len(transport.calls) == 1


def test_conditional_request_returns_not_modified_without_content() -> None:
    transport = FakeTransport(
        [
            HttpResponse(
                status_code=304,
                headers={"etag": 'W/"fixture"', "last-modified": "Mon, 13 Jul 2026 10:43:55 GMT"},
                peer_ip="8.8.8.8",
            )
        ]
    )
    client = ResilientHttpClient(
        _policy(),
        resolver=FakeResolver({"www.mem.gov.cn": ("8.8.8.8",)}),
        transport=transport,
        clock=FakeClock(),
    )

    result = asyncio.run(
        client.get(
            "https://www.mem.gov.cn/gk/list.shtml",
            checkpoint=SourceCheckpoint(
                etag='W/"fixture"',
                last_modified="Mon, 13 Jul 2026 10:43:55 GMT",
            ),
        )
    )

    headers = transport.calls[0][1]
    assert headers["If-None-Match"] == 'W/"fixture"'
    assert headers["If-Modified-Since"] == "Mon, 13 Jul 2026 10:43:55 GMT"
    assert headers["User-Agent"] == "SRBGSourceAdapter/1.0"
    assert result.not_modified is True
    assert result.content is None


def test_optional_public_metadata_fetch_can_observe_missing_resource() -> None:
    transport = FakeTransport(
        [HttpResponse(status_code=404, headers={}, content=b"not found", peer_ip="8.8.8.8")]
    )
    client = ResilientHttpClient(
        _policy(max_attempts=1),
        resolver=FakeResolver({"www.mem.gov.cn": ("8.8.8.8",)}),
        transport=transport,
        clock=FakeClock(),
    )

    result = asyncio.run(
        client.get(
            "https://www.mem.gov.cn/robots.txt",
            checkpoint=SourceCheckpoint(),
            allow_not_found=True,
        )
    )

    assert result.status_code == 404
    assert result.content == b"not found"


def test_retry_is_bounded_then_circuit_opens_for_subsequent_request() -> None:
    transport = FakeTransport(
        [
            HttpResponse(status_code=503, headers={}, peer_ip="8.8.8.8"),
            HttpResponse(status_code=503, headers={}, peer_ip="8.8.8.8"),
        ]
    )
    clock = FakeClock()
    client = ResilientHttpClient(
        _policy(),
        resolver=FakeResolver({"www.mem.gov.cn": ("8.8.8.8",)}),
        transport=transport,
        clock=clock,
    )

    with pytest.raises(OSError, match="503"):
        asyncio.run(
            client.get(
                "https://www.mem.gov.cn/gk/list.shtml",
                checkpoint=SourceCheckpoint(),
            )
        )
    assert len(transport.calls) == 2

    with pytest.raises(CircuitOpen):
        asyncio.run(
            client.get(
                "https://www.mem.gov.cn/gk/list.shtml",
                checkpoint=SourceCheckpoint(),
            )
        )
    assert len(transport.calls) == 2


def test_retry_after_header_is_honored_for_rate_limited_source() -> None:
    transport = FakeTransport(
        [
            HttpResponse(
                status_code=429,
                headers={"Retry-After": "15"},
                peer_ip="8.8.8.8",
            ),
            HttpResponse(status_code=200, headers={}, content=b"{}", peer_ip="8.8.8.8"),
        ]
    )
    clock = FakeClock()
    client = ResilientHttpClient(
        _policy(base_backoff_seconds=0.1),
        resolver=FakeResolver({"www.mem.gov.cn": ("8.8.8.8",)}),
        transport=transport,
        clock=clock,
    )

    result = asyncio.run(
        client.get(
            "https://www.mem.gov.cn/gk/list.shtml",
            checkpoint=SourceCheckpoint(),
        )
    )

    assert result.status_code == 200
    assert clock.value == 115.0
