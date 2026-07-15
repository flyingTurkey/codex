import json
from pathlib import Path


def test_v21_evaluation_allows_missing_scores_but_selected_policy_still_requires_them() -> None:
    schema = json.loads(
        Path("docs/codex-kit/assets/validation/publication_evaluation.schema.json").read_text(
            encoding="utf-8"
        )
    )
    gate = json.loads(
        Path("docs/codex-kit/assets/validation/publication_gate.json").read_text(encoding="utf-8")
    )

    assert schema["title"] == "Authoritative Publication Evaluation Context"
    assert "scores" not in schema["properties"]["server"]["required"]
    assert "scores" in schema["properties"]["server"]["properties"]
    assert gate["version"] == "2.1.0"
    assert gate["default_decision"] == "DENY"
    assert gate["selected_feed_rules"]["minimum_server_scores"]
