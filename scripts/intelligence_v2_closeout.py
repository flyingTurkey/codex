"""Validate private v2 acceptance evidence and emit a fail-closed readiness manifest."""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker, ValidationError
from srbg_api.intelligence_v2.closeout import (
    AcceptanceProfile,
    CompensationInspection,
    FeedInspection,
    QualificationInspection,
    RuntimeObservation,
    evaluate_compensation,
    evaluate_feed,
    evaluate_qualification,
    evaluate_runtime_window,
)
from srbg_api.intelligence_v2.gold_calibration import (
    OWNER_GOLD_CORPUS_VERSION,
    calibration_grant,
    load_calibration_fact,
)
from srbg_api.source_registry.v2_rollout import (
    SourceAdmissionMetrics,
    production_admission_verdict,
)
from srbg_contracts import EngineeringObject, PrimaryIntelligenceType

_SHA256 = re.compile(r"^[a-f0-9]{64}$")
_GIT_COMMIT = re.compile(r"^[a-f0-9]{40}$")
_UUID7 = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")
_ENGINEERING_GATES = (
    "lint",
    "typecheck",
    "test",
    "contract_test",
    "security_check",
    "fixture_replay",
    "quality_gate",
    "web_e2e",
    "web_a11y",
)
_ROOT = Path(__file__).resolve().parents[1]
_REPORT_SCHEMA = _ROOT / "docs/codex-kit/assets/validation/intelligence_v2_closeout.schema.json"
_SOURCE_ROLLOUT = (
    _ROOT / "docs/codex-kit/assets/validation/civil_engineering_source_rollout_v2.json"
)
_OWNER_ANNOTATION_SCHEMA = (
    _ROOT / "docs/codex-kit/assets/validation/intelligence_v2_owner_gold_annotation.schema.json"
)
_FEED_OWNER_ANNOTATION_SCHEMA = (
    _ROOT / "docs/codex-kit/assets/validation/intelligence_v2_owner_annotation.schema.json"
)
_QUALIFICATION_PREDICTION_SCHEMA = (
    _ROOT / "docs/codex-kit/assets/validation/intelligence_v2_qualification_prediction.schema.json"
)
_FEED_STRUCTURAL_SCHEMA = (
    _ROOT / "docs/codex-kit/assets/validation/intelligence_v2_feed_structural_audit.schema.json"
)
_EVIDENCE_FILES = (
    "runtime.jsonl",
    "qualification.jsonl",
    "qualification-predictions.jsonl",
    "qualification-calibration.json",
    "feed.jsonl",
    "sources.json",
    "engineering.json",
    "compensation.json",
    "preflight.json",
    "context.json",
    "historical_budget.json",
)


def _canonical_json(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path.name} must contain one JSON object")
    return value


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            raise ValueError(f"{path.name}:{line_number} must contain one JSON object")
        rows.append(value)
    return rows


def _owner(row: dict[str, Any]) -> None:
    if row.get("annotator_kind") != "HUMAN_OWNER":
        raise ValueError("acceptance annotations require annotator_kind=HUMAN_OWNER")


def _validate_owner_annotation(
    row: dict[str, Any], *, schema_path: Path = _OWNER_ANNOTATION_SCHEMA
) -> None:
    try:
        Draft202012Validator(json.loads(schema_path.read_text(encoding="utf-8"))).validate(row)
    except ValidationError as error:
        raise ValueError("owner annotation does not match the locked schema") from error


def _hash(value: object, field: str) -> str:
    text = str(value or "")
    if not _SHA256.fullmatch(text):
        raise ValueError(f"{field} must be a lowercase SHA-256")
    return text


def load_owner_qualification(
    path: Path, prediction_path: Path | None = None
) -> list[QualificationInspection]:
    annotation_rows = _read_jsonl(path)
    for annotation_row in annotation_rows:
        _owner(annotation_row)
    if prediction_path is None:
        raise ValueError("independent qualification predictions are required")
    prediction_schema = json.loads(_QUALIFICATION_PREDICTION_SCHEMA.read_text(encoding="utf-8"))
    prediction_validator = Draft202012Validator(prediction_schema, format_checker=FormatChecker())
    predictions: dict[str, dict[str, Any]] = {}
    for prediction in _read_jsonl(prediction_path):
        prediction_validator.validate(prediction)
        case_id = str(prediction["case_id"])
        if case_id in predictions:
            raise ValueError("duplicate qualification prediction")
        predictions[case_id] = prediction
    inspections: list[QualificationInspection] = []
    annotation_ids: set[str] = set()
    for row in annotation_rows:
        _validate_owner_annotation(row)
        _hash(row.get("content_sha256"), "content_sha256")
        _hash(row.get("raw_object_sha256"), "raw_object_sha256")
        if (
            row.get("corpus_version") != OWNER_GOLD_CORPUS_VERSION
            or row.get("rule_version") != "intelligence-v2-qualification-1.0.0"
            or row.get("schema_version") != "intelligence-v2-owner-gold-2.0.0"
        ):
            raise ValueError("qualification rule_version is invalid")
        if not str(row.get("evidence_locator") or "").strip():
            raise ValueError("qualification locator cannot be empty")
        case_id = str(row.get("case_id") or "")
        if not case_id or case_id in annotation_ids:
            raise ValueError("qualification case_id is invalid")
        annotation_ids.add(case_id)
        matched_prediction = predictions.get(case_id)
        if (
            matched_prediction is None
            or matched_prediction.get("content_sha256") != row.get("content_sha256")
            or matched_prediction.get("corpus_version") != row.get("corpus_version")
            or matched_prediction.get("rule_version") != row.get("rule_version")
            or matched_prediction.get("model_id") != row.get("model_id")
            or matched_prediction.get("prompt_version") != row.get("prompt_version")
        ):
            raise ValueError("qualification prediction does not match annotation")
        bucket = str(row.get("bucket"))
        if bucket not in {"POSITIVE", "BOUNDARY", "NEGATIVE"}:
            raise ValueError("qualification bucket is invalid")
        expected = row.get("expected_relevant")
        predicted = matched_prediction.get("predicted_relevant")
        if not isinstance(expected, bool) or not isinstance(predicted, bool):
            raise ValueError("qualification relevance labels must be boolean")
        if expected:
            PrimaryIntelligenceType(str(row.get("primary_type")))
            objects = row.get("engineering_objects")
            if not isinstance(objects, list) or not objects:
                raise ValueError("relevant qualification labels require engineering objects")
            for value in objects:
                EngineeringObject(str(value))
        elif row.get("primary_type") is not None or row.get("engineering_objects"):
            raise ValueError("irrelevant qualification labels cannot assign type or object")
        locked = row.get("locked_negative")
        if not isinstance(locked, bool) or (bucket == "NEGATIVE" and not locked):
            raise ValueError("negative qualification labels must be locked")
        inspections.append(
            QualificationInspection(
                case_id=case_id,
                bucket=bucket,  # type: ignore[arg-type]
                expected_relevant=expected,
                predicted_relevant=predicted,
                locked_negative=locked,
            )
        )
    if annotation_ids != set(predictions):
        raise ValueError("qualification predictions are incomplete")
    return inspections


def _load_runtime(path: Path) -> list[RuntimeObservation]:
    values: list[RuntimeObservation] = []
    for row in _read_jsonl(path):
        values.append(
            RuntimeObservation(
                observed_at=datetime.fromisoformat(str(row["observed_at"])),
                worker_heartbeat_at=datetime.fromisoformat(str(row["worker_heartbeat_at"])),
                queue_healthy=row["queue_healthy"] is True,
                budget_healthy=row["budget_healthy"] is True,
                last_real_schema_success_at=(
                    datetime.fromisoformat(str(row["last_real_schema_success_at"]))
                    if row.get("last_real_schema_success_at")
                    else None
                ),
                external_balance_state=str(row["external_balance_state"]),  # type: ignore[arg-type]
            )
        )
    return values


def _load_feed(path: Path, *, acceptance_profile: AcceptanceProfile) -> list[FeedInspection]:
    values: list[FeedInspection] = []
    snapshot_hash: str | None = None
    for row in _read_jsonl(path):
        if acceptance_profile == "production":
            _owner(row)
            _validate_owner_annotation(row, schema_path=_FEED_OWNER_ANNOTATION_SCHEMA)
        else:
            try:
                Draft202012Validator(
                    json.loads(_FEED_STRUCTURAL_SCHEMA.read_text(encoding="utf-8"))
                ).validate(row)
            except ValidationError as error:
                raise ValueError(
                    "feed audit does not match the locked engineering schema"
                ) from error
        current_hash = _hash(row.get("snapshot_sha256"), "snapshot_sha256")
        _hash(row.get("content_sha256"), "content_sha256")
        _hash(row.get("raw_object_sha256"), "raw_object_sha256")
        expected_rule = (
            "intelligence-v2-feed-structural-engineering-1.0.0"
            if acceptance_profile == "engineering"
            else "intelligence-v2-feed-inspection-1.0.0"
        )
        if row.get("rule_version") != expected_rule:
            raise ValueError("feed inspection rule_version is invalid")
        if snapshot_hash is not None and current_hash != snapshot_hash:
            raise ValueError("feed annotations must belong to one frozen snapshot")
        snapshot_hash = current_hash
        relevant = row.get("owner_relevant")
        if acceptance_profile == "production" and not isinstance(relevant, bool):
            raise ValueError("feed owner_relevant must be boolean")
        values.append(
            FeedInspection(
                projection_id=str(row.get("projection_id") or ""),
                owner_relevant=relevant,
                risk_tier=str(row.get("risk_tier")),  # type: ignore[arg-type]
                unaccepted_claims=int(row.get("unaccepted_claims", -1)),
                unsupported_facts=int(row.get("unsupported_facts", -1)),
            )
        )
    return values


def _append_reason(reasons: list[str], reason: str) -> None:
    if reason not in reasons:
        reasons.append(reason)


def _source_assessments_valid(
    sources: dict[str, Any],
    rollout: dict[str, Any],
    *,
    acceptance_profile: AcceptanceProfile,
) -> bool:
    assessments = sources.get("assessments")
    expected_rule = (
        "civil-source-rollout-v2-engineering-1.0.0"
        if acceptance_profile == "engineering"
        else "civil-source-rollout-v2.0.0"
    )
    if sources.get("rule_version") != expected_rule or not isinstance(assessments, list):
        return False
    expected_batch = {
        str(institution): batch_index
        for batch_index, batch in enumerate(rollout["batches"], 1)
        for institution in batch["institutions"]
    }
    if len(assessments) != 20 or {
        str(value.get("institution")) for value in assessments if isinstance(value, dict)
    } != set(expected_batch):
        return False
    windows: dict[int, list[tuple[datetime, datetime, int]]] = {1: [], 2: []}
    wave_counts: Counter[tuple[int, int]] = Counter()
    for value in assessments:
        if not isinstance(value, dict):
            return False
        institution = str(value.get("institution"))
        batch = value.get("batch")
        wave = value.get("wave")
        if batch != expected_batch[institution] or not isinstance(wave, int) or not 1 <= wave <= 5:
            return False
        started_at = datetime.fromisoformat(str(value.get("started_at")))
        ended_at = datetime.fromisoformat(str(value.get("ended_at")))
        cutoff = datetime.fromisoformat(str(value.get("sample_cutoff")))
        if (
            started_at.tzinfo is None
            or ended_at.tzinfo is None
            or cutoff.tzinfo is None
            or ended_at - started_at
            < timedelta(hours=1 if acceptance_profile == "engineering" else 72)
            or cutoff > ended_at
            or value.get("lookback_days") != 90
        ):
            return False
        _hash(value.get("sample_manifest_sha256"), "sample_manifest_sha256")
        sample_size = value.get("sample_size")
        metrics = value.get("metrics")
        if not isinstance(sample_size, int) or not isinstance(metrics, dict):
            return False
        hard_flags = (
            "robots_allowed",
            "terms_allowed",
            "copyright_reviewed",
            "public_network_safe",
            "hard_negative_evaluated",
        )
        numeric_metrics = (
            "fetch_success_bps",
            "parse_evidence_success_bps",
            "metadata_success_bps",
            "useful_yield_bps",
            "duplicate_bps",
            "hard_negative_leaks",
        )
        if any(not isinstance(metrics.get(field), bool) for field in hard_flags) or any(
            not isinstance(metrics.get(field), int) or isinstance(metrics.get(field), bool)
            for field in numeric_metrics
        ):
            return False
        calculated = production_admission_verdict(
            SourceAdmissionMetrics(sample_size=sample_size, **metrics), calibration=None
        )
        if value.get("verdict") != calculated:
            return False
        windows[batch].append((started_at, ended_at, wave))
        wave_counts[(batch, wave)] += 1
    if any(wave_counts[(batch, wave)] != 2 for batch in (1, 2) for wave in range(1, 6)):
        return False
    if acceptance_profile == "engineering":
        return True
    first_start = min(start for start, _, _ in windows[1])
    first_end = max(end for _, end, _ in windows[1])
    second_start = min(start for start, _, _ in windows[2])
    return first_end - first_start >= timedelta(days=14) and second_start >= first_end


def build_closeout_report(root: Path, *, acceptance_profile: AcceptanceProfile) -> dict[str, Any]:
    reasons: list[str] = []
    checks: dict[str, object] = {}
    runtime_values: list[RuntimeObservation] = []

    runtime_path = root / "runtime.jsonl"
    if runtime_path.is_file():
        try:
            runtime_values = _load_runtime(runtime_path)
            runtime = evaluate_runtime_window(runtime_values, acceptance_profile=acceptance_profile)
            checks["ai_runtime"] = runtime.__dict__
            reasons.extend(runtime.reasons)
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            _append_reason(reasons, "AI_RUNTIME_EVIDENCE_INVALID")
    else:
        _append_reason(reasons, "AI_RUNTIME_WINDOW_INCOMPLETE")

    qualification_path = root / "qualification.jsonl"
    qualification_prediction_path = root / "qualification-predictions.jsonl"
    calibration_path = root / "qualification-calibration.json"
    if acceptance_profile == "engineering":
        checks["qualification"] = {
            "passed": True,
            "required": False,
            "rule_version": "not-required-engineering-1.0.0",
        }
    elif qualification_path.is_file() and qualification_prediction_path.is_file():
        try:
            qualification_values = load_owner_qualification(
                qualification_path, qualification_prediction_path
            )
            distribution = Counter(value.bucket for value in qualification_values)
            if len(qualification_values) != 40 or distribution != {
                "POSITIVE": 20,
                "NEGATIVE": 20,
            }:
                _append_reason(reasons, "OWNER_GOLD_INCOMPLETE")
            qualification = evaluate_qualification(qualification_values)
            if not calibration_path.is_file():
                _append_reason(reasons, "OWNER_GOLD_CALIBRATION_INCOMPLETE")
                checks["qualification"] = qualification.__dict__ | {"distribution": distribution}
            else:
                calibration = load_calibration_fact(calibration_path)
                grant = calibration_grant(
                    calibration,
                    corpus_version=OWNER_GOLD_CORPUS_VERSION,
                    rule_version="intelligence-v2-qualification-1.0.0",
                    model_id="deepseek-v4-flash",
                    prompt_version="ai01-classify-v1",
                )
                if grant is None:
                    _append_reason(reasons, "OWNER_GOLD_CALIBRATION_NO_GO")
                checks["qualification"] = qualification.__dict__ | {
                    "distribution": distribution,
                    "calibration_fact_sha256": calibration.fact_sha256,
                    "corpus_version": calibration.corpus_version,
                    "model_id": calibration.model_id,
                    "prompt_version": calibration.prompt_version,
                    "auto_pass_threshold_bps": calibration.auto_pass_threshold_bps,
                    "calibration_decision": calibration.decision,
                }
            reasons.extend(qualification.reasons)
        except (TypeError, ValueError, json.JSONDecodeError):
            _append_reason(reasons, "OWNER_GOLD_OR_CALIBRATION_INVALID")
    else:
        _append_reason(reasons, "OWNER_GOLD_INCOMPLETE")

    feed_path = root / "feed.jsonl"
    if feed_path.is_file():
        try:
            feed = evaluate_feed(
                _load_feed(feed_path, acceptance_profile=acceptance_profile),
                acceptance_profile=acceptance_profile,
            )
            checks["feed"] = feed.__dict__
            reasons.extend(feed.reasons)
        except (TypeError, ValueError, json.JSONDecodeError):
            _append_reason(reasons, "FEED_SAMPLE_INVALID")
    else:
        _append_reason(reasons, "FEED_SAMPLE_INSUFFICIENT")

    sources_path = root / "sources.json"
    if sources_path.is_file():
        try:
            sources = _read_json(sources_path)
            assessments = sources.get("assessments")
            rollout = _read_json(_SOURCE_ROLLOUT)
            valid = _source_assessments_valid(
                sources, rollout, acceptance_profile=acceptance_profile
            )
            checks["sources"] = {"passed": valid, "count": len(assessments or [])}
            if not valid:
                _append_reason(reasons, "SOURCE_ASSESSMENT_INCOMPLETE")
        except (TypeError, ValueError, json.JSONDecodeError):
            _append_reason(reasons, "SOURCE_ASSESSMENT_INVALID")
    else:
        _append_reason(reasons, "SOURCE_ASSESSMENT_INCOMPLETE")

    engineering_path = root / "engineering.json"
    if engineering_path.is_file():
        engineering = _read_json(engineering_path)
        missing_gates = [gate for gate in _ENGINEERING_GATES if engineering.get(gate) is not True]
        checks["engineering"] = {"passed": not missing_gates, "missing": missing_gates}
        if missing_gates:
            _append_reason(reasons, "ENGINEERING_GATES_FAILED")
    else:
        _append_reason(reasons, "ENGINEERING_GATES_INCOMPLETE")

    compensation_path = root / "compensation.json"
    if compensation_path.is_file():
        compensation = _read_json(compensation_path)
        try:
            result = evaluate_compensation(
                CompensationInspection(
                    injected_transient_count=int(compensation.get("injected_transient_count", 0)),
                    recovered_count=int(compensation.get("recovered_count", -1)),
                    injected_permanent_count=int(compensation.get("injected_permanent_count", 0)),
                    permanent_error_observed_count=int(
                        compensation.get("permanent_error_observed_count", 0)
                    ),
                    duplicate_side_effects=int(compensation.get("duplicate_side_effects", -1)),
                    stale_version_recoveries=int(compensation.get("stale_version_recoveries", -1)),
                    permanent_error_retries=int(compensation.get("permanent_error_retries", -1)),
                )
            )
            checks["compensation"] = {
                "passed": result.passed,
                "reasons": result.reasons,
            }
            if not result.passed:
                _append_reason(reasons, "AI_COMPENSATION_INCOMPLETE")
        except (TypeError, ValueError):
            _append_reason(reasons, "AI_COMPENSATION_INCOMPLETE")
    else:
        _append_reason(reasons, "AI_COMPENSATION_INCOMPLETE")

    preflight_path = root / "preflight.json"
    if preflight_path.is_file():
        preflight = _read_json(preflight_path)
        preflight_ok = (
            all(
                preflight.get(field) is True
                for field in (
                    "backup_receipt_verified",
                    "object_inventory_verified",
                    "audit_tail_anchor_verified",
                    "v1_archive_sha256_verified",
                )
            )
            and preflight.get("mutation_performed") is False
        )
        checks["preflight"] = {
            "passed": preflight_ok,
            "mutation_performed": preflight.get("mutation_performed"),
        }
        if not preflight_ok:
            _append_reason(reasons, "ARCHIVE_PREFLIGHT_INCOMPLETE")
    else:
        _append_reason(reasons, "ARCHIVE_PREFLIGHT_INCOMPLETE")

    baseline_commit: str | None = None
    environment: str | None = None
    campaign_id: str | None = None
    context_path = root / "context.json"
    if context_path.is_file():
        try:
            supplied_context = _read_json(context_path)
            candidate_commit = str(supplied_context.get("baseline_commit") or "")
            candidate_environment = str(supplied_context.get("environment") or "").strip()
            candidate_campaign_id = str(supplied_context.get("campaign_id") or "")
            if (
                _GIT_COMMIT.fullmatch(candidate_commit)
                and supplied_context.get("migration_head") == "0039_t04_content_candidates"
                and candidate_environment
                and _UUID7.fullmatch(candidate_campaign_id)
            ):
                baseline_commit = candidate_commit
                environment = candidate_environment
                campaign_id = candidate_campaign_id
            else:
                _append_reason(reasons, "READINESS_CONTEXT_INVALID")
        except (TypeError, ValueError, json.JSONDecodeError):
            _append_reason(reasons, "READINESS_CONTEXT_INVALID")
    else:
        _append_reason(reasons, "READINESS_CONTEXT_INCOMPLETE")

    ordered_runtime = sorted(runtime_values, key=lambda value: value.observed_at)
    time_window = (
        {
            "start": ordered_runtime[0].observed_at.isoformat(),
            "end": ordered_runtime[-1].observed_at.isoformat(),
        }
        if ordered_runtime
        else None
    )
    evidence_refs = [
        {
            "path": name,
            "sha256": sha256((root / name).read_bytes()).hexdigest(),
        }
        for name in _EVIDENCE_FILES
        if (root / name).is_file()
    ]
    context = {
        "baseline_commit": baseline_commit,
        "migration_head": "0039_t04_content_candidates",
        "environment": environment,
        "campaign_id": campaign_id,
        "time_window": time_window,
        "rule_versions": {
            "closeout": (
                "intelligence-v2-closeout-engineering-1.0.0"
                if acceptance_profile == "engineering"
                else "intelligence-v2-closeout-production-1.0.0"
            ),
            "source_rollout": (
                "civil-source-rollout-v2-engineering-1.0.0"
                if acceptance_profile == "engineering"
                else "civil-source-rollout-v2.0.0"
            ),
            "qualification": (
                "not-required-engineering-1.0.0"
                if acceptance_profile == "engineering"
                else "intelligence-v2-qualification-1.0.0"
            ),
            "feed_inspection": (
                "intelligence-v2-feed-structural-engineering-1.0.0"
                if acceptance_profile == "engineering"
                else "intelligence-v2-feed-inspection-1.0.0"
            ),
            "runtime": (
                "intelligence-v2-runtime-engineering-1.0.0"
                if acceptance_profile == "engineering"
                else "intelligence-v2-runtime-production-1.0.0"
            ),
        },
        "evidence_refs": evidence_refs,
    }

    report: dict[str, Any] = {
        "schema_version": "intelligence-v2-closeout-1.0.0",
        "acceptance_profile": (
            "ENGINEERING_CLOSEOUT" if acceptance_profile == "engineering" else "PRODUCTION_CLOSEOUT"
        ),
        "generated_at": datetime.now(UTC).isoformat(),
        "decision": "GO" if not reasons else "NO_GO",
        "reasons": list(dict.fromkeys(reasons)),
        "checks": checks,
        "context": context,
    }
    report["manifest_sha256"] = sha256(_canonical_json(report)).hexdigest()
    schema = json.loads(_REPORT_SCHEMA.read_text(encoding="utf-8"))
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--acceptance-profile",
        choices=("engineering", "production"),
        required=True,
    )
    parser.add_argument("--evidence-root", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = build_closeout_report(args.evidence_root, acceptance_profile=args.acceptance_profile)
    rendered = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0 if report["decision"] == "GO" else 1


if __name__ == "__main__":
    raise SystemExit(main())
