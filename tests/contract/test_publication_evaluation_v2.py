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


def test_v21_evaluation_requires_production_execution_domain() -> None:
    schema = json.loads(
        Path("docs/codex-kit/assets/validation/publication_evaluation.schema.json").read_text(
            encoding="utf-8"
        )
    )
    gate = json.loads(
        Path("docs/codex-kit/assets/validation/publication_gate.json").read_text(encoding="utf-8")
    )
    document = schema["properties"]["server"]["properties"]["document"]

    assert "execution_domain" in document["required"]
    assert document["properties"]["execution_domain"] == {"const": "PRODUCTION"}
    assert any(
        rule.get("code") == "NON_PRODUCTION_EXECUTION_DOMAIN"
        and rule.get("field") == "server.document.execution_domain"
        and rule.get("not_eq") == "PRODUCTION"
        for rule in gate["deny_overrides"]
    )
