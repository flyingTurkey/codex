from inspect import getsource

from srbg_api.safety_regulations.query import PostgresIntelligenceQueryService


def test_all_feed_variants_apply_governed_ai_and_revision_projection() -> None:
    service_source = getsource(PostgresIntelligenceQueryService)

    assert "async def _with_round09_projection" in service_source
    assert service_source.count("await self._with_round09_projection(visible)") == 4
    assert "accepted.verification_status = 'ACCEPTED'" in service_source
    assert "current_revision.action AS revision_action" in service_source


def test_feed_projection_reads_only_completed_four_step_live_runs() -> None:
    service_source = getsource(PostgresIntelligenceQueryService)

    assert "run.mode = 'LIVE' AND run.status = 'SUCCEEDED'" in service_source
    assert "count(DISTINCT step.step)" in service_source
    assert "= 4" in service_source
