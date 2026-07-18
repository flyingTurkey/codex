"""Fail-closed HTTP acquisition with conditional requests and SSRF protection."""

import asyncio
import ipaddress
import json
import math
from collections.abc import AsyncIterable, Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from email.utils import parsedate_to_datetime
from hashlib import sha256
from typing import Protocol
from urllib.parse import unquote, urljoin, urlsplit
from uuid import UUID

from srbg_api.acquisition.contracts import FetchResult, SourceCheckpoint


class SsrfRejected(ValueError):
    pass


class CircuitOpen(RuntimeError):
    pass


class ResponseTooLarge(OSError):
    pass


class HttpStatusError(OSError):
    def __init__(
        self,
        status_code: int,
        *,
        retry_after_seconds: float | None = None,
    ) -> None:
        super().__init__(f"upstream returned {status_code}")
        self.status_code = status_code
        self.retry_after_seconds = retry_after_seconds


MAX_VALIDATED_DNS_ADDRESSES = 16


class _RetryableResponse(HttpStatusError):
    pass


@dataclass(frozen=True, slots=True)
class FetchPolicy:
    allowed_hosts: tuple[str, ...]
    timeout_seconds: float
    max_attempts: int
    base_backoff_seconds: float
    rate_limit_per_minute: int
    minimum_interval_seconds: int
    circuit_failure_threshold: int
    circuit_reset_seconds: float
    max_redirects: int
    user_agent: str
    max_response_bytes: int = 5 * 1024 * 1024
    allowed_schemes: tuple[str, ...] = ("https",)
    max_backoff_seconds: float = 60.0

    def __post_init__(self) -> None:
        if (
            not self.allowed_hosts
            or not math.isfinite(self.timeout_seconds)
            or self.timeout_seconds <= 0
            or self.max_attempts < 1
        ):
            raise ValueError("invalid fail-closed fetch policy")
        if (
            self.rate_limit_per_minute < 1
            or self.minimum_interval_seconds < 1
            or self.minimum_interval_seconds > 604800
            or self.circuit_failure_threshold < 1
            or not math.isfinite(self.circuit_reset_seconds)
            or self.circuit_reset_seconds <= 0
        ):
            raise ValueError("invalid resilience limits")
        if (
            not math.isfinite(self.base_backoff_seconds)
            or not math.isfinite(self.max_backoff_seconds)
            or self.base_backoff_seconds < 0
            or self.max_backoff_seconds <= 0
            or (self.max_attempts > 1 and self.base_backoff_seconds > self.max_backoff_seconds)
        ):
            raise ValueError("invalid bounded backoff policy")
        if (
            self.max_redirects < 0
            or not 1 <= len(self.user_agent) <= 300
            or not self.user_agent.strip()
            or any(ord(character) < 32 or ord(character) == 127 for character in self.user_agent)
        ):
            raise ValueError("invalid redirect or user-agent policy")
        if self.max_response_bytes < 1:
            raise ValueError("invalid response size limit")
        if not self.allowed_schemes or not set(self.allowed_schemes).issubset({"http", "https"}):
            raise ValueError("invalid acquisition schemes")


@dataclass(frozen=True, slots=True)
class HttpResponse:
    status_code: int
    headers: dict[str, str]
    content: bytes | None = None
    peer_ip: str | None = None


class Resolver(Protocol):
    async def resolve(
        self,
        hostname: str,
        *,
        timeout_seconds: float,
    ) -> tuple[str, ...]: ...


class Transport(Protocol):
    async def request(
        self,
        url: str,
        *,
        headers: dict[str, str],
        timeout_seconds: float,
        max_response_bytes: int,
        validated_ips: frozenset[str],
    ) -> HttpResponse: ...


class Clock(Protocol):
    def monotonic(self) -> float: ...

    async def sleep(self, seconds: float) -> None: ...

    def now(self) -> datetime: ...


@dataclass(frozen=True, slots=True)
class PhysicalAttemptReservation:
    id: UUID
    max_response_bytes: int


class PhysicalAttemptObserver(Protocol):
    async def reserve(self, url: str, requested_max_bytes: int) -> PhysicalAttemptReservation: ...

    async def settle(
        self,
        reservation: PhysicalAttemptReservation,
        *,
        response_bytes: int,
        failed: bool,
        failure_code: str | None,
    ) -> None: ...


class ResilientHttpClient:
    def __init__(
        self,
        policy: FetchPolicy,
        *,
        resolver: Resolver,
        transport: Transport,
        clock: Clock,
        before_request: Callable[[str], Awaitable[None]] | None = None,
        after_response: Callable[[str, int], Awaitable[None]] | None = None,
        attempt_observer: PhysicalAttemptObserver | None = None,
    ) -> None:
        self._policy = policy
        self._resolver = resolver
        self._transport = transport
        self._clock = clock
        self._before_request = before_request
        self._after_response = after_response
        self._attempt_observer = attempt_observer
        self._failure_count: dict[str, int] = {}
        self._circuit_open_until: dict[str, float] = {}
        self._last_request_at: dict[str, float] = {}
        self._rate_limit_locks: dict[str, asyncio.Lock] = {}

    async def get(
        self,
        url: str,
        *,
        checkpoint: SourceCheckpoint,
        accept: str = "text/html",
        credential_headers: dict[str, str] | None = None,
        allow_not_found: bool = False,
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
        headers.update(_validated_credential_headers(credential_headers))

        last_error: OSError | None = None
        resolution_pins: dict[str, frozenset[str]] = {}
        for attempt in range(self._policy.max_attempts):
            try:
                response, final_url, redirect_chain = await self._request_with_redirects(
                    url,
                    headers,
                    resolution_pins,
                )
                if (
                    response.content is not None
                    and len(response.content) > self._policy.max_response_bytes
                ):
                    raise OSError("upstream response exceeds the configured size limit")
                if response.status_code in {429, 500, 502, 503, 504}:
                    raise _RetryableResponse(
                        response.status_code,
                        retry_after_seconds=_retry_after_seconds(
                            _header(response.headers, "retry-after"), self._clock.now()
                        ),
                    )
                if response.status_code == 304:
                    self._record_success(hostname)
                    return _fetch_result(
                        response,
                        url,
                        final_url,
                        redirect_chain,
                        self._clock.now(),
                        True,
                    )
                if allow_not_found and response.status_code in {404, 410}:
                    self._record_success(hostname)
                    return _fetch_result(
                        response,
                        url,
                        final_url,
                        redirect_chain,
                        self._clock.now(),
                        False,
                    )
                if not 200 <= response.status_code < 300:
                    raise HttpStatusError(response.status_code)
                self._record_success(hostname)
                return _fetch_result(
                    response,
                    url,
                    final_url,
                    redirect_chain,
                    self._clock.now(),
                    False,
                )
            except (CircuitOpen, ResponseTooLarge, SsrfRejected):
                raise
            except OSError as exc:
                last_error = exc
                if attempt + 1 < self._policy.max_attempts:
                    backoff = self._policy.base_backoff_seconds * (2**attempt)
                    if isinstance(exc, _RetryableResponse):
                        backoff = max(backoff, exc.retry_after_seconds or 0.0)
                    await self._clock.sleep(min(backoff, self._policy.max_backoff_seconds))

        self._record_failure(hostname)
        if last_error is None:
            raise OSError("acquisition failed without a transport result")
        raise last_error

    async def _request_with_redirects(
        self,
        url: str,
        headers: dict[str, str],
        resolution_pins: dict[str, frozenset[str]],
    ) -> tuple[HttpResponse, str, tuple[str, ...]]:
        current_url = url
        redirect_chain: list[str] = []
        for redirect_count in range(self._policy.max_redirects + 1):
            resolved_addresses = await self._validate_url(current_url, resolution_pins)
            hostname = _hostname(current_url)
            await self._respect_rate_limit(hostname)
            if self._before_request is not None:
                await self._before_request(current_url)
            reservation = None
            if self._attempt_observer is not None:
                reservation = await self._attempt_observer.reserve(
                    current_url, self._policy.max_response_bytes
                )
            try:
                response = await self._transport.request(
                    current_url,
                    headers=dict(headers),
                    timeout_seconds=self._policy.timeout_seconds,
                    max_response_bytes=(
                        reservation.max_response_bytes
                        if reservation is not None
                        else self._policy.max_response_bytes
                    ),
                    validated_ips=resolved_addresses,
                )
                if response.peer_ip is None:
                    raise SsrfRejected("connected peer address is required")
                peer_ip = _validated_ip(response.peer_ip)
                if peer_ip not in resolved_addresses:
                    raise SsrfRejected("connected peer does not match validated public DNS results")
            except Exception as error:
                if reservation is not None and self._attempt_observer is not None:
                    await self._attempt_observer.settle(
                        reservation,
                        response_bytes=0,
                        failed=True,
                        failure_code=type(error).__name__[:80].upper(),
                    )
                raise
            if reservation is not None and self._attempt_observer is not None:
                failed_status = response.status_code >= 400 and response.status_code not in {
                    404,
                    410,
                }
                await self._attempt_observer.settle(
                    reservation,
                    response_bytes=len(response.content or b""),
                    failed=failed_status,
                    failure_code=(f"HTTP_{response.status_code}" if failed_status else None),
                )
            if self._after_response is not None:
                await self._after_response(current_url, len(response.content or b""))
            if response.status_code not in {301, 302, 303, 307, 308}:
                return response, current_url, tuple(redirect_chain)
            location = _header(response.headers, "location")
            if not location:
                raise OSError("redirect response has no location")
            if redirect_count >= self._policy.max_redirects:
                raise OSError("redirect limit exceeded")
            next_url = urljoin(current_url, location)
            try:
                current_scheme = urlsplit(current_url).scheme.casefold()
                next_scheme = urlsplit(next_url).scheme.casefold()
            except ValueError as error:
                raise SsrfRejected("redirect target is malformed") from error
            if current_scheme == "https" and next_scheme == "http":
                raise SsrfRejected("HTTPS redirect downgrade is denied")
            if _contains_credential_header(headers) and _origin(current_url) != _origin(next_url):
                raise SsrfRejected("credentialed cross-origin redirect is denied")
            redirect_chain.append(next_url)
            current_url = next_url
        raise OSError("redirect limit exceeded")

    async def _validate_url(
        self,
        url: str,
        resolution_pins: dict[str, frozenset[str]],
    ) -> frozenset[str]:
        if any(ord(character) < 32 or ord(character) == 127 for character in unquote(url)):
            raise SsrfRejected("invalid acquisition URL")
        try:
            parsed = urlsplit(url)
            port = parsed.port
        except ValueError as error:
            raise SsrfRejected("invalid acquisition URL") from error
        hostname = parsed.hostname
        if (
            parsed.scheme not in self._policy.allowed_schemes
            or hostname is None
            or parsed.username is not None
            or parsed.password is not None
            or bool(parsed.fragment)
            or len(url) > 2048
        ):
            raise SsrfRejected("invalid acquisition URL")
        if (parsed.scheme == "https" and port not in {None, 443}) or (
            parsed.scheme == "http" and port not in {None, 80}
        ):
            raise SsrfRejected("non-standard acquisition port is denied")
        if "?" in url:
            raise SsrfRejected("query targets are denied by declarative source policy")
        normalized_host = hostname.rstrip(".").lower()
        if normalized_host not in {host.rstrip(".").lower() for host in self._policy.allowed_hosts}:
            raise SsrfRejected("redirect or host is outside the source allowlist")
        try:
            addresses = await self._resolver.resolve(
                normalized_host,
                timeout_seconds=self._policy.timeout_seconds,
            )
        except (OSError, KeyError) as exc:
            raise SsrfRejected("source hostname could not be resolved safely") from exc
        if not addresses:
            raise SsrfRejected("source hostname has no validated public address")
        if len(addresses) > MAX_VALIDATED_DNS_ADDRESSES:
            raise SsrfRejected("source hostname returned too many DNS addresses")
        validated_addresses = frozenset(_validated_ip(address) for address in addresses)
        previous = resolution_pins.get(normalized_host)
        if previous is not None and previous != validated_addresses:
            raise SsrfRejected("DNS rebinding changed the validated address set")
        resolution_pins[normalized_host] = validated_addresses
        return validated_addresses

    async def _respect_rate_limit(self, hostname: str) -> None:
        lock = self._rate_limit_locks.setdefault(hostname, asyncio.Lock())
        async with lock:
            minimum_interval = max(
                float(self._policy.minimum_interval_seconds),
                60.0 / self._policy.rate_limit_per_minute,
            )
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
    try:
        hostname = urlsplit(url).hostname
    except ValueError as error:
        raise SsrfRejected("acquisition URL has an invalid hostname") from error
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
    if not math.isfinite(seconds):
        return None
    return max(0.0, seconds)


def _fetch_result(
    response: HttpResponse,
    request_url: str,
    final_url: str,
    redirect_chain: tuple[str, ...],
    fetched_at: datetime,
    not_modified: bool,
) -> FetchResult:
    content = None if not_modified else response.content
    return FetchResult(
        url=final_url,
        status_code=response.status_code,
        content=content,
        content_type=_header(response.headers, "content-type"),
        etag=_header(response.headers, "etag"),
        last_modified=_header(response.headers, "last-modified"),
        fetched_at=fetched_at,
        not_modified=not_modified,
        request_url=request_url,
        redirect_chain=redirect_chain,
        response_sha256=_response_sha256(response, content or b""),
    )


async def read_bounded_body(
    chunks: AsyncIterable[bytes],
    *,
    content_length: str | None,
    max_response_bytes: int,
) -> bytes:
    """Read decoded response bytes without ever exceeding the configured budget."""

    if max_response_bytes < 1:
        raise ValueError("response byte budget must be positive")
    if content_length is not None:
        try:
            declared_length = int(content_length)
        except ValueError as error:
            raise OSError("upstream Content-Length is invalid") from error
        if declared_length < 0:
            raise OSError("upstream Content-Length is invalid")
        if declared_length > max_response_bytes:
            raise ResponseTooLarge("upstream response exceeds the configured size limit")
    body = bytearray()
    async for chunk in chunks:
        if len(body) + len(chunk) > max_response_bytes:
            raise ResponseTooLarge("upstream response exceeds the configured size limit")
        body.extend(chunk)
    return bytes(body)


_METADATA_ADDRESSES = {
    ipaddress.ip_address("168.63.129.16"),
    ipaddress.ip_address("169.254.169.254"),
    ipaddress.ip_address("169.254.170.2"),
    ipaddress.ip_address("100.100.100.200"),
    ipaddress.ip_address("192.0.0.192"),
}


def _validated_ip(value: str) -> str:
    try:
        address = ipaddress.ip_address(value)
    except ValueError as error:
        raise SsrfRejected("source DNS result is not an IP address") from error
    if (
        not address.is_global
        or address.is_multicast
        or address.is_reserved
        or address in _METADATA_ADDRESSES
        or (isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is not None)
        or (isinstance(address, ipaddress.IPv6Address) and address.sixtofour is not None)
        or (isinstance(address, ipaddress.IPv6Address) and address.teredo is not None)
        or getattr(address, "scope_id", None) is not None
    ):
        raise SsrfRejected("source DNS results must contain only direct public addresses")
    return str(address)


def _validated_credential_headers(value: dict[str, str] | None) -> dict[str, str]:
    if value is None:
        return {}
    allowed = {"authorization", "x-api-key"}
    result: dict[str, str] = {}
    for name, secret in value.items():
        if name.casefold() not in allowed or not secret or len(secret) > 4096:
            raise ValueError("credential header is not allowed")
        if any(character in name + secret for character in ("\r", "\n", "\x00")):
            raise ValueError("credential header is not allowed")
        result[name] = secret
    return result


def _contains_credential_header(headers: dict[str, str]) -> bool:
    return any(name.casefold() in {"authorization", "x-api-key"} for name in headers)


def _origin(url: str) -> tuple[str, str, int]:
    try:
        parsed = urlsplit(url)
        hostname = parsed.hostname
        port = parsed.port
    except ValueError as error:
        raise SsrfRejected("redirect target is malformed") from error
    if hostname is None:
        raise SsrfRejected("redirect target is malformed")
    scheme = parsed.scheme.casefold()
    effective_port = port if port is not None else (443 if scheme == "https" else 80)
    return scheme, hostname.rstrip(".").casefold(), effective_port


def _response_sha256(response: HttpResponse, content: bytes) -> str:
    selected = {
        name: _header(response.headers, name) or ""
        for name in ("content-type", "etag", "last-modified")
    }
    evidence = (
        f"{response.status_code}\n".encode()
        + json.dumps(selected, sort_keys=True, separators=(",", ":")).encode()
        + b"\n"
        + content
    )
    return sha256(evidence).hexdigest()
