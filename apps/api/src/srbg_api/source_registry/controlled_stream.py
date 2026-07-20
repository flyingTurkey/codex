"""Fail-closed stream-level control facts for T07 shadow acquisition."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass, fields
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Literal
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from srbg_api.identifiers import uuid7
from srbg_api.observability import SOURCE_STREAM_CONTROL_DECISIONS


class SourceResearchDisposition(StrEnum):
    ADMISSION_READY = "ADMISSION_READY"
    BOUNDARY_DISCOVERY = "BOUNDARY_DISCOVERY"
    MANUAL_SHADOW = "MANUAL_SHADOW"


class StreamRuntimeState(StrEnum):
    PAUSED = "PAUSED"
    SHADOW_AUTHORIZED = "SHADOW_AUTHORIZED"
    SHADOW_RUNNING = "SHADOW_RUNNING"


@dataclass(frozen=True, slots=True)
class AdmissionGates:
    public_network_safe: bool | None
    robots_allowed: bool | None
    terms_allowed: bool | None
    copyright_allowed: bool | None
    access_boundary_allowed: bool | None
    rate_limit_configured: bool | None
    budget_available: bool | None
    quality_passed: bool | None
    circuit_closed: bool | None
    runtime_gate_open: bool | None

    @classmethod
    def unknown(cls) -> AdmissionGates:
        return cls(**{field.name: None for field in fields(cls)})

    def failure_reasons(self) -> tuple[str, ...]:
        reasons: list[str] = []
        for field in fields(self):
            value = getattr(self, field.name)
            if value is not True:
                suffix = "UNKNOWN" if value is None else "FAILED"
                reasons.append(f"{field.name.upper()}_{suffix}")
        return tuple(reasons)


@dataclass(frozen=True, slots=True)
class StreamControlFacts:
    source_id: UUID
    source_stream_id: UUID
    disposition: SourceResearchDisposition
    desired_enabled: bool
    admission_verdict: Literal["ADMIT", "OBSERVE", "PAUSE"] | None
    gates: AdmissionGates
    admission_decided_at: datetime | None
    admission_valid_until: datetime | None

    def __post_init__(self) -> None:
        for value in (self.admission_decided_at, self.admission_valid_until):
            if value is not None and value.tzinfo is None:
                raise ValueError("source admission time must include timezone")
        if (self.admission_decided_at is None) != (self.admission_valid_until is None):
            raise ValueError("source admission decision and expiry must be recorded together")
        if (
            self.admission_decided_at is not None
            and self.admission_valid_until is not None
            and self.admission_valid_until <= self.admission_decided_at
        ):
            raise ValueError("source admission expiry must follow its decision")


@dataclass(frozen=True, slots=True)
class StreamRuntimeDecision:
    source_id: UUID
    source_stream_id: UUID
    state: StreamRuntimeState
    actual_running: bool
    reason_codes: tuple[str, ...]
    run_id: UUID | None = None

    def start(self, *, run_id: UUID) -> StreamRuntimeDecision:
        if self.state is not StreamRuntimeState.SHADOW_AUTHORIZED or self.reason_codes:
            raise PermissionError("shadow stream is not authorized")
        return StreamRuntimeDecision(
            source_id=self.source_id,
            source_stream_id=self.source_stream_id,
            state=StreamRuntimeState.SHADOW_RUNNING,
            actual_running=True,
            reason_codes=(),
            run_id=run_id,
        )


def decide_shadow_authorization(
    facts: StreamControlFacts,
    *,
    now: datetime,
) -> StreamRuntimeDecision:
    """Derive eligibility without treating research or Owner intent as authority."""

    if now.tzinfo is None:
        raise ValueError("shadow authorization time must include timezone")
    reasons: list[str] = []
    if not facts.desired_enabled:
        reasons.append("OWNER_INTENT_DISABLED")
    if facts.admission_verdict is None:
        reasons.append("SOURCE_ADMISSION_MISSING")
    elif facts.admission_verdict != "ADMIT":
        reasons.append(f"SOURCE_ADMISSION_{facts.admission_verdict}")
    elif facts.admission_valid_until is None or facts.admission_decided_at is None:
        reasons.append("SOURCE_ADMISSION_MISSING")
    elif now >= facts.admission_valid_until:
        reasons.append("SOURCE_ADMISSION_EXPIRED")
    reasons.extend(facts.gates.failure_reasons())
    if reasons:
        return StreamRuntimeDecision(
            source_id=facts.source_id,
            source_stream_id=facts.source_stream_id,
            state=StreamRuntimeState.PAUSED,
            actual_running=False,
            reason_codes=tuple(reasons),
        )
    return StreamRuntimeDecision(
        source_id=facts.source_id,
        source_stream_id=facts.source_stream_id,
        state=StreamRuntimeState.SHADOW_AUTHORIZED,
        actual_running=False,
        reason_codes=(),
    )


class PostgresControlledStreamRepository:
    """Append control facts and invoke the database-owned runtime transition commands."""

    def __init__(
        self,
        engine: AsyncEngine,
        *,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._engine = engine
        self._now = now or (lambda: datetime.now(UTC))

    async def record_research_disposition(
        self,
        *,
        source_id: UUID,
        source_stream_id: UUID,
        disposition: SourceResearchDisposition,
        research_sha256: str,
        actor_id: UUID,
    ) -> None:
        _require_sha256(research_sha256)
        async with self._engine.begin() as connection:
            await connection.execute(
                text(
                    "INSERT INTO source_research_disposition_v2("
                    "id,source_id,source_stream_id,disposition,research_sha256,recorded_by,"
                    "recorded_at) VALUES(:id,:source_id,:stream_id,:disposition,:hash,:actor,:now)"
                ),
                {
                    "id": uuid7(),
                    "source_id": source_id,
                    "stream_id": source_stream_id,
                    "disposition": disposition.value,
                    "hash": research_sha256,
                    "actor": actor_id,
                    "now": self._now(),
                },
            )
        SOURCE_STREAM_CONTROL_DECISIONS.labels(phase="research", outcome="recorded").inc()

    async def record_owner_intent(
        self,
        *,
        source_id: UUID,
        source_stream_id: UUID,
        desired_enabled: bool,
        actor_id: UUID,
        request_id: str,
    ) -> None:
        if re.fullmatch(r"[A-Za-z0-9._:-]{1,100}", request_id) is None:
            raise ValueError("source owner intent request id is invalid")
        async with self._engine.begin() as connection:
            await connection.execute(
                text(
                    "WITH intent AS (INSERT INTO source_owner_intent_v2("
                    "id,source_id,source_stream_id,desired_enabled,recorded_by,request_id,"
                    "recorded_at) VALUES(:id,:source_id,:stream_id,:desired,:actor,:request_id,"
                    ":now) ON CONFLICT(request_id) DO NOTHING RETURNING source_id) "
                    "UPDATE source SET desired_enabled=:desired,updated_at=:now "
                    "WHERE id=(SELECT source_id FROM intent)"
                ),
                {
                    "id": uuid7(),
                    "source_id": source_id,
                    "stream_id": source_stream_id,
                    "desired": desired_enabled,
                    "actor": actor_id,
                    "request_id": request_id,
                    "now": self._now(),
                },
            )
        SOURCE_STREAM_CONTROL_DECISIONS.labels(
            phase="intent", outcome="enabled" if desired_enabled else "disabled"
        ).inc()

    async def record_admission_decision(
        self,
        *,
        source_id: UUID,
        source_stream_id: UUID,
        gates: AdmissionGates,
        evidence_sha256: str,
        actor_id: UUID,
        valid_for: timedelta,
        rule_version: str = "t07-source-stream-admission-v1",
    ) -> Literal["ADMIT", "PAUSE"]:
        _require_sha256(evidence_sha256)
        if not timedelta(0) < valid_for <= timedelta(hours=24):
            raise ValueError("source admission validity must be between zero and 24 hours")
        if re.fullmatch(r"[A-Za-z0-9._:-]{1,100}", rule_version) is None:
            raise ValueError("source admission rule version is invalid")
        reasons = gates.failure_reasons()
        verdict: Literal["ADMIT", "PAUSE"] = "ADMIT" if not reasons else "PAUSE"
        decided_at = self._now()
        gates_payload = {field.name: getattr(gates, field.name) for field in fields(gates)}
        async with self._engine.begin() as connection:
            await connection.execute(
                text(
                    "INSERT INTO source_stream_admission_decision_v2("
                    "id,source_id,source_stream_id,rule_version,verdict,gates,evidence_sha256,"
                    "reason_codes,decided_by,decided_at,valid_until) VALUES("
                    ":id,:source_id,:stream_id,:rule_version,:verdict,CAST(:gates AS jsonb),"
                    ":hash,:reason_codes,:actor,:now,:valid_until)"
                ),
                {
                    "id": uuid7(),
                    "source_id": source_id,
                    "stream_id": source_stream_id,
                    "rule_version": rule_version,
                    "verdict": verdict,
                    "gates": json.dumps(gates_payload, sort_keys=True, separators=(",", ":")),
                    "hash": evidence_sha256,
                    "reason_codes": list(reasons),
                    "actor": actor_id,
                    "now": decided_at,
                    "valid_until": decided_at + valid_for,
                },
            )
        SOURCE_STREAM_CONTROL_DECISIONS.labels(phase="admission", outcome=verdict.casefold()).inc()
        return verdict

    async def authorize_shadow(
        self, *, source_id: UUID, source_stream_id: UUID
    ) -> UUID | None:
        event_id = uuid7()
        async with self._engine.begin() as connection:
            value = await connection.scalar(
                text(
                    "SELECT authorize_source_stream_shadow_v2("
                    ":event_id,:source_id,:stream_id,:now)"
                ),
                {
                    "event_id": event_id,
                    "source_id": source_id,
                    "stream_id": source_stream_id,
                    "now": self._now(),
                },
            )
        result = value if isinstance(value, UUID) else None
        SOURCE_STREAM_CONTROL_DECISIONS.labels(
            phase="authorization", outcome="authorized" if result is not None else "paused"
        ).inc()
        return result

    async def start_shadow(
        self, *, authorization_event_id: UUID, run_id: UUID
    ) -> UUID | None:
        event_id = uuid7()
        async with self._engine.begin() as connection:
            value = await connection.scalar(
                text(
                    "SELECT start_source_stream_shadow_v2("
                    ":event_id,:authorization_id,:run_id,:now)"
                ),
                {
                    "event_id": event_id,
                    "authorization_id": authorization_event_id,
                    "run_id": run_id,
                    "now": self._now(),
                },
            )
        result = value if isinstance(value, UUID) else None
        SOURCE_STREAM_CONTROL_DECISIONS.labels(
            phase="runtime", outcome="started" if result is not None else "revoked"
        ).inc()
        return result

    async def close(self) -> None:
        await self._engine.dispose()


def _require_sha256(value: str) -> None:
    if re.fullmatch(r"[a-f0-9]{64}", value) is None:
        raise ValueError("source control evidence hash must be SHA-256")
