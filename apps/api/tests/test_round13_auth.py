import logging
from uuid import UUID

import pytest
from fastapi import HTTPException
from srbg_api.auth import Principal, require_local_owner
from srbg_contracts import UserRole


@pytest.mark.asyncio
async def test_nonfixed_identity_denial_emits_privacy_safe_structured_log(
    caplog: pytest.LogCaptureFixture,
) -> None:
    principal = Principal(
        user_id=UUID("019b0000-0000-7000-8000-000000001399"),
        display_name="forged owner",
        roles=frozenset({UserRole.OWNER}),
        local_identity=True,
    )

    with caplog.at_level(logging.WARNING, logger="srbg.auth"), pytest.raises(HTTPException):
        await require_local_owner(principal)

    record = next(record for record in caplog.records if record.message == "authorization_denied")
    assert record.reason == "personal_owner"
    assert not hasattr(record, "user_id")
