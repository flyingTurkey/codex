"""Canonical public contracts shared by API and Worker processes."""

from datetime import datetime
from enum import StrEnum
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, Field

API_VERSION: Final[Literal["v1"]] = "v1"
CONTENT_SCHEMA_VERSION: Final[Literal["1.0.0"]] = "1.0.0"


class ContractModel(BaseModel):
    """Base class that rejects fields not declared by the public contract."""

    model_config = ConfigDict(extra="forbid")


class UserRole(StrEnum):
    VIEWER = "viewer"
    EDITOR = "editor"
    REVIEWER = "reviewer"
    SOURCE_ADMIN = "source_admin"
    PLATFORM_ADMIN = "platform_admin"
    AUDITOR = "auditor"


class Channel(StrEnum):
    DIGITAL = "DIGITAL"
    SAFETY = "SAFETY"


class ItemType(StrEnum):
    DIGITAL_CASE = "DIGITAL_CASE"
    JOURNAL_PAPER = "JOURNAL_PAPER"
    SOFTWARE_PRODUCT = "SOFTWARE_PRODUCT"
    IOT_PRODUCT = "IOT_PRODUCT"
    LOW_ALTITUDE_EQUIPMENT = "LOW_ALTITUDE_EQUIPMENT"
    AI_EQUIPMENT = "AI_EQUIPMENT"
    SAFETY_REGULATION = "SAFETY_REGULATION"
    SAFETY_CASE = "SAFETY_CASE"


class RiskLevel(StrEnum):
    R1 = "R1"
    R2 = "R2"
    R3 = "R3"
    R4 = "R4"


class DependencyName(StrEnum):
    POSTGRESQL = "postgresql"
    REDIS = "redis"
    OBJECT_STORAGE = "object_storage"


class DependencyCheck(ContractModel):
    status: Literal["up", "down"]
    latency_ms: int = Field(ge=0)
    error_code: Literal["timeout", "unavailable", "misconfigured"] | None = None


class LivenessResponse(ContractModel):
    status: Literal["ok"] = "ok"
    service: Literal["api"] = "api"
    timestamp: datetime


class ReadinessResponse(ContractModel):
    status: Literal["ready", "not_ready"]
    service: Literal["api"] = "api"
    timestamp: datetime
    checks: dict[DependencyName, DependencyCheck]


class VersionResponse(ContractModel):
    api_version: Literal["v1"] = API_VERSION
    content_schema_version: Literal["1.0.0"] = CONTENT_SCHEMA_VERSION


class ProblemDetails(ContractModel):
    type: str = "about:blank"
    title: str
    status: int = Field(ge=400, le=599)
    detail: str | None = None
    instance: str | None = None
    request_id: str


class CursorPage[T](ContractModel):
    items: list[T]
    next_cursor: str | None = None
    has_more: bool
