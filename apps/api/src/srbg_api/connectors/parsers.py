"""Built-in, non-executable parsers for the six declarative connector kinds."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from hashlib import sha256
from html.parser import HTMLParser
from typing import ClassVar, Protocol
from urllib.parse import urljoin, urlsplit
from xml.etree import ElementTree

from defusedxml import ElementTree as DefusedElementTree  # type: ignore[import-untyped]
from defusedxml.common import DefusedXmlException  # type: ignore[import-untyped]

from srbg_api.acquisition.contracts import DiscoveryRecord, FetchResult
from srbg_api.connectors.config import ConnectorKind


class DeclarativeParseError(ValueError):
    pass


class EmptyDiscoveryError(DeclarativeParseError):
    """The discovery document is valid but contains no current records."""


class RequiredFieldMissingError(DeclarativeParseError):
    """A discovered candidate cannot be represented without a required field."""


MAX_DISCOVERY_RECORDS = 500
MAX_STRUCTURED_NODES = 20_000
MAX_STRUCTURED_DEPTH = 64
MAX_DISCOVERY_BYTES = 5 * 1024 * 1024
MAX_DISCOVERY_EXTERNAL_ID_LENGTH = 500
MAX_DISCOVERY_TITLE_LENGTH = 500
MAX_DISCOVERY_URL_LENGTH = 2_048
MAX_DISCOVERY_TIMESTAMP_LENGTH = 100

_GENERIC_ENGINEERING_TERMS = (
    "工程",
    "公路",
    "道路",
    "桥梁",
    "隧道",
    "路桥",
    "交通",
    "建设",
    "施工",
    "engineering",
    "highway",
    "road",
    "bridge",
    "tunnel",
    "construction",
    "transport",
)
_GENERIC_SAFETY_TERMS = (
    "安全",
    "事故",
    "应急",
    "通报",
    "处罚",
    "整改",
    "标准",
    "规范",
    "指南",
    "safety",
    "accident",
    "emergency",
    "penalty",
    "standard",
)
_GENERIC_DIGITAL_TERMS = (
    "数字化",
    "智慧",
    "人工智能",
    "物联网",
    "低空",
    "无人机",
    "软件",
    "平台",
    "设备",
    "digital",
    "artificial intelligence",
    "iot",
    "drone",
    "software",
    "platform",
)
_GENERIC_DETAIL_PATH_TERMS = (
    "detail",
    "article",
    "content",
    "notice",
    "news",
    "report",
    "case",
    "document",
    "bulletin",
    "announcement",
    "policy",
    "standard",
)
_GENERIC_NAVIGATION_TERMS = (
    "首页",
    "导航",
    "栏目",
    "部门",
    "机构",
    "联系我们",
    "网站地图",
    "home",
    "navigation",
    "menu",
    "channel",
    "category",
    "department",
    "contact",
    "sitemap",
)
_GENERIC_DETAIL_SUFFIXES = (".html", ".htm", ".shtml", ".pdf")
_GENERIC_INDEX_NAMES = frozenset({"", "index", "index.html", "default", "list", "home"})


@dataclass(frozen=True, slots=True)
class ConnectorRequest:
    url: str
    role: str
    accept: str


class DeclarativeParser(Protocol):
    kind: ConnectorKind

    def initial_requests(self, config: dict[str, object]) -> tuple[ConnectorRequest, ...]: ...

    def discover(
        self,
        fetched: FetchResult,
        config: dict[str, object],
    ) -> tuple[DiscoveryRecord, ...]: ...

    def direct_record(
        self,
        request: ConnectorRequest,
        fetched: FetchResult,
    ) -> DiscoveryRecord: ...


class RssAtomConnector:
    kind = ConnectorKind.RSS_ATOM

    def initial_requests(self, config: dict[str, object]) -> tuple[ConnectorRequest, ...]:
        return (ConnectorRequest(_string(config, "feed_url"), "DISCOVERY", "application/xml"),)

    def discover(
        self,
        fetched: FetchResult,
        config: dict[str, object],
    ) -> tuple[DiscoveryRecord, ...]:
        root = _xml_root(fetched)
        entries = [node for node in root.iter() if _local_name(node.tag) in {"item", "entry"}]
        _enforce_record_limit(len(entries))
        records: list[DiscoveryRecord] = []
        for entry in entries:
            title = _child_text(entry, ("title",))
            link = _rss_link(entry)
            if not title or not link:
                raise RequiredFieldMissingError("feed entry lacks a title or link")
            url = urljoin(fetched.url, link)
            external_id = _child_text(entry, ("guid", "id")) or _stable_id(url)
            published = _parse_datetime(_child_text(entry, ("pubDate", "published")))
            source_modified_at = _parse_datetime(_child_text(entry, ("updated",)))
            records.append(
                _discovery_record(
                    external_id=external_id,
                    url=url,
                    title=title,
                    published_at=published,
                    discovered_at=fetched.fetched_at,
                    source_modified_at=source_modified_at,
                )
            )
        if not records:
            raise EmptyDiscoveryError("feed contains no discoverable entries")
        return tuple(records)

    def direct_record(
        self,
        request: ConnectorRequest,
        fetched: FetchResult,
    ) -> DiscoveryRecord:
        raise DeclarativeParseError("RSS connector has no direct document request")


class JsonApiConnector:
    kind = ConnectorKind.JSON_API

    def initial_requests(self, config: dict[str, object]) -> tuple[ConnectorRequest, ...]:
        return (ConnectorRequest(_string(config, "endpoint_url"), "DISCOVERY", "application/json"),)

    def discover(
        self,
        fetched: FetchResult,
        config: dict[str, object],
    ) -> tuple[DiscoveryRecord, ...]:
        if fetched.content is None:
            raise DeclarativeParseError("JSON API response has no body")
        if len(fetched.content) > MAX_DISCOVERY_BYTES:
            raise DeclarativeParseError("JSON API response exceeds the byte limit")
        try:
            document: object = json.loads(fetched.content)
        except (ValueError, RecursionError) as error:
            raise DeclarativeParseError("JSON API response is malformed") from error
        _validate_structured_shape(document)
        items = _resolve_pointer(document, _string(config, "items_pointer"))
        if not isinstance(items, list):
            raise DeclarativeParseError("JSON API items pointer is not an array")
        if not items:
            raise EmptyDiscoveryError("JSON API items pointer is an empty array")
        _enforce_record_limit(len(items))
        pointers = config.get("field_pointers")
        if not isinstance(pointers, dict):
            raise DeclarativeParseError("JSON API field pointers are missing")
        records: list[DiscoveryRecord] = []
        for item in items:
            external_id = _pointer_string(item, pointers, "external_id")
            title = _pointer_string(item, pointers, "title")
            raw_url = _pointer_string(item, pointers, "url")
            published_pointer = pointers.get("published_at")
            published_value = (
                _resolve_pointer(item, published_pointer)
                if isinstance(published_pointer, str)
                else None
            )
            records.append(
                _discovery_record(
                    external_id=external_id,
                    url=urljoin(fetched.url, raw_url),
                    title=title,
                    published_at=(
                        _parse_datetime(published_value)
                        if isinstance(published_value, str)
                        else None
                    ),
                    discovered_at=fetched.fetched_at,
                )
            )
        return tuple(records)

    def direct_record(
        self,
        request: ConnectorRequest,
        fetched: FetchResult,
    ) -> DiscoveryRecord:
        raise DeclarativeParseError("JSON API connector has no direct document request")


class SitemapConnector:
    kind = ConnectorKind.SITEMAP

    def initial_requests(self, config: dict[str, object]) -> tuple[ConnectorRequest, ...]:
        return (ConnectorRequest(_string(config, "sitemap_url"), "DISCOVERY", "application/xml"),)

    def discover(
        self,
        fetched: FetchResult,
        config: dict[str, object],
    ) -> tuple[DiscoveryRecord, ...]:
        root = _xml_root(fetched)
        records: list[DiscoveryRecord] = []
        for node in root.iter():
            if _local_name(node.tag) != "url":
                continue
            _enforce_record_limit(len(records) + 1)
            loc = _child_text(node, ("loc",))
            if not loc:
                raise RequiredFieldMissingError("sitemap URL entry has no location")
            url = urljoin(fetched.url, loc)
            source_modified_at = _parse_datetime(_child_text(node, ("lastmod",)))
            records.append(
                _discovery_record(
                    external_id=_stable_id(url),
                    url=url,
                    title=_filename_title(url),
                    published_at=None,
                    discovered_at=fetched.fetched_at,
                    source_modified_at=source_modified_at,
                )
            )
        if not records:
            raise EmptyDiscoveryError("sitemap contains no URL entries")
        return tuple(records)

    def direct_record(
        self,
        request: ConnectorRequest,
        fetched: FetchResult,
    ) -> DiscoveryRecord:
        raise DeclarativeParseError("sitemap connector has no direct document request")


@dataclass(slots=True)
class _HtmlNode:
    tag: str
    attrs: dict[str, str]
    children: list[_HtmlNode] = field(default_factory=list)
    text_parts: list[str] = field(default_factory=list)


class _TreeParser(HTMLParser):
    _VOID: ClassVar[frozenset[str]] = frozenset(
        {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta"}
    )

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = _HtmlNode("document", {})
        self._stack = [self.root]
        self._node_count = 1

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._node_count += 1
        if self._node_count > MAX_STRUCTURED_NODES or len(self._stack) > MAX_STRUCTURED_DEPTH:
            raise DeclarativeParseError("HTML discovery structure exceeds safety limits")
        node = _HtmlNode(tag.casefold(), {key.casefold(): value or "" for key, value in attrs})
        self._stack[-1].children.append(node)
        if tag.casefold() not in self._VOID:
            self._stack.append(node)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if tag.casefold() not in self._VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        expected = tag.casefold()
        for index in range(len(self._stack) - 1, 0, -1):
            if self._stack[index].tag == expected:
                del self._stack[index:]
                return

    def handle_data(self, data: str) -> None:
        self._stack[-1].text_parts.append(data)


class ListDetailConnector:
    kind = ConnectorKind.LIST_DETAIL

    def initial_requests(self, config: dict[str, object]) -> tuple[ConnectorRequest, ...]:
        return (ConnectorRequest(_string(config, "list_url"), "DISCOVERY", "text/html"),)

    def discover(
        self,
        fetched: FetchResult,
        config: dict[str, object],
    ) -> tuple[DiscoveryRecord, ...]:
        if fetched.content is None:
            raise DeclarativeParseError("list response has no body")
        if len(fetched.content) > MAX_DISCOVERY_BYTES:
            raise DeclarativeParseError("list response exceeds the byte limit")
        parser = _TreeParser()
        try:
            parser.feed(fetched.content.decode("utf-8"))
        except UnicodeDecodeError as error:
            raise DeclarativeParseError("list response is not UTF-8 HTML") from error
        item_selector = _string(config, "item_selector")
        link_selector = _string(config, "link_selector")
        title_selector = _string(config, "title_selector")
        published_selector = config.get("published_selector")
        items = _find_nodes(parser.root, item_selector)
        generic_internal_links = (
            item_selector == "a" and link_selector == "a" and title_selector == "a"
        )
        if not generic_internal_links:
            _enforce_record_limit(len(items))
        records: list[DiscoveryRecord] = []
        generic_candidates: list[tuple[int, int, DiscoveryRecord]] = []
        generic_candidate_indexes: dict[str, int] = {}
        for document_position, item in enumerate(items):
            link_node = _find_first(item, link_selector)
            title_node = _find_first(item, title_selector)
            href = link_node.attrs.get("href") if link_node is not None else None
            title = _node_text(title_node) if title_node is not None else ""
            if not href or not title:
                if generic_internal_links:
                    continue
                raise RequiredFieldMissingError(
                    "list item lacks a declarative link or title"
                )
            url = urljoin(fetched.url, href)
            if generic_internal_links and (
                not _generic_internal_url_allowed(url, config)
                or url == fetched.url
            ):
                continue
            published = None
            if isinstance(published_selector, str):
                published_node = _find_first(item, published_selector)
                published = _parse_datetime(
                    _node_text(published_node) if published_node is not None else None
                )
            try:
                record = _discovery_record(
                    external_id=_stable_id(url),
                    url=url,
                    title=title,
                    published_at=published,
                    discovered_at=fetched.fetched_at,
                )
            except DeclarativeParseError:
                if generic_internal_links:
                    continue
                raise
            if not generic_internal_links:
                records.append(record)
                continue
            quality = _generic_link_quality(title=title, url=url)
            existing_index = generic_candidate_indexes.get(url)
            if existing_index is None:
                generic_candidate_indexes[url] = len(generic_candidates)
                generic_candidates.append((quality, document_position, record))
            elif quality > generic_candidates[existing_index][0]:
                first_position = generic_candidates[existing_index][1]
                generic_candidates[existing_index] = (quality, first_position, record)
        if generic_internal_links:
            generic_candidates.sort(key=lambda candidate: (-candidate[0], candidate[1]))
            max_items = config.get("max_items", 50)
            if isinstance(max_items, bool) or not isinstance(max_items, int) or max_items < 2:
                raise DeclarativeParseError("generic list max_items is invalid")
            records = [candidate[2] for candidate in generic_candidates[:max_items]]
        if not records:
            raise EmptyDiscoveryError("list contains no matching items")
        return tuple(records)

    def direct_record(
        self,
        request: ConnectorRequest,
        fetched: FetchResult,
    ) -> DiscoveryRecord:
        raise DeclarativeParseError("list connector has no direct document request")


class DirectPdfConnector:
    kind = ConnectorKind.DIRECT_PDF

    def initial_requests(self, config: dict[str, object]) -> tuple[ConnectorRequest, ...]:
        values = config.get("document_urls")
        if not isinstance(values, list):
            raise DeclarativeParseError("direct PDF URLs are missing")
        return tuple(
            ConnectorRequest(value, "DOCUMENT", "application/pdf")
            for value in values
            if isinstance(value, str)
        )

    def discover(
        self,
        fetched: FetchResult,
        config: dict[str, object],
    ) -> tuple[DiscoveryRecord, ...]:
        raise DeclarativeParseError("direct PDF response is not a discovery document")

    def direct_record(
        self,
        request: ConnectorRequest,
        fetched: FetchResult,
    ) -> DiscoveryRecord:
        return _discovery_record(
            external_id=_stable_id(request.url),
            url=request.url,
            title=_filename_title(request.url),
            published_at=None,
            discovered_at=fetched.fetched_at,
        )


CONNECTOR_PARSERS: dict[ConnectorKind, DeclarativeParser] = {
    ConnectorKind.RSS_ATOM: RssAtomConnector(),
    ConnectorKind.JSON_API: JsonApiConnector(),
    ConnectorKind.SITEMAP: SitemapConnector(),
    ConnectorKind.LIST_DETAIL: ListDetailConnector(),
    ConnectorKind.DIRECT_PDF: DirectPdfConnector(),
}


def _string(document: dict[str, object], field_name: str) -> str:
    value = document.get(field_name)
    if not isinstance(value, str):
        raise DeclarativeParseError(f"connector field is missing: {field_name}")
    return value


def _xml_root(fetched: FetchResult) -> ElementTree.Element:
    if fetched.content is None:
        raise DeclarativeParseError("XML response has no body")
    if len(fetched.content) > MAX_DISCOVERY_BYTES:
        raise DeclarativeParseError("XML discovery response exceeds the byte limit")
    try:
        root: ElementTree.Element = DefusedElementTree.fromstring(
            fetched.content,
            forbid_dtd=True,
            forbid_entities=True,
            forbid_external=True,
        )
    except (ElementTree.ParseError, DefusedXmlException) as error:
        raise DeclarativeParseError("XML response is malformed") from error
    _validate_xml_shape(root)
    return root


def _local_name(tag: str) -> str:
    return tag.rsplit("}", maxsplit=1)[-1]


def _child_text(node: ElementTree.Element, names: tuple[str, ...]) -> str | None:
    for child in node:
        if _local_name(child.tag) in names and child.text:
            value = " ".join(child.text.split())
            if value:
                return value
    return None


def _rss_link(node: ElementTree.Element) -> str | None:
    for child in node:
        if _local_name(child.tag) != "link":
            continue
        href = child.attrib.get("href")
        if href:
            return href.strip()
        if child.text and child.text.strip():
            return child.text.strip()
    return None


def _parse_datetime(value: str | None) -> datetime | None:
    if value is None or not value.strip():
        return None
    candidate = value.strip()
    if len(candidate) > MAX_DISCOVERY_TIMESTAMP_LENGTH:
        raise DeclarativeParseError("published timestamp exceeds the length limit")
    try:
        parsed = datetime.fromisoformat(candidate.replace("Z", "+00:00"))
    except ValueError:
        try:
            parsed = parsedate_to_datetime(candidate)
        except (TypeError, ValueError, OverflowError) as error:
            raise DeclarativeParseError("published timestamp is invalid") from error
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _resolve_pointer(document: object, pointer: str) -> object:
    current = document
    for encoded in pointer.split("/")[1:]:
        token = encoded.replace("~1", "/").replace("~0", "~")
        if isinstance(current, dict) and token in current:
            current = current[token]
        elif isinstance(current, list) and token.isdigit() and int(token) < len(current):
            current = current[int(token)]
        else:
            raise DeclarativeParseError("JSON pointer does not resolve")
    return current


def _pointer_string(item: object, pointers: dict[object, object], field_name: str) -> str:
    pointer = pointers.get(field_name)
    if not isinstance(pointer, str):
        raise RequiredFieldMissingError("JSON field pointer is missing")
    try:
        value = _resolve_pointer(item, pointer)
    except DeclarativeParseError as error:
        raise RequiredFieldMissingError("JSON required field does not resolve") from error
    if not isinstance(value, str) or not value.strip():
        raise RequiredFieldMissingError("JSON field pointer does not resolve to text")
    return value.strip()


def _find_nodes(root: _HtmlNode, selector: str) -> list[_HtmlNode]:
    matches: list[_HtmlNode] = []
    for child in root.children:
        if _matches(child, selector):
            matches.append(child)
        matches.extend(_find_nodes(child, selector))
    return matches


def _generic_internal_url_allowed(url: str, config: dict[str, object]) -> bool:
    allowed_value = config.get("allowed_hosts")
    if not isinstance(allowed_value, list) or not allowed_value:
        return False
    allowed_hosts = {
        value.rstrip(".").casefold()
        for value in allowed_value
        if isinstance(value, str) and value
    }
    try:
        parts = urlsplit(url)
        hostname = None if parts.hostname is None else parts.hostname.rstrip(".").casefold()
        port = parts.port
    except ValueError:
        return False
    list_url = config.get("list_url")
    if not isinstance(list_url, str):
        return False
    list_path = urlsplit(list_url).path or "/"
    normalized_prefix = list_path if list_path.endswith("/") else list_path + "/"
    within_path = parts.path == normalized_prefix[:-1] or parts.path.startswith(
        normalized_prefix
    )
    return bool(
        parts.scheme.casefold() == "https"
        and hostname in allowed_hosts
        and port in {None, 443}
        and parts.username is None
        and parts.password is None
        and not parts.query
        and not parts.fragment
        and within_path
    )


def _generic_link_quality(*, title: str, url: str) -> int:
    """Rank generic links using only deterministic, auditable page evidence."""
    path = urlsplit(url).path.casefold()
    evidence = f"{title.casefold()} {path}"
    score = 0
    for terms in (
        _GENERIC_ENGINEERING_TERMS,
        _GENERIC_SAFETY_TERMS,
        _GENERIC_DIGITAL_TERMS,
    ):
        if any(term in evidence for term in terms):
            score += 100
    if path.endswith(_GENERIC_DETAIL_SUFFIXES):
        score += 30
    if any(term in path for term in _GENERIC_DETAIL_PATH_TERMS):
        score += 20
    last_segment = path.rstrip("/").rsplit("/", maxsplit=1)[-1]
    if last_segment.casefold() not in _GENERIC_INDEX_NAMES and not path.endswith("/"):
        score += 20
    if any(character.isdigit() for character in last_segment):
        score += 10
    if len([segment for segment in path.split("/") if segment]) >= 2:
        score += 5
    if len(title.strip()) >= 8:
        score += 5
    if any(term in evidence for term in _GENERIC_NAVIGATION_TERMS):
        score -= 100
    if path.endswith("/"):
        score -= 20
    return score


def _find_first(root: _HtmlNode, selector: str) -> _HtmlNode | None:
    if _matches(root, selector):
        return root
    for child in root.children:
        found = _find_first(child, selector)
        if found is not None:
            return found
    return None


def _matches(node: _HtmlNode, selector: str) -> bool:
    marker_index = next(
        (index for index, char in enumerate(selector) if char in {".", "#"}),
        len(selector),
    )
    tag = selector[:marker_index]
    marker = selector[marker_index : marker_index + 1]
    name = selector[marker_index + 1 :]
    if tag and node.tag != tag:
        return False
    if marker == ".":
        return name in node.attrs.get("class", "").split()
    if marker == "#":
        return node.attrs.get("id") == name
    return bool(tag) and node.tag == tag


def _node_text(node: _HtmlNode) -> str:
    values = list(node.text_parts)
    for child in node.children:
        values.append(_node_text(child))
    return " ".join(" ".join(values).split())


def _stable_id(url: str) -> str:
    return sha256(url.encode()).hexdigest()


def _filename_title(url: str) -> str:
    path = urlsplit(url).path.rstrip("/")
    return path.rsplit("/", maxsplit=1)[-1] or "document"


def _discovery_record(
    *,
    external_id: str,
    url: str,
    title: str,
    published_at: datetime | None,
    discovered_at: datetime,
    source_modified_at: datetime | None = None,
) -> DiscoveryRecord:
    return DiscoveryRecord(
        external_id=_bounded_field(
            external_id,
            field_name="external id",
            max_length=MAX_DISCOVERY_EXTERNAL_ID_LENGTH,
        ),
        url=_bounded_field(
            url,
            field_name="URL",
            max_length=MAX_DISCOVERY_URL_LENGTH,
        ),
        title=_bounded_field(
            title,
            field_name="title",
            max_length=MAX_DISCOVERY_TITLE_LENGTH,
        ),
        published_at=published_at,
        discovered_at=discovered_at,
        source_modified_at=source_modified_at,
    )


def _bounded_field(value: str, *, field_name: str, max_length: int) -> str:
    if not value or len(value) > max_length:
        raise DeclarativeParseError(f"discovery {field_name} is empty or exceeds the length limit")
    return value


def _enforce_record_limit(count: int) -> None:
    if count > MAX_DISCOVERY_RECORDS:
        raise DeclarativeParseError("discovery record limit exceeded")


def _validate_structured_shape(document: object) -> None:
    stack: list[tuple[object, int]] = [(document, 1)]
    nodes = 0
    while stack:
        value, depth = stack.pop()
        nodes += 1
        if nodes > MAX_STRUCTURED_NODES or depth > MAX_STRUCTURED_DEPTH:
            raise DeclarativeParseError("JSON discovery structure exceeds safety limits")
        if isinstance(value, dict):
            stack.extend((nested, depth + 1) for nested in value.values())
        elif isinstance(value, list):
            stack.extend((nested, depth + 1) for nested in value)


def _validate_xml_shape(root: ElementTree.Element) -> None:
    stack: list[tuple[ElementTree.Element, int]] = [(root, 1)]
    nodes = 0
    while stack:
        node, depth = stack.pop()
        nodes += 1
        if nodes > MAX_STRUCTURED_NODES or depth > MAX_STRUCTURED_DEPTH:
            raise DeclarativeParseError("XML discovery structure exceeds safety limits")
        stack.extend((child, depth + 1) for child in node)
