"""Publication gate v2 evaluated only from server-authoritative context."""

import json
from collections.abc import Mapping
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any, Literal, TypeGuard

from jsonschema import Draft202012Validator, FormatChecker


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
            policy.get("version")
            not in {"2.0.0", "2.1.0", "3.0.0", "4.0.0", "5.0.0", "6.0.0", "7.0.0"}
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
        if tuple(
            Draft202012Validator(self._schema, format_checker=FormatChecker()).iter_errors(context)
        ):
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
        round04 = _mapping(server.get("round04"))
        round05 = _mapping(server.get("round05"))
        round06 = _mapping(server.get("round06"))
        round07 = _mapping(server.get("round07"))

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
        unresolved_conflicts = evidence.get("unresolved_conflict_count")
        if not _is_nonnegative_count(unresolved_conflicts) or unresolved_conflicts > 0:
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
        if self.policy_version == "2.1.0":
            if pipeline.get("unauthorized_candidate_field_count") != 0:
                reasons.append("UNAUTHORIZED_AI_AUTHORITY_CANDIDATE")
            ai_status = pipeline.get("ai_status")
            if ai_status not in {"VALIDATED", "NOT_RUN_DEGRADED"}:
                reasons.append("AI_PIPELINE_STATUS_INVALID")
            if ai_status == "VALIDATED":
                if pipeline.get("four_steps_completed") is not True:
                    reasons.append("AI_FOUR_STEPS_INCOMPLETE")
                if pipeline.get("accepted_summary_claim_refs_valid") is not True:
                    reasons.append("SUMMARY_CLAIM_REFS_INVALID")
        if review.get("risk_level") == "R4":
            reasons.append("R4_NOT_PUBLISHABLE")

        if (
            item.get("item_type") in {"SAFETY_REGULATION", "SAFETY_CASE"}
            or review.get("risk_level") == "R3"
        ):
            if review.get("decision_status") != "APPROVED" or not review.get("decision_id"):
                reasons.append("HUMAN_REVIEW_REQUIRED")
            if review.get("duties_separated") is not True:
                reasons.append("DUTIES_NOT_SEPARATED")
            if review.get("submitted_by") == review.get("decided_by"):
                reasons.append("DUTIES_NOT_SEPARATED")
            if (
                self.policy_version == "2.1.0"
                and not str(review.get("decision_reason") or "").strip()
            ):
                reasons.append("HUMAN_REVIEW_REASON_REQUIRED")

        if self.policy_version in {
            "2.1.0",
            "3.0.0",
            "4.0.0",
            "5.0.0",
            "6.0.0",
            "7.0.0",
        }:
            if document.get("processing_state") != "READY":
                reasons.append("DOCUMENT_NOT_READY")
            if document.get("raw_security_status") != "CLEAN":
                reasons.append("RAW_OBJECT_NOT_CLEAN")
            if _number(evidence.get("minimum_critical_ocr_confidence_bps")) < 9500:
                reasons.append("OCR_CRITICAL_CONFIDENCE_TOO_LOW")
            unresolved_relations = round03.get("unresolved_relation_candidate_count")
            if not _is_nonnegative_count(unresolved_relations) or unresolved_relations > 0:
                reasons.append("RELATION_CANDIDATE_UNREVIEWED")
            unreviewed_status = round03.get("unreviewed_regulation_status_candidate_count")
            if not _is_nonnegative_count(unreviewed_status) or unreviewed_status > 0:
                reasons.append("REGULATION_STATUS_CANDIDATE_UNREVIEWED")
            unsafe_attachments = round03.get("unsafe_attachment_count")
            if not _is_nonnegative_count(unsafe_attachments) or unsafe_attachments > 0:
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

        if (
            self.policy_version in {"2.1.0", "4.0.0", "5.0.0", "6.0.0", "7.0.0"}
            and item.get("item_type") == "SAFETY_CASE"
        ):
            if round04.get("event_assignment_confirmed") is not True:
                reasons.append("SAFETY_CASE_EVENT_UNCONFIRMED")
            if round04.get("profile_metadata_claims_authorized") is not True:
                reasons.append("SAFETY_CASE_PROFILE_METADATA_UNAUTHORIZED")
            unreviewed_critical = round04.get("unreviewed_critical_claim_count")
            if not _is_nonnegative_count(unreviewed_critical) or unreviewed_critical > 0:
                reasons.append("SAFETY_CASE_CRITICAL_CLAIM_UNREVIEWED")
            casualty_conflicts = round04.get("unresolved_casualty_loss_conflict_count")
            if not _is_nonnegative_count(casualty_conflicts) or casualty_conflicts > 0:
                reasons.append("SAFETY_CASE_CASUALTY_LOSS_CONFLICT")
            if round04.get("casualty_loss_claims_authorized") is not True:
                reasons.append("SAFETY_CASE_CASUALTY_LOSS_NOT_AUTHORIZED")
            _check_formal_basis(
                round04,
                state_field="cause_basis_state",
                evidence_field="formal_cause_evidence_authorized",
                reason="SAFETY_CASE_CAUSE_NOT_FORMALLY_AUTHORIZED",
                reasons=reasons,
            )
            _check_formal_basis(
                round04,
                state_field="responsibility_basis_state",
                evidence_field="formal_responsibility_evidence_authorized",
                reason="SAFETY_CASE_RESPONSIBILITY_NOT_FORMALLY_AUTHORIZED",
                reasons=reasons,
            )
            if round04.get("controlled_prevention_tags_only") is not True:
                reasons.append("SAFETY_CASE_UNCONTROLLED_PREVENTION_CONTENT")
            operational_instructions = round04.get("operational_instruction_count")
            if not _is_nonnegative_count(operational_instructions) or operational_instructions > 0:
                reasons.append("SAFETY_CASE_OPERATIONAL_INSTRUCTION_FORBIDDEN")

        if (
            self.policy_version in {"2.1.0", "5.0.0", "6.0.0", "7.0.0"}
            and item.get("item_type") == "DIGITAL_CASE"
        ):
            if round05.get("classification_claims_authorized") is not True:
                reasons.append("DIGITAL_CLASSIFICATION_UNAUTHORIZED")
            if round05.get("outcome_attribution_valid") is not True:
                reasons.append("DIGITAL_OUTCOME_ATTRIBUTION_INVALID")
            if round05.get("verified_outcomes_have_independent_evidence") is not True:
                reasons.append("DIGITAL_VERIFIED_OUTCOME_EVIDENCE_REQUIRED")
            if round05.get("maturity_evidence_valid") is not True:
                reasons.append("DIGITAL_MATURITY_EVIDENCE_REQUIRED")
            if round05.get("relevance_rule_version") != "relevance-v1.0.0":
                reasons.append("DIGITAL_RELEVANCE_RULE_INVALID")
            relevance_score = round05.get("relevance_score")
            if (
                not isinstance(relevance_score, int)
                or isinstance(relevance_score, bool)
                or not 0 <= relevance_score <= 100
            ):
                reasons.append("DIGITAL_RELEVANCE_RULE_INVALID")
            if round05.get("recommended_actions_valid") is not True:
                reasons.append("DIGITAL_RECOMMENDED_ACTION_INVALID")
            source_nature = round05.get("source_nature")
            if source_nature not in {
                "GOVERNMENT_CASE_COLLECTION",
                "ENTERPRISE_SELF_REPORT",
            }:
                reasons.append("DIGITAL_SOURCE_NATURE_INVALID")
            if source_nature == "ENTERPRISE_SELF_REPORT" and (
                review.get("decision_status") != "APPROVED"
                or not review.get("decision_id")
                or review.get("duties_separated") is not True
            ):
                reasons.append("ENTERPRISE_CASE_HUMAN_REVIEW_REQUIRED")

        if (
            self.policy_version in {"2.1.0", "6.0.0", "7.0.0"}
            and item.get("item_type") == "JOURNAL_PAPER"
        ):
            if round06.get("identity_resolved") is not True:
                reasons.append("PAPER_IDENTITY_UNRESOLVED")
            access_level = round06.get("access_level")
            if (
                access_level
                not in {
                    "METADATA_ONLY",
                    "ABSTRACT_ALLOWED",
                    "OPEN_FULLTEXT",
                }
                or round06.get("access_policy_valid") is not True
            ):
                reasons.append("PAPER_ACCESS_POLICY_INVALID")
            if round06.get("abstract_present") is True and (
                round06.get("abstract_permitted") is not True or access_level == "METADATA_ONLY"
            ):
                reasons.append("PAPER_ABSTRACT_LICENCE_REQUIRED")
            fulltext_storage_count = round06.get("fulltext_storage_count")
            if not _is_nonnegative_count(fulltext_storage_count) or fulltext_storage_count > 0:
                reasons.append("PAPER_FULLTEXT_STORAGE_FORBIDDEN")
            if (
                access_level == "OPEN_FULLTEXT"
                and round06.get("fulltext_link_licensed") is not True
            ):
                reasons.append("PAPER_FULLTEXT_LICENCE_REQUIRED")
            if round06.get("research_claim_refs_valid") is not True:
                reasons.append("PAPER_RESEARCH_CLAIM_REFS_INVALID")
            if round06.get("maturity_evidence_valid") is not True:
                reasons.append("PAPER_MATURITY_EVIDENCE_REQUIRED")
            unreviewed_updates = round06.get("unreviewed_update_relation_count")
            if not _is_nonnegative_count(unreviewed_updates) or unreviewed_updates > 0:
                reasons.append("PAPER_UPDATE_RELATION_UNREVIEWED")
            if round06.get("relation_status") not in {
                "CURRENT",
                "CORRECTED",
                "RETRACTED",
                "WITHDRAWN",
            }:
                reasons.append("PAPER_RELATION_STATUS_INVALID")

        product_types = {
            "SOFTWARE_PRODUCT",
            "IOT_PRODUCT",
            "LOW_ALTITUDE_EQUIPMENT",
            "AI_EQUIPMENT",
        }
        if self.policy_version in {"2.1.0", "7.0.0"} and item.get("item_type") in product_types:
            if round07.get("identity_safe") is not True:
                reasons.append("PRODUCT_IDENTITY_UNSAFE")
            if round07.get("capability_groups_separated") is not True:
                reasons.append("PRODUCT_CAPABILITY_GROUPS_INVALID")
            if round07.get("verified_capabilities_have_independent_evidence") is not True:
                reasons.append("PRODUCT_VERIFIED_CAPABILITY_EVIDENCE_REQUIRED")
            if round07.get("promotional_claims_vendor_attributed") is not True:
                reasons.append("PRODUCT_PROMOTIONAL_ATTRIBUTION_REQUIRED")
            procurement_conclusions = round07.get("procurement_conclusion_count")
            if not _is_nonnegative_count(procurement_conclusions) or procurement_conclusions > 0:
                reasons.append("PRODUCT_PROCUREMENT_CONCLUSION_FORBIDDEN")
            image_downloads = round07.get("vendor_image_download_count")
            if not _is_nonnegative_count(image_downloads) or image_downloads > 0:
                reasons.append("PRODUCT_VENDOR_IMAGE_DOWNLOAD_FORBIDDEN")
            permit_status = round07.get("permit_status")
            if permit_status not in {"VERIFIED", "NOT_REQUIRED", "UNKNOWN"}:
                reasons.append("PRODUCT_PERMIT_STATUS_INVALID")
            if (
                item.get("item_type") == "LOW_ALTITUDE_EQUIPMENT"
                and permit_status == "VERIFIED"
                and round07.get("permit_evidence_authorized") is not True
            ):
                reasons.append("PRODUCT_PERMIT_EVIDENCE_REQUIRED")
            if action == "SELECTED" and (
                review.get("decision_status") != "APPROVED"
                or not review.get("decision_id")
                or review.get("duties_separated") is not True
                or review.get("submitted_by") == review.get("decided_by")
            ):
                reasons.append("PRODUCT_SELECTED_HUMAN_REVIEW_REQUIRED")

        if action == "SELECTED":
            if item.get("item_type") not in {"DIGITAL_CASE", "JOURNAL_PAPER", *product_types}:
                scores = server.get("scores")
                if not isinstance(scores, Mapping):
                    reasons.append("SELECTED_SCORES_REQUIRED")
                else:
                    minimums = self._policy["selected_feed_rules"]["minimum_server_scores"]
                    if any(
                        _number(scores.get(name)) < minimum for name, minimum in minimums.items()
                    ):
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


def _check_formal_basis(
    round04: Mapping[str, Any],
    *,
    state_field: str,
    evidence_field: str,
    reason: str,
    reasons: list[str],
) -> None:
    state = round04.get(state_field)
    if state == "NO_FORMAL_BASIS":
        return
    if state not in {"FORMAL_REVIEWED_NO_FINDING", "FORMAL_REVIEWED_FINDINGS"}:
        reasons.append(reason)
        return
    if round04.get(evidence_field) is not True:
        reasons.append(reason)


def _number(value: Any) -> float:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else 0.0


def _is_nonnegative_count(value: object) -> TypeGuard[int]:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0
