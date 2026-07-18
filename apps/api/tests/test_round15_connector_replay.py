from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from uuid import UUID
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
import srbg_api.connectors.replay as connector_replay
from srbg_api.acquisition.contracts import (
    DiscoveryRecord,
    DocumentVersion,
    ExecutionDomain,
    FetchResult,
    RawObject,
    SourceAdapter,
)
from srbg_api.connectors import ConnectorKind
from srbg_api.connectors.parsers import (
    MAX_DISCOVERY_BYTES,
    MAX_DISCOVERY_RECORDS,
    MAX_DISCOVERY_TITLE_LENGTH,
    MAX_DISCOVERY_URL_LENGTH,
)
from srbg_api.connectors.replay import (
    ConnectorParseFailed,
    FixedFixtureTransport,
    FixedReplayExecutor,
    FixtureExchange,
    FixtureProductionDenied,
    InMemoryEvidenceStore,
    ManualImportSubmission,
    RawFirstIngestionService,
)

FIXTURES = Path(__file__).parent / "fixtures"
CONNECTOR_FIXTURES = FIXTURES / "round15" / "connectors"
SOURCE_FIXTURES = FIXTURES / "source"
NOW = datetime(2026, 7, 16, 1, 2, 3, tzinfo=UTC)
DETAIL = (CONNECTOR_FIXTURES / "detail.html").read_bytes()
PDF = (SOURCE_FIXTURES / "round01-sample.pdf").read_bytes()


def _exchange(
    url: str,
    content: bytes,
    content_type: str,
    *,
    etag: str,
) -> FixtureExchange:
    return FixtureExchange(
        url=url,
        status_code=200,
        headers={
            "Content-Type": content_type,
            "ETag": etag,
            "Last-Modified": "Wed, 15 Jul 2026 06:00:00 GMT",
        },
        content=content,
    )


def _safe_zip() -> bytes:
    target = BytesIO()
    with ZipFile(target, "w", ZIP_DEFLATED) as archive:
        archive.writestr("notice.html", DETAIL)
    return target.getvalue()


def _compression_bomb_zip() -> bytes:
    target = BytesIO()
    with ZipFile(target, "w", ZIP_DEFLATED) as archive:
        archive.writestr(
            "notice.html",
            b"<!doctype html><html><body>" + b"A" * 200_000 + b"</body></html>",
        )
    return target.getvalue()


def _fixture_case(
    kind: ConnectorKind,
) -> tuple[dict[str, object], tuple[FixtureExchange, ...], tuple[ManualImportSubmission, ...]]:
    if kind is ConnectorKind.RSS_ATOM:
        feed = "https://feeds.example.test/road/rss.xml"
        document = "https://docs.example.test/rss-bridge-001.html"
        return (
            {
                "feed_url": feed,
                "allowed_hosts": ["feeds.example.test", "docs.example.test"],
            },
            (
                _exchange(
                    feed,
                    (CONNECTOR_FIXTURES / "rss.xml").read_bytes(),
                    "application/rss+xml",
                    etag='"rss-v1"',
                ),
                _exchange(document, DETAIL, "text/html", etag='"rss-detail-v1"'),
            ),
            (),
        )
    if kind is ConnectorKind.JSON_API:
        endpoint = "https://api.example.test/v1/notices"
        document = "https://docs.example.test/api-tunnel-001.html"
        return (
            {
                "endpoint_url": endpoint,
                "allowed_hosts": ["api.example.test", "docs.example.test"],
                "items_pointer": "/data/items",
                "field_pointers": {
                    "external_id": "/id",
                    "url": "/url",
                    "title": "/title",
                    "published_at": "/published_at",
                },
                "pagination": "NONE",
            },
            (
                _exchange(
                    endpoint,
                    (CONNECTOR_FIXTURES / "api.json").read_bytes(),
                    "application/json",
                    etag='"api-v1"',
                ),
                _exchange(document, DETAIL, "text/html", etag='"api-detail-v1"'),
            ),
            (),
        )
    if kind is ConnectorKind.SITEMAP:
        sitemap = "https://www.example.test/sitemap.xml"
        document = "https://www.example.test/sitemap-rail-001.html"
        return (
            {"sitemap_url": sitemap, "allowed_hosts": ["www.example.test"]},
            (
                _exchange(
                    sitemap,
                    (CONNECTOR_FIXTURES / "sitemap.xml").read_bytes(),
                    "application/xml",
                    etag='"sitemap-v1"',
                ),
                _exchange(document, DETAIL, "text/html", etag='"sitemap-detail-v1"'),
            ),
            (),
        )
    if kind is ConnectorKind.LIST_DETAIL:
        listing = "https://www.example.test/notices/index.html"
        document = "https://www.example.test/notices/list-rail-001.html"
        return (
            {
                "list_url": listing,
                "allowed_hosts": ["www.example.test"],
                "item_selector": "article.item",
                "link_selector": "a.detail",
                "title_selector": "h2.title",
                "published_selector": "time.published",
            },
            (
                _exchange(
                    listing,
                    (CONNECTOR_FIXTURES / "list.html").read_bytes(),
                    "text/html",
                    etag='"list-v1"',
                ),
                _exchange(document, DETAIL, "text/html", etag='"list-detail-v1"'),
            ),
            (),
        )
    if kind is ConnectorKind.DIRECT_PDF:
        document = "https://files.example.test/rules/bridge-safety.pdf"
        return (
            {"document_urls": [document], "allowed_hosts": ["files.example.test"]},
            (_exchange(document, PDF, "application/pdf", etag='"pdf-v1"'),),
            (),
        )
    if kind is ConnectorKind.MANUAL_IMPORT:
        url = "https://docs.example.test/manual-url.html"
        return (
            {
                "allowed_hosts": ["docs.example.test"],
                "url_import_enabled": True,
                "file_import_enabled": True,
                "allowed_file_types": ["HTML", "PDF", "ZIP"],
            },
            (_exchange(url, DETAIL, "text/html", etag='"manual-url-v1"'),),
            (
                ManualImportSubmission.for_url(url=url, title="人工URL导入"),
                ManualImportSubmission.for_file(
                    canonical_url="https://docs.example.test/manual-file.pdf",
                    title="人工文件导入",
                    filename="manual-file.pdf",
                    declared_mime="application/pdf",
                    content=PDF,
                ),
            ),
        )
    raise AssertionError(f"unhandled connector kind: {kind}")


@pytest.mark.parametrize("kind", list(ConnectorKind))
async def test_six_fixed_replays_share_the_evidence_contract_and_never_use_network(
    kind: ConnectorKind,
) -> None:
    config, exchanges, manual_imports = _fixture_case(kind)
    transport = FixedFixtureTransport(exchanges)
    store = InMemoryEvidenceStore()
    executor = FixedReplayExecutor(transport=transport, store=store, now=lambda: NOW)

    result = await executor.run(
        kind,
        config,
        source_allowed_hosts=tuple(config["allowed_hosts"]),
        domain=ExecutionDomain.FIXTURE,
        manual_imports=manual_imports,
    )

    expected_documents = 2 if kind is ConnectorKind.MANUAL_IMPORT else 1
    expected_raw_objects = (
        expected_documents
        if kind in {ConnectorKind.DIRECT_PDF, ConnectorKind.MANUAL_IMPORT}
        else expected_documents + 1
    )
    assert len(result.discovery_records) == expected_documents
    assert len(result.document_versions) == expected_documents
    assert len(result.raw_objects) == expected_raw_objects
    assert all(isinstance(item, DiscoveryRecord) for item in result.discovery_records)
    assert all(isinstance(item, FetchResult) for item in result.fetch_results)
    assert all(isinstance(item, RawObject) for item in result.raw_objects)
    assert all(isinstance(item, DocumentVersion) for item in result.document_versions)
    assert all(item.execution_domain is ExecutionDomain.FIXTURE for item in result.raw_objects)
    assert all(
        item.execution_domain is ExecutionDomain.FIXTURE for item in result.document_versions
    )
    assert all(len(item.content_sha256) == 64 for item in result.raw_objects)
    assert all(item.status == "READY" for item in result.document_versions)
    assert transport.real_network_calls == 0

    for version in result.document_versions:
        raw_event = ("RAW_PERSISTED", str(version.raw_object_id))
        ready_event = ("DOCUMENT_READY", str(version.raw_object_id))
        assert store.events.index(raw_event) < store.events.index(ready_event)
    if kind not in {ConnectorKind.DIRECT_PDF, ConnectorKind.MANUAL_IMPORT}:
        discovery_raw = result.raw_objects[0]
        assert store.events.index(("RAW_PERSISTED", str(discovery_raw.id))) < store.events.index(
            ("DISCOVERY_PARSED", str(discovery_raw.id))
        )


async def test_generic_list_connector_filters_links_outside_the_list_path_boundary() -> None:
    listing = "https://www.example.test/policy/"
    detail = "https://www.example.test/policy/2026/content_1001.html"
    body = (
        b"<html><body>"
        b"<a href='/other/2026/content_9999.html'>Other safety content</a>"
        b"<a href='/policy/2026/content_1001.html'>Transport safety policy update</a>"
        b"</body></html>"
    )
    config = {
        "list_url": listing,
        "allowed_hosts": ["www.example.test"],
        "item_selector": "a",
        "link_selector": "a",
        "title_selector": "a",
    }
    transport = FixedFixtureTransport(
        (
            _exchange(listing, body, "text/html", etag='"list-v1"'),
            _exchange(detail, DETAIL, "text/html", etag='"detail-v1"'),
        )
    )
    executor = FixedReplayExecutor(
        transport=transport, store=InMemoryEvidenceStore(), now=lambda: NOW
    )

    await executor.run(
        ConnectorKind.LIST_DETAIL,
        config,
        source_allowed_hosts=("www.example.test",),
        domain=ExecutionDomain.FIXTURE,
    )

    assert transport.calls == [listing, detail]


async def test_fixed_replay_is_idempotent_and_preserves_http_validators() -> None:
    config, exchanges, _ = _fixture_case(ConnectorKind.RSS_ATOM)
    store = InMemoryEvidenceStore()
    executor = FixedReplayExecutor(
        transport=FixedFixtureTransport(exchanges),
        store=store,
        now=lambda: NOW,
    )

    first = await executor.run(
        ConnectorKind.RSS_ATOM,
        config,
        source_allowed_hosts=("feeds.example.test", "docs.example.test"),
        domain=ExecutionDomain.FIXTURE,
    )
    second = await executor.run(
        ConnectorKind.RSS_ATOM,
        config,
        source_allowed_hosts=("feeds.example.test", "docs.example.test"),
        domain=ExecutionDomain.FIXTURE,
    )

    assert [item.id for item in first.raw_objects] == [item.id for item in second.raw_objects]
    assert [item.id for item in first.document_versions] == [
        item.id for item in second.document_versions
    ]
    assert first.raw_objects[0].etag == '"rss-v1"'
    assert first.raw_objects[0].last_modified == "Wed, 15 Jul 2026 06:00:00 GMT"
    assert first.discovery_records[0].published_at == datetime(2026, 7, 15, 2, tzinfo=UTC)


async def test_direct_pdf_keeps_http_last_modified_only_as_raw_validator() -> None:
    config, exchanges, _ = _fixture_case(ConnectorKind.DIRECT_PDF)
    executor = FixedReplayExecutor(
        transport=FixedFixtureTransport(exchanges),
        store=InMemoryEvidenceStore(),
        now=lambda: NOW,
    )

    result = await executor.run(
        ConnectorKind.DIRECT_PDF,
        config,
        source_allowed_hosts=("files.example.test",),
        domain=ExecutionDomain.FIXTURE,
    )

    assert result.discovery_records[0].published_at is None
    assert result.document_versions[0].published_at is None
    assert result.raw_objects[0].last_modified == "Wed, 15 Jul 2026 06:00:00 GMT"


async def test_sitemap_lastmod_is_retained_without_becoming_a_publication_time() -> None:
    config, exchanges, _ = _fixture_case(ConnectorKind.SITEMAP)
    executor = FixedReplayExecutor(
        transport=FixedFixtureTransport(exchanges),
        store=InMemoryEvidenceStore(),
        now=lambda: NOW,
    )

    result = await executor.run(
        ConnectorKind.SITEMAP,
        config,
        source_allowed_hosts=("www.example.test",),
        domain=ExecutionDomain.FIXTURE,
    )

    assert result.discovery_records[0].published_at is None
    assert result.discovery_records[0].source_modified_at == datetime(2026, 7, 15, 4, tzinfo=UTC)
    assert result.document_versions[0].published_at is None
    assert result.document_versions[0].source_modified_at == datetime(2026, 7, 15, 4, tzinfo=UTC)


async def test_atom_updated_time_is_not_mislabeled_as_publication_time() -> None:
    feed_url = "https://feeds.example.test/atom.xml"
    document_url = "https://docs.example.test/updated-only.html"
    atom = f"""<?xml version="1.0" encoding="UTF-8"?>
    <feed xmlns="http://www.w3.org/2005/Atom">
      <entry><id>updated-only</id><title>Updated only</title>
      <link href="{document_url}"/><updated>2026-07-15T06:00:00Z</updated></entry>
    </feed>""".encode()
    executor = FixedReplayExecutor(
        transport=FixedFixtureTransport(
            (
                _exchange(feed_url, atom, "application/atom+xml", etag='"atom-v1"'),
                _exchange(document_url, DETAIL, "text/html", etag='"detail-v1"'),
            )
        ),
        store=InMemoryEvidenceStore(),
        now=lambda: NOW,
    )

    result = await executor.run(
        ConnectorKind.RSS_ATOM,
        {
            "feed_url": feed_url,
            "allowed_hosts": ["feeds.example.test", "docs.example.test"],
        },
        source_allowed_hosts=("feeds.example.test", "docs.example.test"),
        domain=ExecutionDomain.FIXTURE,
    )

    assert result.discovery_records[0].published_at is None
    assert result.discovery_records[0].source_modified_at == datetime(2026, 7, 15, 6, tzinfo=UTC)


@pytest.mark.parametrize("last_modified", [None, "not-an-http-date"])
async def test_direct_pdf_does_not_guess_time_when_last_modified_is_unusable(
    last_modified: str | None,
) -> None:
    config, exchanges, _ = _fixture_case(ConnectorKind.DIRECT_PDF)
    headers = dict(exchanges[0].headers)
    if last_modified is None:
        headers.pop("Last-Modified")
    else:
        headers["Last-Modified"] = last_modified
    exchange = FixtureExchange(
        url=exchanges[0].url,
        status_code=200,
        headers=headers,
        content=exchanges[0].content,
    )
    executor = FixedReplayExecutor(
        transport=FixedFixtureTransport((exchange,)),
        store=InMemoryEvidenceStore(),
        now=lambda: NOW,
    )

    result = await executor.run(
        ConnectorKind.DIRECT_PDF,
        config,
        source_allowed_hosts=("files.example.test",),
        domain=ExecutionDomain.FIXTURE,
    )

    assert result.document_versions[0].published_at is None


async def test_raw_is_persisted_before_parse_failure_and_existing_ready_is_not_replaced() -> None:
    config, exchanges, _ = _fixture_case(ConnectorKind.RSS_ATOM)
    store = InMemoryEvidenceStore()
    good = FixedReplayExecutor(
        transport=FixedFixtureTransport(exchanges),
        store=store,
        now=lambda: NOW,
    )
    ready = await good.run(
        ConnectorKind.RSS_ATOM,
        config,
        source_allowed_hosts=("feeds.example.test", "docs.example.test"),
        domain=ExecutionDomain.FIXTURE,
    )
    current_before = store.current_ready(
        ExecutionDomain.FIXTURE,
        ready.discovery_records[0].url,
    )

    broken_exchanges = (
        exchanges[0],
        _exchange(
            ready.discovery_records[0].url,
            b"this is not html",
            "text/html",
            etag='"broken-v2"',
        ),
    )
    broken = FixedReplayExecutor(
        transport=FixedFixtureTransport(broken_exchanges),
        store=store,
        now=lambda: NOW,
    )

    with pytest.raises(ConnectorParseFailed, match="document bytes"):
        await broken.run(
            ConnectorKind.RSS_ATOM,
            config,
            source_allowed_hosts=("feeds.example.test", "docs.example.test"),
            domain=ExecutionDomain.FIXTURE,
        )

    assert store.events[-2][0] == "RAW_PERSISTED"
    assert store.events[-1][0] == "PARSE_FAILED"
    failed_raw_id = UUID(store.events[-1][1])
    assert store.read_raw_bytes(failed_raw_id) == b"this is not html"
    assert store.parse_failure_reason(failed_raw_id) is not None
    assert (
        store.current_ready(ExecutionDomain.FIXTURE, ready.discovery_records[0].url)
        == current_before
    )


async def test_malformed_discovery_is_retained_as_raw_before_failure() -> None:
    config, exchanges, _ = _fixture_case(ConnectorKind.RSS_ATOM)
    malformed = _exchange(
        exchanges[0].url,
        b"<rss><channel><item>",
        "application/rss+xml",
        etag='"malformed"',
    )
    store = InMemoryEvidenceStore()
    executor = FixedReplayExecutor(
        transport=FixedFixtureTransport((malformed,)),
        store=store,
        now=lambda: NOW,
    )

    with pytest.raises(ConnectorParseFailed, match="discovery response"):
        await executor.run(
            ConnectorKind.RSS_ATOM,
            config,
            source_allowed_hosts=("feeds.example.test", "docs.example.test"),
            domain=ExecutionDomain.FIXTURE,
        )

    assert [event[0] for event in store.events] == ["RAW_PERSISTED", "PARSE_FAILED"]
    raw_id = UUID(store.events[-1][1])
    assert store.read_raw_bytes(raw_id) == b"<rss><channel><item>"
    assert store.parse_failure_reason(raw_id) == "DISCOVERY_PARSE_FAILED"


async def test_trial_and_production_evidence_are_isolated_by_execution_domain() -> None:
    store = InMemoryEvidenceStore()
    service = RawFirstIngestionService(store=store)
    record = DiscoveryRecord(
        external_id="same-evidence",
        url="https://docs.example.test/same.html",
        title="同字节域隔离",
        published_at=NOW,
        discovered_at=NOW,
    )
    fetched = FetchResult(
        url=record.url,
        status_code=200,
        content=DETAIL,
        content_type="text/html",
        etag='"same"',
        last_modified=None,
        fetched_at=NOW,
    )

    trial = await service.ingest_document(fetched, record, domain=ExecutionDomain.TRIAL)
    production = await service.ingest_document(
        fetched,
        record,
        domain=ExecutionDomain.PRODUCTION,
    )

    assert trial.raw_object.id != production.raw_object.id
    assert trial.document_version.id != production.document_version.id
    assert trial.raw_object.execution_domain is ExecutionDomain.TRIAL
    assert production.raw_object.execution_domain is ExecutionDomain.PRODUCTION


async def test_fixture_transport_can_never_be_used_as_production_authorization() -> None:
    config, exchanges, _ = _fixture_case(ConnectorKind.DIRECT_PDF)
    executor = FixedReplayExecutor(
        transport=FixedFixtureTransport(exchanges),
        store=InMemoryEvidenceStore(),
        now=lambda: NOW,
    )

    with pytest.raises(FixtureProductionDenied):
        await executor.run(
            ConnectorKind.DIRECT_PDF,
            config,
            source_allowed_hosts=("files.example.test",),
            domain=ExecutionDomain.PRODUCTION,
        )


def test_configuration_preview_is_pure_and_does_not_create_a_run_or_touch_transport() -> None:
    config, exchanges, _ = _fixture_case(ConnectorKind.RSS_ATOM)
    transport = FixedFixtureTransport(exchanges)
    store = InMemoryEvidenceStore()
    executor = FixedReplayExecutor(transport=transport, store=store, now=lambda: NOW)

    preview = executor.preview(
        ConnectorKind.RSS_ATOM,
        config,
        source_allowed_hosts=("feeds.example.test", "docs.example.test"),
    )

    assert preview["network_io_performed"] is False
    assert transport.calls == []
    assert store.events == []


@pytest.mark.parametrize("kind", list(ConnectorKind))
def test_each_declarative_replay_uses_the_canonical_source_adapter_protocol(
    kind: ConnectorKind,
) -> None:
    config, exchanges, manual_imports = _fixture_case(kind)
    executor = FixedReplayExecutor(
        transport=FixedFixtureTransport(exchanges),
        store=InMemoryEvidenceStore(),
        now=lambda: NOW,
    )

    adapter = executor.adapter(
        kind,
        config,
        source_allowed_hosts=tuple(config["allowed_hosts"]),
        manual_imports=manual_imports,
    )

    assert isinstance(adapter, SourceAdapter)


async def test_manual_zip_import_is_validated_and_replayed() -> None:
    config, _, _ = _fixture_case(ConnectorKind.MANUAL_IMPORT)
    submission = ManualImportSubmission.for_file(
        canonical_url="https://docs.example.test/manual-safe.zip",
        title="人工ZIP导入",
        filename="manual-safe.zip",
        declared_mime="application/zip",
        content=_safe_zip(),
    )
    executor = FixedReplayExecutor(
        transport=FixedFixtureTransport(()),
        store=InMemoryEvidenceStore(),
        now=lambda: NOW,
    )

    result = await executor.run(
        ConnectorKind.MANUAL_IMPORT,
        config,
        source_allowed_hosts=("docs.example.test",),
        domain=ExecutionDomain.FIXTURE,
        manual_imports=(submission,),
    )

    assert result.document_versions[0].status == "READY"


async def test_raw_idempotency_key_keeps_distinct_redirect_origins_separate() -> None:
    store = InMemoryEvidenceStore()
    first = FetchResult(
        url="https://docs.example.test/final.html",
        request_url="https://docs.example.test/first",
        redirect_chain=("https://docs.example.test/final.html",),
        status_code=200,
        content=DETAIL,
        content_type="text/html",
        etag='"same"',
        last_modified=None,
        fetched_at=NOW,
    )
    second = FetchResult(
        url=first.url,
        request_url="https://docs.example.test/second",
        redirect_chain=first.redirect_chain,
        status_code=first.status_code,
        content=first.content,
        content_type=first.content_type,
        etag=first.etag,
        last_modified=first.last_modified,
        fetched_at=NOW,
    )

    first_raw = await store.persist_raw(first, ExecutionDomain.TRIAL)
    second_raw = await store.persist_raw(second, ExecutionDomain.TRIAL)

    assert first_raw.id != second_raw.id


async def test_raw_bytes_are_immutable_when_a_response_hash_is_reused() -> None:
    store = InMemoryEvidenceStore()
    first = FetchResult(
        url="https://docs.example.test/evidence.json",
        status_code=200,
        content=b'{"version":1}',
        content_type="application/json",
        etag='"same"',
        last_modified=None,
        fetched_at=NOW,
        response_sha256="a" * 64,
    )
    first_raw = await store.persist_raw(first, ExecutionDomain.TRIAL)
    conflicting = FetchResult(
        url=first.url,
        status_code=first.status_code,
        content=b'{"version":2}',
        content_type=first.content_type,
        etag=first.etag,
        last_modified=first.last_modified,
        fetched_at=NOW,
        response_sha256=first.response_sha256,
    )

    with pytest.raises(ValueError, match="idempotency collision"):
        await store.persist_raw(conflicting, ExecutionDomain.TRIAL)

    assert store.read_raw_bytes(first_raw.id) == b'{"version":1}'


def _oversized_discovery(kind: ConnectorKind) -> tuple[bytes, str]:
    count = MAX_DISCOVERY_RECORDS + 1
    if kind is ConnectorKind.RSS_ATOM:
        items = "".join(
            f"<item><guid>{index}</guid><title>item</title>"
            f"<link>https://docs.example.test/{index}.html</link></item>"
            for index in range(count)
        )
        return f"<rss><channel>{items}</channel></rss>".encode(), "application/rss+xml"
    if kind is ConnectorKind.JSON_API:
        items = [
            {
                "id": str(index),
                "title": "item",
                "url": f"https://docs.example.test/{index}.html",
            }
            for index in range(count)
        ]
        return json.dumps({"data": {"items": items}}).encode(), "application/json"
    if kind is ConnectorKind.SITEMAP:
        items = "".join(
            f"<url><loc>https://www.example.test/{index}.html</loc></url>" for index in range(count)
        )
        return f"<urlset>{items}</urlset>".encode(), "application/xml"
    if kind is ConnectorKind.LIST_DETAIL:
        items = "".join(
            f'<article class="item"><h2 class="title">item</h2>'
            f'<a class="detail" href="/{index}.html">detail</a></article>'
            for index in range(count)
        )
        return f"<!doctype html><html>{items}</html>".encode(), "text/html"
    raise AssertionError("connector does not parse a discovery response")


@pytest.mark.parametrize(
    "kind",
    [
        ConnectorKind.RSS_ATOM,
        ConnectorKind.JSON_API,
        ConnectorKind.SITEMAP,
        ConnectorKind.LIST_DETAIL,
    ],
)
async def test_discovery_record_limits_fail_after_raw_is_persisted(kind: ConnectorKind) -> None:
    config, exchanges, _ = _fixture_case(kind)
    content, content_type = _oversized_discovery(kind)
    oversized = _exchange(
        exchanges[0].url,
        content,
        content_type,
        etag='"oversized"',
    )
    store = InMemoryEvidenceStore()
    executor = FixedReplayExecutor(
        transport=FixedFixtureTransport((oversized,)),
        store=store,
        now=lambda: NOW,
    )

    with pytest.raises(ConnectorParseFailed, match="discovery response"):
        await executor.run(
            kind,
            config,
            source_allowed_hosts=tuple(config["allowed_hosts"]),
            domain=ExecutionDomain.FIXTURE,
        )

    assert [event[0] for event in store.events] == ["RAW_PERSISTED", "PARSE_FAILED"]


@pytest.mark.parametrize(
    "unsafe_xml",
    [
        b'<!DOCTYPE rss [<!ENTITY x "boom">]><rss><channel>&x;</channel></rss>',
        b"<!ENTITY x SYSTEM 'file:///etc/passwd'><rss/>",
        b" " * 131_073
        + (
            b'<!DOCTYPE rss [<!ENTITY unused "boom">]><rss><channel><item>'
            b"<guid>unsafe-dtd</guid><title>must not parse</title>"
            b"<link>https://docs.example.test/unsafe-dtd.html</link>"
            b"</item></channel></rss>"
        ),
        (
            '<?xml version="1.0" encoding="utf-16"?>'
            '<!DOCTYPE rss [<!ENTITY unused "boom">]><rss><channel><item>'
            "<guid>unsafe-utf16</guid><title>must not parse</title>"
            "<link>https://docs.example.test/unsafe-utf16.html</link>"
            "</item></channel></rss>"
        ).encode("utf-16"),
    ],
    ids=["ascii-entity", "orphan-entity", "late-dtd", "utf16-dtd"],
)
async def test_xml_dtd_and_entities_fail_after_raw_is_persisted(unsafe_xml: bytes) -> None:
    config, exchanges, _ = _fixture_case(ConnectorKind.RSS_ATOM)
    exchange = _exchange(
        exchanges[0].url,
        unsafe_xml,
        "application/rss+xml",
        etag='"entity"',
    )
    store = InMemoryEvidenceStore()
    executor = FixedReplayExecutor(
        transport=FixedFixtureTransport((exchange,)),
        store=store,
        now=lambda: NOW,
    )

    with pytest.raises(ConnectorParseFailed):
        await executor.run(
            ConnectorKind.RSS_ATOM,
            config,
            source_allowed_hosts=("feeds.example.test", "docs.example.test"),
            domain=ExecutionDomain.FIXTURE,
        )

    assert [event[0] for event in store.events] == ["RAW_PERSISTED", "PARSE_FAILED"]
    raw_id = UUID(store.events[-1][1])
    assert store.read_raw_bytes(raw_id) == unsafe_xml
    assert store.parse_failure_reason(raw_id) == "DISCOVERY_PARSE_FAILED"
    assert (
        store.current_ready(
            ExecutionDomain.FIXTURE,
            "https://docs.example.test/unsafe-utf16.html",
        )
        is None
    )


async def test_json_recursion_error_is_converted_to_a_bounded_parse_failure() -> None:
    config, exchanges, _ = _fixture_case(ConnectorKind.JSON_API)
    deeply_nested = b"[" * 5_000 + b"0" + b"]" * 5_000
    exchange = _exchange(
        exchanges[0].url,
        deeply_nested,
        "application/json",
        etag='"deeply-nested"',
    )
    store = InMemoryEvidenceStore()
    executor = FixedReplayExecutor(
        transport=FixedFixtureTransport((exchange,)),
        store=store,
        now=lambda: NOW,
    )

    with pytest.raises(ConnectorParseFailed, match="discovery response"):
        await executor.run(
            ConnectorKind.JSON_API,
            config,
            source_allowed_hosts=("api.example.test", "docs.example.test"),
            domain=ExecutionDomain.FIXTURE,
        )

    raw_id = UUID(store.events[-1][1])
    assert store.read_raw_bytes(raw_id) == deeply_nested
    assert store.parse_failure_reason(raw_id) == "DISCOVERY_PARSE_FAILED"


async def test_json_oversized_integer_is_converted_to_a_stable_parse_failure() -> None:
    config, exchanges, _ = _fixture_case(ConnectorKind.JSON_API)
    oversized_integer = (
        b'{"data":{"items":[{"id":'
        + b"9" * 5_000
        + b',"title":"item","url":"https://docs.example.test/item.html"}]}}'
    )
    exchange = _exchange(
        exchanges[0].url,
        oversized_integer,
        "application/json",
        etag='"oversized-integer"',
    )
    store = InMemoryEvidenceStore()
    executor = FixedReplayExecutor(
        transport=FixedFixtureTransport((exchange,)),
        store=store,
        now=lambda: NOW,
    )

    with pytest.raises(ConnectorParseFailed, match="discovery response"):
        await executor.run(
            ConnectorKind.JSON_API,
            config,
            source_allowed_hosts=("api.example.test", "docs.example.test"),
            domain=ExecutionDomain.FIXTURE,
        )

    assert [event[0] for event in store.events] == ["RAW_PERSISTED", "PARSE_FAILED"]
    raw_id = UUID(store.events[-1][1])
    assert store.read_raw_bytes(raw_id) == oversized_integer
    assert store.parse_failure_reason(raw_id) == "DISCOVERY_PARSE_FAILED"


async def test_runtime_discovery_allowlist_failure_is_a_retained_security_failure() -> None:
    config, exchanges, _ = _fixture_case(ConnectorKind.RSS_ATOM)
    store = InMemoryEvidenceStore()
    good = FixedReplayExecutor(
        transport=FixedFixtureTransport(exchanges),
        store=store,
        now=lambda: NOW,
    )
    ready = await good.run(
        ConnectorKind.RSS_ATOM,
        config,
        source_allowed_hosts=("feeds.example.test", "docs.example.test"),
        domain=ExecutionDomain.FIXTURE,
    )
    canonical_url = ready.discovery_records[0].url
    current_before = store.current_ready(ExecutionDomain.FIXTURE, canonical_url)
    unsafe_feed = (
        b"<rss><channel><item><guid>outside-allowlist</guid>"
        b"<title>outside allowlist</title>"
        b"<link>https://outside.example.test/item.html</link>"
        b"</item></channel></rss>"
    )
    unsafe = FixedReplayExecutor(
        transport=FixedFixtureTransport(
            (
                _exchange(
                    exchanges[0].url,
                    unsafe_feed,
                    "application/rss+xml",
                    etag='"outside-allowlist"',
                ),
            )
        ),
        store=store,
        now=lambda: NOW,
    )

    with pytest.raises(ConnectorParseFailed, match="discovery target"):
        await unsafe.run(
            ConnectorKind.RSS_ATOM,
            config,
            source_allowed_hosts=("feeds.example.test", "docs.example.test"),
            domain=ExecutionDomain.FIXTURE,
        )

    assert [event[0] for event in store.events[-2:]] == ["RAW_PERSISTED", "PARSE_FAILED"]
    raw_id = UUID(store.events[-1][1])
    assert store.read_raw_bytes(raw_id) == unsafe_feed
    assert store.parse_failure_reason(raw_id) == "DISCOVERY_SECURITY_FAILED"
    assert store.current_ready(ExecutionDomain.FIXTURE, canonical_url) == current_before


@pytest.mark.parametrize(
    ("filename", "declared_mime", "content"),
    [
        ("manual-file.txt", "application/pdf", PDF),
        ("manual-file.pdf", "text/html", PDF),
        ("manual-file.pdf", "application/pdf", b""),
        (
            "manual-file.html",
            "text/html",
            b"<!doctype html><html><script>alert(1)</script></html>",
        ),
        ("manual-file.zip", "application/zip", _compression_bomb_zip()),
    ],
    ids=["wrong-extension", "mime-mismatch", "empty", "active-content", "zip-bomb"],
)
async def test_manual_file_uses_submitted_name_mime_and_bytes_for_bounded_validation(
    filename: str,
    declared_mime: str,
    content: bytes,
) -> None:
    config, _, _ = _fixture_case(ConnectorKind.MANUAL_IMPORT)
    canonical_url = "https://docs.example.test/manual-file.pdf"
    submission = ManualImportSubmission.for_file(
        canonical_url=canonical_url,
        title="unsafe manual file",
        filename=filename,
        declared_mime=declared_mime,
        content=content,
    )
    store = InMemoryEvidenceStore()
    executor = FixedReplayExecutor(
        transport=FixedFixtureTransport(()),
        store=store,
        now=lambda: NOW,
    )

    with pytest.raises(ConnectorParseFailed, match="document bytes"):
        await executor.run(
            ConnectorKind.MANUAL_IMPORT,
            config,
            source_allowed_hosts=("docs.example.test",),
            domain=ExecutionDomain.FIXTURE,
            manual_imports=(submission,),
        )

    assert [event[0] for event in store.events] == ["RAW_PERSISTED", "PARSE_FAILED"]
    raw_id = UUID(store.events[-1][1])
    assert store.read_raw_bytes(raw_id) == content
    assert store.parse_failure_reason(raw_id) is not None
    assert store.current_ready(ExecutionDomain.FIXTURE, canonical_url) is None


async def test_manual_file_size_limit_uses_the_same_raw_first_validation_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config, _, _ = _fixture_case(ConnectorKind.MANUAL_IMPORT)
    monkeypatch.setattr(
        connector_replay,
        "_FILE_POLICY",
        replace(connector_replay._FILE_POLICY, max_file_bytes=32),
    )
    content = PDF[:64]
    canonical_url = "https://docs.example.test/manual-oversized.pdf"
    submission = ManualImportSubmission.for_file(
        canonical_url=canonical_url,
        title="oversized manual file",
        filename="actual-upload.pdf",
        declared_mime="application/pdf",
        content=content,
    )
    store = InMemoryEvidenceStore()
    executor = FixedReplayExecutor(
        transport=FixedFixtureTransport(()),
        store=store,
        now=lambda: NOW,
    )

    with pytest.raises(ConnectorParseFailed, match="document bytes"):
        await executor.run(
            ConnectorKind.MANUAL_IMPORT,
            config,
            source_allowed_hosts=("docs.example.test",),
            domain=ExecutionDomain.FIXTURE,
            manual_imports=(submission,),
        )

    raw_id = UUID(store.events[-1][1])
    assert store.read_raw_bytes(raw_id) == content
    assert store.parse_failure_reason(raw_id) == "FILE_SIZE_LIMIT"
    assert store.current_ready(ExecutionDomain.FIXTURE, canonical_url) is None


def _overlong_field_discovery(kind: ConnectorKind) -> tuple[bytes, str]:
    overlong_title = "x" * (MAX_DISCOVERY_TITLE_LENGTH + 1)
    if kind is ConnectorKind.RSS_ATOM:
        return (
            (
                "<rss><channel><item><guid>item-1</guid>"
                f"<title>{overlong_title}</title>"
                "<link>https://docs.example.test/item-1.html</link>"
                "</item></channel></rss>"
            ).encode(),
            "application/rss+xml",
        )
    if kind is ConnectorKind.JSON_API:
        return (
            json.dumps(
                {
                    "data": {
                        "items": [
                            {
                                "id": "item-1",
                                "title": overlong_title,
                                "url": "https://docs.example.test/item-1.html",
                            }
                        ]
                    }
                }
            ).encode(),
            "application/json",
        )
    if kind is ConnectorKind.SITEMAP:
        overlong_url = "https://www.example.test/" + "x" * MAX_DISCOVERY_URL_LENGTH
        return (
            f"<urlset><url><loc>{overlong_url}</loc></url></urlset>".encode(),
            "application/xml",
        )
    if kind is ConnectorKind.LIST_DETAIL:
        return (
            (
                '<!doctype html><article class="item">'
                f'<h2 class="title">{overlong_title}</h2>'
                '<a class="detail" href="/item-1.html">detail</a>'
                "</article>"
            ).encode(),
            "text/html",
        )
    raise AssertionError("connector does not parse a discovery response")


@pytest.mark.parametrize(
    "kind",
    [
        ConnectorKind.RSS_ATOM,
        ConnectorKind.JSON_API,
        ConnectorKind.SITEMAP,
        ConnectorKind.LIST_DETAIL,
    ],
)
async def test_discovery_fields_have_uniform_length_limits(kind: ConnectorKind) -> None:
    config, exchanges, _ = _fixture_case(kind)
    content, content_type = _overlong_field_discovery(kind)
    exchange = _exchange(
        exchanges[0].url,
        content,
        content_type,
        etag='"overlong-field"',
    )
    store = InMemoryEvidenceStore()
    executor = FixedReplayExecutor(
        transport=FixedFixtureTransport((exchange,)),
        store=store,
        now=lambda: NOW,
    )

    with pytest.raises(ConnectorParseFailed, match="discovery response"):
        await executor.run(
            kind,
            config,
            source_allowed_hosts=tuple(config["allowed_hosts"]),
            domain=ExecutionDomain.FIXTURE,
        )

    assert store.parse_failure_reason(UUID(store.events[-1][1])) == ("DISCOVERY_PARSE_FAILED")


async def test_list_discovery_response_has_a_byte_limit() -> None:
    config, exchanges, _ = _fixture_case(ConnectorKind.LIST_DETAIL)
    oversized = b" " * (MAX_DISCOVERY_BYTES + 1)
    exchange = _exchange(
        exchanges[0].url,
        oversized,
        "text/html",
        etag='"oversized-list"',
    )
    store = InMemoryEvidenceStore()
    executor = FixedReplayExecutor(
        transport=FixedFixtureTransport((exchange,)),
        store=store,
        now=lambda: NOW,
    )

    with pytest.raises(ConnectorParseFailed, match="discovery response"):
        await executor.run(
            ConnectorKind.LIST_DETAIL,
            config,
            source_allowed_hosts=("www.example.test",),
            domain=ExecutionDomain.FIXTURE,
        )

    raw_id = UUID(store.events[-1][1])
    assert len(store.read_raw_bytes(raw_id)) == MAX_DISCOVERY_BYTES + 1
    assert store.parse_failure_reason(raw_id) == "DISCOVERY_PARSE_FAILED"


@pytest.mark.parametrize(
    ("unsafe_pdf", "failure_reason"),
    [
        (PDF.replace(b"%%EOF", b"/JavaScript 9 0 R\n%%EOF"), "PDF_ACTIVE_ACTION"),
        (PDF.replace(b"%%EOF", b"/Encrypt 9 0 R\n%%EOF"), "PDF_ENCRYPTED"),
        (PDF + b"PK\x03\x04hidden-archive", "PDF_POLYGLOT"),
    ],
)
async def test_zip_with_unsafe_pdf_never_creates_a_ready_version(
    unsafe_pdf: bytes,
    failure_reason: str,
) -> None:
    config, _, _ = _fixture_case(ConnectorKind.MANUAL_IMPORT)
    target = BytesIO()
    with ZipFile(target, "w", ZIP_DEFLATED) as archive:
        archive.writestr("attachments/unsafe.pdf", unsafe_pdf)
    unsafe_zip = target.getvalue()
    canonical_url = "https://docs.example.test/manual-active-pdf.zip"
    submission = ManualImportSubmission.for_file(
        canonical_url=canonical_url,
        title="unsafe PDF archive",
        filename="manual-active-pdf.zip",
        declared_mime="application/zip",
        content=unsafe_zip,
    )
    store = InMemoryEvidenceStore()
    executor = FixedReplayExecutor(
        transport=FixedFixtureTransport(()),
        store=store,
        now=lambda: NOW,
    )

    with pytest.raises(ConnectorParseFailed, match="document bytes"):
        await executor.run(
            ConnectorKind.MANUAL_IMPORT,
            config,
            source_allowed_hosts=("docs.example.test",),
            domain=ExecutionDomain.FIXTURE,
            manual_imports=(submission,),
        )

    raw_id = UUID(store.events[-1][1])
    assert store.read_raw_bytes(raw_id) == unsafe_zip
    assert store.parse_failure_reason(raw_id) == failure_reason
    assert store.current_ready(ExecutionDomain.FIXTURE, canonical_url) is None
