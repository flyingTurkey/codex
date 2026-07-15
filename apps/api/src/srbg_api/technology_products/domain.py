"""Deterministic identity and evidence rules for technology products."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Literal
from uuid import UUID

ProductItemType = Literal[
    "SOFTWARE_PRODUCT", "IOT_PRODUCT", "LOW_ALTITUDE_EQUIPMENT", "AI_EQUIPMENT"
]


@dataclass(frozen=True, slots=True)
class CapabilityEvidence:
    attributed_vendor_id: UUID
    source_vendor_ids: tuple[UUID, ...]
    evidence_roles: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ProductIdentity:
    vendor_name: str
    product_name: str
    model_no: str | None
    version: str | None


@dataclass(frozen=True, slots=True)
class IdentityResolution:
    action: Literal["REUSE", "KEEP_DISTINCT", "LINK_AS_NEW_VERSION", "REVIEW"]
    candidate_type: Literal["MODEL_ALIAS", "VERSION_SUCCESSOR", "POSSIBLE_DUPLICATE"] | None


def normalize_product_identifier(value: str | None) -> str | None:
    if value is None or not value.strip():
        return None
    normalized = unicodedata.normalize("NFKC", value).casefold().strip()
    return re.sub(r"\s+", " ", normalized)


def resolve_identity(existing: ProductIdentity, incoming: ProductIdentity) -> IdentityResolution:
    existing_values = tuple(
        normalize_product_identifier(value)
        for value in (
            existing.vendor_name,
            existing.product_name,
            existing.model_no,
            existing.version,
        )
    )
    incoming_values = tuple(
        normalize_product_identifier(value)
        for value in (
            incoming.vendor_name,
            incoming.product_name,
            incoming.model_no,
            incoming.version,
        )
    )
    if existing_values == incoming_values:
        return IdentityResolution("REUSE", None)
    same_product = existing_values[:2] == incoming_values[:2]
    if same_product and existing_values[2] and incoming_values[2]:
        if existing_values[2] != incoming_values[2]:
            return IdentityResolution("KEEP_DISTINCT", "POSSIBLE_DUPLICATE")
        if existing_values[3] != incoming_values[3]:
            return IdentityResolution("LINK_AS_NEW_VERSION", "VERSION_SUCCESSOR")
    return IdentityResolution("REVIEW", "POSSIBLE_DUPLICATE")


def validate_capability(kind: str, evidence: CapabilityEvidence) -> tuple[str, ...]:
    if kind == "PROMOTIONAL_CLAIM":
        return ()
    if kind != "VERIFIED_CAPABILITY":
        raise ValueError(f"unsupported product capability kind: {kind}")
    has_independent_role = "INDEPENDENT_CONFIRMATION" in evidence.evidence_roles
    has_independent_source = any(
        source_id != evidence.attributed_vendor_id for source_id in evidence.source_vendor_ids
    )
    if not has_independent_role or not has_independent_source:
        return ("PRODUCT_VERIFIED_CAPABILITY_INDEPENDENT_EVIDENCE_REQUIRED",)
    return ()


def determine_permit_status(item_type: ProductItemType, evidence_roles: tuple[str, ...]) -> str:
    if item_type != "LOW_ALTITUDE_EQUIPMENT":
        return "NOT_REQUIRED"
    return "VERIFIED" if "PRIMARY_OFFICIAL" in evidence_roles else "UNKNOWN"


_PROCUREMENT_CONCLUSION_PATTERNS = (
    re.compile(r"适用于四川路桥采购"),
    re.compile(r"纳入采购(?:短名单|清单)"),
    re.compile(r"满足四川路桥采购要求"),
)


def contains_procurement_conclusion(value: str) -> bool:
    return any(pattern.search(value) is not None for pattern in _PROCUREMENT_CONCLUSION_PATTERNS)

