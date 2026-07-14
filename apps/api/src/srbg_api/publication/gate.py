"""Publication gate v2 evaluated only from server-authoritative context."""

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any, Literal


@dataclass(frozen=True, slots=True)
class GateResult:
    allowed: bool
    decision: Literal["PUBLISH", "SELECTED", "DENY"]
    reasons: tuple[str, ...]
    policy_version: str
    policy_sha256: str


class PublicationGate:
    def __init__(self, policy: dict[str, Any], schema: dict[str, Any], policy_sha256: str) -> None:
        if (
            policy.get("version") not in {"2.0.0", "3.0.0"}
            or policy.get("default_decision") != "DENY"
        ):
            raise ValueError("publication gate must be a supported default-deny policy")
        if schema.get("title") != "Authoritative Publication Evaluation Context":
            raise ValueError("unexpected publication evaluation schema")
        self._policy = policy
        self._schema = schema
        self.policy_sha256 = policy_sha256

    @property
    def policy_version(self) -> str:
        return str(self._policy["version"])

    @classmethod
    def from_files(cls, policy_path: Path, schema_path: Path) -> "PublicationGate":
        policy_bytes = policy_path.read_bytes()
        return cls(
            json.loads(policy_bytes),
            json.loads(schema_path.read_text(encoding="utf-8")),
            sha256(policy_bytes).hexdigest(),
        )

    def evaluate(
        self,
        context: Mapping[str, Any],
        *,
        action: Literal["PUBLISH", "SELECTED"],
    ) -> GateResult:
        reasons: list[str] = []
        if _schema_errors(context, self._schema, "$"):
            reasons.append("EVALUATION_SCHEMA_INVALID")
        if context.get("policy_version") != self._policy["version"]:
            reasons.append("POLICY_VERSION_MISMATCH")
        if context.get("policy_sha256") != self.policy_sha256:
            reasons.append("POLICY_HASH_MISMATCH")

        item = _mapping(context.get("item"))
        server = _mapping(context.get("server"))
        source = _mapping(server.get("source"))
        document = _mapping(server.get("document"))
        evidence = _mapping(server.get("evidence_integrity"))
        security = _mapping(server.get("security"))
        privacy = _mapping(server.get("privacy"))
        review = _mapping(server.get("review"))
        pipeline = _mapping(server.get("pipeline"))
        round03 = _mapping(server.get("round03"))

        if item.get("is_demo") is True or item.get("publishable") is not True:
            reasons.append("DEMO_OR_NONPUBLISHABLE")
        if source.get("status") != "ACTIVE":
            reasons.append("SOURCE_NOT_ACTIVE")
        if source.get("policy_status") != "VALID":
            reasons.append("SOURCE_POLICY_INVALID")
        if source.get("excerpt_policy_pass") is not True:
            reasons.append("COPYRIGHT_OR_ATTRIBUTION_INVALID")
        if source.get("attribution_policy_pass") is not True:
            reasons.append("COPYRIGHT_OR_ATTRIBUTION_INVALID")
        if document.get("is_current") is not True:
            reasons.append("DOCUMENT_NOT_CURRENT")
        if document.get("lifecycle_status") in {"WITHDRAWN", "SUPERSEDED"}:
            reasons.append("DOCUMENT_WITHDRAWN_OR_SUPERSEDED")
        if document.get("hash_verified") is not True or document.get("url_policy_pass") is not True:
            reasons.append("DOCUMENT_HASH_OR_URL_INVALID")
        if _number(evidence.get("claim_count")) < 1 or _number(evidence.get("evidence_count")) < 1:
            reasons.append("EMPTY_CLAIM_OR_EVIDENCE_SET")
        if not all(
            evidence.get(field) is True
            for field in (
                "bidirectional_refs_valid",
                "locators_verified",
                "excerpts_match_source",
            )
        ):
            reasons.append("EVIDENCE_REFERENTIAL_INTEGRITY_FAILED")
        if _number(evidence.get("accepted_critical_claim_coverage_percent")) < 100:
            reasons.append("CRITICAL_CLAIM_COVERAGE_INCOMPLETE")
        if _number(evidence.get("unresolved_conflict_count")) > 0:
            reasons.append("UNRESOLVED_CLAIM_CONFLICT")
        if security.get("resolution_status") not in {"NONE", "RESOLVED_BY_SECURITY_REVIEW"}:
            reasons.append("PROMPT_INJECTION_UNRESOLVED")
        if security.get("prompt_injection_detected") is True and not security.get("resolution_id"):
            reasons.append("PROMPT_INJECTION_UNRESOLVED")
        if privacy.get("status") not in {"CLEAR", "REDACTED_AND_APPROVED"}:
            reasons.append("PII_OR_REPUTATIONAL_REVIEW_FAILED")
        if pipeline.get("candidate_schema_valid") is not True:
            reasons.append("CANDIDATE_SCHEMA_INVALID")
        if pipeline.get("semantic_safety_scan_pass") is not True:
            reasons.append("SEMANTIC_SAFETY_SCAN_FAILED")

        if item.get("item_type") == "SAFETY_REGULATION" or review.get("risk_level") == "R3":
            if review.get("decision_status") != "APPROVED" or not review.get("decision_id"):
                reasons.append("HUMAN_REVIEW_REQUIRED")
            if review.get("duties_separated") is not True:
                reasons.append("DUTIES_NOT_SEPARATED")
            if review.get("submitted_by") == review.get("decided_by"):
                reasons.append("DUTIES_NOT_SEPARATED")

        if self.policy_version == "3.0.0":
            if document.get("processing_state") != "READY":
                reasons.append("DOCUMENT_NOT_READY")
            if document.get("raw_security_status") != "CLEAN":
                reasons.append("RAW_OBJECT_NOT_CLEAN")
            if _number(evidence.get("minimum_critical_ocr_confidence_bps")) < 9500:
                reasons.append("OCR_CRITICAL_CONFIDENCE_TOO_LOW")
            if _number(round03.get("unresolved_relation_candidate_count")) > 0:
                reasons.append("RELATION_CANDIDATE_UNREVIEWED")
            if _number(round03.get("unreviewed_regulation_status_candidate_count")) > 0:
                reasons.append("REGULATION_STATUS_CANDIDATE_UNREVIEWED")
            if _number(round03.get("unsafe_attachment_count")) > 0:
                reasons.append("ATTACHMENT_NOT_CLEAN")
            if round03.get("summary_claim_refs_valid") is not True:
                reasons.append("SUMMARY_CLAIM_REFS_INVALID")
            if item.get("regulation_status", "UNKNOWN") != "UNKNOWN" and not (
                round03.get("official_status_evidence") is True
                and round03.get("status_reviewer_decision") is True
            ):
                reasons.append("LEGAL_EFFECT_NOT_AUTHORIZED")
        elif item.get("regulation_status", "UNKNOWN") != "UNKNOWN":
            reasons.append("LEGAL_EFFECT_NOT_AUTHORIZED")

        if action == "SELECTED":
            scores = server.get("scores")
            if not isinstance(scores, Mapping):
                reasons.append("SELECTED_SCORES_REQUIRED")
            else:
                minimums = self._policy["selected_feed_rules"]["minimum_server_scores"]
                if any(_number(scores.get(name)) < minimum for name, minimum in minimums.items()):
                    reasons.append("SELECTED_SCORE_THRESHOLD_FAILED")

        unique_reasons = tuple(dict.fromkeys(reasons))
        return GateResult(
            allowed=not unique_reasons,
            decision=action if not unique_reasons else "DENY",
            reasons=unique_reasons,
            policy_version=str(self._policy["version"]),
            policy_sha256=self.policy_sha256,
        )


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _number(value: Any) -> float:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else 0.0


def _schema_errors(value: Any, schema: Mapping[str, Any], path: str) -> list[str]:
    errors: list[str] = []
    if "const" in schema and value != schema["const"]:
        errors.append(f"{path}:const")
    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{path}:enum")

    declared_type = schema.get("type")
    if declared_type is not None and not _matches_type(value, declared_type):
        return [*errors, f"{path}:type"]

    if isinstance(value, Mapping):
        required = schema.get("required", [])
        for name in required:
            if name not in value:
                errors.append(f"{path}.{name}:required")
        properties = _mapping(schema.get("properties"))
        if schema.get("additionalProperties") is False:
            for name in value:
                if name not in properties:
                    errors.append(f"{path}.{name}:additional")
        for name, child_schema in properties.items():
            if name in value and isinstance(child_schema, Mapping):
                errors.extend(_schema_errors(value[name], child_schema, f"{path}.{name}"))
    elif isinstance(value, list):
        minimum = schema.get("minItems")
        if isinstance(minimum, int) and len(value) < minimum:
            errors.append(f"{path}:minItems")
        if schema.get("uniqueItems") is True and len({repr(item) for item in value}) != len(value):
            errors.append(f"{path}:uniqueItems")
        child_schema = schema.get("items")
        if isinstance(child_schema, Mapping):
            for index, child in enumerate(value):
                errors.extend(_schema_errors(child, child_schema, f"{path}[{index}]"))
    elif isinstance(value, str):
        minimum = schema.get("minLength")
        if isinstance(minimum, int) and len(value) < minimum:
            errors.append(f"{path}:minLength")
        pattern = schema.get("pattern")
        if isinstance(pattern, str) and re.search(pattern, value) is None:
            errors.append(f"{path}:pattern")
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        minimum = schema.get("minimum")
        maximum = schema.get("maximum")
        if isinstance(minimum, (int, float)) and value < minimum:
            errors.append(f"{path}:minimum")
        if isinstance(maximum, (int, float)) and value > maximum:
            errors.append(f"{path}:maximum")

    for condition in schema.get("allOf", []):
        if not isinstance(condition, Mapping):
            continue
        if_schema = condition.get("if")
        then_schema = condition.get("then")
        if isinstance(if_schema, Mapping) and isinstance(then_schema, Mapping):
            if not _schema_errors(value, if_schema, path):
                errors.extend(_schema_errors(value, then_schema, path))
    return errors


def _matches_type(value: Any, declared: Any) -> bool:
    if isinstance(declared, list):
        return any(_matches_type(value, item) for item in declared)
    return {
        "object": isinstance(value, Mapping),
        "array": isinstance(value, list),
        "string": isinstance(value, str),
        "integer": isinstance(value, int) and not isinstance(value, bool),
        "number": isinstance(value, (int, float)) and not isinstance(value, bool),
        "boolean": isinstance(value, bool),
        "null": value is None,
    }.get(str(declared), True)
