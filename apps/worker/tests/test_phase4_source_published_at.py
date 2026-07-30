from __future__ import annotations

import inspect
from datetime import UTC, datetime

import pytest
from srbg_worker.ai_content_preparation import (
    PostgresAiPreparationRepository,
    _evidence_backed_published_at,
)


def test_evidence_backed_published_at_normalizes_only_a_real_non_future_date() -> None:
    evaluated_at = datetime(2026, 7, 30, tzinfo=UTC)

    assert _evidence_backed_published_at("2026年7月17日", evaluated_at=evaluated_at) == (
        datetime(2026, 7, 17, tzinfo=UTC)
    )

    with pytest.raises(ValueError, match="invalid accepted published_at"):
        _evidence_backed_published_at("2026-02-31", evaluated_at=evaluated_at)
    with pytest.raises(ValueError, match="future accepted published_at"):
        _evidence_backed_published_at("2026-08-01", evaluated_at=evaluated_at)


def test_materialization_projects_published_at_only_after_automatic_acceptance() -> None:
    source = inspect.getsource(PostgresAiPreparationRepository.materialize)

    assert source.index("_INSERT_AUTOMATIC_FACT_STATE_SQL") < source.index(
        "_UPDATE_SOURCE_PUBLISHED_AT_SQL"
    )
    assert "candidate[\"field\"] == \"published_at\"" in source
