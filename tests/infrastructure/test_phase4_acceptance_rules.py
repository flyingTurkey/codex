import pytest

from scripts.run_phase4_real_event_acceptance import require_complete_model_chain


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
