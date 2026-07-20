"""Qualification decisions that prevent extraction and publication side effects."""

from enum import StrEnum

from srbg_api.ai_pipeline.contracts import ClassificationOutput
from srbg_api.intelligence_v2.gold_calibration import AutoPassCalibrationGrant


class QualificationReason(StrEnum):
    IRRELEVANT = "IRRELEVANT"
    LOW_CONFIDENCE = "LOW_CONFIDENCE"
    CLASSIFICATION_FAILED = "CLASSIFICATION_FAILED"
    PRIMARY_TYPE_TIE = "PRIMARY_TYPE_TIE"
    HUMAN_REVIEW_REQUIRED = "HUMAN_REVIEW_REQUIRED"
    LOCKED_NEGATIVE = "LOCKED_NEGATIVE"
    PROMPT_INJECTION_UNRESOLVED = "PROMPT_INJECTION_UNRESOLVED"
    EVIDENCE_LOCATOR_MISMATCH = "EVIDENCE_LOCATOR_MISMATCH"
    NO_SUBSTANTIVE_ENGINEERING_ACTIVITY = "NO_SUBSTANTIVE_ENGINEERING_ACTIVITY"
    CALIBRATION_UNAVAILABLE = "CALIBRATION_UNAVAILABLE"


_LOCKED_NEGATIVE_PHRASES = (
    "中医药",
    "中药",
    "医疗健康",
    "健康消费",
    "旅游消费",
    "文旅促销",
    "景区营销",
    "股票市场",
    "金融行情",
    "股价",
    "证券行情",
    "通用人工智能",
    "通用大模型",
)
_GENERAL_MANUFACTURING_PHRASES = ("erp", "生产线改造", "工业互联网改造")
_ENGINEERING_ACTIVITY_PHRASES = (
    "规划",
    "设计",
    "施工",
    "建设",
    "运营",
    "运维",
    "养护",
    "安全",
    "监测",
    "数字化",
    "planning",
    "design",
    "construction",
    "operation",
    "maintenance",
    "safety",
    "monitoring",
    "digitalization",
)


def _is_locked_negative(output: ClassificationOutput, document_text: str) -> bool:
    normalized = document_text.casefold()
    if any(phrase in normalized for phrase in _LOCKED_NEGATIVE_PHRASES):
        return True
    if "港口企业" in normalized and any(
        phrase in normalized for phrase in ("营收", "利润", "经营业绩")
    ):
        return True
    return bool(output.equipment_domains) and any(
        phrase in normalized for phrase in _GENERAL_MANUFACTURING_PHRASES
    )


def qualification_reason(
    output: ClassificationOutput,
    *,
    document_text: str,
    allowed_evidence_locators: frozenset[str] | None = None,
    calibration: AutoPassCalibrationGrant | None = None,
) -> QualificationReason | None:
    """Return the fail-closed review reason, or ``None`` for an extraction candidate."""

    if output.security.prompt_injection_status == "UNRESOLVED":
        return QualificationReason.PROMPT_INJECTION_UNRESOLVED
    if allowed_evidence_locators is not None and not set(output.evidence_locators) <= set(
        allowed_evidence_locators
    ):
        return QualificationReason.EVIDENCE_LOCATOR_MISMATCH
    if _is_locked_negative(output, document_text):
        return QualificationReason.LOCKED_NEGATIVE
    normalized = document_text.casefold()
    if output.direct_relevance == "RELEVANT" and not any(
        phrase in normalized for phrase in _ENGINEERING_ACTIVITY_PHRASES
    ):
        return QualificationReason.NO_SUBSTANTIVE_ENGINEERING_ACTIVITY
    if "PRIMARY_TYPE_TIE" in output.review_reasons:
        return QualificationReason.PRIMARY_TYPE_TIE
    if output.direct_relevance == "FAILED":
        return QualificationReason.CLASSIFICATION_FAILED
    if output.direct_relevance == "IRRELEVANT":
        return QualificationReason.IRRELEVANT
    if output.direct_relevance == "LOW_CONFIDENCE":
        return QualificationReason.LOW_CONFIDENCE
    if output.needs_human_review:
        return QualificationReason.HUMAN_REVIEW_REQUIRED
    if output.primary_type is None:
        return QualificationReason.CLASSIFICATION_FAILED
    if calibration is None:
        return QualificationReason.CALIBRATION_UNAVAILABLE
    if round(output.confidence * 10_000) < calibration.threshold_bps:
        return QualificationReason.LOW_CONFIDENCE
    return None


def classification_allows_extraction(
    output: ClassificationOutput,
    *,
    document_text: str,
    allowed_evidence_locators: frozenset[str] | None = None,
    calibration: AutoPassCalibrationGrant | None = None,
) -> bool:
    return (
        qualification_reason(
            output,
            document_text=document_text,
            allowed_evidence_locators=allowed_evidence_locators,
            calibration=calibration,
        )
        is None
    )
