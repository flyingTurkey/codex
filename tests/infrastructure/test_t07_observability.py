import re
from inspect import getsource

from srbg_api import observability
from srbg_api.source_registry.controlled_stream import PostgresControlledStreamRepository
from srbg_worker.controlled_shadow import ControlledShadowCollector


def test_t07_metrics_use_only_bounded_phase_outcome_and_document_kind_labels() -> None:
    assert observability.SOURCE_STREAM_CONTROL_DECISIONS._labelnames == ("phase", "outcome")
    assert observability.SOURCE_SHADOW_COLLECTION._labelnames == ("outcome", "document_kind")

    source = getsource(PostgresControlledStreamRepository)
    worker = getsource(ControlledShadowCollector)
    assert "SOURCE_STREAM_CONTROL_DECISIONS.labels" in source
    assert "SOURCE_SHADOW_COLLECTION.labels" in worker
    for call in re.findall(r"\.labels\((.*?)\)", source + worker, flags=re.DOTALL):
        assert "source_id" not in call
        assert "source_stream_id" not in call
