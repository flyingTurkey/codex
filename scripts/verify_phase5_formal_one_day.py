"""Collect and verify the Phase 5 one-source formal operating window."""

# ruff: noqa: S608 -- UUID values are parsed before interpolation into fixed SQL.

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from itertools import pairwise
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import urlopen
from uuid import UUID

FORMAL_PROJECT = "srbg-intelligence"
FORMAL_POSTGRES = f"{FORMAL_PROJECT}-postgres-1"
EXPECTED_REVISION = "0060_phase5_extract_prompt_v3"
EXPECTED_RUN_LIMITS = {
    "request_limit": 80,
    "byte_limit": 157_286_400,
    "response_limit": 52_428_800,
    "ai_cost_limit_microusd": 1_250_000,
    "failure_limit": 10,
    "failure_rate_bps": 3_000,
    "failure_rate_min_samples": 10,
}
REQUIRED_SERVICES = (
    "api",
    "web",
    "parser",
    "worker",
    "scheduler",
    "publisher",
    "personal-source-worker",
    "source-discovery",
    "ai-worker",
)


def append_sample(path: Path, sample: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(
        dict(sample), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    with path.open("a", encoding="utf-8", newline="\n") as evidence:
        evidence.write(payload + "\n")


def load_samples(path: Path) -> list[dict[str, object]]:
    samples: list[dict[str, object]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        value = json.loads(line)
        if not isinstance(value, dict):
            raise ValueError("phase5 sample must be a JSON object")
        samples.append(value)
    return samples


def write_final_report(path: Path, report: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(
        dict(report), ensure_ascii=False, sort_keys=True, indent=2
    ) + "\n"
    with path.open("x", encoding="utf-8", newline="\n") as evidence:
        evidence.write(payload)


def _run(command: Sequence[str]) -> str:
    completed = subprocess.run(  # noqa: S603 - fixed local executables and arguments.
        list(command),
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
        encoding="utf-8",
        errors="replace",
    )
    return completed.stdout.strip()


def _docker() -> str:
    executable = shutil.which("docker")
    if executable is None:
        raise RuntimeError("PHASE5_DOCKER_NOT_FOUND")
    return executable


def _assert_formal_postgres() -> None:
    payload = json.loads(
        _run([_docker(), "inspect", FORMAL_POSTGRES, "--format", "{{json .}}"])
    )
    labels = payload.get("Config", {}).get("Labels", {})
    if labels.get("com.docker.compose.project") != FORMAL_PROJECT:
        raise RuntimeError("PHASE5_FORMAL_PROJECT_MISMATCH")
    mounts = payload.get("Mounts", [])
    postgres_mounts = [
        mount
        for mount in mounts
        if mount.get("Destination") == "/var/lib/postgresql/data"
    ]
    if len(postgres_mounts) != 1 or "/SRBGDataDisk/srv/postgres" not in str(
        postgres_mounts[0].get("Source", "")
    ):
        raise RuntimeError("PHASE5_FORMAL_DATA_MOUNT_MISMATCH")


def _psql_json(sql: str) -> dict[str, object]:
    payload = _run(
        [
            _docker(),
            "exec",
            FORMAL_POSTGRES,
            "psql",
            "-U",
            "srbg",
            "-d",
            "srbg",
            "-At",
            "-q",
            "-v",
            "ON_ERROR_STOP=1",
            "-c",
            sql,
        ]
    )
    value = json.loads(payload)
    if not isinstance(value, dict):
        raise RuntimeError("PHASE5_DATABASE_SNAPSHOT_INVALID")
    return value


def _database_snapshot_sql(run_id: UUID, source_stream_id: UUID) -> str:
    return f"""
WITH selected_run AS (
  SELECT * FROM personal_controlled_run WHERE id='{run_id}'::uuid
), selected_stream AS (
  SELECT id,source_id FROM source_stream WHERE id='{source_stream_id}'::uuid
), run_fetch AS (
  SELECT fr.* FROM fetch_run fr
   WHERE fr.controlled_run_id='{run_id}'::uuid
), run_docs AS (
  SELECT DISTINCT version.id AS version_id,document.id AS document_id,
         document.canonical_url,version.content_hash
    FROM run_fetch fr
    JOIN raw_object_capture capture ON capture.fetch_run_id=fr.id
    JOIN document_version version ON version.raw_object_capture_id=capture.id
    JOIN document ON document.id=version.document_id
), run_pipelines AS (
  SELECT pipeline.* FROM ai_pipeline_run pipeline
   WHERE pipeline.controlled_run_id='{run_id}'::uuid
      OR pipeline.document_version_id IN (SELECT version_id FROM run_docs)
), visible AS (
  SELECT projection.* FROM visible_intelligence_projection_v2 projection
   WHERE projection.document_version_id IN (SELECT version_id FROM run_docs)
), accepted AS (
  SELECT claim.id AS claim_id,evidence.id AS evidence_id
    FROM claim
    JOIN intelligence_item item ON item.id=claim.item_id
    LEFT JOIN claim_evidence evidence ON evidence.claim_id=claim.id
      AND evidence.document_version_id=claim.document_version_id
   WHERE claim.document_version_id IN (SELECT version_id FROM run_docs)
     AND claim.verification_status='ACCEPTED'
), unpublished AS (
  SELECT docs.version_id,
         array_remove(ARRAY[
           decision.disposition,
           pipeline.failure_code,
           outbox.last_error_code,
           publication.reason_codes[1]
         ],NULL)::text[] || COALESCE(decision.reason_codes,ARRAY[]::varchar[])::text[]
           AS reason_codes
    FROM run_docs docs
    LEFT JOIN LATERAL (
      SELECT disposition,reason_codes
        FROM automated_qualification_decision_v2 decision
       WHERE decision.document_version_id=docs.version_id
       ORDER BY decision.decided_at DESC,decision.id DESC LIMIT 1
    ) decision ON true
    LEFT JOIN LATERAL (
      SELECT status,failure_code FROM run_pipelines pipeline
       WHERE pipeline.document_version_id=docs.version_id
       ORDER BY pipeline.started_at DESC,pipeline.id DESC LIMIT 1
    ) pipeline ON true
    LEFT JOIN LATERAL (
      SELECT status,last_error_code FROM source_content_outbox outbox
       WHERE outbox.document_version_id=docs.version_id
       ORDER BY outbox.created_at DESC,outbox.id DESC LIMIT 1
    ) outbox ON true
    LEFT JOIN LATERAL (
      SELECT outcome,reason_codes FROM publication_decision_v2 publication
       WHERE publication.document_version_id=docs.version_id
       ORDER BY publication.created_at DESC,publication.id DESC LIMIT 1
    ) publication ON true
   WHERE NOT EXISTS(
     SELECT 1 FROM visible WHERE visible.document_version_id=docs.version_id
   )
), duplicate_events AS (
  SELECT document_version_id,count(DISTINCT event_id)-1 AS duplicates
    FROM visible GROUP BY document_version_id
)
SELECT json_build_object(
  'database_revision',(SELECT version_num FROM alembic_version),
  'event_id',(SELECT event_id::text FROM visible ORDER BY projected_at LIMIT 1),
  'source_id',(SELECT source_id::text FROM selected_stream),
  'source_stream_id','{source_stream_id}',
  'run',(
    SELECT json_build_object(
      'id',id::text,'state',state,'wall_started_at',wall_started_at,
      'wall_deadline',wall_deadline,'stop_reason',stop_reason,
      'request_limit',request_limit,'byte_limit',byte_limit,
      'response_limit',response_limit,
      'ai_cost_limit_microusd',ai_cost_limit_microusd,
      'failure_limit',failure_limit,'failure_rate_bps',failure_rate_bps,
      'failure_rate_min_samples',failure_rate_min_samples,
      'requests_reserved',requests_reserved,'bytes_settled',bytes_settled,
      'attempts_settled',attempts_settled,'attempts_failed',attempts_failed,
      'ai_cost_settled_microusd',ai_cost_settled_microusd
    ) FROM selected_run
  ),
  'metrics',json_build_object(
    'run_source_count',(SELECT count(*) FROM personal_controlled_run_source
      WHERE run_id='{run_id}'::uuid),
    'run_source_matches_stream',EXISTS(
      SELECT 1 FROM personal_controlled_run_source controlled
      JOIN selected_stream stream ON stream.source_id=controlled.source_id
      WHERE controlled.run_id='{run_id}'::uuid
    ),
    'run_stream_count',(SELECT count(DISTINCT source_stream_id) FROM run_fetch),
    'run_stream_mismatch',(SELECT count(*) FROM run_fetch
      WHERE source_stream_id IS DISTINCT FROM '{source_stream_id}'::uuid),
    'discovered',COALESCE((SELECT sum(discovered_count) FROM run_fetch),0),
    'fetched',COALESCE((SELECT sum(fetched_count) FROM run_fetch),0),
    'parsed',(SELECT count(*) FROM run_docs),
    'auto_filtered',(SELECT count(*) FROM automated_qualification_decision_v2
      WHERE document_version_id IN (SELECT version_id FROM run_docs)
        AND disposition='AUTO_FILTERED'),
    'ai_succeeded',(SELECT count(*) FROM run_pipelines WHERE status='SUCCEEDED'),
    'published',(SELECT count(DISTINCT event_id) FROM visible),
    'failed',
      (SELECT count(*) FROM personal_controlled_http_attempt
        WHERE run_id='{run_id}'::uuid AND outcome='FAILED') +
      (SELECT count(*) FROM run_fetch WHERE status='FAILED'
        OR transport_status='FAILED' OR discovery_status='FALSE_SUCCESS'
        OR parse_status='DEGRADED' OR quality_status='DEGRADED') +
      (SELECT count(*) FROM run_pipelines WHERE status IN ('FAILED','DEGRADED')) +
      (SELECT count(*) FROM source_content_outbox
        WHERE document_version_id IN (SELECT version_id FROM run_docs)
          AND status IN ('FAILED','DEAD_LETTER')),
    'silent_failures',
      (SELECT count(*) FROM personal_controlled_http_attempt
        WHERE run_id='{run_id}'::uuid AND outcome='FAILED'
          AND failure_code IS NULL) +
      (SELECT count(*) FROM run_fetch WHERE status='FAILED'
        AND error_code IS NULL AND failure_class IS NULL) +
      (SELECT count(*) FROM run_pipelines WHERE status IN ('FAILED','DEGRADED')
        AND failure_code IS NULL) +
      (SELECT count(*) FROM source_content_outbox
        WHERE document_version_id IN (SELECT version_id FROM run_docs)
          AND status IN ('FAILED','DEAD_LETTER') AND last_error_code IS NULL),
    'hanging',
      (SELECT count(*) FROM personal_controlled_http_attempt
        WHERE run_id='{run_id}'::uuid AND outcome='RESERVED') +
      (SELECT count(*) FROM run_fetch
        WHERE status IN ('PENDING_DISPATCH','DISPATCHED','RUNNING','RETRY_WAIT')) +
      (SELECT count(*) FROM source_content_outbox
        WHERE document_version_id IN (SELECT version_id FROM run_docs)
          AND status IN ('PENDING','WAITING_AI')) +
      (SELECT count(*) FROM run_pipelines
        WHERE status IN ('QUEUED','PREPARING','CLASSIFYING','EXTRACTING',
          'WAITING_CLAIM_REVIEW','RUNNING')) +
      (SELECT count(*) FROM ai_budget_reservation reservation
        JOIN run_pipelines pipeline ON pipeline.id=reservation.pipeline_run_id
        WHERE reservation.billing_status IN ('RESERVED','UNKNOWN')),
    'retries',
      COALESCE((SELECT sum(GREATEST(attempt_count-1,0)) FROM run_fetch),0) +
      COALESCE((SELECT sum(GREATEST(attempt_count-1,0))
        FROM source_content_outbox
        WHERE document_version_id IN (SELECT version_id FROM run_docs)),0) +
      (SELECT count(*) FROM ai_step_run step JOIN run_pipelines pipeline
        ON pipeline.id=step.pipeline_run_id WHERE step.attempt>1),
    'duplicates',
      COALESCE((SELECT sum(duplicates) FROM duplicate_events),0) +
      ((SELECT count(*) FROM run_docs) -
       (SELECT count(DISTINCT canonical_url) FROM run_docs)),
    'other_source_fetches',(SELECT count(*) FROM fetch_run fr
      CROSS JOIN selected_run run
      WHERE fr.started_at>=run.wall_started_at
        AND fr.started_at<=run.wall_deadline
        AND fr.source_stream_id IS DISTINCT FROM '{source_stream_id}'::uuid),
    'input_tokens',COALESCE((SELECT sum(step.input_tokens) FROM ai_step_run step
      JOIN run_pipelines pipeline ON pipeline.id=step.pipeline_run_id),0),
    'output_tokens',COALESCE((SELECT sum(step.output_tokens) FROM ai_step_run step
      JOIN run_pipelines pipeline ON pipeline.id=step.pipeline_run_id),0),
    'cost_microusd',COALESCE((SELECT ai_cost_settled_microusd
      FROM selected_run),0),
    'step_cost_microusd',COALESCE((SELECT sum(COALESCE(
      step.provider_cost_microusd,step.cost_microusd,0)) FROM ai_step_run step
      JOIN run_pipelines pipeline ON pipeline.id=step.pipeline_run_id),0),
    'accepted_claims',(SELECT count(DISTINCT claim_id) FROM accepted),
    'claim_evidence_links',(SELECT count(DISTINCT evidence_id) FROM accepted
      WHERE evidence_id IS NOT NULL),
    'claims_without_evidence',(SELECT count(DISTINCT claim_id) FROM accepted
      WHERE evidence_id IS NULL),
    'other_primary_types',(SELECT count(*) FROM visible
      WHERE primary_type<>'INDUSTRY_UPDATE'),
    'higher_risk_published',(SELECT count(*) FROM visible
      WHERE risk_tier NOT IN ('R1','R2')),
    'fetch_latency_ms_p95',COALESCE((SELECT CAST(percentile_cont(0.95) WITHIN GROUP(
      ORDER BY EXTRACT(EPOCH FROM (completed_at-started_at))*1000) AS bigint)
      FROM run_fetch WHERE completed_at IS NOT NULL),0),
    'ai_latency_ms_p95',COALESCE((SELECT CAST(percentile_cont(0.95) WITHIN GROUP(
      ORDER BY step.latency_ms) AS bigint) FROM ai_step_run step
      JOIN run_pipelines pipeline ON pipeline.id=step.pipeline_run_id),0),
    'unpublished',COALESCE((SELECT json_agg(json_build_object(
      'document_version_id',version_id::text,'reason_codes',reason_codes)
      ORDER BY version_id) FROM unpublished),'[]'::json)
  )
)
"""


def _database_snapshot(run_id: UUID, source_stream_id: UUID) -> dict[str, object]:
    return _psql_json(_database_snapshot_sql(run_id, source_stream_id))


def _service_start_times() -> dict[str, str]:
    starts: dict[str, str] = {}
    for service in REQUIRED_SERVICES:
        container = f"{FORMAL_PROJECT}-{service}-1"
        payload = json.loads(
            _run([_docker(), "inspect", container, "--format", "{{json .State}}"])
        )
        if payload.get("Status") != "running":
            raise RuntimeError(f"PHASE5_SERVICE_NOT_RUNNING:{service}")
        started_at = payload.get("StartedAt")
        if not isinstance(started_at, str):
            raise RuntimeError(f"PHASE5_SERVICE_START_UNKNOWN:{service}")
        starts[service] = started_at
    return starts


def _contains_identifier(value: object, identifier: str) -> bool:
    return identifier in json.dumps(value, ensure_ascii=False, sort_keys=True)


def _http_get(url: str) -> tuple[int, object | None]:
    try:
        with urlopen(url, timeout=10) as response:  # noqa: S310 - fixed loopback URLs.
            payload = response.read()
            content_type = response.headers.get_content_type()
            value = (
                json.loads(payload)
                if content_type == "application/json"
                else payload.decode("utf-8", errors="replace")
            )
            return response.status, value
    except HTTPError as error:
        return error.code, None


def _surface_snapshot(event_id: str | None) -> dict[str, object]:
    all_status, all_page = _http_get("http://127.0.0.1:3000/all")
    feed_status, feed = _http_get("http://127.0.0.1:8000/api/v2/feed")
    detail_status = 0
    detail_contains = False
    feed_contains = bool(event_id and _contains_identifier(feed, event_id))
    if feed_status == 200 and event_id:
        detail_status, detail = _http_get(
            f"http://127.0.0.1:8000/api/v2/events/{event_id}"
        )
        detail_contains = bool(
            detail_status == 200 and _contains_identifier(detail, event_id)
        )
    return {
        "all_status": all_status,
        "all_contains_event": bool(
            event_id and _contains_identifier(all_page, event_id)
        ),
        "feed_status": feed_status,
        "feed_contains_event": feed_contains,
        "detail_status": detail_status,
        "detail_contains_event": detail_contains,
    }


def collect_snapshot(run_id: UUID, source_stream_id: UUID) -> dict[str, object]:
    _assert_formal_postgres()
    database = _database_snapshot(run_id, source_stream_id)
    event_id = database.get("event_id")
    database["surfaces"] = _surface_snapshot(
        event_id if isinstance(event_id, str) else None
    )
    database["sampled_at"] = datetime.now(UTC).isoformat()
    database["services"] = _service_start_times()
    return database


def _git_sha() -> str:
    return _run(["git", "rev-parse", "HEAD"])


def _sha256(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _timestamp(value: object) -> datetime:
    if not isinstance(value, str):
        raise ValueError("phase5 timestamp must be an ISO-8601 string")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("phase5 timestamp must include an offset")
    return parsed


def _integer(mapping: Mapping[str, object], name: str) -> int:
    value = mapping.get(name)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"phase5 metric {name} must be an integer")
    return value


def evaluate_operation(
    samples: Sequence[Mapping[str, object]], final: Mapping[str, object]
) -> dict[str, object]:
    """Evaluate only externally recorded operation facts; never infer a PASS."""

    reasons: list[str] = []
    ordered = sorted(_timestamp(sample.get("sampled_at")) for sample in samples)
    if len(ordered) < 2 or ordered[-1] - ordered[0] < timedelta(hours=8):
        reasons.append("WINDOW_TOO_SHORT")
    elif any(
        later - earlier > timedelta(minutes=30)
        for earlier, later in pairwise(ordered)
    ):
        reasons.append("SAMPLING_GAP")

    run = final.get("run")
    metrics = final.get("metrics")
    surfaces = final.get("surfaces")
    if not isinstance(run, Mapping) or not isinstance(metrics, Mapping):
        raise ValueError("phase5 final evidence is missing run or metrics")
    if not isinstance(surfaces, Mapping):
        raise ValueError("phase5 final evidence is missing surfaces")

    started_at = _timestamp(run.get("wall_started_at"))
    deadline = _timestamp(run.get("wall_deadline"))
    if final.get("database_revision") != EXPECTED_REVISION:
        reasons.append("DATABASE_REVISION_INVALID")
    if any(run.get(name) != value for name, value in EXPECTED_RUN_LIMITS.items()):
        reasons.append("CONTROLLED_RUN_LIMITS_INVALID")
    if not ordered or abs(ordered[0] - started_at) > timedelta(minutes=30):
        reasons.append("RUN_START_NOT_SAMPLED")
    if not ordered or ordered[-1] < started_at + timedelta(hours=8):
        reasons.append("RUN_END_NOT_SAMPLED")
    if deadline - started_at < timedelta(hours=8):
        reasons.append("CONTROLLED_RUN_DEADLINE_TOO_SHORT")
    if run.get("state") != "COMPLETED":
        reasons.append("CONTROLLED_RUN_NOT_COMPLETED")
    stop_reason = run.get("stop_reason")
    if not isinstance(stop_reason, str) or not stop_reason.strip():
        reasons.append("RUN_STOP_REASON_MISSING")

    worker_starts: set[str] = set()
    for sample in samples:
        services = sample.get("services")
        if isinstance(services, Mapping):
            worker_started = services.get("worker")
            if isinstance(worker_started, str):
                worker_starts.add(worker_started)
    if len(worker_starts) < 2:
        reasons.append("RESTART_RECOVERY_NOT_PROVEN")

    required_positive = {
        "discovered": "NO_DISCOVERY",
        "fetched": "NO_FETCH",
        "parsed": "NO_PARSE",
        "ai_succeeded": "NO_AI_SUCCESS",
        "published": "NO_PUBLICATION",
        "accepted_claims": "NO_ACCEPTED_CLAIMS",
        "claim_evidence_links": "NO_CLAIM_EVIDENCE_LINKS",
    }
    for name, reason in required_positive.items():
        if _integer(metrics, name) < 1:
            reasons.append(reason)

    if _integer(metrics, "other_source_fetches") != 0:
        reasons.append("OTHER_SOURCE_RAN")
    if _integer(metrics, "run_source_count") != 1:
        reasons.append("RUN_SOURCE_COUNT_INVALID")
    if metrics.get("run_source_matches_stream") is not True:
        reasons.append("RUN_SOURCE_STREAM_SOURCE_MISMATCH")
    if _integer(metrics, "run_stream_count") != 1:
        reasons.append("RUN_STREAM_COUNT_INVALID")
    if _integer(metrics, "run_stream_mismatch") != 0:
        reasons.append("RUN_STREAM_MISMATCH")
    if _integer(metrics, "other_primary_types") != 0:
        reasons.append("CONTENT_TYPE_OUT_OF_SCOPE")
    if _integer(metrics, "higher_risk_published") != 0:
        reasons.append("CONTENT_RISK_OUT_OF_SCOPE")
    if _integer(metrics, "duplicates") != 0:
        reasons.append("DUPLICATE_OUTPUT")
    if _integer(metrics, "silent_failures") != 0:
        reasons.append("SILENT_FAILURE")
    if _integer(metrics, "hanging") != 0:
        reasons.append("PERMANENT_HANG")
    if _integer(metrics, "claims_without_evidence") != 0:
        reasons.append("CLAIM_EVIDENCE_TRACE_INCOMPLETE")

    cost = _integer(metrics, "cost_microusd")
    limit = _integer(run, "ai_cost_limit_microusd")
    if cost > limit:
        reasons.append("AI_BUDGET_EXCEEDED")

    unpublished = metrics.get("unpublished")
    if not isinstance(unpublished, list):
        raise ValueError("phase5 unpublished evidence must be a list")
    if any(
        not isinstance(item, Mapping)
        or not isinstance(item.get("reason_codes"), list)
        or not item["reason_codes"]
        or any(
            not isinstance(reason, str) or not reason.strip()
            for reason in item["reason_codes"]
        )
        for item in unpublished
    ):
        reasons.append("UNPUBLISHED_REASON_MISSING")

    if surfaces.get("all_status") != 200:
        reasons.append("ALL_PAGE_UNREADABLE")
    if surfaces.get("all_contains_event") is not True:
        reasons.append("ALL_PAGE_ITEM_MISSING")
    if surfaces.get("feed_contains_event") is not True:
        reasons.append("FEED_ITEM_MISSING")
    if surfaces.get("detail_status") != 200 or surfaces.get("detail_contains_event") is not True:
        reasons.append("EVENT_DETAIL_UNREADABLE")

    return {
        "decision": "PASS" if not reasons else "NO_GO",
        "reasons": sorted(set(reasons)),
    }


def _parse_args(arguments: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--action", choices=("sample", "verify"), required=True)
    parser.add_argument("--run-id", type=UUID, required=True)
    parser.add_argument("--source-stream-id", type=UUID, required=True)
    parser.add_argument("--evidence-root", type=Path, required=True)
    return parser.parse_args(arguments)


def main(arguments: Sequence[str] | None = None) -> int:
    args = _parse_args(arguments)
    evidence_root = args.evidence_root.resolve()
    sample_path = evidence_root / f"phase5-{args.run_id}-samples.jsonl"
    snapshot = collect_snapshot(args.run_id, args.source_stream_id)
    append_sample(sample_path, snapshot)
    if args.action == "sample":
        print(sample_path)
        return 0

    samples = load_samples(sample_path)
    result = evaluate_operation(samples, snapshot)
    report = {
        "schema_version": "phase5-formal-one-day-v1",
        "generated_at": datetime.now(UTC).isoformat(),
        "code_sha": _git_sha(),
        "run_id": str(args.run_id),
        "source_stream_id": str(args.source_stream_id),
        "sample_evidence_path": str(sample_path),
        "sample_evidence_sha256": _sha256(sample_path),
        "sample_count": len(samples),
        "final": snapshot,
        **result,
    }
    report_path = evidence_root / f"phase5-{args.run_id}-final.json"
    write_final_report(report_path, report)
    print(json.dumps({"report": str(report_path), **result}, sort_keys=True))
    return 0 if result["decision"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
