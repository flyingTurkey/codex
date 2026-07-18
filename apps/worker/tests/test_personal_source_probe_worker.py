from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

import pytest
from srbg_worker.personal_source_probe import (
    PersonalProbeBinding,
    PersonalProbeExecutor,
    ProbeFetch,
    _probe_timeout_seconds,
)

RUN_ID = UUID("019b0000-0000-7000-8000-000000000201")


def test_controlled_probe_timeout_includes_durable_domain_slots() -> None:
    binding = PersonalProbeBinding(
        run_id=RUN_ID,
        source_id=UUID("019b0000-0000-7000-8000-000000000202"),
        stream_id=UUID("019b0000-0000-7000-8000-000000000203"),
        requested_url="https://example.test/",
        allowed_host="example.test",
        controlled_run_id=UUID("019b0000-0000-7000-8000-000000000204"),
    )
    assert _probe_timeout_seconds(binding) == 900
    assert (
        _probe_timeout_seconds(
            PersonalProbeBinding(
                run_id=binding.run_id,
                source_id=binding.source_id,
                stream_id=binding.stream_id,
                requested_url=binding.requested_url,
                allowed_host=binding.allowed_host,
            )
        )
        == 30
    )


class Gateway:
    def __init__(self) -> None:
        self.completed = None
        self.failed = None

    async def acquire(self, run_id: UUID):
        assert run_id == RUN_ID
        return PersonalProbeBinding(
            run_id=run_id,
            source_id=UUID("019b0000-0000-7000-8000-000000000202"),
            stream_id=UUID("019b0000-0000-7000-8000-000000000203"),
            requested_url="https://example.test/",
            allowed_host="example.test",
        )

    async def complete(self, binding, result, captures):
        self.completed = (binding, result, captures)

    async def fail(self, binding, *, code, reason, captures):
        self.failed = (binding, code, reason, captures)


class Fetcher:
    async def fetch(self, url: str, *, allowed_host: str) -> ProbeFetch:
        assert allowed_host == "example.test"
        if url.endswith("feed.xml"):
            body = b"<rss><channel/></rss>"
            mime = "application/rss+xml"
        else:
            body = (
                b"<html><head><link rel='alternate' type='application/rss+xml' "
                b"href='/feed.xml'></head></html>"
            )
            mime = "text/html"
        return ProbeFetch(url, url, 200, mime, body, datetime.now(UTC), ())


class Store:
    def __init__(self) -> None:
        self.keys = []

    async def put_if_absent(self, key: str, content: bytes, content_type: str) -> str:
        self.keys.append((key, content, content_type))
        return "etag"


@pytest.mark.asyncio
async def test_probe_stores_raw_before_following_and_completes_feed() -> None:
    gateway, store = Gateway(), Store()
    result = await PersonalProbeExecutor(
        gateway=gateway, fetcher=Fetcher(), object_store=store
    ).run(RUN_ID)

    assert result == "SUCCEEDED"
    assert len(store.keys) == 2
    assert gateway.completed is not None
    assert gateway.completed[1].streams[0].normalized_url == "https://example.test/feed.xml"


@dataclass
class BlockedFetcher:
    marker: bytes

    async def fetch(self, url: str, *, allowed_host: str) -> ProbeFetch:
        del allowed_host
        return ProbeFetch(url, url, 200, "text/html", self.marker, datetime.now(UTC), ())


@pytest.mark.asyncio
@pytest.mark.parametrize("marker", [b"please login", b"captcha", b"subscribe to continue"])
async def test_login_captcha_and_paywall_are_hard_failures(marker: bytes) -> None:
    gateway = Gateway()
    result = await PersonalProbeExecutor(
        gateway=gateway, fetcher=BlockedFetcher(marker), object_store=Store()
    ).run(RUN_ID)
    assert result == "FAILED"
    assert gateway.failed is not None
    assert gateway.failed[1] in {"LOGIN_REQUIRED", "CAPTCHA_DETECTED", "PAYWALL_DETECTED"}
