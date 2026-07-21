"""Run the sealed autonomous-policy benchmark and print aggregate metrics only."""

from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx2 as httpx
from srbg_api.ai_pipeline.budget import BudgetPolicy
from srbg_api.ai_pipeline.contracts import AiStep, ModelRequest
from srbg_api.ai_pipeline.gateway import (
    DeepSeekProvider,
    HttpResponse,
    ModelOutputRejected,
    TransientProviderError,
)
from srbg_api.identifiers import uuid7
from srbg_api.intelligence_v2.autonomous_policy import (
    AutomatedAdjudicationService,
    QualificationPolicyBundle,
)
from srbg_api.intelligence_v2.private_policy_replay import (
    CachingClassificationModelEdge,
    MappingModelEdge,
    load_private_policy_pack,
    run_offline_policy_replay,
)
from srbg_contracts import AutonomousClassificationCandidate

_PUBLIC_AGGREGATES = (
    "total_cases",
    "auto_accepted",
    "auto_filtered",
    "technical_retry",
    "technical_failed",
    "safety_hold",
    "owner_suppressed",
    "precision_bps",
    "recall_bps",
    "locked_negative_leaks",
    "schema_valid_bps",
    "new_owner_semantic_tasks",
    "gate_passed",
    "authorizes_production",
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--pack-root", type=Path, required=True)
    parser.add_argument("--code-version", required=True)
    parser.add_argument("--attempt-manifest-sha256", required=True)
    parser.add_argument("--response-artifact-sha256", required=True)
    parser.add_argument("--api-key-file", type=Path)
    parser.add_argument("--candidate-cache", type=Path)
    return parser


def _read_api_key(path: Path) -> str:
    value = path.read_text(encoding="utf-8")
    if not value or len(value) > 4096 or any(character in value for character in "\r\n\x00"):
        raise ValueError("PRIVATE_REPLAY_API_KEY_INVALID")
    return value


class DeepSeekPolicyCandidateFetcher:
    def __init__(self, *, api_key: str, timeout_seconds: float = 30.0) -> None:
        self._api_key = api_key
        self._timeout_seconds = timeout_seconds

    def __call__(
        self, *, system_prompt: str, user_prompt: str, input_sha256: str
    ) -> dict[str, object]:
        return asyncio.run(
            self._fetch(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                input_sha256=input_sha256,
            )
        )

    async def _fetch(
        self, *, system_prompt: str, user_prompt: str, input_sha256: str
    ) -> dict[str, object]:
        policy = BudgetPolicy.deepseek_v4_flash()
        request = ModelRequest(
            step=AiStep.CLASSIFY,
            prompt_version="autonomous-classify-2.3.0",
            schema_version="autonomous-classify-output-2.0.0",
            model_profile="deepseek-v4-flash",
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            input_sha256=input_sha256,
            response_schema=AutonomousClassificationCandidate.model_json_schema(),
            parameters={"temperature": 0, "max_tokens": 1200},
            data_classification="PUBLIC_SOURCE",
            input_price_microusd_per_million=(policy.cache_miss_microusd_per_million),
            cache_hit_input_price_microusd_per_million=(policy.cache_hit_microusd_per_million),
            output_price_microusd_per_million=policy.output_microusd_per_million,
        )
        try:
            async with httpx.AsyncClient(
                base_url="https://api.deepseek.com",
                follow_redirects=False,
            ) as client:
                result = await DeepSeekProvider(
                    client=_HttpxClientAdapter(client),
                    api_key=self._api_key,
                    timeout_seconds=self._timeout_seconds,
                ).complete(request)
        except httpx.TransportError as exc:
            raise TransientProviderError("policy model transport failed") from exc
        try:
            decoded = json.loads(result.content)
        except json.JSONDecodeError as exc:
            raise ModelOutputRejected("policy model returned invalid JSON") from exc
        if not isinstance(decoded, dict):
            raise ModelOutputRejected("policy model output must be an object")
        return decoded


class _HttpxClientAdapter:
    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client

    async def post(self, path: str, **kwargs: Any) -> HttpResponse:
        response = await self._client.post(path, **kwargs)
        if response.status_code in {502, 504}:
            raise TransientProviderError("policy model gateway is temporarily unavailable")
        return response


def main() -> int:
    try:
        args = _parser().parse_args()
        pack = load_private_policy_pack(
            args.pack_root,
            expected_attempt_manifest_sha256=args.attempt_manifest_sha256,
            expected_response_artifact_sha256=args.response_artifact_sha256,
        )
        use_live_model = args.api_key_file is not None
        if use_live_model != (args.candidate_cache is not None):
            raise ValueError("PRIVATE_REPLAY_LIVE_ARGUMENTS_INCOMPLETE")
        policy = QualificationPolicyBundle.create(
            policy_version="qualification-policy-2.0.0",
            global_rule_version="global-rules-2.0.0",
            source_stream_policy_version="owner-gold-private-v4",
            ai_provider="deepseek" if use_live_model else "protocol-equivalent-recorded",
            ai_model="deepseek-v4-flash" if use_live_model else "semantic-classifier-v2",
            prompt_version="autonomous-classify-2.3.0",
            schema_version="autonomous-classify-output-2.0.0",
            code_version=args.code_version,
        )
        model_edge = (
            CachingClassificationModelEdge(
                evidence_locators_by_hash={
                    case.normalized_input_sha256: tuple(case.evidence_locators)
                    for case in pack.cases
                },
                fetch_candidate=DeepSeekPolicyCandidateFetcher(
                    api_key=_read_api_key(args.api_key_file)
                ),
                cache_path=args.candidate_cache,
                policy_identity=policy.identity,
            )
            if args.api_key_file is not None and args.candidate_cache is not None
            else MappingModelEdge(pack.responses)
        )
        service = AutomatedAdjudicationService(
            policy=policy,
            model_edge=model_edge,
            clock=lambda: datetime.now(UTC),
            id_factory=uuid7,
        )
        report = run_offline_policy_replay(
            pack.cases,
            service=service,
            benchmark_version=pack.benchmark_version,
            corpus_manifest_sha256=pack.corpus_manifest_sha256,
            policy_bundle_sha256=policy.identity.bundle_sha256,
        )
        values = asdict(report)
        print(
            json.dumps(
                {name: values[name] for name in _PUBLIC_AGGREGATES},
                separators=(",", ":"),
                sort_keys=True,
            )
        )
        return 0 if report.gate_passed else 1
    except Exception as exc:
        print(
            json.dumps(
                {
                    "error": "PRIVATE_REPLAY_FAILED",
                    "category": type(exc).__name__,
                },
                separators=(",", ":"),
                sort_keys=True,
            )
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
