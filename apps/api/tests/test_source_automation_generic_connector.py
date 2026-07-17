from datetime import UTC, datetime

import pytest
from srbg_api.acquisition.contracts import FetchResult
from srbg_api.connectors.parsers import (
    MAX_DISCOVERY_RECORDS,
    DeclarativeParseError,
    ListDetailConnector,
)


def _fetched(html: str) -> FetchResult:
    return FetchResult(
        url="https://jtt.sc.gov.cn/",
        status_code=200,
        content=html.encode(),
        content_type="text/html",
        etag=None,
        last_modified=None,
        fetched_at=datetime(2026, 7, 17, tzinfo=UTC),
    )


def _generic_config() -> dict[str, object]:
    return {
        "list_url": "https://jtt.sc.gov.cn/",
        "allowed_hosts": ["jtt.sc.gov.cn"],
        "item_selector": "a",
        "link_selector": "a",
        "title_selector": "a",
    }


def test_generic_automated_list_profile_keeps_only_bounded_internal_links() -> None:
    noisy_links = "".join(
        f'<a href="https://external-{index}.example/a">external {index}</a>'
        for index in range(600)
    )
    html = (
        "<html><body>"
        '<a href="">empty</a>'
        '<a href="javascript:alert(1)">script</a>'
        f"{noisy_links}"
        '<a href="/safety/notice-1.html">桥梁安全生产通报</a>'
        '<a href="/digital/case-2.html">公路数字化转型案例</a>'
        "</body></html>"
    ).encode()
    records = ListDetailConnector().discover(_fetched(html.decode()), _generic_config())

    assert [record.url for record in records] == [
        "https://jtt.sc.gov.cn/safety/notice-1.html",
        "https://jtt.sc.gov.cn/digital/case-2.html",
    ]


def test_generic_profile_ranks_relevant_detail_links_ahead_of_internal_navigation() -> None:
    navigation_links = "".join(
        f'<a href="/channels/navigation-{index}/">部门导航 {index}</a>'
        for index in range(640)
    )
    html = (
        "<html><body>"
        f"{navigation_links}"
        '<a href="/safety/2026/bridge-accident-notice-42.html">桥梁工程安全事故通报</a>'
        '<a href="/digital/2026/highway-iot-case-17.html">公路物联网数字化应用案例</a>'
        '<a href="/safety/2026/bridge-accident-notice-42.html">重复通报</a>'
        '<a href="http://jtt.sc.gov.cn/safety/insecure.html">非 HTTPS</a>'
        '<a href="https://other.example/digital/case.html">越界主机</a>'
        "</body></html>"
    )

    records = ListDetailConnector().discover(_fetched(html), _generic_config())

    assert len(records) == 50
    assert [record.url for record in records[:2]] == [
        "https://jtt.sc.gov.cn/safety/2026/bridge-accident-notice-42.html",
        "https://jtt.sc.gov.cn/digital/2026/highway-iot-case-17.html",
    ]
    assert len({record.url for record in records}) == len(records)
    assert all(record.url.startswith("https://jtt.sc.gov.cn/") for record in records)


def test_generic_profile_preserves_document_order_when_quality_scores_tie() -> None:
    html = (
        "<html><body>"
        '<a href="/safety/notice-2.html">桥梁安全生产通报</a>'
        '<a href="/safety/notice-1.html">桥梁安全生产通报</a>'
        "</body></html>"
    )

    records = ListDetailConnector().discover(_fetched(html), _generic_config())

    assert [record.url for record in records] == [
        "https://jtt.sc.gov.cn/safety/notice-2.html",
        "https://jtt.sc.gov.cn/safety/notice-1.html",
    ]


def test_strict_list_profile_retains_fail_fast_record_limit() -> None:
    items = "".join(
        (
            '<article class="item"><a class="detail" href="/notices/'
            f'{index}.html"><h2 class="title">通知 {index}</h2></a></article>'
        )
        for index in range(MAX_DISCOVERY_RECORDS + 1)
    )
    config: dict[str, object] = {
        "list_url": "https://jtt.sc.gov.cn/",
        "allowed_hosts": ["jtt.sc.gov.cn"],
        "item_selector": "article.item",
        "link_selector": "a.detail",
        "title_selector": "h2.title",
    }

    with pytest.raises(DeclarativeParseError, match="record limit exceeded"):
        ListDetailConnector().discover(_fetched(items), config)
