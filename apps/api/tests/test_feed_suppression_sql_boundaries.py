import inspect

from srbg_api.intelligence_v2.service import PostgresV2IntelligenceService
from srbg_api.publication.repository import PostgresPublicationRepository


def test_feed_search_and_hotspot_filter_in_sql_before_limit_and_cursor() -> None:
    for method in (
        PostgresV2IntelligenceService.feed,
        PostgresV2IntelligenceService.search,
        PostgresV2IntelligenceService.hotspots,
    ):
        source = inspect.getsource(method)
        assert "visible_intelligence_projection_v2" in source
        assert "LIMIT :row_limit" in source
        assert "intelligence_projection_v2 " not in source.replace(
            "visible_intelligence_projection_v2", ""
        )


def test_detail_appendix_and_media_authorize_suppression_in_sql() -> None:
    event_source = inspect.getsource(PostgresV2IntelligenceService.event)
    appendix_source = inspect.getsource(PostgresV2IntelligenceService.appendix)
    media_source = inspect.getsource(PostgresV2IntelligenceService._media)

    assert "visible_intelligence_projection_v2" in event_source
    assert "visible_intelligence_projection_v2" in appendix_source
    assert "visible_intelligence_projection_v2" in media_source
    assert "media.event_id=projection.event_id" in media_source


def test_projection_writer_rebuilds_all_suppression_match_keys_atomically() -> None:
    source = inspect.getsource(PostgresPublicationRepository.upsert_v2_projection)
    refresh_source = inspect.getsource(PostgresPublicationRepository.refresh_v2_projection)

    assert "DELETE FROM event_suppression_match_v2" in source
    assert "INSERT INTO event_suppression_match_v2" in source
    assert "suppression_targets" in source
    assert "ARRAY(SELECT DISTINCT related.source_id::text" in refresh_source
    assert "FROM topic_event membership" in refresh_source
    assert 'topic.status=\'CONFIRMED\'' in refresh_source
    assert 'row["custom_topics"]' in refresh_source
