import logging
from datetime import UTC, datetime
from typing import cast

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine
from srbg_api.acquisition.http import HttpResponse
from srbg_api.source_automation.search import (
    BAIDU_SEARCH_API_URL,
    BaiduSearchProvider,
    BudgetReservation,
    InMemoryMonthlyBudgetLedger,
    PinnedBaiduJsonTransport,
    PostgresMonthlyBudgetLedger,
    SearchBudgetExceeded,
    SearchProviderError,
    SearchQuery,
)


class StubTransport:
    def __init__(self) -> None:
        self.requests: list[tuple[str, dict[str, object], float]] = []

    async def post_json(
        self,
        url: str,
        *,
        payload: dict[str, object],
        headers: dict[str, str],
        timeout: float,  # noqa: ASYNC109 - protocol requires an explicit timeout
    ) -> dict[str, object]:
        assert headers["Authorization"] == "Bearer secret-token"
        self.requests.append((url, payload, timeout))
        return {
            "results": [
                {
                    "title": "四川交通安全通报",
                    "url": "https://jtt.sc.gov.cn/notice/1.html",
                    "snippet": "事故通报",
                    "published_at": "2026-07-16T00:00:00+08:00",
                }
            ]
        }


@pytest.mark.asyncio
async def test_baidu_provider_enforces_top_k_and_accounts_before_call_without_persisting_response(
) -> None:
    ledger = InMemoryMonthlyBudgetLedger(
        monthly_cap_micrormb=200_000_000,
        free_calls_per_month=1_500,
        alert_threshold_bps=8_000,
    )
    transport = StubTransport()
    provider = BaiduSearchProvider(
        api_url="https://qianfan.baidubce.com/v2/ai_search",
        api_key="secret-token",
        transport=transport,
        budget_ledger=ledger,
        cost_per_call_micrormb=36_000,
        timeout_seconds=2.0,
    )

    result = await provider.search(
        SearchQuery(
            query="四川 公路 工程 安全 通报",
            site="sc.gov.cn",
            top_k=50,
            published_after=datetime(2026, 7, 1, tzinfo=UTC),
        ),
        now=datetime(2026, 7, 17, tzinfo=UTC),
    )

    assert result.items[0].url == "https://jtt.sc.gov.cn/notice/1.html"
    assert not hasattr(result.items[0], "title")
    assert not hasattr(result.items[0], "snippet")
    assert result.transient_response is True
    assert ledger.request_count("2026-07") == 1
    assert ledger.spent_micrormb("2026-07") == 0
    assert transport.requests[0][1]["top_k"] == 50

    with pytest.raises(ValueError, match="top_k"):
        SearchQuery(query="engineering", top_k=51)


@pytest.mark.asyncio
async def test_baidu_provider_skips_dirty_individual_results_without_losing_valid_urls() -> None:
    class MixedTransport(StubTransport):
        async def post_json(
            self,
            url: str,
            *,
            payload: dict[str, object],
            headers: dict[str, str],
            timeout: float,  # noqa: ASYNC109 - protocol requires explicit timeout
        ) -> dict[str, object]:
            del url, payload, headers, timeout
            return {
                "results": [
                    "malformed",
                    {"url": "javascript:alert(1)"},
                    {"url": "https://jtt.sc.gov.cn/valid-without-provider-title"},
                    {
                        "title": "ignored provider title",
                        "url": "https://jtyst.shaanxi.gov.cn/valid-two",
                    },
                ]
            }

    provider = BaiduSearchProvider(
        api_url=BAIDU_SEARCH_API_URL,
        api_key="secret-token",
        transport=MixedTransport(),
        budget_ledger=InMemoryMonthlyBudgetLedger(
            monthly_cap_micrormb=200_000_000,
            free_calls_per_month=1_500,
            alert_threshold_bps=8_000,
        ),
        cost_per_call_micrormb=36_000,
        timeout_seconds=2.0,
    )

    result = await provider.search(
        SearchQuery(query="工程安全"),
        now=datetime(2026, 7, 17, tzinfo=UTC),
    )

    assert [item.url for item in result.items] == [
        "https://jtt.sc.gov.cn/valid-without-provider-title",
        "https://jtyst.shaanxi.gov.cn/valid-two",
    ]


@pytest.mark.asyncio
async def test_paid_search_stops_at_the_monthly_hard_cap() -> None:
    ledger = InMemoryMonthlyBudgetLedger(
        monthly_cap_micrormb=35_999,
        free_calls_per_month=0,
        alert_threshold_bps=8_000,
    )
    transport = StubTransport()
    provider = BaiduSearchProvider(
        api_url="https://qianfan.baidubce.com/v2/ai_search",
        api_key="secret-token",
        transport=transport,
        budget_ledger=ledger,
        cost_per_call_micrormb=36_000,
        timeout_seconds=2.0,
    )

    with pytest.raises(SearchBudgetExceeded):
        await provider.search(
            SearchQuery(query="工程 数字化"),
            now=datetime(2026, 7, 17, tzinfo=UTC),
        )

    assert ledger.spent_micrormb("2026-07") == 0
    assert transport.requests == []


@pytest.mark.asyncio
async def test_budget_alert_is_returned_once_without_weakening_the_hard_cap() -> None:
    ledger = InMemoryMonthlyBudgetLedger(
        monthly_cap_micrormb=100_000,
        free_calls_per_month=0,
        alert_threshold_bps=8_000,
    )

    first = await ledger.reserve("2026-07", 80_000)
    second = await ledger.reserve("2026-07", 20_000)

    assert first == BudgetReservation(
        request_count=1,
        cost_micrormb=80_000,
        alert_required=True,
    )
    assert second == BudgetReservation(
        request_count=2,
        cost_micrormb=100_000,
        alert_required=False,
    )
    with pytest.raises(SearchBudgetExceeded):
        await ledger.reserve("2026-07", 1)


@pytest.mark.asyncio
async def test_budget_threshold_is_emitted_before_a_failing_provider_call(
    caplog: pytest.LogCaptureFixture,
) -> None:
    class AlertLedger:
        async def reserve(self, month: str, amount_micrormb: int) -> BudgetReservation:
            assert (month, amount_micrormb) == ("2026-07", 36_000)
            return BudgetReservation(1_501, 160_000_000, True)

    class FailingTransport:
        async def post_json(
            self,
            url: str,
            *,
            payload: dict[str, object],
            headers: dict[str, str],
            timeout: float,  # noqa: ASYNC109 - protocol requires explicit timeout
        ) -> dict[str, object]:
            del url, payload, headers, timeout
            raise SearchProviderError("provider unavailable")

    provider = BaiduSearchProvider(
        api_url=BAIDU_SEARCH_API_URL,
        api_key="secret-token",
        transport=FailingTransport(),
        budget_ledger=AlertLedger(),
        cost_per_call_micrormb=36_000,
        timeout_seconds=2.0,
    )

    with caplog.at_level(logging.WARNING, logger="srbg.source_automation.search"):
        with pytest.raises(SearchProviderError):
            await provider.search(
                SearchQuery(query="工程安全"),
                now=datetime(2026, 7, 17, tzinfo=UTC),
            )

    assert [record.message for record in caplog.records] == [
        "baidu_search_monthly_budget_threshold_reached"
    ]


@pytest.mark.asyncio
async def test_first_1500_calls_are_free_and_the_1501st_costs_point_zero_three_six_rmb(
) -> None:
    ledger = InMemoryMonthlyBudgetLedger(
        monthly_cap_micrormb=200_000_000,
        free_calls_per_month=1_500,
        alert_threshold_bps=8_000,
    )

    for _ in range(1_500):
        reservation = await ledger.reserve("2026-07", 36_000)
    assert reservation.request_count == 1_500
    assert reservation.cost_micrormb == 0

    charged = await ledger.reserve("2026-07", 36_000)

    assert charged.request_count == 1_501
    assert charged.cost_micrormb == 36_000


class _Result:
    def __init__(self, row: dict[str, object] | None = None) -> None:
        self._row = row

    def mappings(self) -> "_Result":
        return self

    def one_or_none(self) -> dict[str, object] | None:
        return self._row


class _Connection:
    def __init__(self) -> None:
        self.statements: list[str] = []
        self.parameters: list[dict[str, object]] = []

    async def execute(
        self,
        statement: object,
        parameters: dict[str, object],
    ) -> _Result:
        self.statements.append(str(statement))
        self.parameters.append(parameters)
        return _Result(
            {
                "request_count": 1,
                "cost_micrormb": 0,
                "alert_required": False,
            }
        )


class _Context:
    def __init__(self, connection: _Connection) -> None:
        self._connection = connection

    async def __aenter__(self) -> _Connection:
        return self._connection

    async def __aexit__(self, *args: object) -> None:
        del args


class _Engine:
    def __init__(self, connection: _Connection) -> None:
        self._connection = connection

    def begin(self) -> _Context:
        return _Context(self._connection)


@pytest.mark.asyncio
async def test_postgres_budget_ledger_reserves_atomically_before_provider_io() -> None:
    connection = _Connection()
    ledger = PostgresMonthlyBudgetLedger(
        cast(AsyncEngine, _Engine(connection)),
        provider="BAIDU_SEARCH",
        monthly_cap_micrormb=200_000_000,
        free_calls_per_month=1_500,
        alert_threshold_bps=8_000,
        now=lambda: datetime(2026, 7, 17, tzinfo=UTC),
    )

    reservation = await ledger.reserve("2026-07", 36_000)

    assert reservation == BudgetReservation(1, 0, False)
    assert connection.statements == [
        "\nSELECT request_count,cost_micrormb,alert_required\n"
        "  FROM reserve_source_provider_usage(:provider,:month,:now)\n"
    ]
    assert connection.parameters[0] == {
        "provider": "BAIDU_SEARCH",
        "month": "2026-07",
        "now": datetime(2026, 7, 17, tzinfo=UTC),
    }


def test_baidu_provider_rejects_every_endpoint_except_the_pinned_api() -> None:
    with pytest.raises(ValueError, match="pinned"):
        BaiduSearchProvider(
            api_url="https://qianfan.baidubce.com/v2/ai_search/other",
            api_key="secret-token",
            transport=StubTransport(),
            budget_ledger=InMemoryMonthlyBudgetLedger(
                monthly_cap_micrormb=200_000_000,
            ),
            cost_per_call_micrormb=36_000,
            timeout_seconds=2.0,
        )


class _Resolver:
    def __init__(self) -> None:
        self.calls: list[tuple[str, float]] = []

    async def resolve(self, hostname: str, *, timeout_seconds: float) -> tuple[str, ...]:
        self.calls.append((hostname, timeout_seconds))
        return ("93.184.216.34",)


class _Sender:
    def __init__(self, response: HttpResponse) -> None:
        self.response = response
        self.calls: list[tuple[str, dict[str, object], float, int, frozenset[str]]] = []

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
        assert headers["Authorization"] == "Bearer secret-token"
        self.calls.append(
            (url, payload, timeout_seconds, max_response_bytes, validated_ips)
        )
        return self.response


@pytest.mark.asyncio
async def test_live_json_transport_pins_dns_peer_disables_alternate_urls_and_bounds_response(
) -> None:
    resolver = _Resolver()
    sender = _Sender(
        HttpResponse(
            status_code=200,
            headers={"content-type": "application/json"},
            content=b'{"results": []}',
            peer_ip="93.184.216.34",
        )
    )
    transport = PinnedBaiduJsonTransport(resolver=resolver, sender=sender)

    response = await transport.post_json(
        BAIDU_SEARCH_API_URL,
        payload={"query": "fixed code-owned query", "top_k": 50},
        headers={"Authorization": "Bearer secret-token"},
        timeout=2.0,
    )

    assert response == {"results": []}
    assert resolver.calls == [("qianfan.baidubce.com", 2.0)]
    assert sender.calls[0][0] == BAIDU_SEARCH_API_URL
    assert sender.calls[0][2] == 2.0
    assert sender.calls[0][3] == 2 * 1024 * 1024
    assert sender.calls[0][4] == frozenset({"93.184.216.34"})

    with pytest.raises(SearchProviderError, match="pinned"):
        await transport.post_json(
            "https://example.com/v2/ai_search",
            payload={"query": "must not leave fixed endpoint", "top_k": 50},
            headers={"Authorization": "Bearer secret-token"},
            timeout=2.0,
        )
    assert len(resolver.calls) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("response", "match"),
    [
        (
            HttpResponse(
                status_code=302,
                headers={"location": "https://example.com/"},
                content=b"{}",
                peer_ip="93.184.216.34",
            ),
            "status",
        ),
        (
            HttpResponse(
                status_code=200,
                headers={},
                content=b"{}",
                peer_ip="1.1.1.1",
            ),
            "peer",
        ),
        (
            HttpResponse(
                status_code=200,
                headers={},
                content=b"x" * (2 * 1024 * 1024 + 1),
                peer_ip="93.184.216.34",
            ),
            "size",
        ),
    ],
)
async def test_live_json_transport_fails_closed_on_redirect_peer_or_size(
    response: HttpResponse,
    match: str,
) -> None:
    transport = PinnedBaiduJsonTransport(resolver=_Resolver(), sender=_Sender(response))

    with pytest.raises(SearchProviderError, match=match):
        await transport.post_json(
            BAIDU_SEARCH_API_URL,
            payload={"query": "fixed code-owned query", "top_k": 50},
            headers={"Authorization": "Bearer secret-token"},
            timeout=2.0,
        )
