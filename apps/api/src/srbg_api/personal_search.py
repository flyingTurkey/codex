"""Budgeted paid-search boundary for optional personal source discovery.

Provider responses are parsed into a small transient value object and are never retained by
this module. Persisting a candidate is a separate, policy-controlled operation.
"""

from __future__ import annotations

import ipaddress
import json
import logging
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from threading import Lock
from typing import Literal, Protocol, cast
from urllib.parse import urlsplit

import httpx2 as httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from srbg_api.acquisition.http import (
    MAX_VALIDATED_DNS_ADDRESSES,
    HttpResponse,
    Resolver,
    ResponseTooLarge,
    read_bounded_body,
)
from srbg_api.acquisition.live import (
    IndependentDohResolver,
    _peer_ip,
    _PinnedHttpxTransport,
    _PinnedNetworkBackend,
)

BAIDU_SEARCH_API_URL = "https://qianfan.baidubce.com/v2/ai_search"
BAIDU_SEARCH_HOST = "qianfan.baidubce.com"
MAX_PROVIDER_RESPONSE_BYTES = 2 * 1024 * 1024
logger = logging.getLogger("srbg.personal_search")


class SearchBudgetExceeded(RuntimeError):
    """Raised before provider I/O when the monthly hard cap would be exceeded."""


class SearchProviderError(RuntimeError):
    """Raised when a provider returns a response outside the configured contract."""


@dataclass(frozen=True, slots=True)
class SearchQuery:
    query: str
    site: str | None = None
    top_k: int = 10
    published_after: datetime | None = None

    def __post_init__(self) -> None:
        normalized_query = self.query.strip()
        if not normalized_query or len(normalized_query) > 500:
            raise ValueError("query must contain between 1 and 500 characters")
        if self.top_k < 1 or self.top_k > 50:
            raise ValueError("top_k must be between 1 and 50")
        if self.site is not None:
            normalized_site = self.site.rstrip(".").lower()
            if (
                len(normalized_site) > 253
                or re.fullmatch(
                    r"(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}",
                    normalized_site,
                )
                is None
            ):
                raise ValueError("site must be a fixed DNS host name")
            object.__setattr__(self, "site", normalized_site)
        if self.published_after is not None:
            object.__setattr__(
                self,
                "published_after",
                _require_aware_utc(self.published_after, field="published_after"),
            )
        object.__setattr__(self, "query", normalized_query)


@dataclass(frozen=True, slots=True)
class SearchItem:
    url: str
    published_at: datetime | None


@dataclass(frozen=True, slots=True)
class SearchResult:
    items: tuple[SearchItem, ...]
    transient_response: Literal[True] = True
    budget_alert_required: bool = False


class JsonSearchTransport(Protocol):
    async def post_json(
        self,
        url: str,
        *,
        payload: dict[str, object],
        headers: dict[str, str],
        timeout: float,  # noqa: ASYNC109 - transport contract accepts an explicit I/O timeout
    ) -> dict[str, object]: ...


class PinnedJsonSender(Protocol):
    async def send(
        self,
        url: str,
        *,
        payload: dict[str, object],
        headers: dict[str, str],
        timeout_seconds: float,
        max_response_bytes: int,
        validated_ips: frozenset[str],
    ) -> HttpResponse: ...


class PinnedBaiduJsonTransport:
    """Production POST transport fixed to Baidu Qianfan and a validated peer set."""

    def __init__(
        self,
        *,
        resolver: Resolver | None = None,
        sender: PinnedJsonSender | None = None,
    ) -> None:
        self._resolver = resolver or IndependentDohResolver()
        self._sender = sender or _HttpxPinnedJsonSender()

    async def post_json(
        self,
        url: str,
        *,
        payload: dict[str, object],
        headers: dict[str, str],
        timeout: float,  # noqa: ASYNC109 - transport contract requires an explicit deadline
    ) -> dict[str, object]:
        if url != BAIDU_SEARCH_API_URL:
            raise SearchProviderError("paid-search transport refused a non-pinned endpoint")
        if timeout <= 0 or timeout > 30:
            raise SearchProviderError("paid-search transport timeout is invalid")
        addresses = await self._resolver.resolve(
            BAIDU_SEARCH_HOST,
            timeout_seconds=timeout,
        )
        if not addresses or len(addresses) > MAX_VALIDATED_DNS_ADDRESSES:
            raise SearchProviderError("paid-search endpoint has no bounded public DNS result")
        try:
            validated_ips = frozenset(_public_ip(address) for address in addresses)
        except ValueError as error:
            raise SearchProviderError(
                "paid-search endpoint resolved to a non-public address"
            ) from error
        response = await self._sender.send(
            BAIDU_SEARCH_API_URL,
            payload=payload,
            headers=dict(headers),
            timeout_seconds=timeout,
            max_response_bytes=MAX_PROVIDER_RESPONSE_BYTES,
            validated_ips=validated_ips,
        )
        if response.peer_ip is None or _public_ip(response.peer_ip) not in validated_ips:
            raise SearchProviderError("paid-search connected peer did not match pinned DNS")
        # Redirect responses are rejected rather than followed by both this boundary and its sender.
        if not 200 <= response.status_code < 300:
            raise SearchProviderError("paid-search endpoint returned a rejected status")
        content = response.content
        if content is None or len(content) > MAX_PROVIDER_RESPONSE_BYTES:
            raise SearchProviderError("paid-search response size is invalid")
        try:
            decoded = json.loads(content.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise SearchProviderError("paid-search response is not valid JSON") from error
        if not isinstance(decoded, dict):
            raise SearchProviderError("paid-search response must be a JSON object")
        return cast(dict[str, object], decoded)


class _HttpxPinnedJsonSender:
    async def send(
        self,
        url: str,
        *,
        payload: dict[str, object],
        headers: dict[str, str],
        timeout_seconds: float,
        max_response_bytes: int,
        validated_ips: frozenset[str],
    ) -> HttpResponse:
        network_backend = _PinnedNetworkBackend(
            expected_hostname=BAIDU_SEARCH_HOST,
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
                    url,
                    json=payload,
                    headers=headers,
                    timeout=timeout_seconds,
                ) as response:
                    peer_ip = _peer_ip(response.extensions)
                    if peer_ip is None:
                        raise SearchProviderError(
                            "paid-search transport could not verify its connected peer"
                        )
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
        except ResponseTooLarge as error:
            raise SearchProviderError("paid-search response exceeded its size limit") from error
        except httpx.HTTPError as error:
            raise SearchProviderError("paid-search HTTPS request failed") from error


class MonthlyBudgetLedger(Protocol):
    async def reserve(self, month: str, amount_micrormb: int) -> BudgetReservation: ...


@dataclass(frozen=True, slots=True)
class BudgetReservation:
    request_count: int
    cost_micrormb: int
    alert_required: bool


class InMemoryMonthlyBudgetLedger:
    """Thread-safe test/development ledger using integer micro-RMB amounts."""

    def __init__(
        self,
        *,
        monthly_cap_micrormb: int,
        free_calls_per_month: int = 1_500,
        alert_threshold_bps: int = 8_000,
    ) -> None:
        if monthly_cap_micrormb <= 0:
            raise ValueError("monthly budget cap must be positive")
        if free_calls_per_month < 0:
            raise ValueError("monthly free call count cannot be negative")
        if not 1 <= alert_threshold_bps <= 9_999:
            raise ValueError("budget alert threshold must be between 1 and 9999 bps")
        self._monthly_cap_micrormb = monthly_cap_micrormb
        self._free_calls_per_month = free_calls_per_month
        self._alert_threshold_bps = alert_threshold_bps
        self._spend_by_month: dict[str, int] = {}
        self._requests_by_month: dict[str, int] = {}
        self._alerted_months: set[str] = set()
        self._lock = Lock()

    async def reserve(self, month: str, amount_micrormb: int) -> BudgetReservation:
        if re.fullmatch(r"\d{4}-(?:0[1-9]|1[0-2])", month) is None:
            raise ValueError("month must use YYYY-MM format")
        if amount_micrormb < 0:
            raise ValueError("reserved search cost cannot be negative")
        with self._lock:
            spent = self._spend_by_month.get(month, 0)
            requests = self._requests_by_month.get(month, 0)
            charged = 0 if requests < self._free_calls_per_month else amount_micrormb
            if spent + charged > self._monthly_cap_micrormb:
                raise SearchBudgetExceeded("monthly paid-search hard cap would be exceeded")
            next_spent = spent + charged
            next_requests = requests + 1
            alert_required = bool(
                month not in self._alerted_months
                and next_spent * 10_000
                >= self._monthly_cap_micrormb * self._alert_threshold_bps
            )
            self._spend_by_month[month] = next_spent
            self._requests_by_month[month] = next_requests
            if alert_required:
                self._alerted_months.add(month)
            return BudgetReservation(
                request_count=next_requests,
                cost_micrormb=next_spent,
                alert_required=alert_required,
            )

    def spent_micrormb(self, month: str) -> int:
        with self._lock:
            return self._spend_by_month.get(month, 0)

    def request_count(self, month: str) -> int:
        with self._lock:
            return self._requests_by_month.get(month, 0)


class PostgresMonthlyBudgetLedger:
    """PostgreSQL-backed reservation ledger shared by every discovery worker."""

    def __init__(
        self,
        engine: AsyncEngine,
        *,
        provider: str,
        monthly_cap_micrormb: int,
        free_calls_per_month: int,
        alert_threshold_bps: int,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        if re.fullmatch(r"[A-Z0-9_]{1,40}", provider) is None:
            raise ValueError("paid-search provider code is invalid")
        if (
            monthly_cap_micrormb,
            free_calls_per_month,
            alert_threshold_bps,
        ) != (200_000_000, 1_500, 8_000):
            raise ValueError("PostgreSQL paid-search budget policy is database-pinned")
        self._engine = engine
        self._provider = provider
        self._now = now

    async def reserve(self, month: str, amount_micrormb: int) -> BudgetReservation:
        if re.fullmatch(r"\d{4}-(?:0[1-9]|1[0-2])", month) is None:
            raise ValueError("month must use YYYY-MM format")
        if amount_micrormb < 0:
            raise ValueError("reserved search cost cannot be negative")
        if amount_micrormb != 36_000:
            raise ValueError("PostgreSQL paid-search unit cost is database-pinned")
        now = _require_aware_utc(self._now(), field="budget reservation time")
        parameters = {
            "provider": self._provider,
            "month": month,
            "now": now,
        }
        async with self._engine.begin() as connection:
            row = (
                (await connection.execute(text(_RESERVE_USAGE_SQL), parameters))
                .mappings()
                .one_or_none()
            )
        if row is None:
            raise SearchBudgetExceeded("monthly paid-search hard cap would be exceeded")
        request_count = row.get("request_count")
        cost_micrormb = row.get("cost_micrormb")
        alert_required = row.get("alert_required")
        if (
            isinstance(request_count, bool)
            or not isinstance(request_count, int)
            or isinstance(cost_micrormb, bool)
            or not isinstance(cost_micrormb, int)
            or not isinstance(alert_required, bool)
        ):
            raise RuntimeError("paid-search budget reservation returned invalid state")
        return BudgetReservation(request_count, cost_micrormb, alert_required)


class BaiduSearchProvider:
    """Narrow adapter for the configured Baidu AI search endpoint."""

    def __init__(
        self,
        *,
        api_url: str,
        api_key: str,
        transport: JsonSearchTransport,
        budget_ledger: MonthlyBudgetLedger,
        cost_per_call_micrormb: int,
        timeout_seconds: float,
    ) -> None:
        parsed_api_url = urlsplit(api_url)
        if (
            api_url != BAIDU_SEARCH_API_URL
            or parsed_api_url.scheme != "https"
            or parsed_api_url.hostname != BAIDU_SEARCH_HOST
            or parsed_api_url.username is not None
            or parsed_api_url.password is not None
        ):
            raise ValueError("paid-search api_url must use the pinned Baidu Qianfan endpoint")
        if not api_key:
            raise ValueError("paid-search api_key cannot be empty")
        if cost_per_call_micrormb <= 0:
            raise ValueError("paid-search cost must be a positive integer micro-RMB amount")
        if timeout_seconds <= 0 or timeout_seconds > 30:
            raise ValueError("paid-search timeout must be between 0 and 30 seconds")
        self._api_url = api_url
        self._api_key = api_key
        self._transport = transport
        self._budget_ledger = budget_ledger
        self._cost_per_call_micrormb = cost_per_call_micrormb
        self._timeout_seconds = timeout_seconds

    async def search(self, query: SearchQuery, *, now: datetime) -> SearchResult:
        charged_at = _require_aware_utc(now, field="now")
        month = charged_at.strftime("%Y-%m")
        # Reserve first: concurrent callers can never cross the configured hard cap.
        reservation = await self._budget_ledger.reserve(month, self._cost_per_call_micrormb)
        if reservation.alert_required:
            logger.warning(
                "baidu_search_monthly_budget_threshold_reached",
                extra={
                    "provider": "BAIDU_SEARCH",
                    "utc_month": month,
                    "cost_micrormb": reservation.cost_micrormb,
                },
            )

        payload: dict[str, object] = {"query": query.query, "top_k": query.top_k}
        if query.site is not None:
            payload["site"] = query.site
        if query.published_after is not None:
            payload["published_after"] = query.published_after.isoformat()
        response = await self._transport.post_json(
            self._api_url,
            payload=payload,
            headers={"Authorization": f"Bearer {self._api_key}"},
            timeout=self._timeout_seconds,
        )
        return SearchResult(
            items=_parse_items(response, top_k=query.top_k),
            budget_alert_required=reservation.alert_required,
        )


def _parse_items(response: dict[str, object], *, top_k: int) -> tuple[SearchItem, ...]:
    raw_items = response.get("results")
    if not isinstance(raw_items, list):
        raise SearchProviderError("paid-search response must contain a results array")
    items: list[SearchItem] = []
    invalid_count = 0
    for raw_item in raw_items[:top_k]:
        if not isinstance(raw_item, dict):
            invalid_count += 1
            continue
        url = raw_item.get("url")
        if not isinstance(url, str) or not _is_safe_candidate_url(url):
            invalid_count += 1
            continue
        raw_published_at = raw_item.get("published_at")
        published_at: datetime | None = None
        if raw_published_at is not None:
            if not isinstance(raw_published_at, str):
                invalid_count += 1
                continue
            try:
                published_at = _require_aware_utc(
                    datetime.fromisoformat(raw_published_at),
                    field="paid-search published_at",
                )
            except ValueError:
                invalid_count += 1
                continue
        # Provider-authored title/snippet content is deliberately discarded at this boundary.
        items.append(SearchItem(url=url, published_at=published_at))
    if invalid_count:
        logger.warning(
            "baidu_search_invalid_items_skipped",
            extra={"provider": "BAIDU_SEARCH", "invalid_item_count": invalid_count},
        )
    return tuple(items)


def _is_safe_candidate_url(value: str) -> bool:
    parsed = urlsplit(value)
    return bool(
        parsed.scheme == "https"
        and parsed.hostname
        and parsed.username is None
        and parsed.password is None
    )


def _public_ip(value: str) -> str:
    address = ipaddress.ip_address(value)
    if not address.is_global:
        raise ValueError("network address is not globally routable")
    return str(address)


def _require_aware_utc(value: datetime, *, field: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must include a UTC offset")
    return value.astimezone(UTC)


_RESERVE_USAGE_SQL = """
SELECT request_count,cost_micrormb,alert_required
  FROM reserve_source_provider_usage(:provider,:month,:now)
"""
