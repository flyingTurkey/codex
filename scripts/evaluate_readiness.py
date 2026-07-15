"""Evaluate versioned gold manifests and validate CI-owned readiness evidence."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[1]
QUALITY_GATES = ROOT / "docs/codex-kit/assets/validation/quality_gates.json"
READINESS_SCHEMA = ROOT / "docs/codex-kit/assets/validation/readiness_evidence.schema.json"


def canonical_json(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def manifest_sha256(value: dict[str, Any]) -> str:
    payload = dict(value)
    payload.pop("manifest_sha256", None)
    return sha256(canonical_json(payload)).hexdigest()


def evaluate_gold_manifest(path: Path) -> dict[str, Any]:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    thresholds = json.loads(QUALITY_GATES.read_text(encoding="utf-8"))["gold_set_minimums"]
    counts = {name: len(manifest.get(name, [])) for name in thresholds}
    checks = {
        name: {"actual": counts[name], "minimum": minimum, "passed": counts[name] >= minimum}
        for name, minimum in thresholds.items()
    }
    passed = all(check["passed"] for check in checks.values())
    return {
        "version": manifest.get("version"),
        "sha256": sha256(path.read_bytes()).hexdigest(),
        "counts": counts,
        "checks": checks,
        "passed": passed,
        "decision": "INTERNAL_PILOT_READY" if passed else "BLOCKED",
    }


def validate_readiness(path: Path) -> None:
    schema = json.loads(READINESS_SCHEMA.read_text(encoding="utf-8"))
    evidence = json.loads(path.read_text(encoding="utf-8"))
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(evidence)
    if evidence["manifest_sha256"] != manifest_sha256(evidence):
        raise ValueError("readiness manifest SHA-256 does not match canonical content")
    started_at = datetime.fromisoformat(evidence["window"]["started_at"].replace("Z", "+00:00"))
    ended_at = datetime.fromisoformat(evidence["window"]["ended_at"].replace("Z", "+00:00"))
    if ended_at < started_at:
        raise ValueError("readiness window ends before it starts")
    policy_sha256 = sha256(QUALITY_GATES.read_bytes()).hexdigest()
    gold_path = ROOT / "tests/gold/v1/manifest.json"
    gold_sha256 = sha256(gold_path.read_bytes()).hexdigest()
    for claim in evidence["claims"]:
        executed_at = datetime.fromisoformat(claim["executed_at"].replace("Z", "+00:00"))
        if not started_at <= executed_at <= ended_at:
            raise ValueError(f"claim {claim['code']} execution time is outside the evidence window")
        actor = claim["executed_by"]
        if actor["kind"] == "HUMAN" and actor["id"].strip().lower() == "codex":
            raise ValueError("Codex cannot be recorded as HUMAN")
        if claim["policy"]["sha256"] != policy_sha256:
            raise ValueError(f"claim {claim['code']} policy SHA-256 mismatch")
        if claim["gold_set"]["sha256"] != gold_sha256:
            raise ValueError(f"claim {claim['code']} gold-set SHA-256 mismatch")
        for reference in claim["evidence_refs"]:
            if reference["baseline_commit"] != evidence["baseline_commit"]:
                raise ValueError("evidence baseline commit mismatch")
            if reference["environment"] != evidence["environment"]:
                raise ValueError("evidence environment mismatch")
            if reference["window_id"] != evidence["window"]["id"]:
                raise ValueError("evidence window mismatch")
            target = (ROOT / reference["uri"]).resolve()
            try:
                target.relative_to(ROOT.resolve())
            except ValueError as exc:
                raise ValueError("evidence reference escapes repository root") from exc
            if not target.is_file():
                raise ValueError(f"evidence reference does not exist: {reference['uri']}")
            if sha256(target.read_bytes()).hexdigest() != reference["sha256"]:
                raise ValueError(f"evidence SHA-256 mismatch: {reference['uri']}")
    if evidence["decision"] != "BLOCKED" and any(
        claim["status"] != "PASSED" for claim in evidence["claims"]
    ):
        raise ValueError("READY decision requires every claim to pass")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gold-manifest", type=Path, default=ROOT / "tests/gold/v1/manifest.json")
    parser.add_argument("--readiness", type=Path)
    args = parser.parse_args()
    result = evaluate_gold_manifest(args.gold_manifest)
    if args.readiness:
        validate_readiness(args.readiness)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
