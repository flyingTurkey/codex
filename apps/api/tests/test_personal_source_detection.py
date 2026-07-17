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
    body = b"<html><head><link rel='canonical' href='/news/'></head></html>"
    result = detect_streams(
        url="https://example.test/index", content_type="text/html", content=body
    )
    assert result.follow_up_urls == ("https://example.test/news/",)


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
