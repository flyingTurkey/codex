import pytest
from srbg_api.personal_source_probe import (
    ProbeDetectionError,
    detect_streams,
    normalize_public_https_url,
)
from srbg_contracts import PersonalSourceInputKind, PersonalSourceStreamType


@pytest.mark.parametrize(
    ("url", "content_type", "body", "expected"),
    [
        (
            "https://example.test/feed",
            "application/rss+xml",
            b"<rss><channel/></rss>",
            PersonalSourceStreamType.RSS_ATOM,
        ),
        (
            "https://example.test/sitemap.xml",
            "application/xml",
            b"<urlset xmlns='http://www.sitemaps.org/schemas/sitemap/0.9'/>",
            PersonalSourceStreamType.SITEMAP,
        ),
        (
            "https://example.test/api",
            "application/json",
            b'{"items":[{"id":"1","url":"https://example.test/a","title":"A"}]}',
            PersonalSourceStreamType.JSON_API,
        ),
        (
            "https://example.test/file",
            "application/pdf",
            b"%PDF-1.7\n%%EOF",
            PersonalSourceStreamType.DIRECT_PDF,
        ),
        (
            "https://example.test/news/",
            "text/html",
            b"<html><body><main><article><a href='/a'>A</a></article>"
            b"<article><a href='/b'>B</a></article></main></body></html>",
            PersonalSourceStreamType.LIST_DETAIL,
        ),
    ],
)
def test_direct_stream_types_are_detected_from_bytes_and_structure(
    url: str, content_type: str, body: bytes, expected: PersonalSourceStreamType
) -> None:
    result = detect_streams(url=url, content_type=content_type, content=body)
    assert result.streams[0].stream_type is expected


def test_homepage_discovers_same_origin_public_feed() -> None:
    body = (
        b"<html><head><link rel='alternate' type='application/rss+xml' "
        b"href='/feed.xml'></head></html>"
    )
    result = detect_streams(url="https://example.test/", content_type="text/html", content=body)
    assert result.input_kind is PersonalSourceInputKind.HOMEPAGE
    assert result.follow_up_urls == ("https://example.test/feed.xml",)


def test_html_canonical_is_a_bounded_same_origin_follow_up() -> None:
    body = b"<html><head><link rel='canonical' href='/index/news/'></head></html>"
    result = detect_streams(
        url="https://example.test/index", content_type="text/html", content=body
    )
    assert result.follow_up_urls == ("https://example.test/index/news/",)


def test_legacy_government_list_uses_bounded_generic_anchor_connector() -> None:
    body = b"""
    <html><body><div class="news-list"><ul>
      <li><a href="/policy/2026/content_1001.html">Transport safety policy update</a></li>
      <li><a href="/policy/2026/content_1002.html">Digital transport guidance update</a></li>
    </ul></div></body></html>
    """

    result = detect_streams(
        url="https://example.test/policy/", content_type="text/html", content=body
    )

    assert result.input_kind is PersonalSourceInputKind.LIST_PAGE
    assert result.streams[0].stream_type is PersonalSourceStreamType.LIST_DETAIL
    assert result.streams[0].config == {
        "allowed_hosts": ["example.test"],
        "item_selector": "a",
        "link_selector": "a",
        "list_url": "https://example.test/policy/",
        "max_items": 5,
        "title_selector": "a",
    }


def test_generic_anchor_detection_excludes_hidden_noisy_and_out_of_scope_links() -> None:
    body = b"""
    <html><body>
      <div style="display:none">
        <a href="/policy/2026/content_hidden.html">Hidden safety report</a>
      </div>
      <a href="https://other.test/policy/2026/content_1.html">External safety report</a>
      <a href="/other/2026/content_2.html">Out of path safety report</a>
      <a href="/policy/2026/content_3.html?preview=1">Preview safety report</a>
      <a href="/policy/">Policy home</a>
    </body></html>
    """

    with pytest.raises(ProbeDetectionError, match="UNRECOGNIZED_PUBLIC_ENTRY"):
        detect_streams(
            url="https://example.test/policy/", content_type="text/html", content=body
        )


def test_zero_delay_same_scope_meta_refresh_is_a_bounded_follow_up() -> None:
    body = b"<html><head><meta http-equiv='refresh' content='0; URL=/policy/list/'></head></html>"

    result = detect_streams(
        url="https://example.test/policy/", content_type="text/html", content=body
    )

    assert result.follow_up_urls == ("https://example.test/policy/list/",)


def test_javascript_redirect_is_classified_but_never_interpreted() -> None:
    body = b"""
    <html><body><script>
      const domain = 'https://example.test';
      const targetPath = '/policy/list/';
      window.location.href = domain + targetPath;
    </script></body></html>
    """

    with pytest.raises(ProbeDetectionError, match="UNSUPPORTED_CLIENT_REDIRECT"):
        detect_streams(
            url="https://example.test/policy/", content_type="text/html", content=body
        )


def test_year_archive_directories_are_bounded_same_scope_follow_ups() -> None:
    body = b"""
    <html><body>
      <a href="/reports/2026/">2026</a>
      <a href="/reports/2025/">2025</a>
      <a href="/other/2024/">2024</a>
      <script>window.location.href = dynamicTarget;</script>
    </body></html>
    """

    result = detect_streams(
        url="https://example.test/reports/", content_type="text/html", content=body
    )

    assert result.follow_up_urls == (
        "https://example.test/reports/2026/",
        "https://example.test/reports/2025/",
    )


def test_cross_origin_canonical_is_not_followed() -> None:
    body = b"<html><head><link rel='canonical' href='https://other.test/news/'></head></html>"
    with pytest.raises(ProbeDetectionError, match="UNRECOGNIZED_PUBLIC_ENTRY"):
        detect_streams(url="https://example.test/", content_type="text/html", content=body)


@pytest.mark.parametrize(
    "url",
    [
        "http://example.test/",
        "https://127.0.0.1/",
        "https://169.254.169.254/latest/meta-data/",
        "https://user:password@example.test/",
        "https://example.test:444/",
    ],
)
def test_obviously_unsafe_urls_are_rejected_before_network(url: str) -> None:
    with pytest.raises(ValueError):
        normalize_public_https_url(url)


def test_mime_spoofing_and_unrecognized_html_fail_with_stable_reason() -> None:
    with pytest.raises(ProbeDetectionError, match="MIME_MISMATCH"):
        detect_streams(
            url="https://example.test/document.pdf",
            content_type="application/pdf",
            content=b"<html>not a pdf</html>",
        )
    with pytest.raises(ProbeDetectionError, match="UNRECOGNIZED_PUBLIC_ENTRY"):
        detect_streams(
            url="https://example.test/",
            content_type="text/html",
            content=b"<html><body>plain landing page</body></html>",
        )
