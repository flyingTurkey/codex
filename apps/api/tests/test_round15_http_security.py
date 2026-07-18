from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID

import pytest
from srbg_api.acquisition.contracts import SourceCheckpoint
from srbg_api.acquisition.http import (
    FetchPolicy,
    HttpResponse,
    PhysicalAttemptReservation,
    ResilientHttpClient,
    ResponseTooLarge,
    SsrfRejected,
    read_bounded_body,
)
from srbg_api.acquisition.live import _PinnedNetworkBackend


class SequenceResolver:
    def __init__(self, answers: dict[str, list[tuple[str, ...]]]) -> None:
        self._answers = answers
        self.calls: list[str] = []
        self.timeouts: list[float | None] = []

    async def resolve(
        self,
        hostname: str,
        *,
        timeout_seconds: float | None = None,
    ) -> tuple[str, ...]:
        self.calls.append(hostname)
        self.timeouts.append(timeout_seconds)
        values = self._answers[hostname]
        if len(values) == 1:
            return values[0]
        return values.pop(0)


@dataclass
class RecordingTransport:
    responses: list[HttpResponse]
    calls: list[tuple[str, dict[str, str], float, int, frozenset[str]]] = field(
        default_factory=list
    )

    async def request(
        self,
        url: str,
        *,
        headers: dict[str, str],
        timeout_seconds: float,
        max_response_bytes: int,
        validated_ips: frozenset[str],
    ) -> HttpResponse:
        self.calls.append((url, dict(headers), timeout_seconds, max_response_bytes, validated_ips))
        return self.responses.pop(0)


@dataclass
class FakeClock:
    value: float = 10.0
    sleeps: list[float] = field(default_factory=list)

    def monotonic(self) -> float:
        return self.value

    async def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.value += seconds

    def now(self) -> datetime:
        return datetime(2026, 7, 16, tzinfo=UTC)


@dataclass
class CoordinatedClock(FakeClock):
    async def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        target = self.value + seconds
        await asyncio.sleep(0)
        self.value = max(self.value, target)


class TimestampTransport(RecordingTransport):
    def __init__(self, clock: FakeClock) -> None:
        super().__init__(
            [
                HttpResponse(status_code=200, headers={}, content=b"ok", peer_ip="8.8.8.8")
                for _ in range(3)
            ]
        )
        self._clock = clock
        self.request_times: list[float] = []

    async def request(
        self,
        url: str,
        *,
        headers: dict[str, str],
        timeout_seconds: float,
        max_response_bytes: int,
        validated_ips: frozenset[str],
    ) -> HttpResponse:
        self.request_times.append(self._clock.monotonic())
        return await super().request(
            url,
            headers=headers,
            timeout_seconds=timeout_seconds,
            max_response_bytes=max_response_bytes,
            validated_ips=validated_ips,
        )


@dataclass
class RecordingAttemptObserver:
    settlements: list[tuple[int, bool, str | None]] = field(default_factory=list)

    async def reserve(self, url: str, requested_max_bytes: int) -> PhysicalAttemptReservation:
        assert url.startswith("https://source.example.test/")
        assert requested_max_bytes == 64
        return PhysicalAttemptReservation(UUID("019b0000-0000-7000-8000-000000003104"), 7)

    async def settle(
        self,
        reservation: PhysicalAttemptReservation,
        *,
        response_bytes: int,
        failed: bool,
        failure_code: str | None,
    ) -> None:
        assert reservation.max_response_bytes == 7
        self.settlements.append((response_bytes, failed, failure_code))


def _policy(
    *,
    allowed_hosts: tuple[str, ...] = ("source.example.test",),
    max_backoff_seconds: float = 60.0,
) -> FetchPolicy:
    return FetchPolicy(
        allowed_hosts=allowed_hosts,
        timeout_seconds=3.5,
        max_attempts=2,
        base_backoff_seconds=0.25,
        rate_limit_per_minute=30,
        minimum_interval_seconds=1,
        circuit_failure_threshold=3,
        circuit_reset_seconds=60,
        max_redirects=2,
        user_agent="SRBG-Connector/2.0",
        max_response_bytes=64,
        max_backoff_seconds=max_backoff_seconds,
    )


async def test_physical_attempt_observer_limits_and_settles_actual_response() -> None:
    observer = RecordingAttemptObserver()
    transport = RecordingTransport(
        [HttpResponse(status_code=200, headers={}, content=b"result", peer_ip="8.8.8.8")]
    )
    client = ResilientHttpClient(
        _policy(),
        resolver=SequenceResolver({"source.example.test": [("8.8.8.8",)]}),
        transport=transport,
        clock=FakeClock(),
        attempt_observer=observer,
    )

    result = await client.get("https://source.example.test/a", checkpoint=SourceCheckpoint())

    assert result.content == b"result"
    assert transport.calls[0][3] == 7
    assert observer.settlements == [(6, False, None)]


async def test_physical_attempt_observer_records_peer_integrity_failure() -> None:
    observer = RecordingAttemptObserver()
    transport = RecordingTransport(
        [HttpResponse(status_code=200, headers={}, content=b"bad", peer_ip="9.9.9.9")]
    )
    client = ResilientHttpClient(
        _policy(),
        resolver=SequenceResolver({"source.example.test": [("8.8.8.8",)]}),
        transport=transport,
        clock=FakeClock(),
        attempt_observer=observer,
    )

    with pytest.raises(SsrfRejected):
        await client.get("https://source.example.test/a", checkpoint=SourceCheckpoint())

    assert observer.settlements == [(0, True, "SSRFREJECTED")]


@pytest.mark.parametrize(
    ("url", "hostname", "addresses"),
    [
        ("https://source.example.test/a", "source.example.test", ("8.8.8.8", "127.0.0.1")),
        ("https://source.example.test/a", "source.example.test", ("0.0.0.0",)),  # noqa: S104
        ("https://source.example.test/a", "source.example.test", ("224.0.0.1",)),
        ("https://source.example.test/a", "source.example.test", ("168.63.129.16",)),
        ("https://source.example.test/a", "source.example.test", ("::ffff:8.8.8.8",)),
        ("https://source.example.test/a", "source.example.test", ("2002:0808:0808::1",)),
    ],
)
async def test_all_dns_answers_must_be_direct_public_non_metadata_addresses(
    url: str,
    hostname: str,
    addresses: tuple[str, ...],
) -> None:
    transport = RecordingTransport([])
    client = ResilientHttpClient(
        _policy(),
        resolver=SequenceResolver({hostname: [addresses]}),
        transport=transport,
        clock=FakeClock(),
    )

    with pytest.raises(SsrfRejected):
        await client.get(url, checkpoint=SourceCheckpoint())

    assert transport.calls == []


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "gopher://source.example.test/_stats",
        "data:text/plain,secret",
        "javascript:alert(1)",
        "https://source.example.test:80/a",
        "http://source.example.test:443/a",
        "https://source.example.test:22/a",
        "https://user:pass@source.example.test/a",
        "https://source.example.test/a#client-fragment",
    ],
)
async def test_dangerous_schemes_ports_and_url_credentials_fail_before_io(url: str) -> None:
    transport = RecordingTransport([])
    client = ResilientHttpClient(
        _policy(),
        resolver=SequenceResolver({"source.example.test": [("8.8.8.8",)]}),
        transport=transport,
        clock=FakeClock(),
    )

    with pytest.raises(SsrfRejected):
        await client.get(url, checkpoint=SourceCheckpoint())

    assert transport.calls == []


async def test_dns_rebinding_between_retries_is_rejected_before_second_transport_call() -> None:
    transport = RecordingTransport([HttpResponse(status_code=503, headers={}, peer_ip="8.8.8.8")])
    resolver = SequenceResolver({"source.example.test": [("8.8.8.8",), ("1.1.1.1",)]})
    client = ResilientHttpClient(
        _policy(),
        resolver=resolver,
        transport=transport,
        clock=FakeClock(),
    )

    with pytest.raises(SsrfRejected, match="rebinding"):
        await client.get(
            "https://source.example.test/a",
            checkpoint=SourceCheckpoint(),
        )

    assert len(transport.calls) == 1
    assert resolver.calls == ["source.example.test", "source.example.test"]


async def test_every_redirect_is_re_resolved_and_https_downgrade_is_denied() -> None:
    transport = RecordingTransport(
        [
            HttpResponse(
                status_code=302,
                headers={"Location": "http://cdn.example.test/document"},
                peer_ip="8.8.8.8",
            )
        ]
    )
    resolver = SequenceResolver(
        {
            "source.example.test": [("8.8.8.8",)],
            "cdn.example.test": [("1.1.1.1",)],
        }
    )
    client = ResilientHttpClient(
        _policy(allowed_hosts=("source.example.test", "cdn.example.test")),
        resolver=resolver,
        transport=transport,
        clock=FakeClock(),
    )

    with pytest.raises(SsrfRejected, match="downgrade"):
        await client.get(
            "https://source.example.test/a",
            checkpoint=SourceCheckpoint(),
        )

    assert len(transport.calls) == 1
    assert resolver.calls == ["source.example.test"]


async def test_credential_headers_cannot_follow_a_cross_origin_redirect() -> None:
    transport = RecordingTransport(
        [
            HttpResponse(
                status_code=302,
                headers={"Location": "https://cdn.example.test/document"},
                peer_ip="8.8.8.8",
            )
        ]
    )
    resolver = SequenceResolver(
        {
            "source.example.test": [("8.8.8.8",)],
            "cdn.example.test": [("1.1.1.1",)],
        }
    )
    client = ResilientHttpClient(
        _policy(allowed_hosts=("source.example.test", "cdn.example.test")),
        resolver=resolver,
        transport=transport,
        clock=FakeClock(),
    )

    with pytest.raises(SsrfRejected, match="credentialed cross-origin"):
        await client.get(
            "https://source.example.test/a",
            checkpoint=SourceCheckpoint(),
            credential_headers={"Authorization": "Bearer private"},
        )

    assert len(transport.calls) == 1
    assert resolver.calls == ["source.example.test"]


@pytest.mark.parametrize(
    "target_url",
    [
        "https://source.example.test/document?token=private",
        "https://source.example.test/document?X-Amz-Signature=private",
        "https://source.example.test/document?X-Goog-Credential=private",
        "https://source.example.test/document?%2574oken=double-encoded-private",
        "https://source.example.test/document?auth=private",
        "https://source.example.test/document?page=1",
    ],
)
async def test_sensitive_query_targets_are_rejected_before_the_target_is_requested(
    target_url: str,
) -> None:
    transport = RecordingTransport(
        [
            HttpResponse(
                status_code=302,
                headers={"Location": target_url},
                peer_ip="8.8.8.8",
            )
        ]
    )
    resolver = SequenceResolver({"source.example.test": [("8.8.8.8",)]})
    client = ResilientHttpClient(
        _policy(),
        resolver=resolver,
        transport=transport,
        clock=FakeClock(),
    )

    with pytest.raises(SsrfRejected, match="query targets"):
        await client.get(
            "https://source.example.test/a",
            checkpoint=SourceCheckpoint(),
        )

    assert len(transport.calls) == 1


async def test_sensitive_query_on_initial_url_fails_without_network_io() -> None:
    transport = RecordingTransport([])
    client = ResilientHttpClient(
        _policy(),
        resolver=SequenceResolver({"source.example.test": [("8.8.8.8",)]}),
        transport=transport,
        clock=FakeClock(),
    )

    with pytest.raises(SsrfRejected, match="query targets"):
        await client.get(
            "https://source.example.test/a?api_key=private",
            checkpoint=SourceCheckpoint(),
        )

    assert transport.calls == []


@pytest.mark.parametrize(
    "user_agent",
    ["ok\r\nX-Evil: yes", "bad\x00agent", "a" * 301],
)
def test_fetch_policy_rejects_unsafe_user_agent(user_agent: str) -> None:
    with pytest.raises(ValueError, match="user-agent"):
        FetchPolicy(
            allowed_hosts=("source.example.test",),
            timeout_seconds=3.5,
            max_attempts=2,
            base_backoff_seconds=0.25,
            rate_limit_per_minute=30,
            minimum_interval_seconds=1,
            circuit_failure_threshold=3,
            circuit_reset_seconds=60,
            max_redirects=2,
            user_agent=user_agent,
        )


async def test_policy_minimum_interval_dominates_per_minute_rate() -> None:
    transport = RecordingTransport(
        [
            HttpResponse(status_code=200, headers={}, content=b"one", peer_ip="8.8.8.8"),
            HttpResponse(status_code=200, headers={}, content=b"two", peer_ip="8.8.8.8"),
        ]
    )
    clock = FakeClock()
    policy = FetchPolicy(
        allowed_hosts=("source.example.test",),
        timeout_seconds=3.5,
        max_attempts=1,
        base_backoff_seconds=0,
        rate_limit_per_minute=4,
        minimum_interval_seconds=900,
        circuit_failure_threshold=3,
        circuit_reset_seconds=60,
        max_redirects=0,
        user_agent="SRBG-Connector/2.0",
    )
    client = ResilientHttpClient(
        policy,
        resolver=SequenceResolver({"source.example.test": [("8.8.8.8",)]}),
        transport=transport,
        clock=clock,
    )

    await client.get("https://source.example.test/one", checkpoint=SourceCheckpoint())
    await client.get("https://source.example.test/two", checkpoint=SourceCheckpoint())

    assert clock.sleeps == [900]


async def test_concurrent_requests_are_serialized_by_source_host_rate_limit() -> None:
    clock = CoordinatedClock()
    transport = TimestampTransport(clock)
    client = ResilientHttpClient(
        _policy(),
        resolver=SequenceResolver({"source.example.test": [("8.8.8.8",)]}),
        transport=transport,
        clock=clock,
    )

    await asyncio.gather(
        *(
            client.get(
                f"https://source.example.test/{index}",
                checkpoint=SourceCheckpoint(),
            )
            for index in range(3)
        )
    )

    assert transport.request_times == [10.0, 12.0, 14.0]


async def test_excessive_dns_answer_count_is_rejected_before_transport() -> None:
    transport = RecordingTransport([])
    client = ResilientHttpClient(
        _policy(),
        resolver=SequenceResolver({"source.example.test": [("8.8.8.8",) * 17]}),
        transport=transport,
        clock=FakeClock(),
    )

    with pytest.raises(SsrfRejected, match="too many"):
        await client.get(
            "https://source.example.test/a",
            checkpoint=SourceCheckpoint(),
        )

    assert transport.calls == []


async def test_connected_peer_must_match_the_current_hop_dns_set() -> None:
    transport = RecordingTransport(
        [HttpResponse(status_code=200, headers={}, content=b"ok", peer_ip="1.1.1.1")]
    )
    client = ResilientHttpClient(
        _policy(),
        resolver=SequenceResolver({"source.example.test": [("8.8.8.8",)]}),
        transport=transport,
        clock=FakeClock(),
    )

    with pytest.raises(SsrfRejected, match="peer"):
        await client.get(
            "https://source.example.test/a",
            checkpoint=SourceCheckpoint(),
        )


async def test_validated_dns_set_is_given_to_transport_before_network_io() -> None:
    transport = RecordingTransport(
        [HttpResponse(status_code=200, headers={}, content=b"ok", peer_ip="8.8.8.8")]
    )
    resolver = SequenceResolver({"source.example.test": [("8.8.8.8",)]})
    client = ResilientHttpClient(
        _policy(),
        resolver=resolver,
        transport=transport,
        clock=FakeClock(),
    )

    await client.get(
        "https://source.example.test/a",
        checkpoint=SourceCheckpoint(),
    )

    assert transport.calls[0][4] == frozenset({"8.8.8.8"})
    assert resolver.timeouts == [3.5]


class RecordingNetworkBackend:
    def __init__(self) -> None:
        self.hosts: list[str] = []

    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,  # noqa: ASYNC109 - fake httpcore backend protocol
        local_address: str | None = None,
        socket_options: object = None,
    ) -> object:
        del port, timeout, local_address, socket_options
        self.hosts.append(host)
        return object()

    async def connect_unix_socket(self, *args: object, **kwargs: object) -> object:
        del args, kwargs
        raise AssertionError("Unix sockets are forbidden for source acquisition")

    async def sleep(self, seconds: float) -> None:
        del seconds


async def test_pinned_network_backend_connects_to_validated_ip_not_hostname() -> None:
    delegate = RecordingNetworkBackend()
    backend = _PinnedNetworkBackend(
        expected_hostname="source.example.test",
        validated_ips=frozenset({"8.8.8.8"}),
        delegate=delegate,
    )

    await backend.connect_tcp("source.example.test", 443)

    assert delegate.hosts == ["8.8.8.8"]


async def test_missing_connected_peer_is_rejected_even_for_an_injected_transport() -> None:
    transport = RecordingTransport(
        [HttpResponse(status_code=200, headers={}, content=b"ok", peer_ip=None)]
    )
    client = ResilientHttpClient(
        _policy(),
        resolver=SequenceResolver({"source.example.test": [("8.8.8.8",)]}),
        transport=transport,
        clock=FakeClock(),
    )

    with pytest.raises(SsrfRejected, match="peer"):
        await client.get(
            "https://source.example.test/a",
            checkpoint=SourceCheckpoint(),
        )


async def test_timeout_size_limit_user_agent_backoff_and_rate_limit_are_transport_authority() -> (
    None
):
    transport = RecordingTransport(
        [
            HttpResponse(status_code=503, headers={}, peer_ip="8.8.8.8"),
            HttpResponse(
                status_code=200,
                headers={"Content-Type": "text/plain"},
                content=b"ok",
                peer_ip="8.8.8.8",
            ),
        ]
    )
    clock = FakeClock()
    client = ResilientHttpClient(
        _policy(),
        resolver=SequenceResolver({"source.example.test": [("8.8.8.8",)]}),
        transport=transport,
        clock=clock,
    )

    result = await client.get(
        "https://source.example.test/a",
        checkpoint=SourceCheckpoint(),
    )

    assert result.content == b"ok"
    assert len(transport.calls) == 2
    assert all(call[2] == 3.5 for call in transport.calls)
    assert all(call[3] == 64 for call in transport.calls)
    assert all(call[1]["User-Agent"] == "SRBG-Connector/2.0" for call in transport.calls)
    assert clock.sleeps == [0.25, 1.75]


async def test_before_request_counts_every_physical_retry_and_redirect_hop() -> None:
    transport = RecordingTransport(
        [
            HttpResponse(
                status_code=302,
                headers={"Location": "https://source.example.test/detail"},
                peer_ip="8.8.8.8",
            ),
            HttpResponse(status_code=503, headers={}, peer_ip="8.8.8.8"),
            HttpResponse(
                status_code=302,
                headers={"Location": "https://source.example.test/detail"},
                peer_ip="8.8.8.8",
            ),
            HttpResponse(status_code=200, headers={}, content=b"ok", peer_ip="8.8.8.8"),
        ]
    )
    physical_requests: list[str] = []
    physical_responses: list[tuple[str, int]] = []

    async def before_request(url: str) -> None:
        physical_requests.append(url)

    async def after_response(url: str, response_bytes: int) -> None:
        physical_responses.append((url, response_bytes))

    client = ResilientHttpClient(
        _policy(),
        resolver=SequenceResolver({"source.example.test": [("8.8.8.8",)]}),
        transport=transport,
        clock=FakeClock(),
        before_request=before_request,
        after_response=after_response,
    )

    result = await client.get(
        "https://source.example.test/list",
        checkpoint=SourceCheckpoint(),
    )

    assert result.content == b"ok"
    assert physical_requests == [
        "https://source.example.test/list",
        "https://source.example.test/detail",
        "https://source.example.test/list",
        "https://source.example.test/detail",
    ]
    assert physical_responses == [
        ("https://source.example.test/list", 0),
        ("https://source.example.test/detail", 0),
        ("https://source.example.test/list", 0),
        ("https://source.example.test/detail", 2),
    ]
    assert len(transport.calls) == 4


async def test_before_request_budget_rejection_happens_before_next_transport_call() -> None:
    class BudgetExhausted(RuntimeError):
        pass

    transport = RecordingTransport([HttpResponse(status_code=503, headers={}, peer_ip="8.8.8.8")])
    reservations: list[str] = []

    async def before_request(url: str) -> None:
        reservations.append(url)
        if len(reservations) > 1:
            raise BudgetExhausted

    client = ResilientHttpClient(
        _policy(),
        resolver=SequenceResolver({"source.example.test": [("8.8.8.8",)]}),
        transport=transport,
        clock=FakeClock(),
        before_request=before_request,
    )

    with pytest.raises(BudgetExhausted):
        await client.get(
            "https://source.example.test/list",
            checkpoint=SourceCheckpoint(),
        )

    assert len(reservations) == 2
    assert len(transport.calls) == 1


async def test_retry_after_cannot_override_the_server_owned_backoff_ceiling() -> None:
    transport = RecordingTransport(
        [
            HttpResponse(
                status_code=429,
                headers={"Retry-After": "999999999"},
                peer_ip="8.8.8.8",
            ),
            HttpResponse(status_code=200, headers={}, content=b"ok", peer_ip="8.8.8.8"),
        ]
    )
    clock = FakeClock()
    client = ResilientHttpClient(
        _policy(max_backoff_seconds=1.0),
        resolver=SequenceResolver({"source.example.test": [("8.8.8.8",)]}),
        transport=transport,
        clock=clock,
    )

    result = await client.get(
        "https://source.example.test/a",
        checkpoint=SourceCheckpoint(),
    )

    assert result.content == b"ok"
    assert clock.sleeps == [1.0, 1.0]


class GuardedChunks:
    def __init__(self, chunks: tuple[bytes, ...]) -> None:
        self._chunks = chunks
        self.iterated = False

    def __aiter__(self) -> AsyncIterator[bytes]:
        self.iterated = True
        return self._iterate()

    async def _iterate(self) -> AsyncIterator[bytes]:
        for chunk in self._chunks:
            yield chunk


async def test_declared_length_is_rejected_before_stream_consumption() -> None:
    chunks = GuardedChunks((b"small",))

    with pytest.raises(ResponseTooLarge):
        await read_bounded_body(chunks, content_length="65", max_response_bytes=64)

    assert chunks.iterated is False


async def test_chunked_response_is_stopped_as_soon_as_decoded_budget_is_exceeded() -> None:
    chunks = GuardedChunks((b"a" * 32, b"b" * 33, b"never-consumed"))

    with pytest.raises(ResponseTooLarge):
        await read_bounded_body(chunks, content_length=None, max_response_bytes=64)


async def test_secret_headers_are_injected_without_entering_result_or_error_text() -> None:
    credential_value = "Bearer must-not-be-persisted"
    transport = RecordingTransport(
        [HttpResponse(status_code=200, headers={}, content=b"ok", peer_ip="8.8.8.8")]
    )
    client = ResilientHttpClient(
        _policy(),
        resolver=SequenceResolver({"source.example.test": [("8.8.8.8",)]}),
        transport=transport,
        clock=FakeClock(),
    )

    result = await client.get(
        "https://source.example.test/a",
        checkpoint=SourceCheckpoint(),
        credential_headers={"Authorization": credential_value},
    )

    assert transport.calls[0][1]["Authorization"] == credential_value
    assert credential_value not in repr(result)
