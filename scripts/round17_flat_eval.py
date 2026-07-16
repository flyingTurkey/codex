"""Offline evaluator for the frozen Round 17 single-expert pilot contract."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
AUTHORITY = ROOT / "docs/codex-kit/assets/validation/round17_approved_authority.json"
SIGNED = ROOT / "docs/acceptance/assets/round17/leo-signed-approval.json"
DEFAULT_EVIDENCE = ROOT / "docs/acceptance/assets/round17/round17-flat-evidence.json"
DEFAULT_REFERENCE = ROOT / "tests/gold/round17/leo-reference-manifest.json"
LEO = "019f6b65-4cf5-71d1-b75c-a6c908912f58"
EXPECTED_COUNTS = {
    "documents": 500,
    "duplicate_pairs": 300,
    "event_clusters": 100,
    "claim_evidence_annotations": 200,
    "search_questions": 100,
}
RATE_THRESHOLDS_BPS = {
    "discovery_within_slo": 9500,
    "correct_eventization": 9500,
    "searchable_readable": 9500,
    "tier1_transport_success": 9900,
    "html_parse_success": 9800,
    "text_pdf_parse_success": 9700,
    "ocr_usable": 9200,
    "safety_key_field_accuracy": 9800,
    "other_field_accuracy": 9500,
    "exact_dedup_precision": 9950,
    "fuzzy_candidate_precision": 9800,
    "fuzzy_candidate_recall": 9300,
    "cluster_purity": 9500,
}
ZERO_GATES = {
    "r3_review_bypass_count",
    "r4_or_unpublished_leak_count",
    "publication_service_bypass_count",
}


def _canonical_json(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )


def _load(path: Path, issues: list[dict[str, str]], code: str) -> dict[str, Any] | None:
    if not path.is_file():
        issues.append({"code": code, "message": f"required file is missing: {path}"})
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        issues.append({"code": f"{code}_INVALID", "message": f"invalid JSON: {path}"})
        return None
    if not isinstance(value, dict):
        issues.append({"code": f"{code}_INVALID", "message": "root must be an object"})
        return None
    return value


def _time(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.astimezone(UTC)


def _check_ref(ref: object, *, issues: list[dict[str, str]]) -> None:
    if not isinstance(ref, dict) or set(ref) != {"uri", "sha256"}:
        issues.append({"code": "EVIDENCE_REFERENCE_INVALID", "message": "hash reference differs"})
        return
    uri, digest = ref.get("uri"), ref.get("sha256")
    if not isinstance(uri, str) or not isinstance(digest, str):
        issues.append(
            {"code": "EVIDENCE_REFERENCE_INVALID", "message": "hash reference types differ"}
        )
        return
    target = (ROOT / uri).resolve()
    try:
        target.relative_to(ROOT.resolve())
    except ValueError:
        issues.append({"code": "EVIDENCE_REFERENCE_UNSAFE", "message": uri})
        return
    if not target.is_file():
        issues.append({"code": "EVIDENCE_REFERENCE_MISSING", "message": uri})
        return
    if target.stat().st_size > 64 * 1024 * 1024:
        issues.append({"code": "EVIDENCE_REFERENCE_TOO_LARGE", "message": uri})
        return
    if sha256(target.read_bytes()).hexdigest() != digest:
        issues.append({"code": "EVIDENCE_REFERENCE_HASH_MISMATCH", "message": uri})


def evaluate(
    evidence_path: Path, reference_path: Path, *, now: datetime | None = None
) -> dict[str, Any]:
    issues: list[dict[str, str]] = []
    evidence = _load(evidence_path, issues, "REQUIRED_EVIDENCE_MISSING")
    reference = _load(reference_path, issues, "REQUIRED_REFERENCE_MISSING")
    authority = _load(AUTHORITY, issues, "APPROVED_AUTHORITY_MISSING")
    signed = _load(SIGNED, issues, "SIGNED_AUTHORITY_MISSING")
    if evidence is None or reference is None or authority is None or signed is None:
        return {"round": 17, "decision": "BLOCKED", "checks": {}, "issues": issues}

    authority_hash = sha256(_canonical_json(authority)).hexdigest()
    if (
        signed.get("approval_document") != authority
        or signed.get("approval_document_sha256") != authority_hash
        or evidence.get("authority_document_sha256") != authority_hash
        or reference.get("authority_document_sha256") != authority_hash
    ):
        issues.append(
            {
                "code": "AUTHORITY_BINDING_MISMATCH",
                "message": "artifacts do not bind the signed authority",
            }
        )

    if evidence.get("schema_version") != "round17-flat-evidence-v1":
        issues.append(
            {"code": "EVIDENCE_SCHEMA_VERSION_INVALID", "message": "flat evidence version differs"}
        )
    if reference.get("schema_version") != "round17-leo-reference-v1":
        issues.append(
            {"code": "REFERENCE_SCHEMA_VERSION_INVALID", "message": "reference version differs"}
        )
    expected_versions = {
        "database_revision": "0017c_round17_flat_pilot",
        "roster_version": authority.get("roster_version"),
        "metric_definition_version": authority.get("metric_definition_version"),
        "reference_definition_version": authority.get("reference_definition_version"),
    }
    if any(evidence.get(key) != value for key, value in expected_versions.items()):
        issues.append({"code": "VERSION_PIN_MISMATCH", "message": "evidence version pins differ"})

    window = evidence.get("window")
    start = _time(window.get("started_at")) if isinstance(window, dict) else None
    end = _time(window.get("ended_at")) if isinstance(window, dict) else None
    current = (now or datetime.now(UTC)).astimezone(UTC)
    if (
        not isinstance(window, dict)
        or start is None
        or end is None
        or end - start != timedelta(hours=168)
        or end > current
        or window.get("duration_hours") != 168
        or window.get("continuous_hours_proven") != 168
        or window.get("state") != "COMPLETED"
    ):
        issues.append(
            {
                "code": "OBSERVATION_WINDOW_INVALID",
                "message": "immutable completed 168-hour window is not proven",
            }
        )
    elif isinstance(window, dict):
        _check_ref(window.get("monitor_query_ref"), issues=issues)

    expected_codes = {str(source["source_code"]) for source in authority["sources"]}
    sources = evidence.get("sources")
    actual_codes = (
        {str(source.get("source_code")) for source in sources if isinstance(source, dict)}
        if isinstance(sources, list)
        else set()
    )
    if actual_codes != expected_codes or not isinstance(sources, list) or len(sources) != 20:
        issues.append(
            {"code": "SOURCE_ROSTER_INVALID", "message": "exact 20-source evidence is required"}
        )
    elif isinstance(sources, list):
        for source in sources:
            if source.get("honest_status") not in {"REAL_CHAIN", "NO_UPDATE_HEALTHY"}:
                issues.append(
                    {"code": "SOURCE_STATUS_INVALID", "message": str(source.get("source_code"))}
                )
            _check_ref(source.get("health_evidence_ref"), issues=issues)

    if (
        reference.get("definition_version") != authority.get("reference_definition_version")
        or reference.get("annotator_actor_id") != LEO
        or reference.get("reference_model") != "LEO_SINGLE_EXPERT_REFERENCE_SET"
        or reference.get("assurance") != "LOWER_THAN_DUAL_EXPERT_GOLD"
        or reference.get("counts") != EXPECTED_COUNTS
        or _time(reference.get("frozen_at")) is None
    ):
        issues.append(
            {"code": "REFERENCE_MANIFEST_INVALID", "message": "LEO reference contract differs"}
        )
    _check_ref(reference.get("records_ref"), issues=issues)

    rates = evidence.get("metric_results")
    if not isinstance(rates, dict) or set(rates) != set(RATE_THRESHOLDS_BPS):
        issues.append({"code": "METRIC_SET_INVALID", "message": "approved metric set differs"})
    else:
        for name, threshold in RATE_THRESHOLDS_BPS.items():
            result = rates[name]
            if not isinstance(result, dict):
                issues.append({"code": "METRIC_RESULT_INVALID", "message": name})
                continue
            numerator, denominator = result.get("numerator"), result.get("denominator")
            if (
                not isinstance(numerator, int)
                or not isinstance(denominator, int)
                or denominator <= 0
                or numerator < 0
                or numerator > denominator
                or numerator * 10_000 < threshold * denominator
            ):
                issues.append({"code": "METRIC_GATE_FAILED", "message": name})

    absolute = evidence.get("absolute_gates")
    critical = evidence.get("published_critical_evidence")
    if not isinstance(absolute, dict) or any(absolute.get(name) != 0 for name in ZERO_GATES):
        issues.append(
            {
                "code": "ABSOLUTE_SAFETY_GATE_FAILED",
                "message": "R3/R4/publication bypass must be zero",
            }
        )
    if (
        not isinstance(critical, dict)
        or not isinstance(critical.get("published_claim_count"), int)
        or critical.get("published_claim_count") != critical.get("with_current_evidence_count")
    ):
        issues.append(
            {
                "code": "CRITICAL_EVIDENCE_GATE_FAILED",
                "message": "published critical evidence must be 100%",
            }
        )

    north_star = evidence.get("north_star")
    if (
        not isinstance(north_star, dict)
        or not isinstance(north_star.get("successful_events"), int)
        or not isinstance(north_star.get("expected_high_value_events"), int)
        or north_star.get("expected_high_value_events", 0) <= 0
        or north_star.get("successful_events", -1) < 0
        or north_star.get("successful_events", 0) > north_star.get("expected_high_value_events", 0)
    ):
        issues.append(
            {"code": "NORTH_STAR_INVALID", "message": "direct numerator/denominator is required"}
        )

    drill = evidence.get("fault_drill")
    if (
        not isinstance(drill, dict)
        or drill.get("approved_by") != LEO
        or drill.get("environment") != "TEST"
    ):
        issues.append(
            {"code": "FAULT_DRILL_INVALID", "message": "approved test-only drill is required"}
        )
    elif isinstance(drill, dict):
        _check_ref(drill.get("evidence_ref"), issues=issues)

    return {
        "round": 17,
        "decision": "PASSED" if not issues else "BLOCKED",
        "checks": {"single_expert_contract": not issues},
        "issues": issues,
        "north_star": north_star if isinstance(north_star, dict) else {},
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence", type=Path, default=DEFAULT_EVIDENCE)
    parser.add_argument("--reference-manifest", type=Path, default=DEFAULT_REFERENCE)
    args = parser.parse_args()
    result = evaluate(args.evidence, args.reference_manifest)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    raise SystemExit(0 if result["decision"] == "PASSED" else 1)


if __name__ == "__main__":
    main()
