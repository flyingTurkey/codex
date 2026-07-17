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
