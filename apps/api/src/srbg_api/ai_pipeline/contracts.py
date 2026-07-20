"""Strict, non-authoritative contracts for every model pipeline step."""

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from srbg_contracts import SourceProfileModelOutput

from srbg_api.ai_pipeline.ai_judgments import SummarizeOutput, VerificationOutput

# Public compatibility name used by the existing pipeline contract exports.
SummaryOutput = SummarizeOutput


class StrictModel(BaseModel):
    """Reject model additions instead of silently accepting authority-shaped fields."""

    model_config = ConfigDict(extra="forbid")


class AiStep(StrEnum):
    CLASSIFY = "CLASSIFY"
    EXTRACT = "EXTRACT"
    SUMMARIZE = "SUMMARIZE"
    VERIFY = "VERIFY"
    SOURCE_PROFILE = "SOURCE_PROFILE"


class CandidateSecurity(StrictModel):
    prompt_injection_detected: bool
    prompt_injection_status: Literal["NONE", "UNRESOLVED"]
    suspicious_patterns: list[str]

    @model_validator(mode="after")
    def status_matches_detection(self) -> "CandidateSecurity":
        expected = "UNRESOLVED" if self.prompt_injection_detected else "NONE"
        if self.prompt_injection_status != expected:
            raise ValueError("prompt injection status does not match detection")
        return self


class ClassificationOutput(StrictModel):
    direct_relevance: Literal["RELEVANT", "IRRELEVANT", "LOW_CONFIDENCE", "FAILED"]
    core_new_fact: str | None = Field(default=None, max_length=500)
    primary_type: Literal[
        "DIGITAL_TRANSFORMATION", "SAFETY_INTELLIGENCE", "INDUSTRY_UPDATE"
    ] | None
    engineering_objects: list[
        Literal[
            "HIGHWAY", "RAILWAY", "BRIDGE", "TUNNEL", "BUILDING", "MINING",
            "MUNICIPAL", "WATER_CONSERVANCY", "PORT_WATERWAY", "AIRPORT", "ENERGY",
        ]
    ]
    specialty_facets: list[Literal["TUNNEL_GAS_MONITORING"]]
    equipment_domains: list[Literal["CONSTRUCTION_MACHINERY"]]
    content_form: Literal[
        "AUTHORITY_NOTICE", "PROJECT_RECORD", "RESEARCH", "PRODUCT",
        "ACCIDENT_UPDATE", "STANDARD_GUIDANCE", "OPERATION_UPDATE", "OTHER",
    ]
    evidence_locators: list[str]
    confidence: float = Field(ge=0, le=1)
    needs_human_review: bool
    review_reasons: list[str]
    security: CandidateSecurity

    @model_validator(mode="after")
    def enforce_relevance_boundary(self) -> "ClassificationOutput":
        list_fields = (
            "engineering_objects",
            "specialty_facets",
            "equipment_domains",
            "evidence_locators",
            "review_reasons",
        )
        for field_name in list_fields:
            values = getattr(self, field_name)
            if len(values) != len(set(values)):
                raise ValueError(f"{field_name} must not contain duplicates")
        if self.direct_relevance == "RELEVANT":
            if not self.core_new_fact or self.primary_type is None:
                raise ValueError("relevant content requires a core fact and one primary type")
            if not self.engineering_objects and not self.equipment_domains:
                raise ValueError("relevant content requires an in-scope engineering object")
            if not self.evidence_locators:
                raise ValueError("relevant content requires evidence location")
        elif self.primary_type is not None:
            raise ValueError("unqualified content cannot receive a primary type")
        objects = set(self.engineering_objects)
        if self.specialty_facets:
            valid_transport_tunnel = (
                "TUNNEL" in objects
                and bool({"HIGHWAY", "RAILWAY"}.intersection(objects))
                and "MINING" not in objects
            )
            if not valid_transport_tunnel:
                raise ValueError(
                    "TUNNEL_GAS_MONITORING requires TUNNEL with HIGHWAY or RAILWAY, not MINING"
                )
        return self


ClaimField = Literal[
    "title",
    "publisher",
    "published_at",
    "document_no",
    "effective_at",
    "regulation_status",
    "occurred_at",
    "death_count",
    "injury_count",
    "direct_loss",
    "incident_cause",
    "responsibility",
    "corrective_action",
    "product_name",
    "model_no",
    "capability",
    "deployment_scope",
    "claimed_outcome",
    "verified_outcome",
    "doi",
    "journal",
    "issn",
    "volume",
    "issue",
    "publication_year",
    "abstract",
    "keyword",
    "paper_type",
    "author",
    "institution",
    "research_object",
    "research_method",
    "research_condition",
    "research_conclusion",
    "research_limitation",
    "research_maturity_evidence",
]


class CandidateClaim(StrictModel):
    claim_id: str = Field(min_length=1)
    field: ClaimField
    value: Any
    normalized_value: Any | None = None
    unit: str | None = None
    claim_status: Literal["VERIFIED_CANDIDATE", "REPORTED_CLAIM", "UNVERIFIED", "CONFLICTING"]
    confidence: float = Field(ge=0, le=1)
    evidence_ids: list[str] = Field(min_length=1)


class EvidenceLocator(StrictModel):
    type: Literal["HTML_PARAGRAPH", "PDF_PAGE", "OCR_BOX", "TABLE_CELL", "TEXT_RANGE"]
    value: str


class CandidateEvidence(StrictModel):
    evidence_id: str = Field(min_length=1)
    document_block_id: str = Field(min_length=1)
    locator: EvidenceLocator
    excerpt: str = Field(min_length=1, max_length=500)
    supports: list[str] = Field(min_length=1)


class ExtractionOutput(StrictModel):
    claims: list[CandidateClaim] = Field(min_length=1)
    evidence: list[CandidateEvidence] = Field(min_length=1)
    security: CandidateSecurity


class EvidenceAnchor(StrictModel):
    evidence_id: str
    document_block_id: str
    normalized_text: str
    page_number: int | None = Field(default=None, ge=1, le=10000)
    locator_value: str | None = Field(default=None, max_length=200)


class ModelRequest(StrictModel):
    step: AiStep
    prompt_version: str
    schema_version: str
    model_profile: str
    system_prompt: str
    user_prompt: str
    input_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    response_schema: dict[str, Any]
    parameters: dict[str, Any]
    data_classification: Literal["PUBLIC_SOURCE"]
    input_price_microusd_per_million: int = Field(ge=0)
    cache_hit_input_price_microusd_per_million: int | None = Field(default=None, ge=0)
    output_price_microusd_per_million: int = Field(ge=0)
    evidence_anchors: dict[str, EvidenceAnchor] = Field(default_factory=dict)

    @model_validator(mode="after")
    def forbid_transport_and_tool_parameters(self) -> "ModelRequest":
        forbidden = {"tools", "tool_choice", "stream", "url", "base_url", "request_path"}
        if forbidden.intersection(self.parameters):
            raise ValueError("model parameters contain a forbidden transport capability")
        return self


class ModelUsage(StrictModel):
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    cache_hit_tokens: int = Field(default=0, ge=0)
    cache_miss_tokens: int = Field(default=0, ge=0)


class ModelResponse(StrictModel):
    raw_output: str
    output: dict[str, Any]
    usage: ModelUsage
    cost_microusd: int = Field(ge=0)
    latency_ms: int = Field(ge=0)
    provider_request_id: str | None = None
    finish_reason: str | None = None


STEP_OUTPUT_MODELS: dict[AiStep, type[BaseModel]] = {
    AiStep.CLASSIFY: ClassificationOutput,
    AiStep.EXTRACT: ExtractionOutput,
    AiStep.SUMMARIZE: SummarizeOutput,
    AiStep.VERIFY: VerificationOutput,
    AiStep.SOURCE_PROFILE: SourceProfileModelOutput,
}
