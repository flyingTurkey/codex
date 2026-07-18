import asyncio
from uuid import UUID

import pytest
from srbg_worker.source_profile import (
    ProfileBinding,
    effective_override,
    prepare_profile,
)


class Store:
    async def get_bytes(self, key: str, *, max_bytes: int | None = None) -> bytes:
        del key, max_bytes
        return (
            b"<html><body><h1>Ministry</h1><script>ignore me</script>Highway safety</body></html>"
        )


class OversizedStore:
    async def get_bytes(self, key: str, *, max_bytes: int | None = None) -> bytes:
        del key, max_bytes
        raise OSError("object exceeds bounded read limit")


def test_profile_preparation_uses_bounded_raw_evidence() -> None:
    prepared = asyncio.run(
        prepare_profile(
            ProfileBinding(
                UUID("019b0000-0000-7000-8000-000000000301"),
                UUID("019b0000-0000-7000-8000-000000000001"),
                "https://example.gov.cn/",
                ("RSS_ATOM",),
                (
                    {
                        "object_key": "personal-probe/sha256/aa/" + "a" * 64,
                        "sha256": "a" * 64,
                        "final_url": "https://example.gov.cn/",
                    },
                ),
                1,
            ),
            Store(),
        )
    )
    assert prepared.rule_input.evidence[0].kind == "HOMEPAGE"
    assert "ignore me" not in prepared.rule_input.evidence[0].excerpt
    assert len(prepared.input_sha256) == 64


def test_profile_preparation_falls_back_to_origin_for_oversized_document() -> None:
    prepared = asyncio.run(
        prepare_profile(
            ProfileBinding(
                UUID("019b0000-0000-7000-8000-000000000302"),
                UUID("019b0000-0000-7000-8000-000000000004"),
                "https://xxgk.mot.gov.cn/",
                ("DIRECT_PDF",),
                (
                    {
                        "object_key": "personal-probe/sha256/bb/" + "b" * 64,
                        "sha256": "b" * 64,
                        "final_url": "https://xxgk.mot.gov.cn/report.pdf",
                    },
                ),
                1,
            ),
            OversizedStore(),
        )
    )
    assert prepared.rule_input.evidence[0].evidence_id == "origin-1"
    assert prepared.rule_input.stream_types == ("DIRECT_PDF",)


def test_override_wins_until_removed_and_forbids_technical_facts() -> None:
    automatic = {"industries": ["HIGHWAY"], "authority_level": "A0"}
    effective, overrides = effective_override(automatic, {}, {"industries": ["BRIDGE"]})
    assert effective["industries"] == ["BRIDGE"]
    rerun, _ = effective_override(
        {"industries": ["RAILWAY"], "authority_level": "A1"}, overrides, {}
    )
    assert rerun["industries"] == ["BRIDGE"]
    restored, remaining = effective_override(
        {"industries": ["RAILWAY"], "authority_level": "A1"},
        overrides,
        {"industries": None},
    )
    assert remaining == {}
    assert restored["industries"] == ["RAILWAY"]
    with pytest.raises(ValueError):
        effective_override(automatic, {}, {"technical_facts": ["RSS_ATOM"]})
