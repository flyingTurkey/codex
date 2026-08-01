from pathlib import Path

import pytest

from scripts.run_phase4_real_event_acceptance import require_complete_model_chain

LIVE_ACCEPTANCE = Path("tests/live/test_phase4_real_event_acceptance.py")


def test_live_profile_has_one_bounded_transport_retry_slot() -> None:
    source = LIVE_ACCEPTANCE.read_text(encoding="utf-8")

    assert "MAX_FETCH_ATTEMPTS = 2" in source
    assert "MAX_SOURCE_REQUESTS = 3" in source
    assert '"max_attempts": MAX_FETCH_ATTEMPTS' in source
    assert '"request_budget": MAX_SOURCE_REQUESTS' in source


def test_complete_model_chain_accepts_one_bounded_semantic_recheck() -> None:
    require_complete_model_chain(
        qualification_disposition="AUTO_ACCEPTED",
        completed_steps=[
            "CLASSIFY",
            "CLASSIFY",
            "EXTRACT",
            "SUMMARIZE",
            "VERIFY",
        ],
    )


def test_complete_model_chain_rejects_filtered_qualification_explicitly() -> None:
    with pytest.raises(
        RuntimeError,
        match="QUALIFICATION_NOT_AUTO_ACCEPTED_AUTO_FILTERED",
    ):
        require_complete_model_chain(
            qualification_disposition="AUTO_FILTERED",
            completed_steps=["CLASSIFY", "CLASSIFY"],
        )
