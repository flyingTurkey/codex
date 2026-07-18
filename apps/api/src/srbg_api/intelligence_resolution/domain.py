"""Pure, versioned rules for Round 08 intelligence resolution."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from difflib import SequenceMatcher
from typing import Literal
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

SCORING_RULE_VERSION = "scoring-v1.0.0"
DEDUP_RULE_VERSION = "dedup-v1.0.0"

_TRACKING_QUERY_KEYS = {
    "from",
    "spm",
    "utm_campaign",
    "utm_content",
    "utm_medium",
    "utm_source",
    "utm_term",
}
_RELATION_HINTS = {
    "REVISION",
    "CLARIFICATION",
    "WITHDRAWAL",
    "CORRECTION",
    "FOLLOW_UP",
}
_HARD_FIELDS = {
    "project": "PROJECT",
    "contract_section": "CONTRACT_SECTION",
    "model_no": "MODEL_NO",
    "document_number": "DOCUMENT_NUMBER",
    "accident_stage": "ACCIDENT_STAGE",
}


@dataclass(frozen=True, slots=True)
class DeduplicationDocument:
    canonical_url: str | None = None
    source_id: str | None = None
    external_id: str | None = None
    doi: str | None = None
    issuer: str | None = None
    document_number: str | None = None
    content_sha256: str | None = None
    title: str = ""
    body: str = ""
    entities: tuple[str, ...] = ()
    occurred_at: datetime | None = None
    region: str | None = None
    project: str | None = None
    contract_section: str | None = None
    model_no: str | None = None
    accident_stage: str | None = None
    relation_hint: str | None = None


@dataclass(frozen=True, slots=True)
class CandidateAssessment:
    similarity_bps: int
    features: tuple[tuple[str, int], ...]
    hard_conflicts: tuple[str, ...]
    blocked: bool
    recommendation: Literal[
        "POSSIBLE_DUPLICATE", "KEEP_DISTINCT", "LINK_RELATION", "EXACT_DUPLICATE"
    ]
    relation_type: str | None = None
    rule_version: str = DEDUP_RULE_VERSION
    requires_human_review: bool = True


@dataclass(frozen=True, slots=True)
class SourceLineage:
    source_id: str
    organization_key: str
    lineage_root: str
    role: Literal[
        "ORIGINAL",
        "REPRINT",
        "MIRROR",
        "INDEPENDENT_REPORT",
        "VENDOR_STATEMENT",
        "MEDIA_REPORT",
        "INDEPENDENT_VERIFICATION",
    ]


@dataclass(frozen=True, slots=True)
class ScoreValue:
    score: int
    features: tuple[tuple[str, int, str], ...]
    rule_version: str = SCORING_RULE_VERSION


def _text(value: str | None) -> str:
    return re.sub(r"[\W_]+", "", (value or "").casefold())


def _canonical_url(value: str | None) -> str | None:
    if not value:
        return None
    parsed = urlsplit(value.strip())
    host = (parsed.hostname or "").casefold()
    if parsed.port and parsed.port not in {80, 443}:
        host = f"{host}:{parsed.port}"
    query = urlencode(
        sorted(
            (key, item)
            for key, item in parse_qsl(parsed.query, keep_blank_values=True)
            if key.casefold() not in _TRACKING_QUERY_KEYS
        )
    )
    path = parsed.path.rstrip("/") or "/"
    return urlunsplit((parsed.scheme.casefold(), host, path, query, ""))


def _doi(value: str | None) -> str | None:
    if not value:
        return None
    normalized = value.strip().casefold()
    for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
        if normalized.startswith(prefix):
            normalized = normalized.removeprefix(prefix)
    return normalized


def _hard_conflicts(left: DeduplicationDocument, right: DeduplicationDocument) -> tuple[str, ...]:
    conflicts: list[str] = []
    for field, code in _HARD_FIELDS.items():
        left_value = _text(getattr(left, field))
        right_value = _text(getattr(right, field))
        if left_value and right_value and left_value != right_value:
            conflicts.append(code)
    return tuple(conflicts)


def exact_identity_matches(left: DeduplicationDocument, right: DeduplicationDocument) -> set[str]:
    matches: set[str] = set()
    if _canonical_url(left.canonical_url) and _canonical_url(left.canonical_url) == _canonical_url(
        right.canonical_url
    ):
        matches.add("CANONICAL_URL")
    if (
        left.source_id
        and left.source_id == right.source_id
        and left.external_id
        and _text(left.external_id) == _text(right.external_id)
    ):
        matches.add("EXTERNAL_ID")
    if _doi(left.doi) and _doi(left.doi) == _doi(right.doi):
        matches.add("DOI")
    if (
        _text(left.issuer)
        and _text(left.issuer) == _text(right.issuer)
        and _text(left.document_number)
        and _text(left.document_number) == _text(right.document_number)
    ):
        matches.add("DOCUMENT_NUMBER")
    if (
        left.content_sha256
        and re.fullmatch(r"[0-9a-f]{64}", left.content_sha256)
        and left.content_sha256 == right.content_sha256
        and not _hard_conflicts(left, right)
    ):
        matches.add("CONTENT_SHA256")
    return matches


def _ratio(left: str, right: str) -> int:
    if not left or not right:
        return 0
    return round(SequenceMatcher(None, _text(left), _text(right)).ratio() * 10_000)


def _token_similarity(left: str, right: str) -> int:
    left_tokens = set(re.findall(r"[\w\u4e00-\u9fff]{2,}", left.casefold()))
    right_tokens = set(re.findall(r"[\w\u4e00-\u9fff]{2,}", right.casefold()))
    if not left_tokens or not right_tokens:
        return 0
    return len(left_tokens & right_tokens) * 10_000 // len(left_tokens | right_tokens)


def assess_duplicate(
    left: DeduplicationDocument,
    right: DeduplicationDocument,
    *,
    vector_similarity_bps: int | None = None,
) -> CandidateAssessment:
    conflicts = _hard_conflicts(left, right)
    if conflicts:
        return CandidateAssessment(
            similarity_bps=0,
            features=tuple((code, 0) for code in conflicts),
            hard_conflicts=conflicts,
            blocked=True,
            recommendation="KEEP_DISTINCT",
        )

    relation = right.relation_hint or left.relation_hint
    if relation in _RELATION_HINTS:
        return CandidateAssessment(
            similarity_bps=10_000,
            features=(("RELATION_HINT", 10_000),),
            hard_conflicts=(),
            blocked=False,
            recommendation="LINK_RELATION",
            relation_type=relation,
        )

    exact = exact_identity_matches(left, right)
    if exact:
        if (
            exact == {"CANONICAL_URL"}
            and left.content_sha256
            and right.content_sha256
            and left.content_sha256 != right.content_sha256
        ):
            return CandidateAssessment(
                similarity_bps=10_000,
                features=(("CANONICAL_URL_VERSION", 10_000),),
                hard_conflicts=(),
                blocked=False,
                recommendation="LINK_RELATION",
                relation_type="CONTENT_UPDATE",
            )
        return CandidateAssessment(
            similarity_bps=10_000,
            features=tuple((value, 10_000) for value in sorted(exact)),
            hard_conflicts=(),
            blocked=False,
            recommendation="EXACT_DUPLICATE",
        )

    title = _ratio(left.title, right.title)
    body = _token_similarity(left.body, right.body)
    left_entities = {_text(value) for value in left.entities if _text(value)}
    right_entities = {_text(value) for value in right.entities if _text(value)}
    entity = (
        len(left_entities & right_entities) * 10_000 // len(left_entities | right_entities)
        if left_entities and right_entities
        else 0
    )
    time = 0
    if left.occurred_at and right.occurred_at:
        seconds = abs((left.occurred_at - right.occurred_at).total_seconds())
        time = 10_000 if seconds <= 86_400 else 5_000 if seconds <= 604_800 else 0
    region = 10_000 if _text(left.region) and _text(left.region) == _text(right.region) else 0
    rule_score = title * 30 // 100 + body * 25 // 100 + entity * 20 // 100
    rule_score += time * 15 // 100 + region * 10 // 100
    combined = max(rule_score, vector_similarity_bps or 0)
    return CandidateAssessment(
        similarity_bps=min(10_000, combined),
        features=(
            ("TITLE", title),
            ("BODY_FINGERPRINT", body),
            ("ENTITY", entity),
            ("TIME", time),
            ("REGION", region),
            ("VECTOR", vector_similarity_bps or 0),
        ),
        hard_conflicts=(),
        blocked=False,
        recommendation="POSSIBLE_DUPLICATE" if combined >= 7_000 else "KEEP_DISTINCT",
    )


def count_independent_sources(lineages: list[SourceLineage]) -> int:
    roots: set[tuple[str, str]] = set()
    for lineage in lineages:
        if lineage.role in {"ORIGINAL", "INDEPENDENT_REPORT", "INDEPENDENT_VERIFICATION"}:
            roots.add((lineage.lineage_root, lineage.organization_key))
    return len(roots)


def _score(value: int, *features: tuple[str, int, str]) -> ScoreValue:
    return ScoreValue(score=max(0, min(100, value)), features=features)


def calculate_scores(
    *,
    relevance_features: tuple[int, ...] | None,
    authority_level: str | None,
    impact_features: tuple[int, ...] | None,
    novelty_similarity_bps: int | None,
    published_at: datetime | None,
    content_type: str,
    accepted_claim_coverage_bps: int | None,
    locator_integrity: bool | None,
    primary_evidence: bool | None,
    extraction_confidence_bps: int | None,
    cross_source_agreement_bps: int | None,
    human_reviewed: bool | None,
    unresolved_conflicts: int,
    independent_source_count: int,
    event_activity_count: int,
    now: datetime | None = None,
) -> dict[str, ScoreValue]:
    calculated: dict[str, ScoreValue] = {}
    current = (now or datetime.now(UTC)).astimezone(UTC)
    if relevance_features is not None:
        relevance = min(100, sum(relevance_features))
        calculated["RELEVANCE"] = _score(
            relevance,
            ("RELEVANCE_FACTORS", relevance, "工程专业、四川及四川路桥关系的已接受事实"),
        )
    if authority_level is not None:
        authority = {"A0": 100, "A1": 95, "A2": 85, "B1": 80, "B2": 60, "C1": 40, "C2": 20}.get(
            authority_level, 0
        )
        calculated["AUTHORITY"] = _score(
            authority, ("SOURCE_AUTHORITY", authority, f"来源等级 {authority_level}")
        )
    if impact_features is not None:
        impact = min(100, sum(impact_features))
        calculated["IMPACT"] = _score(
            impact, ("TYPE_SPECIFIC_IMPACT", impact, "按内容类型映射的效力、范围、成熟度与适用性")
        )
    if novelty_similarity_bps is not None:
        novelty = 100 - max(0, min(10_000, novelty_similarity_bps)) // 100
        calculated["NOVELTY"] = _score(
            novelty, ("PRIOR_SIMILARITY", novelty, "与通过硬约束的既有内容比较")
        )

    timeliness: int | None = None
    if published_at is not None:
        half_life = {
            "SAFETY_CASE": 7,
            "SAFETY_REGULATION": 30,
            "DIGITAL_CASE": 90,
            "SOFTWARE_PRODUCT": 90,
            "IOT_PRODUCT": 90,
            "LOW_ALTITUDE_EQUIPMENT": 90,
            "AI_EQUIPMENT": 90,
            "JOURNAL_PAPER": 180,
        }.get(content_type, 90)
        age_days = max(0, (current - published_at.astimezone(UTC)).days)
        timeliness = max(0, 100 - age_days * 50 // half_life)
        calculated["TIMELINESS"] = _score(
            timeliness,
            ("AGE_DECAY", timeliness, f"{half_life} 天半衰期的确定性整数衰减"),
        )
    if accepted_claim_coverage_bps is not None and locator_integrity is not None:
        evidence = accepted_claim_coverage_bps * 70 // 10_000
        evidence += 20 if locator_integrity else 0
        evidence += 10 if primary_evidence else 0
        calculated["EVIDENCE"] = _score(
            evidence,
            (
                "ACCEPTED_CLAIM_COVERAGE",
                accepted_claim_coverage_bps * 70 // 10_000,
                "关键事实证据覆盖",
            ),
            ("LOCATOR_INTEGRITY", 20 if locator_integrity else 0, "证据定位与哈希完整性"),
            ("PRIMARY_EVIDENCE", 10 if primary_evidence else 0, "一手或独立证据"),
        )
    if extraction_confidence_bps is not None and cross_source_agreement_bps is not None:
        confidence = extraction_confidence_bps * 60 // 10_000
        confidence += cross_source_agreement_bps * 20 // 10_000
        confidence += 20 if human_reviewed else 0
        if unresolved_conflicts:
            confidence = min(confidence, 49)
        calculated["CONFIDENCE"] = _score(
            confidence,
            (
                "EXTRACTION_CONFIDENCE",
                extraction_confidence_bps * 60 // 10_000,
                "已接受字段抽取置信",
            ),
            ("CROSS_SOURCE_AGREEMENT", cross_source_agreement_bps * 20 // 10_000, "独立来源一致性"),
            ("HUMAN_REVIEW", 20 if human_reviewed else 0, "人工复核状态"),
        )
    if timeliness is not None:
        source_points = min(
            60, independent_source_count * 10 + (10 if independent_source_count else 0)
        )
        activity_points = min(30, event_activity_count * 3)
        decay_points = timeliness * 10 // 100
        calculated["HEAT"] = _score(
            source_points + activity_points + decay_points,
            ("INDEPENDENT_SOURCES", source_points, "去除转载后的独立信源"),
            ("EVENT_ACTIVITY", activity_points, "事件活动数量"),
            ("TIME_DECAY", decay_points, "时间衰减; 不进入置信分"),
        )
    return calculated
