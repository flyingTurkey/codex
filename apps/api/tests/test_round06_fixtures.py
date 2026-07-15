import json
from hashlib import sha256
from pathlib import Path

from srbg_api.papers.domain import normalize_doi

ROOT = Path("apps/api/tests/fixtures/round06")


def test_round06_fixed_responses_are_hashed_and_contain_no_abstract_or_fulltext() -> None:
    manifest = json.loads((ROOT / "round06-paper-manifest.json").read_text(encoding="utf-8"))
    for fixture in manifest["files"]:
        content = (ROOT / fixture["path"]).read_bytes()
        assert sha256(content).hexdigest() == fixture["sha256"]
        assert b'"abstract"' not in content
        assert b'"fulltext"' not in content
    assert manifest["expected"]["fulltext_object_count"] == 0


def test_openalex_and_crossref_fixture_resolve_to_one_canonical_doi() -> None:
    openalex = json.loads((ROOT / "openalex-page1.json").read_text(encoding="utf-8"))
    crossref = json.loads((ROOT / "crossref-work.json").read_text(encoding="utf-8"))
    dois = {
        normalize_doi(openalex["results"][0]["doi"]),
        normalize_doi(crossref["message"]["DOI"]),
    }
    assert dois == {"10.1000/bridge.2025.1"}


def test_live_academic_sources_remain_candidate_and_disabled() -> None:
    registry = Path("docs/codex-kit/assets/source_registry.csv").read_text(encoding="utf-8")
    for code in ("RES-004", "RES-007", "RES-008"):
        line = next(row for row in registry.splitlines() if row.startswith(f"{code},"))
        assert ",CANDIDATE," in line
        assert ",false," in line
    assert "知网" in registry and "licensed_api_or_manual" in registry
    assert "万方" in registry
