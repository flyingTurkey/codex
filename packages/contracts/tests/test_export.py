import json
from pathlib import Path

import srbg_contracts.export as contract_export


def test_exported_json_schemas_are_deterministic(tmp_path: Path) -> None:
    assert hasattr(contract_export, "write_schemas")

    contract_export.write_schemas(tmp_path)

    expected_names = {
        "cursor-page.schema.json",
        "liveness-response.schema.json",
        "problem-details.schema.json",
        "readiness-response.schema.json",
        "version-response.schema.json",
    }
    assert {path.name for path in tmp_path.glob("*.json")} == expected_names
    version_schema = json.loads((tmp_path / "version-response.schema.json").read_text())
    assert version_schema["properties"]["api_version"]["const"] == "v1"
    assert version_schema["properties"]["content_schema_version"]["const"] == "1.0.0"


def test_committed_schemas_match_canonical_models(tmp_path: Path) -> None:
    assert hasattr(contract_export, "write_schemas")

    contract_export.write_schemas(tmp_path)
    generated_dir = Path("packages/contracts/generated/json-schema")

    assert generated_dir.is_dir()
    for generated in sorted(tmp_path.glob("*.json")):
        assert (generated_dir / generated.name).read_text(encoding="utf-8") == generated.read_text(
            encoding="utf-8"
        )


def test_generated_types_expose_health_and_version_contracts() -> None:
    types_path = Path("packages/contracts/generated/types/index.d.ts")

    assert types_path.is_file()
    generated_types = types_path.read_text(encoding="utf-8")
    assert "export interface LivenessResponse" in generated_types
    assert "export interface ReadinessResponse" in generated_types
    assert "export interface VersionResponse" in generated_types
