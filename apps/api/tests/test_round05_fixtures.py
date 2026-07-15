import json
from hashlib import sha256
from pathlib import Path

MANIFEST = Path("apps/api/tests/fixtures/round05/round05-digital-case-manifest.json")


def test_round05_manifest_locks_one_government_and_one_enterprise_case() -> None:
    payload = json.loads(MANIFEST.read_text(encoding="utf-8"))

    assert payload["fixture_policy"] == "SHORT_EXCERPTS_ONLY"
    assert {sample["source_nature"] for sample in payload["samples"]} == {
        "GOVERNMENT_CASE_COLLECTION",
        "ENTERPRISE_SELF_REPORT",
    }
    assert all(
        sample["production_source_state"] == "CANDIDATE_DISABLED" for sample in payload["samples"]
    )


def test_round05_fixture_excerpts_have_stable_hashes_and_evidence_locators() -> None:
    payload = json.loads(MANIFEST.read_text(encoding="utf-8"))

    for sample in payload["samples"]:
        encoded = sample["excerpt"].encode("utf-8")
        assert sha256(encoded).hexdigest() == sample["excerpt_sha256"]
        assert sample["evidence_locator"]["type"] in {"PDF_TEXT", "HTML_PARAGRAPH"}
        assert sample["original_url"].startswith("https://")
