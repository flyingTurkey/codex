"""Generate deterministic JSON Schema artifacts from canonical models."""

import json
from pathlib import Path

from pydantic import BaseModel

from srbg_contracts.models import (
    CursorPage,
    LivenessResponse,
    ProblemDetails,
    ReadinessResponse,
    VersionResponse,
)

SCHEMA_MODELS: dict[str, type[BaseModel]] = {
    "cursor-page.schema.json": CursorPage[dict[str, str | int | bool | None]],
    "liveness-response.schema.json": LivenessResponse,
    "problem-details.schema.json": ProblemDetails,
    "readiness-response.schema.json": ReadinessResponse,
    "version-response.schema.json": VersionResponse,
}


def render_schemas() -> dict[str, str]:
    return {
        filename: json.dumps(
            model.model_json_schema(), ensure_ascii=False, indent=2, sort_keys=True
        )
        + "\n"
        for filename, model in SCHEMA_MODELS.items()
    }


def write_schemas(output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for filename, content in render_schemas().items():
        (output_dir / filename).write_text(content, encoding="utf-8", newline="\n")


def main() -> None:
    repository_root = Path(__file__).resolve().parents[4]
    write_schemas(repository_root / "packages/contracts/generated/json-schema")


if __name__ == "__main__":
    main()
