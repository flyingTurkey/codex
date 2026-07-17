import json
from pathlib import Path

import pytest
from srbg_api.source_profile_ai import build_profile_request
from srbg_api.source_profiles import (
    ProfileEvidence,
    ProfileRuleInput,
    build_source_profile,
)

MANIFEST = Path("apps/api/tests/fixtures/source_profiles/manifest.json")


def test_fixed_source_profile_replay_is_offline_and_deterministic() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert manifest["network_io_allowed"] is False
    assert len(manifest["cases"]) == 6
    for case in manifest["cases"]:
        evidence = (
            ProfileEvidence(
                "home", "HOMEPAGE", case["origin"], "a" * 64, case["excerpt"]
            ),
        )
        if case["code"] == "prompt_injection":
            with pytest.raises(PermissionError, match="PROMPT_INJECTION"):
                build_profile_request(evidence)
            continue
        profile = build_source_profile(
            ProfileRuleInput(case["origin"], (), evidence),
            model_output=None,
            partial_reason="FIXTURE_MODEL_DISABLED",
        )
        assert profile.status == "PARTIAL"
        if "expected_authority" in case:
            assert profile.authority_level == case["expected_authority"]
