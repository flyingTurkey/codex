"""Fail-closed HTTP acquisition with conditional requests and SSRF protection."""

import ipaddress
from dataclasses import dataclass
from datetime import datetime
from email.utils import parsedate_to_datetime
from typing import Protocol
from urllib.parse import urljoin, urlsplit

from srbg_api.acquisition.contracts import FetchResult, SourceCheckpoint


class SsrfRejected(ValueError):
    pass


class CircuitOpen(RuntimeError):
    pass


class _RetryableResponse(OSError):
    def __init__(self, message: str, *, retry_after_seconds: float | None = None) -> None:
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds


@dataclass(frozen=True, slots=True)
class FetchPolicy:
    allowed_hosts: tuple[str, ...]
    timeout_seconds: float
    max_attempts: int
    base_backoff_seconds: float
    rate_limit_per_minute: int
    circuit_failure_threshold: int
    circuit_reset_seconds: float
    max_redirects: int
    user_agent: str
    max_response_bytes: int = 5 * 1024 * 1024

    def __post_init__(self) -> None:
        if not self.allowed_hosts or self.timeout_seconds <= 0 or self.max_attempts < 1:
            raise ValueError("invalid fail-closed fetch policy")
        if self.rate_limit_per_minute < 1 or self.circuit_failure_threshold < 1:
            raise ValueError("invalid resilience limits")
        if self.max_redirects < 0 or not self.user_agent.strip():
            raise ValueError("invalid redirect or user-agent policy")
        if self.max_response_bytes < 1:
            raise ValueError("invalid response size limit")


@dataclass(frozen=True, slots=True)
class HttpResponse:
    status_code: int
    headers: dict[str, str]
    content: bytes | None = None
    peer_ip: str | None = None


class Resolver(Protocol):
    async def resolve(self, hostname: str) -> tuple[str, ...]: ...


class Transport(Protocol):
    async def request(
        self,
        url: str,
        *,
        headers: dict[str, str],
        timeout_seconds: float,
    ) -> HttpResponse: ...


class Clock(Protocol):
    def monotonic(self) -> float: ...

    async def sleep(self, seconds: float) -> None: ...

    def now(self) -> datetime: ...


class ResilientHttpClient:
    def __init__(
        self,
        policy: FetchPolicy,
        *,
        resolver: Resolver,
        transport: Transport,
        clock: Clock,
    ) -> None:
        self._policy = policy
        self._resolver = resolver
        self._transport = transport
        self._clock = clock
        self._failure_count: dict[str, int] = {}
        self._circuit_open_until: dict[str, float] = {}
        self._last_request_at: dict[str, float] = {}

    async def get(
        self,
        url: str,
        *,
        checkpoint: SourceCheckpoint,
        accept: str = "text/html",
    ) -> FetchResult:
        hostname = _hostname(url)
        open_until = self._circuit_open_until.get(hostname, 0.0)
        if open_until > self._clock.monotonic():
            raise CircuitOpen("source circuit is open")

        headers = {"Accept": accept, "User-Agent": self._policy.user_agent}
        if checkpoint.etag:
            headers["If-None-Match"] = checkpoint.etag
        if checkpoint.last_modified:
            headers["If-Modified-Since"] = checkpoint.last_modified

        last_error: OSError | None = None
        for attempt in range(self._policy.max_attempts):
            try:
                response, final_url = await self._request_with_redirects(url, headers)
                if (
                    response.content is not None
                    and len(response.content) > self._policy.max_response_bytes
                ):
                    raise OSError("upstream response exceeds the configured size limit")
                if response.status_code in {429, 500, 502, 503, 504}:
                    raise _RetryableResponse(
                        f"upstream returned {response.status_code}",
                        retry_after_seconds=_retry_after_seconds(
                            _header(response.headers, "retry-after"), self._clock.now()
                        ),
                    )
                if response.status_code == 304:
                    self._record_success(hostname)
                    return _fetch_result(response, final_url, self._clock.now(), True)
                if not 200 <= response.status_code < 300:
                    raise OSError(f"upstream returned {response.status_code}")
                self._record_success(hostname)
                return _fetch_result(response, final_url, self._clock.now(), False)
            except (CircuitOpen, SsrfRejected):
                raise
            except OSError as exc:
                last_error = exc
                if attempt + 1 < self._policy.max_attempts:
                    backoff = self._policy.base_backoff_seconds * (2**attempt)
                    if isinstance(exc, _RetryableResponse):
                        backoff = max(backoff, exc.retry_after_seconds or 0.0)
                    await self._clock.sleep(backoff)

        self._record_failure(hostname)
        if last_error is None:
            raise OSError("acquisition failed without a transport result")
        raise last_error

    async def _request_with_redirects(
        self, url: str, headers: dict[str, str]
    ) -> tuple[HttpResponse, str]:
        current_url = url
        for redirect_count in range(self._policy.max_redirects + 1):
            resolved_addresses = await self._validate_url(current_url)
            hostname = _hostname(current_url)
            await self._respect_rate_limit(hostname)
            response = await self._transport.request(
                current_url,
                headers=dict(headers),
                timeout_seconds=self._policy.timeout_seconds,
            )
            if response.peer_ip is not None and response.peer_ip not in resolved_addresses:
                raise SsrfRejected("connected peer does not match validated public DNS results")
            if response.status_code not in {301, 302, 303, 307, 308}:
                return response, current_url
            location = _header(response.headers, "location")
            if not location:
                raise OSError("redirect response has no location")
            if redirect_count >= self._policy.max_redirects:
                raise OSError("redirect limit exceeded")
            current_url = urljoin(current_url, location)
        raise OSError("redirect limit exceeded")

    async def _validate_url(self, url: str) -> frozenset[str]:
        parsed = urlsplit(url)
        hostname = parsed.hostname
        if (
            parsed.scheme not in {"http", "https"}
            or hostname is None
            or parsed.username is not None
            or parsed.password is not None
            or len(url) > 2048
        ):
            raise SsrfRejected("invalid acquisition URL")
        if parsed.port not in {None, 80, 443}:
            raise SsrfRejected("non-standard acquisition port is denied")
        normalized_host = hostname.rstrip(".").lower()
        if normalized_host not in {host.rstrip(".").lower() for host in self._policy.allowed_hosts}:
            raise SsrfRejected("redirect or host is outside the source allowlist")
        try:
            addresses = await self._resolver.resolve(normalized_host)
        except (OSError, KeyError) as exc:
            raise SsrfRejected("source hostname could not be resolved safely") from exc
        if not addresses:
            raise SsrfRejected("source hostname has no validated public address")
        for address in addresses:
            try:
                parsed_address = ipaddress.ip_address(address)
            except ValueError as exc:
                raise SsrfRejected("source DNS result is not an IP address") from exc
            if not parsed_address.is_global:
                raise SsrfRejected("source DNS results must contain only public addresses")
        return frozenset(addresses)

    async def _respect_rate_limit(self, hostname: str) -> None:
        minimum_interval = 60.0 / self._policy.rate_limit_per_minute
        previous = self._last_request_at.get(hostname)
        now = self._clock.monotonic()
        if previous is not None and now - previous < minimum_interval:
            await self._clock.sleep(minimum_interval - (now - previous))
        self._last_request_at[hostname] = self._clock.monotonic()

    def _record_success(self, hostname: str) -> None:
        self._failure_count[hostname] = 0
        self._circuit_open_until.pop(hostname, None)

    def _record_failure(self, hostname: str) -> None:
        failures = self._failure_count.get(hostname, 0) + 1
        self._failure_count[hostname] = failures
        if failures >= self._policy.circuit_failure_threshold:
            self._circuit_open_until[hostname] = (
                self._clock.monotonic() + self._policy.circuit_reset_seconds
            )


def _hostname(url: str) -> str:
    hostname = urlsplit(url).hostname
    if hostname is None:
        raise SsrfRejected("acquisition URL has no hostname")
    return hostname.rstrip(".").lower()


def _header(headers: dict[str, str], name: str) -> str | None:
    expected = name.lower()
    return next((value for key, value in headers.items() if key.lower() == expected), None)


def _retry_after_seconds(value: str | None, now: datetime) -> float | None:
    if value is None:
        return None
    try:
        seconds = float(value.strip())
    except ValueError:
        try:
            retry_at = parsedate_to_datetime(value)
            if retry_at.tzinfo is None or now.tzinfo is None:
                return None
            seconds = (retry_at - now).total_seconds()
        except (TypeError, ValueError, OverflowError):
            return None
    return max(0.0, seconds)


def _fetch_result(
    response: HttpResponse,
    url: str,
    fetched_at: datetime,
    not_modified: bool,
) -> FetchResult:
    return FetchResult(
        url=url,
        status_code=response.status_code,
        content=None if not_modified else response.content,
        content_type=_header(response.headers, "content-type"),
        etag=_header(response.headers, "etag"),
        last_modified=_header(response.headers, "last-modified"),
        fetched_at=fetched_at,
        not_modified=not_modified,
    )
