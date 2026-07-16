"""Strict, offline evaluator for the Round 17 real-source pilot.

The evaluator intentionally has no network client. It accepts only local, hashed exports and
returns BLOCKED whenever required real-world evidence is absent or internally inconsistent.
"""

from __future__ import annotations

import argparse
import base64
import binascii
import json
import math
import os
import re
from datetime import UTC, date, datetime, timedelta
from hashlib import sha256
from pathlib import Path
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_SCHEMA_PATH = ROOT / "docs/codex-kit/assets/validation/round17_evidence.schema.json"
GOLD_SCHEMA_PATH = ROOT / "docs/codex-kit/assets/validation/round17_gold.schema.json"
METRICS_DEFINITION_PATH = ROOT / "docs/codex-kit/assets/validation/round17_metrics_definition.json"
DEFAULT_EVIDENCE_PATH = ROOT / "docs/acceptance/assets/round17/round17-evidence.json"
DEFAULT_GOLD_PATH = ROOT / "tests/gold/round17/manifest.json"

EXPECTED_DATABASE_REVISION = "0017b_round17_pilot"
EXPECTED_METRICS_VERSION = "phase2-round17-metrics-v1.0.0"
EXPECTED_GOLD_VERSION = "phase2-round17-gold-v1.0.0"
EXPECTED_ROSTER_VERSION = "r17-sources-v0.1"
EXPECTED_WINDOW_SECONDS = 168 * 60 * 60
MAX_RUN_START_LATENESS_SECONDS = 15 * 60
MAX_INPUT_BYTES = 64 * 1024 * 1024
MAX_TRUST_ANCHOR_BYTES = 16 * 1024
EXPECTED_RUN_UNIVERSE_QUERY = """SELECT fr.id AS run_id
FROM fetch_run AS fr
JOIN round17_pilot_window_source AS segment
  ON segment.id = fr.pilot_window_source_id
WHERE segment.window_id = :window_id
  AND fr.run_origin = 'SCHEDULED'
  AND fr.execution_domain = 'PRODUCTION'
ORDER BY fr.id
"""

CANDIDATE_GOLD_COUNTS = {
    "documents": 500,
    "duplicate_pairs": 300,
    "event_clusters": 100,
    "claim_evidence_annotations": 200,
    "search_questions": 100,
}
CANDIDATE_PROPORTION_GATES = {
    "discovery_within_slo": 0.95,
    "correct_eventization": 0.95,
    "searchable_readable": 0.95,
    "tier1_transport_success": 0.99,
    "html_parse_success": 0.98,
    "text_pdf_parse_success": 0.97,
    "ocr_usable": 0.92,
    "safety_key_field_accuracy": 0.98,
    "other_field_accuracy": 0.95,
    "exact_dedup_precision": 0.995,
    "fuzzy_candidate_precision": 0.98,
    "fuzzy_candidate_recall": 0.93,
    "cluster_purity": 0.95,
}
CANDIDATE_SOURCE_ROSTER = (
    ("GOV-002", 6, 8),
    ("GOV-003", 6, 8),
    ("GOV-004", 6, 8),
    ("GOV-005", 6, 8),
    ("GOV-006", 6, 8),
    ("GOV-007", 6, 8),
    ("GOV-014", 6, 8),
    ("GOV-015", 6, 8),
    ("GOV-016", 6, 8),
    ("GOV-017", 6, 8),
    ("GOV-020", 6, 8),
    ("NRA-001", 6, 8),
    ("GOV-010", 12, 18),
    ("RES-004", 12, 18),
    ("GOV-008", 24, 30),
    ("RES-001", 24, 30),
    ("ENT-005", 24, 30),
    ("ENT-006", 24, 30),
    ("ENT-007", 24, 30),
    ("ENT-008", 24, 30),
)
CANDIDATE_ZERO_GATES = {
    "r3_review_bypass_count",
    "r4_or_unpublished_leak_count",
    "publication_service_bypass_count",
    "final_overdue_operator_backlog_count",
    "external_model_api_notification_cost_minor",
}
RATE_POPULATIONS = {
    "discovery_within_slo": "EVENT_ENUMERATION",
    "correct_eventization": "EVENT_ENUMERATION",
    "searchable_readable": "EVENT_ENUMERATION",
    "tier1_transport_success": "SCHEDULED_RUNS",
    "html_parse_success": "GOLD_DOCUMENTS",
    "text_pdf_parse_success": "GOLD_DOCUMENTS",
    "ocr_usable": "GOLD_DOCUMENTS",
    "safety_key_field_accuracy": "GOLD_KEY_SAFETY_CLAIMS",
    "other_field_accuracy": "GOLD_OTHER_CLAIMS",
    "exact_dedup_precision": "GOLD_DUPLICATE_PAIRS",
    "fuzzy_candidate_precision": "GOLD_DUPLICATE_PAIRS",
    "fuzzy_candidate_recall": "GOLD_DUPLICATE_PAIRS",
    "cluster_purity": "GOLD_EVENT_CLUSTERS",
}
ABSOLUTE_QUERY_IDS = {
    "r3_review_bypass_count": "round17.absolute.r3_review_bypass",
    "r4_or_unpublished_leak_count": "round17.absolute.r4_or_unpublished_leak",
    "publication_service_bypass_count": "round17.absolute.publication_service_bypass",
    "published_critical_claim_count": "round17.absolute.published_critical_claims",
    "published_critical_claim_with_current_evidence_count": (
        "round17.absolute.published_critical_claims_current_evidence"
    ),
    "final_overdue_operator_backlog_count": "round17.absolute.final_overdue_backlog",
    "external_model_api_notification_cost_minor": "round17.absolute.external_cost_minor",
}
OPERATOR_CATEGORIES = {
    "SOURCE_MAINTENANCE": "source_maintenance",
    "EXCEPTION_HANDLING": "exception_handling",
    "R3_REVIEW": "r3_review",
    "COPYRIGHT_CORRECTION": "copyright_correction",
}
FORBIDDEN_INLINE_KEYS = {
    "access_token",
    "attachment_bytes",
    "body",
    "content",
    "cookie",
    "cookies",
    "document_text",
    "full_text",
    "note",
    "notes",
    "password",
    "personal_data",
    "raw_html",
    "raw_text",
    "secret",
    "token",
}
TRACE_FIELDS = {
    "source_key",
    "run_id",
    "raw_object_id",
    "document_id",
    "accepted_claim_ids",
    "evidence_ids",
    "event_id",
    "publication_revision_id",
    "projection_revision_id",
    "run_origin",
    "execution_domain",
}
EVENT_PREDICATE_FACT_FIELDS = {
    "published_at",
    "discovered_at",
    "discovery_slo_hours",
    "gold_cluster_id",
    "gold_member_document_ids",
    "event_document_ids",
    "cluster_platform_event_ids",
    "accepted_claim_ids",
    "current_evidence_ids",
    "claim_evidence_links",
    "projection_revision_id",
    "projection_event_id",
    "projection_state",
    "search_query_id",
    "search_result_event_ids",
    "retrieval_status",
}
EVENT_PREDICATE_RESULT_FIELDS = {
    "within_slo",
    "correct_eventization",
    "nonduplicate",
    "critical_evidence_current",
    "searchable_readable",
}
PREFLIGHT_CONFIRMATION_FIELDS = (
    "decision_id",
    "approver_subject",
    "confirmed_at",
    "mfa_verified_at",
    "roster_version",
    "roster_sha256",
    "metrics_definition_version",
    "metrics_definition_sha256",
    "window_seconds",
)
SOURCE_ADMISSION_ENTRY_FIELDS = (
    "source_key",
    "source_id",
    "display_name",
    "canonical_endpoint",
    "access_mode",
    "allowed_domains",
    "url_scopes",
    "governance_owner_subject",
    "policy_version",
    "policy_sha256",
    "connector_version",
    "connector_sha256",
    "config_version",
    "config_sha256",
    "poll_interval_hours",
    "discovery_slo_hours",
)
APPROVAL_AUDIT_FIELDS = (
    "source_key",
    "source_id",
    "display_name",
    "canonical_endpoint",
    "access_mode",
    "allowed_domains",
    "url_scopes",
    "governance_owner_subject",
    "poll_interval_hours",
    "discovery_slo_hours",
    "stage",
    "status",
    "approver_subject",
    "signed_at",
    "mfa_verified_at",
    "expires_at",
    "decision_id",
    "admission_manifest_sha256",
    "policy_version",
    "policy_sha256",
    "connector_version",
    "connector_sha256",
    "config_version",
    "config_sha256",
)
WINDOW_EXPORT_FIELDS = (
    "id",
    "state",
    "version",
    "started_at",
    "ended_at",
    "duration_seconds",
    "immutable",
    "started_by_subject",
    "server_time",
    "database_revision",
    "source_admission_manifest_sha256",
    "source_segments",
    "pause_resume_events",
)
RUN_UNIVERSE_FILTERS = {
    "window_bound_segment_required": True,
    "run_origin": "SCHEDULED",
    "execution_domain": "PRODUCTION",
}

Issue = dict[str, Any]
Payload = dict[str, Any]


def canonical_json_bytes(
    value: Payload,
    *,
    excluded_keys: set[str] | None = None,
) -> bytes:
    """Serialize canonical JSON after excluding named top-level envelope fields."""

    payload = {key: item for key, item in value.items() if key not in (excluded_keys or set())}
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def canonical_sha256(value: Payload, *, excluded_keys: set[str] | None = None) -> str:
    """Hash canonical JSON after excluding named top-level envelope fields."""

    return sha256(canonical_json_bytes(value, excluded_keys=excluded_keys)).hexdigest()


def _issue(issues: list[Issue], code: str, message: str, **details: Any) -> None:
    item: Issue = {"code": code, "message": message}
    if details:
        item["details"] = details
    issues.append(item)


def _parse_time(value: object, *, field: str, issues: list[Issue]) -> datetime | None:
    if not isinstance(value, str):
        _issue(issues, "INVALID_TIMESTAMP", f"{field} must be an RFC 3339 timestamp")
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        _issue(issues, "INVALID_TIMESTAMP", f"{field} is not a valid timestamp")
        return None
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        _issue(issues, "TIMESTAMP_NOT_UTC", f"{field} must be UTC")
        return None
    return parsed.astimezone(UTC)


def _valid_external_oidc_actor(actor: object, expected_name: str) -> bool:
    if not isinstance(actor, dict):
        return False
    issuer = str(actor.get("issuer", "")).strip().lower()
    subject = str(actor.get("subject", "")).strip()
    try:
        subject_uuid = UUID(subject)
    except ValueError:
        return False
    prohibited_issuer_parts = ("localhost", "127.0.0.1", ".local", ".example")
    return bool(
        actor.get("display_name") == expected_name
        and actor.get("identity_provider") == "OIDC"
        and actor.get("is_local") is False
        and issuer.startswith("https://")
        and not any(part in issuer for part in prohibited_issuer_parts)
        and subject_uuid.version == 7
    )


def _is_uuid7(value: object) -> bool:
    if not isinstance(value, str):
        return False
    try:
        return UUID(value).version == 7
    except ValueError:
        return False


def _validate_actor_set(
    evidence: Payload,
    gold: Payload,
    issues: list[Issue],
) -> dict[str, str]:
    evidence_actors = evidence.get("actors", {})
    gold_actors = gold.get("actors", {})
    subjects: dict[str, str] = {}
    for name in ("LEO", "yinzi", "baixuejiao"):
        actor = evidence_actors.get(name) if isinstance(evidence_actors, dict) else None
        if not _valid_external_oidc_actor(actor, name):
            _issue(
                issues,
                "ACTOR_NOT_EXTERNAL_OIDC",
                f"{name} must be bound to a non-local UUIDv7 OIDC identity",
            )
            continue
        if not isinstance(actor, dict):
            continue
        subjects[name] = str(actor["subject"])
        if not isinstance(gold_actors, dict) or gold_actors.get(name) != actor:
            _issue(
                issues,
                "GOLD_ACTOR_BINDING_MISMATCH",
                f"gold actor binding for {name} differs from pilot evidence",
            )
    if len(set(subjects.values())) != len(subjects):
        _issue(
            issues, "ACTOR_SUBJECT_COLLISION", "the three human duties need distinct OIDC subjects"
        )
    return subjects


def _safe_ref_target(root: Path, uri: object) -> Path | None:
    if not isinstance(uri, str) or not uri or "://" in uri:
        return None
    relative = Path(uri)
    if relative.is_absolute() or relative.drive:
        return None
    target = (root / relative).resolve()
    try:
        target.relative_to(root.resolve())
    except ValueError:
        return None
    return target


def _validate_ref(
    ref: object,
    *,
    root: Path,
    issues: list[Issue],
    cache: set[tuple[str, str]],
) -> Path | None:
    if not isinstance(ref, dict):
        _issue(issues, "EVIDENCE_REFERENCE_INVALID", "evidence reference is not an object")
        return None
    uri = ref.get("uri")
    expected_hash = ref.get("sha256")
    if not isinstance(uri, str) or not isinstance(expected_hash, str):
        _issue(issues, "EVIDENCE_REFERENCE_INVALID", "evidence reference lacks uri or sha256")
        return None
    cache_key = (uri, expected_hash)
    if cache_key in cache:
        return _safe_ref_target(root, uri)
    cache.add(cache_key)
    target = _safe_ref_target(root, uri)
    if target is None:
        _issue(issues, "EVIDENCE_REFERENCE_UNSAFE", "evidence reference must stay under root")
        return None
    if not target.is_file():
        _issue(issues, "EVIDENCE_REFERENCE_MISSING", "evidence reference file is missing", uri=uri)
        return None
    if target.stat().st_size > MAX_INPUT_BYTES:
        _issue(issues, "EVIDENCE_REFERENCE_TOO_LARGE", "evidence reference is too large", uri=uri)
        return None
    actual_hash = sha256(target.read_bytes()).hexdigest()
    if not re.fullmatch(r"[0-9a-f]{64}", expected_hash) or actual_hash != expected_hash:
        _issue(
            issues, "EVIDENCE_REFERENCE_HASH_MISMATCH", "evidence reference hash differs", uri=uri
        )
        return None
    return target


def _validate_exact_json_export(
    ref: object,
    expected: object,
    *,
    issue_code: str,
    message: str,
    root: Path,
    issues: list[Issue],
    cache: set[tuple[str, str]],
) -> bool:
    """Require a hash-bound reference to contain exactly the asserted ID-only export."""

    target = _validate_ref(ref, root=root, issues=issues, cache=cache)
    referenced: object = None
    if target is not None:
        try:
            referenced = json.loads(target.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            referenced = None
    if referenced != expected:
        _issue(issues, issue_code, message)
        return False
    return True


def _run_database_record_statement(run: Payload) -> Payload:
    response_metadata = run.get("response_metadata")
    return {
        "query_id": "round17.authoritative_run_record.v1",
        "query_version": "v1",
        "database_revision": EXPECTED_DATABASE_REVISION,
        "run_id": run.get("run_id"),
        "source_key": run.get("source_key"),
        "source_id": run.get("source_id"),
        "window_id": run.get("window_id"),
        "segment_id": run.get("segment_id"),
        "scheduled_slot_at": run.get("scheduled_slot_at"),
        "started_at": run.get("started_at"),
        "ended_at": run.get("ended_at"),
        "outcome": run.get("outcome"),
        "response_state": run.get("response_state"),
        "request_count": run.get("request_count"),
        "response_bytes": (
            response_metadata.get("response_bytes")
            if isinstance(response_metadata, dict)
            else None
        ),
        "transport_failure_code": run.get("transport_failure_code"),
        "failure_detected_at": run.get("failure_detected_at"),
        "recovered": run.get("recovered") is True,
        "recovery_of_run_id": run.get("recovery_of_run_id"),
    }


def _admission_manifest(evidence: Payload) -> Payload | None:
    manifest = evidence.get("source_admission_manifest")
    return manifest if isinstance(manifest, dict) else None


def _admission_manifest_sha256(evidence: Payload) -> str | None:
    manifest = _admission_manifest(evidence)
    digest = manifest.get("manifest_sha256") if manifest is not None else None
    return digest if isinstance(digest, str) else None


def _source_version_binding(source: Payload) -> Payload:
    return {
        "source_id": source.get("source_id"),
        "source_key": source.get("source_key"),
        "policy_version": source.get("policy_version"),
        "policy_sha256": source.get("policy_sha256"),
        "connector_version": source.get("connector_version"),
        "connector_sha256": source.get("connector_sha256"),
        "config_version": source.get("config_version"),
        "config_sha256": source.get("config_sha256"),
    }


def _segment_number(segment: Payload) -> int:
    value = segment.get("segment_number")
    return value if isinstance(value, int) and not isinstance(value, bool) else -1


def _validate_authoritative_trace(
    trace: object,
    *,
    expected_source_key: str,
    expected_run_id: str,
    expected_event_id: str | None,
    issue_code: str,
    root: Path,
    issues: list[Issue],
    cache: set[tuple[str, str]],
) -> bool:
    """Validate a signed, hash-bound ID-only production trace and its exact export."""

    if not isinstance(trace, dict) or set(trace) != TRACE_FIELDS | {"evidence_ref"}:
        _issue(issues, issue_code, "trace must contain only the complete ID-only chain")
        return False
    statement = {field: trace.get(field) for field in TRACE_FIELDS}
    accepted_claim_ids = statement["accepted_claim_ids"]
    evidence_ids = statement["evidence_ids"]
    scalar_ids = (
        statement["raw_object_id"],
        statement["document_id"],
        statement["event_id"],
        statement["publication_revision_id"],
        statement["projection_revision_id"],
    )
    valid = bool(
        statement["source_key"] == expected_source_key
        and statement["run_id"] == expected_run_id
        and (expected_event_id is None or statement["event_id"] == expected_event_id)
        and statement["run_origin"] == "SCHEDULED"
        and statement["execution_domain"] == "PRODUCTION"
        and all(_is_uuid7(value) for value in scalar_ids)
        and isinstance(accepted_claim_ids, list)
        and accepted_claim_ids
        and all(isinstance(value, str) for value in accepted_claim_ids)
        and len(accepted_claim_ids) == len(set(accepted_claim_ids))
        and all(_is_uuid7(value) for value in accepted_claim_ids)
        and isinstance(evidence_ids, list)
        and evidence_ids
        and all(isinstance(value, str) for value in evidence_ids)
        and len(evidence_ids) == len(set(evidence_ids))
        and all(_is_uuid7(value) for value in evidence_ids)
    )
    target = _validate_ref(trace.get("evidence_ref"), root=root, issues=issues, cache=cache)
    if target is None:
        valid = False
    else:
        try:
            referenced_statement = json.loads(target.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            referenced_statement = None
        if referenced_statement != statement:
            valid = False
    if not valid:
        _issue(
            issues,
            issue_code,
            "trace is not an exact SCHEDULED/PRODUCTION Raw→Document→accepted "
            "Claim/Evidence→Event→Publication projection export",
        )
    return valid


def _schema_issues(payload: Payload, schema_path: Path, label: str, issues: list[Issue]) -> None:
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors = sorted(validator.iter_errors(payload), key=lambda error: list(error.absolute_path))
    for error in errors[:25]:
        path = "/".join(str(part) for part in error.absolute_path) or "$"
        _issue(issues, f"{label}_SCHEMA_INVALID", f"{path}: {error.message}")
    if len(errors) > 25:
        _issue(issues, f"{label}_SCHEMA_INVALID", "additional schema errors were suppressed")


def _validate_external_trust_anchor(
    evidence: Payload,
    *,
    trusted_public_key_pem: bytes | None,
    expected_key_fingerprint_sha256: str | None,
    issues: list[Issue],
) -> None:
    """Verify the detached evidence signature against caller-supplied trust material."""

    if trusted_public_key_pem is None or not expected_key_fingerprint_sha256:
        _issue(
            issues,
            "TRUST_ANCHOR_MISSING",
            "a trusted Ed25519 public key file and expected SHA-256 fingerprint are required",
        )
        return
    if not re.fullmatch(r"[0-9a-f]{64}", expected_key_fingerprint_sha256):
        _issue(
            issues,
            "TRUST_ANCHOR_FINGERPRINT_MISMATCH",
            "the configured trusted-key fingerprint is not lowercase SHA-256",
        )
        return
    try:
        loaded_key = serialization.load_pem_public_key(trusted_public_key_pem)
    except (TypeError, ValueError):
        _issue(
            issues,
            "TRUST_ANCHOR_INVALID",
            "the trusted public key file is not valid PEM SubjectPublicKeyInfo",
        )
        return
    if not isinstance(loaded_key, Ed25519PublicKey):
        _issue(issues, "TRUST_ANCHOR_INVALID", "the trusted public key is not Ed25519")
        return
    raw_public_key = loaded_key.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    actual_fingerprint = sha256(raw_public_key).hexdigest()
    if actual_fingerprint != expected_key_fingerprint_sha256:
        _issue(
            issues,
            "TRUST_ANCHOR_FINGERPRINT_MISMATCH",
            "the trusted public key differs from its independently configured fingerprint",
        )
        return

    signature_envelope = evidence.get("trust_signature")
    if not isinstance(signature_envelope, dict):
        _issue(
            issues,
            "EVIDENCE_SIGNATURE_MISSING",
            "the evidence snapshot lacks its detached Ed25519 signature envelope",
        )
        return
    if signature_envelope.get("algorithm") != "Ed25519":
        _issue(issues, "EVIDENCE_SIGNATURE_INVALID", "the evidence signature is not Ed25519")
        return
    if signature_envelope.get("key_fingerprint_sha256") != actual_fingerprint:
        _issue(
            issues,
            "EVIDENCE_SIGNING_KEY_MISMATCH",
            "the evidence signature fingerprint is not the external trusted key",
        )
        return
    encoded_signature = signature_envelope.get("signature_base64")
    if not isinstance(encoded_signature, str):
        _issue(issues, "EVIDENCE_SIGNATURE_INVALID", "the detached signature is missing")
        return
    try:
        signature = base64.b64decode(encoded_signature, validate=True)
    except (binascii.Error, ValueError):
        _issue(issues, "EVIDENCE_SIGNATURE_INVALID", "the detached signature is not base64")
        return
    try:
        loaded_key.verify(
            signature,
            canonical_json_bytes(evidence, excluded_keys={"trust_signature"}),
        )
    except InvalidSignature:
        _issue(
            issues,
            "EVIDENCE_SIGNATURE_INVALID",
            "the detached signature does not authenticate the canonical evidence payload",
        )


def _validate_no_inline_content(
    value: object,
    *,
    label: str,
    issues: list[Issue],
    path: str = "$",
) -> None:
    if len(issues) >= 100:
        return
    if isinstance(value, dict):
        for key, nested in value.items():
            nested_path = f"{path}/{key}"
            if str(key).lower() in FORBIDDEN_INLINE_KEYS:
                _issue(
                    issues,
                    "EVIDENCE_INLINE_CONTENT_FORBIDDEN",
                    f"{label} contains forbidden inline content at {nested_path}",
                )
            else:
                _validate_no_inline_content(
                    nested,
                    label=label,
                    issues=issues,
                    path=nested_path,
                )
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            _validate_no_inline_content(
                nested,
                label=label,
                issues=issues,
                path=f"{path}/{index}",
            )


def _validate_definition(
    metrics_definition: Payload,
    evidence: Payload,
    *,
    root: Path,
    issues: list[Issue],
    ref_cache: set[tuple[str, str]],
) -> None:
    expected_roster = [
        {
            "source_key": source_key,
            "poll_interval_hours": poll_hours,
            "discovery_slo_hours": slo_hours,
        }
        for source_key, poll_hours, slo_hours in CANDIDATE_SOURCE_ROSTER
    ]
    exact_checks = {
        "version": EXPECTED_METRICS_VERSION,
        "roster_version": EXPECTED_ROSTER_VERSION,
        "window_seconds": EXPECTED_WINDOW_SECONDS,
        "gold_required_counts": CANDIDATE_GOLD_COUNTS,
        "proportion_gates": CANDIDATE_PROPORTION_GATES,
        "source_roster": expected_roster,
        "authority_state": "CANDIDATE_REQUIRES_EXPLICIT_LEO_CONFIRMATION",
    }
    for field, expected in exact_checks.items():
        if metrics_definition.get(field) != expected:
            _issue(
                issues,
                "METRICS_DEFINITION_MISMATCH",
                f"metrics definition field {field} differs from the pinned candidate contract",
            )
    if metrics_definition.get("north_star", {}).get("minimum") != 0.90:
        _issue(issues, "METRICS_DEFINITION_MISMATCH", "north-star candidate threshold differs")
    if set(metrics_definition.get("absolute_zero_gates", [])) != CANDIDATE_ZERO_GATES:
        _issue(issues, "METRICS_DEFINITION_MISMATCH", "absolute zero gates differ")
    if metrics_definition.get("operator_limits") != {
        "daily_total_median_minutes_max": 120,
        "daily_total_p95_minutes_max": 240,
    }:
        _issue(issues, "METRICS_DEFINITION_MISMATCH", "operator candidate limits differ")
    if metrics_definition.get("confidence_interval") != {
        "method": "WILSON_SCORE",
        "confidence_level": 0.95,
        "gate_uses": "POINT_ESTIMATE",
    }:
        _issue(issues, "METRICS_DEFINITION_MISMATCH", "confidence policy differs")

    definition_ref = evidence.get("metrics_definition")
    target = _validate_ref(
        definition_ref,
        root=root,
        issues=issues,
        cache=ref_cache,
    )
    if (
        not isinstance(definition_ref, dict)
        or definition_ref.get("version") != EXPECTED_METRICS_VERSION
    ):
        _issue(issues, "METRICS_VERSION_MISMATCH", "evidence uses a different metrics version")
    if target is not None:
        try:
            referenced_definition = json.loads(target.read_text(encoding="utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            _issue(
                issues, "METRICS_REFERENCE_INVALID", "referenced metrics definition is invalid JSON"
            )
        else:
            if referenced_definition != metrics_definition:
                _issue(
                    issues,
                    "METRICS_REFERENCE_MISMATCH",
                    "referenced metrics definition differs from the evaluator definition",
                )


def _validate_preflight_authorization(
    evidence: Payload,
    metrics_definition: Payload,
    subjects: dict[str, str],
    started_at: datetime | None,
    *,
    root: Path,
    issues: list[Issue],
    ref_cache: set[tuple[str, str]],
) -> None:
    """Require one real, immutable LEO decision binding all R17 preflight choices."""

    authorization = evidence.get("preflight_authorization")
    if not isinstance(authorization, dict):
        _issue(
            issues,
            "PREFLIGHT_AUTHORIZATION_MISSING",
            "real LEO preflight authorization evidence is required",
        )
        return

    if authorization.get("approver_subject") != subjects.get("LEO"):
        _issue(issues, "PREFLIGHT_NOT_LEO", "preflight authorization is not bound to LEO")

    decision_id = authorization.get("decision_id")
    try:
        decision_uuid = UUID(str(decision_id))
    except ValueError:
        decision_uuid = None
    if decision_uuid is None or decision_uuid.version != 7:
        _issue(
            issues,
            "PREFLIGHT_DECISION_ID_INVALID",
            "preflight authorization needs an immutable UUIDv7 decision ID",
        )

    confirmed_at = _parse_time(
        authorization.get("confirmed_at"),
        field="preflight_authorization.confirmed_at",
        issues=issues,
    )
    mfa_at = _parse_time(
        authorization.get("mfa_verified_at"),
        field="preflight_authorization.mfa_verified_at",
        issues=issues,
    )
    if confirmed_at and started_at and confirmed_at > started_at:
        _issue(
            issues,
            "PREFLIGHT_CONFIRMATION_AFTER_T0",
            "LEO must confirm the roster, metrics, and 168-hour window no later than T0",
        )
    if mfa_at and started_at and mfa_at > started_at:
        _issue(
            issues,
            "PREFLIGHT_MFA_AFTER_T0",
            "preflight MFA evidence must exist no later than T0",
        )
    if confirmed_at and mfa_at and mfa_at > confirmed_at:
        _issue(
            issues,
            "PREFLIGHT_CONFIRMATION_MFA_ORDER_INVALID",
            "MFA verification must precede or coincide with the preflight decision",
        )
    if confirmed_at and mfa_at and abs((confirmed_at - mfa_at).total_seconds()) > 300:
        _issue(
            issues,
            "PREFLIGHT_CONFIRMATION_MFA_STALE",
            "preflight confirmation MFA must be within five minutes of the decision",
        )

    expected_roster_sha256 = _admission_manifest_sha256(evidence)
    if (
        authorization.get("roster_version") != EXPECTED_ROSTER_VERSION
        or evidence.get("roster_version") != EXPECTED_ROSTER_VERSION
        or expected_roster_sha256 is None
        or authorization.get("roster_sha256") != expected_roster_sha256
    ):
        _issue(
            issues,
            "PREFLIGHT_ROSTER_NOT_CONFIRMED",
            "LEO preflight evidence does not bind the exact candidate roster version and hash",
        )

    definition_ref = evidence.get("metrics_definition")
    referenced_sha256 = definition_ref.get("sha256") if isinstance(definition_ref, dict) else None
    if (
        authorization.get("metrics_definition_version") != EXPECTED_METRICS_VERSION
        or authorization.get("metrics_definition_sha256") != referenced_sha256
    ):
        _issue(
            issues,
            "PREFLIGHT_METRICS_NOT_CONFIRMED",
            "LEO preflight evidence does not bind the exact candidate metrics version and hash",
        )

    if authorization.get("window_seconds") != EXPECTED_WINDOW_SECONDS:
        _issue(
            issues,
            "PREFLIGHT_WINDOW_NOT_CONFIRMED",
            "LEO preflight evidence does not explicitly confirm a 604800-second window",
        )

    try:
        statement = {field: authorization[field] for field in PREFLIGHT_CONFIRMATION_FIELDS}
    except KeyError:
        statement = {}
    expected_confirmation_sha256 = canonical_sha256(statement)
    if authorization.get("confirmation_sha256") != expected_confirmation_sha256:
        _issue(
            issues,
            "PREFLIGHT_CONFIRMATION_HASH_MISMATCH",
            "preflight decision fields differ from their canonical confirmation hash",
        )

    target = _validate_ref(
        authorization.get("evidence_ref"),
        root=root,
        issues=issues,
        cache=ref_cache,
    )
    if target is None:
        return
    try:
        referenced_confirmation = json.loads(target.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        _issue(
            issues,
            "PREFLIGHT_CONFIRMATION_REFERENCE_INVALID",
            "preflight authorization reference is not valid UTF-8 JSON",
        )
        return
    expected_reference = {
        **statement,
        "confirmation_sha256": authorization.get("confirmation_sha256"),
    }
    if referenced_confirmation != expected_reference:
        _issue(
            issues,
            "PREFLIGHT_CONFIRMATION_REFERENCE_MISMATCH",
            "referenced audit export does not contain the explicit preflight confirmation",
        )


def _validate_window(
    evidence: Payload,
    subjects: dict[str, str],
    *,
    root: Path,
    issues: list[Issue],
    ref_cache: set[tuple[str, str]],
) -> tuple[datetime | None, datetime | None]:
    window = evidence.get("window", {})
    if not isinstance(window, dict):
        _issue(issues, "WINDOW_INVALID", "window must be an object")
        return None, None
    window_id = window.get("id")
    if not _is_uuid7(window_id):
        _issue(issues, "WINDOW_ID_INVALID", "the immutable window ID must be UUIDv7")
    started_at = _parse_time(window.get("started_at"), field="window.started_at", issues=issues)
    ended_at = _parse_time(window.get("ended_at"), field="window.ended_at", issues=issues)
    exact = bool(
        started_at
        and ended_at
        and (ended_at - started_at).total_seconds() == EXPECTED_WINDOW_SECONDS
        and window.get("duration_seconds") == EXPECTED_WINDOW_SECONDS
        and window.get("immutable") is True
    )
    if not exact:
        _issue(
            issues,
            "WINDOW_NOT_EXACT_168_HOURS",
            "the immutable observation window must be exactly 604800 seconds",
        )
    if ended_at is not None and ended_at > datetime.now(UTC):
        _issue(issues, "WINDOW_NOT_COMPLETE", "the observation window has not ended")
    if window.get("started_by_subject") != subjects.get("LEO"):
        _issue(issues, "WINDOW_START_NOT_APPROVED", "LEO must start the window")
    mfa_at = _parse_time(
        window.get("mfa_verified_at"), field="window.mfa_verified_at", issues=issues
    )
    if started_at and mfa_at:
        if mfa_at > started_at:
            _issue(
                issues,
                "WINDOW_START_MFA_ORDER_INVALID",
                "window start MFA must precede or coincide with the start decision",
            )
        elif (started_at - mfa_at).total_seconds() > 300:
            _issue(issues, "WINDOW_START_MFA_STALE", "window start MFA must be within five minutes")
    _validate_ref(
        window.get("start_evidence_ref"),
        root=root,
        issues=issues,
        cache=ref_cache,
    )

    if (
        window.get("state") != "COMPLETED"
        or not isinstance(window.get("version"), int)
        or isinstance(window.get("version"), bool)
        or int(window.get("version", 0)) < 1
        or window.get("database_revision") != EXPECTED_DATABASE_REVISION
        or window.get("source_admission_manifest_sha256")
        != _admission_manifest_sha256(evidence)
    ):
        _issue(
            issues,
            "WINDOW_DATABASE_EXPORT_MISMATCH",
            "window state, version, database revision, or admission manifest binding differs",
        )
    server_time = _parse_time(
        window.get("server_time"), field="window.server_time", issues=issues
    )
    if (
        server_time is None
        or ended_at is None
        or server_time < ended_at
        or server_time > datetime.now(UTC)
    ):
        _issue(
            issues,
            "WINDOW_DATABASE_EXPORT_MISMATCH",
            "window DB server time must prove a completed, non-future export",
        )

    manifest = _admission_manifest(evidence)
    entries = manifest.get("entries", []) if manifest is not None else []
    manifest_entries = {
        str(entry.get("source_key")): entry
        for entry in entries
        if isinstance(entry, dict) and isinstance(entry.get("source_key"), str)
    }
    source_segments = window.get("source_segments")
    pause_resume_events = window.get("pause_resume_events")
    segment_groups: dict[str, list[Payload]] = {key: [] for key in manifest_entries}
    segment_ids: set[str] = set()
    segments_valid = isinstance(source_segments, list) and isinstance(pause_resume_events, list)
    if isinstance(source_segments, list):
        for segment in source_segments:
            if not isinstance(segment, dict):
                segments_valid = False
                continue
            source_key = segment.get("source_key")
            segment_id = segment.get("segment_id")
            if (
                source_key not in manifest_entries
                or not _is_uuid7(segment_id)
                or str(segment_id) in segment_ids
            ):
                segments_valid = False
                continue
            segment_ids.add(str(segment_id))
            segment_groups[str(source_key)].append(segment)
            entry = manifest_entries[str(source_key)]
            expected_versions = {
                field: entry.get(field)
                for field in (
                    "source_id",
                    "source_key",
                    "policy_version",
                    "policy_sha256",
                    "connector_version",
                    "connector_sha256",
                    "config_version",
                    "config_sha256",
                )
            }
            if segment.get("source_versions") != expected_versions:
                segments_valid = False
    expected_events: list[Payload] = []
    for source_key, group in segment_groups.items():
        ordered = sorted(group, key=_segment_number)
        if not ordered or [item.get("segment_number") for item in ordered] != list(
            range(1, len(ordered) + 1)
        ):
            segments_valid = False
            continue
        previous_end = started_at
        for index, segment in enumerate(ordered):
            segment_start = _parse_time(
                segment.get("started_at"),
                field=f"window.{source_key}.segment.started_at",
                issues=issues,
            )
            segment_end = _parse_time(
                segment.get("ended_at"),
                field=f"window.{source_key}.segment.ended_at",
                issues=issues,
            )
            is_last = index == len(ordered) - 1
            if (
                segment_start is None
                or segment_end is None
                or previous_end is None
                or segment_start != previous_end
                or segment_end <= segment_start
                or (is_last and segment_end != ended_at)
                or segment.get("status") != ("COMPLETED" if is_last else "PAUSED")
            ):
                segments_valid = False
            if not is_last:
                if (
                    segment.get("paused_at") != segment.get("ended_at")
                    or not isinstance(segment.get("pause_reason"), str)
                    or not str(segment.get("pause_reason", "")).strip()
                ):
                    segments_valid = False
                expected_events.append(
                    {
                        "event": "PAUSE",
                        "source_key": source_key,
                        "source_id": segment.get("source_id"),
                        "segment_id": segment.get("segment_id"),
                        "at": segment.get("ended_at"),
                        "reason": segment.get("pause_reason"),
                    }
                )
            elif segment.get("paused_at") is not None or segment.get("pause_reason") is not None:
                segments_valid = False
            if index == 0:
                if any(
                    segment.get(field) is not None
                    for field in ("resumed_by_subject", "resume_reason")
                ):
                    segments_valid = False
            else:
                if (
                    segment.get("resumed_by_subject") != subjects.get("yinzi")
                    or not isinstance(segment.get("resume_reason"), str)
                    or not str(segment.get("resume_reason", "")).strip()
                ):
                    segments_valid = False
                expected_events.append(
                    {
                        "event": "RESUME",
                        "source_key": source_key,
                        "source_id": segment.get("source_id"),
                        "segment_id": segment.get("segment_id"),
                        "at": segment.get("started_at"),
                        "resumed_by_subject": segment.get("resumed_by_subject"),
                        "reason": segment.get("resume_reason"),
                    }
                )
            previous_end = segment_end
    if set(segment_groups) != set(manifest_entries) or any(
        not group for group in segment_groups.values()
    ):
        segments_valid = False
    if isinstance(pause_resume_events, list) and sorted(
        pause_resume_events,
        key=lambda item: canonical_json_bytes(item) if isinstance(item, dict) else b"",
    ) != sorted(expected_events, key=canonical_json_bytes):
        segments_valid = False
    if not segments_valid:
        _issue(
            issues,
            "WINDOW_DATABASE_EXPORT_MISMATCH",
            "window source segments or pause/resume history are incomplete or inconsistent",
        )

    try:
        window_export = {field: window[field] for field in WINDOW_EXPORT_FIELDS}
    except KeyError:
        window_export = {}
    _validate_exact_json_export(
        window.get("database_export_ref"),
        window_export,
        issue_code="WINDOW_DATABASE_EXPORT_MISMATCH",
        message="the immutable window DB export differs from the signed inline facts",
        root=root,
        issues=issues,
        cache=ref_cache,
    )
    baseline = evidence.get("baseline", {})
    if isinstance(baseline, dict):
        if baseline.get("database_revision") != EXPECTED_DATABASE_REVISION:
            _issue(issues, "DATABASE_REVISION_MISMATCH", "R17 database revision is not recorded")
        if baseline.get("config_version") != EXPECTED_ROSTER_VERSION:
            _issue(issues, "CONFIG_VERSION_MISMATCH", "baseline config is not the frozen roster")
        commit = baseline.get("commit")
        if not isinstance(commit, str) or len(set(commit)) < 4:
            _issue(issues, "BASELINE_COMMIT_INVALID", "baseline commit looks like a placeholder")
        recorded_at = _parse_time(
            baseline.get("recorded_at"), field="baseline.recorded_at", issues=issues
        )
        if started_at and recorded_at and recorded_at > started_at:
            _issue(issues, "BASELINE_RECORDED_AFTER_START", "baseline must precede T0")
    return started_at, ended_at


def _placeholder_version(value: object) -> bool:
    if not isinstance(value, str) or not value.strip():
        return True
    return value.strip().lower().startswith(("todo", "pending", "fixture", "example"))


def _finite_number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    converted = float(value)
    return converted if math.isfinite(converted) else None


def _https_host(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    match = re.match(r"^https://([^/:?#]+)(?::[0-9]+)?(?:[/?#]|$)", value.strip(), re.I)
    if match is None or "@" in match.group(1):
        return None
    return match.group(1).lower().rstrip(".")


def _valid_domain(value: object) -> bool:
    if not isinstance(value, str) or len(value) > 253:
        return False
    return bool(
        re.fullmatch(
            r"(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+"
            r"[a-z](?:[a-z0-9-]{0,61}[a-z0-9])?",
            value.lower(),
        )
    )


def _validate_sources(
    evidence: Payload,
    metrics_definition: Payload,
    subjects: dict[str, str],
    started_at: datetime | None,
    ended_at: datetime | None,
    *,
    root: Path,
    issues: list[Issue],
    ref_cache: set[tuple[str, str]],
) -> dict[str, Payload]:
    sources = evidence.get("sources", [])
    if not isinstance(sources, list):
        _issue(issues, "SOURCE_ROSTER_MISMATCH", "sources must be an array")
        return {}
    source_map = {
        str(source.get("source_key")): source
        for source in sources
        if isinstance(source, dict) and isinstance(source.get("source_key"), str)
    }
    expected_roster = metrics_definition.get("source_roster", [])
    expected = {
        entry["source_key"]: entry
        for entry in expected_roster
        if isinstance(entry, dict) and isinstance(entry.get("source_key"), str)
    }
    if len(sources) != 20 or len(source_map) != 20 or set(source_map) != set(expected):
        _issue(
            issues,
            "SOURCE_ROSTER_MISMATCH",
            "evidence must contain exactly the 20 streams bound by preflight authorization",
        )
    manifest = _admission_manifest(evidence)
    manifest_entries = manifest.get("entries") if manifest is not None else None
    if (
        manifest is None
        or set(manifest) != {
            "version",
            "source_count",
            "entries",
            "manifest_sha256",
            "evidence_ref",
        }
        or manifest.get("version") != EXPECTED_ROSTER_VERSION
        or manifest.get("source_count") != 20
        or not isinstance(manifest_entries, list)
    ):
        _issue(
            issues,
            "SOURCE_ADMISSION_MANIFEST_MISMATCH",
            "the full 20-source admission manifest is absent or malformed",
        )
        manifest_entries = []
    decision_ids: set[str] = set()
    source_ids: set[str] = set()
    actual_manifest_entries: list[Payload] = []
    for source_key, expected_source in expected.items():
        source = source_map.get(source_key)
        if source is None:
            continue
        source_id = source.get("source_id")
        if not _is_uuid7(source_id) or str(source_id) in source_ids:
            _issue(
                issues,
                "SOURCE_ADMISSION_MANIFEST_MISMATCH",
                f"{source_key} source identity must be a unique UUIDv7",
            )
        else:
            source_ids.add(str(source_id))
        if (
            source.get("state") != "ACTIVE"
            or source.get("server_authoritative") is not True
            or source.get("governance_owner_subject") != subjects.get("yinzi")
        ):
            _issue(
                issues,
                "SOURCE_NOT_AUTHORITATIVE_ACTIVE",
                f"{source_key} is not an authoritative ACTIVE source owned by yinzi",
            )
        if (
            source.get("poll_interval_hours") != expected_source["poll_interval_hours"]
            or source.get("discovery_slo_hours") != expected_source["discovery_slo_hours"]
        ):
            _issue(issues, "SOURCE_SLO_MISMATCH", f"{source_key} poll/SLO differs from v1.0.0")
        for field in ("policy_version", "connector_version", "config_version"):
            if _placeholder_version(source.get(field)):
                _issue(issues, "SOURCE_VERSION_MISSING", f"{source_key} lacks a real {field}")
        for field in ("policy_sha256", "connector_sha256", "config_sha256"):
            if not isinstance(source.get(field), str) or not re.fullmatch(
                r"[0-9a-f]{64}", str(source.get(field))
            ):
                _issue(issues, "SOURCE_VERSION_MISSING", f"{source_key} lacks a real {field}")
        governance_policy = source.get("governance_policy")
        required_policy_fields = {
            "allowed_domains",
            "url_scopes",
            "robots_decision",
            "terms_decision",
            "copyright_decision",
            "raw_retention_days",
            "storage_policy",
            "display_policy",
            "max_requests_per_run",
            "robots_evidence_ref",
            "terms_evidence_ref",
            "copyright_evidence_ref",
        }
        if (
            not isinstance(governance_policy, dict)
            or set(governance_policy) != required_policy_fields
        ):
            _issue(
                issues,
                "SOURCE_LEGAL_POLICY_INCOMPLETE",
                f"{source_key} lacks the complete robots/terms/copyright policy record",
            )
        else:
            domains = governance_policy.get("allowed_domains")
            scopes = governance_policy.get("url_scopes")
            domains_valid = bool(
                isinstance(domains, list)
                and domains
                and len(domains) == len(set(domains))
                and all(_valid_domain(domain) for domain in domains)
            )
            domain_values = domains if isinstance(domains, list) else []
            normalized_domains = {
                str(domain).lower() for domain in domain_values if isinstance(domain, str)
            }
            scopes_valid = bool(
                isinstance(scopes, list)
                and scopes
                and len(scopes) == len(set(scopes))
                and domains_valid
                and all(_https_host(scope) in normalized_domains for scope in scopes)
            )
            raw_retention_days = governance_policy.get("raw_retention_days")
            max_requests = governance_policy.get("max_requests_per_run")
            legal_decisions = {
                "EXPLICIT_ALLOW",
                "PARTIAL_ALLOW",
                "RIGHTSHOLDER_PERMISSION",
                "SIGNED_LEGAL_ASSESSMENT",
                "PUBLIC_INFORMATION_LIMITED_USE",
            }
            if not (
                domains_valid
                and scopes_valid
                and governance_policy.get("robots_decision") in legal_decisions
                and governance_policy.get("terms_decision") in legal_decisions
                and governance_policy.get("copyright_decision") in legal_decisions
                and isinstance(raw_retention_days, int)
                and not isinstance(raw_retention_days, bool)
                and 1 <= raw_retention_days <= 90
                and governance_policy.get("storage_policy") == "PRIVATE_RAW"
                and governance_policy.get("display_policy") == "METADATA_FACTS_SHORT_SUMMARY_LINK"
                and isinstance(max_requests, int)
                and not isinstance(max_requests, bool)
                and 1 <= max_requests <= 100
            ):
                _issue(
                    issues,
                    "SOURCE_LEGAL_POLICY_INCOMPLETE",
                    f"{source_key} legal scope, retention, or display policy is invalid",
                )
            for ref_name in (
                "robots_evidence_ref",
                "terms_evidence_ref",
                "copyright_evidence_ref",
            ):
                _validate_ref(
                    governance_policy.get(ref_name),
                    root=root,
                    issues=issues,
                    cache=ref_cache,
                )
            if source.get("policy_sha256") != canonical_sha256(governance_policy):
                _issue(
                    issues,
                    "SOURCE_ADMISSION_MANIFEST_MISMATCH",
                    f"{source_key} governance policy hash differs from the admitted policy",
                )
            _validate_exact_json_export(
                source.get("policy_evidence_ref"),
                governance_policy,
                issue_code="SOURCE_ADMISSION_MANIFEST_MISMATCH",
                message=f"{source_key} admitted policy export differs from its runtime policy",
                root=root,
                issues=issues,
                cache=ref_cache,
            )
            connector_ref = source.get("connector_evidence_ref")
            config_ref = source.get("config_evidence_ref")
            _validate_ref(connector_ref, root=root, issues=issues, cache=ref_cache)
            _validate_ref(config_ref, root=root, issues=issues, cache=ref_cache)
            if (
                not isinstance(connector_ref, dict)
                or connector_ref.get("sha256") != source.get("connector_sha256")
                or not isinstance(config_ref, dict)
                or config_ref.get("sha256") != source.get("config_sha256")
            ):
                _issue(
                    issues,
                    "SOURCE_ADMISSION_MANIFEST_MISMATCH",
                    f"{source_key} connector/config artifact hashes are not bound",
                )
            domains = governance_policy.get("allowed_domains", [])
            scopes = governance_policy.get("url_scopes", [])
            canonical_endpoint = source.get("canonical_endpoint")
            normalized_domains = {
                str(domain).lower() for domain in domains if isinstance(domain, str)
            } if isinstance(domains, list) else set()
            if (
                not isinstance(source.get("display_name"), str)
                or not str(source.get("display_name", "")).strip()
                or source.get("access_mode") not in {"API", "RSS", "SITEMAP", "PUBLIC_LIST"}
                or _https_host(canonical_endpoint) not in normalized_domains
                or not isinstance(scopes, list)
                or not any(
                    isinstance(scope, str)
                    and isinstance(canonical_endpoint, str)
                    and canonical_endpoint.startswith(scope)
                    for scope in scopes
                )
            ):
                _issue(
                    issues,
                    "SOURCE_ADMISSION_MANIFEST_MISMATCH",
                    f"{source_key} display name, access mode, or canonical endpoint is invalid",
                )

        admission_entry = {
            "source_key": source.get("source_key"),
            "source_id": source.get("source_id"),
            "display_name": source.get("display_name"),
            "canonical_endpoint": source.get("canonical_endpoint"),
            "access_mode": source.get("access_mode"),
            "allowed_domains": governance_policy.get("allowed_domains")
            if isinstance(governance_policy, dict)
            else None,
            "url_scopes": governance_policy.get("url_scopes")
            if isinstance(governance_policy, dict)
            else None,
            "governance_owner_subject": source.get("governance_owner_subject"),
            "policy_version": source.get("policy_version"),
            "policy_sha256": source.get("policy_sha256"),
            "connector_version": source.get("connector_version"),
            "connector_sha256": source.get("connector_sha256"),
            "config_version": source.get("config_version"),
            "config_sha256": source.get("config_sha256"),
            "poll_interval_hours": source.get("poll_interval_hours"),
            "discovery_slo_hours": source.get("discovery_slo_hours"),
        }
        actual_manifest_entries.append(admission_entry)

        approvals = source.get("approvals", [])
        if not isinstance(approvals, list):
            approvals = []
        approval_map = {
            approval.get("stage"): approval for approval in approvals if isinstance(approval, dict)
        }
        if len(approvals) != 3 or set(approval_map) != {"COMPLIANCE", "LIVE_TRIAL", "PRODUCTION"}:
            _issue(
                issues,
                "SOURCE_APPROVAL_STAGES_INCOMPLETE",
                f"{source_key} must have three separate signed approval decisions",
            )
        for stage, approval in approval_map.items():
            signed_at = _parse_time(
                approval.get("signed_at"),
                field=f"{source_key}.{stage}.signed_at",
                issues=issues,
            )
            mfa_at = _parse_time(
                approval.get("mfa_verified_at"),
                field=f"{source_key}.{stage}.mfa_verified_at",
                issues=issues,
            )
            expires_at = _parse_time(
                approval.get("expires_at"),
                field=f"{source_key}.{stage}.expires_at",
                issues=issues,
            )
            if (
                approval.get("status") != "APPROVED"
                or approval.get("approver_subject") != subjects.get("LEO")
                or signed_at is None
                or mfa_at is None
                or started_at is None
                or ended_at is None
                or signed_at > started_at
                or mfa_at > signed_at
                or (signed_at - mfa_at).total_seconds() > 300
                or expires_at is None
                or expires_at < ended_at
            ):
                _issue(
                    issues,
                    "APPROVAL_NOT_WINDOW_VALID",
                    f"{source_key} {stage} approval is not signed and valid for the full window",
                )
            if signed_at is not None and mfa_at is not None and mfa_at > signed_at:
                _issue(
                    issues,
                    "APPROVAL_MFA_ORDER_INVALID",
                    f"{source_key} {stage} MFA occurs after the approval decision",
                )
            decision_id = approval.get("decision_id")
            if not _is_uuid7(decision_id) or str(decision_id) in decision_ids:
                _issue(
                    issues,
                    "APPROVAL_DECISION_ID_INVALID",
                    "approval decision IDs must be unique UUIDv7 values",
                )
            else:
                decision_ids.add(str(decision_id))
            try:
                approval_statement = {field: approval[field] for field in APPROVAL_AUDIT_FIELDS}
            except KeyError:
                approval_statement = {}
            expected_audit_sha256 = canonical_sha256(approval_statement)
            if approval.get("audit_record_sha256") != expected_audit_sha256:
                _issue(
                    issues,
                    "APPROVAL_AUDIT_REFERENCE_MISMATCH",
                    f"{source_key} {stage} audit hash differs from its structured decision",
                )
            if (
                any(
                    approval.get(field) != admission_entry.get(field)
                    for field in SOURCE_ADMISSION_ENTRY_FIELDS
                )
                or approval.get("admission_manifest_sha256")
                != _admission_manifest_sha256(evidence)
            ):
                _issue(
                    issues,
                    "APPROVAL_AUDIT_REFERENCE_MISMATCH",
                    f"{source_key} {stage} approval is not bound to the admitted source versions",
                )
            _validate_exact_json_export(
                approval.get("evidence_ref"),
                {**approval_statement, "audit_record_sha256": approval.get("audit_record_sha256")},
                issue_code="APPROVAL_AUDIT_REFERENCE_MISMATCH",
                message=f"{source_key} {stage} audit export differs from the decision",
                root=root,
                issues=issues,
                cache=ref_cache,
            )
        _validate_exact_json_export(
            source.get("health_evidence_ref"),
            {
                "window_id": evidence.get("window", {}).get("id")
                if isinstance(evidence.get("window"), dict)
                else None,
                "source_key": source_key,
                "source_id": source.get("source_id"),
                "health_summary": source.get("health_summary"),
            },
            issue_code="SOURCE_HEALTH_EXPORT_MISMATCH",
            message=f"{source_key} health export differs from its signed summary",
            root=root,
            issues=issues,
            cache=ref_cache,
        )

    manifest_statement = {
        "version": EXPECTED_ROSTER_VERSION,
        "source_count": 20,
        "entries": actual_manifest_entries,
    }
    expected_manifest_sha256 = canonical_sha256(manifest_statement)
    if (
        manifest_entries != actual_manifest_entries
        or manifest is None
        or manifest.get("manifest_sha256") != expected_manifest_sha256
    ):
        _issue(
            issues,
            "SOURCE_ADMISSION_MANIFEST_MISMATCH",
            "source runtime identities differ from the full admitted roster manifest",
        )
    if manifest is not None:
        _validate_exact_json_export(
            manifest.get("evidence_ref"),
            {**manifest_statement, "manifest_sha256": expected_manifest_sha256},
            issue_code="SOURCE_ADMISSION_MANIFEST_MISMATCH",
            message="the referenced source admission export differs from the signed manifest",
            root=root,
            issues=issues,
            cache=ref_cache,
        )
    return source_map


def _validate_runs(
    evidence: Payload,
    source_map: dict[str, Payload],
    subjects: dict[str, str],
    started_at: datetime | None,
    ended_at: datetime | None,
    *,
    root: Path,
    issues: list[Issue],
    ref_cache: set[tuple[str, str]],
) -> dict[str, Any]:
    runs = evidence.get("runs", [])
    if not isinstance(runs, list):
        _issue(issues, "RUN_PROVENANCE_NOT_AUTHORITATIVE", "runs must be an array")
        return {"included_run_count": 0}
    run_ids: set[str] = set()
    run_map: dict[str, Payload] = {}
    no_response_failure_ids: set[str] = set()
    runs_by_source: dict[str, list[Payload]] = {source_key: [] for source_key in source_map}
    window = evidence.get("window", {})
    window_id = window.get("id") if isinstance(window, dict) else None
    raw_segments = window.get("source_segments", []) if isinstance(window, dict) else []
    segment_map = {
        str(segment.get("segment_id")): segment
        for segment in raw_segments
        if isinstance(segment, dict) and isinstance(segment.get("segment_id"), str)
    }
    for run in runs:
        if not isinstance(run, dict):
            _issue(issues, "RUN_PROVENANCE_NOT_AUTHORITATIVE", "run is not an object")
            continue
        allowed_run_fields = {
            "run_id",
            "source_key",
            "source_id",
            "window_id",
            "segment_id",
            "policy_version",
            "policy_sha256",
            "connector_version",
            "connector_sha256",
            "config_version",
            "config_sha256",
            "environment",
            "origin",
            "evidence_class",
            "is_original",
            "included_in_metrics",
            "source_state_at_start",
            "scheduled_slot_at",
            "started_at",
            "ended_at",
            "outcome",
            "response_state",
            "request_url",
            "final_url",
            "request_count",
            "raw_response_sha256",
            "raw_evidence_ref",
            "response_metadata",
            "database_record_ref",
            "transport_failure_code",
            "failure_detected_at",
            "failure_detector_version",
            "failure_evidence_ref",
            "fake_success_detected",
            "fake_success_detected_at",
            "fake_success_rule_version",
            "fake_success_evidence_ref",
            "failure_cause_code",
            "recovered",
            "recovery_of_run_id",
            "recovery_verified_at",
            "recovery_evidence_ref",
        }
        if not set(run).issubset(allowed_run_fields):
            _issue(
                issues,
                "EVIDENCE_INLINE_CONTENT_FORBIDDEN",
                "run evidence may contain only provenance, counters, IDs, hashes, and refs",
            )
        run_id = run.get("run_id")
        if not isinstance(run_id, str) or run_id in run_ids:
            _issue(issues, "RUN_ID_DUPLICATE", "real run IDs must be present and unique")
            continue
        run_ids.add(run_id)
        run_map[run_id] = run
        source_key = run.get("source_key")
        if source_key not in source_map:
            _issue(
                issues, "RUN_SOURCE_NOT_APPROVED", f"run {run_id} references an unapproved source"
            )
            continue
        runs_by_source[str(source_key)].append(run)
        source = source_map[str(source_key)]
        segment = segment_map.get(str(run.get("segment_id")))
        expected_binding = _source_version_binding(source)
        actual_binding = {
            field: run.get(field)
            for field in (
                "source_id",
                "source_key",
                "policy_version",
                "policy_sha256",
                "connector_version",
                "connector_sha256",
                "config_version",
                "config_sha256",
            )
        }
        if (
            run.get("window_id") != window_id
            or segment is None
            or segment.get("source_id") != source.get("source_id")
            or segment.get("source_key") != source_key
            or segment.get("source_versions") != expected_binding
            or actual_binding != expected_binding
        ):
            _issue(
                issues,
                "RUN_WINDOW_VERSION_BINDING_MISMATCH",
                f"run {run_id} is not pinned to its immutable window segment and source versions",
            )
        response_state = run.get("response_state")
        expected_evidence_class = (
            "REAL_RESPONSE" if response_state == "RECEIVED" else "REAL_ATTEMPT"
        )
        if not (
            run.get("environment") == "PILOT"
            and run.get("origin") == "SCHEDULED"
            and response_state in {"RECEIVED", "NO_RESPONSE"}
            and run.get("evidence_class") == expected_evidence_class
            and run.get("is_original") is True
            and run.get("included_in_metrics") is True
            and run.get("source_state_at_start") == "ACTIVE"
        ):
            _issue(
                issues,
                "RUN_PROVENANCE_NOT_AUTHORITATIVE",
                f"run {run_id} is not an original PILOT SCHEDULED ACTIVE-source observation",
            )
        slot_at = _parse_time(
            run.get("scheduled_slot_at"), field=f"run.{run_id}.scheduled_slot_at", issues=issues
        )
        run_started = _parse_time(
            run.get("started_at"), field=f"run.{run_id}.started_at", issues=issues
        )
        run_ended = _parse_time(run.get("ended_at"), field=f"run.{run_id}.ended_at", issues=issues)
        if (
            started_at
            and ended_at
            and slot_at
            and run_started
            and run_ended
            and not (started_at <= slot_at <= run_started <= run_ended <= ended_at)
        ):
            _issue(issues, "RUN_OUTSIDE_WINDOW", f"run {run_id} is outside its immutable window")
        segment_started = (
            _parse_time(
                segment.get("started_at"),
                field=f"run.{run_id}.segment.started_at",
                issues=[],
            )
            if isinstance(segment, dict)
            else None
        )
        segment_ended = (
            _parse_time(
                segment.get("ended_at"),
                field=f"run.{run_id}.segment.ended_at",
                issues=[],
            )
            if isinstance(segment, dict)
            else None
        )
        if (
            slot_at is not None
            and run_started is not None
            and run_ended is not None
            and (
                segment_started is None
                or segment_ended is None
                or not (
                    segment_started <= slot_at <= run_started <= run_ended <= segment_ended
                )
            )
        ):
            _issue(
                issues,
                "RUN_WINDOW_VERSION_BINDING_MISMATCH",
                f"run {run_id} timestamps fall outside its pinned source segment",
            )
        if slot_at is not None and run_started is not None:
            lateness_seconds = (run_started - slot_at).total_seconds()
            if lateness_seconds < 0 or lateness_seconds > MAX_RUN_START_LATENESS_SECONDS:
                _issue(
                    issues,
                    "RUN_START_LATENESS_EXCEEDED",
                    f"run {run_id} did not start within the 15-minute scheduling bound",
                    lateness_seconds=lateness_seconds,
                )
        raw_ref = run.get("raw_evidence_ref")
        if response_state == "RECEIVED":
            _validate_ref(raw_ref, root=root, issues=issues, cache=ref_cache)
            if (
                isinstance(raw_ref, dict)
                and run.get("raw_response_sha256") != raw_ref.get("sha256")
            ):
                _issue(issues, "RAW_RESPONSE_HASH_MISMATCH", f"run {run_id} raw hash differs")
        elif raw_ref is not None or run.get("raw_response_sha256") is not None:
            _issue(
                issues,
                "NO_RESPONSE_FAILURE_INVALID",
                f"run {run_id} cannot claim raw response evidence when no response arrived",
            )
        if run.get("outcome") not in {"SUCCEEDED", "NO_UPDATE", "FAILED"}:
            _issue(issues, "RUN_OUTCOME_INVALID", f"run {run_id} has no honest terminal outcome")
        response_metadata = run.get("response_metadata")
        metadata_statement: Payload = {}
        metadata_valid = isinstance(response_metadata, dict) and set(response_metadata) == {
            "run_id",
            "source_key",
            "observed_at",
            "http_status",
            "response_bytes",
            "response_sha256",
            "response_headers_sha256",
            "conditional_request_used",
            "observation_method",
            "detector_version",
            "detector_sha256",
            "parsed_item_count",
            "new_item_count",
            "evidence_ref",
        }
        if isinstance(response_metadata, dict):
            metadata_statement = {
                field: response_metadata.get(field)
                for field in response_metadata
                if field != "evidence_ref"
            }
            observed_at = _parse_time(
                response_metadata.get("observed_at"),
                field=f"run.{run_id}.response_metadata.observed_at",
                issues=[],
            )
            http_status = response_metadata.get("http_status")
            response_bytes = response_metadata.get("response_bytes")
            metadata_valid = bool(
                metadata_valid
                and response_metadata.get("run_id") == run_id
                and response_metadata.get("source_key") == source_key
                and observed_at is not None
                and observed_at == run_ended
                and isinstance(http_status, int)
                and not isinstance(http_status, bool)
                and 0 <= http_status <= 599
                and isinstance(response_bytes, int)
                and not isinstance(response_bytes, bool)
                and response_bytes >= 0
                and response_metadata.get("response_sha256") == run.get("raw_response_sha256")
                and _valid_sha256(response_metadata.get("response_headers_sha256"))
                and isinstance(response_metadata.get("conditional_request_used"), bool)
                and not _placeholder_version(response_metadata.get("detector_version"))
                and _valid_sha256(response_metadata.get("detector_sha256"))
                and _validate_exact_json_export(
                    response_metadata.get("evidence_ref"),
                    metadata_statement,
                    issue_code="RUN_RESPONSE_METADATA_INVALID",
                    message="response metadata export differs from the signed run observation",
                    root=root,
                    issues=issues,
                    cache=ref_cache,
                )
            )
        outcome = run.get("outcome")
        method = response_metadata.get("observation_method") if isinstance(
            response_metadata, dict
        ) else None
        parsed_count = response_metadata.get("parsed_item_count") if isinstance(
            response_metadata, dict
        ) else None
        new_count = response_metadata.get("new_item_count") if isinstance(
            response_metadata, dict
        ) else None
        if response_state == "RECEIVED":
            if outcome == "NO_UPDATE":
                no_update_semantics = bool(
                    isinstance(response_metadata, dict)
                    and (
                        (
                            method == "HTTP_NOT_MODIFIED"
                            and response_metadata.get("http_status") == 304
                            and response_metadata.get("conditional_request_used") is True
                            and parsed_count is None
                            and new_count is None
                        )
                        or (
                            method == "PARSED_DISCOVERY_LIST"
                            and response_metadata.get("http_status") == 200
                            and isinstance(parsed_count, int)
                            and not isinstance(parsed_count, bool)
                            and parsed_count >= 0
                            and new_count == 0
                            and response_metadata.get("response_bytes", 0) > 0
                        )
                    )
                )
                if not metadata_valid or not no_update_semantics:
                    _issue(
                        issues,
                        "NO_UPDATE_RESPONSE_METADATA_INVALID",
                        f"run {run_id} NO_UPDATE is not proved by a 304 or parsed list",
                    )
            elif outcome == "SUCCEEDED":
                succeeded_semantics = bool(
                    isinstance(response_metadata, dict)
                    and method == "PARSED_DISCOVERY_LIST"
                    and response_metadata.get("http_status") == 200
                    and isinstance(parsed_count, int)
                    and not isinstance(parsed_count, bool)
                    and parsed_count > 0
                    and isinstance(new_count, int)
                    and not isinstance(new_count, bool)
                    and 0 < new_count <= parsed_count
                    and response_metadata.get("response_bytes", 0) > 0
                )
                if not metadata_valid or not succeeded_semantics:
                    _issue(
                        issues,
                        "RUN_RESPONSE_METADATA_INVALID",
                        f"run {run_id} success lacks parsed new-item response evidence",
                    )
            elif not metadata_valid:
                _issue(
                    issues,
                    "RUN_RESPONSE_METADATA_INVALID",
                    f"run {run_id} failure lacks a hash-bound response observation",
                )
        elif response_state == "NO_RESPONSE":
            failure_code = run.get("transport_failure_code")
            failure_detected_at = _parse_time(
                run.get("failure_detected_at"),
                field=f"run.{run_id}.failure_detected_at",
                issues=[],
            )
            failure_statement = {
                "run_id": run_id,
                "source_key": source_key,
                "failure_code": failure_code,
                "detected_at": run.get("failure_detected_at"),
                "detector_version": run.get("failure_detector_version"),
                "request_url": run.get("request_url"),
                "request_count": run.get("request_count"),
            }
            request_count = run.get("request_count")
            failure_valid = bool(
                outcome == "FAILED"
                and response_metadata is None
                and run.get("final_url") is None
                and failure_code
                in {"DNS_RESOLUTION_FAILED", "CONNECT_TIMEOUT", "READ_TIMEOUT"}
                and failure_detected_at is not None
                and run_started is not None
                and run_ended is not None
                and run_started <= failure_detected_at <= run_ended
                and not _placeholder_version(run.get("failure_detector_version"))
                and isinstance(request_count, int)
                and not isinstance(request_count, bool)
                and (
                    (failure_code == "DNS_RESOLUTION_FAILED" and request_count == 0)
                    or (failure_code != "DNS_RESOLUTION_FAILED" and request_count >= 1)
                )
                and _validate_exact_json_export(
                    run.get("failure_evidence_ref"),
                    failure_statement,
                    issue_code="NO_RESPONSE_FAILURE_INVALID",
                    message="no-response failure export differs from the scheduled DB run",
                    root=root,
                    issues=issues,
                    cache=ref_cache,
                )
            )
            if not failure_valid:
                _issue(
                    issues,
                    "NO_RESPONSE_FAILURE_INVALID",
                    f"run {run_id} lacks an honest DNS/timeout no-response failure record",
                )
            no_response_failure_ids.add(run_id)
        else:
            _issue(
                issues,
                "RUN_RESPONSE_METADATA_INVALID",
                f"run {run_id} lacks a recognized response state",
            )

        _validate_exact_json_export(
            run.get("database_record_ref"),
            _run_database_record_statement(run),
            issue_code="RUN_DATABASE_EXPORT_INVALID",
            message="run counters and response state differ from the authoritative DB export",
            root=root,
            issues=issues,
            cache=ref_cache,
        )
        transport_failure_fields = {
            "transport_failure_code",
            "failure_detected_at",
            "failure_detector_version",
            "failure_evidence_ref",
        }
        if response_state != "NO_RESPONSE" and any(
            field in run for field in transport_failure_fields
        ):
            _issue(
                issues,
                "NO_RESPONSE_FAILURE_INVALID",
                f"run {run_id} has no-response failure fields despite receiving a response",
            )
        fake_success_fields = {
            "fake_success_detected_at",
            "fake_success_rule_version",
            "fake_success_evidence_ref",
            "failure_cause_code",
        }
        fake_success_detected = run.get("fake_success_detected") is True
        if fake_success_detected:
            detected_at = _parse_time(
                run.get("fake_success_detected_at"),
                field=f"run.{run_id}.fake_success_detected_at",
                issues=[],
            )
            detection_statement = {
                "run_id": run_id,
                "source_key": source_key,
                "detected_at": run.get("fake_success_detected_at"),
                "rule_version": run.get("fake_success_rule_version"),
                "failure_cause_code": run.get("failure_cause_code"),
            }
            if (
                run.get("outcome") != "FAILED"
                or detected_at is None
                or run_started is None
                or run_ended is None
                or not (run_started <= detected_at <= run_ended)
                or not isinstance(run.get("fake_success_rule_version"), str)
                or not run.get("fake_success_rule_version")
                or not isinstance(run.get("failure_cause_code"), str)
                or not run.get("failure_cause_code")
                or not _validate_exact_json_export(
                    run.get("fake_success_evidence_ref"),
                    detection_statement,
                    issue_code="FALSE_SUCCESS_CAUSAL_EVIDENCE_MISSING",
                    message="false-success detection export does not exactly bind the failed run",
                    root=root,
                    issues=issues,
                    cache=ref_cache,
                )
            ):
                _issue(
                    issues,
                    "FALSE_SUCCESS_CAUSAL_EVIDENCE_MISSING",
                    f"run {run_id} false-success flag lacks causal detector evidence",
                )
        elif any(field in run for field in fake_success_fields):
            _issue(
                issues,
                "FALSE_SUCCESS_CAUSAL_EVIDENCE_MISSING",
                f"run {run_id} has false-success details without a true detection flag",
            )
        governance_policy = source_map[str(source_key)].get("governance_policy", {})
        allowed_domains = (
            governance_policy.get("allowed_domains", [])
            if isinstance(governance_policy, dict)
            else []
        )
        url_scopes = (
            governance_policy.get("url_scopes", []) if isinstance(governance_policy, dict) else []
        )
        request_url = run.get("request_url")
        final_url = run.get("final_url")
        request_count = run.get("request_count")
        max_requests = (
            governance_policy.get("max_requests_per_run")
            if isinstance(governance_policy, dict)
            else None
        )
        allowed_domain_values = allowed_domains if isinstance(allowed_domains, list) else []
        allowed_domain_set = {
            str(domain).lower() for domain in allowed_domain_values if isinstance(domain, str)
        }
        request_in_scope = bool(
            isinstance(url_scopes, list)
            and any(
                isinstance(scope, str)
                and isinstance(request_url, str)
                and request_url.startswith(scope)
                for scope in url_scopes
            )
        )
        final_in_scope = bool(
            isinstance(url_scopes, list)
            and any(
                isinstance(scope, str)
                and isinstance(final_url, str)
                and final_url.startswith(scope)
                for scope in url_scopes
            )
        )
        domain_valid = bool(
            _https_host(request_url) in allowed_domain_set
            and request_in_scope
            and (
                (
                    response_state == "RECEIVED"
                    and _https_host(final_url) in allowed_domain_set
                    and final_in_scope
                )
                or (response_state == "NO_RESPONSE" and final_url is None)
            )
        )
        if not domain_valid:
            _issue(
                issues,
                "RUN_DOMAIN_NOT_ALLOWED",
                f"run {run_id} left the signed URL scope or allowed domains",
            )
        if (
            not isinstance(request_count, int)
            or isinstance(request_count, bool)
            or not isinstance(max_requests, int)
            or request_count < (0 if response_state == "NO_RESPONSE" else 1)
            or request_count > max_requests
        ):
            _issue(
                issues,
                "RUN_FREQUENCY_POLICY_EXCEEDED",
                f"run {run_id} request count exceeds the signed source policy",
            )

    recovered_failure_ids: set[str] = set()
    for run_id, run in run_map.items():
        recovery_fields = {
            "recovery_of_run_id",
            "recovery_verified_at",
            "recovery_evidence_ref",
        }
        if run.get("recovered") is True:
            failed_run_id = run.get("recovery_of_run_id")
            failed_run = run_map.get(str(failed_run_id))
            recovery_started = _parse_time(
                run.get("started_at"), field=f"run.{run_id}.started_at", issues=[]
            )
            recovery_ended = _parse_time(
                run.get("ended_at"), field=f"run.{run_id}.ended_at", issues=[]
            )
            failed_ended = (
                _parse_time(
                    failed_run.get("ended_at"),
                    field=f"run.{failed_run_id}.ended_at",
                    issues=[],
                )
                if isinstance(failed_run, dict)
                else None
            )
            verified_at = _parse_time(
                run.get("recovery_verified_at"),
                field=f"run.{run_id}.recovery_verified_at",
                issues=[],
            )
            recovery_statement = {
                "run_id": run_id,
                "source_key": run.get("source_key"),
                "recovery_of_run_id": failed_run_id,
                "verified_at": run.get("recovery_verified_at"),
            }
            if (
                not isinstance(failed_run_id, str)
                or not isinstance(failed_run, dict)
                or failed_run.get("source_key") != run.get("source_key")
                or failed_run.get("outcome") != "FAILED"
                or not (
                    failed_run.get("fake_success_detected") is True
                    or failed_run.get("response_state") == "NO_RESPONSE"
                )
                or run.get("outcome") not in {"SUCCEEDED", "NO_UPDATE"}
                or failed_ended is None
                or recovery_started is None
                or recovery_ended is None
                or verified_at is None
                or not (failed_ended < recovery_started <= verified_at <= recovery_ended)
                or not _validate_exact_json_export(
                    run.get("recovery_evidence_ref"),
                    recovery_statement,
                    issue_code="RECOVERY_CAUSAL_LINK_INVALID",
                    message="recovery export does not exactly bind the prior failed run",
                    root=root,
                    issues=issues,
                    cache=ref_cache,
                )
            ):
                _issue(
                    issues,
                    "RECOVERY_CAUSAL_LINK_INVALID",
                    f"run {run_id} recovery does not causally follow a same-source failure",
                )
            elif isinstance(failed_run_id, str):
                recovered_failure_ids.add(failed_run_id)
        elif any(field in run for field in recovery_fields):
            _issue(
                issues,
                "RECOVERY_CAUSAL_LINK_INVALID",
                f"run {run_id} has recovery details without a true recovery flag",
            )
    for run_id, run in run_map.items():
        if (
            run.get("fake_success_detected") is True
            or run_id in no_response_failure_ids
        ) and run_id not in recovered_failure_ids:
            _issue(
                issues,
                "RECOVERY_CAUSAL_LINK_INVALID",
                f"failed run {run_id} has no later verified same-source recovery",
            )

    if started_at and ended_at:
        for source_key, source in source_map.items():
            poll_hours = source.get("poll_interval_hours")
            if not isinstance(poll_hours, int) or poll_hours <= 0:
                continue
            expected_slots = {
                started_at + timedelta(hours=offset) for offset in range(0, 168, poll_hours)
            }
            actual_slots: set[datetime] = set()
            for run in runs_by_source[source_key]:
                slot = _parse_time(
                    run.get("scheduled_slot_at"),
                    field=f"run.{run.get('run_id')}.scheduled_slot_at",
                    issues=[],
                )
                if slot is not None:
                    actual_slots.add(slot)
            if actual_slots != expected_slots or len(runs_by_source[source_key]) != len(
                expected_slots
            ):
                _issue(
                    issues,
                    "SCHEDULE_SLOT_COVERAGE_INCOMPLETE",
                    f"{source_key} lacks one or more scheduled execution records",
                    expected=len(expected_slots),
                    actual=len(runs_by_source[source_key]),
                )
            outcome_counts = {
                "SUCCEEDED": sum(
                    run.get("outcome") == "SUCCEEDED" for run in runs_by_source[source_key]
                ),
                "NO_UPDATE": sum(
                    run.get("outcome") == "NO_UPDATE" for run in runs_by_source[source_key]
                ),
                "FAILED": sum(run.get("outcome") == "FAILED" for run in runs_by_source[source_key]),
            }
            expected_health = {
                "scheduled_slot_count": len(expected_slots),
                "recorded_run_count": len(runs_by_source[source_key]),
                "succeeded_count": outcome_counts["SUCCEEDED"],
                "no_update_count": outcome_counts["NO_UPDATE"],
                "failed_count": outcome_counts["FAILED"],
                "false_success_count": sum(
                    run.get("fake_success_detected") is True for run in runs_by_source[source_key]
                ),
                "recovery_count": sum(
                    run.get("recovered") is True for run in runs_by_source[source_key]
                ),
            }
            if source.get("health_summary") != expected_health:
                _issue(
                    issues,
                    "SOURCE_HEALTH_SUMMARY_MISMATCH",
                    f"{source_key} health summary cannot be reproduced from its runs",
                )

    for source_key, source in source_map.items():
        source_runs = runs_by_source[source_key]
        successful_run_ids = {
            str(run.get("run_id")) for run in source_runs if run.get("outcome") == "SUCCEEDED"
        }
        evidence_state = source.get("window_evidence_state")
        chain_evidence = source.get("chain_evidence")
        if successful_run_ids:
            chain_run_id = (
                str(chain_evidence.get("run_id"))
                if isinstance(chain_evidence, dict)
                else ""
            )
            if (
                evidence_state != "REAL_CHAIN"
                or chain_run_id not in successful_run_ids
                or not _validate_authoritative_trace(
                    chain_evidence,
                    expected_source_key=source_key,
                    expected_run_id=chain_run_id,
                    expected_event_id=None,
                    issue_code="SOURCE_REAL_CHAIN_EVIDENCE_MISSING",
                    root=root,
                    issues=issues,
                    cache=ref_cache,
                )
            ):
                _issue(
                    issues,
                    "SOURCE_REAL_CHAIN_EVIDENCE_MISSING",
                    f"{source_key} has an update but no bidirectional real production chain",
                )
        elif (
            evidence_state != "NO_UPDATE"
            or chain_evidence is not None
            or not any(run.get("outcome") == "NO_UPDATE" for run in source_runs)
        ):
            _issue(
                issues,
                "SOURCE_NO_UPDATE_EVIDENCE_INVALID",
                f"{source_key} must have either a real chain or honest no-update health",
            )

    excluded = evidence.get("excluded_runs", [])
    excluded_ids: set[str] = set()
    excluded_map: dict[str, Payload] = {}
    if not isinstance(excluded, list):
        _issue(issues, "EXCLUDED_RUNS_INVALID", "excluded_runs must be an array")
    else:
        for excluded_run in excluded:
            if not isinstance(excluded_run, dict):
                _issue(issues, "EXCLUDED_RUNS_INVALID", "excluded run is not an object")
                continue
            excluded_id = excluded_run.get("run_id")
            if isinstance(excluded_id, str):
                excluded_ids.add(excluded_id)
                excluded_map[excluded_id] = excluded_run
            if excluded_run.get("included_in_metrics") is not False or (
                excluded_run.get("origin") not in {"REPLAY", "BACKFILL", "DRILL", "FIXTURE"}
                and excluded_run.get("environment") not in {"TEST", "FIXTURE"}
            ):
                _issue(issues, "EXCLUDED_RUNS_INVALID", "excluded run provenance is inconsistent")
            exclusion_statement = {
                "run_id": excluded_run.get("run_id"),
                "environment": excluded_run.get("environment"),
                "origin": excluded_run.get("origin"),
                "included_in_metrics": excluded_run.get("included_in_metrics"),
                "exclusion_reason_code": excluded_run.get("exclusion_reason_code"),
            }
            _validate_exact_json_export(
                excluded_run.get("evidence_ref"),
                exclusion_statement,
                issue_code="EXCLUDED_RUNS_INVALID",
                message="excluded-run export differs from its contamination classification",
                root=root,
                issues=issues,
                cache=ref_cache,
            )

    universe = evidence.get("run_universe")
    universe_valid = isinstance(universe, dict) and set(universe) == {
        "window_id",
        "export_environment",
        "exported_at",
        "exporter_subject",
        "database_identity",
        "transaction_watermark",
        "query_id",
        "query_sha256",
        "query_ref",
        "filters",
        "included_run_count",
        "included_run_ids",
        "excluded_run_count",
        "excluded_run_ids",
        "evidence_ref",
    }
    if isinstance(universe, dict):
        exported_at = _parse_time(
            universe.get("exported_at"), field="run_universe.exported_at", issues=[]
        )
        database_identity = universe.get("database_identity")
        transaction_watermark = universe.get("transaction_watermark")
        query_ref = universe.get("query_ref")
        query_target = _validate_ref(query_ref, root=root, issues=issues, cache=ref_cache)
        query_exact = False
        if query_target is not None:
            try:
                query_exact = (
                    query_target.read_text(encoding="utf-8") == EXPECTED_RUN_UNIVERSE_QUERY
                )
            except (OSError, UnicodeDecodeError):
                query_exact = False
        universe_valid = bool(
            universe_valid
            and universe.get("window_id") == window_id
            and universe.get("export_environment") == evidence.get("environment") == "PILOT"
            and universe.get("exporter_subject") == subjects.get("yinzi")
            and exported_at is not None
            and ended_at is not None
            and ended_at <= exported_at <= datetime.now(UTC)
            and isinstance(database_identity, dict)
            and set(database_identity)
            == {
                "system",
                "cluster_id",
                "database_name_sha256",
                "database_role_sha256",
                "revision",
            }
            and database_identity.get("system") == "POSTGRESQL"
            and _is_uuid7(database_identity.get("cluster_id"))
            and _valid_sha256(database_identity.get("database_name_sha256"))
            and _valid_sha256(database_identity.get("database_role_sha256"))
            and database_identity.get("revision") == EXPECTED_DATABASE_REVISION
            and isinstance(transaction_watermark, dict)
            and set(transaction_watermark) == {"snapshot", "transaction_id"}
            and isinstance(transaction_watermark.get("snapshot"), str)
            and re.fullmatch(
                r"[0-9]+:[0-9]+:(?:[0-9]+(?:,[0-9]+)*)?",
                transaction_watermark["snapshot"],
            )
            is not None
            and isinstance(transaction_watermark.get("transaction_id"), int)
            and not isinstance(transaction_watermark.get("transaction_id"), bool)
            and transaction_watermark.get("transaction_id", 0) > 0
            and universe.get("query_id") == "round17.authoritative_run_universe.v1"
            and isinstance(query_ref, dict)
            and universe.get("query_sha256") == query_ref.get("sha256")
            and query_exact
            and universe.get("filters") == RUN_UNIVERSE_FILTERS
            and universe.get("included_run_count") == len(run_ids)
            and universe.get("included_run_ids") == sorted(run_ids)
            and universe.get("excluded_run_count") == len(excluded_ids)
            and universe.get("excluded_run_ids") == sorted(excluded_ids)
        )
        universe_statement = {
            field: value for field, value in universe.items() if field != "evidence_ref"
        }
        if not _validate_exact_json_export(
            universe.get("evidence_ref"),
            universe_statement,
            issue_code="RUN_UNIVERSE_EXPORT_MISMATCH",
            message="run-universe DB export differs from its signed transaction snapshot",
            root=root,
            issues=issues,
            cache=ref_cache,
        ):
            universe_valid = False
    if not universe_valid:
        _issue(
            issues,
            "RUN_UNIVERSE_EXPORT_MISMATCH",
            "the transactionally exported run universe is incomplete or not authoritative",
        )

    drill = evidence.get("failure_drill")
    drill_valid = isinstance(drill, dict) and set(drill) == {
        "drill_id",
        "source_key",
        "source_id",
        "run_id",
        "environment",
        "fault_mode",
        "approved_by_subject",
        "approval_decision_id",
        "approved_at",
        "mfa_verified_at",
        "executed_at",
        "completed_at",
        "real_source_contacted",
        "test_endpoint_used",
        "result",
        "alert_observed",
        "pause_observed",
        "replay_observed",
        "approval_ref",
        "result_ref",
    }
    if isinstance(drill, dict):
        approved_at = _parse_time(
            drill.get("approved_at"), field="failure_drill.approved_at", issues=[]
        )
        drill_mfa_at = _parse_time(
            drill.get("mfa_verified_at"), field="failure_drill.mfa_verified_at", issues=[]
        )
        executed_at = _parse_time(
            drill.get("executed_at"), field="failure_drill.executed_at", issues=[]
        )
        completed_at = _parse_time(
            drill.get("completed_at"), field="failure_drill.completed_at", issues=[]
        )
        drill_source = source_map.get(str(drill.get("source_key")))
        excluded_drill = excluded_map.get(str(drill.get("run_id")))
        approval_statement = {
            field: drill.get(field)
            for field in (
                "drill_id",
                "source_key",
                "source_id",
                "run_id",
                "environment",
                "fault_mode",
                "approved_by_subject",
                "approval_decision_id",
                "approved_at",
                "mfa_verified_at",
                "real_source_contacted",
                "test_endpoint_used",
            )
        }
        result_statement = {
            field: drill.get(field)
            for field in (
                "drill_id",
                "run_id",
                "executed_at",
                "completed_at",
                "result",
                "alert_observed",
                "pause_observed",
                "replay_observed",
                "real_source_contacted",
            )
        }
        drill_valid = bool(
            drill_valid
            and _is_uuid7(drill.get("drill_id"))
            and _is_uuid7(drill.get("approval_decision_id"))
            and drill_source is not None
            and drill.get("source_id") == drill_source.get("source_id")
            and drill.get("environment") == "TEST"
            and drill.get("fault_mode")
            in {"CONNECTOR_TIMEOUT", "DOM_BREAK", "PARSER_FAILURE", "HTTP_503"}
            and drill.get("approved_by_subject") == subjects.get("LEO")
            and approved_at is not None
            and drill_mfa_at is not None
            and drill_mfa_at <= approved_at
            and (approved_at - drill_mfa_at).total_seconds() <= 300
            and executed_at is not None
            and completed_at is not None
            and started_at is not None
            and ended_at is not None
            and started_at <= approved_at <= executed_at <= completed_at <= ended_at
            and drill.get("real_source_contacted") is False
            and drill.get("test_endpoint_used") is True
            and drill.get("result") == "PASSED"
            and drill.get("alert_observed") is True
            and drill.get("pause_observed") is True
            and drill.get("replay_observed") is True
            and isinstance(excluded_drill, dict)
            and excluded_drill.get("environment") == "TEST"
            and excluded_drill.get("origin") == "DRILL"
            and _validate_exact_json_export(
                drill.get("approval_ref"),
                approval_statement,
                issue_code="FAILURE_DRILL_INVALID",
                message="fault-drill approval export differs from LEO's decision",
                root=root,
                issues=issues,
                cache=ref_cache,
            )
            and _validate_exact_json_export(
                drill.get("result_ref"),
                result_statement,
                issue_code="FAILURE_DRILL_INVALID",
                message="fault-drill result export does not prove alert, pause, and replay",
                root=root,
                issues=issues,
                cache=ref_cache,
            )
        )
    if not drill_valid:
        _issue(
            issues,
            "FAILURE_DRILL_INVALID",
            "one LEO-approved, non-contacting TEST fault drill with result evidence is required",
        )
    metrics = evidence.get("metrics", {})
    input_run_ids = metrics.get("input_run_ids", []) if isinstance(metrics, dict) else []
    input_set = set(input_run_ids) if isinstance(input_run_ids, list) else set()
    if (
        not isinstance(input_run_ids, list)
        or len(input_set) != len(input_run_ids)
        or input_set != run_ids
        or input_set & excluded_ids
    ):
        _issue(
            issues,
            "METRIC_INPUT_CONTAMINATION",
            "metric input IDs must equal only the authoritative scheduled run set",
        )
    return {"included_run_count": len(run_ids), "excluded_run_count": len(excluded_ids)}


def _gold_collections(gold: Payload) -> list[tuple[str, list[Payload]]]:
    result: list[tuple[str, list[Payload]]] = []
    for name in CANDIDATE_GOLD_COUNTS:
        value = gold.get(name, [])
        result.append((name, value if isinstance(value, list) else []))
    return result


def _valid_sha256(value: object) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _gold_label(annotation: object, role: str) -> Payload | None:
    if not isinstance(annotation, dict):
        return None
    label = annotation.get(role)
    return label if isinstance(label, dict) else None


def _recompute_nominal_agreement(
    pairs: list[tuple[str, str]], coefficient_name: object
) -> tuple[float, float]:
    if not pairs:
        return 0.0, 0.0
    observed = sum(left == right for left, right in pairs) / len(pairs)
    categories = sorted({label for pair in pairs for label in pair})
    if coefficient_name == "COHEN_KAPPA":
        left_counts = {label: 0 for label in categories}
        right_counts = {label: 0 for label in categories}
        for left, right in pairs:
            left_counts[left] += 1
            right_counts[right] += 1
        expected = sum(
            (left_counts[label] / len(pairs)) * (right_counts[label] / len(pairs))
            for label in categories
        )
    elif coefficient_name == "GWET_AC1":
        if len(categories) <= 1:
            expected = 0.0
        else:
            pooled = {
                label: sum(
                    int(left == label) + int(right == label) for left, right in pairs
                )
                / (2 * len(pairs))
                for label in categories
            }
            expected = sum(value * (1 - value) for value in pooled.values()) / (
                len(categories) - 1
            )
    else:
        return observed, 0.0
    coefficient = 1.0 if math.isclose(expected, 1.0) and math.isclose(observed, 1.0) else (
        (observed - expected) / (1 - expected) if not math.isclose(expected, 1.0) else -1.0
    )
    return observed, coefficient


def _validate_gold_release_binding(
    gold: Payload,
    subjects: dict[str, str],
    *,
    root: Path,
    issues: list[Issue],
    ref_cache: set[tuple[str, str]],
) -> str | None:
    release_id = gold.get("gold_release_id")
    db_manifest_sha256 = gold.get("db_manifest_sha256")
    if not _is_uuid7(release_id) or not _valid_sha256(db_manifest_sha256):
        _issue(
            issues,
            "GOLD_RELEASE_BINDING_MISSING",
            "gold must bind a UUIDv7 round17_gold_release row and its database manifest hash",
        )
        return None
    audit_target = _validate_ref(
        gold.get("release_audit_ref"), root=root, issues=issues, cache=ref_cache
    )
    if audit_target is None:
        _issue(
            issues,
            "GOLD_RELEASE_BINDING_MISSING",
            "gold release needs a retrievable immutable audit export",
        )
        return str(release_id)
    try:
        audit_statement = json.loads(audit_target.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        audit_statement = None
    expected_audit = {
        "audit_action": "ROUND17_GOLD_RELEASE_FROZEN",
        "gold_release_id": release_id,
        "version": gold.get("version"),
        "roster_version": gold.get("roster_version"),
        "gold_definition_version": EXPECTED_GOLD_VERSION,
        "db_manifest_sha256": db_manifest_sha256,
        "status": "FROZEN",
        "frozen_by_subject": subjects.get("LEO"),
        "frozen_at": gold.get("released_at"),
    }
    if audit_statement != expected_audit:
        _issue(
            issues,
            "GOLD_RELEASE_AUDIT_MISMATCH",
            "gold release audit export does not exactly bind the frozen database release",
        )
    return str(release_id)


def _validate_collection_identity(
    collection_name: str,
    record: Payload,
    *,
    document_ids: set[str],
    event_cluster_ids: set[str],
    release_id: str | None,
    issues: list[Issue],
) -> None:
    expected_kind = {
        "documents": "DOCUMENT",
        "duplicate_pairs": "DUPLICATE_PAIR",
        "event_clusters": "EVENT_CLUSTER",
        "claim_evidence_annotations": "CLAIM_EVIDENCE",
        "search_questions": "SEARCH_QUESTION",
    }[collection_name]
    valid = record.get("sample_kind") == expected_kind and record.get(
        "gold_release_id"
    ) == release_id
    if collection_name == "documents":
        valid = valid and _is_uuid7(record.get("document_id"))
    elif collection_name == "duplicate_pairs":
        left = record.get("left_document_id")
        right = record.get("right_document_id")
        valid = bool(
            valid
            and _is_uuid7(left)
            and _is_uuid7(right)
            and left != right
            and left in document_ids
            and right in document_ids
            and record.get("relationship_code")
            in {"SAME_EVENT", "DIFFERENT_EVENT", "FOLLOW_UP"}
        )
    elif collection_name == "event_clusters":
        members = record.get("member_document_ids")
        valid = bool(
            valid
            and isinstance(members, list)
            and members
            and len(members) == len(set(members))
            and all(_is_uuid7(member) and member in document_ids for member in members)
            and record.get("high_value") is True
        )
    elif collection_name == "claim_evidence_annotations":
        valid = bool(
            valid
            and _is_uuid7(record.get("claim_id"))
            and _is_uuid7(record.get("evidence_id"))
            and isinstance(record.get("fact_kind"), str)
            and record.get("fact_kind")
        )
    else:
        expected_events = record.get("expected_event_cluster_ids")
        valid = bool(
            valid
            and _is_uuid7(record.get("question_id"))
            and isinstance(expected_events, list)
            and expected_events
            and len(expected_events) == len(set(expected_events))
            and all(event_id in event_cluster_ids for event_id in expected_events)
        )
    if not valid:
        _issue(
            issues,
            "GOLD_COLLECTION_RECORD_INVALID",
            f"{collection_name} record lacks its authoritative sample identity or members",
        )


def _validate_gold(
    gold: Payload,
    evidence: Payload,
    subjects: dict[str, str],
    source_map: dict[str, Payload],
    *,
    root: Path,
    issues: list[Issue],
    ref_cache: set[tuple[str, str]],
) -> dict[str, Any]:
    expected_hash = canonical_sha256(gold, excluded_keys={"manifest_sha256"})
    if gold.get("manifest_sha256") != expected_hash:
        _issue(issues, "GOLD_MANIFEST_HASH_MISMATCH", "gold manifest canonical hash differs")
    gold_ref = evidence.get("gold_manifest", {})
    if not isinstance(gold_ref, dict) or (
        gold_ref.get("version") != EXPECTED_GOLD_VERSION or gold_ref.get("sha256") != expected_hash
    ):
        _issue(
            issues, "GOLD_VERSION_HASH_MISMATCH", "pilot evidence does not bind this gold release"
        )
    if (
        gold.get("version") != EXPECTED_GOLD_VERSION
        or gold.get("roster_version") != EXPECTED_ROSTER_VERSION
        or gold.get("metrics_definition_version") != EXPECTED_METRICS_VERSION
        or gold.get("released_by_subject") != subjects.get("LEO")
    ):
        _issue(issues, "GOLD_RELEASE_NOT_APPROVED", "gold release version or LEO approval differs")

    release_id = _validate_gold_release_binding(
        gold, subjects, root=root, issues=issues, ref_cache=ref_cache
    )

    raw_documents = gold.get("documents", [])
    document_ids = {
        str(record.get("document_id"))
        for record in raw_documents
        if isinstance(record, dict) and _is_uuid7(record.get("document_id"))
    } if isinstance(raw_documents, list) else set()
    raw_events = gold.get("event_clusters", [])
    event_cluster_ids = {
        str(record.get("id"))
        for record in raw_events
        if isinstance(record, dict)
        and isinstance(record.get("id"), str)
        and record.get("high_value") is True
    } if isinstance(raw_events, list) else set()

    seen_ids: set[str] = set()
    source_coverage: set[str] = set()
    key_safety: list[Payload] = []
    digital: list[Payload] = []
    digital_secondary_count = 0
    counts: dict[str, int] = {}
    for collection_name, records in _gold_collections(gold):
        counts[collection_name] = len(records)
        if len(records) != CANDIDATE_GOLD_COUNTS[collection_name]:
            _issue(
                issues,
                "GOLD_MINIMUM_NOT_MET",
                f"{collection_name} must contain exactly the frozen phase-one sample size",
                required=CANDIDATE_GOLD_COUNTS[collection_name],
                actual=len(records),
            )
        for record in records:
            if not isinstance(record, dict):
                _issue(issues, "GOLD_RECORD_INVALID", f"{collection_name} contains a non-object")
                continue
            record_id = record.get("id")
            if not isinstance(record_id, str) or record_id in seen_ids:
                _issue(issues, "GOLD_RECORD_ID_INVALID", "gold record IDs must be unique")
            else:
                seen_ids.add(record_id)
            _validate_collection_identity(
                collection_name,
                record,
                document_ids=document_ids,
                event_cluster_ids=event_cluster_ids,
                release_id=release_id,
                issues=issues,
            )
            source_key = record.get("source_key")
            if source_key not in source_map:
                _issue(
                    issues, "GOLD_SOURCE_NOT_APPROVED", "gold record uses a source outside the 20"
                )
            else:
                source_coverage.add(str(source_key))
            content_hash = record.get("content_sha256")
            if not _valid_sha256(content_hash):
                _issue(issues, "GOLD_CONTENT_HASH_INVALID", "gold record lacks a content hash")
            _validate_ref(
                record.get("authorization_ref"), root=root, issues=issues, cache=ref_cache
            )
            if record.get("key_safety") is True:
                key_safety.append(record)
            if record.get("domain") == "DIGITAL":
                digital.append(record)
            annotation = record.get("annotation")
            primary_label = _gold_label(annotation, "primary")
            secondary_label = _gold_label(annotation, "secondary")
            arbitration = _gold_label(annotation, "arbitration")
            if primary_label is None or not _valid_sha256(primary_label.get("label_sha256")):
                _issue(
                    issues,
                    "GOLD_LABEL_HASH_INVALID",
                    "every gold sample needs a non-empty lowercase SHA-256 primary label",
                )
            if secondary_label is not None and not _valid_sha256(
                secondary_label.get("label_sha256")
            ):
                _issue(
                    issues,
                    "GOLD_LABEL_HASH_INVALID",
                    "every secondary gold label must have a non-empty lowercase SHA-256 hash",
                )
            if arbitration is not None and not _valid_sha256(
                arbitration.get("resolved_label_sha256")
            ):
                _issue(
                    issues,
                    "GOLD_LABEL_HASH_INVALID",
                    "every arbitration needs a non-empty lowercase SHA-256 resolved label",
                )
            if record.get("domain") == "DIGITAL":
                if primary_label is None or primary_label.get(
                    "annotator_subject"
                ) != subjects.get("baixuejiao"):
                    _issue(
                        issues,
                        "DIGITAL_PRIMARY_LABEL_INVALID",
                        "baixuejiao must be the digital primary annotator",
                    )
                if (
                    secondary_label is not None
                    and secondary_label.get("annotator_subject") == subjects.get("yinzi")
                    and _valid_sha256(secondary_label.get("label_sha256"))
                    and secondary_label.get("blinded") is True
                ):
                    digital_secondary_count += 1
    if source_coverage != set(source_map):
        _issue(issues, "GOLD_SOURCE_COVERAGE_INCOMPLETE", "gold set does not cover all 20 sources")

    agreement_pairs: list[tuple[str, str]] = []
    for record in key_safety:
        annotation = record.get("annotation")
        primary = _gold_label(annotation, "primary")
        secondary = _gold_label(annotation, "secondary")
        arbitration = _gold_label(annotation, "arbitration")
        primary_code = primary.get("label_code") if primary is not None else None
        secondary_code = secondary.get("label_code") if secondary is not None else None
        primary_hash = primary.get("label_sha256") if primary is not None else None
        secondary_hash = secondary.get("label_sha256") if secondary is not None else None
        if not (
            record.get("domain") == "SAFETY"
            and primary is not None
            and secondary is not None
            and primary.get("annotator_subject") == subjects.get("yinzi")
            and secondary.get("annotator_subject") == subjects.get("baixuejiao")
            and isinstance(primary_code, str)
            and bool(primary_code)
            and isinstance(secondary_code, str)
            and bool(secondary_code)
            and _valid_sha256(primary.get("label_sha256"))
            and _valid_sha256(secondary.get("label_sha256"))
            and secondary.get("blinded") is True
        ):
            _issue(
                issues,
                "KEY_SAFETY_DOUBLE_LABEL_MISSING",
                "every key safety sample needs yinzi/baixuejiao blind labels",
            )
        else:
            agreement_pairs.append(
                (f"{primary_code}:{primary_hash}", f"{secondary_code}:{secondary_hash}")
            )
        if (
            isinstance(primary_code, str)
            and isinstance(secondary_code, str)
            and isinstance(primary_hash, str)
            and isinstance(secondary_hash, str)
        ):
            labels_disagree = primary_code != secondary_code or primary_hash != secondary_hash
            resolved_signature = (
                (
                    arbitration.get("resolved_label_code"),
                    arbitration.get("resolved_label_sha256"),
                )
                if arbitration is not None
                else None
            )
            if labels_disagree and (
                arbitration is None
                or arbitration.get("arbitrator_subject") != subjects.get("LEO")
                or not _valid_sha256(arbitration.get("resolved_label_sha256"))
                or resolved_signature
                not in {(primary_code, primary_hash), (secondary_code, secondary_hash)}
            ):
                _issue(
                    issues,
                    "GOLD_ARBITRATION_MISSING",
                    "every key safety disagreement needs LEO arbitration",
                )
    if len(key_safety) < 20:
        _issue(
            issues,
            "KEY_SAFETY_SAMPLE_INSUFFICIENT",
            "gold set needs at least 20 critical safety samples",
            required=20,
            actual=len(key_safety),
        )
    statistics = gold.get("agreement_statistics", {})
    raw_agreement = (
        _finite_number(statistics.get("raw_agreement")) if isinstance(statistics, dict) else None
    )
    coefficient = (
        _finite_number(statistics.get("coefficient")) if isinstance(statistics, dict) else None
    )
    coefficient_name = statistics.get("coefficient_name") if isinstance(statistics, dict) else None
    derived_agreement, derived_coefficient = _recompute_nominal_agreement(
        agreement_pairs, coefficient_name
    )
    if not isinstance(statistics, dict) or (
        statistics.get("key_safety_count") != len(key_safety)
        or len(agreement_pairs) != len(key_safety)
        or raw_agreement is None
        or not math.isclose(raw_agreement, derived_agreement, rel_tol=0.0, abs_tol=1e-12)
        or derived_agreement < 0.95
        or coefficient_name not in {"COHEN_KAPPA", "GWET_AC1"}
        or coefficient is None
        or not math.isclose(coefficient, derived_coefficient, rel_tol=0.0, abs_tol=1e-12)
        or derived_coefficient < 0.80
    ):
        _issue(
            issues,
            "GOLD_AGREEMENT_GATE_FAILED",
            "key safety agreement must be reproducible, >=95%, with coefficient >=0.80",
        )
    if isinstance(statistics, dict):
        _validate_ref(statistics.get("evidence_ref"), root=root, issues=issues, cache=ref_cache)
    if not digital:
        _issue(
            issues,
            "DIGITAL_SAMPLE_MISSING",
            "digital secondary review cannot be evaded with a zero-sized digital collection",
        )
    required_digital_secondary = max(1, math.ceil(len(digital) * 0.20))
    if digital_secondary_count < required_digital_secondary:
        _issue(
            issues,
            "DIGITAL_SECONDARY_REVIEW_INSUFFICIENT",
            "yinzi must blindly re-label at least 20% of digital gold records",
            required=required_digital_secondary,
            actual=digital_secondary_count,
        )

    evaluations = evidence.get("event_evaluations", [])
    evaluation_ids = [
        evaluation.get("gold_event_id")
        for evaluation in evaluations
        if isinstance(evaluation, dict)
        and isinstance(evaluation.get("gold_event_id"), str)
    ] if isinstance(evaluations, list) else []
    if (
        len(event_cluster_ids) != CANDIDATE_GOLD_COUNTS["event_clusters"]
        or len(evaluation_ids) != len(event_cluster_ids)
        or len(evaluation_ids) != len(set(evaluation_ids))
        or set(evaluation_ids) != event_cluster_ids
    ):
        _issue(
            issues,
            "GOLD_EVENT_SET_MISMATCH",
            "event_evaluations must exactly equal the frozen 100 high-value gold event clusters",
        )
    return {
        "counts": counts,
        "key_safety_count": len(key_safety),
        "digital_secondary_reviewed": digital_secondary_count,
        "digital_secondary_required": required_digital_secondary,
        "event_denominator_count": len(event_cluster_ids),
        "gold_release_id": release_id,
    }


def _wilson_95(numerator: int, denominator: int) -> list[float]:
    if denominator <= 0:
        return [0.0, 0.0]
    z = 1.959963984540054
    estimate = numerator / denominator
    z_squared = z * z
    denominator_term = 1 + z_squared / denominator
    center = (estimate + z_squared / (2 * denominator)) / denominator_term
    margin = (
        z
        * math.sqrt(
            estimate * (1 - estimate) / denominator + z_squared / (4 * denominator * denominator)
        )
        / denominator_term
    )
    return [center - margin, center + margin]


def _rate_result(numerator: int, denominator: int, minimum: float) -> dict[str, Any]:
    estimate = numerator / denominator if denominator else 0.0
    return {
        "numerator": numerator,
        "denominator": denominator,
        "point_estimate": estimate,
        "minimum": minimum,
        "wilson_95": _wilson_95(numerator, denominator),
        "passed": denominator > 0 and estimate >= minimum,
    }


def _nearest_rank_p95(values: list[int]) -> int:
    ordered = sorted(values)
    return ordered[max(0, math.ceil(0.95 * len(ordered)) - 1)]


def _shanghai_window_dates(started_at: datetime, ended_at: datetime) -> set[str]:
    """Return local calendar dates touched by the half-open observation window [start, end)."""

    if ended_at <= started_at:
        return set()
    shanghai = ZoneInfo("Asia/Shanghai")
    first_date = started_at.astimezone(shanghai).date()
    last_date = (ended_at - timedelta(microseconds=1)).astimezone(shanghai).date()
    dates: set[str] = set()
    cursor = first_date
    while cursor <= last_date:
        dates.add(cursor.isoformat())
        cursor += timedelta(days=1)
    return dates


def _validate_metrics(
    evidence: Payload,
    gold: Payload,
    subjects: dict[str, str],
    source_map: dict[str, Payload],
    started_at: datetime | None,
    ended_at: datetime | None,
    *,
    root: Path,
    issues: list[Issue],
    ref_cache: set[tuple[str, str]],
) -> dict[str, Any]:
    metrics = evidence.get("metrics", {})
    if not isinstance(metrics, dict):
        _issue(issues, "METRICS_INVALID", "metrics must be an object")
        return {}
    window = evidence.get("window", {})
    if not isinstance(window, dict) or metrics.get("window_id") != window.get("id"):
        _issue(issues, "METRIC_WINDOW_MISMATCH", "metrics are not bound to this window")

    event_evaluations = evidence.get("event_evaluations", [])
    if not isinstance(event_evaluations, list) or not event_evaluations:
        _issue(issues, "NORTH_STAR_DENOMINATOR_EMPTY", "human event enumeration is empty")
        event_evaluations = []
    event_ids: set[str] = set()
    platform_event_ids: set[str] = set()
    runs = evidence.get("runs", [])
    run_map = {
        str(run.get("run_id")): run
        for run in runs
        if isinstance(run, dict) and isinstance(run.get("run_id"), str)
    } if isinstance(runs, list) else {}
    raw_gold_clusters = gold.get("event_clusters", [])
    gold_cluster_map = {
        str(cluster.get("id")): cluster
        for cluster in raw_gold_clusters
        if isinstance(cluster, dict) and isinstance(cluster.get("id"), str)
    } if isinstance(raw_gold_clusters, list) else {}
    north_star_numerator = 0
    current_claim_ids_in_events: set[str] = set()
    derived = {
        "discovery_within_slo": 0,
        "correct_eventization": 0,
        "searchable_readable": 0,
    }
    for event in event_evaluations:
        if not isinstance(event, dict):
            _issue(issues, "EVENT_GOLD_INVALID", "window event evaluation is not an object")
            continue
        allowed_event_fields = {
            "gold_event_id",
            "source_key",
            "enumerated_by_subject",
            "high_value",
            "platform_event_id",
            "source_run_id",
            "trace_evidence_ref",
            "predicate_facts",
            "predicate_results",
            "predicate_evidence_ref",
            "enumeration_evidence_ref",
        }
        if set(event) != allowed_event_fields:
            _issue(
                issues,
                "EVENT_PREDICATE_FACTS_INVALID",
                "event evaluation must use structured predicate facts, not naked booleans",
            )
        event_id = event.get("gold_event_id")
        if not isinstance(event_id, str) or event_id in event_ids:
            _issue(issues, "EVENT_GOLD_ID_INVALID", "window gold event IDs must be unique")
        else:
            event_ids.add(event_id)
        enumeration_target = _validate_ref(
            event.get("enumeration_evidence_ref"),
            root=root,
            issues=issues,
            cache=ref_cache,
        )
        expected_enumeration = {
            "gold_event_id": event_id,
            "source_key": event.get("source_key"),
            "enumerated_by_subject": event.get("enumerated_by_subject"),
        }
        if enumeration_target is not None:
            try:
                referenced_enumeration = json.loads(
                    enumeration_target.read_text(encoding="utf-8")
                )
            except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                referenced_enumeration = None
            if referenced_enumeration != expected_enumeration:
                _issue(
                    issues,
                    "EVENT_ENUMERATION_NOT_AUTHORITATIVE",
                    "event enumeration reference does not exactly bind its gold event, "
                    "source, and human enumerator",
                )
        if (
            event.get("enumerated_by_subject") != subjects.get("baixuejiao")
            or event.get("source_key") not in source_map
            or event.get("high_value") is not True
        ):
            _issue(
                issues,
                "EVENT_GOLD_NOT_INDEPENDENT_HUMAN",
                "each denominator event needs independent baixuejiao enumeration",
            )
        gold_cluster = gold_cluster_map.get(str(event_id))
        if (
            not isinstance(gold_cluster, dict)
            or gold_cluster.get("source_key") != event.get("source_key")
            or gold_cluster.get("high_value") is not True
        ):
            _issue(
                issues,
                "EVENT_GOLD_SOURCE_MISMATCH",
                "event source/high-value status differs from its frozen gold cluster",
            )

        platform_event_id = event.get("platform_event_id")
        source_run_id = event.get("source_run_id")
        trace_ref = event.get("trace_evidence_ref")
        validated_trace_statement: Payload | None = None
        trace_valid = False
        if platform_event_id is None:
            if source_run_id is not None or trace_ref is not None:
                _issue(
                    issues,
                    "EVENT_TRACE_NOT_AUTHORITATIVE",
                    "an event trace cannot exist without a platform Event identifier",
                )
        else:
            event_run = run_map.get(str(source_run_id))
            binding_valid = bool(
                _is_uuid7(platform_event_id)
                and platform_event_id not in platform_event_ids
                and isinstance(source_run_id, str)
                and isinstance(event_run, dict)
                and event_run.get("source_key") == event.get("source_key")
                and event_run.get("outcome") == "SUCCEEDED"
                and event_run.get("origin") == "SCHEDULED"
                and event_run.get("environment") == "PILOT"
                and event_run.get("evidence_class") == "REAL_RESPONSE"
                and event_run.get("included_in_metrics") is True
            )
            if _is_uuid7(platform_event_id):
                if platform_event_id in platform_event_ids:
                    _issue(
                        issues,
                        "EVENT_TRACE_NOT_AUTHORITATIVE",
                        "platform Event identifiers must be unique in the enumerated set",
                    )
                platform_event_ids.add(platform_event_id)

            trace_target = _validate_ref(
                trace_ref,
                root=root,
                issues=issues,
                cache=ref_cache,
            )
            trace: object = None
            if trace_target is not None and isinstance(trace_ref, dict):
                try:
                    trace_statement = json.loads(trace_target.read_text(encoding="utf-8"))
                except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                    trace_statement = None
                if isinstance(trace_statement, dict):
                    validated_trace_statement = trace_statement
                    trace = {**trace_statement, "evidence_ref": trace_ref}
            trace_valid = bool(
                isinstance(source_run_id, str)
                and _validate_authoritative_trace(
                    trace,
                    expected_source_key=str(event.get("source_key")),
                    expected_run_id=source_run_id,
                    expected_event_id=str(platform_event_id),
                    issue_code="EVENT_TRACE_NOT_AUTHORITATIVE",
                    root=root,
                    issues=issues,
                    cache=ref_cache,
                )
            )
            if not binding_valid or not trace_valid:
                _issue(
                    issues,
                    "EVENT_TRACE_NOT_AUTHORITATIVE",
                    "platform Event must bind one included successful real source run "
                    "from the same source",
                )
        raw_facts = event.get("predicate_facts")
        submitted_results = event.get("predicate_results")
        facts: Payload
        if isinstance(raw_facts, dict) and set(raw_facts) == EVENT_PREDICATE_FACT_FIELDS:
            facts = raw_facts
        else:
            _issue(
                issues,
                "EVENT_PREDICATE_FACTS_INVALID",
                "event predicate facts are missing or contain unapproved fields",
            )
            facts = {}

        published_at = _parse_time(
            facts.get("published_at"), field=f"event.{event_id}.published_at", issues=[]
        )
        discovered_at = _parse_time(
            facts.get("discovered_at"), field=f"event.{event_id}.discovered_at", issues=[]
        )
        source = source_map.get(str(event.get("source_key")), {})
        source_slo = source.get("discovery_slo_hours") if isinstance(source, dict) else None
        within_slo = bool(
            isinstance(source_slo, int)
            and facts.get("discovery_slo_hours") == source_slo
            and published_at is not None
            and discovered_at is not None
            and started_at is not None
            and ended_at is not None
            and published_at <= discovered_at
            and started_at <= discovered_at <= ended_at
            and (discovered_at - published_at).total_seconds() <= source_slo * 3600
        )

        gold_member_ids = (
            gold_cluster.get("member_document_ids")
            if isinstance(gold_cluster, dict)
            else None
        )
        event_document_ids = facts.get("event_document_ids")
        fact_gold_member_ids = facts.get("gold_member_document_ids")
        correct_eventization = bool(
            trace_valid
            and isinstance(validated_trace_statement, dict)
            and facts.get("gold_cluster_id") == event_id
            and isinstance(gold_member_ids, list)
            and gold_member_ids
            and all(isinstance(value, str) and _is_uuid7(value) for value in gold_member_ids)
            and isinstance(fact_gold_member_ids, list)
            and fact_gold_member_ids == sorted(set(gold_member_ids))
            and isinstance(event_document_ids, list)
            and event_document_ids == sorted(set(gold_member_ids))
            and validated_trace_statement.get("document_id") in event_document_ids
            and validated_trace_statement.get("event_id") == platform_event_id
        )

        cluster_platform_event_ids = facts.get("cluster_platform_event_ids")
        nonduplicate = bool(
            isinstance(platform_event_id, str)
            and _is_uuid7(platform_event_id)
            and isinstance(cluster_platform_event_ids, list)
            and all(
                isinstance(value, str) and _is_uuid7(value)
                for value in cluster_platform_event_ids
            )
            and cluster_platform_event_ids == [platform_event_id]
        )

        accepted_claim_ids = facts.get("accepted_claim_ids")
        current_evidence_ids = facts.get("current_evidence_ids")
        links = facts.get("claim_evidence_links")
        valid_links = bool(
            isinstance(links, list)
            and links
            and all(
                isinstance(link, dict)
                and set(link) == {"claim_id", "evidence_id", "current"}
                and link.get("current") is True
                and isinstance(link.get("claim_id"), str)
                and isinstance(link.get("evidence_id"), str)
                for link in links
            )
        )
        linked_claim_ids = (
            sorted({str(link["claim_id"]) for link in links})
            if valid_links and isinstance(links, list)
            else []
        )
        linked_evidence_ids = (
            sorted({str(link["evidence_id"]) for link in links})
            if valid_links and isinstance(links, list)
            else []
        )
        trace_claim_ids = (
            validated_trace_statement.get("accepted_claim_ids")
            if isinstance(validated_trace_statement, dict)
            else None
        )
        trace_evidence_ids = (
            validated_trace_statement.get("evidence_ids")
            if isinstance(validated_trace_statement, dict)
            else None
        )
        critical_evidence_current = bool(
            trace_valid
            and isinstance(accepted_claim_ids, list)
            and accepted_claim_ids
            and all(isinstance(value, str) for value in accepted_claim_ids)
            and accepted_claim_ids == sorted(set(accepted_claim_ids))
            and accepted_claim_ids == trace_claim_ids
            and accepted_claim_ids == linked_claim_ids
            and isinstance(current_evidence_ids, list)
            and current_evidence_ids
            and all(isinstance(value, str) for value in current_evidence_ids)
            and current_evidence_ids == sorted(set(current_evidence_ids))
            and current_evidence_ids == trace_evidence_ids
            and current_evidence_ids == linked_evidence_ids
        )

        search_result_event_ids = facts.get("search_result_event_ids")
        searchable_readable = bool(
            trace_valid
            and isinstance(validated_trace_statement, dict)
            and facts.get("projection_revision_id")
            == validated_trace_statement.get("projection_revision_id")
            and facts.get("projection_event_id") == platform_event_id
            and facts.get("projection_state") == "PUBLISHED"
            and _is_uuid7(facts.get("search_query_id"))
            and isinstance(search_result_event_ids, list)
            and all(isinstance(value, str) for value in search_result_event_ids)
            and search_result_event_ids == sorted(set(search_result_event_ids))
            and platform_event_id in search_result_event_ids
            and facts.get("retrieval_status") == "READABLE"
        )
        computed_results = {
            "within_slo": within_slo,
            "correct_eventization": correct_eventization,
            "nonduplicate": nonduplicate,
            "critical_evidence_current": critical_evidence_current,
            "searchable_readable": searchable_readable,
        }
        if critical_evidence_current and isinstance(accepted_claim_ids, list):
            current_claim_ids_in_events.update(
                value for value in accepted_claim_ids if isinstance(value, str)
            )
        if (
            not isinstance(submitted_results, dict)
            or set(submitted_results) != EVENT_PREDICATE_RESULT_FIELDS
            or not all(isinstance(value, bool) for value in submitted_results.values())
            or submitted_results != computed_results
        ):
            _issue(
                issues,
                "EVENT_PREDICATE_NOT_REPRODUCIBLE",
                "five north-star predicates differ from timestamps, trace, gold, evidence, "
                "or retrieval facts",
            )
        predicate_statement = {
            "gold_event_id": event_id,
            "source_key": event.get("source_key"),
            "platform_event_id": platform_event_id,
            "predicate_facts": facts,
            "predicate_results": submitted_results,
        }
        _validate_exact_json_export(
            event.get("predicate_evidence_ref"),
            predicate_statement,
            issue_code="EVENT_PREDICATE_EXPORT_INVALID",
            message="event predicate DB/search export differs from the asserted facts",
            root=root,
            issues=issues,
            cache=ref_cache,
        )
        for name, result_name in (
            ("discovery_within_slo", "within_slo"),
            ("correct_eventization", "correct_eventization"),
            ("searchable_readable", "searchable_readable"),
        ):
            if computed_results[result_name]:
                derived[name] += 1
        north_pass = all(computed_results.values())
        if north_pass:
            if not platform_event_id:
                _issue(issues, "NORTH_STAR_EVENT_ID_MISSING", "successful event lacks platform ID")
            north_star_numerator += 1
    result_metrics: dict[str, Any] = {
        "north_star": _rate_result(north_star_numerator, len(event_evaluations), 0.90)
    }
    if not result_metrics["north_star"]["passed"]:
        _issue(issues, "NORTH_STAR_GATE_FAILED", "north-star point estimate is below 90%")

    def gold_ids(collection: str, *, key_safety: bool | None = None) -> list[str]:
        records = gold.get(collection, [])
        if not isinstance(records, list):
            return []
        return sorted(
            str(record.get("id"))
            for record in records
            if isinstance(record, dict)
            and isinstance(record.get("id"), str)
            and (key_safety is None or record.get("key_safety") is key_safety)
        )

    populations = {
        "EVENT_ENUMERATION": sorted(event_ids),
        "SCHEDULED_RUNS": sorted(run_map),
        "GOLD_DOCUMENTS": gold_ids("documents"),
        "GOLD_KEY_SAFETY_CLAIMS": gold_ids(
            "claim_evidence_annotations", key_safety=True
        ),
        "GOLD_OTHER_CLAIMS": gold_ids("claim_evidence_annotations", key_safety=False),
        "GOLD_DUPLICATE_PAIRS": gold_ids("duplicate_pairs"),
        "GOLD_EVENT_CLUSTERS": gold_ids("event_clusters"),
    }
    rates = metrics.get("rates", {})
    if not isinstance(rates, dict) or set(rates) != set(CANDIDATE_PROPORTION_GATES):
        _issue(
            issues,
            "RATE_SET_MISMATCH",
            "metric rate set differs from the preflight-confirmed candidate set",
        )
        rates = rates if isinstance(rates, dict) else {}
    allowed_rate_fields = {
        "numerator",
        "denominator",
        "population_kind",
        "eligible_ids",
        "passing_ids",
        "snapshot_at",
        "watermark",
        "evidence_ref",
    }
    for name, minimum in CANDIDATE_PROPORTION_GATES.items():
        rate = rates.get(name, {})
        if not isinstance(rate, dict) or set(rate) != allowed_rate_fields:
            _issue(
                issues,
                "RATE_POPULATION_MISMATCH",
                f"{name} lacks its complete enumerable population contract",
            )
            continue
        numerator = rate.get("numerator")
        denominator = rate.get("denominator")
        population_kind = RATE_POPULATIONS[name]
        eligible_ids = rate.get("eligible_ids")
        passing_ids = rate.get("passing_ids")
        expected_eligible_ids = populations[population_kind]
        population_valid = bool(
            rate.get("population_kind") == population_kind
            and isinstance(eligible_ids, list)
            and all(isinstance(value, str) for value in eligible_ids)
            and eligible_ids == expected_eligible_ids
            and isinstance(denominator, int)
            and not isinstance(denominator, bool)
            and denominator == len(expected_eligible_ids)
        )
        if not population_valid:
            _issue(
                issues,
                "RATE_POPULATION_MISMATCH",
                f"{name} eligible IDs differ from its complete event/run/gold population",
            )
        passing_valid = bool(
            isinstance(passing_ids, list)
            and all(isinstance(value, str) for value in passing_ids)
            and passing_ids == sorted(set(passing_ids))
            and isinstance(eligible_ids, list)
            and set(passing_ids).issubset(set(eligible_ids))
        )
        counts_valid = bool(
            isinstance(numerator, int)
            and not isinstance(numerator, bool)
            and isinstance(denominator, int)
            and not isinstance(denominator, bool)
            and denominator == len(expected_eligible_ids)
            and isinstance(passing_ids, list)
            and numerator == len(passing_ids)
            and numerator <= denominator
        )
        if not passing_valid or not counts_valid:
            _issue(
                issues,
                "RATE_COUNTS_NOT_REPRODUCIBLE",
                f"{name} numerator/denominator cannot be reproduced from its ID sets",
            )
        snapshot_at = _parse_time(
            rate.get("snapshot_at"), field=f"metrics.rates.{name}.snapshot_at", issues=[]
        )
        if (
            snapshot_at is None
            or ended_at is None
            or snapshot_at != ended_at
            or not isinstance(rate.get("watermark"), str)
            or not re.fullmatch(r"[A-Za-z0-9:._/-]{1,128}", str(rate.get("watermark")))
        ):
            _issue(
                issues,
                "RATE_QUERY_EXPORT_INVALID",
                f"{name} export is not pinned to the final window snapshot/watermark",
            )
        statement = {
            "metric_name": name,
            "population_kind": rate.get("population_kind"),
            "eligible_ids": eligible_ids,
            "passing_ids": passing_ids,
            "snapshot_at": rate.get("snapshot_at"),
            "watermark": rate.get("watermark"),
        }
        _validate_exact_json_export(
            rate.get("evidence_ref"),
            statement,
            issue_code="RATE_QUERY_EXPORT_INVALID",
            message=f"{name} hash-bound query export differs from the asserted ID sets",
            root=root,
            issues=issues,
            cache=ref_cache,
        )
        if not counts_valid:
            continue
        if (
            not isinstance(numerator, int)
            or isinstance(numerator, bool)
            or not isinstance(denominator, int)
            or isinstance(denominator, bool)
        ):
            continue
        rate_result = _rate_result(numerator, denominator, minimum)
        result_metrics[name] = rate_result
        if not rate_result["passed"]:
            _issue(
                issues,
                "PROPORTION_GATE_FAILED",
                f"{name} point estimate is below its preflight-confirmed threshold",
            )
        if name in derived and (
            numerator != derived[name] or denominator != len(event_evaluations)
        ):
            _issue(
                issues,
                "EVENT_METRIC_COUNTS_MISMATCH",
                f"{name} counts differ from the same enumerated event set",
            )

    absolute = metrics.get("absolute_gates", {})
    if not isinstance(absolute, dict) or set(absolute) != set(ABSOLUTE_QUERY_IDS):
        _issue(issues, "ABSOLUTE_GATE_FAILED", "absolute gate set is missing or differs")
        absolute = absolute if isinstance(absolute, dict) else {}
    absolute_values: dict[str, int] = {}
    absolute_rows: dict[str, list[str]] = {}
    allowed_absolute_fields = {
        "query_id",
        "query_version",
        "database_revision",
        "window_id",
        "snapshot_at",
        "watermark",
        "row_ids",
        "count",
        "evidence_ref",
    }
    for name, expected_query_id in ABSOLUTE_QUERY_IDS.items():
        record = absolute.get(name)
        if not isinstance(record, dict) or set(record) != allowed_absolute_fields:
            _issue(
                issues,
                "ABSOLUTE_QUERY_EXPORT_INVALID",
                f"{name} must be a structured authoritative DB query export",
            )
            continue
        count = record.get("count")
        row_ids = record.get("row_ids")
        snapshot_at = _parse_time(
            record.get("snapshot_at"), field=f"metrics.absolute.{name}.snapshot_at", issues=[]
        )
        structural_valid = bool(
            record.get("query_id") == expected_query_id
            and record.get("query_version") == "r17-absolute-v1"
            and record.get("database_revision") == EXPECTED_DATABASE_REVISION
            and record.get("window_id") == metrics.get("window_id")
            and snapshot_at is not None
            and ended_at is not None
            and snapshot_at == ended_at
            and isinstance(record.get("watermark"), str)
            and re.fullmatch(r"[A-Za-z0-9:._/-]{1,128}", str(record.get("watermark")))
            is not None
            and isinstance(row_ids, list)
            and all(isinstance(value, str) and _is_uuid7(value) for value in row_ids)
            and row_ids == sorted(set(row_ids))
            and isinstance(count, int)
            and not isinstance(count, bool)
            and count >= 0
            and count == len(row_ids)
        )
        if not structural_valid:
            _issue(
                issues,
                "ABSOLUTE_QUERY_EXPORT_INVALID",
                f"{name} query metadata, watermark, row IDs, or count is invalid",
            )
        statement = {key: record.get(key) for key in allowed_absolute_fields - {"evidence_ref"}}
        _validate_exact_json_export(
            record.get("evidence_ref"),
            statement,
            issue_code="ABSOLUTE_QUERY_EXPORT_INVALID",
            message=f"{name} hash-bound DB export differs from the asserted query result",
            root=root,
            issues=issues,
            cache=ref_cache,
        )
        if isinstance(count, int) and not isinstance(count, bool) and isinstance(row_ids, list):
            absolute_values[name] = count
            absolute_rows[name] = [value for value in row_ids if isinstance(value, str)]
    for gate in CANDIDATE_ZERO_GATES:
        if absolute_values.get(gate) != 0:
            _issue(issues, "ABSOLUTE_GATE_FAILED", f"{gate} must be exactly zero")
    published_total = absolute_values.get("published_critical_claim_count")
    published_current = absolute_values.get(
        "published_critical_claim_with_current_evidence_count"
    )
    if published_total == 0:
        _issue(
            issues,
            "PUBLISHED_CRITICAL_CLAIMS_EMPTY",
            "100% current-evidence coverage cannot be proven with a zero/zero population",
        )
    if (
        not isinstance(published_total, int)
        or published_total <= 0
        or published_current != published_total
        or absolute_rows.get("published_critical_claim_count")
        != absolute_rows.get("published_critical_claim_with_current_evidence_count")
        or not set(absolute_rows.get("published_critical_claim_count", [])).issubset(
            current_claim_ids_in_events
        )
    ):
        _issue(
            issues,
            "ABSOLUTE_GATE_FAILED",
            "published critical claims must have 100% current evidence coverage",
        )

    operator_export = metrics.get("operator_work_export")
    operator_statement: dict[str, Any] = {}
    operator_ref: object = None
    tasks: list[Payload] = []
    sessions: list[Payload] = []
    corrections: list[Payload] = []
    overdue_task_ids: list[str] = []
    cost_entries: list[Payload] = []
    if not isinstance(operator_export, dict) or set(operator_export) != {
        "query_id",
        "query_version",
        "database_revision",
        "window_id",
        "actor_subject",
        "tasks",
        "sessions",
        "corrections",
        "overdue_backlog_task_ids",
        "cost_entries",
        "snapshot_at",
        "watermark",
        "evidence_ref",
    }:
        _issue(
            issues,
            "OPERATOR_EXPORT_INVALID",
            "operator work needs one complete ID-only session/correction export",
        )
    else:
        operator_statement = {
            key: operator_export.get(key) for key in operator_export if key != "evidence_ref"
        }
        operator_ref = operator_export.get("evidence_ref")
        if (
            operator_export.get("query_id") != "round17.authoritative_operator_work.v1"
            or operator_export.get("query_version") != "v1"
            or operator_export.get("database_revision") != EXPECTED_DATABASE_REVISION
            or operator_export.get("window_id") != metrics.get("window_id")
        ):
            _issue(
                issues,
                "OPERATOR_EXPORT_INVALID",
                "operator work export is not an authoritative versioned DB query",
            )
        if operator_export.get("actor_subject") != subjects.get("yinzi"):
            _issue(
                issues,
                "OPERATOR_SUBJECT_INVALID",
                "the 1-person pilot operator export actor must be yinzi's OIDC subject",
            )
        raw_tasks = operator_export.get("tasks")
        raw_sessions = operator_export.get("sessions")
        raw_corrections = operator_export.get("corrections")
        raw_overdue = operator_export.get("overdue_backlog_task_ids")
        raw_costs = operator_export.get("cost_entries")
        tasks = (
            [value for value in raw_tasks if isinstance(value, dict)]
            if isinstance(raw_tasks, list)
            else []
        )
        sessions = (
            [value for value in raw_sessions if isinstance(value, dict)]
            if isinstance(raw_sessions, list)
            else []
        )
        corrections = (
            [value for value in raw_corrections if isinstance(value, dict)]
            if isinstance(raw_corrections, list)
            else []
        )
        overdue_task_ids = (
            [value for value in raw_overdue if isinstance(value, str)]
            if isinstance(raw_overdue, list)
            else []
        )
        cost_entries = (
            [value for value in raw_costs if isinstance(value, dict)]
            if isinstance(raw_costs, list)
            else []
        )
        operator_snapshot = _parse_time(
            operator_export.get("snapshot_at"),
            field="metrics.operator_work_export.snapshot_at",
            issues=[],
        )
        if (
            operator_snapshot is None
            or ended_at is None
            or operator_snapshot != ended_at
            or not isinstance(operator_export.get("watermark"), str)
            or re.fullmatch(
                r"[A-Za-z0-9:._/-]{1,128}", str(operator_export.get("watermark"))
            )
            is None
        ):
            _issue(
                issues,
                "OPERATOR_EXPORT_INVALID",
                "operator export is not pinned to the final window snapshot/watermark",
            )
        _validate_exact_json_export(
            operator_ref,
            operator_statement,
            issue_code="OPERATOR_EXPORT_INVALID",
            message="operator hash-bound DB export differs from its session/correction records",
            root=root,
            issues=issues,
            cache=ref_cache,
        )

    shanghai = ZoneInfo("Asia/Shanghai")
    task_map: dict[str, Payload] = {}
    overdue_task_ids_from_tasks: set[str] = set()
    for task in tasks:
        if set(task) != {
            "task_id",
            "operator_subject",
            "category",
            "created_at",
            "completed_at",
            "status",
        }:
            _issue(issues, "OPERATOR_TASK_INVALID", "operator task fields differ")
            continue
        task_id = task.get("task_id")
        created_at = _parse_time(
            task.get("created_at"), field=f"operator.task.{task_id}.created_at", issues=[]
        )
        completed_at = _parse_time(
            task.get("completed_at"), field=f"operator.task.{task_id}.completed_at", issues=[]
        )
        status = task.get("status")
        task_valid = bool(
            isinstance(task_id, str)
            and _is_uuid7(task_id)
            and task_id not in task_map
            and task.get("operator_subject") == subjects.get("yinzi")
            and task.get("category") in OPERATOR_CATEGORIES
            and status in {"COMPLETED", "OVERDUE"}
            and created_at is not None
            and started_at is not None
            and ended_at is not None
            and started_at <= created_at <= ended_at
            and (
                (
                    status == "COMPLETED"
                    and completed_at is not None
                    and created_at <= completed_at <= ended_at
                )
                or (status == "OVERDUE" and task.get("completed_at") is None)
            )
        )
        if not task_valid:
            _issue(
                issues,
                "OPERATOR_TASK_INVALID",
                "operator task must be an in-window yinzi task with a valid lifecycle",
            )
            continue
        if not isinstance(task_id, str):
            continue
        task_map[task_id] = task
        if status == "OVERDUE":
            overdue_task_ids_from_tasks.add(task_id)

    session_ids: set[str] = set()
    task_ids: set[str] = set()
    daily_seconds: dict[str, dict[str, int]] = {}
    daily_tasks: dict[str, dict[str, set[str]]] = {}
    for session in sessions:
        if set(session) != {
            "session_id",
            "operator_subject",
            "task_id",
            "category",
            "started_at",
            "ended_at",
            "active_seconds",
        }:
            _issue(issues, "OPERATOR_SESSION_INVALID", "operator session fields differ")
            continue
        session_id = session.get("session_id")
        task_id = session.get("task_id")
        category = session.get("category")
        active_seconds = session.get("active_seconds")
        session_started = _parse_time(
            session.get("started_at"), field=f"operator.session.{session_id}.started_at", issues=[]
        )
        session_ended = _parse_time(
            session.get("ended_at"), field=f"operator.session.{session_id}.ended_at", issues=[]
        )
        bound_task = task_map.get(str(task_id))
        task_created = (
            _parse_time(
                bound_task.get("created_at"),
                field=f"operator.task.{task_id}.created_at",
                issues=[],
            )
            if isinstance(bound_task, dict)
            else None
        )
        task_completed = (
            _parse_time(
                bound_task.get("completed_at"),
                field=f"operator.task.{task_id}.completed_at",
                issues=[],
            )
            if isinstance(bound_task, dict)
            else None
        )
        session_valid = bool(
            isinstance(session_id, str)
            and _is_uuid7(session_id)
            and session_id not in session_ids
            and isinstance(task_id, str)
            and _is_uuid7(task_id)
            and task_id in task_map
            and task_map[task_id].get("category") == category
            and task_map[task_id].get("operator_subject") == session.get("operator_subject")
            and task_created is not None
            and task_completed is not None
            and category in OPERATOR_CATEGORIES
            and session.get("operator_subject") == subjects.get("yinzi")
            and isinstance(active_seconds, int)
            and not isinstance(active_seconds, bool)
            and active_seconds > 0
            and active_seconds % 60 == 0
            and session_started is not None
            and session_ended is not None
            and started_at is not None
            and ended_at is not None
            and started_at <= session_started < session_ended <= ended_at
            and task_created <= session_started < session_ended <= task_completed
            and active_seconds <= (session_ended - session_started).total_seconds()
            and session_started.astimezone(shanghai).date()
            == session_ended.astimezone(shanghai).date()
        )
        if not session_valid:
            _issue(
                issues,
                "OPERATOR_SESSION_INVALID",
                "operator session must be a bounded yinzi task with positive active seconds",
            )
            continue
        if (
            not isinstance(session_id, str)
            or not isinstance(task_id, str)
            or not isinstance(session_started, datetime)
            or not isinstance(active_seconds, int)
        ):
            continue
        session_ids.add(session_id)
        task_ids.add(task_id)
        day_key = session_started.astimezone(shanghai).date().isoformat()
        category_key = OPERATOR_CATEGORIES[str(category)]
        daily_seconds.setdefault(day_key, {value: 0 for value in OPERATOR_CATEGORIES.values()})
        daily_tasks.setdefault(day_key, {value: set() for value in OPERATOR_CATEGORIES.values()})
        daily_seconds[day_key][category_key] += active_seconds
        daily_tasks[day_key][category_key].add(task_id)

    if task_ids != set(task_map):
        _issue(
            issues,
            "OPERATOR_TASK_SESSION_MISMATCH",
            "every operator task must have a session and every session must bind a task",
        )

    correction_task_ids: set[str] = set()
    correction_ids: set[str] = set()
    for correction in corrections:
        if set(correction) != {
            "correction_id",
            "task_id",
            "operator_subject",
            "recorded_at",
        }:
            _issue(issues, "OPERATOR_CORRECTION_INVALID", "correction fields differ")
            continue
        correction_id = correction.get("correction_id")
        task_id = correction.get("task_id")
        recorded_at = _parse_time(
            correction.get("recorded_at"),
            field=f"operator.correction.{correction_id}.recorded_at",
            issues=[],
        )
        if not (
            isinstance(correction_id, str)
            and _is_uuid7(correction_id)
            and correction_id not in correction_ids
            and isinstance(task_id, str)
            and task_id in task_ids
            and task_id not in correction_task_ids
            and correction.get("operator_subject") == subjects.get("yinzi")
            and recorded_at is not None
            and started_at is not None
            and ended_at is not None
            and started_at <= recorded_at <= ended_at
        ):
            _issue(
                issues,
                "OPERATOR_CORRECTION_INVALID",
                "copyright correction must bind one real yinzi task inside the window",
            )
            continue
        correction_ids.add(correction_id)
        correction_task_ids.add(task_id)
    copyright_task_ids = {
        str(session.get("task_id"))
        for session in sessions
        if session.get("category") == "COPYRIGHT_CORRECTION"
        and isinstance(session.get("task_id"), str)
    }
    if correction_task_ids != copyright_task_ids:
        _issue(
            issues,
            "OPERATOR_CORRECTION_INVALID",
            "copyright work sessions and correction records must be bidirectionally complete",
        )

    if (
        overdue_task_ids != sorted(set(overdue_task_ids))
        or not all(_is_uuid7(value) for value in overdue_task_ids)
        or set(overdue_task_ids) != overdue_task_ids_from_tasks
    ):
        _issue(issues, "OPERATOR_BACKLOG_INVALID", "overdue backlog task IDs are invalid")
    cost_total = 0
    cost_entry_ids: set[str] = set()
    for entry in cost_entries:
        entry_id = entry.get("ledger_entry_id")
        amount = entry.get("amount_minor")
        recorded_at = _parse_time(
            entry.get("recorded_at"), field=f"operator.cost.{entry_id}.recorded_at", issues=[]
        )
        if not (
            set(entry) == {"ledger_entry_id", "amount_minor", "category", "recorded_at"}
            and isinstance(entry_id, str)
            and _is_uuid7(entry_id)
            and entry_id not in cost_entry_ids
            and isinstance(amount, int)
            and not isinstance(amount, bool)
            and amount >= 0
            and entry.get("category") in {"EXTERNAL_MODEL", "EMAIL", "WECHAT_WORK"}
            and recorded_at is not None
            and started_at is not None
            and ended_at is not None
            and started_at <= recorded_at <= ended_at
        ):
            _issue(issues, "OPERATOR_COST_INVALID", "operator external cost ledger is invalid")
            continue
        cost_entry_ids.add(entry_id)
        cost_total += amount
    if absolute_values.get("final_overdue_operator_backlog_count") != len(overdue_task_ids):
        _issue(
            issues,
            "OPERATOR_BACKLOG_INVALID",
            "absolute backlog query differs from work export",
        )
    if absolute_values.get("external_model_api_notification_cost_minor") != cost_total:
        _issue(issues, "OPERATOR_COST_INVALID", "absolute cost query differs from cost ledger")

    operator_days = metrics.get("operator_days", [])
    daily_totals: list[int] = []
    window_dates = (
        _shanghai_window_dates(started_at, ended_at)
        if started_at is not None and ended_at is not None
        else set()
    )
    if (
        not isinstance(operator_days, list)
        or len(operator_days) != len(window_dates)
        or len(operator_days) not in {7, 8}
    ):
        _issue(
            issues,
            "OPERATOR_WINDOW_INCOMPLETE",
            "operator records must cover every Shanghai date touched by [start, end)",
        )
        operator_days = []
    allowed_day_fields = {"date", "evidence_ref"} | {
        f"{category}_minutes" for category in OPERATOR_CATEGORIES.values()
    } | {f"{category}_task_count" for category in OPERATOR_CATEGORIES.values()}
    seen_dates: set[str] = set()
    for day in operator_days:
        if not isinstance(day, dict) or set(day) != allowed_day_fields:
            _issue(
                issues,
                "OPERATOR_RECORD_INVALID",
                "operator day must contain four recomputable times and task counts",
            )
            continue
        date_value = day.get("date")
        try:
            parsed_date = date.fromisoformat(str(date_value))
        except ValueError:
            parsed_date = None
        if (
            parsed_date is None
            or not isinstance(date_value, str)
            or parsed_date.isoformat() != date_value
            or date_value in seen_dates
        ):
            _issue(issues, "OPERATOR_RECORD_INVALID", "operator dates must be distinct")
            continue
        seen_dates.add(date_value)
        if date_value not in window_dates:
            _issue(
                issues,
                "OPERATOR_RECORD_OUTSIDE_WINDOW",
                "operator dates must fall inside the immutable Asia/Shanghai window",
            )
        expected_seconds = daily_seconds.get(
            date_value, {value: 0 for value in OPERATOR_CATEGORIES.values()}
        )
        expected_tasks = daily_tasks.get(
            date_value, {value: set() for value in OPERATOR_CATEGORIES.values()}
        )
        submitted_minutes: list[int] = []
        reproducible = True
        for category in OPERATOR_CATEGORIES.values():
            minutes = day.get(f"{category}_minutes")
            task_count = day.get(f"{category}_task_count")
            if (
                not isinstance(minutes, int)
                or isinstance(minutes, bool)
                or minutes < 0
                or minutes * 60 != expected_seconds[category]
                or not isinstance(task_count, int)
                or isinstance(task_count, bool)
                or task_count < 0
                or task_count != len(expected_tasks[category])
            ):
                reproducible = False
            if isinstance(minutes, int) and not isinstance(minutes, bool) and minutes >= 0:
                submitted_minutes.append(minutes)
        if not reproducible:
            _issue(
                issues,
                "OPERATOR_SUMMARY_NOT_REPRODUCIBLE",
                "operator daily times/task counts differ from raw work sessions",
            )
        if len(submitted_minutes) == len(OPERATOR_CATEGORIES):
            daily_totals.append(sum(submitted_minutes))
        if day.get("evidence_ref") != operator_ref:
            _issue(
                issues,
                "OPERATOR_EXPORT_INVALID",
                "each operator day must bind the same final authoritative work export",
            )
    if seen_dates != window_dates:
        _issue(
            issues,
            "OPERATOR_WINDOW_INCOMPLETE",
            "operator evidence must cover every Shanghai calendar date touched by the window",
        )
    total_active_seconds = sum(
        seconds for by_category in daily_seconds.values() for seconds in by_category.values()
    )
    if not sessions or total_active_seconds <= 0 or not task_ids:
        _issue(
            issues,
            "OPERATOR_ACTIVITY_EMPTY",
            "all-zero or session-free records cannot prove 1-person pilot operability",
        )
    if daily_totals:
        ordered = sorted(daily_totals)
        middle = len(ordered) // 2
        median = (
            float(ordered[middle])
            if len(ordered) % 2
            else (ordered[middle - 1] + ordered[middle]) / 2
        )
        p95 = _nearest_rank_p95(daily_totals)
        result_metrics["operator_daily_minutes"] = {"median": median, "p95": p95}
        if median > 120 or p95 > 240:
            _issue(issues, "OPERATOR_TIME_GATE_FAILED", "operator median or p95 exceeds limit")
    return result_metrics


def evaluate_round17_payloads(
    *,
    evidence: Payload,
    gold: Payload,
    metrics_definition: Payload,
    trusted_public_key_pem: bytes | None = None,
    expected_key_fingerprint_sha256: str | None = None,
    root: Path = ROOT,
) -> Payload:
    """Evaluate already-loaded inputs without any external I/O beyond hashed local refs."""

    issues: list[Issue] = []
    checks: dict[str, Any] = {}
    ref_cache: set[tuple[str, str]] = set()

    before = len(issues)
    _schema_issues(evidence, EVIDENCE_SCHEMA_PATH, "EVIDENCE", issues)
    _schema_issues(gold, GOLD_SCHEMA_PATH, "GOLD", issues)
    if not isinstance(evidence.get("trust_signature"), dict):
        _issue(
            issues,
            "EVIDENCE_SIGNATURE_MISSING",
            "the evidence snapshot lacks its detached Ed25519 signature envelope",
        )
    if not isinstance(evidence.get("preflight_authorization"), dict):
        _issue(
            issues,
            "PREFLIGHT_AUTHORIZATION_MISSING",
            "real LEO preflight authorization evidence is required",
        )
    checks["schema"] = {"passed": len(issues) == before}
    if len(issues) != before:
        return {
            "round": 17,
            "decision": "BLOCKED",
            "checks": checks,
            "metrics": {},
            "issues": issues,
        }

    before = len(issues)
    _validate_external_trust_anchor(
        evidence,
        trusted_public_key_pem=trusted_public_key_pem,
        expected_key_fingerprint_sha256=expected_key_fingerprint_sha256,
        issues=issues,
    )
    checks["external_trust_anchor"] = {"passed": len(issues) == before}
    if len(issues) != before:
        return {
            "round": 17,
            "decision": "BLOCKED",
            "checks": checks,
            "metrics": {},
            "issues": issues,
        }

    before = len(issues)
    _validate_no_inline_content(evidence, label="evidence", issues=issues)
    _validate_no_inline_content(gold, label="gold", issues=issues)
    checks["privacy"] = {"passed": len(issues) == before}

    if evidence.get("manifest_sha256") != canonical_sha256(
        evidence, excluded_keys={"manifest_sha256", "trust_signature"}
    ):
        _issue(
            issues,
            "EVIDENCE_MANIFEST_HASH_MISMATCH",
            "evidence manifest canonical hash differs",
        )

    before = len(issues)
    _validate_definition(
        metrics_definition,
        evidence,
        root=root,
        issues=issues,
        ref_cache=ref_cache,
    )
    checks["definition"] = {"passed": len(issues) == before}
    if len(issues) != before:
        return {
            "round": 17,
            "decision": "BLOCKED",
            "checks": checks,
            "metrics": {},
            "issues": issues,
        }

    before = len(issues)
    subjects = _validate_actor_set(evidence, gold, issues)
    checks["actor_identity"] = {"passed": len(issues) == before}

    before = len(issues)
    started_at, ended_at = _validate_window(
        evidence,
        subjects,
        root=root,
        issues=issues,
        ref_cache=ref_cache,
    )
    checks["window"] = {"passed": len(issues) == before}

    before = len(issues)
    _validate_preflight_authorization(
        evidence,
        metrics_definition,
        subjects,
        started_at,
        root=root,
        issues=issues,
        ref_cache=ref_cache,
    )
    checks["preflight_authorization"] = {"passed": len(issues) == before}

    before = len(issues)
    source_map = _validate_sources(
        evidence,
        metrics_definition,
        subjects,
        started_at,
        ended_at,
        root=root,
        issues=issues,
        ref_cache=ref_cache,
    )
    checks["source_governance"] = {
        "passed": len(issues) == before,
        "details": {"source_count": len(source_map)},
    }

    before = len(issues)
    run_details = _validate_runs(
        evidence,
        source_map,
        subjects,
        started_at,
        ended_at,
        root=root,
        issues=issues,
        ref_cache=ref_cache,
    )
    checks["run_provenance"] = {"passed": len(issues) == before, "details": run_details}

    before = len(issues)
    gold_details = _validate_gold(
        gold,
        evidence,
        subjects,
        source_map,
        root=root,
        issues=issues,
        ref_cache=ref_cache,
    )
    checks["gold"] = {"passed": len(issues) == before, "details": gold_details}

    before = len(issues)
    result_metrics = _validate_metrics(
        evidence,
        gold,
        subjects,
        source_map,
        started_at,
        ended_at,
        root=root,
        issues=issues,
        ref_cache=ref_cache,
    )
    checks["metrics"] = {"passed": len(issues) == before}

    return {
        "round": 17,
        "decision": "PASSED" if not issues else "BLOCKED",
        "metrics_definition_version": EXPECTED_METRICS_VERSION,
        "roster_version": EXPECTED_ROSTER_VERSION,
        "gold_version": EXPECTED_GOLD_VERSION,
        "checks": checks,
        "metrics": result_metrics,
        "issues": issues,
    }


def _load_json(path: Path, label: str) -> Payload:
    if not path.is_file():
        raise ValueError(f"{label} is missing: {path}")
    if path.stat().st_size > MAX_INPUT_BYTES:
        raise ValueError(f"{label} exceeds {MAX_INPUT_BYTES} bytes")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} is not valid UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object")
    return value


def evaluate_round17_files(
    *,
    evidence_path: Path,
    gold_path: Path,
    metrics_definition_path: Path = METRICS_DEFINITION_PATH,
    trusted_public_key_path: Path | None = None,
    expected_key_fingerprint_sha256: str | None = None,
    root: Path = ROOT,
) -> Payload:
    # Load required evidence first so its absence remains the primary external blocker.
    evidence = _load_json(evidence_path, "round17 evidence")
    gold = _load_json(gold_path, "round17 gold manifest")
    metrics_definition = _load_json(metrics_definition_path, "round17 metrics definition")
    trusted_public_key_pem: bytes | None = None
    if trusted_public_key_path is not None:
        if not trusted_public_key_path.is_file():
            return {
                "round": 17,
                "decision": "BLOCKED",
                "checks": {"external_trust_anchor": {"passed": False}},
                "metrics": {},
                "issues": [
                    {
                        "code": "TRUST_ANCHOR_INVALID",
                        "message": f"trusted public key file is missing: {trusted_public_key_path}",
                    }
                ],
            }
        if trusted_public_key_path.stat().st_size > MAX_TRUST_ANCHOR_BYTES:
            return {
                "round": 17,
                "decision": "BLOCKED",
                "checks": {"external_trust_anchor": {"passed": False}},
                "metrics": {},
                "issues": [
                    {
                        "code": "TRUST_ANCHOR_INVALID",
                        "message": "trusted public key file exceeds the 16 KiB limit",
                    }
                ],
            }
        trusted_public_key_pem = trusted_public_key_path.read_bytes()
    return evaluate_round17_payloads(
        evidence=evidence,
        gold=gold,
        metrics_definition=metrics_definition,
        trusted_public_key_pem=trusted_public_key_pem,
        expected_key_fingerprint_sha256=expected_key_fingerprint_sha256,
        root=root,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Offline Round 17 evidence evaluator")
    parser.add_argument("--evidence", type=Path, default=DEFAULT_EVIDENCE_PATH)
    parser.add_argument("--gold-manifest", type=Path, default=DEFAULT_GOLD_PATH)
    parser.add_argument("--metrics-definition", type=Path, default=METRICS_DEFINITION_PATH)
    trusted_key_from_env = os.environ.get("ROUND17_TRUSTED_PUBLIC_KEY", "").strip()
    parser.add_argument(
        "--trusted-public-key",
        type=Path,
        default=Path(trusted_key_from_env) if trusted_key_from_env else None,
    )
    parser.add_argument(
        "--trusted-public-key-sha256",
        default=os.environ.get("ROUND17_TRUSTED_PUBLIC_KEY_SHA256", "").strip() or None,
    )
    args = parser.parse_args()
    try:
        result = evaluate_round17_files(
            evidence_path=args.evidence,
            gold_path=args.gold_manifest,
            metrics_definition_path=args.metrics_definition,
            trusted_public_key_path=args.trusted_public_key,
            expected_key_fingerprint_sha256=args.trusted_public_key_sha256,
        )
    except ValueError as exc:
        result = {
            "round": 17,
            "decision": "BLOCKED",
            "checks": {},
            "metrics": {},
            "issues": [{"code": "REQUIRED_EVIDENCE_MISSING", "message": str(exc)}],
        }
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result["decision"] == "PASSED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
