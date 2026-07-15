from srbg_api.internal_projection.domain import ProjectionInput, decide_projection


def test_r3_pending_official_is_metadata_only_and_excluded_from_distribution() -> None:
    decision = decide_projection(
        ProjectionInput(
            publication_risk_tier="R3",
            review_status="PENDING",
            publication_status=None,
            official_source=True,
        )
    )
    assert decision.level == "METADATA_ONLY"
    assert decision.allowed_surfaces == frozenset({"FEED", "EVENT", "TITLE_SEARCH"})


def test_r4_is_never_projected() -> None:
    decision = decide_projection(
        ProjectionInput(
            publication_risk_tier="R4",
            review_status="APPROVED",
            publication_status="PUBLISHED",
            official_source=True,
        )
    )
    assert decision.level == "NONE"
    assert not decision.allowed_surfaces


def test_severity_cannot_grant_projection() -> None:
    low = ProjectionInput("R4", "APPROVED", "PUBLISHED", True, "LOW")
    critical = ProjectionInput("R4", "APPROVED", "PUBLISHED", True, "CRITICAL")
    assert decide_projection(low) == decide_projection(critical)
