"""Deterministic, evidence-bound source profiling for the personal platform."""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from hashlib import sha256
from urllib.parse import urlsplit

from srbg_contracts import (
    AuthorityLevel,
    SourceContentDomain,
    SourceDeclaredRole,
    SourceIndependenceLevel,
    SourceIndustry,
    SourceProfileCandidate,
    SourceProfileModelOutput,
)

RULE_VERSION = "source-profile-rules-v1"
PROMPT_VERSION = "source-profile-prompt-v1"
SCHEMA_VERSION = "source-profile-output-v1"
MODEL_VERSION = "deepseek-v4-flash"
PROFILE_FIELDS = (
    "industries",
    "content_domains",
    "language_tags",
    "country_codes",
    "region_codes",
    "declared_roles",
    "authority_level",
    "independence_level",
)


@dataclass(frozen=True, slots=True)
class ProfileEvidence:
    evidence_id: str
    kind: str
    url: str
    sha256: str
    excerpt: str


@dataclass(frozen=True, slots=True)
class ProfileRuleInput:
    origin: str
    stream_types: tuple[str, ...]
    evidence: tuple[ProfileEvidence, ...]


@dataclass(frozen=True, slots=True)
class TechnicalFact:
    code: str
    confidence: int = 95


@dataclass(frozen=True, slots=True)
class FieldExplanation:
    confidence: int
    reason_codes: tuple[str, ...]
    evidence_ids: tuple[str, ...]
    basis: str = "AUTO_INFERRED"


@dataclass(frozen=True, slots=True)
class BuiltSourceProfile:
    status: str
    industries: tuple[str, ...]
    content_domains: tuple[str, ...]
    language_tags: tuple[str, ...]
    country_codes: tuple[str, ...]
    region_codes: tuple[str, ...]
    declared_roles: tuple[str, ...]
    authority_level: str
    independence_level: str
    authority_basis: str
    independence_basis: str
    overall_confidence: int
    field_explanations: dict[str, FieldExplanation]
    technical_facts: tuple[TechnicalFact, ...]
    reason_codes: tuple[str, ...]


def canonical_profile_input_hash(value: ProfileRuleInput) -> str:
    payload = {
        "origin": value.origin,
        "stream_types": sorted(set(value.stream_types)),
        "evidence": sorted(
            (asdict(item) for item in value.evidence), key=lambda item: str(item["evidence_id"])
        ),
    }
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()
    return sha256(encoded).hexdigest()


def validate_model_evidence(
    output: SourceProfileModelOutput, evidence: tuple[ProfileEvidence, ...]
) -> None:
    issued = {item.evidence_id for item in evidence}
    for collection in (
        output.industry_candidates,
        output.content_domain_candidates,
        output.language_candidates,
        output.country_candidates,
        output.region_candidates,
        output.declared_role_candidates,
        output.organization_clues,
        output.ownership_clues,
    ):
        for candidate in collection:
            if not set(candidate.evidence_ids).issubset(issued):
                raise ValueError("profile evidence id was not server-issued")


def build_source_profile(
    source: ProfileRuleInput,
    *,
    model_output: SourceProfileModelOutput | None,
    partial_reason: str | None = None,
) -> BuiltSourceProfile:
    if model_output is not None:
        validate_model_evidence(model_output, source.evidence)
    text = " ".join(item.excerpt for item in source.evidence).casefold()
    evidence_ids = tuple(item.evidence_id for item in source.evidence)
    host = (urlsplit(source.origin).hostname or "").casefold()
    is_china = host.endswith(".cn") or any(marker in text for marker in ("中国", "中华人民共和国"))
    is_government = host.endswith(".gov.cn") or any(
        marker in text for marker in ("国务院组成部门", "人民政府", "交通运输部", "应急管理部")
    )

    industries: list[str] = []
    if any(marker in text for marker in ("公路", "高速公路")):
        industries.append(SourceIndustry.HIGHWAY.value)
    if any(marker in text for marker in ("交通运输", "交通运输部")):
        industries.append(SourceIndustry.GENERAL_TRANSPORT.value)
    content_domains: list[str] = []
    if any(marker in text for marker in ("安全生产", "安全规定", "事故调查")):
        content_domains.append(SourceContentDomain.SAFETY_REGULATION.value)
    if any(marker in text for marker in ("数字化转型", "数字交通")):
        content_domains.append(SourceContentDomain.DIGITAL_TRANSFORMATION_CASE.value)

    languages = ["zh-CN"] if _contains_cjk(text) else []
    countries = ["CN"] if is_china else []
    roles = [SourceDeclaredRole.OFFICIAL_PRIMARY.value] if is_government else []
    authority = AuthorityLevel.A0.value if is_government else AuthorityLevel.UNKNOWN.value
    independence = (
        SourceIndependenceLevel.NOT_INDEPENDENT.value
        if is_government
        else SourceIndependenceLevel.UNKNOWN.value
    )

    model_ids: dict[str, tuple[str, ...]] = {}
    if model_output is not None:
        industries = _merge_enum_candidates(
            industries,
            model_output.industry_candidates,
            {item.value for item in SourceIndustry},
            model_ids,
            "industries",
        )
        content_domains = _merge_enum_candidates(
            content_domains,
            model_output.content_domain_candidates,
            {item.value for item in SourceContentDomain},
            model_ids,
            "content_domains",
        )
        languages = _merge_pattern_candidates(
            languages, model_output.language_candidates, model_ids, "language_tags"
        )
        countries = _merge_pattern_candidates(
            countries, model_output.country_candidates, model_ids, "country_codes"
        )
        roles = _merge_enum_candidates(
            roles,
            model_output.declared_role_candidates,
            {item.value for item in SourceDeclaredRole},
            model_ids,
            "declared_roles",
        )

    values: dict[str, tuple[str, ...] | str] = {
        "industries": tuple(industries) or (SourceIndustry.UNKNOWN.value,),
        "content_domains": tuple(content_domains) or (SourceContentDomain.UNKNOWN.value,),
        "language_tags": tuple(languages),
        "country_codes": tuple(countries),
        "region_codes": (),
        "declared_roles": tuple(roles) or (SourceDeclaredRole.UNKNOWN.value,),
        "authority_level": authority,
        "independence_level": independence,
    }
    explanations: dict[str, FieldExplanation] = {}
    for field, value in values.items():
        known = (
            bool(value)
            and value
            not in {
                AuthorityLevel.UNKNOWN.value,
                SourceIndependenceLevel.UNKNOWN.value,
            }
            and value
            not in {
                (SourceIndustry.UNKNOWN.value,),
                (SourceContentDomain.UNKNOWN.value,),
                (SourceDeclaredRole.UNKNOWN.value,),
            }
        )
        if field in model_ids and known:
            confidence = 70 if _has_local_value(field, text, is_china, is_government) else 50
            reason = ("MODEL_AND_LOCAL_CORROBORATED",) if confidence == 70 else ("MODEL_CANDIDATE",)
            refs = model_ids[field]
        elif known:
            confidence = (
                95
                if field
                in {
                    "country_codes",
                    "language_tags",
                    "authority_level",
                    "independence_level",
                    "declared_roles",
                }
                else 85
            )
            reason = ("DETERMINISTIC_SOURCE_EVIDENCE",)
            refs = evidence_ids
        else:
            confidence = 0
            reason = ("INSUFFICIENT_EVIDENCE",)
            refs = ()
        explanations[field] = FieldExplanation(confidence, reason, refs)

    complete = model_output is not None and all(
        explanations[field].confidence > 0 for field in explanations
    )
    reasons = tuple(
        dict.fromkeys(
            ([partial_reason] if partial_reason else [])
            + ([] if complete else ["PROFILE_EVIDENCE_PARTIAL"])
        )
    )
    facts = tuple(TechnicalFact(code) for code in sorted(set(source.stream_types)))
    return BuiltSourceProfile(
        status="COMPLETE" if complete else "PARTIAL",
        industries=tuple(values["industries"]),
        content_domains=tuple(values["content_domains"]),
        language_tags=tuple(values["language_tags"]),
        country_codes=tuple(values["country_codes"]),
        region_codes=tuple(values["region_codes"]),
        declared_roles=tuple(values["declared_roles"]),
        authority_level=str(values["authority_level"]),
        independence_level=str(values["independence_level"]),
        authority_basis="AUTO_INFERRED",
        independence_basis="AUTO_INFERRED",
        overall_confidence=min(item.confidence for item in explanations.values()),
        field_explanations=explanations,
        technical_facts=facts,
        reason_codes=reasons,
    )


def _contains_cjk(value: str) -> bool:
    return any("\u4e00" <= character <= "\u9fff" for character in value)


def _merge_enum_candidates(
    existing: list[str],
    candidates: Sequence[SourceProfileCandidate],
    allowed: set[str],
    refs: dict[str, tuple[str, ...]],
    field: str,
) -> list[str]:
    values = list(existing)
    evidence: list[str] = []
    for raw in candidates:
        candidate = raw
        value = candidate.value
        if value in allowed and value != "UNKNOWN" and candidate.confidence >= 50:
            if value not in values:
                values.append(value)
            evidence.extend(candidate.evidence_ids)
    if evidence:
        refs[field] = tuple(dict.fromkeys(evidence))
    return values


def _merge_pattern_candidates(
    existing: list[str],
    candidates: Sequence[SourceProfileCandidate],
    refs: dict[str, tuple[str, ...]],
    field: str,
) -> list[str]:
    values = list(existing)
    evidence: list[str] = []
    for raw in candidates:
        value = str(raw.value)
        if raw.confidence >= 50 and 2 <= len(value) <= 35 and value not in values:
            values.append(value)
            evidence.extend(raw.evidence_ids)
    if evidence:
        refs[field] = tuple(dict.fromkeys(evidence))
    return values


def _has_local_value(field: str, text: str, is_china: bool, is_government: bool) -> bool:
    if field == "country_codes":
        return is_china
    if field == "declared_roles":
        return is_government
    if field == "language_tags":
        return _contains_cjk(text)
    return bool(text)
