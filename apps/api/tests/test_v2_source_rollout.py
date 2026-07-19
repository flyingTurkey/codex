from datetime import UTC, datetime, timedelta

from srbg_api.source_registry.v2_rollout import (
    SourceAdmissionMetrics,
    SourceSampleCandidate,
    admission_verdict,
    select_admission_sample,
)


def test_source_admission_requires_hard_compliance_and_quality_thresholds() -> None:
    passing = SourceAdmissionMetrics(
        sample_size=30,
        robots_allowed=True,
        terms_allowed=True,
        copyright_reviewed=True,
        public_network_safe=True,
        fetch_success_bps=9800,
        parse_evidence_success_bps=9500,
        metadata_success_bps=9800,
        useful_yield_bps=5000,
        duplicate_bps=3000,
        hard_negative_leaks=0,
    )
    assert admission_verdict(passing) == "ADMIT"
    assert (
        admission_verdict(passing.__class__(**(passing.__dict__ | {"hard_negative_leaks": 1})))
        == "PAUSE"
    )
    assert (
        admission_verdict(passing.__class__(**(passing.__dict__ | {"sample_size": 29})))
        == "OBSERVE"
    )


def test_source_sample_is_recent_deduplicated_and_deterministic() -> None:
    cutoff = datetime(2026, 7, 19, tzinfo=UTC)
    values = [
        SourceSampleCandidate(
            document_version_id=f"version-{index:02d}",
            canonical_key=f"document-{index % 35:02d}",
            source_published_at=cutoff - timedelta(days=index % 95),
        )
        for index in range(50)
    ]
    selected = select_admission_sample(values, cutoff=cutoff)
    assert len(selected) == 30
    assert len({value.canonical_key for value in selected}) == 30
    assert all(value.source_published_at >= cutoff - timedelta(days=90) for value in selected)
    assert selected == tuple(
        sorted(
            selected,
            key=lambda value: (value.source_published_at, value.document_version_id),
            reverse=True,
        )
    )
