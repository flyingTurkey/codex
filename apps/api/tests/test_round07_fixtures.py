import json
from hashlib import sha256
from pathlib import Path

ROOT = Path("apps/api/tests/fixtures/round07")


def test_round07_product_fixtures_are_hashed_and_do_not_download_images() -> None:
    manifest = json.loads((ROOT / "round07-product-manifest.json").read_text(encoding="utf-8"))
    for fixture in manifest["files"]:
        content = (ROOT / fixture["path"]).read_bytes()
        payload = json.loads(content)
        assert sha256(content).hexdigest() == fixture["sha256"]
        assert payload["image_downloaded"] is False
        assert "image_url" not in payload
        assert payload["publishable"] is False
    assert manifest["expected"]["vendor_image_download_count"] == 0


def test_product_sources_remain_candidate_and_disabled() -> None:
    registry = Path("docs/codex-kit/assets/source_registry.csv").read_text(encoding="utf-8")
    for code in ("ENT-007", "ENT-008"):
        line = next(row for row in registry.splitlines() if row.startswith(f"{code},"))
        assert ",CANDIDATE," in line
        assert ",false," in line

