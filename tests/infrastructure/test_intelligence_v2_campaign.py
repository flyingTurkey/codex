import json
from pathlib import Path

SCRIPT = Path("scripts/intelligence_v2_engineering_campaign.py")
MAKEFILE = Path("Makefile")
ROSTER = Path("docs/codex-kit/assets/validation/civil_engineering_source_campaign_v2.json")


def test_campaign_command_is_explicit_and_resumable() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    makefile = MAKEFILE.read_text(encoding="utf-8")

    for action in ("prepare", "start", "status", "finalize"):
        assert action in source
    assert "intelligence-v2-engineering-campaign:" in makefile
    assert '--action "$(ACTION)"' in makefile
    assert '--campaign-id "$(CAMPAIGN_ID)"' in makefile
    assert "CAMPAIGN_ID_REQUIRED" in source


def test_campaign_roster_has_twenty_unique_official_origins() -> None:
    roster = json.loads(ROSTER.read_text(encoding="utf-8"))
    sources = roster["sources"]

    assert roster["rule_version"] == "civil-engineering-campaign-v2.0.0"
    assert len(sources) == 20
    assert len({source["institution"] for source in sources}) == 20
    assert len({source["official_origin"] for source in sources}) == 20
    assert all(source["official_origin"].startswith("https://") for source in sources)
    assert all(source["registration_mode"] == "CANDIDATE_ONLY" for source in sources)


def test_campaign_script_never_contains_secret_values_or_forced_go() -> None:
    source = SCRIPT.read_text(encoding="utf-8")

    assert "decision=GO" not in source
    assert "SRBG_AI_API_KEY=" not in source
    assert "HUMAN_OWNER" not in source
    assert "desired_enabled=true" not in source.lower()


def test_restored_campaign_resumes_missing_readiness_instead_of_reporting_success() -> None:
    source = SCRIPT.read_text(encoding="utf-8")

    assert "CAMPAIGN_READINESS_MISSING" in source
    assert "return _existing_readiness_result(campaign_root)" in source


def test_environment_switch_refreshes_migration_image_before_runtime_gates() -> None:
    source = SCRIPT.read_text(encoding="utf-8")

    assert '"build",\n            "migrate",' in source


def test_started_campaign_reasserts_acceptance_environment_when_resumed() -> None:
    source = SCRIPT.read_text(encoding="utf-8")

    assert '"resumed": True' in source
    assert "if transition is None and current.phase is CampaignPhase.STARTED:" in source


def test_campaign_publishes_only_current_hashed_evidence_for_plain_closeout_command() -> None:
    source = SCRIPT.read_text(encoding="utf-8")

    assert "active-campaign.json" in source
    assert "_publish_current_evidence(root, campaign_root)" in source
    assert "target.unlink(missing_ok=True)" in source
    assert '(root / "readiness.json").unlink(missing_ok=True)' in source


def test_source_assessment_uses_the_durable_transport_success_value() -> None:
    source = SCRIPT.read_text(encoding="utf-8")

    assert "transport_status='SUCCEEDED'" in source
    assert "transport_status='SUCCESS'" not in source


def test_source_assessment_writes_the_current_production_admission_semantics() -> None:
    source = SCRIPT.read_text(encoding="utf-8")

    assert "append_production_admission_assessment(" in source
    assert "INSERT INTO source_admission_assessment_v2" not in source


def test_source_sample_cutoff_is_campaign_fixed_and_document_versions_are_unique() -> None:
    source = SCRIPT.read_text(encoding="utf-8")

    assert "cutoff = started_at" in source
    assert "SELECT DISTINCT ON (item.current_document_version_id)" in source
    assert "hard_negative_evaluated=False" in source
    assert '"ended_at": row["assessed_at"].isoformat()' in source
    assert 'metrics.pop("sample_size")' in source
