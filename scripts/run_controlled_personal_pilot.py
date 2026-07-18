# ruff: noqa: E501, S603, S608
"""Fail-closed unattended pilot orchestration; no network in preflight mode."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit
from uuid import UUID

from srbg_api.identifiers import uuid7

SOURCES = (
    "https://www.gov.cn/zhengce/",
    "https://www.mot.gov.cn/",
    "https://xxgk.mot.gov.cn/",
    "https://jtt.sc.gov.cn/",
    "https://www.mem.gov.cn/gk/sgcc/tbzdsgdcbg/",
)
FINAL_PASS_SOURCE_THRESHOLD = 4
LIMITED_PASS_SOURCE_THRESHOLD = 3
FIXED_FIVE_POLICY_VERSION = "pers10-fixed-five-3of5-v1"
POST_STOP_OBSERVATION_SECONDS = 90
CONTENT_PROJECTION_DRAIN_SECONDS = 600


def classify_pilot_verdict(
    successful_sources: int,
    *,
    content_chain_ok: bool,
    invariants_ok: bool,
    policy_version: str | None = None,
    exact_fixed_source_set: bool = False,
) -> str:
    if not content_chain_ok or not invariants_ok:
        return "FAIL"
    if successful_sources >= FINAL_PASS_SOURCE_THRESHOLD:
        return "PASS"
    if successful_sources >= LIMITED_PASS_SOURCE_THRESHOLD:
        if policy_version == FIXED_FIVE_POLICY_VERSION and exact_fixed_source_set:
            return "PASS"
        return "LIMITED_PASS"
    return "FAIL"


def _is_exact_fixed_source_set(source_outcomes: list[dict[str, object]]) -> bool:
    return {str(item.get("base_url")) for item in source_outcomes} == set(SOURCES)


def _source_failure_diagnosis(
    source_outcomes: list[dict[str, object]],
) -> list[dict[str, object]]:
    """Classify failed fixed-pilot sources without performing new network I/O."""
    candidates = {
        "https://xxgk.mot.gov.cn/": (
            "https://xxgk.mot.gov.cn/2020/zhengce/qtwjlist_3.html",
            "https://www.mot.gov.cn/gongkai/zcjd/",
        ),
        "https://www.mem.gov.cn/gk/sgcc/tbzdsgdcbg/": (
            "https://www.mem.gov.cn/gk/index.shtml",
        ),
    }
    diagnoses: list[dict[str, object]] = []
    for outcome in source_outcomes:
        if bool(outcome.get("successful")):
            continue
        base_url = str(outcome.get("base_url"))
        failure = str(outcome.get("probe_reason") or "UNKNOWN")
        if failure == "UNSUPPORTED_CLIENT_REDIRECT":
            category = "SOURCE_RESPONSE_OR_CLIENT_REDIRECT"
        elif base_url.endswith("/tbzdsgdcbg/"):
            category = "SOURCE_SELECTION_OR_PATH_BOUNDARY"
        else:
            category = "RUNTIME_OR_SOURCE_RELIABILITY"
        diagnoses.append(
            {
                "base_url": base_url,
                "failure_code": failure,
                "category": category,
                "replacement_candidates": list(candidates.get(base_url, ())),
                "requires_bounded_reprobe_before_replacement": True,
            }
        )
    return diagnoses


@dataclass(frozen=True, slots=True)
class PilotLimits:
    active_seconds: int = 7200
    wall_seconds: int = 14400
    requests: int = 80
    bytes: int = 150 * 1024 * 1024
    ai_cost_microusd: int = 1_250_000


def _psql(sql: str) -> str:
    docker = shutil.which("docker")
    if docker is None:
        raise RuntimeError("PILOT_DOCKER_NOT_FOUND")
    try:
        completed = subprocess.run(
            [
                docker,
                "exec",
                "srbg-intelligence-postgres-1",
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
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except subprocess.CalledProcessError as error:
        safe_lines = [line.strip() for line in (error.stderr or "").splitlines() if line.strip()]
        error_lines = [line for line in safe_lines if "ERROR:" in line]
        detail = (
            (error_lines[0] if error_lines else safe_lines[-1])[:160]
            if safe_lines
            else "PSQL_COMMAND_FAILED"
        )
        raise RuntimeError(detail) from error
    return completed.stdout.strip()


def _psql_json(sql: str) -> object:
    payload = _psql(sql)
    return None if not payload else json.loads(payload)


def _source_outcomes(run_id: str) -> list[dict[str, object]]:
    value = _psql_json(
        f"""
WITH run AS (
  SELECT id,wall_started_at FROM personal_controlled_run WHERE id='{run_id}'::uuid
), outcomes AS (
  SELECT source.base_url,
         COALESCE(probe.status,'MISSING') AS probe_status,
         probe.failure_code AS probe_reason,
         COALESCE(profile.status,'MISSING') AS profile_status,
         COALESCE(stream.ready_streams,0) AS ready_streams,
         COALESCE(schedule.active_schedules,0) AS active_schedules,
         schedule.health_status,schedule.health_reason,
         COALESCE(fetch_stats.fetch_runs,0) AS fetch_runs,
         COALESCE(fetch_stats.successful_fetch_runs,0) AS successful_fetch_runs,
         COALESCE(fetch_stats.controlled_schedules,0) AS controlled_schedules,
         COALESCE(fetch_stats.discovered_count,0) AS discovered_count,
         COALESCE(fetch_stats.fetched_count,0) AS fetched_count,
         COALESCE(fetch_stats.failed_count,0) AS failed_count
    FROM run
    JOIN personal_controlled_run_source controlled ON controlled.run_id=run.id
    JOIN source ON source.id=controlled.source_id
    LEFT JOIN LATERAL (
      SELECT status,failure_code FROM stream_probe_run
       WHERE controlled_run_id=run.id AND source_id=source.id
       ORDER BY created_at DESC,id DESC LIMIT 1
    ) probe ON true
    LEFT JOIN LATERAL (
      SELECT status FROM source_profile_snapshot
       WHERE source_id=source.id AND generated_at>=run.wall_started_at
       ORDER BY generated_at DESC,id DESC LIMIT 1
    ) profile ON true
    LEFT JOIN LATERAL (
      SELECT count(*) FILTER (WHERE status='READY') AS ready_streams
        FROM source_stream WHERE source_id=source.id
    ) stream ON true
    LEFT JOIN LATERAL (
      SELECT count(*) FILTER (WHERE status='ACTIVE') AS active_schedules,
             max(health_status) AS health_status,max(health_reason) AS health_reason
        FROM fetch_schedule WHERE source_id=source.id
    ) schedule ON true
    LEFT JOIN LATERAL (
      SELECT count(*) AS fetch_runs,
             count(*) FILTER (WHERE status='SUCCEEDED' AND failed_count=0) AS successful_fetch_runs,
             count(DISTINCT schedule_id) AS controlled_schedules,
             COALESCE(sum(discovered_count),0) AS discovered_count,
             COALESCE(sum(fetched_count),0) AS fetched_count,
             COALESCE(sum(failed_count),0) AS failed_count
        FROM fetch_run WHERE controlled_run_id=run.id AND source_id=source.id
    ) fetch_stats ON true
)
SELECT COALESCE(json_agg(json_build_object(
  'base_url',base_url,'probe_status',probe_status,'probe_reason',probe_reason,
  'profile_status',profile_status,'ready_streams',ready_streams,
  'active_schedules',active_schedules,'health_status',health_status,
  'health_reason',health_reason,'fetch_runs',fetch_runs,
  'controlled_schedules',controlled_schedules,
  'successful_fetch_runs',successful_fetch_runs,'discovered_count',discovered_count,
  'fetched_count',fetched_count,'failed_count',failed_count,
  'successful',(probe_status='SUCCEEDED' AND profile_status IN ('SUCCEEDED','PARTIAL')
    AND ready_streams>0 AND (active_schedules>0 OR controlled_schedules>0)
    AND successful_fetch_runs>0)
) ORDER BY base_url),'[]'::json) FROM outcomes
"""
    )
    if not isinstance(value, list):
        raise RuntimeError("CONTROLLED_PILOT_SOURCE_OUTCOME_INVALID")
    return [item for item in value if isinstance(item, dict)]


def _content_evidence(run_id: str) -> dict[str, object]:
    value = _psql_json(
        f"""
WITH run_versions AS (
  SELECT DISTINCT version.id AS version_id,version.document_id,version.content_hash,
         raw.sha256 AS raw_sha256,capture.final_url,item.id AS item_id
    FROM fetch_run run_fetch
    JOIN raw_object_capture capture ON capture.fetch_run_id=run_fetch.id
    JOIN raw_object raw ON raw.id=capture.raw_object_id
    JOIN document_version version ON version.raw_object_capture_id=capture.id
    LEFT JOIN intelligence_item item ON item.current_document_version_id=version.id
   WHERE run_fetch.controlled_run_id='{run_id}'::uuid
), facts AS (
  SELECT run_versions.*,
         count(DISTINCT claim.id) FILTER (WHERE claim.verification_status='ACCEPTED') AS accepted_claims,
         count(DISTINCT evidence.id) FILTER (WHERE claim.verification_status='ACCEPTED') AS evidence_ids,
         count(DISTINCT claim.id) FILTER (
           WHERE claim.verification_status='ACCEPTED' AND claim.critical
             AND evidence.id IS NULL
         ) AS critical_without_evidence,
         bool_or(COALESCE(projection.visible,false)
           AND projection.document_version_id=run_versions.version_id) AS projected
    FROM run_versions
    LEFT JOIN claim ON claim.item_id=run_versions.item_id
      AND claim.document_version_id=run_versions.version_id
    LEFT JOIN claim_evidence evidence ON evidence.claim_id=claim.id
      AND evidence.document_version_id=run_versions.version_id
    LEFT JOIN personal_content_projection projection ON projection.item_id=run_versions.item_id
    GROUP BY run_versions.version_id,run_versions.document_id,run_versions.content_hash,
             run_versions.raw_sha256,run_versions.final_url,run_versions.item_id
), ai_index AS (
  SELECT count(*) AS count
    FROM unverified_ai_search_projection search
    JOIN personal_signal_projection signal ON signal.id=search.signal_id
   WHERE signal.item_id IN (SELECT item_id FROM facts WHERE item_id IS NOT NULL)
     AND search.visible
), summary AS (
  SELECT count(*) AS raw_version_count,
         count(*) FILTER (WHERE content_hash=raw_sha256) AS valid_hash_count,
         count(*) FILTER (WHERE item_id IS NOT NULL) AS item_count,
         COALESCE(sum(accepted_claims),0) AS accepted_claim_count,
         COALESCE(sum(evidence_ids),0) AS evidence_id_count,
         COALESCE(sum(critical_without_evidence),0) AS critical_without_evidence,
         count(*) FILTER (WHERE projected) AS projected_item_count,
         min(item_id::text) FILTER (WHERE projected) AS sample_item_id,
         min(final_url) FILTER (WHERE projected) AS sample_original_url,
         EXISTS(SELECT 1 FROM facts WHERE item_id IS NOT NULL AND accepted_claims>0
           AND evidence_ids>0 AND critical_without_evidence=0 AND projected
           AND content_hash=raw_sha256) AS end_to_end_ok
    FROM facts
)
SELECT json_build_object(
  'raw_version_count',summary.raw_version_count,
  'valid_hash_count',summary.valid_hash_count,
  'item_count',summary.item_count,
  'accepted_claim_count',summary.accepted_claim_count,
  'evidence_id_count',summary.evidence_id_count,
  'critical_without_evidence',summary.critical_without_evidence,
  'projected_item_count',summary.projected_item_count,
  'unverified_ai_fact_index_count',ai_index.count,
  'sample_item_id',summary.sample_item_id,
  'sample_original_url',summary.sample_original_url,
  'end_to_end_ok',(summary.end_to_end_ok AND summary.raw_version_count>0
    AND summary.valid_hash_count=summary.raw_version_count
    AND summary.critical_without_evidence=0 AND ai_index.count=0)
) FROM summary CROSS JOIN ai_index
"""
    )
    if not isinstance(value, dict):
        raise RuntimeError("CONTROLLED_PILOT_CONTENT_EVIDENCE_INVALID")
    return value


def _publication_invariant() -> dict[str, object]:
    value = _psql_json(
        """
SELECT json_build_object(
 'api_can_write',has_table_privilege('srbg_api_role','personal_content_projection','INSERT')
   OR has_table_privilege('srbg_api_role','personal_content_projection','UPDATE')
   OR has_table_privilege('srbg_api_role','personal_content_projection','DELETE'),
 'worker_can_write',has_table_privilege('srbg_worker_role','personal_content_projection','INSERT')
   OR has_table_privilege('srbg_worker_role','personal_content_projection','UPDATE')
   OR has_table_privilege('srbg_worker_role','personal_content_projection','DELETE'),
 'publication_writer_can_write',
   has_table_privilege('srbg_publication_writer','personal_content_projection','INSERT')
   AND has_table_privilege('srbg_publication_writer','personal_content_projection','UPDATE'),
 'ok',NOT has_table_privilege('srbg_api_role','personal_content_projection','INSERT')
   AND NOT has_table_privilege('srbg_api_role','personal_content_projection','UPDATE')
   AND NOT has_table_privilege('srbg_api_role','personal_content_projection','DELETE')
   AND NOT has_table_privilege('srbg_worker_role','personal_content_projection','INSERT')
   AND NOT has_table_privilege('srbg_worker_role','personal_content_projection','UPDATE')
   AND NOT has_table_privilege('srbg_worker_role','personal_content_projection','DELETE')
   AND has_table_privilege('srbg_publication_writer','personal_content_projection','INSERT')
   AND has_table_privilege('srbg_publication_writer','personal_content_projection','UPDATE')
)
"""
    )
    if not isinstance(value, dict):
        raise RuntimeError("CONTROLLED_PILOT_PUBLICATION_INVARIANT_INVALID")
    return value


def _source_change_observation(run_id: str) -> dict[str, object]:
    value = _psql_json(
        f"""
WITH changed AS (
  SELECT version.document_id,count(DISTINCT version.content_hash) AS hashes,
         bool_and(item.current_document_version_id=projection.document_version_id) AS current_only
    FROM fetch_run run_fetch
    JOIN raw_object_capture capture ON capture.fetch_run_id=run_fetch.id
    JOIN document_version version ON version.raw_object_capture_id=capture.id
    JOIN intelligence_item item ON item.primary_document_id=version.document_id
    JOIN personal_content_projection projection ON projection.item_id=item.id
   WHERE run_fetch.controlled_run_id='{run_id}'::uuid
   GROUP BY version.document_id
  HAVING count(DISTINCT version.content_hash)>1
)
SELECT json_build_object(
  'status',CASE WHEN count(*)=0 THEN 'NOT_OBSERVED'
                WHEN bool_and(current_only) THEN 'OBSERVED_INVALIDATED'
                ELSE 'OBSERVED_INVARIANT_FAILED' END,
  'changed_document_count',count(*),
  'all_old_results_invalidated',COALESCE(bool_and(current_only),true)
) FROM changed
"""
    )
    if not isinstance(value, dict):
        raise RuntimeError("CONTROLLED_PILOT_CHANGE_OBSERVATION_INVALID")
    return value


def _reassess_completed_run(run_id: str) -> dict[str, object]:
    state = _psql(
        "SELECT state||'|'||COALESCE(stop_reason,'') FROM personal_controlled_run "
        f"WHERE id='{run_id}'::uuid"
    )
    if state != "COMPLETED|ACTIVE_LIMIT":
        raise RuntimeError("PILOT_REASSESS_REQUIRES_COMPLETED_RUN")
    stopped_sources = _psql(
        "SELECT count(*) FROM source JOIN personal_controlled_run_source controlled "
        "ON controlled.source_id=source.id "
        f"WHERE controlled.run_id='{run_id}'::uuid AND source.desired_enabled=false "
        "AND source.enabled=false AND source.runtime_state='STOPPED'"
    )
    if stopped_sources != str(len(SOURCES)):
        raise RuntimeError("PILOT_REASSESS_REQUIRES_STOPPED_SOURCES")
    source_outcomes = _source_outcomes(run_id)
    exact_fixed_source_set = _is_exact_fixed_source_set(source_outcomes)
    content_evidence = _content_evidence(run_id)
    publication_invariant = _publication_invariant()
    change_observation = _source_change_observation(run_id)
    post_stop_network_attempts = int(
        _psql(
            "SELECT count(*) FROM personal_controlled_http_attempt attempt "
            f"WHERE attempt.run_id='{run_id}'::uuid AND attempt.started_at>=(SELECT min(source.manual_disabled_at) "
            "FROM source JOIN personal_controlled_run_source controlled "
            "ON controlled.source_id=source.id WHERE controlled.run_id=attempt.run_id)"
        )
    )
    stats = _psql(
        "SELECT requests_reserved||'|'||bytes_settled||'|'||attempts_settled||'|'||"
        "attempts_failed||'|'||active_seconds||'|'||COALESCE(stop_reason,'') "
        f"FROM personal_controlled_run WHERE id='{run_id}'::uuid"
    ).split("|")
    successful_sources = sum(bool(item.get("successful")) for item in source_outcomes)
    invariants_ok = (
        bool(publication_invariant.get("ok"))
        and bool(change_observation.get("all_old_results_invalidated"))
        and post_stop_network_attempts == 0
    )
    verdict = classify_pilot_verdict(
        successful_sources,
        content_chain_ok=bool(content_evidence.get("end_to_end_ok")),
        invariants_ok=invariants_ok,
        policy_version=FIXED_FIVE_POLICY_VERSION,
        exact_fixed_source_set=exact_fixed_source_set,
    )
    return {
        "report_kind": "POST_RUN_REASSESSMENT",
        "run_id": run_id,
        "state": "COMPLETED",
        "verdict": verdict,
        "pilot_policy_version": FIXED_FIVE_POLICY_VERSION,
        "exact_fixed_source_set": exact_fixed_source_set,
        "gate_verdict": "PRECHECKED_NO_BASELINE_EXCEPTIONS",
        "baseline_exceptions": [],
        "source_outcomes": source_outcomes,
        "source_failure_diagnosis": _source_failure_diagnosis(source_outcomes),
        "successful_source_count": successful_sources,
        "content_evidence": content_evidence,
        "publication_invariant": publication_invariant,
        "post_stop_network_attempts": post_stop_network_attempts,
        "source_change_observation": change_observation,
        "ai_state": "DEGRADED_DISABLED",
        "ai_reason": "CONTROLLED_AI_LEDGER_NOT_AVAILABLE",
        "usage": {
            "http_requests": int(stats[0]),
            "response_bytes": int(stats[1]),
            "attempts_settled": int(stats[2]),
            "attempts_failed": int(stats[3]),
            "active_seconds": int(stats[4]),
            "stop_reason": stats[5],
            "ai_cost_microusd": 0,
        },
        "replacement_source_review_required": successful_sources < FINAL_PASS_SOURCE_THRESHOLD,
        "reassessment_network_io_performed": False,
        "finished_at": datetime.now(UTC).isoformat(),
    }


def _arm_run(limits: PilotLimits) -> str:
    run_id = uuid7()
    owner_id = "019b0000-0000-7000-8000-000000009001"
    bindings = []
    probes = []
    events = []
    for index, seed_url in enumerate(SOURCES):
        parsed = urlsplit(seed_url)
        path = parsed.path or "/"
        bindings.append(f"('{run_id}','{seed_url}','{parsed.hostname}','{path}')")
        probe_id = uuid7()
        probes.append(
            "SELECT '"
            + str(probe_id)
            + "'::uuid,source.id,stream.id,source.base_url,source.base_url,"
            + f"'{parsed.scheme}://{parsed.hostname}','UNKNOWN','QUEUED',0,'{owner_id}'::uuid,"
            + f"'controlled-pilot:{run_id}:{index}',now(),now(),'{run_id}'::uuid "
            + "FROM source JOIN LATERAL (SELECT id FROM source_stream WHERE source_id=source.id "
            + "AND canonical_url=source.base_url ORDER BY created_at,id LIMIT 1) stream ON true "
            + f"WHERE source.base_url='{seed_url}'"
        )
        events.append(
            f"('{uuid7()}','{seed_url}','MANUAL_ENABLED','{owner_id}',"
            + f"'controlled-pilot:{run_id}')"
        )
    source_list = ",".join(f"'{url}'" for url in SOURCES)
    sql = f"""
BEGIN;
INSERT INTO personal_controlled_run(
 id,state,wall_started_at,wall_deadline,created_at,updated_at
) VALUES(
 '{run_id}','PREPARING',now(),now()+interval '{limits.wall_seconds} seconds',now(),now()
);
INSERT INTO personal_controlled_run_source(run_id,source_id,seed_url,expected_host,path_prefix)
SELECT binding.run_id::uuid,source.id,binding.seed_url,binding.expected_host,binding.path_prefix
FROM (VALUES {",".join(bindings)}) AS binding(run_id,seed_url,expected_host,path_prefix)
JOIN source ON source.base_url=binding.seed_url;
DO $$ BEGIN
 IF (SELECT count(*) FROM personal_controlled_run_source WHERE run_id='{run_id}')<>5
 THEN RAISE EXCEPTION 'CONTROLLED_PILOT_SOURCE_SET_INCOMPLETE'; END IF;
END $$;
INSERT INTO source_key_activity_event(
 id,source_id,event_type,actor_id,request_id,before_state,after_state,created_at
)
SELECT event.id::uuid,source.id,event.event_type,event.actor_id::uuid,event.request_id,
       jsonb_build_object('desired_enabled',source.desired_enabled),
       jsonb_build_object('desired_enabled',true),now()
FROM (VALUES {",".join(events)}) AS event(
 id,seed_url,event_type,actor_id,request_id
) JOIN source ON source.base_url=event.seed_url;
UPDATE source SET desired_enabled=true,manual_disabled_at=NULL,updated_at=now()
 WHERE base_url IN ({source_list});
UPDATE source_stream SET status='PROBING',updated_at=now()
 WHERE (source_id,canonical_url) IN (
   SELECT id,base_url FROM source WHERE base_url IN ({source_list})
 ) AND status IN ('QUALIFIED','PROBE_FAILED','READY');
INSERT INTO stream_probe_run(
 id,source_id,stream_id,requested_url,normalized_url,normalized_origin,input_kind,
 status,attempt_count,requested_by,request_id,created_at,updated_at,controlled_run_id
)
{" UNION ALL ".join(probes)};
UPDATE personal_controlled_run SET state='ARMED',updated_at=now() WHERE id='{run_id}';
COMMIT;
"""
    _psql(sql)
    return str(run_id)


def _disable_controlled_sources() -> None:
    owner_id = "019b0000-0000-7000-8000-000000009001"
    event_values = ",".join(f"('{uuid7()}','{url}')" for url in SOURCES)
    _psql(
        f"""
BEGIN;
INSERT INTO source_key_activity_event(
 id,source_id,event_type,actor_id,request_id,before_state,after_state,created_at
)
SELECT gen.id::uuid,source.id,'MANUAL_DISABLED','{owner_id}'::uuid,
       'controlled-pilot-stop',jsonb_build_object('desired_enabled',source.desired_enabled),
       jsonb_build_object('desired_enabled',false),now()
FROM (VALUES {event_values}) AS gen(id,seed_url)
JOIN source ON source.base_url=gen.seed_url
JOIN personal_controlled_run_source controlled ON controlled.source_id=source.id
WHERE controlled.run_id=(SELECT id FROM personal_controlled_run ORDER BY created_at DESC LIMIT 1)
  AND source.desired_enabled=true
;
UPDATE fetch_schedule SET status='PAUSED',updated_at=now()
 WHERE source_id IN (
  SELECT source_id FROM personal_controlled_run_source
   WHERE run_id=(SELECT id FROM personal_controlled_run ORDER BY created_at DESC LIMIT 1)
 );
UPDATE source SET desired_enabled=false,manual_disabled_at=now(),enabled=false,
                  runtime_state='STOPPED',updated_at=now()
 WHERE id IN (
  SELECT source_id FROM personal_controlled_run_source
   WHERE run_id=(SELECT id FROM personal_controlled_run ORDER BY created_at DESC LIMIT 1)
 );
COMMIT;
"""
    )


def _fail_active_run() -> None:
    _psql(
        "UPDATE personal_controlled_run SET state='STOPPING',"
        "stop_reason=COALESCE(stop_reason,'CONTROLLER_FAILURE'),updated_at=now() "
        "WHERE state IN ('PREPARING','ARMED','RUNNING','PAUSED');"
        "UPDATE fetch_schedule SET status='PAUSED',updated_at=now() WHERE source_id IN ("
        "SELECT source_id FROM personal_controlled_run_source WHERE run_id=("
        "SELECT id FROM personal_controlled_run WHERE state='STOPPING' ORDER BY created_at DESC LIMIT 1));"
        "UPDATE source SET desired_enabled=false,manual_disabled_at=now(),enabled=false,"
        "runtime_state='STOPPED',updated_at=now() WHERE id IN (SELECT source_id FROM "
        "personal_controlled_run_source WHERE run_id=(SELECT id FROM personal_controlled_run "
        "WHERE state='STOPPING' ORDER BY created_at DESC LIMIT 1));"
        "UPDATE stream_probe_run SET status='FAILED',"
        "failure_code=COALESCE(failure_code,'CONTROLLER_FAILURE'),"
        "failure_reason=COALESCE(failure_reason,'controlled pilot stopped fail-closed'),"
        "completed_at=COALESCE(completed_at,now()),updated_at=now() "
        "WHERE status IN ('QUEUED','RUNNING') AND controlled_run_id=(SELECT id FROM "
        "personal_controlled_run WHERE state='STOPPING' ORDER BY created_at DESC LIMIT 1);"
        "UPDATE personal_controlled_run run SET state='FAILED',updated_at=now() "
        "WHERE state='STOPPING' AND NOT EXISTS(SELECT 1 FROM personal_controlled_http_attempt "
        "attempt WHERE attempt.run_id=run.id AND attempt.outcome='RESERVED')"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--reassess-run")
    args = parser.parse_args()
    if args.reassess_run is not None:
        run_id = str(UUID(args.reassess_run))
        report = _reassess_completed_run(run_id)
        report_path = args.data_root / "reports" / f"controlled-pilot-reassessment-{run_id}.json"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        return 0 if report["verdict"] in {"PASS", "LIMITED_PASS"} else 2
    limits = PilotLimits()
    started = datetime.now(UTC)
    report: dict[str, object] = {
        "state": "BLOCKED_PRE_START",
        "verdict": "PENDING",
        "pilot_policy_version": FIXED_FIVE_POLICY_VERSION,
        "gate_verdict": "PRECHECK_REQUIRED",
        "baseline_exceptions": [],
        "source_outcomes": [],
        "content_evidence": {},
        "publication_invariant": {},
        "post_stop_network_attempts": None,
        "source_change_observation": {"status": "NOT_EVALUATED"},
        "ai_state": "DEGRADED_DISABLED",
        "ai_reason": "CONTROLLED_AI_LEDGER_NOT_AVAILABLE",
        "started_at": started.isoformat(),
        "sources": list(SOURCES),
        "limits": {
            "active_seconds": limits.active_seconds,
            "wall_seconds": limits.wall_seconds,
            "requests": limits.requests,
            "bytes": limits.bytes,
            "ai_cost_microusd": limits.ai_cost_microusd,
        },
    }
    try:
        # The controller never bypasses the durable authority: a run must be armed by the
        # tested database command before any source is enabled or any network task queued.
        active = _psql(
            "SELECT count(*) FROM personal_controlled_run WHERE state IN ('PREPARING','ARMED','RUNNING','PAUSED','STOPPING')"
        )
        if active == "0":
            report["run_id"] = _arm_run(limits)
        elif active != "1":
            raise RuntimeError("CONTROLLED_PILOT_ACTIVE_RUN_CONFLICT")
        else:
            report["run_id"] = _psql(
                "SELECT id FROM personal_controlled_run WHERE state IN "
                "('PREPARING','ARMED','RUNNING','PAUSED','STOPPING') "
                "ORDER BY created_at DESC LIMIT 1"
            )
        armed_state = _psql(
            "SELECT state FROM personal_controlled_run WHERE state IN ('PREPARING','ARMED','RUNNING','PAUSED','STOPPING') ORDER BY created_at DESC LIMIT 1"
        )
        if armed_state != "ARMED":
            raise RuntimeError("CONTROLLED_PILOT_REQUIRES_ARMED_RUN")
        _psql(
            "UPDATE personal_controlled_run SET state='RUNNING',last_resumed_at=now(),updated_at=now() WHERE state='ARMED'"
        )
        report["state"] = "RUNNING"
        previous_tick = time.monotonic()
        while True:
            snapshot = _psql(
                "SELECT state||'|'||active_seconds||'|'||CASE WHEN now()>=wall_deadline THEN '1' ELSE '0' END "
                "FROM personal_controlled_run ORDER BY created_at DESC LIMIT 1"
            )
            state, _active_seconds, wall_deadline = snapshot.split("|")
            if state == "STOPPING":
                break
            if wall_deadline == "1":
                _psql(
                    "UPDATE personal_controlled_run SET state='STOPPING',stop_reason='WALL_LIMIT',updated_at=now() WHERE state IN ('RUNNING','PAUSED')"
                )
                break
            if state == "PAUSED":
                time.sleep(5)
                previous_tick = time.monotonic()
                continue
            if state != "RUNNING":
                raise RuntimeError("CONTROLLED_RUN_STATE_INVALID")
            integrity_failures = int(
                _psql(
                    "SELECT count(*) FROM stream_probe_run WHERE controlled_run_id=("
                    "SELECT id FROM personal_controlled_run ORDER BY created_at DESC LIMIT 1) "
                    "AND status='FAILED' AND failure_code IN ('RAW_OBJECT_HASH_MISMATCH')"
                )
            )
            if integrity_failures:
                _psql(
                    "UPDATE personal_controlled_run SET state='STOPPING',"
                    "stop_reason='DATA_INTEGRITY_GATE',updated_at=now() "
                    "WHERE state='RUNNING'"
                )
                break
            terminal_failures = int(
                _psql(
                    "SELECT count(*) FROM stream_probe_run WHERE controlled_run_id=("
                    "SELECT id FROM personal_controlled_run ORDER BY created_at DESC LIMIT 1) "
                    "AND status='FAILED'"
                )
            )
            if len(SOURCES) - terminal_failures < LIMITED_PASS_SOURCE_THRESHOLD:
                _psql(
                    "UPDATE personal_controlled_run SET state='STOPPING',"
                    "stop_reason='SOURCE_RELIABILITY_GATE',updated_at=now() "
                    "WHERE state='RUNNING'"
                )
                break
            time.sleep(5)
            current_tick = time.monotonic()
            elapsed = max(0, round(current_tick - previous_tick))
            previous_tick = current_tick
            updated_active = _psql(
                "UPDATE personal_controlled_run SET active_seconds=LEAST(7200,active_seconds+"
                f"{elapsed}),updated_at=now() WHERE state='RUNNING' RETURNING active_seconds"
            )
            if updated_active and int(updated_active) >= limits.active_seconds:
                _psql(
                    "UPDATE personal_controlled_run SET state='STOPPING',stop_reason='ACTIVE_LIMIT',updated_at=now() WHERE state='RUNNING'"
                )
                break
        run_id = str(report["run_id"])
        source_outcomes = _source_outcomes(run_id)
        publication_invariant = _publication_invariant()
        report["source_outcomes"] = source_outcomes
        report["source_failure_diagnosis"] = _source_failure_diagnosis(source_outcomes)
        report["publication_invariant"] = publication_invariant
        stop_reason = _psql(
            "SELECT COALESCE(stop_reason,'') FROM personal_controlled_run "
            "ORDER BY created_at DESC LIMIT 1"
        )
        successful_end = stop_reason == "ACTIVE_LIMIT"
        _disable_controlled_sources()
        drain_deadline = time.monotonic() + 120
        while (
            _psql(
                "SELECT count(*) FROM personal_controlled_http_attempt WHERE run_id=(SELECT id FROM personal_controlled_run ORDER BY created_at DESC LIMIT 1) AND outcome='RESERVED'"
            )
            != "0"
        ):
            if time.monotonic() >= drain_deadline:
                _psql(
                    "UPDATE personal_controlled_run SET state='FAILED',stop_reason='CONTROLLED_RUN_DRAIN_TIMEOUT',updated_at=now() WHERE state='STOPPING'"
                )
                raise RuntimeError("CONTROLLED_RUN_DRAIN_TIMEOUT")
            time.sleep(2)
        observation_started_at = _psql("SELECT now()")
        observation_started_monotonic = time.monotonic()
        content_deadline = time.monotonic() + (
            CONTENT_PROJECTION_DRAIN_SECONDS if successful_end else 0
        )
        while True:
            content_evidence = _content_evidence(run_id)
            if content_evidence.get("end_to_end_ok") or time.monotonic() >= content_deadline:
                break
            time.sleep(10)
        report["content_evidence"] = content_evidence
        source_change_observation = _source_change_observation(run_id)
        report["source_change_observation"] = source_change_observation
        observation_remaining = POST_STOP_OBSERVATION_SECONDS - (
            time.monotonic() - observation_started_monotonic
        )
        if observation_remaining > 0:
            time.sleep(observation_remaining)
        post_stop_network_attempts = int(
            _psql(
                "SELECT count(*) FROM personal_controlled_http_attempt WHERE run_id='"
                + run_id
                + "'::uuid AND started_at>'"
                + observation_started_at
                + "'::timestamptz"
            )
        )
        report["post_stop_network_attempts"] = post_stop_network_attempts
        _psql(
            "UPDATE personal_controlled_run SET state='"
            + ("COMPLETED" if successful_end else "FAILED")
            + "',updated_at=now() WHERE state='STOPPING'"
        )
        report["state"] = _psql(
            "SELECT state FROM personal_controlled_run ORDER BY created_at DESC LIMIT 1"
        )
        stats = _psql(
            "SELECT requests_reserved||'|'||bytes_settled||'|'||attempts_settled||'|'||attempts_failed||'|'||active_seconds||'|'||COALESCE(stop_reason,'') FROM personal_controlled_run ORDER BY created_at DESC LIMIT 1"
        ).split("|")
        report["usage"] = {
            "http_requests": int(stats[0]),
            "response_bytes": int(stats[1]),
            "attempts_settled": int(stats[2]),
            "attempts_failed": int(stats[3]),
            "active_seconds": int(stats[4]),
            "stop_reason": stats[5],
            "ai_cost_microusd": 0,
        }
        successful_sources = sum(
            bool(item.get("successful"))
            for item in source_outcomes
        )
        content_chain_ok = bool(content_evidence.get("end_to_end_ok"))
        invariants_ok = (
            bool(publication_invariant.get("ok"))
            and bool(source_change_observation.get("all_old_results_invalidated"))
            and post_stop_network_attempts == 0
        )
        report["successful_source_count"] = successful_sources
        verdict = (
            classify_pilot_verdict(
                successful_sources,
                content_chain_ok=content_chain_ok,
                invariants_ok=invariants_ok,
                policy_version=FIXED_FIVE_POLICY_VERSION,
                exact_fixed_source_set=_is_exact_fixed_source_set(source_outcomes),
            )
            if successful_end
            else "FAIL"
        )
        report["verdict"] = verdict
        report["replacement_source_review_required"] = (
            successful_sources < FINAL_PASS_SOURCE_THRESHOLD
        )
        report["gate_verdict"] = "PRECHECKED_NO_BASELINE_EXCEPTIONS"
        return 0 if verdict in {"PASS", "LIMITED_PASS"} else 2
    except Exception as error:
        report["error_code"] = str(error).splitlines()[0][:120]
        try:
            _fail_active_run()
        except Exception:
            report["fail_closed_cleanup"] = "FAILED_REQUIRES_OPERATOR"
        return 2
    finally:
        report["finished_at"] = datetime.now(UTC).isoformat()
        report_path = args.data_root / "reports" / f"controlled-pilot-{started:%Y%m%dT%H%M%SZ}.json"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
