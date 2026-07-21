"""Local, resumable and prediction-blind Owner Gold annotation entry."""

# ruff: noqa: RUF001

from __future__ import annotations

import argparse
import json
from collections import Counter
from dataclasses import asdict, dataclass, fields
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Literal, cast

Bucket = Literal["POSITIVE", "BOUNDARY", "NEGATIVE"]
_ROOT = Path(__file__).resolve().parents[1]
_PRIMARY_TYPES = (
    "DIGITAL_TRANSFORMATION",
    "SAFETY_INTELLIGENCE",
    "INDUSTRY_UPDATE",
)
_ENGINEERING_OBJECTS = (
    "HIGHWAY",
    "RAILWAY",
    "BRIDGE",
    "TUNNEL",
    "BUILDING",
    "MINING",
    "MUNICIPAL",
    "WATER_CONSERVANCY",
    "PORT_WATERWAY",
    "AIRPORT",
    "ENERGY",
)
_RUBRIC_VERSION = "owner-gold-rubric-2.1.0"
_PRODUCTION_CORPUS_VERSION = "owner-gold-2026-07-20.4"
_PREPARATION_CORPUS_VERSION = "owner-gold-2026-07-20.5"


@dataclass(frozen=True)
class OwnerAnswer:
    bucket: Bucket
    expected_relevant: bool
    primary_type: str | None
    engineering_objects: tuple[str, ...]
    specialty_facets: tuple[str, ...]
    equipment_domains: tuple[str, ...]
    evidence_locator: str


_ANSWER_FIELDS = {field.name for field in fields(OwnerAnswer)}


def _cases(pack: dict[str, object]) -> dict[str, dict[str, object]]:
    if (
        pack.get("corpus_version")
        not in {
            "owner-gold-2026-07-20.1",
            "owner-gold-2026-07-20.2",
            "owner-gold-2026-07-20.3",
            "owner-gold-2026-07-20.4",
            _PREPARATION_CORPUS_VERSION,
        }
        or pack.get("schema_version") != "intelligence-v2-owner-gold-blind-pack-1.0.0"
    ):
        raise ValueError("BLIND_PACK_VERSION_INVALID")
    values = pack.get("cases")
    if not isinstance(values, list) or len(values) != 40:
        raise ValueError("BLIND_PACK_CASES_INVALID")
    loaded: dict[str, dict[str, object]] = {}
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
    for value in values:
        if not isinstance(value, dict) or prohibited & set(value):
            raise ValueError("BLIND_PACK_LABEL_LEAK")
        case_id = str(value.get("case_id") or "")
        if not case_id or case_id in loaded:
            raise ValueError("BLIND_PACK_CASE_ID_INVALID")
        loaded[case_id] = value
    return loaded


def _validate_answer(case: dict[str, object], answer: OwnerAnswer) -> None:
    if answer.bucket == "POSITIVE" and not answer.expected_relevant:
        raise ValueError("POSITIVE_MUST_BE_RELEVANT")
    if answer.bucket == "NEGATIVE" and answer.expected_relevant:
        raise ValueError("NEGATIVE_MUST_BE_IRRELEVANT")
    if answer.expected_relevant:
        if answer.primary_type not in _PRIMARY_TYPES or not answer.engineering_objects:
            raise ValueError("RELEVANT_LABEL_REQUIRES_TYPE_AND_OBJECT")
    elif answer.primary_type is not None or answer.engineering_objects:
        raise ValueError("IRRELEVANT_LABEL_CANNOT_ASSIGN_TYPE_OR_OBJECT")
    if any(value not in _ENGINEERING_OBJECTS for value in answer.engineering_objects):
        raise ValueError("ENGINEERING_OBJECT_INVALID")
    if any(value != "TUNNEL_GAS_MONITORING" for value in answer.specialty_facets):
        raise ValueError("SPECIALTY_FACET_INVALID")
    if any(value != "CONSTRUCTION_MACHINERY" for value in answer.equipment_domains):
        raise ValueError("EQUIPMENT_DOMAIN_INVALID")
    if answer.specialty_facets and not (
        "TUNNEL" in answer.engineering_objects
        and bool({"HIGHWAY", "RAILWAY"} & set(answer.engineering_objects))
        and "MINING" not in answer.engineering_objects
    ):
        raise ValueError("TUNNEL_GAS_COMBINATION_INVALID")
    locators = case.get("evidence_locators")
    if not isinstance(locators, list) or answer.evidence_locator not in locators:
        raise ValueError("EVIDENCE_LOCATOR_INVALID")


def _load_draft(path: Path) -> dict[str, dict[str, object]]:
    if not path.exists():
        return {}
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("OWNER_ANNOTATION_DRAFT_INVALID")
    return {str(key): cast(dict[str, object], row) for key, row in value.items()}


def _answer_from_row(row: dict[str, object]) -> OwnerAnswer:
    return OwnerAnswer(
        bucket=cast(Bucket, row["bucket"]),
        expected_relevant=bool(row["expected_relevant"]),
        primary_type=cast(str | None, row["primary_type"]),
        engineering_objects=tuple(cast(list[str] | tuple[str, ...], row["engineering_objects"])),
        specialty_facets=tuple(cast(list[str] | tuple[str, ...], row["specialty_facets"])),
        equipment_domains=tuple(cast(list[str] | tuple[str, ...], row["equipment_domains"])),
        evidence_locator=str(row["evidence_locator"]),
    )


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _write_once(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != content:
            raise ValueError("OWNER_ATTEMPT_APPEND_ONLY_CONFLICT")
        return
    with path.open("xb") as stream:
        stream.write(content)


def _attempt_reason_codes(answers: dict[str, OwnerAnswer]) -> tuple[str, ...]:
    reasons: list[str] = []
    distribution = Counter(answer.bucket for answer in answers.values())
    if distribution != {"POSITIVE": 20, "NEGATIVE": 20}:
        reasons.append("OWNER_GOLD_DISTRIBUTION_INVALID")
    return tuple(reasons)


def seal_no_go_attempt(
    pack: dict[str, object],
    *,
    draft_path: Path,
    corpus_manifest_path: Path,
    attempt_labels_path: Path,
    attempt_manifest_path: Path,
    training_pack_path: Path,
    sealed_at: datetime,
    rubric_version: str,
) -> dict[str, object]:
    """Seal a completed but ineligible Owner attempt without minting Gold evidence."""

    if sealed_at.tzinfo is None:
        raise ValueError("OWNER_ATTEMPT_TIMESTAMP_INVALID")
    cases = _cases(pack)
    draft = _load_draft(draft_path)
    if set(draft) != set(cases) or len(draft) != 40:
        raise ValueError("OWNER_ANNOTATIONS_INCOMPLETE")
    answers = {case_id: _answer_from_row(row) for case_id, row in draft.items()}
    for case_id, answer in answers.items():
        _validate_answer(cases[case_id], answer)
    reason_codes = _attempt_reason_codes(answers)
    if not reason_codes:
        raise ValueError("OWNER_ATTEMPT_IS_ELIGIBLE_FOR_GOLD")

    draft_sha256 = sha256(draft_path.read_bytes()).hexdigest()
    corpus_manifest_file_sha256 = sha256(corpus_manifest_path.read_bytes()).hexdigest()
    prediction_seal_sha256 = str(pack.get("prediction_seal_sha256") or "")
    if len(prediction_seal_sha256) != 64:
        raise ValueError("PREDICTION_SEAL_SHA256_INVALID")
    if attempt_manifest_path.exists():
        existing = cast(
            dict[str, object],
            json.loads(attempt_manifest_path.read_text(encoding="utf-8")),
        )
        if (
            existing.get("draft_sha256") == draft_sha256
            and existing.get("corpus_manifest_file_sha256") == corpus_manifest_file_sha256
            and existing.get("prediction_seal_sha256") == prediction_seal_sha256
        ):
            return existing
        raise ValueError("OWNER_ATTEMPT_ALREADY_SEALED_CONFLICT")

    attempt_rows: list[dict[str, object]] = []
    for case_id in sorted(cases):
        case = cases[case_id]
        source = draft[case_id]
        answer = answers[case_id]
        attempt_rows.append(
            {
                "artifact_kind": "OWNER_ATTEMPT_LABEL",
                "production_calibration_eligible": False,
                "case_id": case_id,
                "corpus_version": pack["corpus_version"],
                "content_sha256": case["content_sha256"],
                "raw_object_sha256": case["raw_object_sha256"],
                "annotator_kind": "HUMAN_OWNER",
                "annotated_at": source.get("annotated_at"),
                "annotation_timestamp_status": (
                    "CAPTURED_PER_CASE"
                    if source.get("annotated_at")
                    else "NOT_CAPTURED_LEGACY_DRAFT"
                ),
                "rubric_version": source.get("rubric_version") or rubric_version,
                **asdict(answer),
            }
        )
    labels_content = (
        "\n".join(json.dumps(row, ensure_ascii=False, sort_keys=True) for row in attempt_rows)
        + "\n"
    ).encode("utf-8")
    attempt_labels_sha256 = sha256(labels_content).hexdigest()

    positive_case_ids = sorted(
        case_id for case_id, answer in answers.items() if answer.bucket == "POSITIVE"
    )
    training = {
        "schema_version": "intelligence-v2-owner-training-replay-1.0.0",
        "artifact_kind": "OWNER_TRAINING_REPLAY",
        "corpus_version": pack["corpus_version"],
        "selection_basis": "KNOWN_OWNER_LABEL",
        "production_calibration_eligible": False,
        "source_draft_sha256": draft_sha256,
        "rubric_version": rubric_version,
        "cases": [
            {
                **cases[case_id],
                "owner_answer": asdict(answers[case_id]),
            }
            for case_id in positive_case_ids
        ],
    }
    training_content = (
        json.dumps(training, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    training_pack_sha256 = sha256(training_content).hexdigest()

    positives = [answer for answer in answers.values() if answer.bucket == "POSITIVE"]
    bucket_counts = dict(sorted(Counter(answer.bucket for answer in answers.values()).items()))
    positive_types = dict(
        sorted(Counter(answer.primary_type for answer in positives if answer.primary_type).items())
    )
    covered_objects = sorted(
        {value for answer in positives for value in answer.engineering_objects}
    )
    manifest: dict[str, object] = {
        "schema_version": "intelligence-v2-owner-attempt-no-go-1.0.0",
        "artifact_kind": "OWNER_GOLD_ATTEMPT",
        "outcome": "NO_GO",
        "production_calibration_eligible": False,
        "corpus_version": pack["corpus_version"],
        "sealed_at": sealed_at.isoformat(),
        "rubric_version": rubric_version,
        "label_count": len(answers),
        "bucket_counts": bucket_counts,
        "positive_primary_type_counts": positive_types,
        "engineering_objects_covered": covered_objects,
        "engineering_object_coverage_count": len(covered_objects),
        "tunnel_gas_coverage": any(
            "TUNNEL_GAS_MONITORING" in answer.specialty_facets
            and "TUNNEL" in answer.engineering_objects
            and bool({"HIGHWAY", "RAILWAY"} & set(answer.engineering_objects))
            for answer in positives
        ),
        "construction_machinery_coverage_count": sum(
            "CONSTRUCTION_MACHINERY" in answer.equipment_domains for answer in positives
        ),
        "reason_codes": list(reason_codes),
        "draft_sha256": draft_sha256,
        "corpus_manifest_file_sha256": corpus_manifest_file_sha256,
        "prediction_seal_sha256": prediction_seal_sha256,
        "attempt_labels_sha256": attempt_labels_sha256,
        "training_pack_sha256": training_pack_sha256,
    }
    manifest["attempt_manifest_sha256"] = sha256(_canonical_json(manifest)).hexdigest()
    manifest_content = (
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    _write_once(attempt_labels_path, labels_content)
    _write_once(training_pack_path, training_content)
    _write_once(attempt_manifest_path, manifest_content)
    return manifest


def save_owner_answer(
    pack: dict[str, object],
    *,
    draft_path: Path,
    case_id: str,
    answer: OwnerAnswer,
    annotated_at: datetime | None = None,
    rubric_version: str = _RUBRIC_VERSION,
) -> None:
    cases = _cases(pack)
    case = cases.get(case_id)
    if case is None:
        raise ValueError("BLIND_PACK_CASE_NOT_FOUND")
    _validate_answer(case, answer)
    recorded_at = annotated_at or datetime.now(UTC)
    if recorded_at.tzinfo is None or not rubric_version.strip():
        raise ValueError("OWNER_ANNOTATION_PROVENANCE_INVALID")
    draft = _load_draft(draft_path)
    draft[case_id] = {
        **asdict(answer),
        "annotated_at": recorded_at.isoformat(),
        "rubric_version": rubric_version,
    }
    draft_path.parent.mkdir(parents=True, exist_ok=True)
    draft_path.write_text(
        json.dumps(draft, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _try_save_owner_answer(
    pack: dict[str, object],
    *,
    draft_path: Path,
    case_id: str,
    answer: OwnerAnswer,
    annotated_at: datetime | None = None,
    rubric_version: str = _RUBRIC_VERSION,
) -> str | None:
    messages = {
        "TUNNEL_GAS_COMBINATION_INVALID": (
            "交通隧道瓦斯监测必须使用 TUNNEL + HIGHWAY/RAILWAY，且不能包含 MINING。"
        ),
        "RELEVANT_LABEL_REQUIRES_TYPE_AND_OBJECT": (
            "相关案例必须选择唯一主类型，并至少填写一个有效工程对象。"
        ),
        "ENGINEERING_OBJECT_INVALID": "工程对象代码无效，请只使用终端列出的英文代码。",
        "EVIDENCE_LOCATOR_INVALID": "证据定位无效，请从本案例列出的编号中选择。",
        "POSITIVE_MUST_BE_RELEVANT": "POSITIVE 必须最终判断为 RELEVANT。",
        "NEGATIVE_MUST_BE_IRRELEVANT": "NEGATIVE 必须最终判断为 IRRELEVANT。",
    }
    try:
        save_owner_answer(
            pack,
            draft_path=draft_path,
            case_id=case_id,
            answer=answer,
            annotated_at=annotated_at,
            rubric_version=rubric_version,
        )
    except ValueError as error:
        code = str(error)
        return messages.get(code, f"输入未通过校验（{code}），请重新标注本案例。")
    return None


def finalize_annotations(
    pack: dict[str, object],
    *,
    draft_path: Path,
    output_path: Path,
    rule_version: str,
    model_id: str,
    prompt_version: str,
    annotated_at: datetime,
) -> None:
    cases = _cases(pack)
    draft = _load_draft(draft_path)
    if set(draft) != set(cases) or len(draft) != 40:
        raise ValueError("OWNER_ANNOTATIONS_INCOMPLETE")
    if output_path.exists():
        raise ValueError("OWNER_ANNOTATIONS_ALREADY_FINALIZED")
    if annotated_at.tzinfo is None:
        raise ValueError("OWNER_ANNOTATION_TIMESTAMP_INVALID")
    answers = {case_id: _answer_from_row(row) for case_id, row in draft.items()}
    for case_id, answer in answers.items():
        _validate_answer(cases[case_id], answer)
    reason_codes = _attempt_reason_codes(answers)
    if reason_codes:
        raise ValueError(reason_codes[0])
    if pack["corpus_version"] not in {
        _PRODUCTION_CORPUS_VERSION,
        _PREPARATION_CORPUS_VERSION,
    }:
        raise ValueError("OWNER_GOLD_CORPUS_VERSION_NOT_PRODUCTION_ELIGIBLE")
    rows: list[str] = []
    for case_id in sorted(cases):
        case = cases[case_id]
        answer = answers[case_id]
        row = {
            "case_id": case_id,
            "bucket": answer.bucket,
            "annotator_kind": "HUMAN_OWNER",
            "content_sha256": case["content_sha256"],
            "raw_object_sha256": case["raw_object_sha256"],
            "annotated_at": str(draft[case_id].get("annotated_at") or annotated_at.isoformat()),
            "corpus_version": pack["corpus_version"],
            "rule_version": rule_version,
            "model_id": model_id,
            "prompt_version": prompt_version,
            "schema_version": "intelligence-v2-owner-gold-2.0.0",
            "evidence_locator": answer.evidence_locator,
            "expected_relevant": answer.expected_relevant,
            "primary_type": answer.primary_type,
            "engineering_objects": list(answer.engineering_objects),
            "specialty_facets": list(answer.specialty_facets),
            "equipment_domains": list(answer.equipment_domains),
            "locked_negative": answer.bucket == "NEGATIVE",
        }
        rows.append(json.dumps(row, ensure_ascii=False, sort_keys=True))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(rows) + "\n", encoding="utf-8")


def _outside_repository(path: Path) -> None:
    if path.resolve().is_relative_to(_ROOT):
        raise ValueError("PRIVATE_OWNER_GOLD_PATH_MUST_BE_OUTSIDE_REPOSITORY")


def _ask_choice(prompt: str, values: tuple[str, ...]) -> str:
    while True:
        print(prompt)
        for index, value in enumerate(values, 1):
            print(f"  {index}. {value}")
        raw = input("> ").strip()
        if raw.lower() == "q":
            raise KeyboardInterrupt
        if raw.isdigit() and 1 <= int(raw) <= len(values):
            return values[int(raw) - 1]


def _ask_evidence_locator(case: dict[str, object]) -> str:
    blocks = [line.strip() for line in str(case["normalized_content"]).splitlines() if line.strip()]
    locators = tuple(str(value) for value in cast(list[object], case["evidence_locators"]))
    if len(blocks) != len(locators):
        raise ValueError("BLIND_PACK_EVIDENCE_BLOCK_MISMATCH")
    while True:
        print("请选择最能支持判断的证据定位：")
        for index, (locator, block) in enumerate(zip(locators, blocks, strict=True), 1):
            excerpt = " ".join(block.split())
            if len(excerpt) > 240:
                excerpt = excerpt[:237] + "..."
            print(f"  {index}. {excerpt}")
            print(f"     locator: {locator}")
        raw = input("> ").strip()
        if raw.lower() == "q":
            raise KeyboardInterrupt
        if raw.isdigit() and 1 <= int(raw) <= len(locators):
            return locators[int(raw) - 1]


def _interactive_answer(case: dict[str, object]) -> OwnerAnswer:
    print("\n" + "=" * 72)
    print(f"Case: {case['case_id']}\n标题: {case['title']}\n来源: {case['source_url']}")
    print("\n冻结正文：\n" + str(case["normalized_content"]))
    bucket = cast(Bucket, _ask_choice("请选择人工篮子：", ("POSITIVE", "NEGATIVE")))
    if bucket == "POSITIVE":
        relevant = True
    elif bucket == "NEGATIVE":
        relevant = False
    primary_type: str | None = None
    objects: tuple[str, ...] = ()
    specialty: tuple[str, ...] = ()
    equipment: tuple[str, ...] = ()
    if relevant:
        primary_type = _ask_choice("请选择唯一主类型：", _PRIMARY_TYPES)
        print("工程对象代码：" + ", ".join(_ENGINEERING_OBJECTS))
        entered_objects = input("工程对象（逗号分隔）> ").split(",")
        objects = tuple(
            dict.fromkeys(value.strip().upper() for value in entered_objects if value.strip())
        )
        if _ask_choice("是否为交通隧道瓦斯监测？", ("NO", "YES")) == "YES":
            specialty = ("TUNNEL_GAS_MONITORING",)
        if _ask_choice("是否为直接服务工程生命周期的施工机械？", ("NO", "YES")) == "YES":
            equipment = ("CONSTRUCTION_MACHINERY",)
    locator = _ask_evidence_locator(case)
    return OwnerAnswer(
        bucket=bucket,
        expected_relevant=relevant,
        primary_type=primary_type,
        engineering_objects=objects,
        specialty_facets=specialty,
        equipment_domains=equipment,
        evidence_locator=locator,
    )


def _print_rubric() -> None:
    print("\nOwner Gold rubric owner-gold-rubric-2.1.0")
    print("- 本版本只使用 POSITIVE 与 NEGATIVE；BOUNDARY 配额为 0。")
    print("- 标题含“通知”不自动判负：判断正文是否包含新的工程生命周期事实。")
    print("- 仅征集、申报、报送、转发、会议或名单公示，且无工程新事实时排除。")
    print("- 纯诊疗、药品和健康科普排除；医院施工、改扩建、安全或建筑数字化按工程中心事实判断。")
    print("- 任何时候输入 q 可安全暂停。\n")


def _review_saved_answers(
    pack: dict[str, object],
    *,
    draft_path: Path,
    case_id: str | None,
) -> None:
    cases = _cases(pack)
    draft = _load_draft(draft_path)
    selected_ids = [case_id] if case_id else list(cases)
    if case_id and case_id not in cases:
        raise ValueError("BLIND_PACK_CASE_NOT_FOUND")
    for selected_id in selected_ids:
        case = cases[selected_id]
        row = draft.get(selected_id)
        print("\n" + "=" * 72)
        print(f"Case: {selected_id}\n标题: {case['title']}\n来源: {case['source_url']}")
        print("\n冻结正文：\n" + str(case["normalized_content"]))
        if row is None:
            print("\n状态：尚未标注")
        else:
            answer = _answer_from_row(row)
            print(
                "\n已保存判断："
                f"bucket={answer.bucket}, relevant={answer.expected_relevant}, "
                f"primary_type={answer.primary_type}, "
                f"objects={','.join(answer.engineering_objects) or '-'}"
            )
            print(f"标注时间：{row.get('annotated_at') or '旧版草稿未逐条记录'}")
            print(f"rubric：{row.get('rubric_version') or '旧版草稿未逐条记录'}")


def _run_training_replay(path: Path) -> None:
    value = json.loads(path.read_text(encoding="utf-8"))
    if (
        value.get("artifact_kind") != "OWNER_TRAINING_REPLAY"
        or value.get("selection_basis") != "KNOWN_OWNER_LABEL"
        or value.get("production_calibration_eligible") is not False
    ):
        raise ValueError("OWNER_TRAINING_REPLAY_INVALID")
    print("培训回放模式：已知 Owner 正例，仅用于熟悉规则，绝不计入生产校准。")
    cases = value.get("cases")
    if not isinstance(cases, list):
        raise ValueError("OWNER_TRAINING_REPLAY_INVALID")
    for index, case in enumerate(cases, 1):
        if not isinstance(case, dict) or not isinstance(case.get("owner_answer"), dict):
            raise ValueError("OWNER_TRAINING_REPLAY_INVALID")
        print("\n" + "=" * 72)
        print(f"[{index}/{len(cases)}] {case.get('title')}\n来源: {case.get('source_url')}")
        print("\n冻结正文：\n" + str(case.get("normalized_content") or ""))
        answer = cast(dict[str, object], case["owner_answer"])
        print(
            "\nOwner 已知判断："
            f"{answer.get('bucket')} / {answer.get('primary_type')} / "
            f"{answer.get('engineering_objects')}"
        )
        if index < len(cases):
            raw = input("按 Enter 查看下一条，输入 q 退出 > ").strip().lower()
            if raw == "q":
                return


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pack", type=Path)
    parser.add_argument("--draft", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--rule-version", default="intelligence-v2-qualification-1.0.0")
    parser.add_argument("--model-id", default="deepseek-v4-flash")
    parser.add_argument("--prompt-version", default="ai01-classify-v1")
    parser.add_argument("--rubric-version", default=_RUBRIC_VERSION)
    parser.add_argument("--finalize", action="store_true")
    parser.add_argument("--finalize-no-go", action="store_true")
    parser.add_argument("--review", choices=("all", "case"))
    parser.add_argument("--case-id")
    parser.add_argument("--training-replay", type=Path)
    args = parser.parse_args()
    if args.training_replay is not None:
        _outside_repository(args.training_replay)
        _print_rubric()
        _run_training_replay(args.training_replay)
        return 0
    if args.pack is None or args.draft is None or args.output is None:
        parser.error("--pack、--draft 和 --output 在正式盲标/复核/封存模式下均为必填")
    _outside_repository(args.pack)
    _outside_repository(args.draft)
    _outside_repository(args.output)
    pack = json.loads(args.pack.read_text(encoding="utf-8"))
    if pack.get("corpus_version") not in {
        _PRODUCTION_CORPUS_VERSION,
        _PREPARATION_CORPUS_VERSION,
    }:
        raise ValueError("OWNER_GOLD_BLIND_PACK_RETIRED")
    _print_rubric()
    if args.review:
        if args.review == "case" and not args.case_id:
            parser.error("--review case 必须同时提供 --case-id")
        _review_saved_answers(
            pack,
            draft_path=args.draft,
            case_id=args.case_id if args.review == "case" else None,
        )
        return 0
    if args.finalize or args.finalize_no_go:
        private_root = args.pack.resolve().parent.parent
        now = datetime.now(UTC)
        cases = _cases(pack)
        draft = _load_draft(args.draft)
        if set(draft) != set(cases) or len(draft) != 40:
            raise ValueError("OWNER_ANNOTATIONS_INCOMPLETE")
        answers = {case_id: _answer_from_row(row) for case_id, row in draft.items()}
        reason_codes = _attempt_reason_codes(answers)
        if reason_codes or args.finalize_no_go:
            manifest = seal_no_go_attempt(
                pack,
                draft_path=args.draft,
                corpus_manifest_path=private_root / "corpus" / "corpus-manifest.json",
                attempt_labels_path=private_root / "attempts" / "owner-attempt-labels.jsonl",
                attempt_manifest_path=private_root / "attempts" / "owner-attempt-no-go.json",
                training_pack_path=private_root / "training" / "owner-positive-replay.json",
                sealed_at=now,
                rubric_version=args.rubric_version,
            )
            print(
                "OWNER_GOLD_ATTEMPT_NO_GO:"
                f"{private_root / 'attempts' / 'owner-attempt-no-go.json'}:"
                f"{','.join(cast(list[str], manifest['reason_codes']))}"
            )
            return 0
        finalize_annotations(
            pack,
            draft_path=args.draft,
            output_path=args.output,
            rule_version=args.rule_version,
            model_id=args.model_id,
            prompt_version=args.prompt_version,
            annotated_at=now,
        )
        print(f"OWNER_GOLD_FINALIZED:{args.output}")
        return 0
    cases = _cases(pack)
    while True:
        draft = _load_draft(args.draft)
        pending = [case_id for case_id in cases if case_id not in draft]
        print(f"Owner Gold progress: {len(draft)}/40")
        if not pending:
            print("40/40 已完成。请检查后使用 --finalize 显式封存。")
            return 0
        case_id = pending[0]
        try:
            answer = _interactive_answer(cases[case_id])
            if _ask_choice("确认保存本条人工判断？", ("YES", "NO")) == "YES":
                error = _try_save_owner_answer(
                    pack,
                    draft_path=args.draft,
                    case_id=case_id,
                    answer=answer,
                )
                if error is not None:
                    print(f"本条未保存：{error}")
        except KeyboardInterrupt:
            print("已暂停；再次运行同一命令将从下一条继续。")
            return 0


if __name__ == "__main__":
    raise SystemExit(main())
