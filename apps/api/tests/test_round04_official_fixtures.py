import base64
import json
import re
from hashlib import sha256
from pathlib import Path
from typing import Any

import pymupdf

FIXTURES = Path("apps/api/tests/fixtures/round04")
MANIFEST = FIXTURES / "round04-official-manifest.json"


def _manifest() -> dict[str, Any]:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def _bytes(file_name: str) -> bytes:
    return base64.b64decode((FIXTURES / file_name).read_text(encoding="ascii"), validate=True)


def test_official_artifacts_are_immutable_and_self_contained() -> None:
    manifest = _manifest()

    assert manifest["usage"] == "OFFLINE_TEST_ONLY"
    assert len(manifest["artifacts"]) == 6
    for artifact in manifest["artifacts"]:
        payload = _bytes(artifact["file"])
        assert len(payload) == artifact["byte_length"]
        assert sha256(payload).hexdigest() == artifact["sha256"]
        assert artifact["source_url"].startswith("https://")
        assert artifact["source_code"] in {"GOV-019", "GOV-020", "GOV-021", "GOV-022"}


def test_fixture_lifecycle_preserves_changing_casualty_facts_and_open_rectification() -> None:
    initial = _bytes("initial-report.html.b64").decode("utf-8")
    follow_up = _bytes("follow-up-report.html.b64").decode("utf-8")
    investigation = _bytes("investigation-landing.html.b64").decode("utf-8")
    rectification = _bytes("rectification-evaluation.html.b64").decode("utf-8")

    assert "确认死亡人数24人" in initial and "30人正在医院" in initial
    assert "48 人死亡" in follow_up and "3人需要DNA进一步比对确认" in follow_up
    assert "52人死亡" in investigation and "30人受伤" in investigation
    assert "二、存在问题" in rectification and "仍存在" in rectification


def test_fixture_manifest_locks_the_complete_audited_relation_set() -> None:
    assert set(_manifest()["expected_relations"]) == {
        "FOLLOW_UP",
        "INVESTIGATES",
        "PENALIZES",
        "RECTIFIES",
        "CORRECTS",
    }


def test_formal_pdf_contains_reported_facts_and_formal_cause_basis() -> None:
    document = pymupdf.open(stream=_bytes("investigation-report.pdf.b64"), filetype="pdf")
    normalized = re.sub(r"\s+", "", "".join(page.get_text() for page in document))

    assert document.page_count == 31
    assert "52人死亡" in normalized
    assert "30人受伤" in normalized
    assert "三、灾害发生原因" in normalized
    assert "地下水持续累积" in normalized
