"""Strict, versioned schemas for declarative source connectors."""

from __future__ import annotations

import ipaddress
import json
import re
from copy import deepcopy
from dataclasses import dataclass
from enum import StrEnum
from hashlib import sha256
from urllib.parse import unquote, urlsplit, urlunsplit

from jsonschema import Draft202012Validator


class ConnectorKind(StrEnum):
    RSS_ATOM = "RSS_ATOM"
    JSON_API = "JSON_API"
    SITEMAP = "SITEMAP"
    LIST_DETAIL = "LIST_DETAIL"
    DIRECT_PDF = "DIRECT_PDF"
    MANUAL_IMPORT = "MANUAL_IMPORT"


class ConnectorConfigRejected(ValueError):
    """A content-free validation error safe to return from an admin API."""


@dataclass(frozen=True, slots=True)
class ConnectorDefinition:
    kind: ConnectorKind
    definition_version: str
    schema_version: str
    executor_key: str
    capabilities: tuple[str, ...]
    schema: dict[str, object]

    @property
    def schema_sha256(self) -> str:
        canonical = json.dumps(
            self.schema,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return sha256(canonical).hexdigest()


@dataclass(frozen=True, slots=True)
class ValidatedConnectorConfig:
    kind: ConnectorKind
    definition_version: str
    schema_version: str
    schema_sha256: str
    _document_json: str

    @property
    def document(self) -> dict[str, object]:
        value: object = json.loads(self._document_json)
        if not isinstance(value, dict):
            raise RuntimeError("validated connector configuration is not an object")
        return value


_SCHEMA_URI = "https://json-schema.org/draft/2020-12/schema"
_CREDENTIAL_PATTERN = r"^vault://source-connectors/[A-Za-z0-9][A-Za-z0-9/_-]{0,190}$"
_HOST_PATTERN = r"^(?=.{1,253}$)(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,63}$"
_SELECTOR_PATTERN = re.compile(
    r"^(?:[a-z][a-z0-9-]*)?(?:[.#][A-Za-z_][A-Za-z0-9_-]*)?$"
)
_EXPRESSION_MARKERS = ("{{", "}}", "{%", "%}", "${", "<%", "%>")
_METADATA_ADDRESSES = {
    ipaddress.ip_address("168.63.129.16"),
    ipaddress.ip_address("169.254.169.254"),
    ipaddress.ip_address("169.254.170.2"),
    ipaddress.ip_address("100.100.100.200"),
    ipaddress.ip_address("192.0.0.192"),
}


def _common_properties() -> dict[str, object]:
    return {
        "allowed_hosts": {
            "type": "array",
            "minItems": 1,
            "maxItems": 32,
            "uniqueItems": True,
            "items": {"type": "string", "minLength": 1, "maxLength": 253},
        },
        "credential_ref": {
            "type": "string",
            "pattern": _CREDENTIAL_PATTERN,
            "maxLength": 220,
        },
    }


def _object_schema(
    *,
    properties: dict[str, object],
    required: tuple[str, ...],
    all_of: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    schema: dict[str, object] = {
        "$schema": _SCHEMA_URI,
        "type": "object",
        "additionalProperties": False,
        "properties": _common_properties() | properties,
        "required": ["allowed_hosts", *required],
    }
    if all_of:
        schema["allOf"] = all_of
    return schema


def _url_property() -> dict[str, object]:
    return {"type": "string", "minLength": 8, "maxLength": 2048}


def _selector_property() -> dict[str, object]:
    return {"type": "string", "minLength": 1, "maxLength": 100}


def _pointer_property() -> dict[str, object]:
    return {"type": "string", "minLength": 1, "maxLength": 300}


def _definition(
    kind: ConnectorKind,
    schema: dict[str, object],
    capabilities: tuple[str, ...],
) -> ConnectorDefinition:
    schema["$id"] = f"https://schemas.srbg.local/connectors/{kind.value.lower()}/1.0.0"
    return ConnectorDefinition(
        kind=kind,
        definition_version="1.0.0",
        schema_version="2020-12",
        executor_key=f"builtin:{kind.value.lower()}:v1",
        capabilities=capabilities,
        schema=schema,
    )


CONNECTOR_DEFINITIONS: dict[ConnectorKind, ConnectorDefinition] = {
    ConnectorKind.RSS_ATOM: _definition(
        ConnectorKind.RSS_ATOM,
        _object_schema(
            properties={"feed_url": _url_property()},
            required=("feed_url",),
        ),
        ("DISCOVERY", "FETCH"),
    ),
    ConnectorKind.JSON_API: _definition(
        ConnectorKind.JSON_API,
        _object_schema(
            properties={
                "endpoint_url": _url_property(),
                "items_pointer": _pointer_property(),
                "field_pointers": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "external_id": _pointer_property(),
                        "url": _pointer_property(),
                        "title": _pointer_property(),
                        "published_at": _pointer_property(),
                    },
                    "required": ["external_id", "url", "title"],
                },
                "pagination": {"const": "NONE"},
            },
            required=("endpoint_url", "items_pointer", "field_pointers", "pagination"),
        ),
        ("DISCOVERY", "FETCH"),
    ),
    ConnectorKind.SITEMAP: _definition(
        ConnectorKind.SITEMAP,
        _object_schema(
            properties={"sitemap_url": _url_property()},
            required=("sitemap_url",),
        ),
        ("DISCOVERY", "FETCH"),
    ),
    ConnectorKind.LIST_DETAIL: _definition(
        ConnectorKind.LIST_DETAIL,
        _object_schema(
            properties={
                "list_url": _url_property(),
                "item_selector": _selector_property(),
                "link_selector": _selector_property(),
                "title_selector": _selector_property(),
                "published_selector": _selector_property(),
            },
            required=("list_url", "item_selector", "link_selector", "title_selector"),
        ),
        ("DISCOVERY", "FETCH"),
    ),
    ConnectorKind.DIRECT_PDF: _definition(
        ConnectorKind.DIRECT_PDF,
        _object_schema(
            properties={
                "document_urls": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": 100,
                    "uniqueItems": True,
                    "items": _url_property(),
                }
            },
            required=("document_urls",),
        ),
        ("DIRECT_FETCH", "PDF"),
    ),
    ConnectorKind.MANUAL_IMPORT: _definition(
        ConnectorKind.MANUAL_IMPORT,
        _object_schema(
            properties={
                "url_import_enabled": {"type": "boolean"},
                "file_import_enabled": {"type": "boolean"},
                "allowed_file_types": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": 3,
                    "uniqueItems": True,
                    "items": {"enum": ["HTML", "PDF", "ZIP"]},
                },
            },
            required=("url_import_enabled", "file_import_enabled", "allowed_file_types"),
            all_of=[
                {
                    "anyOf": [
                        {"properties": {"url_import_enabled": {"const": True}}},
                        {"properties": {"file_import_enabled": {"const": True}}},
                    ]
                }
            ],
        ),
        ("MANUAL_URL", "MANUAL_FILE"),
    ),
}


def validate_connector_config(
    kind: ConnectorKind,
    document: object,
    *,
    source_allowed_hosts: tuple[str, ...],
) -> ValidatedConnectorConfig:
    """Validate and normalize config without evaluating it or performing I/O."""

    definition = CONNECTOR_DEFINITIONS[kind]
    errors = sorted(
        Draft202012Validator(definition.schema).iter_errors(document),
        key=lambda error: tuple(str(part) for part in error.absolute_path),
    )
    if errors:
        path = "/".join(str(part) for part in errors[0].absolute_path) or "root"
        raise ConnectorConfigRejected(
            f"connector configuration failed schema validation at {path}"
        )
    if not isinstance(document, dict):
        raise ConnectorConfigRejected("connector configuration must be an object")
    normalized = deepcopy(document)
    _reject_expressions(normalized)
    allowed_hosts = _normalize_allowed_hosts(normalized.get("allowed_hosts"))
    source_hosts = _normalize_allowed_hosts(list(source_allowed_hosts))
    if not set(allowed_hosts).issubset(source_hosts):
        raise ConnectorConfigRejected("connector allowed hosts exceed the source policy")
    normalized["allowed_hosts"] = list(allowed_hosts)
    for field_name, urls in _configured_url_fields(kind, normalized):
        normalized_urls = [_normalize_and_validate_url(url, allowed_hosts) for url in urls]
        normalized[field_name] = (
            normalized_urls
            if isinstance(normalized[field_name], list)
            else normalized_urls[0]
        )
    if kind is ConnectorKind.LIST_DETAIL:
        for field in (
            "item_selector",
            "link_selector",
            "title_selector",
            "published_selector",
        ):
            value = normalized.get(field)
            if value is not None and (
                not isinstance(value, str)
                or _SELECTOR_PATTERN.fullmatch(value) is None
                or not value
            ):
                raise ConnectorConfigRejected(f"unsupported declarative selector: {field}")
    if kind is ConnectorKind.JSON_API:
        pointer_values = [normalized.get("items_pointer")]
        field_pointers = normalized.get("field_pointers")
        if isinstance(field_pointers, dict):
            pointer_values.extend(field_pointers.values())
        if any(value is not None and not _is_json_pointer(value) for value in pointer_values):
            raise ConnectorConfigRejected("only RFC 6901 JSON pointer fields are allowed")
    canonical = json.dumps(
        normalized,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return ValidatedConnectorConfig(
        kind=kind,
        definition_version=definition.definition_version,
        schema_version=definition.schema_version,
        schema_sha256=definition.schema_sha256,
        _document_json=canonical,
    )


def preview_connector_config(
    kind: ConnectorKind,
    document: object,
    *,
    source_allowed_hosts: tuple[str, ...],
) -> dict[str, object]:
    validated = validate_connector_config(
        kind,
        document,
        source_allowed_hosts=source_allowed_hosts,
    )
    redacted = validated.document
    if "credential_ref" in redacted:
        redacted["credential_ref"] = "[configured]"
    return {
        "connector_type": kind.value,
        "definition_version": validated.definition_version,
        "schema_version": validated.schema_version,
        "schema_sha256": validated.schema_sha256,
        "config": redacted,
        "network_io_performed": False,
    }


def validate_runtime_url(url: str, *, allowed_hosts: tuple[str, ...]) -> str:
    """Validate a discovered/manual URL against the already-approved exact hosts."""

    normalized_hosts = _normalize_allowed_hosts(list(allowed_hosts))
    return _normalize_and_validate_url(url, normalized_hosts)


def _normalize_allowed_hosts(value: object) -> tuple[str, ...]:
    if not isinstance(value, list) or not value:
        raise ConnectorConfigRejected("at least one exact allowed host is required")
    normalized: list[str] = []
    for host in value:
        if not isinstance(host, str):
            raise ConnectorConfigRejected("allowed host must be a DNS name")
        candidate = host.rstrip(".").casefold()
        if (
            not candidate
            or "*" in candidate
            or _contains_expression(candidate)
            or re.fullmatch(_HOST_PATTERN, candidate) is None
        ):
            raise ConnectorConfigRejected("allowed host must be an exact DNS name")
        try:
            ipaddress.ip_address(candidate)
        except ValueError:
            pass
        else:
            raise ConnectorConfigRejected("allowed host cannot be an IP literal")
        if candidate in normalized:
            raise ConnectorConfigRejected("allowed hosts must be unique after normalization")
        normalized.append(candidate)
    return tuple(normalized)


def _configured_url_fields(
    kind: ConnectorKind,
    document: dict[str, object],
) -> tuple[tuple[str, tuple[str, ...]], ...]:
    field_by_kind = {
        ConnectorKind.RSS_ATOM: "feed_url",
        ConnectorKind.JSON_API: "endpoint_url",
        ConnectorKind.SITEMAP: "sitemap_url",
        ConnectorKind.LIST_DETAIL: "list_url",
    }
    field = field_by_kind.get(kind)
    if field is not None:
        value = document.get(field)
        return ((field, (value,)),) if isinstance(value, str) else ()
    if kind is ConnectorKind.DIRECT_PDF:
        values = document.get("document_urls")
        if isinstance(values, list):
            urls = tuple(value for value in values if isinstance(value, str))
            return (("document_urls", urls),)
    return ()


def _normalize_and_validate_url(url: str, allowed_hosts: tuple[str, ...]) -> str:
    if (
        _contains_expression(url)
        or len(url) > 2048
        or any(ord(character) < 32 or ord(character) == 127 for character in url)
        or any(ord(character) < 32 or ord(character) == 127 for character in unquote(url))
    ):
        raise ConnectorConfigRejected("dynamic or oversized network target is forbidden")
    try:
        parsed = urlsplit(url)
        port = parsed.port
    except ValueError as error:
        raise ConnectorConfigRejected("network target has an invalid host or port") from error
    if (
        parsed.scheme not in {"http", "https"}
        or parsed.hostname is None
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
    ):
        raise ConnectorConfigRejected("network target is not an allowed HTTP URL")
    if (parsed.scheme == "https" and port not in {None, 443}) or (
        parsed.scheme == "http" and port not in {None, 80}
    ):
        raise ConnectorConfigRejected("network target uses a dangerous port")
    if "?" in url:
        raise ConnectorConfigRejected(
            "network target queries are forbidden; credentials require a vault reference"
        )
    host = parsed.hostname.rstrip(".").casefold()
    if host not in allowed_hosts:
        raise ConnectorConfigRejected("network target is outside the exact allowed hosts")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        address = None
    if address is not None and (not address.is_global or address in _METADATA_ADDRESSES):
        raise ConnectorConfigRejected("network target is internal or metadata infrastructure")
    netloc = host if port is None else f"{host}:{port}"
    return urlunsplit((parsed.scheme.casefold(), netloc, parsed.path or "/", "", ""))


def _reject_expressions(value: object) -> None:
    if isinstance(value, str) and _contains_expression(value):
        raise ConnectorConfigRejected("template expressions are forbidden")
    if isinstance(value, dict):
        for key, nested in value.items():
            _reject_expressions(key)
            _reject_expressions(nested)
    elif isinstance(value, list):
        for nested in value:
            _reject_expressions(nested)


def _contains_expression(value: str) -> bool:
    return any(marker in value for marker in _EXPRESSION_MARKERS)


def _is_json_pointer(value: object) -> bool:
    if not isinstance(value, str) or not value.startswith("/") or len(value) > 300:
        return False
    index = 0
    while index < len(value):
        if value[index] == "~":
            if index + 1 >= len(value) or value[index + 1] not in {"0", "1"}:
                return False
            index += 2
        else:
            index += 1
    return True
