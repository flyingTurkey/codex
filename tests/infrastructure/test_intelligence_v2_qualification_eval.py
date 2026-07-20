import json
from pathlib import Path

from srbg_api.intelligence_v2.structural_corpus import (
    CORPUS_VERSION,
    STRUCTURAL_REPLAY_CORPUS,
)

from scripts.evaluate_intelligence_v2_qualification import main


def _prediction_payload() -> dict[str, object]:
    return {
        "corpus_version": CORPUS_VERSION,
        "predictions": [
            {
                "case_id": case.case_id,
                "directly_relevant": case.directly_relevant is True,
                "primary_type": case.primary_type.value if case.primary_type else None,
            }
            for case in STRUCTURAL_REPLAY_CORPUS
        ],
    }


def test_cli_report_cannot_authorize_auto_pass_or_claim_owner_gold(
    tmp_path: Path, capsys
) -> None:
    prediction_file = tmp_path / "predictions.json"
    prediction_file.write_text(
        json.dumps(_prediction_payload(), ensure_ascii=False), encoding="utf-8"
    )

    assert main(["--input", str(prediction_file)]) == 0
    report = json.loads(capsys.readouterr().out)

    assert report["corpus_version"] == CORPUS_VERSION
    assert report["label_authority"] == "STRUCTURAL_REPLAY"
    assert report["authorizes_auto_pass"] is False
    assert report["locked_negative_leaks"] == 0


def test_cli_fails_closed_for_missing_predictions(tmp_path: Path, capsys) -> None:
    payload = _prediction_payload()
    predictions = payload["predictions"]
    assert isinstance(predictions, list)
    missing = predictions.pop()
    prediction_file = tmp_path / "incomplete.json"
    prediction_file.write_text(json.dumps(payload), encoding="utf-8")

    assert main(["--input", str(prediction_file)]) == 1
    report = json.loads(capsys.readouterr().out)

    assert report["failed_case_ids"] == [missing["case_id"]]
    assert report["authorizes_auto_pass"] is False
