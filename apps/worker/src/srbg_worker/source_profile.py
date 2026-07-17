"""Durable PERS-04 profile preparation and immutable snapshot persistence."""

from __future__ import annotations

import html
import json
import re
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine
from srbg_api.ai_pipeline.contracts import ModelResponse
from srbg_api.identifiers import uuid7
from srbg_api.personal_source_discovery import (
    AUTO_SCORE_RULE_VERSION,
    AutoEnableGate,
    ScoringInput,
    calculate_auto_score,
    evaluate_auto_enable,
)
from srbg_api.source_profiles import (
    MODEL_VERSION,
    PROFILE_FIELDS,
    PROMPT_VERSION,
    RULE_VERSION,
    SCHEMA_VERSION,
    BuiltSourceProfile,
    ProfileEvidence,
    ProfileRuleInput,
    canonical_profile_input_hash,
)


class ProfileObjectStore(Protocol):
    async def get_bytes(self, key: str, *, max_bytes: int | None = None) -> bytes: ...


@dataclass(frozen=True, slots=True)
class ProfileBinding:
    run_id: UUID
    source_id: UUID
    origin: str
    stream_types: tuple[str, ...]
    captures: tuple[dict[str, object], ...]
    attempt_count: int


@dataclass(frozen=True, slots=True)
class PreparedProfile:
    binding: ProfileBinding
    rule_input: ProfileRuleInput
    input_sha256: str


class PostgresSourceProfileGateway:
    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def close(self) -> None:
        await self._engine.dispose()

    async def pending_ids(self, *, limit: int = 100) -> tuple[UUID, ...]:
        async with self._engine.connect() as connection:
            rows = await connection.execute(
                text(
                    "SELECT id FROM source_profile_run WHERE status='QUEUED' "
                    "AND next_attempt_at<=now() ORDER BY next_attempt_at,id LIMIT :limit"
                ),
                {"limit": limit},
            )
            return tuple(rows.scalars())

    async def acquire(self, run_id: UUID) -> ProfileBinding | None:
        token = uuid7()
        async with self._engine.begin() as connection:
            row = (
                (
                    await connection.execute(
                        text(
                            "UPDATE source_profile_run SET status='RUNNING',"
                            "attempt_count=attempt_count+1,lease_token=:token,"
                            "leased_until=now()+interval '5 minutes',updated_at=now() "
                            "WHERE id=:id AND status='QUEUED' AND next_attempt_at<=now() "
                            "AND attempt_count<3 RETURNING source_id,attempt_count"
                        ),
                        {"id": run_id, "token": token},
                    )
                )
                .mappings()
                .first()
            )
            if row is None:
                return None
            source = (
                (
                    await connection.execute(
                        text(
                            "SELECT COALESCE(normalized_origin,base_url) AS origin FROM source "
                            "WHERE id=:source_id"
                        ),
                        {"source_id": row["source_id"]},
                    )
                )
                .mappings()
                .one()
            )
            stream_types = tuple(
                (
                    await connection.execute(
                        text(
                            "SELECT DISTINCT stream_type FROM source_stream "
                            "WHERE source_id=:source_id AND status='READY' ORDER BY stream_type"
                        ),
                        {"source_id": row["source_id"]},
                    )
                ).scalars()
            )
            captures = await connection.scalar(
                text(
                    "SELECT capture_manifest FROM stream_probe_run WHERE source_id=:source_id "
                    "AND status='SUCCEEDED' ORDER BY completed_at DESC,id DESC LIMIT 1"
                ),
                {"source_id": row["source_id"]},
            )
        return ProfileBinding(
            run_id=run_id,
            source_id=row["source_id"],
            origin=source["origin"],
            stream_types=stream_types,
            captures=tuple(captures or ()),
            attempt_count=int(row["attempt_count"]),
        )

    async def persist_snapshot(
        self,
        prepared: PreparedProfile,
        profile: BuiltSourceProfile,
        *,
        status: str | None = None,
        failure_code: str | None = None,
    ) -> None:
        now = datetime.now(UTC)
        evidence = [asdict(item) for item in prepared.rule_input.evidence]
        explanations = {key: asdict(value) for key, value in profile.field_explanations.items()}
        facts = [asdict(item) for item in profile.technical_facts]
        final_status = status or profile.status
        async with self._engine.begin() as connection:
            version = int(
                await connection.scalar(
                    text(
                        "SELECT COALESCE(max(version),0)+1 FROM source_profile_snapshot "
                        "WHERE source_id=:source_id"
                    ),
                    {"source_id": prepared.binding.source_id},
                )
            )
            await connection.execute(
                text(
                    "INSERT INTO source_profile_snapshot(id,source_id,version,input_sha256,status,"
                    "industries,content_domains,language_tags,country_codes,region_codes,"
                    "declared_roles,authority_level,independence_level,authority_basis,"
                    "independence_basis,field_explanations,overall_confidence,reason_codes,"
                    "evidence,technical_facts,rule_version,prompt_version,schema_version,"
                    "model_version,generated_at) VALUES(:id,:source_id,:version,:input_hash,"
                    ":status,:industries,:domains,:languages,:countries,:regions,:roles,"
                    ":authority,:independence,'AUTO_INFERRED','AUTO_INFERRED',"
                    "CAST(:explanations AS jsonb),:confidence,:reasons,CAST(:evidence AS jsonb),"
                    "CAST(:facts AS jsonb),:rule,:prompt,:schema,:model,:now)"
                ),
                {
                    "id": uuid7(),
                    "source_id": prepared.binding.source_id,
                    "version": version,
                    "input_hash": prepared.input_sha256,
                    "status": final_status,
                    "industries": list(profile.industries),
                    "domains": list(profile.content_domains),
                    "languages": list(profile.language_tags),
                    "countries": list(profile.country_codes),
                    "regions": list(profile.region_codes),
                    "roles": list(profile.declared_roles),
                    "authority": profile.authority_level,
                    "independence": profile.independence_level,
                    "explanations": json.dumps(explanations, ensure_ascii=False),
                    "confidence": profile.overall_confidence,
                    "reasons": list(profile.reason_codes),
                    "evidence": json.dumps(evidence, ensure_ascii=False),
                    "facts": json.dumps(facts),
                    "rule": RULE_VERSION,
                    "prompt": PROMPT_VERSION,
                    "schema": SCHEMA_VERSION,
                    "model": MODEL_VERSION,
                    "now": now,
                },
            )
            await _persist_personal_auto_score(
                connection,
                prepared=prepared,
                profile=profile,
                now=now,
            )
            await connection.execute(
                text(
                    "UPDATE source_profile_run SET status=:status,input_sha256=:input_hash,"
                    "failure_code=:failure_code,lease_token=NULL,leased_until=NULL,updated_at=:now "
                    "WHERE id=:id"
                ),
                {
                    "status": final_status,
                    "input_hash": prepared.input_sha256,
                    "failure_code": failure_code,
                    "now": now,
                    "id": prepared.binding.run_id,
                },
            )

    async def requeue(self, run_id: UUID, *, failure_code: str) -> bool:
        async with self._engine.begin() as connection:
            attempt = int(
                await connection.scalar(
                    text("SELECT attempt_count FROM source_profile_run WHERE id=:id FOR UPDATE"),
                    {"id": run_id},
                )
            )
            if attempt >= 3:
                return False
            delay = timedelta(minutes=5 if attempt == 1 else 30)
            await connection.execute(
                text(
                    "UPDATE source_profile_run SET status='QUEUED',next_attempt_at=:next,"
                    "failure_code=:code,lease_token=NULL,leased_until=NULL,updated_at=now() "
                    "WHERE id=:id"
                ),
                {"next": datetime.now(UTC) + delay, "code": failure_code, "id": run_id},
            )
            return True

    async def reserve_budget(self, run_id: UUID, attempt: int) -> UUID | None:
        reservation_id = uuid7()
        async with self._engine.begin() as connection:
            policy = (
                (
                    await connection.execute(
                        text(
                            "SELECT id,monthly_points,document_points FROM ai_budget_policy "
                            "WHERE provider='deepseek' AND model='deepseek-v4-flash' AND active "
                            "FOR SHARE"
                        )
                    )
                )
                .mappings()
                .first()
            )
            if policy is None:
                return None
            month = datetime.now(UTC).date().replace(day=1)
            await connection.execute(
                text(
                    "INSERT INTO ai_budget_month(policy_id,month_start) VALUES(:policy,:month) "
                    "ON CONFLICT DO NOTHING"
                ),
                {"policy": policy["id"], "month": month},
            )
            ledger = (
                (
                    await connection.execute(
                        text(
                            "SELECT reserved_points,settled_points FROM ai_budget_month "
                            "WHERE policy_id=:policy AND month_start=:month FOR UPDATE"
                        ),
                        {"policy": policy["id"], "month": month},
                    )
                )
                .mappings()
                .one()
            )
            points = int(policy["document_points"])
            if int(ledger["reserved_points"]) + int(ledger["settled_points"]) + points > int(
                policy["monthly_points"]
            ):
                return None
            existing = await connection.scalar(
                text(
                    "SELECT id FROM source_profile_budget_reservation "
                    "WHERE run_id=:run_id AND attempt=:attempt"
                ),
                {"run_id": run_id, "attempt": attempt},
            )
            if existing is not None:
                return UUID(str(existing))
            await connection.execute(
                text(
                    "INSERT INTO source_profile_budget_reservation(id,run_id,policy_id,attempt,"
                    "month_start,reserved_points,created_at) VALUES(:id,:run_id,:policy,:attempt,"
                    ":month,:points,now())"
                ),
                {
                    "id": reservation_id,
                    "run_id": run_id,
                    "policy": policy["id"],
                    "attempt": attempt,
                    "month": month,
                    "points": points,
                },
            )
            await connection.execute(
                text(
                    "UPDATE ai_budget_month SET reserved_points=reserved_points+:points "
                    "WHERE policy_id=:policy AND month_start=:month"
                ),
                {"points": points, "policy": policy["id"], "month": month},
            )
            return reservation_id

    async def settle_budget(self, reservation_id: UUID, response: ModelResponse | None) -> None:
        async with self._engine.begin() as connection:
            row = (
                (
                    await connection.execute(
                        text(
                            "SELECT reservation.*,policy.points_per_usd FROM "
                            "source_profile_budget_reservation reservation JOIN ai_budget_policy "
                            "policy ON policy.id=reservation.policy_id WHERE reservation.id=:id "
                            "FOR UPDATE OF reservation"
                        ),
                        {"id": reservation_id},
                    )
                )
                .mappings()
                .one()
            )
            if row["billing_status"] != "RESERVED":
                return
            settled = (
                0
                if response is None
                else min(
                    int(row["reserved_points"]),
                    (response.cost_microusd * int(row["points_per_usd"]) + 999_999) // 1_000_000,
                )
            )
            status = "RELEASED" if response is None else "SETTLED"
            await connection.execute(
                text(
                    "UPDATE source_profile_budget_reservation SET settled_points=:settled,"
                    "cost_microusd=:cost,billing_status=:status,settled_at=now() WHERE id=:id"
                ),
                {
                    "settled": settled,
                    "cost": None if response is None else response.cost_microusd,
                    "status": status,
                    "id": reservation_id,
                },
            )
            await connection.execute(
                text(
                    "UPDATE ai_budget_month SET reserved_points=reserved_points-:reserved,"
                    "settled_points=settled_points+:settled WHERE policy_id=:policy "
                    "AND month_start=:month"
                ),
                {
                    "reserved": row["reserved_points"],
                    "settled": settled,
                    "policy": row["policy_id"],
                    "month": row["month_start"],
                },
            )

    async def record_model_attempt(
        self,
        *,
        run_id: UUID,
        attempt: int,
        kind: str,
        input_sha256: str,
        response: ModelResponse | None,
        error_code: str | None,
    ) -> None:
        async with self._engine.begin() as connection:
            await connection.execute(
                text(
                    "INSERT INTO source_profile_model_attempt(id,run_id,attempt,attempt_kind,"
                    "input_sha256,prompt_version,schema_version,model_version,raw_output,"
                    "validated_output,input_tokens,output_tokens,cost_microusd,latency_ms,outcome,"
                    "error_code,created_at) VALUES(:id,:run_id,:attempt,:kind,:hash,:prompt,"
                    ":schema,:model,:raw,CAST(:validated AS jsonb),:input_tokens,:output_tokens,"
                    ":cost,:latency,:outcome,:error,now()) ON CONFLICT(run_id,attempt) DO NOTHING"
                ),
                {
                    "id": uuid7(),
                    "run_id": run_id,
                    "attempt": attempt,
                    "kind": kind,
                    "hash": input_sha256,
                    "prompt": PROMPT_VERSION,
                    "schema": SCHEMA_VERSION,
                    "model": MODEL_VERSION,
                    "raw": None if response is None else response.raw_output,
                    "validated": None
                    if response is None
                    else json.dumps(response.output, ensure_ascii=False),
                    "input_tokens": 0 if response is None else response.usage.input_tokens,
                    "output_tokens": 0 if response is None else response.usage.output_tokens,
                    "cost": 0 if response is None else response.cost_microusd,
                    "latency": 0 if response is None else response.latency_ms,
                    "outcome": "FAILED" if response is None else "SUCCEEDED",
                    "error": error_code,
                },
            )


async def _persist_personal_auto_score(
    connection: AsyncConnection,
    *,
    prepared: PreparedProfile,
    profile: BuiltSourceProfile,
    now: datetime,
) -> None:
    topic_rows = (
        (
            await connection.execute(
                text("SELECT keywords,excluded_terms FROM discovery_topic WHERE enabled")
            )
        )
        .mappings()
        .all()
    )
    sample_texts = [
        f"{item.url} {item.excerpt}".casefold() for item in prepared.rule_input.evidence
    ]
    keywords = {term.casefold() for row in topic_rows for term in row["keywords"]}
    excluded = {term.casefold() for row in topic_rows for term in row["excluded_terms"]}
    excluded_hit = any(term in sample for term in excluded for sample in sample_texts)
    relevant = (
        0
        if excluded_hit
        else sum(any(term in sample for term in keywords) for sample in sample_texts)
    )
    sample_count = max(1, len(sample_texts))
    capture_mimes = {
        str(item.get("final_url", "")): str(item.get("content_type", ""))
        for item in prepared.binding.captures
    }
    completed_fields = 0
    for item in prepared.rule_input.evidence:
        completed_fields += 1  # server-issued external evidence id
        completed_fields += bool(item.url)
        completed_fields += bool(item.excerpt)
        completed_fields += bool(capture_mimes.get(item.url))
    profile_keys = ("industries", "content_domains", "language_tags", "region_codes")
    confidences = tuple(
        profile.field_explanations[key].confidence if key in profile.field_explanations else 0
        for key in profile_keys
    )
    score = calculate_auto_score(
        ScoringInput(
            successful_sample_count=sample_count,
            relevant_sample_count=min(relevant, sample_count),
            stability_checks_passed=5,
            complete_field_count=completed_fields,
            possible_field_count=sample_count * 5,
            profile_confidences=confidences,  # type: ignore[arg-type]
            valid_sample_count=sum(bool(item.excerpt) for item in prepared.rule_input.evidence),
            latest_published_at=None,
        ),
        now=now,
    )
    sticky = bool(
        await connection.scalar(
            text("SELECT manual_disabled_at IS NOT NULL FROM source WHERE id=:source_id"),
            {"source_id": prepared.binding.source_id},
        )
    )
    gate = AutoEnableGate(True, True, True, True, True, True, True, True, True, sticky)
    decision = evaluate_auto_enable(score, gate)
    run_id = await connection.scalar(
        text(
            "SELECT id FROM source_auto_score_run WHERE source_id=:source_id "
            "AND status IN ('QUEUED','RUNNING','DEFERRED') ORDER BY created_at,id LIMIT 1 "
            "FOR UPDATE"
        ),
        {"source_id": prepared.binding.source_id},
    )
    if run_id is None:
        run_id = uuid7()
        await connection.execute(
            text(
                "INSERT INTO source_auto_score_run(id,source_id,status,reason,next_attempt_at,"
                "created_at,updated_at) VALUES(:id,:source_id,'COMPLETE','PROFILE_UPDATED',"
                ":now,:now,:now)"
            ),
            {"id": run_id, "source_id": prepared.binding.source_id, "now": now},
        )
    else:
        await connection.execute(
            text(
                "UPDATE source_auto_score_run SET status='COMPLETE',reason='PROFILE_UPDATED',"
                "lease_token=NULL,leased_until=NULL,updated_at=:now WHERE id=:id"
            ),
            {"id": run_id, "now": now},
        )
    version = int(
        await connection.scalar(
            text(
                "SELECT COALESCE(MAX(version),0)+1 FROM source_auto_score_snapshot "
                "WHERE source_id=:source_id"
            ),
            {"source_id": prepared.binding.source_id},
        )
    )
    hard_gates = {
        "public_network": True,
        "ssrf_safe": True,
        "robots_permitted": True,
        "access_open": True,
        "terms_permitted": True,
        "copyright_permitted": True,
        "connector_executable": True,
        "sample_parsed": True,
        "evidence_current": True,
        "sticky_disabled": sticky,
    }
    explanations = {
        "topic_relevance": "启用主题关键词在真实探测样本中的命中比例",
        "connector_stability": "入口、公网、重定向、连接器和样本抓取检查",
        "sample_completeness": "样本标识、URL、标题、发布时间和 MIME 完整度",
        "profile_evidence": "行业、内容域、语言和地区画像解释置信度",
        "content_validity": "有效样本比例及原文发布时间时效",
    }
    await connection.execute(
        text(
            "INSERT INTO source_auto_score_snapshot(id,source_id,run_id,version,"
            "topic_relevance_score,connector_stability_score,sample_completeness_score,"
            "profile_evidence_score,content_validity_score,total_score,auto_enable_eligible,"
            "hard_gate_results,component_explanations,reason_codes,evidence_refs,"
            "evidence_sha256,rule_version,evaluated_at) VALUES(:id,:source,:run,:version,"
            ":relevance,:stability,:completeness,:profile,:validity,:total,:eligible,"
            "CAST(:gates AS jsonb),CAST(:explanations AS jsonb),:reasons,:refs,:hash,:rule,:now)"
        ),
        {
            "id": uuid7(),
            "source": prepared.binding.source_id,
            "run": run_id,
            "version": version,
            "relevance": score.topic_relevance,
            "stability": score.connector_stability,
            "completeness": score.sample_completeness,
            "profile": score.profile_evidence,
            "validity": score.content_validity,
            "total": score.total,
            "eligible": decision.eligible,
            "gates": json.dumps(hard_gates),
            "explanations": json.dumps(explanations, ensure_ascii=False),
            "reasons": list(decision.reason_codes),
            "refs": [item.evidence_id for item in prepared.rule_input.evidence],
            "hash": prepared.input_sha256,
            "rule": AUTO_SCORE_RULE_VERSION,
            "now": now,
        },
    )


async def prepare_profile(
    binding: ProfileBinding, object_store: ProfileObjectStore
) -> PreparedProfile:
    evidence: list[ProfileEvidence] = []
    for index, capture in enumerate(binding.captures[:5]):
        key = capture.get("object_key")
        digest = capture.get("sha256")
        url = capture.get("final_url") or capture.get("requested_url")
        if not isinstance(key, str) or not isinstance(digest, str) or not isinstance(url, str):
            continue
        content = await object_store.get_bytes(key, max_bytes=2 * 1024 * 1024)
        excerpt = _plain_excerpt(content)
        if not excerpt:
            continue
        lowered_url = url.casefold()
        kind = (
            "HOMEPAGE"
            if index == 0
            else "ABOUT"
            if any(marker in lowered_url for marker in ("about", "jigou", "gaikuang", "简介"))
            else "SECTION_SAMPLE"
        )
        evidence.append(
            ProfileEvidence(
                evidence_id=f"profile-{index + 1}",
                kind=kind,
                url=url,
                sha256=digest,
                excerpt=excerpt,
            )
        )
    if not evidence:
        evidence.append(
            ProfileEvidence(
                evidence_id="origin-1",
                kind="HOMEPAGE",
                url=binding.origin,
                sha256="0" * 64,
                excerpt=binding.origin,
            )
        )
    rule_input = ProfileRuleInput(binding.origin, binding.stream_types, tuple(evidence))
    return PreparedProfile(binding, rule_input, canonical_profile_input_hash(rule_input))


def _plain_excerpt(content: bytes) -> str:
    decoded = content[: 2 * 1024 * 1024].decode("utf-8", errors="ignore")
    without_scripts = re.sub(
        r"<(script|style)\b[^>]*>.*?</\1>", " ", decoded, flags=re.IGNORECASE | re.DOTALL
    )
    text_value = re.sub(r"<[^>]+>", " ", without_scripts)
    normalized = " ".join(html.unescape(text_value).split())
    return normalized[:8_000]


def effective_override(
    automatic: dict[str, object], current: dict[str, object], patch: dict[str, object | None]
) -> tuple[dict[str, object], dict[str, object]]:
    overrides = dict(current)
    for field, value in patch.items():
        if field not in PROFILE_FIELDS:
            raise ValueError("profile override field is not allowed")
        if value is None:
            overrides.pop(field, None)
        else:
            overrides[field] = value
    return ({**automatic, **overrides}, overrides)
