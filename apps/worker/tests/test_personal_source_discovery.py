from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import pytest
from srbg_worker.personal_source_discovery import (
    AutoEnableCandidate,
    PersonalAutoEnableExecutor,
    discover_public_origins,
)

NOW = datetime(2026, 7, 17, tzinfo=UTC)


class StubGateway:
    def __init__(self, candidates: tuple[AutoEnableCandidate, ...], quota: int = 20) -> None:
        self.candidates = candidates
        self.quota = quota
        self.enabled: list[UUID] = []

    async def list_eligible(self, *, limit: int) -> tuple[AutoEnableCandidate, ...]:
        return self.candidates[:limit]

    async def try_auto_enable(self, source_id: UUID, *, now: datetime) -> bool:
        if len(self.enabled) >= self.quota:
            return False
        self.enabled.append(source_id)
        return True


def candidate(index: int, score: int = 70) -> AutoEnableCandidate:
    return AutoEnableCandidate(
        source_id=UUID(f"019f0000-0000-7000-8000-{index:012d}"),
        total_score=score,
        first_discovered_at=NOW,
    )


@pytest.mark.asyncio
async def test_daily_auto_enable_stops_at_twenty_and_defers_remainder() -> None:
    gateway = StubGateway(tuple(candidate(index, 100 - index) for index in range(25)))

    result = await PersonalAutoEnableExecutor(gateway).run(now=NOW)

    assert result.enabled == 20
    assert result.deferred == 5
    assert len(gateway.enabled) == 20


@pytest.mark.asyncio
async def test_auto_enable_uses_score_then_discovery_then_uuid_order() -> None:
    later = datetime(2026, 7, 18, tzinfo=UTC)
    rows = (
        AutoEnableCandidate(candidate(3).source_id, 75, later),
        AutoEnableCandidate(candidate(2).source_id, 75, NOW),
        AutoEnableCandidate(candidate(1).source_id, 75, NOW),
        AutoEnableCandidate(candidate(4).source_id, 80, later),
    )
    gateway = StubGateway(tuple(sorted(rows, key=AutoEnableCandidate.sort_key)))

    await PersonalAutoEnableExecutor(gateway).run(now=NOW)

    assert gateway.enabled == [
        candidate(4).source_id,
        candidate(1).source_id,
        candidate(2).source_id,
        candidate(3).source_id,
    ]


def test_free_link_discovery_accepts_depth_one_and_rejects_depth_two() -> None:
    body = b"<rss><channel><link>https://agency.example.cn/news</link></channel></rss>"
    assert discover_public_origins(body, parent_origin="https://parent.example.cn", depth=0) == (
        "https://agency.example.cn",
    )
    assert discover_public_origins(body, parent_origin="https://parent.example.cn", depth=1) == ()


def test_free_link_discovery_rejects_same_origin_non_https_and_credentials() -> None:
    body = (
        b'<a href="https://parent.example.cn/a">same</a>'
        b'<a href="http://other.example.cn/a">http</a>'
        b'<a href="https://user:pass@evil.example.cn/a">bad</a>'
        b"<loc>https://safe.example.cn/sitemap.xml</loc>"
    )
    assert discover_public_origins(body, parent_origin="https://parent.example.cn", depth=0) == (
        "https://safe.example.cn",
    )
