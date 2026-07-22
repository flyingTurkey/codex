"""Shared atomic writer for immutable autonomous qualification decisions."""

from __future__ import annotations

import json

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection
from srbg_contracts import QualificationDecisionTrace

from srbg_api.identifiers import uuid7
from srbg_api.intelligence_v2.autonomous_policy import QualificationPolicyBundle


async def append_qualification_decision(
    connection: AsyncConnection,
    *,
    trace: QualificationDecisionTrace,
    policy: QualificationPolicyBundle,
) -> None:
    """Persist the exact policy identity and decision in the caller's transaction."""

    identity = policy.identity
    policy_payload = {
        "identity": identity.model_dump(mode="json"),
        "source_allow_terms": list(policy.source_allow_terms),
        "source_exclude_terms": list(policy.source_exclude_terms),
        "maximum_semantic_rechecks": 1,
    }
    await connection.execute(
        text(
            "INSERT INTO qualification_policy_bundle_v2("
            "id,policy_version,global_rule_version,source_stream_policy_version,"
            "ai_provider,ai_model,prompt_version,schema_version,code_version,"
            "authorization_basis,policy_payload,bundle_sha256,created_at) VALUES("
            ":id,:policy_version,:global_rule_version,:stream_version,:provider,:model,"
            ":prompt_version,:schema_version,:code_version,'SERVER_ADJUDICATION_ONLY',"
            "CAST(:payload AS jsonb),:bundle_sha256,:now) "
            "ON CONFLICT (bundle_sha256) DO NOTHING"
        ),
        {
            "id": uuid7(),
            "policy_version": identity.policy_version,
            "global_rule_version": identity.global_rule_version,
            "stream_version": identity.source_stream_policy_version,
            "provider": identity.ai_provider,
            "model": identity.ai_model,
            "prompt_version": identity.prompt_version,
            "schema_version": identity.schema_version,
            "code_version": identity.code_version,
            "payload": json.dumps(policy_payload, ensure_ascii=False, sort_keys=True),
            "bundle_sha256": identity.bundle_sha256,
            "now": trace.decided_at,
        },
    )
    bundle_id = await connection.scalar(
        text("SELECT id FROM qualification_policy_bundle_v2 WHERE bundle_sha256=:bundle_sha256"),
        {"bundle_sha256": identity.bundle_sha256},
    )
    if bundle_id is None:
        raise RuntimeError("QUALIFICATION_POLICY_BUNDLE_NOT_PERSISTED")
    await connection.execute(
        text(
            "INSERT INTO automated_qualification_decision_v2("
            "id,policy_bundle_id,document_version_id,raw_object_id,"
            "normalized_input_sha256,disposition,reason_codes,rule_signals,"
            "model_candidate,evidence_locators,semantic_recheck_count,attempt_number,"
            "decided_at) VALUES(:id,:bundle_id,:version_id,:raw_id,:input_hash,"
            ":disposition,:reasons,CAST(:signals AS jsonb),CAST(:candidate AS jsonb),"
            ":locators,:rechecks,:attempt,:decided_at) "
            "ON CONFLICT (document_version_id,policy_bundle_id,attempt_number) DO NOTHING"
        ),
        {
            "id": trace.decision_id,
            "bundle_id": bundle_id,
            "version_id": trace.document_version_id,
            "raw_id": trace.raw_object_id,
            "input_hash": trace.normalized_input_sha256,
            "disposition": trace.disposition.value,
            "reasons": [reason.value for reason in trace.reason_codes],
            "signals": json.dumps(trace.rule_signals, ensure_ascii=False),
            "candidate": json.dumps(
                None
                if trace.model_candidate is None
                else trace.model_candidate.model_dump(mode="json"),
                ensure_ascii=False,
            ),
            "locators": trace.evidence_locators,
            "rechecks": trace.semantic_recheck_count,
            "attempt": trace.attempt_number,
            "decided_at": trace.decided_at,
        },
    )
