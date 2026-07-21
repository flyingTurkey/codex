import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from srbg_api.intelligence_v2.owner_gold_preparation import (
    FrozenCorpusCase,
    IndependentPrediction,
    build_blind_pack,
    seal_predictions,
)

from scripts.annotate_intelligence_v2_owner_gold import (
    OwnerAnswer,
    _ask_evidence_locator,
    _try_save_owner_answer,
    finalize_annotations,
    save_owner_answer,
    seal_no_go_attempt,
)
from scripts.predict_intelligence_v2_owner_gold import (
    _controlled_repair_prompt,
    _result_requires_controlled_repair,
)

CORPUS_VERSION = "owner-gold-2026-07-20.5"
RULE_VERSION = "intelligence-v2-qualification-1.0.0"
MODEL_ID = "deepseek-v4-flash"
PROMPT_VERSION = "ai01-classify-v1"
SCHEMA_VERSION = "classify-output-v1"
PREDICTED_AT = datetime(2026, 7, 20, 2, tzinfo=UTC)


def test_controlled_repair_prompt_carries_cross_field_domain_invariants() -> None:
    prompt = _controlled_repair_prompt(
        "classify this document",
        {"type": "object", "required": ["specialty_facets"]},
    )

    assert "TUNNEL_GAS_MONITORING" in prompt
    assert "TUNNEL" in prompt
    assert "HIGHWAY" in prompt
    assert "RAILWAY" in prompt
    assert "MINING" in prompt
    assert '"specialty_facets"' in prompt
    assert "must not contain duplicates" in prompt
    assert "primary_type must be null" in prompt
    assert "all schema properties" in prompt
    assert "explicit null" in prompt
    assert "cannot satisfy every RELEVANT requirement" in prompt
    assert "IRRELEVANT" in prompt
    assert "prompt_injection_status" in prompt


def test_successful_gateway_result_with_invalid_local_contract_requires_repair() -> None:
    assert _result_requires_controlled_repair(
        {
            "status": "SUCCEEDED",
            "response": {
                "output": {
                    "direct_relevance": "IRRELEVANT",
                }
            },
        }
    )


def test_evidence_selector_displays_the_excerpt_beside_each_locator(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    case = {
        "normalized_content": "第一段项目正文\n\n第二段安全要求正文",
        "evidence_locators": [
            "html:text-block:10:sha256:" + "a" * 64,
            "html:text-block:20:sha256:" + "b" * 64,
        ],
    }
    monkeypatch.setattr("builtins.input", lambda _prompt: "2")

    selected = _ask_evidence_locator(case)

    output = capsys.readouterr().out
    assert "第一段项目正文" in output
    assert "第二段安全要求正文" in output
    assert "html:text-block:20" in output
    assert selected == case["evidence_locators"][1]


def test_invalid_tunnel_gas_combination_is_not_saved_and_returns_a_retry_message(
    tmp_path: Path,
) -> None:
    cases, predictions = _corpus()
    seal = seal_predictions(
        cases,
        predictions,
        corpus_version=CORPUS_VERSION,
        rule_version=RULE_VERSION,
        model_id=MODEL_ID,
        prompt_version=PROMPT_VERSION,
        schema_version=SCHEMA_VERSION,
        sealed_at=PREDICTED_AT + timedelta(minutes=1),
        annotations_path=tmp_path / "owner-gold.jsonl",
    )
    pack = build_blind_pack(cases, seal=seal)
    case = pack["cases"][0]
    assert isinstance(case, dict)
    draft_path = tmp_path / "draft.json"

    error = _try_save_owner_answer(
        pack,
        draft_path=draft_path,
        case_id=str(case["case_id"]),
        answer=OwnerAnswer(
            bucket="POSITIVE",
            expected_relevant=True,
            primary_type="SAFETY_INTELLIGENCE",
            engineering_objects=("MINING",),
            specialty_facets=("TUNNEL_GAS_MONITORING",),
            equipment_domains=(),
            evidence_locator=str(case["evidence_locators"][0]),
        ),
    )

    assert "TUNNEL + HIGHWAY/RAILWAY" in error
    assert not draft_path.exists()


def _corpus() -> tuple[list[FrozenCorpusCase], list[IndependentPrediction]]:
    cases: list[FrozenCorpusCase] = []
    predictions: list[IndependentPrediction] = []
    types = ["DIGITAL_TRANSFORMATION"] * 7 + ["SAFETY_INTELLIGENCE"] * 7 + ["INDUSTRY_UPDATE"] * 6
    strata = (
        [("POSITIVE", value) for value in types]
        + [("NEGATIVE", None)] * 20
    )
    for index, (bucket, primary_type) in enumerate(strata):
        case_id = f"019f7e60-6728-7{index:03x}-a053-c69617d6d5b3"
        content_hash = f"{index + 1:064x}"
        cases.append(
            FrozenCorpusCase(
                case_id=case_id,
                corpus_version=CORPUS_VERSION,
                sampling_stratum=bucket,
                sampling_primary_type=primary_type,
                title=f"公开材料 {index + 1}",
                source_url=f"https://example.gov.cn/{index + 1}",
                rights_basis="PUBLIC_OFFICIAL_SOURCE_PRIVATE_RESEARCH",
                retrieved_at=PREDICTED_AT - timedelta(hours=1),
                raw_object_path=f"raw/{case_id}.html",
                raw_object_sha256=f"{index + 1001:064x}",
                normalized_content=f"[{index + 1}] 有证据定位的公开内容",
                content_sha256=content_hash,
                evidence_locators=(f"html:p:{index + 1}",),
            )
        )
        predictions.append(
            IndependentPrediction(
                case_id=case_id,
                corpus_version=CORPUS_VERSION,
                content_sha256=content_hash,
                rule_version=RULE_VERSION,
                model_id=MODEL_ID,
                prompt_version=PROMPT_VERSION,
                schema_version=SCHEMA_VERSION,
                predicted_at=PREDICTED_AT,
                predicted_relevant=bucket == "POSITIVE",
                primary_type=primary_type,
                confidence_bps=9300,
                input_sha256=content_hash,
            )
        )
    return cases, predictions


def test_predictions_are_sealed_before_a_prediction_free_blind_pack(tmp_path: Path) -> None:
    cases, predictions = _corpus()

    seal = seal_predictions(
        cases,
        predictions,
        corpus_version=CORPUS_VERSION,
        rule_version=RULE_VERSION,
        model_id=MODEL_ID,
        prompt_version=PROMPT_VERSION,
        schema_version=SCHEMA_VERSION,
        sealed_at=PREDICTED_AT + timedelta(minutes=1),
        annotations_path=tmp_path / "annotations" / "owner-gold.jsonl",
    )
    pack = build_blind_pack(cases, seal=seal)

    assert seal.case_count == 40
    assert len(pack["cases"]) == 40
    assert pack["prediction_seal_sha256"] == seal.seal_sha256
    prohibited = {
        "sampling_stratum",
        "sampling_primary_type",
        "predicted_relevant",
        "primary_type",
        "confidence_bps",
        "model_id",
        "prompt_version",
        "recommended_label",
    }
    assert all(not (prohibited & set(row)) for row in pack["cases"])


def test_prediction_seal_rejects_existing_owner_annotations(tmp_path: Path) -> None:
    cases, predictions = _corpus()
    annotations = tmp_path / "owner-gold.jsonl"
    annotations.write_text("{}\n", encoding="utf-8")

    with pytest.raises(ValueError, match="OWNER_ANNOTATIONS_ALREADY_EXIST"):
        seal_predictions(
            cases,
            predictions,
            corpus_version=CORPUS_VERSION,
            rule_version=RULE_VERSION,
            model_id=MODEL_ID,
            prompt_version=PROMPT_VERSION,
            schema_version=SCHEMA_VERSION,
            sealed_at=PREDICTED_AT + timedelta(minutes=1),
            annotations_path=annotations,
        )


def test_prediction_seal_rejects_a_prediction_after_seal_time(tmp_path: Path) -> None:
    cases, predictions = _corpus()
    predictions[0] = IndependentPrediction(
        **{
            **predictions[0].__dict__,
            "predicted_at": PREDICTED_AT + timedelta(minutes=2),
        }
    )

    with pytest.raises(ValueError, match="PREDICTION_TIMESTAMP_INVALID"):
        seal_predictions(
            cases,
            predictions,
            corpus_version=CORPUS_VERSION,
            rule_version=RULE_VERSION,
            model_id=MODEL_ID,
            prompt_version=PROMPT_VERSION,
            schema_version=SCHEMA_VERSION,
            sealed_at=PREDICTED_AT + timedelta(minutes=1),
            annotations_path=tmp_path / "owner-gold.jsonl",
        )


def test_owner_annotation_draft_resumes_and_finalizes_only_at_40_of_40(
    tmp_path: Path,
) -> None:
    cases, predictions = _corpus()
    seal = seal_predictions(
        cases,
        predictions,
        corpus_version=CORPUS_VERSION,
        rule_version=RULE_VERSION,
        model_id=MODEL_ID,
        prompt_version=PROMPT_VERSION,
        schema_version=SCHEMA_VERSION,
        sealed_at=PREDICTED_AT + timedelta(minutes=1),
        annotations_path=tmp_path / "owner-gold.jsonl",
    )
    pack = build_blind_pack(cases, seal=seal)
    draft_path = tmp_path / "annotations" / "draft.json"
    output_path = tmp_path / "annotations" / "owner-gold.jsonl"

    first = pack["cases"][0]
    assert isinstance(first, dict)
    save_owner_answer(
        pack,
        draft_path=draft_path,
        case_id=str(first["case_id"]),
        annotated_at=PREDICTED_AT + timedelta(minutes=2),
        rubric_version="owner-gold-rubric-2.0.0",
        answer=OwnerAnswer(
            bucket="NEGATIVE",
            expected_relevant=False,
            primary_type=None,
            engineering_objects=(),
            specialty_facets=(),
            equipment_domains=(),
            evidence_locator=str(first["evidence_locators"][0]),
        ),
    )

    saved_draft = json.loads(draft_path.read_text(encoding="utf-8"))
    saved = saved_draft[str(first["case_id"])]
    assert saved["annotated_at"] == (PREDICTED_AT + timedelta(minutes=2)).isoformat()
    assert saved["rubric_version"] == "owner-gold-rubric-2.0.0"

    with pytest.raises(ValueError, match="OWNER_ANNOTATIONS_INCOMPLETE"):
        finalize_annotations(
            pack,
            draft_path=draft_path,
            output_path=output_path,
            rule_version=RULE_VERSION,
            model_id=MODEL_ID,
            prompt_version=PROMPT_VERSION,
            annotated_at=PREDICTED_AT + timedelta(hours=1),
        )
    assert not output_path.exists()


def _write_invalid_owner_attempt(pack: dict[str, object], draft_path: Path) -> None:
    cases = pack["cases"]
    assert isinstance(cases, list)
    object_codes = [
        "HIGHWAY",
        "RAILWAY",
        "BRIDGE",
        "TUNNEL",
        "BUILDING",
        "MINING",
        "MUNICIPAL",
        "WATER_CONSERVANCY",
        "PORT_WATERWAY",
    ]
    draft: dict[str, object] = {}
    for index, case in enumerate(cases):
        assert isinstance(case, dict)
        if index < 15:
            bucket = "POSITIVE"
            relevant = True
            primary_type = "DIGITAL_TRANSFORMATION" if index < 7 else "SAFETY_INTELLIGENCE"
            objects = [object_codes[index % len(object_codes)]]
        elif index < 18:
            bucket = "BOUNDARY"
            relevant = False
            primary_type = None
            objects = []
        else:
            bucket = "NEGATIVE"
            relevant = False
            primary_type = None
            objects = []
        draft[str(case["case_id"])] = {
            "bucket": bucket,
            "expected_relevant": relevant,
            "primary_type": primary_type,
            "engineering_objects": objects,
            "specialty_facets": [],
            "equipment_domains": [],
            "evidence_locator": case["evidence_locators"][0],
        }
    draft_path.parent.mkdir(parents=True, exist_ok=True)
    draft_path.write_text(
        json.dumps(draft, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )


def test_invalid_owner_attempt_is_sealed_no_go_without_production_gold(
    tmp_path: Path,
) -> None:
    cases, predictions = _corpus()
    seal = seal_predictions(
        cases,
        predictions,
        corpus_version=CORPUS_VERSION,
        rule_version=RULE_VERSION,
        model_id=MODEL_ID,
        prompt_version=PROMPT_VERSION,
        schema_version=SCHEMA_VERSION,
        sealed_at=PREDICTED_AT + timedelta(minutes=1),
        annotations_path=tmp_path / "annotations" / "owner-gold.jsonl",
    )
    pack = build_blind_pack(cases, seal=seal)
    draft_path = tmp_path / "annotations" / "owner-gold-draft.json"
    corpus_manifest_path = tmp_path / "corpus" / "corpus-manifest.json"
    attempt_labels_path = tmp_path / "attempts" / "owner-attempt-labels.jsonl"
    attempt_manifest_path = tmp_path / "attempts" / "owner-attempt-no-go.json"
    training_pack_path = tmp_path / "training" / "owner-positive-replay.json"
    _write_invalid_owner_attempt(pack, draft_path)
    corpus_manifest_path.parent.mkdir(parents=True)
    corpus_manifest_path.write_text('{"frozen":true}\n', encoding="utf-8")

    manifest = seal_no_go_attempt(
        pack,
        draft_path=draft_path,
        corpus_manifest_path=corpus_manifest_path,
        attempt_labels_path=attempt_labels_path,
        attempt_manifest_path=attempt_manifest_path,
        training_pack_path=training_pack_path,
        sealed_at=PREDICTED_AT + timedelta(hours=2),
        rubric_version="owner-gold-rubric-2.0.0",
    )

    assert manifest["outcome"] == "NO_GO"
    assert manifest["production_calibration_eligible"] is False
    assert manifest["bucket_counts"] == {
        "BOUNDARY": 3,
        "NEGATIVE": 22,
        "POSITIVE": 15,
    }
    assert manifest["positive_primary_type_counts"] == {
        "DIGITAL_TRANSFORMATION": 7,
        "SAFETY_INTELLIGENCE": 8,
    }
    assert manifest["engineering_object_coverage_count"] == 9
    assert manifest["tunnel_gas_coverage"] is False
    assert manifest["construction_machinery_coverage_count"] == 0
    assert "OWNER_GOLD_DISTRIBUTION_INVALID" in manifest["reason_codes"]
    assert attempt_labels_path.read_text(encoding="utf-8").count("\n") == 40
    training = json.loads(training_pack_path.read_text(encoding="utf-8"))
    assert training["artifact_kind"] == "OWNER_TRAINING_REPLAY"
    assert training["selection_basis"] == "KNOWN_OWNER_LABEL"
    assert training["production_calibration_eligible"] is False
    assert len(training["cases"]) == 15
    assert not (tmp_path / "annotations" / "owner-gold.jsonl").exists()


def test_no_go_attempt_seal_is_idempotent_but_rejects_changed_draft(tmp_path: Path) -> None:
    cases, predictions = _corpus()
    seal = seal_predictions(
        cases,
        predictions,
        corpus_version=CORPUS_VERSION,
        rule_version=RULE_VERSION,
        model_id=MODEL_ID,
        prompt_version=PROMPT_VERSION,
        schema_version=SCHEMA_VERSION,
        sealed_at=PREDICTED_AT + timedelta(minutes=1),
        annotations_path=tmp_path / "owner-gold.jsonl",
    )
    pack = build_blind_pack(cases, seal=seal)
    draft_path = tmp_path / "draft.json"
    corpus_manifest_path = tmp_path / "corpus.json"
    attempt_labels_path = tmp_path / "attempt-labels.jsonl"
    attempt_manifest_path = tmp_path / "attempt-no-go.json"
    training_pack_path = tmp_path / "training.json"
    _write_invalid_owner_attempt(pack, draft_path)
    corpus_manifest_path.write_text("{}\n", encoding="utf-8")
    kwargs = {
        "draft_path": draft_path,
        "corpus_manifest_path": corpus_manifest_path,
        "attempt_labels_path": attempt_labels_path,
        "attempt_manifest_path": attempt_manifest_path,
        "training_pack_path": training_pack_path,
        "sealed_at": PREDICTED_AT + timedelta(hours=2),
        "rubric_version": "owner-gold-rubric-2.0.0",
    }

    first = seal_no_go_attempt(pack, **kwargs)
    second = seal_no_go_attempt(pack, **kwargs)
    assert second == first

    draft_path.write_text(draft_path.read_text(encoding="utf-8") + " ", encoding="utf-8")
    with pytest.raises(ValueError, match="OWNER_ATTEMPT_ALREADY_SEALED_CONFLICT"):
        seal_no_go_attempt(pack, **kwargs)
