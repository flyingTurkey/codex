import json
from pathlib import Path

ASSET = Path("docs/codex-kit/assets/validation/round17_candidate_roster.json")


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
