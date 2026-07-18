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

from srbg_api.identifiers import uuid7

SOURCES = (
    "https://www.gov.cn/zhengce/",
    "https://www.mot.gov.cn/",
    "https://xxgk.mot.gov.cn/",
    "https://jtt.sc.gov.cn/",
    "https://www.mem.gov.cn/gk/sgcc/tbzdsgdcbg/",
)


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
    return completed.stdout.strip()


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
            + f"source.normalized_origin,'UNKNOWN','QUEUED',0,'{owner_id}'::uuid,"
            + f"'controlled-pilot:{run_id}:{index}',now(),now(),'{run_id}'::uuid "
            + "FROM source JOIN LATERAL (SELECT id FROM source_stream WHERE source_id=source.id "
            + "AND canonical_url=source.base_url ORDER BY created_at,id LIMIT 1) stream ON true "
            + f"WHERE source.base_url='{seed_url}'"
        )
        events.append(
            f"('{uuid7()}','{seed_url}','MANUAL_ENABLED','{owner_id}',"
            + f"'controlled-pilot:{run_id}',jsonb_build_object('desired_enabled',source.desired_enabled),"
            + "jsonb_build_object('desired_enabled',true),now())"
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
       event.before_state,event.after_state,event.created_at
FROM (VALUES {",".join(events)}) AS event(
 id,seed_url,event_type,actor_id,request_id,before_state,after_state,created_at
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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", type=Path, required=True)
    args = parser.parse_args()
    limits = PilotLimits()
    started = datetime.now(UTC)
    report = {
        "state": "BLOCKED_PRE_START",
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
        stop_reason = _psql(
            "SELECT COALESCE(stop_reason,'') FROM personal_controlled_run ORDER BY created_at DESC LIMIT 1"
        )
        successful_end = stop_reason == "ACTIVE_LIMIT"
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
        return 0 if report["state"] == "COMPLETED" else 2
    except Exception as error:
        report["error_code"] = str(error).splitlines()[0][:120]
        return 2
    finally:
        report["finished_at"] = datetime.now(UTC).isoformat()
        report_path = args.data_root / "reports" / f"controlled-pilot-{started:%Y%m%dT%H%M%SZ}.json"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
