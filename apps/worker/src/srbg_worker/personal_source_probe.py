"""One-shot PERS-02 probe execution; never creates collection schedules."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from typing import Protocol
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine
from srbg_api.acquisition.contracts import SourceCheckpoint
from srbg_api.acquisition.http import FetchPolicy, ResilientHttpClient, SsrfRejected
from srbg_api.acquisition.live import HttpxTransport, SystemClock, SystemResolver
from srbg_api.identifiers import uuid7
from srbg_api.observability import PERSONAL_SOURCE_PROBES
from srbg_api.personal_source_probe import DetectionResult, ProbeDetectionError, detect_streams

MAX_LOGICAL_URLS = 6
MAX_RESPONSE_BYTES = 10 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class PersonalProbeBinding:
    run_id: UUID
    source_id: UUID
    stream_id: UUID
    requested_url: str
    allowed_host: str


@dataclass(frozen=True, slots=True)
class ProbeFetch:
    requested_url: str
    final_url: str
    status_code: int
    content_type: str
    content: bytes
    fetched_at: datetime
    redirect_chain: tuple[str, ...]


class ProbeGateway(Protocol):
    async def acquire(self, run_id: UUID) -> PersonalProbeBinding | None: ...
    async def complete(
        self,
        binding: PersonalProbeBinding,
        result: DetectionResult,
        captures: list[dict[str, object]],
    ) -> None: ...
    async def fail(
        self,
        binding: PersonalProbeBinding,
        *,
        code: str,
        reason: str,
        captures: list[dict[str, object]],
    ) -> None: ...


class ProbeFetcher(Protocol):
    async def fetch(self, url: str, *, allowed_host: str) -> ProbeFetch: ...


class ObjectStore(Protocol):
    async def put_if_absent(self, key: str, content: bytes, content_type: str) -> str: ...


class PersonalProbeExecutor:
    def __init__(
        self, *, gateway: ProbeGateway, fetcher: ProbeFetcher, object_store: ObjectStore
    ) -> None:
        self._gateway = gateway
        self._fetcher = fetcher
        self._object_store = object_store

    async def run(self, run_id: UUID) -> str:
        binding = await self._gateway.acquire(run_id)
        if binding is None:
            return "DUPLICATE"
        captures: list[dict[str, object]] = []
        try:
            async with asyncio.timeout(30):
                first = await self._capture(binding.requested_url, binding.allowed_host, captures)
                _reject_access_barriers(first.content)
                detected = detect_streams(
                    url=first.final_url, content_type=first.content_type, content=first.content
                )
                streams = list(detected.streams)
                for follow_up in detected.follow_up_urls[: MAX_LOGICAL_URLS - 1]:
                    fetched = await self._capture(follow_up, binding.allowed_host, captures)
                    _reject_access_barriers(fetched.content)
                    child = detect_streams(
                        url=fetched.final_url,
                        content_type=fetched.content_type,
                        content=fetched.content,
                    )
                    streams.extend(child.streams)
                if not streams:
                    raise ProbeDetectionError("UNRECOGNIZED_PUBLIC_ENTRY")
                await self._gateway.complete(
                    binding,
                    DetectionResult(detected.input_kind, tuple(streams), detected.follow_up_urls),
                    captures,
                )
                PERSONAL_SOURCE_PROBES.labels("SUCCEEDED", "NONE").inc()
            return "SUCCEEDED"
        except TimeoutError:
            await self._gateway.fail(
                binding, code="PROBE_TIMEOUT", reason="探测超过 30 秒总时限", captures=captures
            )
            PERSONAL_SOURCE_PROBES.labels("FAILED", "PROBE_TIMEOUT").inc()
        except (ProbeDetectionError, ValueError, OSError) as error:
            code = _bounded_code(str(error))
            await self._gateway.fail(
                binding, code=code, reason=_failure_reason(code), captures=captures
            )
            PERSONAL_SOURCE_PROBES.labels("FAILED", code).inc()
        return "FAILED"

    async def _capture(self, url: str, host: str, captures: list[dict[str, object]]) -> ProbeFetch:
        if len(captures) >= MAX_LOGICAL_URLS:
            raise ProbeDetectionError("PROBE_URL_BUDGET_EXCEEDED")
        fetched = await self._fetcher.fetch(url, allowed_host=host)
        digest = sha256(fetched.content).hexdigest()
        object_key = f"personal-probe/sha256/{digest[:2]}/{digest}"
        await self._object_store.put_if_absent(object_key, fetched.content, fetched.content_type)
        captures.append(
            {
                "object_key": object_key,
                "sha256": digest,
                "byte_size": len(fetched.content),
                "requested_url": fetched.requested_url,
                "final_url": fetched.final_url,
                "content_type": fetched.content_type[:200],
                "status_code": fetched.status_code,
            }
        )
        return fetched


class SafePersonalProbeFetcher:
    """Robots-aware fetcher using the shared DNS-pinned HTTP boundary."""

    async def fetch(self, url: str, *, allowed_host: str) -> ProbeFetch:
        await self._check_robots(url, allowed_host)
        transport = HttpxTransport()
        client = ResilientHttpClient(
            _policy(allowed_host, max_bytes=MAX_RESPONSE_BYTES, redirects=3),
            resolver=SystemResolver(),
            transport=transport,
            clock=SystemClock(),
        )
        try:
            result = await client.get(
                url,
                checkpoint=SourceCheckpoint(),
                accept="text/html,application/xhtml+xml,application/rss+xml,application/atom+xml,application/xml,application/json,application/pdf",
            )
        except SsrfRejected as error:
            raise ValueError("SSRF_REJECTED") from error
        finally:
            await transport.close()
        return ProbeFetch(
            requested_url=url,
            final_url=result.url,
            status_code=result.status_code,
            content_type=result.content_type or "application/octet-stream",
            content=result.content or b"",
            fetched_at=result.fetched_at,
            redirect_chain=result.redirect_chain,
        )

    async def _check_robots(self, target_url: str, host: str) -> None:
        robots_url = f"https://{host}/robots.txt"
        transport = HttpxTransport()
        client = ResilientHttpClient(
            _policy(host, max_bytes=512 * 1024, redirects=1),
            resolver=SystemResolver(),
            transport=transport,
            clock=SystemClock(),
        )
        try:
            result = await client.get(
                robots_url, checkpoint=SourceCheckpoint(), accept="text/plain", allow_not_found=True
            )
        except SsrfRejected as error:
            raise ValueError("SSRF_REJECTED") from error
        finally:
            await transport.close()
        if result.status_code in {404, 410}:
            return
        lines = (result.content or b"").decode("utf-8", errors="ignore").splitlines()
        parser = RobotFileParser(robots_url)
        parser.parse(lines)
        if not lines or not parser.can_fetch("SRBGPersonalProbe/1.0", target_url):
            raise ValueError("ROBOTS_BLOCKED")


def _policy(host: str, *, max_bytes: int, redirects: int) -> FetchPolicy:
    return FetchPolicy(
        allowed_hosts=(host,),
        timeout_seconds=5.0,
        max_attempts=2,
        base_backoff_seconds=0.1,
        rate_limit_per_minute=30,
        minimum_interval_seconds=1,
        circuit_failure_threshold=2,
        circuit_reset_seconds=60.0,
        max_redirects=redirects,
        user_agent="SRBGPersonalProbe/1.0",
        max_response_bytes=max_bytes,
        max_backoff_seconds=1.0,
    )


class PostgresPersonalProbeGateway:
    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def pending_ids(self, *, limit: int = 100) -> tuple[UUID, ...]:
        async with self._engine.connect() as connection:
            rows = await connection.execute(
                text(
                    "SELECT id FROM stream_probe_run WHERE status='QUEUED' "
                    "ORDER BY created_at,id LIMIT :limit"
                ),
                {"limit": limit},
            )
            return tuple(rows.scalars())

    async def acquire(self, run_id: UUID) -> PersonalProbeBinding | None:
        async with self._engine.begin() as connection:
            row = (
                (
                    await connection.execute(
                        text(
                            "UPDATE stream_probe_run SET status='RUNNING',"
                            "attempt_count=attempt_count+1,"
                            "started_at=COALESCE(started_at,now()),updated_at=now() "
                            "WHERE id=:id AND status='QUEUED' AND attempt_count<2 "
                            "RETURNING id,source_id,stream_id,requested_url"
                        ),
                        {"id": run_id},
                    )
                )
                .mappings()
                .first()
            )
            if row is None:
                return None
            host = urlsplit(row["requested_url"]).hostname
            if host is None:
                raise ValueError("URL_INVALID")
            return PersonalProbeBinding(
                row["id"],
                row["source_id"],
                row["stream_id"],
                row["requested_url"],
                host.casefold(),
            )

    async def complete(
        self,
        binding: PersonalProbeBinding,
        result: DetectionResult,
        captures: list[dict[str, object]],
    ) -> None:
        now = datetime.now(UTC)
        async with self._engine.begin() as connection:
            for index, detected in enumerate(result.streams):
                canonical = json.dumps(
                    detected.config, ensure_ascii=False, sort_keys=True, separators=(",", ":")
                )
                config_hash = sha256(canonical.encode()).hexdigest()
                stream_id = binding.stream_id if index == 0 else uuid7()
                if index == 0:
                    conflict = await connection.scalar(
                        text(
                            "SELECT id FROM source_stream WHERE source_id=:source_id "
                            "AND canonical_url=:url AND id<>:id"
                        ),
                        {
                            "source_id": binding.source_id,
                            "url": detected.normalized_url,
                            "id": stream_id,
                        },
                    )
                    if conflict is not None:
                        stream_id = conflict
                    else:
                        await connection.execute(
                            text(
                                "UPDATE source_stream SET canonical_url=:url,name=:url,"
                                "stream_type=:kind,status='READY',"
                                "allowed_hosts=ARRAY[CAST(:host AS varchar(253))],"
                                "config_sha256=:hash,discovery_method=:method,"
                                "failure_reason=NULL,updated_at=:now WHERE id=:id"
                            ),
                            {
                                "url": detected.normalized_url,
                                "kind": detected.stream_type.value,
                                "host": binding.allowed_host,
                                "hash": config_hash,
                                "method": detected.discovery_method,
                                "now": now,
                                "id": stream_id,
                            },
                        )
                else:
                    existing = await connection.scalar(
                        text(
                            "SELECT id FROM source_stream WHERE source_id=:source_id "
                            "AND canonical_url=:url"
                        ),
                        {"source_id": binding.source_id, "url": detected.normalized_url},
                    )
                    if existing is not None:
                        stream_id = existing
                    else:
                        await connection.execute(
                            text(
                                "INSERT INTO source_stream(id,source_id,stream_key,name,"
                                "canonical_url,authorization_boundary,status,rule_version,"
                                "automatically_managed,created_at,updated_at,stream_type,"
                                "allowed_hosts,config_sha256,discovery_method) "
                                "VALUES(:id,:source_id,:key,:url,:url,"
                                "CAST(:host AS varchar(253)),'READY',"
                                "'personal-source-probe-v1',false,:now,:now,:kind,"
                                "ARRAY[CAST(:host AS varchar(253))],:hash,:method)"
                            ),
                            {
                                "id": stream_id,
                                "source_id": binding.source_id,
                                "key": "URL_" + config_hash[:24],
                                "url": detected.normalized_url,
                                "host": binding.allowed_host,
                                "now": now,
                                "kind": detected.stream_type.value,
                                "hash": config_hash,
                                "method": detected.discovery_method,
                            },
                        )
                await connection.execute(
                    text(
                        "INSERT INTO stream_config_version(id,stream_id,probe_run_id,"
                        "connector_type,definition_version,schema_version,config,"
                        "config_sha256,discovery_method,created_at) VALUES(:id,:stream_id,"
                        ":run_id,:kind,'1.0.0','2020-12',CAST(:config AS jsonb),"
                        ":hash,:method,:now) ON CONFLICT(stream_id,config_sha256) DO NOTHING"
                    ),
                    {
                        "id": uuid7(),
                        "stream_id": stream_id,
                        "run_id": binding.run_id,
                        "kind": detected.stream_type.value,
                        "config": canonical,
                        "hash": config_hash,
                        "method": detected.discovery_method,
                        "now": now,
                    },
                )
                config_id = await connection.scalar(
                    text(
                        "SELECT id FROM stream_config_version "
                        "WHERE stream_id=:stream_id AND config_sha256=:hash "
                        "ORDER BY created_at DESC,id DESC LIMIT 1"
                    ),
                    {"stream_id": stream_id, "hash": config_hash},
                )
                source_state = (
                    (
                        await connection.execute(
                            text(
                                "SELECT desired_enabled,manual_disabled_at FROM source "
                                "WHERE id=:source_id"
                            ),
                            {"source_id": binding.source_id},
                        )
                    )
                    .mappings()
                    .one()
                )
                schedule_id = await connection.scalar(
                    text(
                        "SELECT id FROM fetch_schedule WHERE source_stream_id=:stream_id"
                    ),
                    {"stream_id": stream_id},
                )
                schedule_status = (
                    "ACTIVE"
                    if source_state["desired_enabled"]
                    and source_state["manual_disabled_at"] is None
                    else "PAUSED"
                )
                if schedule_id is None:
                    schedule_id = uuid7()
                    await connection.execute(
                        text(
                            "INSERT INTO fetch_schedule("
                            "id,source_id,source_stream_id,stream_config_version_id,"
                            "authority_mode,authority_level,status,interval_seconds,"
                            "next_run_at,backoff_base_seconds,backoff_cap_seconds,max_attempts,"
                            "consecutive_failures,circuit_state,freshness_slo_seconds,"
                            "rate_limit_per_minute,daily_request_budget,daily_byte_budget,"
                            "requests_used,bytes_used,budget_window_started_at,version,updated_at"
                            ") VALUES("
                            ":id,:source_id,:stream_id,:config_id,'PERSONAL_STREAM','PERSONAL',"
                            ":status,3600,:now,30,21600,3,0,'CLOSED',86400,6,500,536870912,"
                            "0,0,:now,1,:now)"
                        ),
                        {
                            "id": schedule_id,
                            "source_id": binding.source_id,
                            "stream_id": stream_id,
                            "config_id": config_id,
                            "status": schedule_status,
                            "now": now,
                        },
                    )
                else:
                    await connection.execute(
                        text(
                            "UPDATE fetch_schedule SET stream_config_version_id=:config_id,"
                            "status=:status,access_state='ACCESSIBLE',next_run_at=:now,"
                            "updated_at=:now,version=version+1 "
                            "WHERE id=:schedule_id AND authority_mode='PERSONAL_STREAM'"
                        ),
                        {
                            "config_id": config_id,
                            "status": schedule_status,
                            "now": now,
                            "schedule_id": schedule_id,
                        },
                    )
                await connection.execute(
                    text(
                        "UPDATE source_stream SET schedule_id=:schedule_id "
                        "WHERE id=:stream_id"
                    ),
                    {"schedule_id": schedule_id, "stream_id": stream_id},
                )
            await connection.execute(
                text(
                    "UPDATE stream_probe_run SET status='SUCCEEDED',input_kind=:kind,"
                    "capture_manifest=CAST(:captures AS jsonb),completed_at=:now,"
                    "duration_ms=GREATEST(0,(EXTRACT(EPOCH FROM (:now-started_at))*1000)::integer),"
                    "updated_at=:now WHERE id=:id AND status='RUNNING'"
                ),
                {
                    "kind": result.input_kind.value,
                    "captures": json.dumps(captures),
                    "now": now,
                    "id": binding.run_id,
                },
            )
            await connection.execute(
                text(
                    "UPDATE source SET runtime_state='STOPPED',updated_at=:now "
                    "WHERE id=:source_id AND manual_disabled_at IS NULL"
                ),
                {"now": now, "source_id": binding.source_id},
            )

    async def fail(
        self,
        binding: PersonalProbeBinding,
        *,
        code: str,
        reason: str,
        captures: list[dict[str, object]],
    ) -> None:
        now = datetime.now(UTC)
        async with self._engine.begin() as connection:
            await connection.execute(
                text(
                    "UPDATE stream_probe_run SET status='FAILED',failure_code=:code,"
                    "failure_reason=:reason,capture_manifest=CAST(:captures AS jsonb),"
                    "completed_at=:now,"
                    "duration_ms=GREATEST(0,(EXTRACT(EPOCH FROM (:now-started_at))*1000)::integer),"
                    "updated_at=:now WHERE id=:id AND status='RUNNING'"
                ),
                {
                    "code": code,
                    "reason": reason,
                    "captures": json.dumps(captures),
                    "now": now,
                    "id": binding.run_id,
                },
            )
            await connection.execute(
                text(
                    "UPDATE source_stream SET status='PROBE_FAILED',"
                    "failure_reason=:reason,updated_at=:now "
                    "WHERE id=:id AND status='PROBING'"
                ),
                {"reason": reason, "now": now, "id": binding.stream_id},
            )


def _reject_access_barriers(content: bytes) -> None:
    sample = content[:262_144].decode("utf-8", errors="ignore").casefold()
    if any(marker in sample for marker in ("captcha", "验证码", "人机验证")):
        raise ValueError("CAPTCHA_DETECTED")
    if any(
        marker in sample
        for marker in ("please login", "sign in to continue", "请登录", "登录后查看")
    ):
        raise ValueError("LOGIN_REQUIRED")
    if any(
        marker in sample
        for marker in ("subscribe to continue", "paywall", "订阅后阅读", "付费阅读")
    ):
        raise ValueError("PAYWALL_DETECTED")


def _bounded_code(value: str) -> str:
    candidate = value.split(":", 1)[0].strip().upper().replace(" ", "_")
    return (
        candidate
        if candidate and len(candidate) <= 80 and all(c.isalnum() or c == "_" for c in candidate)
        else "PROBE_FAILED"
    )


def _failure_reason(code: str) -> str:
    return {
        "CAPTCHA_DETECTED": "目标需要验证码, 系统不会尝试绕过",
        "LOGIN_REQUIRED": "目标需要登录, 系统不会提交凭据",
        "PAYWALL_DETECTED": "目标存在付费访问门禁, 系统不会绕过",
        "ROBOTS_BLOCKED": "robots.txt 不允许本次探测",
        "SSRF_REJECTED": "目标未通过公网地址或重定向安全检查",
        "MIME_MISMATCH": "响应类型与实际内容不一致",
        "UNRECOGNIZED_PUBLIC_ENTRY": "未识别到受支持的公开采集入口",
    }.get(code, "本次安全探测失败, 可稍后重新探测")
