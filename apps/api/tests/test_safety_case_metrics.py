from collections import Counter

from srbg_api.main import _render_publication_gate_denial_metrics
from srbg_api.safety_regulations.query import _render_safety_case_metrics


def test_safety_case_metrics_render_stage_status_and_human_queues() -> None:
    rendered = _render_safety_case_metrics(
        profiles=[
            {"report_stage": "INITIAL_REPORT", "incident_status": "INVESTIGATING", "count": 2},
            {"report_stage": "RECTIFICATION", "incident_status": "RECTIFYING", "count": 1},
        ],
        conflicts=[
            {"field_name": "deaths", "count": 1},
            {"field_name": "official_direct_causes", "count": 2},
        ],
        pending_event_candidates=3,
        pending_critical_claims=4,
    )

    assert (
        'srbg_safety_case_items{report_stage="INITIAL_REPORT",incident_status="INVESTIGATING"} 2'
        in rendered
    )
    assert "srbg_safety_event_candidates_pending 3" in rendered
    assert "srbg_safety_critical_claims_pending 4" in rendered
    assert 'srbg_safety_claim_conflicts_pending{field_name="deaths"} 1' in rendered
    assert 'srbg_safety_claim_conflicts_pending{field_name="official_direct_causes"} 2' in rendered


def test_safety_case_metric_metadata_is_emitted_once_per_family() -> None:
    rendered = _render_safety_case_metrics(
        profiles=[
            {"report_stage": "INITIAL_REPORT", "incident_status": "INVESTIGATING", "count": 2},
            {"report_stage": "RECTIFICATION", "incident_status": "RECTIFYING", "count": 1},
        ],
        conflicts=[
            {"field_name": "deaths", "count": 1},
            {"field_name": "loss_amount_minor", "count": 2},
        ],
        pending_event_candidates=3,
        pending_critical_claims=4,
    )

    assert rendered.count("# TYPE srbg_safety_case_items gauge") == 1
    assert rendered.count("# TYPE srbg_safety_claim_conflicts_pending gauge") == 1


def test_publication_gate_denial_metrics_are_bounded_to_safe_reason_labels() -> None:
    rendered = _render_publication_gate_denial_metrics(
        Counter(
            {
                "SAFETY_CASE_CASUALTY_LOSS_CONFLICT": 2,
                'unsafe"label': 1,
                "unsafe-lowercase": 3,
            }
        )
    )

    assert (
        'srbg_publication_gate_denials_total{reason="SAFETY_CASE_CASUALTY_LOSS_CONFLICT"} 2'
        in rendered
    )
    assert rendered.count("# TYPE srbg_publication_gate_denials_total counter") == 1
    assert rendered.count('srbg_publication_gate_denials_total{reason="UNKNOWN"}') == 1
    assert 'srbg_publication_gate_denials_total{reason="UNKNOWN"} 4' in rendered
    assert 'unsafe"label' not in rendered
