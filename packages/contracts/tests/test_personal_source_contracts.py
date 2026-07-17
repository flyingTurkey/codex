from datetime import UTC, datetime
from uuid import UUID

import pytest
from pydantic import ValidationError
from srbg_contracts import (
    PersonalSourceCreateRequest,
    PersonalSourceInputKind,
    PersonalSourcePatchRequest,
    PersonalSourceProbeStatus,
    PersonalSourceRuntimeState,
    PersonalSourceStreamStatus,
    PersonalSourceStreamType,
    PersonalSourceStreamView,
    PersonalSourceView,
    PersonalStreamHealthReason,
    PersonalStreamHealthStatus,
    PersonalStreamRuntimeState,
    SourceProfileOverrideRequest,
    SourceProfileStatus,
    StreamProbeRunView,
    UserRole,
)


def test_owner_role_and_personal_source_view_keep_intent_separate_from_runtime() -> None:
    view = PersonalSourceView(
        id=UUID("019b0000-0000-7000-8000-000000000001"),
        display_name="交通运输部",
        url="https://www.mot.gov.cn/",
        desired_enabled=True,
        runtime_state=PersonalSourceRuntimeState.PENDING_CONFIGURATION,
        manual_disabled_at=None,
    )

    assert UserRole.OWNER.value == "owner"
    assert view.desired_enabled is True
    assert view.runtime_state is PersonalSourceRuntimeState.PENDING_CONFIGURATION


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"desired_enabled": None},
        {"display_name": None},
        {"display_name": "   "},
        {"desired_enabled": True, "runtime_state": "RUNNING"},
        {"desired_enabled": True, "url": "https://example.test/"},
    ],
)
def test_personal_source_patch_accepts_only_non_null_owner_fields(
    payload: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        PersonalSourcePatchRequest.model_validate(payload)


def test_personal_source_patch_accepts_each_allowed_field() -> None:
    assert PersonalSourcePatchRequest(desired_enabled=False).desired_enabled is False
    assert PersonalSourcePatchRequest(display_name="  交通运输部  ").display_name == "交通运输部"


def test_personal_source_view_accepts_manual_disable_timestamp() -> None:
    disabled_at = datetime.now(UTC)
    view = PersonalSourceView(
        id=UUID("019b0000-0000-7000-8000-000000000001"),
        display_name="交通运输部",
        url="https://www.mot.gov.cn/",
        desired_enabled=False,
        runtime_state=PersonalSourceRuntimeState.STOPPED,
        manual_disabled_at=disabled_at,
    )

    assert view.manual_disabled_at == disabled_at


def test_pers02_contract_adds_probe_and_streams_without_changing_intent() -> None:
    stream_id = UUID("019b0000-0000-7000-8000-000000000111")
    run = StreamProbeRunView(
        id=UUID("019b0000-0000-7000-8000-000000000112"),
        requested_url="https://example.test/feed.xml",
        input_kind=PersonalSourceInputKind.RSS_ATOM,
        status=PersonalSourceProbeStatus.SUCCEEDED,
        duration_ms=12,
        failure_code=None,
        failure_reason=None,
    )
    stream = PersonalSourceStreamView(
        id=stream_id,
        stream_type=PersonalSourceStreamType.RSS_ATOM,
        normalized_url="https://example.test/feed.xml",
        allowed_hosts=["example.test"],
        config_sha256="a" * 64,
        discovery_method="DIRECT",
        status=PersonalSourceStreamStatus.READY,
        failure_reason=None,
    )
    request = PersonalSourceCreateRequest(url="https://example.test/feed.xml")

    assert str(request.url) == "https://example.test/feed.xml"
    assert run.status is PersonalSourceProbeStatus.SUCCEEDED
    assert stream.status is PersonalSourceStreamStatus.READY


def test_pers03_stream_contract_exposes_authoritative_health() -> None:
    last_success = datetime.now(UTC)
    stream = PersonalSourceStreamView(
        id=UUID("019b0000-0000-7000-8000-000000000111"),
        stream_type=PersonalSourceStreamType.RSS_ATOM,
        normalized_url="https://example.test/feed.xml",
        allowed_hosts=["example.test"],
        config_sha256="a" * 64,
        discovery_method="DIRECT",
        status=PersonalSourceStreamStatus.READY,
        failure_reason=None,
        actual_running=False,
        runtime_state=PersonalStreamRuntimeState.CIRCUIT_OPEN,
        health_status=PersonalStreamHealthStatus.UNHEALTHY,
        health_reason=PersonalStreamHealthReason.CIRCUIT_OPEN,
        consecutive_failures=5,
        next_self_heal_at=last_success,
        last_successful_fetch_at=last_success,
        last_content_discovered_at=None,
    )

    assert stream.health_reason is PersonalStreamHealthReason.CIRCUIT_OPEN
    assert stream.consecutive_failures == 5


def test_pers04_override_supports_partial_update_and_explicit_follow_auto() -> None:
    request = SourceProfileOverrideRequest(
        industries=["HIGHWAY"], authority_level="A1", region_codes=None
    )
    assert request.industries == ["HIGHWAY"]
    assert request.authority_level.value == "A1"
    assert "region_codes" in request.model_fields_set


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"industries": []},
        {"technical_facts": ["RSS_ATOM"]},
        {"publication_status": "PUBLISHED"},
    ],
)
def test_pers04_override_rejects_empty_or_non_semantic_fields(
    payload: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        SourceProfileOverrideRequest.model_validate(payload)


def test_pers04_profile_status_is_only_complete_or_partial() -> None:
    assert {value.value for value in SourceProfileStatus} == {"COMPLETE", "PARTIAL"}
