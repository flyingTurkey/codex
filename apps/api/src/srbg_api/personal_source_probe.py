"""Bounded, deterministic detection for Owner-submitted public source URLs."""

from __future__ import annotations

import ipaddress
import json
from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit, urlunsplit

from defusedxml import ElementTree  # type: ignore[import-untyped]
from srbg_contracts import PersonalSourceInputKind, PersonalSourceStreamType

from srbg_api.connectors.config import ConnectorKind, validate_connector_config
from srbg_api.connectors.parsers import (
    _generic_internal_url_allowed,
    _generic_link_quality,
)


class ProbeDetectionError(ValueError):
    """A stable, content-free detection failure safe to persist."""


@dataclass(frozen=True, slots=True)
class DetectedStream:
    stream_type: PersonalSourceStreamType
    normalized_url: str
    config: dict[str, object]
    discovery_method: str = "DIRECT"


@dataclass(frozen=True, slots=True)
class DetectionResult:
    input_kind: PersonalSourceInputKind
    streams: tuple[DetectedStream, ...]
    follow_up_urls: tuple[str, ...] = ()


def normalize_public_https_url(value: str) -> tuple[str, str, str]:
    """Return normalized URL, normalized Origin, and exact allowed host."""

    if not isinstance(value, str) or not value or len(value) > 2048:
        raise ValueError("URL_INVALID")
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise ValueError("URL_INVALID")
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError as error:
        raise ValueError("URL_INVALID") from error
    if (
        parsed.scheme.casefold() != "https"
        or parsed.hostname is None
        or parsed.username is not None
        or parsed.password is not None
        or port not in {None, 443}
        or parsed.fragment
    ):
        raise ValueError("PUBLIC_HTTPS_REQUIRED")
    try:
        host = parsed.hostname.rstrip(".").encode("idna").decode("ascii").casefold()
    except UnicodeError as error:
        raise ValueError("URL_INVALID") from error
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        raise ValueError("IP_LITERAL_FORBIDDEN")
    if "." not in host or len(host) > 253:
        raise ValueError("PUBLIC_DNS_NAME_REQUIRED")
    netloc = host
    path = parsed.path or "/"
    normalized = urlunsplit(("https", netloc, path, parsed.query, ""))
    origin = f"https://{host}/"
    return normalized, origin, host


def detect_streams(*, url: str, content_type: str, content: bytes) -> DetectionResult:
    normalized_url, _, host = normalize_public_https_url(url)
    if not content:
        raise ProbeDetectionError("EMPTY_RESPONSE")
    mime = content_type.split(";", 1)[0].strip().casefold()
    stripped = content.lstrip()
    if mime == "application/pdf" or normalized_url.casefold().endswith(".pdf"):
        if not stripped.startswith(b"%PDF-"):
            raise ProbeDetectionError("MIME_MISMATCH")
        return _single(
            PersonalSourceInputKind.DIRECT_PDF,
            PersonalSourceStreamType.DIRECT_PDF,
            normalized_url,
            host,
            {"document_urls": [normalized_url]},
        )
    if stripped.startswith(b"%PDF-"):
        return _single(
            PersonalSourceInputKind.DIRECT_PDF,
            PersonalSourceStreamType.DIRECT_PDF,
            normalized_url,
            host,
            {"document_urls": [normalized_url]},
        )
    if _looks_json(mime, stripped):
        return _detect_json(normalized_url, host, content)
    if _looks_xml(mime, stripped):
        xml_result = _detect_xml(normalized_url, host, content)
        if xml_result is not None:
            return xml_result
    if mime in {"text/html", "application/xhtml+xml", ""} or b"<html" in stripped[:512].lower():
        return _detect_html(normalized_url, host, content)
    raise ProbeDetectionError("UNSUPPORTED_RESPONSE_TYPE")


def _single(
    input_kind: PersonalSourceInputKind,
    stream_type: PersonalSourceStreamType,
    url: str,
    host: str,
    fields: dict[str, object],
) -> DetectionResult:
    kind = ConnectorKind(stream_type.value)
    document = {"allowed_hosts": [host]} | fields
    validated = validate_connector_config(kind, document, source_allowed_hosts=(host,))
    return DetectionResult(
        input_kind=input_kind,
        streams=(DetectedStream(stream_type, url, validated.document),),
    )


def _looks_json(mime: str, content: bytes) -> bool:
    return mime in {"application/json", "application/ld+json"} or content[:1] in {b"{", b"["}


def _detect_json(url: str, host: str, content: bytes) -> DetectionResult:
    try:
        value = json.loads(content)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ProbeDetectionError("INVALID_JSON") from error
    items: object
    pointer: str
    if isinstance(value, list):
        items, pointer = value, "/"
    elif isinstance(value, dict) and isinstance(value.get("items"), list):
        items, pointer = value["items"], "/items"
    elif isinstance(value, dict) and isinstance(value.get("data"), list):
        items, pointer = value["data"], "/data"
    else:
        raise ProbeDetectionError("UNSUPPORTED_JSON_STRUCTURE")
    first = items[0] if isinstance(items, list) and items else None
    if not isinstance(first, dict):
        raise ProbeDetectionError("UNSUPPORTED_JSON_STRUCTURE")
    id_key = next((key for key in ("id", "guid", "uuid") if key in first), None)
    url_key = next((key for key in ("url", "link", "href") if key in first), None)
    title_key = next((key for key in ("title", "name") if key in first), None)
    if id_key is None or url_key is None or title_key is None:
        raise ProbeDetectionError("UNSUPPORTED_JSON_STRUCTURE")
    fields: dict[str, str] = {
        "external_id": f"/{id_key}",
        "url": f"/{url_key}",
        "title": f"/{title_key}",
    }
    published = next((key for key in ("published_at", "published", "date") if key in first), None)
    if published is not None:
        fields["published_at"] = f"/{published}"
    return _single(
        PersonalSourceInputKind.JSON_API,
        PersonalSourceStreamType.JSON_API,
        url,
        host,
        {
            "endpoint_url": url,
            "items_pointer": pointer,
            "field_pointers": fields,
            "pagination": "NONE",
        },
    )


def _looks_xml(mime: str, content: bytes) -> bool:
    return (
        "xml" in mime
        or content.startswith(b"<?xml")
        or content.startswith((b"<rss", b"<feed", b"<urlset", b"<sitemapindex"))
    )


def _detect_xml(url: str, host: str, content: bytes) -> DetectionResult | None:
    try:
        root = ElementTree.fromstring(content)
    except ElementTree.ParseError as error:
        raise ProbeDetectionError("INVALID_XML") from error
    tag = root.tag.rsplit("}", 1)[-1].casefold()
    if tag in {"rss", "feed"}:
        return _single(
            PersonalSourceInputKind.RSS_ATOM,
            PersonalSourceStreamType.RSS_ATOM,
            url,
            host,
            {"feed_url": url},
        )
    if tag in {"urlset", "sitemapindex"}:
        return _single(
            PersonalSourceInputKind.SITEMAP,
            PersonalSourceStreamType.SITEMAP,
            url,
            host,
            {"sitemap_url": url},
        )
    return None


class _EntryParser(HTMLParser):
    _VOID = frozenset({"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta"})
    _HIDDEN_TAGS = frozenset({"script", "style", "template", "noscript", "svg"})

    def __init__(self, base_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.feed_urls: list[str] = []
        self.sitemap_urls: list[str] = []
        self.canonical_urls: list[str] = []
        self.meta_refresh_urls: list[str] = []
        self.anchor_candidates: list[tuple[str, str]] = []
        self.client_redirect_present = False
        self.article_links = 0
        self._article_depth = 0
        self._element_stack: list[tuple[str, bool]] = []
        self._anchor: tuple[str, list[str], bool] | None = None
        self._script_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        normalized_tag = tag.casefold()
        values = {key.casefold(): value for key, value in attrs if value is not None}
        inherited_hidden = self._element_stack[-1][1] if self._element_stack else False
        style = values.get("style", "").replace(" ", "").casefold()
        own_hidden = (
            normalized_tag in self._HIDDEN_TAGS
            or "hidden" in values
            or values.get("aria-hidden", "").casefold() == "true"
            or "display:none" in style
            or "visibility:hidden" in style
        )
        hidden = inherited_hidden or own_hidden
        if normalized_tag not in self._VOID:
            self._element_stack.append((normalized_tag, hidden))
        if normalized_tag == "script":
            self._script_depth += 1
        if normalized_tag == "article":
            self._article_depth += 1
        if normalized_tag == "link":
            rel = values.get("rel", "").casefold().split()
            kind = values.get("type", "").casefold()
            href = values.get("href")
            if (
                href
                and "alternate" in rel
                and kind in {"application/rss+xml", "application/atom+xml"}
            ):
                self.feed_urls.append(urljoin(self.base_url, href))
            if href and "sitemap" in rel:
                self.sitemap_urls.append(urljoin(self.base_url, href))
            if href and "canonical" in rel:
                self.canonical_urls.append(urljoin(self.base_url, href))
        if normalized_tag == "meta" and values.get("http-equiv", "").casefold() == "refresh":
            content = values.get("content", "")
            delay, separator, target = content.partition(";")
            if separator and delay.strip() == "0" and "=" in target:
                field, value = target.split("=", 1)
                if field.strip().casefold() == "url" and value.strip():
                    self.meta_refresh_urls.append(
                        urljoin(self.base_url, value.strip().strip("\"'"))
                    )
        if normalized_tag == "a" and values.get("href"):
            if self._article_depth:
                self.article_links += 1
            self._anchor = (values["href"], [], hidden)

    def handle_endtag(self, tag: str) -> None:
        normalized_tag = tag.casefold()
        if normalized_tag == "a" and self._anchor is not None:
            href, text_parts, hidden = self._anchor
            title = " ".join(" ".join(text_parts).split())
            if not hidden and title:
                self.anchor_candidates.append((urljoin(self.base_url, href), title))
            self._anchor = None
        if normalized_tag == "article" and self._article_depth:
            self._article_depth -= 1
        if normalized_tag == "script" and self._script_depth:
            self._script_depth -= 1
        for index in range(len(self._element_stack) - 1, -1, -1):
            if self._element_stack[index][0] == normalized_tag:
                del self._element_stack[index:]
                break

    def handle_data(self, data: str) -> None:
        if self._anchor is not None:
            self._anchor[1].append(data)
        if self._script_depth and any(
            marker in data.casefold()
            for marker in ("window.location", "location.href", "location.replace")
        ):
            self.client_redirect_present = True


def _detect_html(url: str, host: str, content: bytes) -> DetectionResult:
    try:
        text = content.decode("utf-8", errors="replace")
    except UnicodeError as error:
        raise ProbeDetectionError("INVALID_HTML") from error
    parser = _EntryParser(url)
    parser.feed(text)
    safe_links: list[str] = []
    for candidate in (
        parser.feed_urls
        + parser.sitemap_urls
        + parser.canonical_urls
        + parser.meta_refresh_urls
    ):
        try:
            normalized, _, candidate_host = normalize_public_https_url(candidate)
        except ValueError:
            continue
        if (
            candidate_host == host
            and normalized != url
            and _generic_internal_url_allowed(
                normalized, {"allowed_hosts": [host], "list_url": url}
            )
            and normalized not in safe_links
        ):
            safe_links.append(normalized)
    if safe_links:
        return DetectionResult(
            input_kind=PersonalSourceInputKind.HOMEPAGE
            if urlsplit(url).path in {"", "/"}
            else PersonalSourceInputKind.LIST_PAGE,
            streams=(),
            follow_up_urls=tuple(safe_links[:5]),
        )
    if parser.article_links >= 2:
        return _single(
            PersonalSourceInputKind.LIST_PAGE,
            PersonalSourceStreamType.LIST_DETAIL,
            url,
            host,
            {
                "list_url": url,
                "item_selector": "article",
                "link_selector": "a",
                "title_selector": "a",
            },
        )
    generic_candidates: dict[str, int] = {}
    archive_follow_ups: list[str] = []
    generic_config: dict[str, object] = {"allowed_hosts": [host], "list_url": url}
    for candidate, title in parser.anchor_candidates:
        if not _generic_internal_url_allowed(candidate, generic_config) or candidate == url:
            continue
        score = _generic_link_quality(title=title, url=candidate)
        if score >= 30:
            generic_candidates[candidate] = max(score, generic_candidates.get(candidate, score))
        candidate_path = urlsplit(candidate).path.rstrip("/")
        if (
            len(title) == 4
            and title.isdigit()
            and 2000 <= int(title) <= 2100
            and candidate_path.rsplit("/", 1)[-1] == title
            and candidate not in archive_follow_ups
        ):
            archive_follow_ups.append(candidate)
    if len(generic_candidates) >= 2:
        return _single(
            PersonalSourceInputKind.LIST_PAGE,
            PersonalSourceStreamType.LIST_DETAIL,
            url,
            host,
            {
                "list_url": url,
                "item_selector": "a",
                "link_selector": "a",
                "title_selector": "a",
            },
        )
    if archive_follow_ups:
        return DetectionResult(
            input_kind=PersonalSourceInputKind.LIST_PAGE,
            streams=(),
            follow_up_urls=tuple(archive_follow_ups[:5]),
        )
    if parser.client_redirect_present:
        raise ProbeDetectionError("UNSUPPORTED_CLIENT_REDIRECT")
    raise ProbeDetectionError("UNRECOGNIZED_PUBLIC_ENTRY")
