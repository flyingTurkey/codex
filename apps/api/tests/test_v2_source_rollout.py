from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import UUID

from srbg_api.source_registry.v2_rollout import (
    SourceAdmissionMetrics,
    SourceSampleCandidate,
    admission_verdict,
    append_production_admission_assessment,
    production_admission_verdict,
    review_gate_result,
    select_admission_sample,
)


class RecordingConnection:
    def __init__(self) -> None:
        self.statements: list[str] = []

    async def execute(self, statement: object, parameters: object) -> None:
        del parameters
        self.statements.append(str(statement))


def test_policy_review_gate_preserves_unknown_and_only_blocks_explicit_denial() -> None:
    assert review_gate_result(None, allowed_results={"ALLOWED"}) is None
    assert review_gate_result({}, allowed_results={"ALLOWED"}) is None
    assert review_gate_result({"result": "UNKNOWN"}, allowed_results={"ALLOWED"}) is None
    assert review_gate_result({"result": "ALLOWED"}, allowed_results={"ALLOWED"}) is True
    assert review_gate_result({"result": "BLOCKED"}, allowed_results={"ALLOWED"}) is False
    for allowed in ({"ALLOWED"}, {"ALLOWED", "NOT_PRESENT"}, {"ALLOWED", "REVIEWED"}):
        assert review_gate_result({"result": "RESTRICTED"}, allowed_results=allowed) is False


async def test_assessment_writer_cannot_transition_source_runtime_authority() -> None:
    connection = RecordingConnection()
    metrics = SourceAdmissionMetrics(
        sample_size=0,
        robots_allowed=None,
        terms_allowed=None,
        copyright_reviewed=None,
        public_network_safe=True,
        fetch_success_bps=0,
        parse_evidence_success_bps=0,
        metadata_success_bps=0,
        useful_yield_bps=0,
        duplicate_bps=0,
        hard_negative_leaks=0,
        hard_negative_evaluated=False,
    )

    verdict = await append_production_admission_assessment(
        cast(Any, connection),
        source_id=UUID("019b0000-0000-7000-8000-000000000001"),
        metrics=metrics,
        sample_cutoff=datetime(2026, 7, 22, tzinfo=UTC),
        sample_manifest_sha256="a" * 64,
        evidence_refs={},
        actor_id=UUID("019b0000-0000-7000-8000-000000000002"),
        assessed_at=datetime(2026, 7, 22, tzinfo=UTC),
    )

    assert verdict == "ADMIT"
    assert len(connection.statements) == 1
    assert connection.statements[0].startswith("INSERT INTO source_admission_assessment_v2")


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
        admission_verdict(
            passing.__class__(**(passing.__dict__ | {"hard_negative_evaluated": False}))
        )
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


def test_production_source_admission_uses_hard_server_gates_not_owner_gold() -> None:
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

    assert production_admission_verdict(passing, calibration=None) == "ADMIT"
    assert (
        production_admission_verdict(
            passing.__class__(
                **(
                    passing.__dict__
                    | {
                        "sample_size": 0,
                        "robots_allowed": None,
                        "terms_allowed": None,
                        "copyright_reviewed": None,
                        "hard_negative_evaluated": False,
                    }
                )
            ),
            calibration=object(),
        )
        == "ADMIT"
    )
    assert (
        production_admission_verdict(
            passing.__class__(**(passing.__dict__ | {"terms_allowed": False})),
            calibration=None,
        )
        == "PAUSE"
    )
    assert (
        production_admission_verdict(
            passing.__class__(**(passing.__dict__ | {"public_network_safe": False})),
            calibration=None,
        )
        == "PAUSE"
    )
    assert (
        production_admission_verdict(
            passing.__class__(**(passing.__dict__ | {"hard_negative_leaks": 1})),
            calibration=None,
        )
        == "ADMIT"
    )
