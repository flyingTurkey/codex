import inspect
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, Mock, call
from uuid import UUID

import pytest
from srbg_api.intelligence_v2.feed_suppressions import (
    FeedSuppressionConflict,
    InvalidFeedSuppressionTarget,
    canonical_custom_topic_match,
)
from srbg_api.publication.service import PublicationDenied, PublicationService
from srbg_contracts import FeedSuppressionCommand, FeedSuppressionRuleView

NOW = datetime(2026, 7, 23, tzinfo=UTC)
RULE_ID = UUID("019f9000-0000-7000-8000-000000000044")
EVENT_ID = UUID("019f9000-0000-7000-8000-000000000046")
VERSION_ID = UUID("019f9000-0000-7000-8000-000000000047")
OWNER_ID = UUID("019f9000-0000-7000-8000-000000000048")
IDEMPOTENCY_KEY = UUID("019f9000-0000-7000-8000-000000000049")


def _service(repository: AsyncMock) -> PublicationService:
    return PublicationService(
        repository=repository,
        gate=Mock(),
        now=lambda: NOW,
    )


@pytest.mark.asyncio
async def test_activation_canonicalizes_target_and_appends_without_republishing() -> None:
    repository = AsyncMock()
    repository.command_feed_suppression.return_value = (
        FeedSuppressionRuleView.model_validate({
            "id": RULE_ID,
            "action": "ACTIVATE",
            "scope": "CUSTOM_TOPIC",
            "target_key": "隧道-监测",
            "feedback_reason": "OWNER_PREFERENCE",
            "supersedes_rule_id": None,
            "effective_at": NOW,
            "created_at": NOW,
        }),
        [],
    )
    command = FeedSuppressionCommand.model_validate(
        {
            "action": "ACTIVATE",
            "scope": "CUSTOM_TOPIC",
            "target_key": "  隧道 监测  ",
            "feedback_reason": "OWNER_PREFERENCE",
        }
    )

    result = await _service(repository).command_feed_suppression(
        command=command,
        owner_id=OWNER_ID,
        idempotency_key=IDEMPOTENCY_KEY,
        expected_rule_id=None,
    )

    assert result.target_key == "隧道-监测"
    saved = repository.command_feed_suppression.await_args.kwargs["command"]
    assert saved.target_key == "隧道-监测"
    repository.refresh_v2_projection.assert_not_awaited()


@pytest.mark.asyncio
async def test_revocation_rechecks_current_publication_gate_and_does_not_blindly_restore() -> None:
    repository = AsyncMock()
    repository.prepare_feed_suppression_revocation.return_value = [(EVENT_ID, VERSION_ID)]
    repository.command_feed_suppression.return_value = (
        FeedSuppressionRuleView.model_validate({
            "id": RULE_ID,
            "action": "REVOKE",
            "scope": "EVENT",
            "target_key": str(EVENT_ID),
            "feedback_reason": "OWNER_PREFERENCE",
            "supersedes_rule_id": RULE_ID,
            "effective_at": NOW,
            "created_at": NOW,
        }),
        [(EVENT_ID, VERSION_ID)],
    )
    repository.refresh_v2_projection.side_effect = PublicationDenied(("CURRENT_GATE_FAILED",))
    command = FeedSuppressionCommand.model_validate(
        {
            "action": "REVOKE",
            "scope": "EVENT",
            "target_key": str(EVENT_ID).upper(),
            "feedback_reason": "OWNER_PREFERENCE",
            "supersedes_rule_id": str(RULE_ID),
        }
    )

    result = await _service(repository).command_feed_suppression(
        command=command,
        owner_id=OWNER_ID,
        idempotency_key=IDEMPOTENCY_KEY,
        expected_rule_id=RULE_ID,
    )

    assert result.action.value == "REVOKE"
    repository.prepare_feed_suppression_revocation.assert_awaited_once_with(
        command=repository.command_feed_suppression.await_args.kwargs["command"],
        idempotency_key=IDEMPOTENCY_KEY,
    )
    repository.refresh_v2_projection.assert_awaited_once_with(
        event_id=EVENT_ID,
        document_version_id=VERSION_ID,
        projected_at=NOW + timedelta(microseconds=1),
    )
    assert (
        repository.method_calls.index(
            call.refresh_v2_projection(
                event_id=EVENT_ID,
                document_version_id=VERSION_ID,
                projected_at=NOW + timedelta(microseconds=1),
            )
        )
        < repository.method_calls.index(call.command_feed_suppression(
            command=repository.command_feed_suppression.await_args.kwargs["command"],
            owner_id=OWNER_ID,
            idempotency_key=IDEMPOTENCY_KEY,
            effective_at=NOW,
        ))
    )


@pytest.mark.asyncio
async def test_revocation_does_not_append_when_revalidation_crashes() -> None:
    repository = AsyncMock()
    repository.prepare_feed_suppression_revocation.return_value = [(EVENT_ID, VERSION_ID)]
    repository.refresh_v2_projection.side_effect = RuntimeError("database unavailable")
    command = FeedSuppressionCommand.model_validate(
        {
            "action": "REVOKE",
            "scope": "EVENT",
            "target_key": str(EVENT_ID),
            "feedback_reason": "OWNER_PREFERENCE",
            "supersedes_rule_id": str(RULE_ID),
        }
    )

    with pytest.raises(RuntimeError, match="database unavailable"):
        await _service(repository).command_feed_suppression(
            command=command,
            owner_id=OWNER_ID,
            idempotency_key=IDEMPOTENCY_KEY,
            expected_rule_id=RULE_ID,
        )

    repository.command_feed_suppression.assert_not_awaited()


@pytest.mark.asyncio
async def test_successful_revocation_idempotency_replay_does_not_rebuild_again() -> None:
    repository = AsyncMock()
    repository.prepare_feed_suppression_revocation.return_value = None
    repository.command_feed_suppression.return_value = (
        FeedSuppressionRuleView.model_validate(
            {
                "id": RULE_ID,
                "action": "REVOKE",
                "scope": "EVENT",
                "target_key": str(EVENT_ID),
                "feedback_reason": "OWNER_PREFERENCE",
                "supersedes_rule_id": RULE_ID,
                "effective_at": NOW,
                "created_at": NOW,
            }
        ),
        [(EVENT_ID, VERSION_ID)],
    )
    command = FeedSuppressionCommand.model_validate(
        {
            "action": "REVOKE",
            "scope": "EVENT",
            "target_key": str(EVENT_ID),
            "feedback_reason": "OWNER_PREFERENCE",
            "supersedes_rule_id": str(RULE_ID),
        }
    )

    result = await _service(repository).command_feed_suppression(
        command=command,
        owner_id=OWNER_ID,
        idempotency_key=IDEMPOTENCY_KEY,
        expected_rule_id=RULE_ID,
    )

    assert result.action.value == "REVOKE"
    repository.refresh_v2_projection.assert_not_awaited()


@pytest.mark.asyncio
async def test_losing_concurrent_revoke_converges_after_winner_timestamp() -> None:
    repository = AsyncMock()
    repository.prepare_feed_suppression_revocation.return_value = [(EVENT_ID, VERSION_ID)]
    repository.command_feed_suppression.side_effect = FeedSuppressionConflict(
        "Suppression is already revoked"
    )
    winner_at = NOW + timedelta(seconds=10)
    repository.feed_suppression_revoked_at.return_value = winner_at
    command = FeedSuppressionCommand.model_validate(
        {
            "action": "REVOKE",
            "scope": "EVENT",
            "target_key": str(EVENT_ID),
            "feedback_reason": "OWNER_PREFERENCE",
            "supersedes_rule_id": str(RULE_ID),
        }
    )

    with pytest.raises(FeedSuppressionConflict, match="already revoked"):
        await _service(repository).command_feed_suppression(
            command=command,
            owner_id=OWNER_ID,
            idempotency_key=IDEMPOTENCY_KEY,
            expected_rule_id=RULE_ID,
        )

    assert repository.refresh_v2_projection.await_args_list == [
        call(
            event_id=EVENT_ID,
            document_version_id=VERSION_ID,
            projected_at=NOW + timedelta(microseconds=1),
        ),
        call(
            event_id=EVENT_ID,
            document_version_id=VERSION_ID,
            projected_at=winner_at + timedelta(microseconds=1),
        ),
    ]


@pytest.mark.asyncio
async def test_scope_targets_are_strictly_validated() -> None:
    repository = AsyncMock()
    service = _service(repository)
    invalid = FeedSuppressionCommand.model_validate(
        {
            "action": "ACTIVATE",
            "scope": "PRIMARY_TYPE",
            "target_key": "not-a-primary-type",
            "feedback_reason": "OWNER_PREFERENCE",
        }
    )

    with pytest.raises(InvalidFeedSuppressionTarget):
        await service.command_feed_suppression(
            command=invalid,
            owner_id=OWNER_ID,
            idempotency_key=IDEMPOTENCY_KEY,
            expected_rule_id=None,
        )
    repository.command_feed_suppression.assert_not_awaited()


@pytest.mark.asyncio
async def test_custom_topic_is_revalidated_after_unicode_canonicalization() -> None:
    repository = AsyncMock()
    command = FeedSuppressionCommand.model_validate(
        {
            "action": "ACTIVATE",
            "scope": "CUSTOM_TOPIC",
            "target_key": "ß" * 300,
            "feedback_reason": "OWNER_PREFERENCE",
        }
    )

    with pytest.raises(InvalidFeedSuppressionTarget):
        await _service(repository).command_feed_suppression(
            command=command,
            owner_id=OWNER_ID,
            idempotency_key=IDEMPOTENCY_KEY,
            expected_rule_id=None,
        )

    repository.command_feed_suppression.assert_not_awaited()


def test_legacy_custom_topic_outside_frozen_target_limit_is_not_projected() -> None:
    assert canonical_custom_topic_match("x" * 301) is None
    assert canonical_custom_topic_match("valid topic") == "valid-topic"


def test_suppression_metrics_have_only_bounded_labels() -> None:
    import srbg_api.observability as observability

    source = inspect.getsource(observability)
    assert '("scope", "action", "outcome")' in source
