"""Production orchestration for explainable safety-event link candidates."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Protocol, cast
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import text
from sqlalchemy.engine import RowMapping
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from srbg_api.identifiers import uuid7
from srbg_api.safety_cases.domain import EventIdentity
from srbg_api.safety_cases.matching import score_event_match

_DISPLAY_TIME_ZONE = ZoneInfo("Asia/Shanghai")


class EventCandidateAlreadyDecided(RuntimeError):
    """The unique event/item proposal already has a terminal human decision."""


@dataclass(frozen=True, slots=True)
class EventCandidateContext:
    identity: EventIdentity
    confirmation_status: str
    member_count: int
    candidate_count: int


@dataclass(frozen=True, slots=True)
class EventCandidateRecord:
    """An explainable candidate that can only enter the human-review queue."""

    event_id: UUID
    item_id: UUID
    score: int
    matched_dimensions: dict[str, int]
    algorithm_version: str
    requires_human_review: bool


class EventCandidateStore(Protocol):
    async def close(self) -> None: ...

    async def create_candidate(
        self,
        *,
        event_id: UUID,
        item_id: UUID,
        build: Callable[[EventCandidateContext, EventIdentity], EventCandidateRecord | None],
    ) -> UUID | None: ...


class SafetyEventCandidateService:
    """Generate review candidates without ever confirming event membership."""

    def __init__(self, store: EventCandidateStore) -> None:
        self._store = store

    async def close(self) -> None:
        await self._store.close()

    async def generate_candidate(
        self,
        *,
        event_id: UUID,
        item_id: UUID,
    ) -> UUID | None:
        return await self._store.create_candidate(
            event_id=event_id,
            item_id=item_id,
            build=lambda event_context, incoming: self._build_candidate(
                event_id=event_id,
                item_id=item_id,
                event_context=event_context,
                incoming=incoming,
            ),
        )

    def _build_candidate(
        self,
        *,
        event_id: UUID,
        item_id: UUID,
        event_context: EventCandidateContext,
        incoming: EventIdentity,
    ) -> EventCandidateRecord | None:
        existing = event_context.identity
        if (
            _identity_is_empty(existing)
            and event_context.confirmation_status == "PENDING_REVIEW"
            and event_context.member_count == 0
            and event_context.candidate_count == 0
        ):
            existing = incoming
        result = score_event_match(existing, incoming)
        if not result.forms_candidate:
            return None
        if not result.requires_human_review:
            raise ValueError("safety-event matches must never bypass human review")
        return EventCandidateRecord(
            event_id=event_id,
            item_id=item_id,
            score=result.total,
            matched_dimensions=result.dimension_scores,
            algorithm_version=result.algorithm_version,
            requires_human_review=True,
        )


class PostgresEventCandidateStore:
    """PostgreSQL adapter for the production candidate-generation service."""

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def close(self) -> None:
        await self._engine.dispose()

    async def create_candidate(
        self,
        *,
        event_id: UUID,
        item_id: UUID,
        build: Callable[[EventCandidateContext, EventIdentity], EventCandidateRecord | None],
    ) -> UUID | None:
        async with self._engine.begin() as connection:
            await connection.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
                {"key": f"event:{event_id}"},
            )
            event_row = (
                (
                    await connection.execute(
                        text(
                            """
                            SELECT safety_event.occurred_at, safety_event.region_name,
                                   safety_event.project_name, safety_event.subject_names,
                                   safety_event.accident_type,
                                   safety_event.confirmation_status,
                                   (SELECT count(*)::integer FROM event_item AS membership
                                    WHERE membership.event_id = safety_event.id) AS member_count,
                                   (SELECT count(*)::integer
                                    FROM event_item_candidate AS candidate
                                    WHERE candidate.event_id = safety_event.id) AS candidate_count
                            FROM event AS safety_event
                            WHERE safety_event.id = :event_id
                            """
                        ),
                        {"event_id": event_id},
                    )
                )
                .mappings()
                .one_or_none()
            )
            if event_row is None:
                raise LookupError(f"safety event {event_id} was not found")

            existing = await _existing_candidate(connection, event_id=event_id, item_id=item_id)
            if existing is not None:
                return _pending_candidate_id(existing, item_id=item_id)

            item_row = (
                (
                    await connection.execute(
                        text(
                            """
                            SELECT occurred_at, region_name, project_name,
                                   subject_names, accident_type
                            FROM safety_case_profile
                            WHERE item_id = :item_id
                            """
                        ),
                        {"item_id": item_id},
                    )
                )
                .mappings()
                .one_or_none()
            )
            if item_row is None:
                raise LookupError(f"safety-case item {item_id} was not found")

            candidate = build(_context_from_row(event_row), _identity_from_row(item_row))
            if candidate is None:
                return None
            if not candidate.requires_human_review:
                raise ValueError("safety-event matches must remain human-review candidates")
            candidate_id = uuid7()
            persisted_id = await connection.scalar(
                text(
                    """
                    INSERT INTO event_item_candidate (
                        id, event_id, item_id, score, matched_dimensions,
                        algorithm_version, submitted_by, created_at
                    )
                    SELECT
                        :id, :event_id, :item_id, :score,
                        CAST(:matched_dimensions AS jsonb), :algorithm_version,
                        item.submitted_by, :created_at
                    FROM intelligence_item AS item
                    WHERE item.id = :item_id
                    ON CONFLICT (event_id, item_id) DO NOTHING
                    RETURNING id
                    """
                ),
                {
                    "id": candidate_id,
                    "event_id": candidate.event_id,
                    "item_id": candidate.item_id,
                    "score": candidate.score,
                    "matched_dimensions": json.dumps(
                        candidate.matched_dimensions,
                        ensure_ascii=False,
                        separators=(",", ":"),
                        sort_keys=True,
                    ),
                    "algorithm_version": candidate.algorithm_version,
                    "created_at": datetime.now(UTC),
                },
            )
            if isinstance(persisted_id, UUID):
                return persisted_id
            existing = await _existing_candidate(
                connection,
                event_id=candidate.event_id,
                item_id=candidate.item_id,
            )
            if existing is None:
                raise LookupError(f"safety-case item {candidate.item_id} was not found")
            return _pending_candidate_id(existing, item_id=candidate.item_id)


async def _existing_candidate(
    connection: AsyncConnection,
    *,
    event_id: UUID,
    item_id: UUID,
) -> RowMapping | None:
    return (
        (
            await connection.execute(
                text(
                    """
                    SELECT candidate.id, decision.id AS decision_id
                    FROM event_item_candidate AS candidate
                    LEFT JOIN event_item_decision AS decision
                      ON decision.candidate_id = candidate.id
                    WHERE candidate.event_id = :event_id
                      AND candidate.item_id = :item_id
                    """
                ),
                {"event_id": event_id, "item_id": item_id},
            )
        )
        .mappings()
        .one_or_none()
    )


def _pending_candidate_id(row: RowMapping, *, item_id: UUID) -> UUID:
    if row["decision_id"] is not None:
        raise EventCandidateAlreadyDecided(
            f"event candidate for item {item_id} already has a decision"
        )
    candidate_id = row["id"]
    if not isinstance(candidate_id, UUID):
        raise RuntimeError("event candidate identifier is invalid")
    return candidate_id


def _context_from_row(row: RowMapping) -> EventCandidateContext:
    confirmation_status = row["confirmation_status"]
    member_count = row["member_count"]
    candidate_count = row["candidate_count"]
    if (
        not isinstance(confirmation_status, str)
        or not isinstance(member_count, int)
        or not isinstance(candidate_count, int)
    ):
        raise RuntimeError("safety event candidate context is invalid")
    return EventCandidateContext(
        identity=_identity_from_row(row),
        confirmation_status=confirmation_status,
        member_count=member_count,
        candidate_count=candidate_count,
    )


def _identity_from_row(row: Mapping[str, object] | RowMapping) -> EventIdentity:
    occurred_at = row["occurred_at"]
    occurred_on: date | None
    if (
        isinstance(occurred_at, datetime)
        and occurred_at.tzinfo is not None
        and occurred_at.utcoffset() is not None
    ):
        occurred_on = occurred_at.astimezone(_DISPLAY_TIME_ZONE).date()
    elif isinstance(occurred_at, date):
        occurred_on = occurred_at
    else:
        occurred_on = None

    subjects_value = row["subject_names"]
    subjects = (
        tuple(value for value in cast(list[object], subjects_value) if isinstance(value, str))
        if isinstance(subjects_value, list)
        else ()
    )
    return EventIdentity(
        occurred_on=occurred_on,
        region=_optional_text(row["region_name"]),
        project=_optional_text(row["project_name"]),
        subjects=subjects,
        accident_type=_optional_text(row["accident_type"]),
    )


def _optional_text(value: object) -> str | None:
    return value if isinstance(value, str) and value.strip() else None


def _identity_is_empty(identity: EventIdentity) -> bool:
    return (
        identity.occurred_on is None
        and identity.region is None
        and identity.project is None
        and not identity.subjects
        and identity.accident_type is None
    )
