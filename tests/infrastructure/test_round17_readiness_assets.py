import json
from base64 import b64decode
from hashlib import sha256
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from scripts.round17_sign_approval import canonical_json

ASSET = Path("docs/codex-kit/assets/validation/round17_candidate_roster.json")
APPROVED = Path("docs/codex-kit/assets/validation/round17_approved_authority.json")
SIGNED = Path("docs/acceptance/assets/round17/leo-signed-approval.json")
FLAT_READINESS = Path("docs/acceptance/phase-2/round-17-flat-readiness.json")


def test_round17_roster_is_an_honest_unapproved_candidate_not_runtime_authority() -> None:
    roster = json.loads(ASSET.read_text(encoding="utf-8"))

    assert roster["roster_version"] == "r17-sources-v0.1"
    assert roster["status"] == "PENDING_LEO_CONFIRMATION"
    assert roster["runtime_authority"] is False
    assert roster["approver"] == "LEO"
    assert roster["approval_evidence_ref"] is None
    assert roster["window"]["suggested_duration_hours"] == 168
    assert roster["window"]["confirmed"] is False
    sources = roster["sources"]
    assert len(sources) == len({source["source_code"] for source in sources}) == 20
    assert all(source["status"] == "PENDING_HUMAN_ADMISSION" for source in sources)
    assert all(source["approval_evidence_ref"] is None for source in sources)
    assert all(source["suggested_governance_owner"] == "yinzi" for source in sources)
    assert any(source["registry_presence"] == "MISSING" for source in sources)


def test_round17_suggested_people_keep_confirmed_and_proposed_duties_separate() -> None:
    roster = json.loads(ASSET.read_text(encoding="utf-8"))
    people = {person["display_name"]: person for person in roster["people"]}

    assert people["LEO"]["confirmed_duties"] == ["SOLE_APPROVER"]
    assert people["yinzi"]["confirmed_duties"] == ["OPERATIONS_ADMIN"]
    assert people["baixuejiao"]["confirmed_duties"] == ["BUSINESS_STANDARD_B"]
    assert "GOLD_ARBITRATOR" in people["LEO"]["suggested_duties"]
    assert "DIGITAL_PRIMARY" in people["baixuejiao"]["suggested_duties"]


def test_round17_flat_authority_records_the_frozen_leo_decisions() -> None:
    authority = json.loads(APPROVED.read_text(encoding="utf-8"))

    assert authority["authority_state"] == "LEO_CONFIRMED_AND_FROZEN"
    assert authority["runtime_authority"] is False
    assert authority["authority_mode"] == "SIGNED_LOCAL_PILOT"
    assert authority["approver"] == {
        "display_name": "LEO",
        "actor_id": "019f6b65-4cf5-71d1-b75c-a6c908912f58",
        "responsibility": "SOURCE_APPROVER",
        "administrator_count": 1,
    }
    assert authority["reference_model"] == "LEO_SINGLE_EXPERT_REFERENCE_SET"
    assert authority["reference_assurance"] == "LOWER_THAN_DUAL_EXPERT_GOLD"
    assert authority["window"] == {
        "duration_hours": 168,
        "confirmed": True,
        "automatic_start": False,
    }
    assert authority["administration"]["individual_performance_targets"] is False


def test_round17_flat_authority_has_exact_roster_and_schedules() -> None:
    authority = json.loads(APPROVED.read_text(encoding="utf-8"))
    sources = authority["sources"]
    codes = [source["source_code"] for source in sources]

    assert len(codes) == len(set(codes)) == 20
    assert set(codes) == {
        "GOV-002", "GOV-003", "GOV-004", "GOV-005", "GOV-006", "GOV-007",
        "GOV-008", "GOV-010", "GOV-014", "GOV-015", "GOV-016", "GOV-017",
        "GOV-020", "NRA-001", "RES-001", "RES-004", "ENT-005", "ENT-006",
        "ENT-007", "ENT-008",
    }
    for source in sources:
        expected = {6: 8, 12: 18, 24: 30}[source["poll_hours"]]
        assert source["discovery_slo_hours"] == expected


def test_round17_public_approval_package_verifies_without_private_material() -> None:
    package = json.loads(SIGNED.read_text(encoding="utf-8"))
    document_bytes = canonical_json(package["approval_document"])
    public_bytes = b64decode(package["signer_public_key_base64"], validate=True)

    assert package["approval_document"] == json.loads(APPROVED.read_text(encoding="utf-8"))
    assert package["approval_document_sha256"] == sha256(document_bytes).hexdigest()
    assert package["signer_public_key_sha256"] == sha256(public_bytes).hexdigest()
    Ed25519PublicKey.from_public_bytes(public_bytes).verify(
        b64decode(package["approval_signature"], validate=True), document_bytes
    )
    assert "private_key" not in json.dumps(package).lower()


def test_round17_flat_readiness_is_honestly_blocked_without_real_window_evidence() -> None:
    readiness = json.loads(FLAT_READINESS.read_text(encoding="utf-8"))
    signed = json.loads(SIGNED.read_text(encoding="utf-8"))

    assert readiness["record_type"] == "ENGINEERING_READINESS_NOT_PILOT_EVIDENCE"
    assert readiness["decision"] == "BLOCKED"
    assert readiness["implementation_commits"] == [
        "d3b11cca0816f5c5da656af0fb4b28e60e87ae0e",
        "6a9ef67dfbbee05c0c1ad0f4b010fbbd3f57369a",
        "ef8d80956d05e000c5e17d0570b9b9532a0b3134",
    ]
    assert readiness["authority"]["approval_document_sha256"] == signed[
        "approval_document_sha256"
    ]
    assert readiness["authority"]["public_key_sha256"] == signed[
        "signer_public_key_sha256"
    ]
    assert readiness["observation_window"] == {
        "confirmed_duration_hours": 168,
        "state": "NOT_STARTED",
        "started_at": None,
        "ended_at": None,
        "continuous_days_proven": 0,
    }
    assert readiness["source_preflight"]["expected_count"] == 20
    assert readiness["source_preflight"]["registered_count"] == 20
    assert readiness["source_preflight"]["missing_source_codes"] == []
    assert readiness["source_preflight"]["active_count"] == 0
    assert readiness["real_evidence"] == {
        "window_evidence_manifest_present": False,
        "single_expert_reference_manifest_present": False,
        "north_star_computed": False,
        "fault_drill_present": False,
        "source_health_series_present": False,
    }
    assert "REAL_168_HOUR_EVIDENCE_MISSING" in readiness["blockers"]
    assert "LEO_SINGLE_EXPERT_REFERENCE_SET_NOT_LABELED" in readiness["blockers"]
    assert "LEO_SINGLE_EXPERT_EVALUATOR_CONTRACT_NOT_VERSIONED" not in readiness["blockers"]
