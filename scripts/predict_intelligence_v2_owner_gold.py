"""Produce independent, private Owner Gold predictions through the production AI worker."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from celery import Celery
from srbg_api.ai_pipeline.content_preparation import AiContentPreparationService
from srbg_api.ai_pipeline.contracts import AiStep, ClassificationOutput
from srbg_api.ai_pipeline.preparation import PreparedDocumentInput
from srbg_api.intelligence_v2.owner_gold_preparation import IndependentPrediction

_ROOT = Path(__file__).resolve().parents[1]


def _controlled_repair_prompt(user_prompt: str, response_schema: dict[str, object]) -> str:
    return (
        user_prompt
        + "\n<controlled_repair>Return valid JSON matching this response schema exactly: "
        + json.dumps(response_schema, ensure_ascii=False, sort_keys=True)
        + " Cross-field domain invariant: TUNNEL_GAS_MONITORING is allowed only when "
        "engineering_objects contains TUNNEL and at least one of HIGHWAY or RAILWAY, "
        "and it must not be used when engineering_objects contains MINING. "
        "Include all schema properties; use an explicit null for nullable fields instead "
        "of omitting them. "
        "All list fields must not contain duplicates. For RELEVANT, core_new_fact and "
        "primary_type are required, at least one engineering_object or equipment_domain "
        "is required, and evidence_locators must be non-empty. For every other "
        "direct_relevance value, primary_type must be null. "
        "If the document cannot satisfy every RELEVANT requirement, use IRRELEVANT and "
        "set primary_type to null; do not invent an object, fact, or locator. "
        "security.prompt_injection_status "
        "must be UNRESOLVED exactly when prompt_injection_detected is true, otherwise NONE."
        "</controlled_repair>"
    )


def _result_requires_controlled_repair(result: dict[str, Any]) -> bool:
    if result.get("status") != "SUCCEEDED":
        return result.get("repairable") is True
    try:
        ClassificationOutput.model_validate(result["response"]["output"])
    except (KeyError, TypeError, ValueError):
        return True
    return False


def _outside_repository(path: Path) -> None:
    if path.resolve().is_relative_to(_ROOT):
        raise ValueError("PRIVATE_OWNER_GOLD_PATH_MUST_BE_OUTSIDE_REPOSITORY")


def _load_existing(path: Path) -> dict[str, dict[str, object]]:
    if not path.exists():
        return {}
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    loaded = {str(row["case_id"]): row for row in rows}
    if len(loaded) != len(rows):
        raise ValueError("DUPLICATE_EXISTING_PREDICTION")
    return loaded


def predict(
    manifest_path: Path,
    output_root: Path,
    *,
    broker_url: str,
    timeout_seconds: float,
) -> int:
    _outside_repository(output_root)
    annotations = output_root / "annotations" / "owner-gold.jsonl"
    if annotations.exists():
        raise ValueError("OWNER_ANNOTATIONS_ALREADY_EXIST")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    prediction_root = output_root / "predictions"
    predictions_path = prediction_root / "qualification-predictions.jsonl"
    restricted_path = prediction_root / "restricted-model-responses.jsonl"
    existing = _load_existing(predictions_path)
    client = Celery("owner-gold-prediction-client", broker=broker_url, backend=broker_url)
    prediction_root.mkdir(parents=True, exist_ok=True)
    for case in manifest["cases"]:
        case_id = str(case["case_id"])
        if case_id in existing:
            if existing[case_id]["content_sha256"] != case["content_sha256"]:
                raise ValueError("EXISTING_PREDICTION_CONTENT_CONFLICT")
            continue
        prepared = PreparedDocumentInput(
            text=str(case["normalized_content"]),
            input_sha256=str(case["content_sha256"]),
            anchors={},
            block_ids=(),
        )
        request = AiContentPreparationService.build_request(AiStep.CLASSIFY, prepared)
        async_result = client.send_task(
            "srbg.ai.generate_attempt", args=[request.model_dump(mode="json")], queue="ai"
        )
        result = async_result.get(timeout=timeout_seconds, disable_sync_subtasks=False)
        attempt_count = 1
        if _result_requires_controlled_repair(result):
            repaired = request.model_copy(
                update={
                    "user_prompt": _controlled_repair_prompt(
                        request.user_prompt, request.response_schema
                    )
                }
            )
            async_result = client.send_task(
                "srbg.ai.generate_attempt",
                args=[repaired.model_dump(mode="json")],
                queue="ai",
            )
            result = async_result.get(timeout=timeout_seconds, disable_sync_subtasks=False)
            attempt_count = 2
        if result.get("status") != "SUCCEEDED":
            raise ValueError(f"OWNER_GOLD_PREDICTION_FAILED:{case_id}:{result.get('error_code')}")
        response = result["response"]
        output = ClassificationOutput.model_validate(response["output"])
        predicted_at = datetime.now(UTC)
        predicted_relevant = output.direct_relevance == "RELEVANT"
        prediction = IndependentPrediction(
            case_id=case_id,
            corpus_version=str(manifest["corpus_version"]),
            content_sha256=str(case["content_sha256"]),
            rule_version=str(manifest["rule_version"]),
            model_id=str(result["runtime_model"]),
            prompt_version=request.prompt_version,
            schema_version="intelligence-v2-owner-gold-2.0.0",
            predicted_at=predicted_at,
            predicted_relevant=predicted_relevant,
            primary_type=output.primary_type if predicted_relevant else None,
            confidence_bps=round(output.confidence * 10_000),
            input_sha256=request.input_sha256,
        )
        public_row = {
            **prediction.__dict__,
            "predicted_at": predicted_at.isoformat(),
        }
        restricted_row = {
            "case_id": case_id,
            "corpus_version": manifest["corpus_version"],
            "rule_version": manifest["rule_version"],
            "model_id": result["runtime_model"],
            "model_profile_version": manifest["model_profile_version"],
            "prompt_version": request.prompt_version,
            "schema_version": request.schema_version,
            "predicted_at": predicted_at.isoformat(),
            "input_sha256": request.input_sha256,
            "physical_attempt_count": attempt_count,
            "response": response,
        }
        with predictions_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(public_row, ensure_ascii=False, sort_keys=True) + "\n")
        with restricted_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(restricted_row, ensure_ascii=False, sort_keys=True) + "\n")
        existing[case_id] = public_row
        print(f"OWNER_GOLD_PREDICTION_PROGRESS:{len(existing)}/40")
    return len(existing)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--broker-url", default="redis://127.0.0.1:6379/0")
    parser.add_argument("--timeout-seconds", type=float, default=60.0)
    args = parser.parse_args(argv)
    count = predict(
        args.manifest,
        args.output_root,
        broker_url=args.broker_url,
        timeout_seconds=args.timeout_seconds,
    )
    print(f"OWNER_GOLD_PREDICTIONS_COMPLETE:{count}")
    return 0 if count == 40 else 1


if __name__ == "__main__":
    raise SystemExit(main())
