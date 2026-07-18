"""Pure PERS-07 signal projection rules used only by PublicationService."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from typing import Any, Literal, cast
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

ResultType = Literal["EVIDENCE_FACT", "AI_JUDGMENT", "UNVERIFIED_AI", "AI_PROCESSING_FAILED"]
SearchSurface = Literal["PRIMARY", "UNVERIFIED"]
DailySection = Literal["EVIDENCE_FACTS", "UNVERIFIED_AI"]


class PersonalSignalInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: UUID
    item_id: UUID
    document_version_id: UUID
    title: str = Field(min_length=1, max_length=500)
    original_url: str = Field(pattern=r"^https?://[^\s]+$", max_length=2048)
    source_name: str = Field(min_length=1, max_length=200)
    domain: Literal["DIGITAL", "SAFETY"] = "DIGITAL"
    content_type: str = "DIGITAL_CASE"
    source_published_at: datetime | None = None
    first_discovered_at: datetime
    activity_at: datetime
    review_status: str = "PENDING"
    event_type: str = "DIGITAL_PROJECT"
    evidence_facts: list[dict[str, Any]]
    judgment_version_id: UUID | None = None
    judgment_status: str | None = None
    judgment_payload: dict[str, Any] | None = None
    failure_reason_codes: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class PersonalSignalProjection:
    signal_id: UUID
    result_type: ResultType
    event_id: UUID
    item_id: UUID
    document_version_id: UUID
    judgment_version_id: UUID | None
    payload: dict[str, Any]
    search_surface: SearchSurface | None
    daily_section: DailySection | None


def build_personal_signal_projections(
    value: PersonalSignalInput,
) -> list[PersonalSignalProjection]:
    common: dict[str, Any] = {
        "title": value.title,
        "original_url": value.original_url,
        "source_name": value.source_name,
        "domain": value.domain,
        "content_type": value.content_type,
        "source_published_at": (
            value.source_published_at.isoformat() if value.source_published_at else None
        ),
        "first_discovered_at": value.first_discovered_at.isoformat(),
        "activity_at": value.activity_at.isoformat(),
        "review_status": value.review_status,
        "event_type": value.event_type,
    }
    projections = [
        PersonalSignalProjection(
            signal_id=_derived_uuid(value.document_version_id, "EVIDENCE_FACT"),
            result_type="EVIDENCE_FACT",
            event_id=value.event_id,
            item_id=value.item_id,
            document_version_id=value.document_version_id,
            judgment_version_id=None,
            payload={**common, "evidence_facts": value.evidence_facts},
            search_surface="PRIMARY",
            daily_section="EVIDENCE_FACTS",
        )
    ]
    if value.judgment_status not in {
        "AI_JUDGMENT",
        "UNVERIFIED_AI",
        "AI_PROCESSING_FAILED",
    }:
        return projections
    result_type = value.judgment_status
    search_surface: SearchSurface | None
    daily_section: DailySection | None
    if result_type == "AI_PROCESSING_FAILED":
        payload = {
            **common,
            "failure_reason_codes": list(value.failure_reason_codes),
        }
        search_surface = None
        daily_section = None
    else:
        payload = {
            **common,
            "judgment": value.judgment_payload or {},
            "failure_reason_codes": list(value.failure_reason_codes),
        }
        search_surface = (
            "UNVERIFIED" if result_type == "UNVERIFIED_AI" else "PRIMARY"
        )
        daily_section = (
            "UNVERIFIED_AI" if result_type == "UNVERIFIED_AI" else None
        )
    projections.append(
        PersonalSignalProjection(
            signal_id=_derived_uuid(value.document_version_id, result_type),
            result_type=cast(ResultType, result_type),
            event_id=value.event_id,
            item_id=value.item_id,
            document_version_id=value.document_version_id,
            judgment_version_id=value.judgment_version_id,
            payload=payload,
            search_surface=search_surface,
            daily_section=daily_section,
        )
    )
    return projections


def _derived_uuid(seed: UUID, purpose: str) -> UUID:
    digest = bytearray(sha256(f"{seed}:{purpose}".encode()).digest()[:16])
    digest[6] = (digest[6] & 0x0F) | 0x70
    digest[8] = (digest[8] & 0x3F) | 0x80
    return UUID(bytes=bytes(digest))
