from __future__ import annotations

import hashlib
import json
import threading
from dataclasses import asdict
from datetime import UTC, datetime
from uuid import UUID

import pytest
from srbg_api.ai_pipeline.gateway import (
    ModelOutputRejected,
    TransientProviderError,
)
from srbg_api.intelligence_v2.autonomous_policy import (
    AdjudicationInput,
    AutomatedAdjudicationService,
    QualificationPolicyBundle,
)
from srbg_api.intelligence_v2.owner_gold_preparation import (
    FrozenCorpusCase,
    IndependentPrediction,
    PredictionSeal,
    prediction_manifest_sha256,
    prediction_seal_sha256,
)
from srbg_api.intelligence_v2.private_policy_replay import (
    CachingClassificationModelEdge,
    DeepSeekPrivateReplayProvider,
    MappingModelEdge,
    OfflineReplayCase,
    load_private_policy_pack,
    run_offline_policy_replay,
)


class _DeepSeekResponse:
    status_code = 200

    def raise_for_status(self) -> None:
        return None

    def json(self) -> object:
        return {
            "id": "private-replay-request",
            "choices": [
                {
                    "finish_reason": "stop",
                    "message": {
                        "content": json.dumps(_candidate()),
                        "reasoning_content": "must remain private and unused",
                    },
                }
            ],
            "usage": {"prompt_tokens": 100, "completion_tokens": 50},
        }


class _RecordingDeepSeekClient:
    def __init__(self) -> None:
        self.requests: list[tuple[str, dict[str, object]]] = []

    async def post(self, path: str, **kwargs: object) -> _DeepSeekResponse:
        self.requests.append((path, kwargs))
        return _DeepSeekResponse()


class _RateLimitedDeepSeekResponse(_DeepSeekResponse):
    status_code = 429


class _RetryingDeepSeekClient(_RecordingDeepSeekClient):
    async def post(self, path: str, **kwargs: object) -> _DeepSeekResponse:
        self.requests.append((path, kwargs))
        if len(self.requests) == 1:
            return _RateLimitedDeepSeekResponse()
        return _DeepSeekResponse()


def _bundle() -> QualificationPolicyBundle:
    return QualificationPolicyBundle.create(
        policy_version="qualification-policy-2.0.0",
        global_rule_version="global-rules-2.0.0",
        source_stream_policy_version="stream-policy-7",
        ai_provider="protocol-equivalent-test",
        ai_model="semantic-classifier-v2",
        prompt_version="autonomous-classify-2.0.0",
        schema_version="autonomous-classify-output-2.0.0",
        code_version="issue-41-test",
    )


def _candidate() -> dict[str, object]:
    return {
        "direct_relevance": "RELEVANT",
        "core_new_fact": "Railway tunnel construction safety remediation started",
        "primary_type": "SAFETY_INTELLIGENCE",
        "engineering_objects": ["RAILWAY", "TUNNEL"],
        "specialty_facets": [],
        "equipment_domains": [],
        "content_form": "AUTHORITY_NOTICE",
        "evidence_locators": ["html:p:8"],
        "ambiguity_indicators": [],
        "security_signals": [],
        "confidence": 0.01,
    }


def _case(
    *,
    suffix: int,
    text: str,
    expected_relevant: bool,
    expected_primary_type: str | None,
    locked_negative: bool,
) -> OfflineReplayCase:
    return OfflineReplayCase(
        document_version_id=UUID(f"019b1d00-0000-7000-8000-{suffix:012d}"),
        raw_object_id=UUID(f"019b1d00-0000-7000-8001-{suffix:012d}"),
        normalized_input_sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
        document_text=text,
        evidence_locators=frozenset({"html:p:8"}),
        expected_relevant=expected_relevant,
        expected_primary_type=expected_primary_type,
        locked_negative=locked_negative,
    )


@pytest.mark.asyncio
async def test_private_replay_provider_pins_v4_flash_rule_following_profile() -> None:
    client = _RecordingDeepSeekClient()
    provider = DeepSeekPrivateReplayProvider(
        client=client,
        api_key="private-test-key",
        timeout_seconds=45.0,
    )

    candidate = await provider.complete(
        system_prompt="qualification policy",
        user_prompt="untrusted source material",
    )

    assert candidate == _candidate()
    assert len(client.requests) == 1
    path, request = client.requests[0]
    assert path == "/chat/completions"
    payload = request["json"]
    assert isinstance(payload, dict)
    assert payload == {
        "model": "deepseek-v4-flash",
        "messages": [
            {"role": "system", "content": "qualification policy"},
            {"role": "user", "content": "untrusted source material"},
        ],
        "thinking": {"type": "disabled"},
        "response_format": {"type": "json_object"},
        "temperature": 0,
        "max_tokens": 1200,
    }
    assert "tools" not in payload
    assert "stream" not in payload
    assert request["headers"] == {
        "Authorization": "Bearer private-test-key",
        "Content-Type": "application/json",
    }
    assert request["timeout"] == 45.0
    assert "reasoning_content" not in json.dumps(candidate)


@pytest.mark.asyncio
async def test_private_replay_provider_retries_rate_limit_once_then_stops() -> None:
    client = _RetryingDeepSeekClient()
    provider = DeepSeekPrivateReplayProvider(
        client=client,
        api_key="private-test-key",
        retry_delay_seconds=0,
    )

    candidate = await provider.complete(system_prompt="policy", user_prompt="document")

    assert candidate == _candidate()
    assert len(client.requests) == 2
    assert all(request[1]["timeout"] == 90.0 for request in client.requests)


def test_private_replay_runs_real_adjudication_and_returns_aggregate_only() -> None:
    positive = _case(
        suffix=1,
        text="Railway tunnel construction safety remediation started.",
        expected_relevant=True,
        expected_primary_type="SAFETY_INTELLIGENCE",
        locked_negative=False,
    )
    negative = _case(
        suffix=2,
        text="Tourism promotion unrelated to engineering construction.",
        expected_relevant=False,
        expected_primary_type=None,
        locked_negative=True,
    )
    edge = MappingModelEdge(
        {
            positive.normalized_input_sha256: [_candidate()],
        }
    )
    service = AutomatedAdjudicationService(
        policy=_bundle(),
        model_edge=edge,
        clock=lambda: datetime(2026, 7, 21, 8, tzinfo=UTC),
        id_factory=lambda: UUID("019b1d00-0000-7000-8000-000000000041"),
    )

    report = run_offline_policy_replay(
        (positive, negative),
        service=service,
        benchmark_version="private-regression-test",
        corpus_manifest_sha256="c" * 64,
        policy_bundle_sha256=_bundle().identity.bundle_sha256,
    )

    assert report.precision_bps == 10_000
    assert report.recall_bps == 10_000
    assert report.locked_negative_leaks == 0
    assert report.schema_valid_bps == 10_000
    assert report.gate_passed is True
    assert report.authorizes_production is False
    assert set(asdict(report)).isdisjoint(
        {
            "case_id",
            "url",
            "document_text",
            "labels",
            "predictions",
            "decision_traces",
        }
    )


def test_private_replay_can_bound_parallelism_without_changing_case_semantics() -> None:
    barrier = threading.Barrier(2)

    class _ConcurrentEdge:
        def classify(
            self, *, system_prompt: str, document_text: str, semantic_recheck: bool
        ) -> dict[str, object]:
            del system_prompt, document_text
            assert semantic_recheck is False
            barrier.wait(timeout=2)
            return _candidate()

    cases = tuple(
        _case(
            suffix=suffix,
            text=f"Railway tunnel construction safety remediation started {suffix}.",
            expected_relevant=True,
            expected_primary_type="SAFETY_INTELLIGENCE",
            locked_negative=False,
        )
        for suffix in (11, 12)
    )
    service = AutomatedAdjudicationService(
        policy=_bundle(),
        model_edge=_ConcurrentEdge(),
        clock=lambda: datetime(2026, 7, 21, 8, tzinfo=UTC),
        id_factory=lambda: UUID("019b1d00-0000-7000-8000-000000000041"),
    )

    report = run_offline_policy_replay(
        cases,
        service=service,
        benchmark_version="private-parallel-test",
        corpus_manifest_sha256="c" * 64,
        policy_bundle_sha256=_bundle().identity.bundle_sha256,
        offline_max_workers=2,
    )

    assert report.total_cases == 2
    assert report.auto_accepted == 2
    assert report.gate_passed is True


def test_private_pack_loader_verifies_seal_and_keeps_case_data_internal(tmp_path) -> None:
    case_id = "019b1d00-0000-7000-8000-000000000061"
    content = "Railway tunnel construction safety remediation started."
    content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
    timestamp = datetime(2026, 7, 20, 8, tzinfo=UTC)
    frozen_case = FrozenCorpusCase(
        case_id=case_id,
        corpus_version="private-test-v4",
        sampling_stratum="POSITIVE",
        sampling_primary_type="SAFETY_INTELLIGENCE",
        title="private test",
        source_url="https://example.invalid/source",
        rights_basis="test fixture",
        retrieved_at=timestamp,
        raw_object_path="private/raw-object",
        raw_object_sha256="a" * 64,
        normalized_content=content,
        content_sha256=content_hash,
        evidence_locators=("html:p:8",),
    )
    prediction = IndependentPrediction(
        case_id=case_id,
        corpus_version="private-test-v4",
        content_sha256=content_hash,
        rule_version="rules-v1",
        model_id="sealed-model",
        prompt_version="prompt-v1",
        schema_version="schema-v1",
        predicted_at=timestamp,
        predicted_relevant=True,
        primary_type="SAFETY_INTELLIGENCE",
        confidence_bps=9000,
        input_sha256=content_hash,
    )
    canonical = lambda value: json.dumps(  # noqa: E731 - concise fixture hashing helper
        value,
        default=lambda item: item.isoformat() if isinstance(item, datetime) else item,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    corpus_hash = hashlib.sha256(canonical([asdict(frozen_case)])).hexdigest()
    seal = PredictionSeal(
        seal_version="intelligence-v2-owner-gold-prediction-seal-1.0.0",
        corpus_version="private-test-v4",
        rule_version="rules-v1",
        model_id="sealed-model",
        prompt_version="prompt-v1",
        schema_version="schema-v1",
        case_count=1,
        corpus_manifest_sha256=corpus_hash,
        prediction_manifest_sha256=prediction_manifest_sha256([prediction]),
        sealed_at=timestamp,
        seal_sha256="",
    )
    seal = PredictionSeal(**(asdict(seal) | {"seal_sha256": prediction_seal_sha256(seal)}))
    seal_hash = seal.seal_sha256
    blind = {
        "schema_version": "blind-v1",
        "corpus_version": "private-test-v4",
        "prediction_seal_sha256": seal_hash,
        "cases": [
            {
                "case_id": case_id,
                "content_sha256": content_hash,
                "normalized_content": content,
                "evidence_locators": ["html:p:8"],
            }
        ],
    }
    (tmp_path / "blind.json").write_text(json.dumps(blind), encoding="utf-8")
    manifest = {
        "artifact_kind": "OWNER_GOLD_CORPUS_MANIFEST",
        "corpus_version": "private-test-v4",
        "case_design": {},
        "cases": [asdict(frozen_case)],
    }
    manifest_bytes = json.dumps(manifest, default=str).encode("utf-8")
    (tmp_path / "manifest.json").write_bytes(manifest_bytes)
    annotation = {
        "case_id": case_id,
        "corpus_version": "private-test-v4",
        "content_sha256": content_hash,
        "expected_relevant": True,
        "primary_type": "SAFETY_INTELLIGENCE",
        "locked_negative": False,
    }
    annotation_bytes = (json.dumps(annotation) + "\n").encode("utf-8")
    (tmp_path / "annotations.jsonl").write_bytes(annotation_bytes)
    prediction_bytes = (json.dumps(asdict(prediction), default=str) + "\n").encode("utf-8")
    (tmp_path / "predictions.jsonl").write_bytes(prediction_bytes)
    response = {
        "case_id": case_id,
        "input_sha256": content_hash,
        "response": {"output": _candidate()},
    }
    response_bytes = (json.dumps(response) + "\n").encode("utf-8")
    (tmp_path / "responses.jsonl").write_bytes(response_bytes)
    response_hash = hashlib.sha256(response_bytes).hexdigest()
    (tmp_path / "seal.json").write_text(
        json.dumps(asdict(seal), default=str), encoding="utf-8"
    )
    attempt = {
        "artifact_kind": "OWNER_GOLD_ATTEMPT",
        "corpus_version": "private-test-v4",
        "prediction_seal_sha256": seal_hash,
        "corpus_manifest_file_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "attempt_labels_sha256": hashlib.sha256(annotation_bytes).hexdigest(),
    }
    attempt["attempt_manifest_sha256"] = hashlib.sha256(canonical(attempt)).hexdigest()
    (tmp_path / "attempt.json").write_text(json.dumps(attempt), encoding="utf-8")

    loaded = load_private_policy_pack(
        tmp_path,
        expected_attempt_manifest_sha256=str(attempt["attempt_manifest_sha256"]),
        expected_response_artifact_sha256=response_hash,
    )

    assert loaded.benchmark_version == "private-test-v4"
    assert loaded.corpus_manifest_sha256 == hashlib.sha256(manifest_bytes).hexdigest()
    assert len(loaded.cases) == 1
    assert set(loaded.responses) == {content_hash}

    (tmp_path / "blind.json").write_text(
        json.dumps(blind | {"cases": [blind["cases"][0], blind["cases"][0]]}),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="PRIVATE_REPLAY_CASE_DUPLICATE"):
        load_private_policy_pack(
            tmp_path,
            expected_attempt_manifest_sha256=str(attempt["attempt_manifest_sha256"]),
            expected_response_artifact_sha256=response_hash,
        )
    (tmp_path / "blind.json").write_text(json.dumps(blind), encoding="utf-8")

    duplicate_annotation_bytes = annotation_bytes + annotation_bytes
    duplicate_annotation_attempt = attempt | {
        "attempt_labels_sha256": hashlib.sha256(duplicate_annotation_bytes).hexdigest(),
    }
    duplicate_annotation_payload = dict(duplicate_annotation_attempt)
    duplicate_annotation_payload.pop("attempt_manifest_sha256")
    duplicate_annotation_attempt["attempt_manifest_sha256"] = hashlib.sha256(
        canonical(duplicate_annotation_payload)
    ).hexdigest()
    (tmp_path / "annotations.jsonl").write_bytes(duplicate_annotation_bytes)
    (tmp_path / "attempt.json").write_text(
        json.dumps(duplicate_annotation_attempt), encoding="utf-8"
    )
    with pytest.raises(ValueError, match="PRIVATE_REPLAY_ANNOTATION_DUPLICATE"):
        load_private_policy_pack(
            tmp_path,
            expected_attempt_manifest_sha256=str(
                duplicate_annotation_attempt["attempt_manifest_sha256"]
            ),
            expected_response_artifact_sha256=response_hash,
        )
    (tmp_path / "annotations.jsonl").write_bytes(annotation_bytes)
    (tmp_path / "attempt.json").write_text(json.dumps(attempt), encoding="utf-8")

    duplicate_response_bytes = response_bytes + response_bytes
    (tmp_path / "responses.jsonl").write_bytes(duplicate_response_bytes)
    with pytest.raises(ValueError, match="PRIVATE_REPLAY_RESPONSE_DUPLICATE"):
        load_private_policy_pack(
            tmp_path,
            expected_attempt_manifest_sha256=str(attempt["attempt_manifest_sha256"]),
            expected_response_artifact_sha256=hashlib.sha256(
                duplicate_response_bytes
            ).hexdigest(),
        )
    (tmp_path / "responses.jsonl").write_bytes(response_bytes)

    (tmp_path / "attempt.json").write_text(
        json.dumps(attempt | {"tampered": True}), encoding="utf-8"
    )
    with pytest.raises(ValueError, match="PRIVATE_REPLAY_ATTEMPT_MANIFEST_INVALID"):
        load_private_policy_pack(
            tmp_path,
            expected_attempt_manifest_sha256=str(attempt["attempt_manifest_sha256"]),
            expected_response_artifact_sha256=response_hash,
        )
    (tmp_path / "attempt.json").write_text(json.dumps(attempt), encoding="utf-8")

    tampered_response = response | {
        "response": {"output": _candidate() | {"engineering_objects": ["HIGHWAY"]}}
    }
    (tmp_path / "responses.jsonl").write_text(
        json.dumps(tampered_response) + "\n", encoding="utf-8"
    )
    with pytest.raises(ValueError, match="PRIVATE_REPLAY_RESPONSE_ARTIFACT_MISMATCH"):
        load_private_policy_pack(
            tmp_path,
            expected_attempt_manifest_sha256=str(attempt["attempt_manifest_sha256"]),
            expected_response_artifact_sha256=response_hash,
        )


def test_live_edge_keeps_candidates_document_and_labels_process_local(tmp_path) -> None:
    document = "Railway tunnel construction safety remediation started."
    content_hash = hashlib.sha256(document.encode("utf-8")).hexdigest()
    prompts: list[str] = []
    received_hashes: list[str] = []

    def fetcher(
        *, system_prompt: str, user_prompt: str, input_sha256: str
    ) -> dict[str, object]:
        prompts.append(system_prompt + user_prompt)
        received_hashes.append(input_sha256)
        return _candidate()

    cache_path = tmp_path / "private-candidates.json"
    edge = CachingClassificationModelEdge(
        evidence_locators_by_hash={content_hash: ("html:p:8",)},
        fetch_candidate=fetcher,
    )

    first = edge.classify(
        system_prompt="policy",
        document_text=document,
        semantic_recheck=False,
    )
    corrected = edge.classify(
        system_prompt="policy",
        document_text=document,
        semantic_recheck=True,
    )

    assert first == corrected == _candidate()
    assert len(prompts) == 2
    assert received_hashes == [content_hash, content_hash]
    assert "independent final verifier" in prompts[1]
    assert "Populate every evidence-supported axis" in prompts[1]
    assert "Never omit primary_type or evidence_locators" in prompts[1]
    assert "先识别标题和首段表达的中心新事实" in prompts[1]
    assert "物理工程项目节点属于 INDUSTRY_UPDATE" in prompts[1]
    assert "鍏堣瘑" not in prompts[1]
    assert not cache_path.exists()


def test_live_edge_turns_provider_output_rejection_into_bounded_recheck() -> None:
    document = "Railway tunnel construction safety remediation started."
    content_hash = hashlib.sha256(document.encode("utf-8")).hexdigest()
    attempts = 0

    def fetcher(
        *, system_prompt: str, user_prompt: str, input_sha256: str
    ) -> dict[str, object]:
        del system_prompt, user_prompt, input_sha256
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise ModelOutputRejected("provider returned invalid JSON")
        return _candidate()

    edge = CachingClassificationModelEdge(
        evidence_locators_by_hash={content_hash: ("html:p:8",)},
        fetch_candidate=fetcher,
    )
    service = AutomatedAdjudicationService(
        policy=_bundle(),
        model_edge=edge,
        clock=lambda: datetime(2026, 7, 21, 8, tzinfo=UTC),
        id_factory=lambda: UUID("019b1d00-0000-7000-8000-000000000041"),
    )

    trace = service.adjudicate(
        AdjudicationInput(
            document_version_id=UUID("019b1d00-0000-7000-8000-000000000071"),
            raw_object_id=UUID("019b1d00-0000-7000-8000-000000000072"),
            normalized_input_sha256=content_hash,
            document_text=document,
            allowed_evidence_locators=frozenset({"html:p:8"}),
        )
    )

    assert attempts == 2
    assert trace.semantic_recheck_count == 1
    assert trace.disposition.value == "AUTO_ACCEPTED"


def test_live_edge_maps_transient_provider_failure_to_stable_retry() -> None:
    document = "Railway tunnel construction safety remediation started."
    content_hash = hashlib.sha256(document.encode("utf-8")).hexdigest()

    def fetcher(**_: str) -> dict[str, object]:
        raise TransientProviderError("temporary provider failure")

    service = AutomatedAdjudicationService(
        policy=_bundle(),
        model_edge=CachingClassificationModelEdge(
            evidence_locators_by_hash={content_hash: ("html:p:8",)},
            fetch_candidate=fetcher,
        ),
        clock=lambda: datetime(2026, 7, 21, 8, tzinfo=UTC),
        id_factory=lambda: UUID("019b1d00-0000-7000-8000-000000000041"),
    )

    trace = service.adjudicate(
        AdjudicationInput(
            document_version_id=UUID("019b1d00-0000-7000-8000-000000000073"),
            raw_object_id=UUID("019b1d00-0000-7000-8000-000000000074"),
            normalized_input_sha256=content_hash,
            document_text=document,
            allowed_evidence_locators=frozenset({"html:p:8"}),
        )
    )

    assert trace.disposition.value == "TECHNICAL_RETRY"
    assert trace.reason_codes == ["TECHNICAL_RETRYABLE"]
    assert trace.semantic_recheck_count == 0
