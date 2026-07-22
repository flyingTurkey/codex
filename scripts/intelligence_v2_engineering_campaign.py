# ruff: noqa: E501,S607
"""Run and export a fail-closed intelligence-v2 engineering campaign.

The database and ignored evidence directory are the only durable runtime outputs.
No credential value or source body is written to evidence.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import posixpath
import shutil
import subprocess
import sys
import time
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path
from typing import cast
from urllib.parse import urlsplit, urlunsplit
from uuid import UUID

import aioboto3
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, create_async_engine
from srbg_api.auth import LOCAL_USER_ID
from srbg_api.identifiers import uuid7
from srbg_api.intelligence_v2.campaign import (
    CampaignAction,
    CampaignPhase,
    CampaignSnapshot,
    decide_transition,
)
from srbg_api.source_registry.v2_rollout import (
    SourceAdmissionMetrics,
    append_production_admission_assessment,
    review_gate_result,
)

ROOT = Path(__file__).resolve().parents[1]
ROSTER_PATH = ROOT / "docs/codex-kit/assets/validation/civil_engineering_source_campaign_v2.json"
ROLLOUT_PATH = ROOT / "docs/codex-kit/assets/validation/civil_engineering_source_rollout_v2.json"
DEFAULT_EVIDENCE_ROOT = ROOT / ".cache/intelligence-v2-evidence"
MIGRATION_HEAD = "0039_t04_content_candidates"
SERVICES = (
    "api",
    "worker",
    "personal-source-worker",
    "parser",
    "publisher",
    "scheduler",
    "ai-worker",
    "source-discovery",
)
GATES = (
    "lint",
    "typecheck",
    "test",
    "contract-test",
    "security-check",
    "fixture-replay",
    "quality-gate",
    "web-e2e",
    "web-a11y",
)
PHASE_EVENTS = {
    "PREPARED": CampaignPhase.PREPARED,
    "STARTED": CampaignPhase.STARTED,
    "FINALIZED": CampaignPhase.FINALIZED,
    "RESTORED": CampaignPhase.RESTORED,
}
CURRENT_EVIDENCE_FILES = (
    "runtime.jsonl",
    "feed.jsonl",
    "sources.json",
    "engineering.json",
    "compensation.json",
    "preflight.json",
    "context.json",
    "historical_budget.json",
)


def _canonical(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )


def _write_json(path: Path, value: object) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(payload, encoding="utf-8")
    temporary.replace(path)
    return sha256(payload.encode("utf-8")).hexdigest()


def _write_jsonl(path: Path, rows: Iterable[dict[str, object]]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = "".join(
        json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
        for row in rows
    )
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(payload, encoding="utf-8")
    temporary.replace(path)
    return sha256(payload.encode("utf-8")).hexdigest()


def _publish_current_evidence(root: Path, campaign_root: Path) -> None:
    """Expose one explicit campaign to the plain closeout command without mixing runs."""

    _write_json(
        root / "active-campaign.json",
        {"campaign_id": campaign_root.name, "evidence_path": campaign_root.name},
    )
    for name in CURRENT_EVIDENCE_FILES:
        source = campaign_root / name
        target = root / name
        if source.is_file():
            shutil.copy2(source, target)
        else:
            target.unlink(missing_ok=True)
    (root / "readiness.json").unlink(missing_ok=True)


def _run(
    command: list[str], *, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603
        command,
        cwd=ROOT,
        env=env,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def _git_commit() -> str:
    return _run(["git", "rev-parse", "HEAD"]).stdout.strip()


def _container_name(service: str) -> str:
    return f"srbg-intelligence-{service}-1"


def _service_environment(service: str) -> str | None:
    result = _run(
        [
            "docker",
            "inspect",
            _container_name(service),
            "--format",
            "{{json .Config.Env}}",
        ]
    )
    values = json.loads(result.stdout)
    keys = ("SRBG_AI_ENVIRONMENT=",) if service == "ai-worker" else ("SRBG_ENVIRONMENT=",)
    for value in values:
        for key in keys:
            if str(value).startswith(key):
                return str(value).removeprefix(key)
    return None


def _discover_database_url(variable: str) -> str:
    result = _run(
        [
            "docker",
            "inspect",
            _container_name("api"),
            "--format",
            "{{json .Config.Env}}",
        ]
    )
    internal = next(
        (
            str(value).removeprefix(f"{variable}=")
            for value in json.loads(result.stdout)
            if str(value).startswith(f"{variable}=")
        ),
        "",
    )
    if not internal:
        raise RuntimeError("CAMPAIGN_DATABASE_URL_REQUIRED")
    port_result = _run(["docker", "port", _container_name("postgres"), "5432"])
    host_port = port_result.stdout.strip().rsplit(":", 1)[-1]
    parsed = urlsplit(internal)
    if parsed.hostname != "postgres" or not parsed.username or parsed.password is None:
        raise RuntimeError("CAMPAIGN_DATABASE_URL_INVALID")
    userinfo = f"{parsed.username}:{parsed.password}"
    return urlunsplit((parsed.scheme, f"{userinfo}@127.0.0.1:{host_port}", parsed.path, "", ""))


def _compose_environment(environment: str) -> dict[str, str]:
    process = dict(os.environ)
    process["SRBG_ENVIRONMENT"] = environment
    process["SRBG_SOURCE_DISCOVERY_ENABLED"] = "true" if environment == "acceptance" else "false"
    if not process.get("SRBG_DATA_ROOT"):
        mounts = json.loads(
            _run(
                [
                    "docker",
                    "inspect",
                    _container_name("postgres"),
                    "--format",
                    "{{json .Mounts}}",
                ]
            ).stdout
        )
        postgres_mount = next(
            mount for mount in mounts if mount.get("Destination") == "/var/lib/postgresql/data"
        )
        process["SRBG_DATA_ROOT"] = posixpath.dirname(str(postgres_mount["Source"]))
    return process


def _switch_services(environment: str) -> None:
    compose = [
        "docker",
        "compose",
        "--project-directory",
        str(ROOT),
        "-f",
        str(ROOT / "infra/compose/compose.yaml"),
    ]
    _run(
        [
            *compose,
            "build",
            "migrate",
        ],
        env=_compose_environment(environment),
    )
    command = [
        *compose,
        "up",
        "-d",
        "--build",
        "--no-deps",
        "--force-recreate",
        *SERVICES,
    ]
    _run(command, env=_compose_environment(environment))


def _dispatch_canary() -> None:
    _run(
        [
            "docker",
            "exec",
            _container_name("worker"),
            "celery",
            "-A",
            "srbg_worker.app:celery_app",
            "call",
            "srbg.ai.v2_canary_dispatch",
            "--queue",
            "celery",
        ]
    )


def _dispatch_fault_injection(campaign_id: UUID, fault_kind: str) -> None:
    _run(
        [
            "docker",
            "exec",
            _container_name("worker"),
            "celery",
            "-A",
            "srbg_worker.app:celery_app",
            "call",
            "srbg.ai.v2_campaign_fault_injection",
            "--queue",
            "celery",
            "--kwargs",
            json.dumps(
                {"campaign_id": str(campaign_id), "fault_kind": fault_kind},
                separators=(",", ":"),
            ),
        ]
    )


def _roster() -> list[dict[str, str]]:
    value = json.loads(ROSTER_PATH.read_text(encoding="utf-8"))
    return cast(list[dict[str, str]], value["sources"])


def _rollout_positions() -> dict[str, tuple[int, int]]:
    rollout = json.loads(ROLLOUT_PATH.read_text(encoding="utf-8"))
    return {
        str(institution): (batch_index, index // 2 + 1)
        for batch_index, batch in enumerate(rollout["batches"], 1)
        for index, institution in enumerate(batch["institutions"])
    }


class CampaignRepository:
    def __init__(self, engine: AsyncEngine, evidence_engine: AsyncEngine) -> None:
        self._engine = engine
        self._evidence_engine = evidence_engine

    async def close(self) -> None:
        await self._engine.dispose()
        await self._evidence_engine.dispose()

    async def migration_head(self) -> str:
        async with self._engine.connect() as connection:
            value = await connection.scalar(text("SELECT version_num FROM alembic_version"))
        return str(value or "")

    async def create(self, campaign_id: UUID, baseline: str, environment: str) -> None:
        now = datetime.now(UTC)
        async with self._engine.begin() as connection:
            await connection.execute(
                text(
                    "INSERT INTO engineering_closeout_campaign_v2("
                    "id,acceptance_profile,baseline_commit,migration_head,environment,created_at) "
                    "VALUES(:id,'ENGINEERING_CLOSEOUT',:baseline,:head,:environment,:now)"
                ),
                {
                    "id": campaign_id,
                    "baseline": baseline,
                    "head": MIGRATION_HEAD,
                    "environment": environment,
                    "now": now,
                },
            )
            await self._append_event(
                connection,
                campaign_id,
                "PREPARED",
                {"environment": environment},
                now,
            )

    async def _append_event(
        self,
        connection: AsyncConnection,
        campaign_id: UUID,
        event_type: str,
        payload: dict[str, object],
        occurred_at: datetime | None = None,
    ) -> None:
        payload_text = _canonical(payload).decode("utf-8")
        await connection.execute(
            text(
                "INSERT INTO engineering_closeout_campaign_event_v2("
                "id,campaign_id,event_type,payload,payload_sha256,occurred_at) "
                "VALUES(:id,:campaign,:event,CAST(:payload AS jsonb),:hash,:now) "
                "ON CONFLICT(campaign_id,event_type,payload_sha256) DO NOTHING"
            ),
            {
                "id": uuid7(),
                "campaign": campaign_id,
                "event": event_type,
                "payload": payload_text,
                "hash": sha256(payload_text.encode("utf-8")).hexdigest(),
                "now": occurred_at or datetime.now(UTC),
            },
        )

    async def append_event(
        self, campaign_id: UUID, event_type: str, payload: dict[str, object]
    ) -> None:
        async with self._engine.begin() as connection:
            await self._append_event(connection, campaign_id, event_type, payload)

    async def snapshot(self, campaign_id: UUID) -> CampaignSnapshot:
        async with self._engine.connect() as connection:
            row = (
                (
                    await connection.execute(
                        text(
                            "SELECT event_type,occurred_at FROM engineering_closeout_campaign_event_v2 "
                            "WHERE campaign_id=:id AND event_type IN ('PREPARED','STARTED','FINALIZED','RESTORED') "
                            "ORDER BY occurred_at DESC,id DESC LIMIT 1"
                        ),
                        {"id": campaign_id},
                    )
                )
                .mappings()
                .one_or_none()
            )
        if row is None:
            raise ValueError("CAMPAIGN_NOT_FOUND")
        return CampaignSnapshot(PHASE_EVENTS[str(row["event_type"])], row["occurred_at"])

    async def event_time(self, campaign_id: UUID, event_type: str) -> datetime | None:
        async with self._engine.connect() as connection:
            return await connection.scalar(
                text(
                    "SELECT occurred_at FROM engineering_closeout_campaign_event_v2 "
                    "WHERE campaign_id=:id AND event_type=:event ORDER BY occurred_at LIMIT 1"
                ),
                {"id": campaign_id, "event": event_type},
            )

    async def campaign_context(self, campaign_id: UUID) -> dict[str, object]:
        async with self._engine.connect() as connection:
            row = (
                (
                    await connection.execute(
                        text(
                            "SELECT baseline_commit,migration_head,environment,created_at "
                            "FROM engineering_closeout_campaign_v2 WHERE id=:id"
                        ),
                        {"id": campaign_id},
                    )
                )
                .mappings()
                .one()
            )
        return dict(row)

    async def register_missing_sources(self, campaign_id: UUID) -> list[str]:
        registered: list[str] = []
        now = datetime.now(UTC)
        async with self._engine.begin() as connection:
            for source in _roster():
                exists = await connection.scalar(
                    text("SELECT id FROM source WHERE name=:name LIMIT 1"),
                    {"name": source["institution"]},
                )
                if exists is not None:
                    continue
                source_id = uuid7()
                await connection.execute(
                    text(
                        "SELECT register_source_candidate("
                        ":id,:name,:origin,'BOTH','official_public','A1','P2','auto_probe',"
                        "1440,'Local Personal Owner',NULL,ARRAY['CN']::text[],ARRAY[]::text[],"
                        "ARRAY['zh-CN']::text[],ARRAY['CIVIL_ENGINEERING']::text[],"
                        "ARRAY['INTELLIGENCE']::text[],ARRAY['PRIMARY_SOURCE']::text[],"
                        ":actor,:request,:audit,:now)"
                    ),
                    {
                        "id": source_id,
                        "name": source["institution"],
                        "origin": source["official_origin"],
                        "actor": LOCAL_USER_ID,
                        "request": f"engineering-campaign:{campaign_id}",
                        "audit": uuid7(),
                        "now": now,
                    },
                )
                registered.append(source["institution"])
        return registered

    async def source_intent(self) -> list[dict[str, object]]:
        names = [source["institution"] for source in _roster()]
        async with self._engine.connect() as connection:
            rows = (
                (
                    await connection.execute(
                        text(
                            "SELECT id::text,name,desired_enabled,runtime_state FROM source "
                            "WHERE name=ANY(:names) ORDER BY name"
                        ),
                        {"names": names},
                    )
                )
                .mappings()
                .all()
            )
        return [dict(row) for row in rows]

    async def assess_sources(
        self, campaign_id: UUID, started_at: datetime, ended_at: datetime
    ) -> None:
        if ended_at - started_at < timedelta(hours=1):
            return
        cutoff = started_at
        async with self._engine.begin() as connection:
            for roster_source in _roster():
                row = (
                    (
                        await connection.execute(
                            text("SELECT id FROM source WHERE name=:name LIMIT 1"),
                            {"name": roster_source["institution"]},
                        )
                    )
                    .mappings()
                    .one()
                )
                already = await connection.scalar(
                    text(
                        "SELECT 1 FROM source_admission_assessment_v2 "
                        "WHERE source_id=:source AND rule_version="
                        "'civil-source-rollout-v2-engineering-1.0.0' "
                        "AND evidence_refs->>'campaign_id'=:campaign LIMIT 1"
                    ),
                    {"source": row["id"], "campaign": str(campaign_id)},
                )
                if already:
                    continue
                samples = (
                    (
                        await connection.execute(
                            text(
                                "WITH unique_documents AS (SELECT DISTINCT ON (item.current_document_version_id) "
                                "item.current_document_version_id::text AS document_version_id,"
                                "item.original_url,item.source_published_at,dv.content_hash,raw.sha256 AS raw_sha256,"
                                "item.title FROM intelligence_item item "
                                "JOIN document_version dv ON dv.id=item.current_document_version_id "
                                "JOIN raw_object raw ON raw.id=dv.raw_object_id "
                                "WHERE item.source_id=:source AND item.is_demo=false "
                                "AND item.source_published_at BETWEEN :lower AND :cutoff "
                                "AND raw.scan_status='CLEAN' ORDER BY item.current_document_version_id,"
                                "item.source_published_at DESC) SELECT * FROM unique_documents "
                                "ORDER BY source_published_at DESC,document_version_id DESC LIMIT 30"
                            ),
                            {
                                "source": row["id"],
                                "lower": cutoff - timedelta(days=90),
                                "cutoff": cutoff,
                            },
                        )
                    )
                    .mappings()
                    .all()
                )
                sample_ids = [str(sample["document_version_id"]) for sample in samples]
                sample_size = len(sample_ids)
                manifest_hash = sha256(_canonical(sample_ids)).hexdigest()
                health = (
                    (
                        await connection.execute(
                            text(
                                "SELECT count(*) AS total,count(*) FILTER(WHERE transport_status='SUCCEEDED') AS fetched,"
                                "COALESCE(avg(required_field_basis_points),0)::int AS metadata_bps,"
                                "COALESCE(avg(duplicate_basis_points),0)::int AS duplicate_bps "
                                "FROM source_health_snapshot WHERE source_id=:source "
                                "AND observed_at BETWEEN :start AND :end"
                            ),
                            {"source": row["id"], "start": started_at, "end": ended_at},
                        )
                    )
                    .mappings()
                    .one()
                )
                total = int(health["total"] or 0)
                fetched = int(health["fetched"] or 0)
                fetch_bps = fetched * 10_000 // total if total else 0
                policy = await connection.scalar(
                    text(
                        "SELECT document FROM source_policy WHERE source_id=:source "
                        "AND status='VALID' AND (valid_until IS NULL OR valid_until>=:cutoff) "
                        "ORDER BY created_at DESC,id DESC LIMIT 1"
                    ),
                    {"source": row["id"], "cutoff": cutoff},
                )
                policy_value = policy if isinstance(policy, dict) else {}
                robots = policy_value.get("robots_review")
                terms = policy_value.get("terms_review")
                copyright_value = policy_value.get("copyright")
                evidence_docs = 0
                useful_docs = 0
                if sample_ids:
                    evidence_docs = int(
                        await connection.scalar(
                            text(
                                "SELECT count(DISTINCT document_version_id) FROM claim_evidence "
                                "WHERE document_version_id::text=ANY(:ids)"
                            ),
                            {"ids": sample_ids},
                        )
                        or 0
                    )
                    useful_docs = int(
                        await connection.scalar(
                            text(
                                "SELECT count(DISTINCT document_version_id) FROM claim "
                                "WHERE document_version_id::text=ANY(:ids) "
                                "AND verification_status='ACCEPTED'"
                            ),
                            {"ids": sample_ids},
                        )
                        or 0
                    )
                metrics = SourceAdmissionMetrics(
                    sample_size=sample_size,
                    robots_allowed=review_gate_result(robots, allowed_results={"ALLOWED"}),
                    terms_allowed=review_gate_result(
                        terms, allowed_results={"ALLOWED", "NOT_PRESENT"}
                    ),
                    copyright_reviewed=review_gate_result(
                        copyright_value, allowed_results={"ALLOWED", "REVIEWED"}
                    ),
                    public_network_safe=total > 0 and fetched > 0,
                    fetch_success_bps=fetch_bps,
                    parse_evidence_success_bps=(
                        evidence_docs * 10_000 // sample_size if sample_size else 0
                    ),
                    metadata_success_bps=int(health["metadata_bps"] or 0),
                    useful_yield_bps=(useful_docs * 10_000 // sample_size if sample_size else 0),
                    duplicate_bps=int(health["duplicate_bps"] or 0),
                    hard_negative_leaks=0,
                    hard_negative_evaluated=False,
                )
                evidence_refs = {
                    "campaign_id": str(campaign_id),
                    "official_origin": roster_source["official_origin"],
                    "sample_document_version_ids_sha256": manifest_hash,
                    "hard_negative_observation": "NOT_EVALUATED_NO_DURABLE_LOCKED_SET",
                }
                await append_production_admission_assessment(
                    connection,
                    source_id=row["id"],
                    metrics=metrics,
                    sample_cutoff=cutoff,
                    sample_manifest_sha256=manifest_hash,
                    evidence_refs=evidence_refs,
                    actor_id=LOCAL_USER_ID,
                    assessed_at=ended_at,
                )

    async def export_runtime(self, root: Path, started_at: datetime, ended_at: datetime) -> int:
        async with self._engine.connect() as connection:
            rows = (
                (
                    await connection.execute(
                        text(
                            "SELECT observed_at,worker_heartbeat_at,queue_healthy,budget_healthy,"
                            "last_real_schema_success_at,external_balance_state "
                            "FROM ai_runtime_observation_v2 WHERE provider='deepseek' "
                            "AND environment='acceptance' AND observed_at BETWEEN :start AND :end "
                            "ORDER BY observed_at,id"
                        ),
                        {"start": started_at, "end": ended_at},
                    )
                )
                .mappings()
                .all()
            )
        values = [
            {
                key: value.isoformat() if isinstance(value, datetime) else value
                for key, value in row.items()
            }
            for row in rows
        ]
        _write_jsonl(root / "runtime.jsonl", values)
        return len(values)

    async def export_sources(self, root: Path, campaign_id: UUID, started_at: datetime) -> int:
        positions = _rollout_positions()
        async with self._engine.connect() as connection:
            rows = (
                (
                    await connection.execute(
                        text(
                            "SELECT source.name,assessment.sample_cutoff,assessment.lookback_days,"
                            "assessment.sample_size,assessment.sample_manifest_sha256,assessment.metrics,"
                            "assessment.verdict,assessment.assessed_at FROM source_admission_assessment_v2 assessment "
                            "JOIN source ON source.id=assessment.source_id "
                            "WHERE assessment.rule_version='civil-source-rollout-v2-engineering-1.0.0' "
                            "AND assessment.evidence_refs->>'campaign_id'=:campaign "
                            "ORDER BY source.name,assessment.assessed_at DESC"
                        ),
                        {"campaign": str(campaign_id)},
                    )
                )
                .mappings()
                .all()
            )
        seen: set[str] = set()
        assessments: list[dict[str, object]] = []
        for row in rows:
            institution = str(row["name"])
            if institution in seen:
                continue
            seen.add(institution)
            batch, wave = positions[institution]
            metrics = dict(row["metrics"])
            if metrics.get("sample_size") == row["sample_size"]:
                metrics.pop("sample_size")
            assessments.append(
                {
                    "institution": institution,
                    "batch": batch,
                    "wave": wave,
                    "started_at": started_at.isoformat(),
                    "ended_at": row["assessed_at"].isoformat(),
                    "sample_cutoff": row["sample_cutoff"].isoformat(),
                    "lookback_days": row["lookback_days"],
                    "sample_manifest_sha256": row["sample_manifest_sha256"],
                    "sample_size": row["sample_size"],
                    "verdict": row["verdict"],
                    "metrics": metrics,
                }
            )
        _write_json(
            root / "sources.json",
            {
                "rule_version": "civil-source-rollout-v2-engineering-1.0.0",
                "assessments": assessments,
            },
        )
        return len(assessments)

    async def export_feed(self, root: Path) -> int:
        async with self._evidence_engine.connect() as connection:
            rows = (
                (
                    await connection.execute(
                        text(
                            "SELECT projection.event_id::text AS projection_id,projection.risk_tier,"
                            "dv.content_hash,raw.sha256 AS raw_object_sha256,"
                            "(SELECT count(*) FROM claim c WHERE c.document_version_id=dv.id "
                            "AND c.verification_status<>'ACCEPTED') AS unaccepted_claims,"
                            "(SELECT count(*) FROM claim c WHERE c.document_version_id=dv.id "
                            "AND c.verification_status='ACCEPTED' AND NOT EXISTS("
                            "SELECT 1 FROM claim_evidence ce WHERE ce.claim_id=c.id)) AS unsupported_facts "
                            "FROM intelligence_projection_v2 projection "
                            "JOIN document_version dv ON dv.id=projection.document_version_id "
                            "JOIN raw_object raw ON raw.id=dv.raw_object_id "
                            "WHERE projection.projection_kind IN ('FULL','R3_METADATA') "
                            "ORDER BY encode(digest(convert_to(projection.event_id::text,'UTF8'),'sha256'),'hex') "
                            "LIMIT 200"
                        )
                    )
                )
                .mappings()
                .all()
            )
        frozen = [
            {
                "projection_id": str(row["projection_id"]),
                "content_sha256": str(row["content_hash"]),
                "raw_object_sha256": str(row["raw_object_sha256"]),
            }
            for row in rows
        ]
        snapshot = sha256(_canonical(frozen)).hexdigest()
        values = [
            {
                "projection_id": str(row["projection_id"]),
                "risk_tier": str(row["risk_tier"]),
                "unaccepted_claims": int(row["unaccepted_claims"]),
                "unsupported_facts": int(row["unsupported_facts"]),
                "evidence_kind": "SERVER_PROJECTION_AUDIT",
                "snapshot_sha256": snapshot,
                "content_sha256": str(row["content_hash"]),
                "raw_object_sha256": str(row["raw_object_sha256"]),
                "rule_version": "intelligence-v2-feed-structural-engineering-1.0.0",
            }
            for row in rows
        ]
        _write_jsonl(root / "feed.jsonl", values)
        return len(values)

    async def export_compensation(self, root: Path, campaign_id: UUID) -> None:
        async with self._engine.connect() as connection:
            events = (
                (
                    await connection.execute(
                        text(
                            "SELECT event_type,payload FROM engineering_closeout_campaign_event_v2 "
                            "WHERE campaign_id=:id AND event_type LIKE 'FAULT_%'"
                        ),
                        {"id": campaign_id},
                    )
                )
                .mappings()
                .all()
            )
        counts: dict[str, int] = {}
        for row in events:
            counts[str(row["event_type"])] = counts.get(str(row["event_type"]), 0) + 1
        _write_json(
            root / "compensation.json",
            {
                "injected_transient_count": counts.get("FAULT_TRANSIENT_INJECTED", 0),
                "recovered_count": counts.get("FAULT_TRANSIENT_RECOVERED", 0),
                "injected_permanent_count": counts.get("FAULT_PERMANENT_INJECTED", 0),
                "permanent_error_observed_count": counts.get("FAULT_PERMANENT_OBSERVED", 0),
                "duplicate_side_effects": counts.get("FAULT_DUPLICATE_SIDE_EFFECT", 0),
                "stale_version_recoveries": counts.get("FAULT_STALE_VERSION_RECOVERY", 0),
                "permanent_error_retries": counts.get("FAULT_PERMANENT_RETRY", 0),
            },
        )

    async def fault_event_counts(self, campaign_id: UUID) -> dict[str, int]:
        async with self._engine.connect() as connection:
            rows = (
                (
                    await connection.execute(
                        text(
                            "SELECT event_type,count(*) AS total "
                            "FROM engineering_closeout_campaign_event_v2 "
                            "WHERE campaign_id=:id AND event_type LIKE 'FAULT_%' "
                            "GROUP BY event_type"
                        ),
                        {"id": campaign_id},
                    )
                )
                .mappings()
                .all()
            )
        return {str(row["event_type"]): int(row["total"]) for row in rows}

    async def export_historical_budget(self, root: Path, campaign_id: UUID) -> None:
        async with self._engine.connect() as connection:
            rows = (
                (
                    await connection.execute(
                        text(
                            "SELECT id::text,pipeline_run_id::text,step,attempt,created_at "
                            "FROM ai_budget_reservation WHERE billing_status='RESERVED' "
                            "ORDER BY created_at,id"
                        )
                    )
                )
                .mappings()
                .all()
            )
        values = [
            {
                key: value.isoformat() if isinstance(value, datetime) else value
                for key, value in row.items()
            }
            for row in rows
        ]
        report = {
            "campaign_id": str(campaign_id),
            "status": "UNSETTLED_NO_TRUSTWORTHY_PROVIDER_USAGE",
            "blocks_new_engineering_campaign": False,
            "reservation_count": len(values),
            "reservation_refs_sha256": sha256(_canonical(values)).hexdigest(),
            "mutation_performed": False,
        }
        _write_json(root / "historical_budget.json", report)
        await self.append_event(
            campaign_id,
            "HISTORICAL_BUDGET_RECONCILED",
            {"count": len(values), "refs_sha256": report["reservation_refs_sha256"]},
        )

    async def legacy_archive_valid(self) -> bool:
        async with self._engine.connect() as connection:
            return bool(
                await connection.scalar(
                    text("SELECT verify_engineering_closeout_archive_preflight()")
                )
            )

    async def audit_anchor_valid(self) -> bool:
        async with self._engine.connect() as connection:
            return bool(
                await connection.scalar(text("SELECT verify_engineering_closeout_audit_anchor()"))
            )


async def _object_inventory(root: Path) -> tuple[bool, str]:
    endpoint = os.environ.get(
        "SRBG_S3_ENDPOINT_URL",
        f"http://127.0.0.1:{os.environ.get('MINIO_PORT', '9000')}",
    )
    access = os.environ.get("SRBG_S3_ACCESS_KEY", os.environ.get("MINIO_ROOT_USER", "srbg_local"))
    secret = os.environ.get(
        "SRBG_S3_SECRET_KEY",
        os.environ.get("MINIO_ROOT_PASSWORD", "srbg_local_storage_only"),
    )
    bucket = os.environ.get("SRBG_S3_BUCKET", "srbg-raw")
    objects: list[dict[str, object]] = []
    session = aioboto3.Session()
    async with session.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=access,
        aws_secret_access_key=secret,
        region_name=os.environ.get("SRBG_S3_REGION", "us-east-1"),
    ) as client:
        token: str | None = None
        while True:
            kwargs: dict[str, object] = {"Bucket": bucket}
            if token:
                kwargs["ContinuationToken"] = token
            response = await client.list_objects_v2(**kwargs)
            objects.extend(
                {
                    "key": value["Key"],
                    "size": value["Size"],
                    "etag": str(value.get("ETag", "")).strip('"'),
                }
                for value in response.get("Contents", [])
            )
            if not response.get("IsTruncated"):
                break
            token = str(response["NextContinuationToken"])
    digest = _write_json(root / "object-inventory.json", {"bucket": bucket, "objects": objects})
    return True, digest


def _backup(root: Path) -> tuple[bool, str]:
    root.mkdir(parents=True, exist_ok=True)
    backup_path = root / "acceptance-backup.dump"
    result = subprocess.run(  # noqa: S603
        [
            "docker",
            "exec",
            _container_name("postgres"),
            "pg_dump",
            "-U",
            "srbg",
            "-d",
            "srbg",
            "-Fc",
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    backup_path.write_bytes(result.stdout)
    digest = sha256(result.stdout).hexdigest()
    _write_json(
        root / "backup-receipt.json",
        {
            "sha256": digest,
            "byte_size": len(result.stdout),
            "created_at": datetime.now(UTC).isoformat(),
        },
    )
    return bool(result.stdout), digest


def _make_executable() -> str:
    candidates = (
        ROOT / ".tools/make/tools/install/bin/make.exe",
        Path("make"),
    )
    for candidate in candidates:
        if candidate.is_file() or str(candidate) == "make":
            return str(candidate)
    raise RuntimeError("MAKE_NOT_AVAILABLE")


def _run_gates(root: Path) -> dict[str, bool]:
    results: dict[str, bool] = {}
    make = _make_executable()
    for gate in GATES:
        completed = subprocess.run(  # noqa: S603
            [make, gate], cwd=ROOT, check=False
        )
        results[gate.replace("-", "_")] = completed.returncode == 0
    _write_json(root / "engineering.json", results)
    return results


async def _prepare(repository: CampaignRepository, root: Path) -> int:
    if await repository.migration_head() != MIGRATION_HEAD:
        raise RuntimeError("CAMPAIGN_MIGRATION_HEAD_REQUIRED")
    campaign_id = uuid7()
    environments = {service: _service_environment(service) for service in SERVICES}
    unique = {value for value in environments.values() if value}
    if len(unique) != 1:
        raise RuntimeError("CAMPAIGN_SERVICE_ENVIRONMENT_INCONSISTENT")
    original_environment = next(iter(unique))
    campaign_root = root / str(campaign_id)
    backup_ok, backup_sha = _backup(campaign_root)
    inventory_ok, inventory_sha = await _object_inventory(campaign_root)
    if not backup_ok or not inventory_ok:
        raise RuntimeError("CAMPAIGN_BASELINE_EVIDENCE_INCOMPLETE")
    await repository.create(campaign_id, _git_commit(), original_environment)
    state = {
        "campaign_id": str(campaign_id),
        "original_environment": original_environment,
        "service_environments": environments,
        "source_intent": await repository.source_intent(),
        "backup_sha256": backup_sha,
        "object_inventory_sha256": inventory_sha,
    }
    _write_json(campaign_root / "campaign-state.json", state)
    print(json.dumps({"campaign_id": str(campaign_id), "phase": "PREPARED"}))
    return 0


async def _start(repository: CampaignRepository, root: Path, campaign_id: UUID) -> int:
    current = await repository.snapshot(campaign_id)
    transition = decide_transition(current, CampaignAction.START, datetime.now(UTC))
    if transition is None and current.phase is CampaignPhase.STARTED:
        _switch_services("acceptance")
        _dispatch_canary()
        print(
            json.dumps(
                {
                    "campaign_id": str(campaign_id),
                    "phase": current.phase.value,
                    "resumed": True,
                }
            )
        )
        return 0
    if transition is None:
        print(json.dumps({"campaign_id": str(campaign_id), "phase": current.phase.value}))
        return 0
    campaign_root = root / str(campaign_id)
    if not (campaign_root / "campaign-state.json").is_file():
        raise RuntimeError("CAMPAIGN_LOCAL_STATE_MISSING")
    state = json.loads((campaign_root / "campaign-state.json").read_text(encoding="utf-8"))
    original_environment = str(state["original_environment"])
    _switch_services("acceptance")
    try:
        registered = await repository.register_missing_sources(campaign_id)
        await repository.append_event(
            campaign_id,
            "STARTED",
            {"registered_candidates": registered, "environment": "acceptance"},
        )
        _dispatch_canary()
    except Exception:
        _switch_services(original_environment)
        raise
    print(
        json.dumps(
            {
                "campaign_id": str(campaign_id),
                "phase": "STARTED",
                "registered_candidates": registered,
            },
            ensure_ascii=False,
        )
    )
    return 0


async def _export(
    repository: CampaignRepository, root: Path, campaign_id: UUID, ended_at: datetime
) -> dict[str, object]:
    campaign_root = root / str(campaign_id)
    started_at = await repository.event_time(campaign_id, "STARTED")
    if started_at is None:
        raise RuntimeError("CAMPAIGN_NOT_STARTED")
    await repository.assess_sources(campaign_id, started_at, ended_at)
    runtime_count = await repository.export_runtime(campaign_root, started_at, ended_at)
    source_count = await repository.export_sources(campaign_root, campaign_id, started_at)
    feed_count = await repository.export_feed(campaign_root)
    await repository.export_compensation(campaign_root, campaign_id)
    await repository.export_historical_budget(campaign_root, campaign_id)
    context = await repository.campaign_context(campaign_id)
    _write_json(
        campaign_root / "context.json",
        {
            "baseline_commit": context["baseline_commit"],
            "migration_head": context["migration_head"],
            "environment": "local-production-equivalent-acceptance",
            "campaign_id": str(campaign_id),
        },
    )
    backup_receipt = json.loads((campaign_root / "backup-receipt.json").read_text(encoding="utf-8"))
    backup_path = campaign_root / "acceptance-backup.dump"
    backup_verified = backup_path.is_file() and sha256(
        backup_path.read_bytes()
    ).hexdigest() == backup_receipt.get("sha256")
    inventory_verified = (campaign_root / "object-inventory.json").is_file()
    anchor_verified = await repository.audit_anchor_valid()
    archive_verified = await repository.legacy_archive_valid()
    _write_json(
        campaign_root / "preflight.json",
        {
            "backup_receipt_verified": backup_verified,
            "object_inventory_verified": inventory_verified,
            "audit_tail_anchor_verified": anchor_verified,
            "v1_archive_sha256_verified": archive_verified,
            "mutation_performed": False,
        },
    )
    summary = {
        "campaign_id": str(campaign_id),
        "phase": (await repository.snapshot(campaign_id)).phase.value,
        "window_seconds": int((ended_at - started_at).total_seconds()),
        "runtime_observations": runtime_count,
        "source_assessments": source_count,
        "feed_projections": feed_count,
    }
    _write_json(campaign_root / "campaign-status.json", summary)
    _publish_current_evidence(root, campaign_root)
    return summary


async def _status(repository: CampaignRepository, root: Path, campaign_id: UUID) -> int:
    summary = await _export(repository, root, campaign_id, datetime.now(UTC))
    print(json.dumps(summary, ensure_ascii=False))
    return 0


async def _exercise_fault_injection(repository: CampaignRepository, campaign_id: UUID) -> None:
    counts = await repository.fault_event_counts(campaign_id)
    if counts.get("FAULT_TRANSIENT_INJECTED", 0) < 1:
        _dispatch_fault_injection(campaign_id, "TRANSIENT")
    if counts.get("FAULT_PERMANENT_INJECTED", 0) < 1:
        _dispatch_fault_injection(campaign_id, "PERMANENT")
    await asyncio.sleep(5)
    counts = await repository.fault_event_counts(campaign_id)
    if not counts.get("FAULT_TRANSIENT_INJECTED"):
        return
    deadline = time.monotonic() + 2 * 60 * 60
    while time.monotonic() < deadline:
        counts = await repository.fault_event_counts(campaign_id)
        if counts.get("FAULT_TRANSIENT_RECOVERED", 0) >= counts.get(
            "FAULT_TRANSIENT_INJECTED", 0
        ) and counts.get("FAULT_PERMANENT_OBSERVED", 0) >= counts.get(
            "FAULT_PERMANENT_INJECTED", 0
        ):
            return
        await asyncio.sleep(30)


def _run_closeout(campaign_root: Path) -> int:
    closeout = subprocess.run(  # noqa: S603
        [
            sys.executable,
            str(ROOT / "scripts/intelligence_v2_closeout.py"),
            "--acceptance-profile",
            "engineering",
            "--evidence-root",
            str(campaign_root),
            "--output",
            str(campaign_root / "readiness.json"),
        ],
        cwd=ROOT,
        check=False,
    )
    return closeout.returncode


def _existing_readiness_result(campaign_root: Path) -> int:
    path = campaign_root / "readiness.json"
    if not path.is_file():
        raise RuntimeError("CAMPAIGN_READINESS_MISSING")
    readiness = json.loads(path.read_text(encoding="utf-8"))
    print(
        json.dumps(
            {
                "campaign_id": campaign_root.name,
                "phase": "RESTORED",
                "decision": readiness.get("decision"),
            }
        )
    )
    return 0 if readiness.get("decision") == "GO" else 1


async def _finalize(repository: CampaignRepository, root: Path, campaign_id: UUID) -> int:
    current = await repository.snapshot(campaign_id)
    transition = decide_transition(current, CampaignAction.FINALIZE, datetime.now(UTC))
    campaign_root = root / str(campaign_id)
    if transition is None and current.phase is CampaignPhase.RESTORED:
        try:
            return _existing_readiness_result(campaign_root)
        except RuntimeError as error:
            if str(error) != "CAMPAIGN_READINESS_MISSING":
                raise
            _run_gates(campaign_root)
            _publish_current_evidence(root, campaign_root)
            return _run_closeout(campaign_root)
    if current.phase is CampaignPhase.STARTED:
        summary = await _export(repository, root, campaign_id, datetime.now(UTC))
        await _exercise_fault_injection(repository, campaign_id)
        summary = await _export(repository, root, campaign_id, datetime.now(UTC))
        await repository.append_event(campaign_id, "FINALIZED", summary)
    else:
        summary = await _export(repository, root, campaign_id, datetime.now(UTC))
    state = json.loads((campaign_root / "campaign-state.json").read_text(encoding="utf-8"))
    original_environment = str(state["original_environment"])
    _switch_services(original_environment)
    await repository.append_event(
        campaign_id,
        "RESTORED",
        {"environment": original_environment, "source_intent_mutated": False},
    )
    _run_gates(campaign_root)
    _publish_current_evidence(root, campaign_root)
    print(json.dumps(summary, ensure_ascii=False))
    return _run_closeout(campaign_root)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--action", required=True, choices=[value.value for value in CampaignAction]
    )
    parser.add_argument("--campaign-id")
    parser.add_argument(
        "--database-url",
        default=os.environ.get("SRBG_CAMPAIGN_DATABASE_URL", ""),
    )
    parser.add_argument(
        "--evidence-database-url",
        default=os.environ.get("SRBG_CAMPAIGN_EVIDENCE_DATABASE_URL", ""),
    )
    parser.add_argument("--evidence-root", type=Path, default=DEFAULT_EVIDENCE_ROOT)
    return parser


async def _main_async(arguments: argparse.Namespace) -> int:
    database_url = str(arguments.database_url or "") or _discover_database_url("SRBG_DATABASE_URL")
    evidence_database_url = str(arguments.evidence_database_url or "") or _discover_database_url(
        "SRBG_PUBLICATION_DATABASE_URL"
    )
    action = CampaignAction(arguments.action)
    if action is not CampaignAction.PREPARE and not arguments.campaign_id:
        raise RuntimeError("CAMPAIGN_ID_REQUIRED")
    engine = create_async_engine(database_url)
    evidence_engine = create_async_engine(evidence_database_url)
    repository = CampaignRepository(engine, evidence_engine)
    try:
        if action is CampaignAction.PREPARE:
            return await _prepare(repository, arguments.evidence_root)
        campaign_id = UUID(str(arguments.campaign_id))
        if campaign_id.version != 7:
            raise RuntimeError("CAMPAIGN_ID_MUST_BE_UUID7")
        if action is CampaignAction.START:
            return await _start(repository, arguments.evidence_root, campaign_id)
        if action is CampaignAction.STATUS:
            return await _status(repository, arguments.evidence_root, campaign_id)
        return await _finalize(repository, arguments.evidence_root, campaign_id)
    finally:
        await repository.close()


def main() -> int:
    try:
        return asyncio.run(_main_async(_parser().parse_args()))
    except (RuntimeError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
