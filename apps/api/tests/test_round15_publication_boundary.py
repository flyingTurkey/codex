import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import pytest
from srbg_api.publication import repository as publication_repository
from srbg_api.publication.service import PublicationDenied
from srbg_api.source_registry.repository import canonical_json_hash

NOW = datetime(2026, 7, 16, 8, 0, tzinfo=UTC)
SOURCE_ID = UUID("019b1500-0000-7000-8000-000000009101")
VERSION_ID = UUID("019b1500-0000-7000-8000-000000009102")
CHANGE_ID = UUID("019b1500-0000-7000-8000-000000009103")


def _v2_active_facts(**overrides: object) -> dict[str, object]:
    facts: dict[str, object] = {
        "source_lifecycle_state_v2": "ACTIVE",
        # Immutable policy rows stay PENDING_REVIEW; the append-only latest
        # COMPLIANCE decision below is the approval authority.
        "source_policy_v2_status": "PENDING_REVIEW",
        "source_policy_v2_hash_verified": True,
        "source_policy_v2_valid_from": NOW - timedelta(days=1),
        "source_policy_v2_valid_until": NOW + timedelta(days=30),
        "source_policy_v2_compliance_approved": True,
        "source_connector_config_v2_status": "VALID",
        "source_trial_v2_kind": "LIVE_TRIAL",
        "source_trial_v2_execution_domain": "TRIAL",
        "source_trial_v2_result_status": "SUCCEEDED",
        "source_production_approval_current": True,
        # Legacy compatibility fields are neither V2 grants nor V2 revocations.
        "source_state": "FIXTURE_TEST",
        "source_enabled": False,
        "onboarding_record": {"decision": "REJECTED"},
    }
    facts.update(overrides)
    return facts


def test_v2_effective_active_ignores_legacy_enabled_and_onboarding_self_report() -> None:
    assert (
        publication_repository._source_is_effectively_active(  # pyright: ignore[reportPrivateUsage]
            _v2_active_facts(), evaluated_at=NOW
        )
        is True
    )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("source_lifecycle_state_v2", "PAUSED"),
        ("source_policy_v2_status", "REJECTED"),
        ("source_policy_v2_hash_verified", False),
        ("source_policy_v2_valid_from", NOW + timedelta(seconds=1)),
        ("source_policy_v2_valid_until", NOW),
        ("source_policy_v2_compliance_approved", False),
        ("source_connector_config_v2_status", "INVALID"),
        ("source_trial_v2_kind", "FIXTURE_REPLAY"),
        ("source_trial_v2_execution_domain", "FIXTURE"),
        ("source_trial_v2_result_status", "FAILED"),
        ("source_production_approval_current", False),
    ],
)
def test_v2_effective_active_is_default_deny_for_incomplete_authority(
    field: str,
    value: object,
) -> None:
    assert (
        publication_repository._source_is_effectively_active(  # pyright: ignore[reportPrivateUsage]
            _v2_active_facts(**{field: value}),
            evaluated_at=NOW,
        )
        is False
    )


@pytest.mark.parametrize("decision_state", ["LATEST_REJECTED", "APPROVAL_EXPIRED"])
def test_v2_effective_active_rejects_noncurrent_compliance_decision(
    decision_state: str,
) -> None:
    facts = _v2_active_facts(
        source_policy_v2_compliance_approved=False,
        source_policy_v2_compliance_state=decision_state,
    )

    assert (
        publication_repository._source_is_effectively_active(  # pyright: ignore[reportPrivateUsage]
            facts,
            evaluated_at=NOW,
        )
        is False
    )


def test_legacy_content_policy_integrity_remains_a_separate_publication_gate() -> None:
    policy = {
        "access": {"allowed_domains": ["example.gov.cn"]},
        "copyright": {"display_policy": "METADATA_EXCERPT_LINK"},
    }
    facts = {
        "source_policy_status": "VALID",
        "source_policy_valid_until": NOW + timedelta(days=30),
        "source_policy_sha256": canonical_json_hash(policy),
    }

    assert publication_repository._legacy_source_policy_is_valid(  # pyright: ignore[reportPrivateUsage]
        facts, source_policy=policy, evaluated_at=NOW
    )
    assert not publication_repository._legacy_source_policy_is_valid(  # pyright: ignore[reportPrivateUsage]
        facts | {"source_policy_sha256": "0" * 64},
        source_policy=policy,
        evaluated_at=NOW,
    )


class _SingleRowResult:
    def __init__(self, row: dict[str, Any]) -> None:
        self._row = row

    def mappings(self) -> "_SingleRowResult":
        return self

    def first(self) -> dict[str, Any]:
        return self._row


class _MetadataConnection:
    def __init__(self, execution_domain: str) -> None:
        self.calls = 0
        self._row = {
            "publication_id": UUID("019b1500-0000-7000-8000-000000009110"),
            "current_revision_id": UUID("019b1500-0000-7000-8000-000000009111"),
            "revision_number": 1,
            "source_policy_id": UUID("019b1500-0000-7000-8000-000000009112"),
            "source_policy_sha256": "a" * 64,
            "review_task_id": UUID("019b1500-0000-7000-8000-000000009113"),
            "evaluation": {},
            "created_by": UUID("019b1500-0000-7000-8000-000000009114"),
            "title": "test",
            "original_url": "https://example.gov.cn/test",
            "source_published_at": NOW,
            "review_status": "APPROVED",
            "source_name": "test source",
            "document_number": None,
            "issuing_authority": None,
            "regulation_status": "UNKNOWN",
            "content_hash": "b" * 64,
            "raw_sha256": "b" * 64,
            "processing_state": "READY",
            "security_status": "CLEAN",
            "execution_domain": execution_domain,
        }

    async def execute(self, *_args: object, **_kwargs: object) -> _SingleRowResult:
        self.calls += 1
        if self.calls > 1:
            raise AssertionError("non-production metadata revision reached a write")
        return _SingleRowResult(self._row)


@pytest.mark.parametrize("execution_domain", ["FIXTURE", "TRIAL", "LEGACY"])
def test_metadata_revision_rejects_every_non_production_execution_domain(
    execution_domain: str,
) -> None:
    connection = _MetadataConnection(execution_domain)

    with pytest.raises(PublicationDenied, match="NON_PRODUCTION_EXECUTION_DOMAIN"):
        asyncio.run(
            publication_repository._publish_metadata_revision(  # pyright: ignore[reportPrivateUsage]
                connection,  # type: ignore[arg-type]
                item_id=SOURCE_ID,
                current_document_version_id=VERSION_ID,
                version_change_id=CHANGE_ID,
                now=NOW,
            )
        )

    assert connection.calls == 1
