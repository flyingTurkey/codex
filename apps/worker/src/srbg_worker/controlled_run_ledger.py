# ruff: noqa: E501
"""PostgreSQL-backed physical attempt observer for controlled runs."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from hashlib import sha256
from urllib.parse import urlsplit
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine
from srbg_api.acquisition.http import PhysicalAttemptReservation
from srbg_api.controlled_runs import validate_acquisition_url
from srbg_api.identifiers import uuid7


class ControlledRunAttemptObserver:
    def __init__(
        self, engine: AsyncEngine, *, run_id: UUID, source_id: UUID | None, purpose: str
    ) -> None:
        self._engine = engine
        self._run_id = run_id
        self._source_id = source_id
        self._purpose = purpose

    async def reserve(self, url: str, requested_max_bytes: int) -> PhysicalAttemptReservation:
        attempt_id = uuid7()
        parsed = urlsplit(url)
        host = (parsed.hostname or "").casefold()
        path = parsed.path or "/"
        url_hash = sha256(url.encode()).hexdigest()
        if self._purpose != "AI":
            await self._wait_for_domain_slot(host)
        async with self._engine.begin() as connection:
            if self._purpose != "AI":
                boundary = (
                    (
                        await connection.execute(
                            text(
                                "SELECT expected_host,path_prefix FROM personal_controlled_run_source "
                                "WHERE run_id=:run AND source_id=:source"
                            ),
                            {"run": self._run_id, "source": self._source_id},
                        )
                    )
                    .mappings()
                    .one_or_none()
                )
                if boundary is None:
                    raise RuntimeError("CONTROLLED_RUN_SOURCE_DENIED")
                validate_acquisition_url(
                    url,
                    expected_host=boundary["expected_host"],
                    path_prefix=boundary["path_prefix"],
                    allow_robots=self._purpose == "ROBOTS",
                )
            allowance = await connection.scalar(
                text(
                    "SELECT reserve_personal_controlled_http_attempt(:attempt,:run,:source,:purpose,:url_hash,:host,:path,:maximum,:now)"
                ),
                {
                    "attempt": attempt_id,
                    "run": self._run_id,
                    "source": self._source_id,
                    "purpose": self._purpose,
                    "url_hash": url_hash,
                    "host": host,
                    "path": path,
                    "maximum": requested_max_bytes,
                    "now": datetime.now(UTC),
                },
            )
        if not isinstance(allowance, int) or allowance < 1:
            raise RuntimeError("CONTROLLED_RUN_RESERVATION_FAILED")
        return PhysicalAttemptReservation(attempt_id, allowance)

    async def _wait_for_domain_slot(self, host: str) -> None:
        async with self._engine.connect() as connection:
            seconds = await connection.scalar(
                text(
                    "SELECT GREATEST(0,EXTRACT(EPOCH FROM (max(started_at)+interval '1 minute'-now()))) "
                    "FROM personal_controlled_http_attempt WHERE run_id=:run AND host=:host"
                ),
                {"run": self._run_id, "host": host},
            )
        delay = float(seconds or 0)
        if delay > 0:
            await asyncio.sleep(min(delay + 0.05, 60.05))

    async def settle(
        self,
        reservation: PhysicalAttemptReservation,
        *,
        response_bytes: int,
        failed: bool,
        failure_code: str | None,
    ) -> None:
        async with self._engine.begin() as connection:
            await connection.scalar(
                text(
                    "SELECT settle_personal_controlled_http_attempt(:attempt,:size,:failed,:code,:now)"
                ),
                {
                    "attempt": reservation.id,
                    "size": response_bytes,
                    "failed": failed,
                    "code": failure_code,
                    "now": datetime.now(UTC),
                },
            )
