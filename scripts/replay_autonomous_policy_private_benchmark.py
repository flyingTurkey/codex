"""Run the sealed autonomous-policy benchmark and print aggregate metrics only."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx2 as httpx
from srbg_api.ai_pipeline.gateway import (
    HttpResponse,
    TransientProviderError,
)
from srbg_api.identifiers import uuid7
from srbg_api.intelligence_v2.autonomous_policy import (
    AutomatedAdjudicationService,
    QualificationPolicyBundle,
)
from srbg_api.intelligence_v2.private_policy_replay import (
    CachingClassificationModelEdge,
    DeepSeekPrivateReplayProvider,
    MappingModelEdge,
    PrivateModelInvocationAudit,
    load_private_policy_pack,
    run_offline_policy_replay,
)
from srbg_contracts import QualificationDecisionTrace

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
    parser.add_argument("--audit-output", type=Path)
    return parser


def _read_api_key(path: Path) -> str:
    try:
        if path.stat().st_size > 4096:
            raise ValueError("PRIVATE_REPLAY_API_KEY_INVALID")
        value = path.read_bytes().decode("utf-8")
    except (OSError, UnicodeError) as exc:
        raise ValueError("PRIVATE_REPLAY_API_KEY_INVALID") from exc
    if not value or len(value) > 4096 or any(character in value for character in "\r\n\x00"):
        raise ValueError("PRIVATE_REPLAY_API_KEY_INVALID")
    return value


class DeepSeekPolicyCandidateFetcher:
    def __init__(
        self,
        *,
        api_key: str,
        prompt_version: str,
        schema_version: str,
        policy_bundle_sha256: str,
        timeout_seconds: float = 90.0,
    ) -> None:
        self._api_key = api_key
        self._timeout_seconds = timeout_seconds
        self._prompt_version = prompt_version
        self._schema_version = schema_version
        self._policy_bundle_sha256 = policy_bundle_sha256
        self._audits: list[PrivateModelInvocationAudit] = []
        self._audit_records: list[dict[str, object]] = []

    @property
    def audits(self) -> tuple[PrivateModelInvocationAudit, ...]:
        return tuple(self._audits)

    @property
    def audit_records(self) -> tuple[dict[str, object], ...]:
        return tuple(dict(record) for record in self._audit_records)

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
        try:
            async with httpx.AsyncClient(
                base_url="https://api.deepseek.com",
                follow_redirects=False,
            ) as client:
                provider = DeepSeekPrivateReplayProvider(
                    client=_HttpxClientAdapter(client),
                    api_key=self._api_key,
                    timeout_seconds=self._timeout_seconds,
                )
                try:
                    candidate = await provider.complete(
                        system_prompt=system_prompt,
                        user_prompt=user_prompt,
                    )
                finally:
                    self._audits.extend(provider.audits)
                    for audit in provider.audits:
                        self._audit_records.append(
                            {
                                "model_id": audit.model_id,
                                "prompt_version": self._prompt_version,
                                "schema_version": self._schema_version,
                                "policy_bundle_sha256": self._policy_bundle_sha256,
                                "input_document_sha256": input_sha256,
                                "prompt_sha256": audit.prompt_sha256,
                                "output_sha256": audit.output_sha256,
                                "latency_ms": audit.latency_ms,
                                "input_tokens": audit.input_tokens,
                                "output_tokens": audit.output_tokens,
                                "cost_microusd": audit.cost_microusd,
                                "outcome": audit.outcome,
                            }
                        )
                return candidate
        except httpx.TransportError as exc:
            raise TransientProviderError("policy model transport failed") from exc


class _HttpxClientAdapter:
    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client

    async def post(self, path: str, **kwargs: Any) -> HttpResponse:
        return await self._client.post(path, **kwargs)


class _ProcessLocalDecisionSink:
    def __init__(self) -> None:
        self.traces: list[QualificationDecisionTrace] = []

    def append(self, trace: QualificationDecisionTrace) -> None:
        self.traces.append(trace)


def _persist_private_audit(path: Path, records: tuple[dict[str, object], ...]) -> None:
    data_root_value = os.environ.get("SRBG_DATA_ROOT", "")
    if not data_root_value:
        raise ValueError("PRIVATE_REPLAY_DATA_ROOT_REQUIRED")
    data_root = Path(data_root_value).resolve()
    resolved = path.resolve()
    if not resolved.is_relative_to(data_root) or not resolved.parent.is_dir():
        raise ValueError("PRIVATE_REPLAY_AUDIT_PATH_INVALID")
    canonical_records = json.dumps(
        records,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    payload = {
        "artifact_kind": "PRIVATE_POLICY_INVOCATION_AUDIT",
        "record_count": len(records),
        "records_sha256": hashlib.sha256(canonical_records).hexdigest(),
        "records": records,
    }
    with resolved.open("x", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def main() -> int:
    try:
        args = _parser().parse_args()
        pack = load_private_policy_pack(
            args.pack_root,
            expected_attempt_manifest_sha256=args.attempt_manifest_sha256,
            expected_response_artifact_sha256=args.response_artifact_sha256,
        )
        use_live_model = args.api_key_file is not None
        if use_live_model != (args.audit_output is not None):
            raise ValueError("PRIVATE_REPLAY_LIVE_AUDIT_REQUIRED")
        policy = QualificationPolicyBundle.create(
            policy_version="qualification-policy-2.2.0",
            global_rule_version="global-rules-2.1.0",
            source_stream_policy_version="owner-gold-private-v4",
            ai_provider="deepseek" if use_live_model else "protocol-equivalent-recorded",
            ai_model="deepseek-v4-flash" if use_live_model else "semantic-classifier-v2",
            prompt_version="autonomous-classify-2.7.0",
            schema_version="autonomous-classify-output-2.0.0",
            code_version=args.code_version,
        )
        live_fetcher = (
            DeepSeekPolicyCandidateFetcher(
                api_key=_read_api_key(args.api_key_file),
                prompt_version=policy.identity.prompt_version,
                schema_version=policy.identity.schema_version,
                policy_bundle_sha256=policy.identity.bundle_sha256,
            )
            if args.api_key_file is not None
            else None
        )
        model_edge = (
            CachingClassificationModelEdge(
                evidence_locators_by_hash={
                    case.normalized_input_sha256: tuple(case.evidence_locators)
                    for case in pack.cases
                },
                fetch_candidate=live_fetcher,
            )
            if args.api_key_file is not None
            else MappingModelEdge(pack.responses)
        )
        decision_sink = _ProcessLocalDecisionSink()
        service = AutomatedAdjudicationService(
            policy=policy,
            model_edge=model_edge,
            clock=lambda: datetime.now(UTC),
            id_factory=uuid7,
            decision_sink=decision_sink,
        )
        try:
            report = run_offline_policy_replay(
                pack.cases,
                service=service,
                benchmark_version=pack.benchmark_version,
                corpus_manifest_sha256=pack.corpus_manifest_sha256,
                policy_bundle_sha256=policy.identity.bundle_sha256,
                offline_max_workers=2 if use_live_model else 1,
            )
        finally:
            if (
                live_fetcher is not None
                and live_fetcher.audit_records
                and args.audit_output is not None
            ):
                _persist_private_audit(args.audit_output, live_fetcher.audit_records)
        if len(decision_sink.traces) != report.total_cases:
            raise ValueError("PRIVATE_REPLAY_DECISION_TRACE_INCOMPLETE")
        if live_fetcher is not None:
            if not live_fetcher.audit_records:
                raise ValueError("PRIVATE_REPLAY_AUDIT_INCOMPLETE")
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
