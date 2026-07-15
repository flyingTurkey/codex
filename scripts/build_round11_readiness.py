"""Build a self-consistent Round 11 evidence manifest from current local artifacts."""

from __future__ import annotations

import json
import shutil
import subprocess
from datetime import UTC, datetime
from hashlib import sha256
from typing import Any

from evaluate_readiness import QUALITY_GATES, ROOT, canonical_json, manifest_sha256

OUTPUT = ROOT / "docs/acceptance/round-11-readiness-evidence.json"
GOLD = ROOT / "tests/gold/v1/manifest.json"
GIT = shutil.which("git")
if GIT is None:
    raise RuntimeError("git is required to build readiness evidence")


def _json(relative: str) -> dict[str, Any]:
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


def _artifact_time(relative: str, field: str = "executed_at") -> str:
    value = _json(relative)[field]
    if not isinstance(value, str):
        raise ValueError(f"{relative} lacks a string {field}")
    return value


def _workspace_snapshot() -> str:
    completed = subprocess.run(  # noqa: S603 - resolved git executable, fixed arguments.
        [GIT, "status", "--porcelain=v1", "-uall"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    entries: list[dict[str, str]] = []
    for line in completed.stdout.splitlines():
        relative = line[3:].replace("\\", "/")
        if relative.startswith("docs/codex-kit/docs/phase-2/"):
            continue
        if relative == "docs/acceptance/round-11-readiness-evidence.json":
            continue
        if relative.startswith("docs/acceptance/assets/round11-"):
            continue
        path = ROOT / relative
        if path.is_file():
            entries.append({"path": relative, "sha256": sha256(path.read_bytes()).hexdigest()})
    return sha256(canonical_json(sorted(entries, key=lambda item: item["path"]))).hexdigest()


def main() -> None:
    baseline_commit = subprocess.run(  # noqa: S603 - resolved git, fixed arguments.
        [GIT, "rev-parse", "HEAD"], cwd=ROOT, check=True, capture_output=True, text=True
    ).stdout.strip()
    branch = subprocess.run(  # noqa: S603 - resolved git executable, fixed arguments.
        [GIT, "branch", "--show-current"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    quality_sha = sha256(QUALITY_GATES.read_bytes()).hexdigest()
    gold_sha = sha256(GOLD.read_bytes()).hexdigest()
    window_id = f"round11-{datetime.now(UTC).strftime('%Y%m%dt%H%M%Sz')}"
    context = {
        "baseline_commit": baseline_commit,
        "environment": "TEST",
        "window_id": window_id,
    }

    def ref(kind: str, uri: str) -> dict[str, str]:
        return {
            "kind": kind,
            "uri": uri,
            "sha256": sha256((ROOT / uri).read_bytes()).hexdigest(),
            **context,
        }

    policy = {"version": "1.0.0", "sha256": quality_sha}
    gold = {"version": "1.0.0-seed", "sha256": gold_sha}
    actor = {"kind": "AGENT", "id": "Codex"}
    claims = [
        (
            "GOLD_SET_COMPLETENESS",
            "INSUFFICIENT_EVIDENCE",
            _artifact_time("docs/acceptance/assets/round11-quality-gates.json"),
            [ref("CONFIG", "tests/gold/v1/manifest.json")],
        ),
        (
            "ROUND11_MIGRATION_REPLAY",
            "PASSED",
            _artifact_time("docs/acceptance/assets/round11-quality-gates.json"),
            [ref("TEST_LOG", "docs/acceptance/assets/round11-migration-replay.txt")],
        ),
        (
            "ISOLATED_RECOVERY_EXERCISE",
            "PASSED",
            _artifact_time("docs/acceptance/assets/round11-recovery-drill.json", "completed_at"),
            [ref("DRILL_RECORD", "docs/acceptance/assets/round11-recovery-drill.json")],
        ),
        (
            "PRODUCTION_PITR_RPO_RTO",
            "INSUFFICIENT_EVIDENCE",
            _artifact_time("docs/acceptance/assets/round11-recovery-drill.json", "completed_at"),
            [ref("DRILL_RECORD", "docs/acceptance/assets/round11-recovery-drill.json")],
        ),
        (
            "LOCAL_LOAD_BASELINE",
            "PASSED",
            _artifact_time("docs/acceptance/assets/round11-load-baseline.json"),
            [ref("REPORT", "docs/acceptance/assets/round11-load-baseline.json")],
        ),
        (
            "OBSERVABILITY_RUNTIME",
            "PASSED",
            _artifact_time("docs/acceptance/assets/round11-observability-runtime.json"),
            [ref("MONITOR_QUERY", "docs/acceptance/assets/round11-observability-runtime.json")],
        ),
        (
            "SECURITY_HIGH_RISK_GATE",
            "PASSED",
            _artifact_time("docs/acceptance/assets/round11-security-scan.json"),
            [ref("TEST_LOG", "docs/acceptance/assets/round11-security-scan.json")],
        ),
        (
            "UI_REGRESSION_ACCESSIBILITY",
            "PASSED",
            _artifact_time("docs/acceptance/assets/round11-quality-gates.json"),
            [
                ref("TEST_LOG", "docs/acceptance/assets/round11-quality-gates.json"),
                ref("REPORT", "apps/web/tests/e2e/visual-baselines/round11-operations.png"),
            ],
        ),
        (
            "CONTINUOUS_SLO_AND_ALERT_ROUTING",
            "INSUFFICIENT_EVIDENCE",
            _json("docs/acceptance/assets/round11-slo-current-window.json")["window"]["ended_at"],
            [
                ref("MONITOR_QUERY", "docs/acceptance/assets/round11-slo-current-window.json"),
                ref("MONITOR_QUERY", "docs/acceptance/assets/round11-observability-runtime.json"),
            ],
        ),
        (
            "SEED_USER_14_DAY_ACCEPTANCE",
            "INSUFFICIENT_EVIDENCE",
            _artifact_time("docs/acceptance/assets/round11-quality-gates.json"),
            [ref("TEST_LOG", "docs/acceptance/assets/round11-quality-gates.json")],
        ),
    ]
    normalized_times = [
        datetime.fromisoformat(value.replace("Z", "+00:00")) for _, _, value, _ in claims
    ]
    started_at = min(normalized_times).astimezone(UTC)
    ended_at = max(normalized_times).astimezone(UTC)
    manifest: dict[str, Any] = {
        "manifest_version": "1.1.0",
        "baseline_commit": baseline_commit,
        "branch": branch,
        "workspace_snapshot_sha256": _workspace_snapshot(),
        "environment": "TEST",
        "window": {
            "id": window_id,
            "started_at": started_at.isoformat().replace("+00:00", "Z"),
            "ended_at": ended_at.isoformat().replace("+00:00", "Z"),
            "duration_days": round((ended_at - started_at).total_seconds() / 86400, 6),
        },
        "claims": [
            {
                "code": code,
                "status": status,
                "executed_at": datetime.fromisoformat(executed_at.replace("Z", "+00:00"))
                .astimezone(UTC)
                .isoformat()
                .replace("+00:00", "Z"),
                "executed_by": actor,
                "policy": policy,
                "gold_set": gold,
                "evidence_refs": references,
            }
            for code, status, executed_at, references in claims
        ],
        "decision": "BLOCKED",
        "generated_by_ci": False,
        "manifest_sha256": "0" * 64,
    }
    manifest["manifest_sha256"] = manifest_sha256(manifest)
    OUTPUT.write_bytes((json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
    print(f"Built {OUTPUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
