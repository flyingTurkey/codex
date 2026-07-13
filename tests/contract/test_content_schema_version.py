import json
from pathlib import Path

import srbg_contracts.models as models


def test_content_schema_version_matches_published_read_model() -> None:
    schema_path = Path("docs/codex-kit/assets/content.schema.json")
    schema = json.loads(schema_path.read_text(encoding="utf-8"))

    assert hasattr(models, "CONTENT_SCHEMA_VERSION")
    assert schema["properties"]["schema_version"]["const"] == models.CONTENT_SCHEMA_VERSION
