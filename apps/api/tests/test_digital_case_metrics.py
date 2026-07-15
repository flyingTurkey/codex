from srbg_api.safety_regulations.query import _render_digital_case_metrics


def test_digital_case_metrics_distinguish_source_maturity_outcomes_and_review_queue() -> None:
    rendered = _render_digital_case_metrics(
        profiles=[
            {
                "source_nature": "GOVERNMENT_CASE_COLLECTION",
                "maturity_level": "PILOT",
                "count": 2,
            },
            {
                "source_nature": "ENTERPRISE_SELF_REPORT",
                "maturity_level": "SINGLE_PROJECT_PRODUCTION",
                "count": 1,
            },
        ],
        outcomes={"CLAIMED": 3, "VERIFIED": 1},
        pending_enterprise_review=1,
    )

    assert 'source_nature="ENTERPRISE_SELF_REPORT"' in rendered
    assert 'maturity_level="SINGLE_PROJECT_PRODUCTION"} 1' in rendered
    assert 'verification="CLAIMED"} 3' in rendered
    assert 'verification="VERIFIED"} 1' in rendered
    assert "srbg_digital_enterprise_review_pending 1" in rendered
