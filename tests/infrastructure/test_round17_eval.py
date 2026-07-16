from __future__ import annotations

import base64
import copy
import json
import sys
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path
from typing import Any

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

import scripts.round17_eval as round17_eval
from scripts.round17_eval import (
    EXPECTED_DATABASE_REVISION,
    METRICS_DEFINITION_PATH,
    canonical_sha256,
    evaluate_round17_files,
    evaluate_round17_payloads,
    main,
)

ROOT = Path(__file__).resolve().parents[2]
LEO = "01900000-0000-7000-8000-000000000001"
YINZI = "01900000-0000-7000-8000-000000000002"
BAIXUEJIAO = "01900000-0000-7000-8000-000000000003"
STARTED_AT = datetime(2026, 7, 1, 0, 0, tzinfo=UTC)
ENDED_AT = STARTED_AT + timedelta(hours=168)
TRUST_SIGNATURE_FIELD = "trust_signature"


def _timestamp(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _digest(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()


def _uuid7(index: int) -> str:
    return f"01900000-0000-7000-8000-{index:012d}"


def _canonical_bytes(value: dict[str, Any], *, excluded_keys: set[str]) -> bytes:
    payload = {key: item for key, item in value.items() if key not in excluded_keys}
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _sign_evidence(
    evidence: dict[str, Any],
    signing: dict[str, Any],
    *,
    recompute_manifest: bool = True,
) -> None:
    evidence.pop(TRUST_SIGNATURE_FIELD, None)
    if recompute_manifest:
        evidence["manifest_sha256"] = canonical_sha256(
            evidence,
            excluded_keys={"manifest_sha256", TRUST_SIGNATURE_FIELD},
        )
    signature = signing["private_key"].sign(
        _canonical_bytes(evidence, excluded_keys={TRUST_SIGNATURE_FIELD})
    )
    evidence[TRUST_SIGNATURE_FIELD] = {
        "algorithm": "Ed25519",
        "key_fingerprint_sha256": signing["fingerprint"],
        "signature_base64": base64.b64encode(signature).decode("ascii"),
    }


def _ref(root: Path, relative: str, content: str) -> dict[str, str]:
    target = root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return {"uri": relative.replace("\\", "/"), "sha256": sha256(target.read_bytes()).hexdigest()}


def _run_database_statement(run: dict[str, Any]) -> dict[str, Any]:
    response_metadata = run.get("response_metadata")
    return {
        "query_id": "round17.authoritative_run_record.v1",
        "query_version": "v1",
        "database_revision": EXPECTED_DATABASE_REVISION,
        "run_id": run.get("run_id"),
        "source_key": run.get("source_key"),
        "source_id": run.get("source_id"),
        "window_id": run.get("window_id"),
        "segment_id": run.get("segment_id"),
        "scheduled_slot_at": run.get("scheduled_slot_at"),
        "started_at": run.get("started_at"),
        "ended_at": run.get("ended_at"),
        "outcome": run.get("outcome"),
        "response_state": run.get("response_state"),
        "request_count": run.get("request_count"),
        "response_bytes": (
            response_metadata.get("response_bytes")
            if isinstance(response_metadata, dict)
            else None
        ),
        "transport_failure_code": run.get("transport_failure_code"),
        "failure_detected_at": run.get("failure_detected_at"),
        "recovered": run.get("recovered") is True,
        "recovery_of_run_id": run.get("recovery_of_run_id"),
    }


def _actor(display_name: str, subject: str, roles: list[str]) -> dict[str, Any]:
    return {
        "display_name": display_name,
        "subject": subject,
        "issuer": "https://sso.srbg.cn/realms/internal",
        "identity_provider": "OIDC",
        "is_local": False,
        "roles": roles,
    }


def _gold_record(
    *,
    index: int,
    kind: str,
    source_key: str,
    domain: str,
    key_safety: bool,
    authorization_ref: dict[str, str],
    gold_release_id: str,
) -> dict[str, Any]:
    record_id = f"{kind}-{index:04d}"
    primary = YINZI if key_safety else BAIXUEJIAO
    primary_label_code = "SUPPORTED" if key_safety else "ACCEPTED"
    primary_label = _digest(f"gold-label:{primary_label_code}")
    secondary: dict[str, Any] | None = None
    arbitration: dict[str, Any] | None = None
    if key_safety:
        secondary_label_code = "SUPPORTED" if index != 0 else "UNSUPPORTED"
        secondary = {
            "annotator_subject": BAIXUEJIAO,
            "label_code": secondary_label_code,
            "label_sha256": _digest(f"gold-label:{secondary_label_code}"),
            "annotated_at": _timestamp(STARTED_AT - timedelta(days=2)),
            "blinded": True,
        }
        if secondary_label_code != primary_label_code:
            arbitration = {
                "arbitrator_subject": LEO,
                "resolved_label_code": primary_label_code,
                "resolved_label_sha256": primary_label,
                "arbitrated_at": _timestamp(STARTED_AT - timedelta(days=1)),
            }
    elif domain == "DIGITAL" and index % 5 == 0:
        secondary = {
            "annotator_subject": YINZI,
            "label_code": primary_label_code,
            "label_sha256": primary_label,
            "annotated_at": _timestamp(STARTED_AT - timedelta(days=2)),
            "blinded": True,
        }
    record: dict[str, Any] = {
        "id": record_id,
        "sample_kind": {
            "documents": "DOCUMENT",
            "duplicate_pairs": "DUPLICATE_PAIR",
            "event_clusters": "EVENT_CLUSTER",
            "claim_evidence_annotations": "CLAIM_EVIDENCE",
            "search_questions": "SEARCH_QUESTION",
        }[kind],
        "source_key": source_key,
        "domain": domain,
        "key_safety": key_safety,
        "content_sha256": _digest(f"content:{record_id}"),
        "authorization_ref": authorization_ref,
        "gold_release_id": gold_release_id,
        "annotation": {
            "primary": {
                "annotator_subject": primary,
                "label_code": primary_label_code,
                "label_sha256": primary_label,
                "annotated_at": _timestamp(STARTED_AT - timedelta(days=2)),
            },
            "secondary": secondary,
            "arbitration": arbitration,
        },
        "created_at": _timestamp(STARTED_AT - timedelta(days=2)),
    }
    if kind == "documents":
        record["document_id"] = _uuid7(300_000 + index)
    elif kind == "duplicate_pairs":
        record.update(
            {
                "left_document_id": _uuid7(300_000 + ((index * 2) % 500)),
                "right_document_id": _uuid7(300_000 + ((index * 2 + 1) % 500)),
                "relationship_code": "SAME_EVENT" if index % 2 == 0 else "DIFFERENT_EVENT",
            }
        )
    elif kind == "event_clusters":
        record.update(
            {
                "member_document_ids": [
                    _uuid7(300_000 + ((index * 2) % 500)),
                    _uuid7(300_000 + ((index * 2 + 1) % 500)),
                ],
                "high_value": True,
            }
        )
    elif kind == "claim_evidence_annotations":
        record.update(
            {
                "claim_id": _uuid7(400_000 + index * 2),
                "evidence_id": _uuid7(400_000 + index * 2 + 1),
                "fact_kind": "CRITICAL_SAFETY_FACT" if key_safety else "OTHER_FACT",
            }
        )
    else:
        record.update(
            {
                "question_id": _uuid7(500_000 + index),
                "expected_event_cluster_ids": [f"event_clusters-{index % 100:04d}"],
            }
        )
    return record


@pytest.fixture(scope="module")
def valid_bundle(
    tmp_path_factory: pytest.TempPathFactory,
) -> tuple[Path, dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    root = tmp_path_factory.mktemp("round17-eval")
    private_key = Ed25519PrivateKey.generate()
    public_key: Ed25519PublicKey = private_key.public_key()
    raw_public_key = public_key.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    public_key_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    public_key_path = root / "trust/round17-evaluator-public.pem"
    public_key_path.parent.mkdir(parents=True, exist_ok=True)
    public_key_path.write_bytes(public_key_pem)
    signing: dict[str, Any] = {
        "private_key": private_key,
        "public_key_pem": public_key_pem,
        "public_key_path": public_key_path,
        "fingerprint": sha256(raw_public_key).hexdigest(),
    }
    metrics = json.loads(METRICS_DEFINITION_PATH.read_text(encoding="utf-8"))
    source_keys = [entry["source_key"] for entry in metrics["source_roster"]]
    approval_refs = {
        source_key: _ref(
            root, f"artifacts/approvals/{source_key}.json", f'{{"source":"{source_key}"}}'
        )
        for source_key in source_keys
    }
    metrics_ref = _ref(
        root,
        "definitions/round17-metrics.json",
        METRICS_DEFINITION_PATH.read_text(encoding="utf-8"),
    )
    roster_sha256 = canonical_sha256(
        {
            "roster_version": metrics["roster_version"],
            "source_roster": metrics["source_roster"],
        }
    )
    preflight_statement: dict[str, Any] = {
        "decision_id": "01900000-0000-7000-8000-000000000170",
        "approver_subject": LEO,
        "confirmed_at": _timestamp(STARTED_AT - timedelta(hours=1)),
        "mfa_verified_at": _timestamp(STARTED_AT - timedelta(hours=1)),
        "roster_version": metrics["roster_version"],
        "roster_sha256": roster_sha256,
        "metrics_definition_version": metrics["version"],
        "metrics_definition_sha256": metrics_ref["sha256"],
        "window_seconds": 604800,
    }
    preflight_statement["confirmation_sha256"] = canonical_sha256(preflight_statement)
    preflight_ref = _ref(
        root,
        "artifacts/approvals/round17-preflight.json",
        json.dumps(preflight_statement, ensure_ascii=False, sort_keys=True),
    )

    actors = {
        "LEO": _actor("LEO", LEO, ["source_admin", "reviewer"]),
        "yinzi": _actor("yinzi", YINZI, ["source_admin", "gold_annotator"]),
        "baixuejiao": _actor("baixuejiao", BAIXUEJIAO, ["gold_annotator"]),
    }
    gold_release_id = _uuid7(170_001)
    db_manifest_sha256 = _digest("round17-db-gold-manifest")
    released_at = _timestamp(STARTED_AT - timedelta(hours=1))
    release_audit_statement = {
        "audit_action": "ROUND17_GOLD_RELEASE_FROZEN",
        "gold_release_id": gold_release_id,
        "version": "phase2-round17-gold-v1.0.0",
        "roster_version": "r17-sources-v0.1",
        "gold_definition_version": "phase2-round17-gold-v1.0.0",
        "db_manifest_sha256": db_manifest_sha256,
        "status": "FROZEN",
        "frozen_by_subject": LEO,
        "frozen_at": released_at,
    }
    release_audit_ref = _ref(
        root,
        "artifacts/gold/round17-release-audit.json",
        json.dumps(release_audit_statement, ensure_ascii=False, sort_keys=True),
    )
    gold: dict[str, Any] = {
        "schema_version": "1.0.0",
        "version": "phase2-round17-gold-v1.0.0",
        "roster_version": "r17-sources-v0.1",
        "metrics_definition_version": metrics["version"],
        "gold_release_id": gold_release_id,
        "db_manifest_sha256": db_manifest_sha256,
        "release_audit_ref": release_audit_ref,
        "actors": actors,
        "released_by_subject": LEO,
        "released_at": released_at,
        "documents": [],
        "duplicate_pairs": [],
        "event_clusters": [],
        "claim_evidence_annotations": [],
        "search_questions": [],
    }
    collection_sizes = {
        "documents": 500,
        "duplicate_pairs": 300,
        "event_clusters": 100,
        "claim_evidence_annotations": 200,
        "search_questions": 100,
    }
    for kind, size in collection_sizes.items():
        for index in range(size):
            source_key = source_keys[index % len(source_keys)]
            key_safety = kind == "claim_evidence_annotations" and index < 20
            domain = "SAFETY" if key_safety else "DIGITAL"
            gold[kind].append(
                _gold_record(
                    index=index,
                    kind=kind,
                    source_key=source_key,
                    domain=domain,
                    key_safety=key_safety,
                    authorization_ref=approval_refs[source_key],
                    gold_release_id=gold_release_id,
                )
            )
    observed_agreement = 19 / 20
    gwet_expected_agreement = 2 * (39 / 40) * (1 / 40)
    gold["agreement_statistics"] = {
        "key_safety_count": 20,
        "raw_agreement": observed_agreement,
        "coefficient_name": "GWET_AC1",
        "coefficient": (
            (observed_agreement - gwet_expected_agreement)
            / (1 - gwet_expected_agreement)
        ),
        "evidence_ref": approval_refs[source_keys[0]],
    }
    gold["manifest_sha256"] = canonical_sha256(gold, excluded_keys={"manifest_sha256"})

    window_id = "01900000-0000-7000-8000-000000000017"
    sources: list[dict[str, Any]] = []
    source_segments: list[dict[str, Any]] = []
    runs: list[dict[str, Any]] = []
    for source_index, source in enumerate(metrics["source_roster"], 1):
        source_key = source["source_key"]
        source_id = _uuid7(700_000 + source_index * 2)
        segment_id = _uuid7(700_000 + source_index * 2 + 1)
        approved_domain = f"{source_key.lower()}.approved.srbg.cn"
        canonical_endpoint = f"https://{approved_domain}/public/list"
        policy_version = "r17-policy-v1"
        connector_version = "r17-connector-v1"
        config_version = "r17-config-v1"
        governance_policy = {
            "allowed_domains": [approved_domain],
            "url_scopes": [f"https://{approved_domain}/public/"],
            "robots_decision": "SIGNED_LEGAL_ASSESSMENT",
            "terms_decision": "SIGNED_LEGAL_ASSESSMENT",
            "copyright_decision": "SIGNED_LEGAL_ASSESSMENT",
            "raw_retention_days": 90,
            "storage_policy": "PRIVATE_RAW",
            "display_policy": "METADATA_FACTS_SHORT_SUMMARY_LINK",
            "max_requests_per_run": 10,
            "robots_evidence_ref": approval_refs[source_key],
            "terms_evidence_ref": approval_refs[source_key],
            "copyright_evidence_ref": approval_refs[source_key],
        }
        policy_ref = _ref(
            root,
            f"artifacts/policies/{source_key}.json",
            json.dumps(governance_policy, ensure_ascii=False, sort_keys=True),
        )
        connector_ref = _ref(
            root,
            f"artifacts/connectors/{source_key}.json",
            json.dumps(
                {
                    "source_key": source_key,
                    "connector_version": connector_version,
                    "adapter": "SourceAdapter",
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
        )
        config_ref = _ref(
            root,
            f"artifacts/config/{source_key}.json",
            json.dumps(
                {
                    "source_key": source_key,
                    "config_version": config_version,
                    "canonical_endpoint": canonical_endpoint,
                    "poll_interval_hours": source["poll_interval_hours"],
                    "discovery_slo_hours": source["discovery_slo_hours"],
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
        )
        policy_sha256 = canonical_sha256(governance_policy)
        first_run_id = f"run-{source_key.lower()}-000"
        chain_base = 100_000 + source_index * 10
        chain_statement = {
            "source_key": source_key,
            "run_id": first_run_id,
            "raw_object_id": _uuid7(chain_base),
            "document_id": _uuid7(chain_base + 1),
            "accepted_claim_ids": [_uuid7(chain_base + 2)],
            "evidence_ids": [_uuid7(chain_base + 3)],
            "event_id": _uuid7(chain_base + 4),
            "publication_revision_id": _uuid7(chain_base + 5),
            "projection_revision_id": _uuid7(chain_base + 6),
            "run_origin": "SCHEDULED",
            "execution_domain": "PRODUCTION",
        }
        chain_ref = _ref(
            root,
            f"artifacts/chains/{source_key}.json",
            json.dumps(chain_statement, ensure_ascii=False, sort_keys=True),
        )
        health_summary = {
            "scheduled_slot_count": 168 // source["poll_interval_hours"],
            "recorded_run_count": 168 // source["poll_interval_hours"],
            "succeeded_count": 1,
            "no_update_count": 168 // source["poll_interval_hours"] - 1,
            "failed_count": 0,
            "false_success_count": 0,
            "recovery_count": 0,
        }
        health_statement = {
            "window_id": window_id,
            "source_key": source_key,
            "source_id": source_id,
            "health_summary": health_summary,
        }
        health_ref = _ref(
            root,
            f"artifacts/health/{source_key}.json",
            json.dumps(health_statement, ensure_ascii=False, sort_keys=True),
        )
        source_payload = {
            "source_key": source_key,
            "source_id": source_id,
            "display_name": f"R17 admitted source {source_key}",
            "canonical_endpoint": canonical_endpoint,
            "access_mode": "PUBLIC_LIST",
            "governance_owner_subject": YINZI,
            "state": "ACTIVE",
            "server_authoritative": True,
            "policy_version": policy_version,
            "policy_sha256": policy_sha256,
            "connector_version": connector_version,
            "connector_sha256": connector_ref["sha256"],
            "config_version": config_version,
            "config_sha256": config_ref["sha256"],
            "poll_interval_hours": source["poll_interval_hours"],
            "discovery_slo_hours": source["discovery_slo_hours"],
            "governance_policy": governance_policy,
            "policy_evidence_ref": policy_ref,
            "connector_evidence_ref": connector_ref,
            "config_evidence_ref": config_ref,
            "approvals": [],
            "health_evidence_ref": health_ref,
            "window_evidence_state": "REAL_CHAIN",
            "chain_evidence": {**chain_statement, "evidence_ref": chain_ref},
            "health_summary": health_summary,
        }
        sources.append(
            source_payload
        )
        source_versions = {
            "source_id": source_id,
            "source_key": source_key,
            "policy_version": policy_version,
            "policy_sha256": policy_sha256,
            "connector_version": connector_version,
            "connector_sha256": connector_ref["sha256"],
            "config_version": config_version,
            "config_sha256": config_ref["sha256"],
        }
        source_segments.append(
            {
                "segment_id": segment_id,
                "source_id": source_id,
                "source_key": source_key,
                "segment_number": 1,
                "status": "COMPLETED",
                "started_at": _timestamp(STARTED_AT),
                "ended_at": _timestamp(ENDED_AT),
                "paused_at": None,
                "pause_reason": None,
                "resumed_by_subject": None,
                "resume_reason": None,
                "source_versions": source_versions,
            }
        )
        slots = 168 // source["poll_interval_hours"]
        for slot in range(slots):
            run_id = f"run-{source_key.lower()}-{slot:03d}"
            raw_payload = json.dumps(
                {
                    "source_key": source_key,
                    "observed_slot": slot,
                    "items": [{"canonical_id": f"{source_key}-item-001"}],
                },
                ensure_ascii=False,
                sort_keys=True,
            )
            raw_ref = _ref(root, f"artifacts/runs/{run_id}.json", raw_payload)
            scheduled_at = STARTED_AT + timedelta(hours=slot * source["poll_interval_hours"])
            run_ended_at = scheduled_at + timedelta(minutes=2)
            response_statement = {
                "run_id": run_id,
                "source_key": source_key,
                "observed_at": _timestamp(run_ended_at),
                "http_status": 200,
                "response_bytes": len(raw_payload.encode("utf-8")),
                "response_sha256": raw_ref["sha256"],
                "response_headers_sha256": _digest(f"headers:{run_id}"),
                "conditional_request_used": slot > 0,
                "observation_method": "PARSED_DISCOVERY_LIST",
                "detector_version": "round17-discovery-detector-v1",
                "detector_sha256": _digest("round17-discovery-detector-v1"),
                "parsed_item_count": 1,
                "new_item_count": 1 if slot == 0 else 0,
            }
            response_ref = _ref(
                root,
                f"artifacts/runs/{run_id}-response-metadata.json",
                json.dumps(response_statement, ensure_ascii=False, sort_keys=True),
            )
            run_payload = {
                    "run_id": run_id,
                    "source_key": source_key,
                    "source_id": source_id,
                    "window_id": window_id,
                    "segment_id": segment_id,
                    "policy_version": policy_version,
                    "policy_sha256": policy_sha256,
                    "connector_version": connector_version,
                    "connector_sha256": connector_ref["sha256"],
                    "config_version": config_version,
                    "config_sha256": config_ref["sha256"],
                    "environment": "PILOT",
                    "origin": "SCHEDULED",
                    "evidence_class": "REAL_RESPONSE",
                    "is_original": True,
                    "included_in_metrics": True,
                    "source_state_at_start": "ACTIVE",
                    "scheduled_slot_at": _timestamp(scheduled_at),
                    "started_at": _timestamp(scheduled_at + timedelta(minutes=1)),
                    "ended_at": _timestamp(run_ended_at),
                    "outcome": "SUCCEEDED" if slot == 0 else "NO_UPDATE",
                    "response_state": "RECEIVED",
                    "request_url": f"https://{approved_domain}/public/list",
                    "final_url": f"https://{approved_domain}/public/list",
                    "request_count": 1,
                    "raw_response_sha256": raw_ref["sha256"],
                    "raw_evidence_ref": raw_ref,
                    "response_metadata": {**response_statement, "evidence_ref": response_ref},
                }
            run_payload["database_record_ref"] = _ref(
                root,
                f"artifacts/runs/{run_id}-database-record.json",
                json.dumps(
                    _run_database_statement(run_payload),
                    ensure_ascii=False,
                    sort_keys=True,
                ),
            )
            runs.append(run_payload)

    admission_entries = [
        {
            "source_key": source["source_key"],
            "source_id": source["source_id"],
            "display_name": source["display_name"],
            "canonical_endpoint": source["canonical_endpoint"],
            "access_mode": source["access_mode"],
            "allowed_domains": source["governance_policy"]["allowed_domains"],
            "url_scopes": source["governance_policy"]["url_scopes"],
            "governance_owner_subject": source["governance_owner_subject"],
            "policy_version": source["policy_version"],
            "policy_sha256": source["policy_sha256"],
            "connector_version": source["connector_version"],
            "connector_sha256": source["connector_sha256"],
            "config_version": source["config_version"],
            "config_sha256": source["config_sha256"],
            "poll_interval_hours": source["poll_interval_hours"],
            "discovery_slo_hours": source["discovery_slo_hours"],
        }
        for source in sources
    ]
    admission_statement = {
        "version": metrics["roster_version"],
        "source_count": 20,
        "entries": admission_entries,
    }
    admission_manifest_sha256 = canonical_sha256(admission_statement)
    admission_ref = _ref(
        root,
        "artifacts/approvals/round17-source-admission-manifest.json",
        json.dumps(
            {**admission_statement, "manifest_sha256": admission_manifest_sha256},
            ensure_ascii=False,
            sort_keys=True,
        ),
    )
    source_admission_manifest = {
        **admission_statement,
        "manifest_sha256": admission_manifest_sha256,
        "evidence_ref": admission_ref,
    }
    for source_index, source in enumerate(sources, 1):
        entry = admission_entries[source_index - 1]
        approvals: list[dict[str, Any]] = []
        for stage_index, stage in enumerate(("COMPLIANCE", "LIVE_TRIAL", "PRODUCTION")):
            signed_at = STARTED_AT - timedelta(days=3 - stage_index)
            approval_statement = {
                **entry,
                "stage": stage,
                "status": "APPROVED",
                "approver_subject": LEO,
                "signed_at": _timestamp(signed_at),
                "mfa_verified_at": _timestamp(signed_at),
                "expires_at": _timestamp(ENDED_AT + timedelta(days=30)),
                "decision_id": _uuid7(710_000 + source_index * 10 + stage_index),
                "admission_manifest_sha256": admission_manifest_sha256,
            }
            audit_record_sha256 = canonical_sha256(approval_statement)
            approval_ref = _ref(
                root,
                f"artifacts/approvals/{source['source_key']}-{stage.lower()}.json",
                json.dumps(
                    {
                        **approval_statement,
                        "audit_record_sha256": audit_record_sha256,
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                ),
            )
            approvals.append(
                {
                    **approval_statement,
                    "audit_record_sha256": audit_record_sha256,
                    "evidence_ref": approval_ref,
                }
            )
        source["approvals"] = approvals

    preflight_statement["roster_sha256"] = admission_manifest_sha256
    preflight_statement.pop("confirmation_sha256", None)
    preflight_statement["confirmation_sha256"] = canonical_sha256(preflight_statement)
    preflight_ref = _ref(
        root,
        "artifacts/approvals/round17-preflight.json",
        json.dumps(preflight_statement, ensure_ascii=False, sort_keys=True),
    )

    event_evaluations = []
    gold_cluster_map = {item["id"]: item for item in gold["event_clusters"]}
    source_slo_hours = {
        item["source_key"]: item["discovery_slo_hours"] for item in metrics["source_roster"]
    }
    for index in range(100):
        source_key = source_keys[index % len(source_keys)]
        gold_event_id = f"event_clusters-{index:04d}"
        enumeration_ref = _ref(
            root,
            f"artifacts/enumeration/{gold_event_id}.json",
            json.dumps(
                {
                    "gold_event_id": gold_event_id,
                    "source_key": source_key,
                    "enumerated_by_subject": BAIXUEJIAO,
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
        )
        trace_base = 200_000 + index * 10
        platform_event_id = _uuid7(trace_base + 4)
        source_run_id = f"run-{source_key.lower()}-000"
        gold_cluster = gold_cluster_map[gold_event_id]
        gold_member_ids = sorted(gold_cluster["member_document_ids"])
        trace_statement = {
            "source_key": source_key,
            "run_id": source_run_id,
            "raw_object_id": _uuid7(trace_base),
            "document_id": gold_member_ids[0],
            "accepted_claim_ids": [_uuid7(trace_base + 2)],
            "evidence_ids": [_uuid7(trace_base + 3)],
            "event_id": platform_event_id,
            "publication_revision_id": _uuid7(trace_base + 5),
            "projection_revision_id": _uuid7(trace_base + 6),
            "run_origin": "SCHEDULED",
            "execution_domain": "PRODUCTION",
        }
        trace_ref = _ref(
            root,
            f"artifacts/events/{gold_event_id}.json",
            json.dumps(trace_statement, ensure_ascii=False, sort_keys=True),
        )
        within_slo = index < 96
        correct_eventization = index < 96
        nonduplicate = index < 99
        searchable_readable = index < 96
        published_at = STARTED_AT + timedelta(minutes=5)
        discovered_at = published_at + timedelta(
            hours=1 if within_slo else source_slo_hours[source_key] + 1
        )
        claim_id = trace_statement["accepted_claim_ids"][0]
        evidence_id = trace_statement["evidence_ids"][0]
        predicate_facts = {
            "published_at": _timestamp(published_at),
            "discovered_at": _timestamp(discovered_at),
            "discovery_slo_hours": source_slo_hours[source_key],
            "gold_cluster_id": gold_event_id,
            "gold_member_document_ids": gold_member_ids,
            "event_document_ids": gold_member_ids if correct_eventization else gold_member_ids[:1],
            "cluster_platform_event_ids": (
                [platform_event_id]
                if nonduplicate
                else [platform_event_id, _uuid7(trace_base + 9)]
            ),
            "accepted_claim_ids": [claim_id],
            "current_evidence_ids": [evidence_id],
            "claim_evidence_links": [
                {"claim_id": claim_id, "evidence_id": evidence_id, "current": True}
            ],
            "projection_revision_id": trace_statement["projection_revision_id"],
            "projection_event_id": platform_event_id,
            "projection_state": "PUBLISHED",
            "search_query_id": _uuid7(600_000 + index),
            "search_result_event_ids": [platform_event_id] if searchable_readable else [],
            "retrieval_status": "READABLE" if searchable_readable else "NOT_FOUND",
        }
        predicate_results = {
            "within_slo": within_slo,
            "correct_eventization": correct_eventization,
            "nonduplicate": nonduplicate,
            "critical_evidence_current": True,
            "searchable_readable": searchable_readable,
        }
        predicate_statement = {
            "gold_event_id": gold_event_id,
            "source_key": source_key,
            "platform_event_id": platform_event_id,
            "predicate_facts": predicate_facts,
            "predicate_results": predicate_results,
        }
        predicate_ref = _ref(
            root,
            f"artifacts/events/{gold_event_id}-predicates.json",
            json.dumps(predicate_statement, ensure_ascii=False, sort_keys=True),
        )
        event_evaluations.append(
            {
                "gold_event_id": gold_event_id,
                "source_key": source_key,
                "enumerated_by_subject": BAIXUEJIAO,
                "high_value": True,
                "platform_event_id": platform_event_id,
                "source_run_id": source_run_id,
                "trace_evidence_ref": trace_ref,
                "predicate_facts": predicate_facts,
                "predicate_results": predicate_results,
                "predicate_evidence_ref": predicate_ref,
                "enumeration_evidence_ref": enumeration_ref,
            }
        )

    event_population = sorted(item["gold_event_id"] for item in event_evaluations)
    run_population = sorted(item["run_id"] for item in runs)
    document_population = sorted(item["id"] for item in gold["documents"])
    key_safety_population = sorted(
        item["id"] for item in gold["claim_evidence_annotations"] if item["key_safety"]
    )
    other_claim_population = sorted(
        item["id"] for item in gold["claim_evidence_annotations"] if not item["key_safety"]
    )
    duplicate_population = sorted(item["id"] for item in gold["duplicate_pairs"])
    cluster_population = sorted(item["id"] for item in gold["event_clusters"])
    rate_populations = {
        "discovery_within_slo": ("EVENT_ENUMERATION", event_population, 96),
        "correct_eventization": ("EVENT_ENUMERATION", event_population, 96),
        "searchable_readable": ("EVENT_ENUMERATION", event_population, 96),
        "tier1_transport_success": (
            "SCHEDULED_RUNS",
            run_population,
            sum(item["outcome"] != "FAILED" for item in runs),
        ),
        "html_parse_success": ("GOLD_DOCUMENTS", document_population, 490),
        "text_pdf_parse_success": ("GOLD_DOCUMENTS", document_population, 485),
        "ocr_usable": ("GOLD_DOCUMENTS", document_population, 460),
        "safety_key_field_accuracy": (
            "GOLD_KEY_SAFETY_CLAIMS",
            key_safety_population,
            len(key_safety_population),
        ),
        "other_field_accuracy": ("GOLD_OTHER_CLAIMS", other_claim_population, 171),
        "exact_dedup_precision": (
            "GOLD_DUPLICATE_PAIRS",
            duplicate_population,
            len(duplicate_population),
        ),
        "fuzzy_candidate_precision": ("GOLD_DUPLICATE_PAIRS", duplicate_population, 294),
        "fuzzy_candidate_recall": ("GOLD_DUPLICATE_PAIRS", duplicate_population, 279),
        "cluster_purity": ("GOLD_EVENT_CLUSTERS", cluster_population, 95),
    }
    rates: dict[str, dict[str, Any]] = {}
    for rate_index, (name, (population_kind, eligible_ids, pass_count)) in enumerate(
        rate_populations.items(), 1
    ):
        passing_ids = eligible_ids[:pass_count]
        statement = {
            "metric_name": name,
            "population_kind": population_kind,
            "eligible_ids": eligible_ids,
            "passing_ids": passing_ids,
            "snapshot_at": _timestamp(ENDED_AT),
            "watermark": f"pg-lsn:0/17{rate_index:02d}",
        }
        rates[name] = {
            "numerator": len(passing_ids),
            "denominator": len(eligible_ids),
            **{key: value for key, value in statement.items() if key != "metric_name"},
            "evidence_ref": _ref(
                root,
                f"artifacts/metrics/rate-{name}.json",
                json.dumps(statement, ensure_ascii=False, sort_keys=True),
            ),
        }

    absolute_row_ids = sorted(
        item["predicate_facts"]["accepted_claim_ids"][0] for item in event_evaluations[:10]
    )
    absolute_specs = {
        "r3_review_bypass_count": ("round17.absolute.r3_review_bypass", [], 0),
        "r4_or_unpublished_leak_count": (
            "round17.absolute.r4_or_unpublished_leak",
            [],
            0,
        ),
        "publication_service_bypass_count": (
            "round17.absolute.publication_service_bypass",
            [],
            0,
        ),
        "published_critical_claim_count": (
            "round17.absolute.published_critical_claims",
            absolute_row_ids,
            10,
        ),
        "published_critical_claim_with_current_evidence_count": (
            "round17.absolute.published_critical_claims_current_evidence",
            absolute_row_ids,
            10,
        ),
        "final_overdue_operator_backlog_count": (
            "round17.absolute.final_overdue_backlog",
            [],
            0,
        ),
        "external_model_api_notification_cost_minor": (
            "round17.absolute.external_cost_minor",
            [],
            0,
        ),
    }
    absolute_gates: dict[str, dict[str, Any]] = {}
    for absolute_index, (name, (query_id, row_ids, count)) in enumerate(
        absolute_specs.items(), 1
    ):
        statement = {
            "query_id": query_id,
            "query_version": "r17-absolute-v1",
            "database_revision": EXPECTED_DATABASE_REVISION,
            "window_id": "01900000-0000-7000-8000-000000000017",
            "snapshot_at": _timestamp(ENDED_AT),
            "watermark": f"pg-lsn:0/18{absolute_index:02d}",
            "row_ids": row_ids,
            "count": count,
        }
        absolute_gates[name] = {
            **statement,
            "evidence_ref": _ref(
                root,
                f"artifacts/metrics/absolute-{name}.json",
                json.dumps(statement, ensure_ascii=False, sort_keys=True),
            ),
        }

    category_minutes = {
        "SOURCE_MAINTENANCE": 30,
        "EXCEPTION_HANDLING": 20,
        "R3_REVIEW": 25,
        "COPYRIGHT_CORRECTION": 10,
    }
    operator_tasks: list[dict[str, Any]] = []
    operator_sessions: list[dict[str, Any]] = []
    operator_corrections: list[dict[str, Any]] = []
    operator_days: list[dict[str, Any]] = []
    for day in range(8):
        day_start = (
            STARTED_AT + timedelta(days=day, hours=1)
            if day < 7
            else ENDED_AT - timedelta(hours=2)
        )
        day_record: dict[str, Any] = {
            "date": (STARTED_AT + timedelta(days=day)).date().isoformat()
        }
        offset_minutes = 0
        for category_index, (category, minutes) in enumerate(category_minutes.items()):
            identity_base = 500_000 + day * 100 + category_index * 3
            session_started = day_start + timedelta(minutes=offset_minutes)
            session_ended = session_started + timedelta(minutes=minutes)
            task_id = _uuid7(identity_base + 1)
            operator_tasks.append(
                {
                    "task_id": task_id,
                    "operator_subject": YINZI,
                    "category": category,
                    "created_at": _timestamp(session_started),
                    "completed_at": _timestamp(session_ended),
                    "status": "COMPLETED",
                }
            )
            operator_sessions.append(
                {
                    "session_id": _uuid7(identity_base),
                    "operator_subject": YINZI,
                    "task_id": task_id,
                    "category": category,
                    "started_at": _timestamp(session_started),
                    "ended_at": _timestamp(session_ended),
                    "active_seconds": minutes * 60,
                }
            )
            category_key = category.lower()
            day_record[f"{category_key}_minutes"] = minutes
            day_record[f"{category_key}_task_count"] = 1
            if category == "COPYRIGHT_CORRECTION":
                operator_corrections.append(
                    {
                        "correction_id": _uuid7(identity_base + 2),
                        "task_id": task_id,
                        "operator_subject": YINZI,
                        "recorded_at": _timestamp(session_ended),
                    }
                )
            offset_minutes += minutes + 1
        operator_days.append(day_record)
    operator_statement = {
        "query_id": "round17.authoritative_operator_work.v1",
        "query_version": "v1",
        "database_revision": EXPECTED_DATABASE_REVISION,
        "window_id": window_id,
        "actor_subject": YINZI,
        "tasks": operator_tasks,
        "sessions": operator_sessions,
        "corrections": operator_corrections,
        "overdue_backlog_task_ids": [],
        "cost_entries": [],
        "snapshot_at": _timestamp(ENDED_AT),
        "watermark": "pg-lsn:0/1900",
    }
    operator_ref = _ref(
        root,
        "artifacts/metrics/operator-work.json",
        json.dumps(operator_statement, ensure_ascii=False, sort_keys=True),
    )
    for day_record in operator_days:
        day_record["evidence_ref"] = operator_ref

    window_export_statement = {
        "id": window_id,
        "state": "COMPLETED",
        "version": 3,
        "started_at": _timestamp(STARTED_AT),
        "ended_at": _timestamp(ENDED_AT),
        "duration_seconds": 604800,
        "immutable": True,
        "started_by_subject": LEO,
        "server_time": _timestamp(ENDED_AT + timedelta(minutes=1)),
        "database_revision": EXPECTED_DATABASE_REVISION,
        "source_admission_manifest_sha256": admission_manifest_sha256,
        "source_segments": source_segments,
        "pause_resume_events": [],
    }
    window_database_ref = _ref(
        root,
        "artifacts/window/round17-window-database-export.json",
        json.dumps(window_export_statement, ensure_ascii=False, sort_keys=True),
    )
    window_payload = {
        **window_export_statement,
        "mfa_verified_at": _timestamp(STARTED_AT),
        "start_evidence_ref": approval_refs[source_keys[0]],
        "database_export_ref": window_database_ref,
    }

    exclusion_statement = {
        "run_id": "drill-run-001",
        "environment": "TEST",
        "origin": "DRILL",
        "included_in_metrics": False,
        "exclusion_reason_code": "NON_PRODUCTION_APPROVED_DRILL",
    }
    exclusion_ref = _ref(
        root,
        "artifacts/drill/drill-run-001-exclusion.json",
        json.dumps(exclusion_statement, ensure_ascii=False, sort_keys=True),
    )
    excluded_runs = [{**exclusion_statement, "evidence_ref": exclusion_ref}]

    drill_approved_at = STARTED_AT + timedelta(hours=1)
    drill_approval_statement = {
        "drill_id": _uuid7(720_000),
        "source_key": sources[0]["source_key"],
        "source_id": sources[0]["source_id"],
        "run_id": "drill-run-001",
        "environment": "TEST",
        "fault_mode": "CONNECTOR_TIMEOUT",
        "approved_by_subject": LEO,
        "approval_decision_id": _uuid7(720_001),
        "approved_at": _timestamp(drill_approved_at),
        "mfa_verified_at": _timestamp(drill_approved_at - timedelta(minutes=1)),
        "real_source_contacted": False,
        "test_endpoint_used": True,
    }
    drill_approval_ref = _ref(
        root,
        "artifacts/drill/round17-failure-drill-approval.json",
        json.dumps(drill_approval_statement, ensure_ascii=False, sort_keys=True),
    )
    drill_result_statement = {
        "drill_id": drill_approval_statement["drill_id"],
        "run_id": "drill-run-001",
        "executed_at": _timestamp(drill_approved_at + timedelta(minutes=1)),
        "completed_at": _timestamp(drill_approved_at + timedelta(minutes=5)),
        "result": "PASSED",
        "alert_observed": True,
        "pause_observed": True,
        "replay_observed": True,
        "real_source_contacted": False,
    }
    drill_result_ref = _ref(
        root,
        "artifacts/drill/round17-failure-drill-result.json",
        json.dumps(drill_result_statement, ensure_ascii=False, sort_keys=True),
    )
    failure_drill = {
        **drill_approval_statement,
        **{
            key: value
            for key, value in drill_result_statement.items()
            if key not in {"drill_id", "run_id", "real_source_contacted"}
        },
        "approval_ref": drill_approval_ref,
        "result_ref": drill_result_ref,
    }

    query_ref = _ref(
        root,
        "artifacts/runs/round17-authoritative-universe.sql",
        round17_eval.EXPECTED_RUN_UNIVERSE_QUERY,
    )
    run_universe_statement = {
        "window_id": window_id,
        "export_environment": "PILOT",
        "exported_at": _timestamp(ENDED_AT + timedelta(minutes=2)),
        "exporter_subject": YINZI,
        "database_identity": {
            "system": "POSTGRESQL",
            "cluster_id": _uuid7(720_002),
            "database_name_sha256": _digest("srbg-preproduction"),
            "database_role_sha256": _digest("srbg_api"),
            "revision": EXPECTED_DATABASE_REVISION,
        },
        "transaction_watermark": {"snapshot": "1000:1001:", "transaction_id": 1000},
        "query_id": "round17.authoritative_run_universe.v1",
        "query_sha256": query_ref["sha256"],
        "query_ref": query_ref,
        "filters": {
            "window_bound_segment_required": True,
            "run_origin": "SCHEDULED",
            "execution_domain": "PRODUCTION",
        },
        "included_run_count": len(runs),
        "included_run_ids": sorted(run["run_id"] for run in runs),
        "excluded_run_count": len(excluded_runs),
        "excluded_run_ids": sorted(run["run_id"] for run in excluded_runs),
    }
    run_universe_ref = _ref(
        root,
        "artifacts/runs/round17-authoritative-universe-export.json",
        json.dumps(run_universe_statement, ensure_ascii=False, sort_keys=True),
    )
    run_universe = {**run_universe_statement, "evidence_ref": run_universe_ref}

    evidence: dict[str, Any] = {
        "schema_version": "1.3.0",
        "round": 17,
        "evidence_kind": "REAL_PILOT",
        "environment": "PILOT",
        "roster_version": "r17-sources-v0.1",
        "metrics_definition": {
            "version": metrics["version"],
            **metrics_ref,
        },
        "baseline": {
            "commit": "b08513965e931f363283384037fc1c1f068a1b1c",
            "config_version": "r17-sources-v0.1",
            "database_revision": EXPECTED_DATABASE_REVISION,
            "recorded_at": _timestamp(STARTED_AT - timedelta(days=4)),
        },
        "actors": actors,
        "preflight_authorization": {
            **preflight_statement,
            "evidence_ref": preflight_ref,
        },
        "source_admission_manifest": source_admission_manifest,
        "window": window_payload,
        "sources": sources,
        "runs": runs,
        "run_universe": run_universe,
        "excluded_runs": excluded_runs,
        "failure_drill": failure_drill,
        "event_evaluations": event_evaluations,
        "metrics": {
            "window_id": "01900000-0000-7000-8000-000000000017",
            "input_run_ids": [run["run_id"] for run in runs],
            "rates": rates,
            "absolute_gates": absolute_gates,
            "operator_work_export": {**operator_statement, "evidence_ref": operator_ref},
            "operator_days": operator_days,
        },
        "gold_manifest": {
            "version": gold["version"],
            "sha256": gold["manifest_sha256"],
        },
    }
    _sign_evidence(evidence, signing)
    return root, evidence, gold, metrics, signing


def _evaluate(
    valid_bundle: tuple[
        Path,
        dict[str, Any],
        dict[str, Any],
        dict[str, Any],
        dict[str, Any],
    ],
    mutate: Any | None = None,
) -> dict[str, Any]:
    root, original_evidence, original_gold, metrics, signing = valid_bundle
    evidence = copy.deepcopy(original_evidence)
    gold = copy.deepcopy(original_gold)
    if mutate is not None:
        mutate(evidence, gold)
    gold["manifest_sha256"] = canonical_sha256(gold, excluded_keys={"manifest_sha256"})
    evidence["gold_manifest"]["sha256"] = gold["manifest_sha256"]
    _sign_evidence(evidence, signing)
    return evaluate_round17_payloads(
        evidence=evidence,
        gold=gold,
        metrics_definition=metrics,
        trusted_public_key_pem=signing["public_key_pem"],
        expected_key_fingerprint_sha256=signing["fingerprint"],
        root=root,
    )


def test_complete_synthetic_contract_bundle_passes_with_wilson_diagnostics(
    valid_bundle: Any,
) -> None:
    result = _evaluate(valid_bundle)

    assert result["decision"] == "PASSED", result["issues"]
    assert result["checks"]["source_governance"]["passed"] is True
    assert result["checks"]["run_provenance"]["details"]["included_run_count"] == 406
    assert result["metrics"]["north_star"]["point_estimate"] == pytest.approx(0.96)
    assert result["metrics"]["north_star"]["wilson_95"][0] < 0.96


def test_external_ed25519_trust_anchor_is_mandatory(valid_bundle: Any) -> None:
    root, evidence, gold, metrics, _signing = valid_bundle

    result = evaluate_round17_payloads(
        evidence=copy.deepcopy(evidence),
        gold=copy.deepcopy(gold),
        metrics_definition=metrics,
        root=root,
    )

    assert result["decision"] == "BLOCKED"
    assert "TRUST_ANCHOR_MISSING" in {issue["code"] for issue in result["issues"]}


def test_evidence_detached_signature_is_mandatory(valid_bundle: Any) -> None:
    root, original_evidence, gold, metrics, signing = valid_bundle
    evidence = copy.deepcopy(original_evidence)
    evidence.pop(TRUST_SIGNATURE_FIELD)

    result = evaluate_round17_payloads(
        evidence=evidence,
        gold=copy.deepcopy(gold),
        metrics_definition=metrics,
        trusted_public_key_pem=signing["public_key_pem"],
        expected_key_fingerprint_sha256=signing["fingerprint"],
        root=root,
    )

    assert result["decision"] == "BLOCKED"
    codes = {issue["code"] for issue in result["issues"]}
    assert "EVIDENCE_SCHEMA_INVALID" in codes
    assert "EVIDENCE_SIGNATURE_MISSING" in codes


@pytest.mark.parametrize(
    ("mutation", "anchor_fingerprint", "issue_code"),
    [
        (
            lambda evidence: evidence[TRUST_SIGNATURE_FIELD].__setitem__(
                "key_fingerprint_sha256", "0" * 64
            ),
            None,
            "EVIDENCE_SIGNING_KEY_MISMATCH",
        ),
        (
            lambda _evidence: None,
            "0" * 64,
            "TRUST_ANCHOR_FINGERPRINT_MISMATCH",
        ),
        (
            lambda evidence: evidence[TRUST_SIGNATURE_FIELD].__setitem__(
                "signature_base64",
                base64.b64encode(b"\x00" * 64).decode("ascii"),
            ),
            None,
            "EVIDENCE_SIGNATURE_INVALID",
        ),
        (
            lambda evidence: evidence["metrics"]["rates"]["fuzzy_candidate_recall"].__setitem__(
                "numerator", 92
            ),
            None,
            "EVIDENCE_SIGNATURE_INVALID",
        ),
    ],
)
def test_untrusted_fingerprint_or_bad_signature_is_blocked(
    valid_bundle: Any,
    mutation: Any,
    anchor_fingerprint: str | None,
    issue_code: str,
) -> None:
    root, original_evidence, gold, metrics, signing = valid_bundle
    evidence = copy.deepcopy(original_evidence)
    mutation(evidence)

    result = evaluate_round17_payloads(
        evidence=evidence,
        gold=copy.deepcopy(gold),
        metrics_definition=metrics,
        trusted_public_key_pem=signing["public_key_pem"],
        expected_key_fingerprint_sha256=anchor_fingerprint or signing["fingerprint"],
        root=root,
    )

    assert result["decision"] == "BLOCKED"
    assert issue_code in {issue["code"] for issue in result["issues"]}


def test_file_evaluator_uses_dynamic_external_public_key(valid_bundle: Any) -> None:
    root, evidence, gold, _metrics, signing = valid_bundle
    evidence_path = root / "round17-evidence.json"
    gold_path = root / "round17-gold.json"
    evidence_path.write_text(json.dumps(evidence), encoding="utf-8")
    gold_path.write_text(json.dumps(gold), encoding="utf-8")

    without_anchor = evaluate_round17_files(
        evidence_path=evidence_path,
        gold_path=gold_path,
        root=root,
    )
    result = evaluate_round17_files(
        evidence_path=evidence_path,
        gold_path=gold_path,
        trusted_public_key_path=signing["public_key_path"],
        expected_key_fingerprint_sha256=signing["fingerprint"],
        root=root,
    )

    assert without_anchor["decision"] == "BLOCKED"
    assert "TRUST_ANCHOR_MISSING" in {issue["code"] for issue in without_anchor["issues"]}
    assert result["decision"] == "PASSED"


def test_invalid_external_public_key_file_is_blocked(valid_bundle: Any) -> None:
    root, evidence, gold, _metrics, signing = valid_bundle
    evidence_path = root / "invalid-anchor-evidence.json"
    gold_path = root / "invalid-anchor-gold.json"
    invalid_key_path = root / "trust/not-a-public-key.pem"
    evidence_path.write_text(json.dumps(evidence), encoding="utf-8")
    gold_path.write_text(json.dumps(gold), encoding="utf-8")
    invalid_key_path.write_text("not a public key", encoding="utf-8")

    result = evaluate_round17_files(
        evidence_path=evidence_path,
        gold_path=gold_path,
        trusted_public_key_path=invalid_key_path,
        expected_key_fingerprint_sha256=signing["fingerprint"],
        root=root,
    )

    assert result["decision"] == "BLOCKED"
    assert "TRUST_ANCHOR_INVALID" in {issue["code"] for issue in result["issues"]}


def test_cli_reads_external_trust_anchor_from_environment(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    key_path = tmp_path / "trusted.pem"
    captured: dict[str, Any] = {}

    def fake_evaluate_round17_files(**kwargs: Any) -> dict[str, Any]:
        captured.update(kwargs)
        return {"round": 17, "decision": "PASSED", "checks": {}, "metrics": {}, "issues": []}

    monkeypatch.setattr(round17_eval, "evaluate_round17_files", fake_evaluate_round17_files)
    monkeypatch.setenv("ROUND17_TRUSTED_PUBLIC_KEY", str(key_path))
    monkeypatch.setenv("ROUND17_TRUSTED_PUBLIC_KEY_SHA256", "a" * 64)
    monkeypatch.setattr(sys, "argv", ["round17_eval.py"])

    exit_code = main()
    capsys.readouterr()

    assert exit_code == 0
    assert captured["trusted_public_key_path"] == key_path
    assert captured["expected_key_fingerprint_sha256"] == "a" * 64


def test_cli_with_evidence_but_without_external_anchor_is_blocked(
    valid_bundle: Any,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root, evidence, gold, _metrics, _signing = valid_bundle
    evidence_path = root / "cli-no-anchor-evidence.json"
    gold_path = root / "cli-no-anchor-gold.json"
    evidence_path.write_text(json.dumps(evidence), encoding="utf-8")
    gold_path.write_text(json.dumps(gold), encoding="utf-8")
    monkeypatch.delenv("ROUND17_TRUSTED_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("ROUND17_TRUSTED_PUBLIC_KEY_SHA256", raising=False)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "round17_eval.py",
            "--evidence",
            str(evidence_path),
            "--gold-manifest",
            str(gold_path),
        ],
    )

    exit_code = main()
    output = json.loads(capsys.readouterr().out)

    assert exit_code == 1
    assert output["decision"] == "BLOCKED"
    assert "TRUST_ANCHOR_MISSING" in {issue["code"] for issue in output["issues"]}


def test_candidate_definition_is_not_self_described_as_approved(valid_bundle: Any) -> None:
    _root, _evidence, _gold, metrics, _signing = valid_bundle

    assert metrics["authority_state"] == "CANDIDATE_REQUIRES_EXPLICIT_LEO_CONFIRMATION"


def test_missing_real_preflight_authorization_is_blocked(valid_bundle: Any) -> None:
    result = _evaluate(
        valid_bundle,
        lambda evidence, _gold: evidence.pop("preflight_authorization"),
    )

    assert result["decision"] == "BLOCKED"
    codes = {issue["code"] for issue in result["issues"]}
    assert "EVIDENCE_SCHEMA_INVALID" in codes
    assert "PREFLIGHT_AUTHORIZATION_MISSING" in codes


@pytest.mark.parametrize(
    ("field", "value", "issue_code"),
    [
        ("approver_subject", YINZI, "PREFLIGHT_NOT_LEO"),
        ("roster_version", "r17-unconfirmed", "PREFLIGHT_ROSTER_NOT_CONFIRMED"),
        ("roster_sha256", "0" * 64, "PREFLIGHT_ROSTER_NOT_CONFIRMED"),
        (
            "metrics_definition_version",
            "phase2-round17-metrics-unconfirmed",
            "PREFLIGHT_METRICS_NOT_CONFIRMED",
        ),
        ("metrics_definition_sha256", "0" * 64, "PREFLIGHT_METRICS_NOT_CONFIRMED"),
        ("window_seconds", 604799, "PREFLIGHT_WINDOW_NOT_CONFIRMED"),
        (
            "confirmed_at",
            _timestamp(STARTED_AT + timedelta(seconds=1)),
            "PREFLIGHT_CONFIRMATION_AFTER_T0",
        ),
        (
            "mfa_verified_at",
            _timestamp(STARTED_AT - timedelta(hours=2)),
            "PREFLIGHT_CONFIRMATION_MFA_STALE",
        ),
        (
            "mfa_verified_at",
            _timestamp(STARTED_AT + timedelta(seconds=1)),
            "PREFLIGHT_MFA_AFTER_T0",
        ),
        (
            "mfa_verified_at",
            _timestamp(STARTED_AT - timedelta(minutes=59)),
            "PREFLIGHT_CONFIRMATION_MFA_ORDER_INVALID",
        ),
        ("confirmation_sha256", "0" * 64, "PREFLIGHT_CONFIRMATION_HASH_MISMATCH"),
    ],
)
def test_preflight_confirmation_must_bind_leo_versions_window_mfa_and_hash(
    valid_bundle: Any,
    field: str,
    value: Any,
    issue_code: str,
) -> None:
    result = _evaluate(
        valid_bundle,
        lambda evidence, _gold: evidence["preflight_authorization"].__setitem__(field, value),
    )

    assert result["decision"] == "BLOCKED"
    assert issue_code in {issue["code"] for issue in result["issues"]}


def test_preflight_reference_must_contain_the_explicit_confirmation(valid_bundle: Any) -> None:
    def mutate(evidence: dict[str, Any], _gold: dict[str, Any]) -> None:
        evidence["preflight_authorization"]["evidence_ref"] = evidence["sources"][0][
            "health_evidence_ref"
        ]

    result = _evaluate(valid_bundle, mutate)

    assert result["decision"] == "BLOCKED"
    assert "PREFLIGHT_CONFIRMATION_REFERENCE_MISMATCH" in {
        issue["code"] for issue in result["issues"]
    }


@pytest.mark.parametrize(
    ("name", "mutate", "issue_code"),
    [
        (
            "nineteen sources",
            lambda evidence, _gold: evidence["sources"].pop(),
            "EVIDENCE_SCHEMA_INVALID",
        ),
        (
            "expired approval",
            lambda evidence, _gold: evidence["sources"][0]["approvals"][0].__setitem__(
                "expires_at", _timestamp(STARTED_AT + timedelta(hours=1))
            ),
            "APPROVAL_NOT_WINDOW_VALID",
        ),
        (
            "local oidc actor",
            lambda evidence, gold: (
                evidence["actors"]["LEO"].__setitem__("is_local", True),
                gold["actors"]["LEO"].__setitem__("is_local", True),
            ),
            "GOLD_SCHEMA_INVALID",
        ),
        (
            "short window",
            lambda evidence, _gold: evidence["window"].__setitem__(
                "ended_at", _timestamp(ENDED_AT - timedelta(seconds=1))
            ),
            "WINDOW_NOT_EXACT_168_HOURS",
        ),
        (
            "replay contamination",
            lambda evidence, _gold: evidence["runs"][0].__setitem__("origin", "REPLAY"),
            "EVIDENCE_SCHEMA_INVALID",
        ),
        (
            "publication bypass",
            lambda evidence, _gold: (
                evidence["metrics"]["absolute_gates"][
                    "publication_service_bypass_count"
                ].__setitem__("count", 1),
                evidence["metrics"]["absolute_gates"][
                    "publication_service_bypass_count"
                ].__setitem__("row_ids", [_uuid7(999_001)]),
            ),
            "ABSOLUTE_GATE_FAILED",
        ),
        (
            "missing legal policy",
            lambda evidence, _gold: evidence["sources"][0].pop("governance_policy"),
            "EVIDENCE_SCHEMA_INVALID",
        ),
        (
            "run escaped allowed domain",
            lambda evidence, _gold: evidence["runs"][0].__setitem__(
                "final_url", "https://unapproved.invalid/public/list"
            ),
            "RUN_DOMAIN_NOT_ALLOWED",
        ),
        (
            "health summary lies",
            lambda evidence, _gold: evidence["sources"][0]["health_summary"].__setitem__(
                "no_update_count", 0
            ),
            "SOURCE_HEALTH_SUMMARY_MISMATCH",
        ),
        (
            "inline response body",
            lambda evidence, _gold: evidence["runs"][0].__setitem__("body", "sensitive"),
            "EVIDENCE_SCHEMA_INVALID",
        ),
        (
            "inline gold body",
            lambda _evidence, gold: gold["documents"][0].__setitem__("body", "sensitive"),
            "GOLD_SCHEMA_INVALID",
        ),
    ],
)
def test_strict_evidence_failures_are_blocked(
    valid_bundle: Any,
    name: str,
    mutate: Any,
    issue_code: str,
) -> None:
    result = _evaluate(valid_bundle, mutate)

    assert result["decision"] == "BLOCKED", name
    assert issue_code in {issue["code"] for issue in result["issues"]}


def test_gold_requires_minimum_counts_blind_double_labels_and_arbitration(
    valid_bundle: Any,
) -> None:
    def mutate(_evidence: dict[str, Any], gold: dict[str, Any]) -> None:
        gold["documents"].pop()
        critical = gold["claim_evidence_annotations"][0]
        critical["annotation"]["secondary"] = None
        disputed = gold["claim_evidence_annotations"][1]
        disputed["annotation"]["secondary"]["label_code"] = "UNSUPPORTED"
        disputed["annotation"]["secondary"]["label_sha256"] = _digest(
            "forced-disagreement"
        )
        disputed["annotation"]["arbitration"] = None

    result = _evaluate(valid_bundle, mutate)

    assert result["decision"] == "BLOCKED"
    codes = {issue["code"] for issue in result["issues"]}
    assert "GOLD_MINIMUM_NOT_MET" in codes
    assert "KEY_SAFETY_DOUBLE_LABEL_MISSING" in codes
    assert "GOLD_ARBITRATION_MISSING" in codes


def test_digital_gold_requires_twenty_percent_blind_secondary_review(valid_bundle: Any) -> None:
    def mutate(_evidence: dict[str, Any], gold: dict[str, Any]) -> None:
        for collection_name in (
            "documents",
            "duplicate_pairs",
            "event_clusters",
            "claim_evidence_annotations",
            "search_questions",
        ):
            for record in gold[collection_name]:
                if record["domain"] == "DIGITAL":
                    record["annotation"]["secondary"] = None

    result = _evaluate(valid_bundle, mutate)

    assert result["decision"] == "BLOCKED"
    assert "DIGITAL_SECONDARY_REVIEW_INSUFFICIENT" in {issue["code"] for issue in result["issues"]}


def test_north_star_denominator_must_equal_the_frozen_high_value_event_set(
    valid_bundle: Any,
) -> None:
    def mutate(evidence: dict[str, Any], _gold: dict[str, Any]) -> None:
        evidence["event_evaluations"][0]["gold_event_id"] = "rogue-window-event"

    result = _evaluate(valid_bundle, mutate)

    assert result["decision"] == "BLOCKED"
    assert "GOLD_EVENT_SET_MISMATCH" in {issue["code"] for issue in result["issues"]}


def test_gold_requires_collection_specific_identity_and_event_members(
    valid_bundle: Any,
) -> None:
    def mutate(_evidence: dict[str, Any], gold: dict[str, Any]) -> None:
        gold["event_clusters"][0]["member_document_ids"] = []

    result = _evaluate(valid_bundle, mutate)

    assert result["decision"] == "BLOCKED"
    assert "GOLD_COLLECTION_RECORD_INVALID" in {
        issue["code"] for issue in result["issues"]
    }


def test_gold_release_must_bind_database_release_hash_and_audit_export(
    valid_bundle: Any,
) -> None:
    def mutate(_evidence: dict[str, Any], gold: dict[str, Any]) -> None:
        gold["db_manifest_sha256"] = _digest("unrelated-db-release")

    result = _evaluate(valid_bundle, mutate)

    assert result["decision"] == "BLOCKED"
    assert "GOLD_RELEASE_AUDIT_MISMATCH" in {
        issue["code"] for issue in result["issues"]
    }


def test_gold_rejects_empty_label_hashes(valid_bundle: Any) -> None:
    def mutate(_evidence: dict[str, Any], gold: dict[str, Any]) -> None:
        gold["documents"][0]["annotation"]["primary"]["label_sha256"] = ""

    result = _evaluate(valid_bundle, mutate)

    assert result["decision"] == "BLOCKED"
    assert "GOLD_SCHEMA_INVALID" in {issue["code"] for issue in result["issues"]}


def test_gold_requires_at_least_twenty_critical_safety_samples(valid_bundle: Any) -> None:
    def mutate(_evidence: dict[str, Any], gold: dict[str, Any]) -> None:
        gold["claim_evidence_annotations"][0]["key_safety"] = False
        gold["agreement_statistics"]["key_safety_count"] = 19
        gold["agreement_statistics"]["raw_agreement"] = 1.0

    result = _evaluate(valid_bundle, mutate)

    assert result["decision"] == "BLOCKED"
    assert "KEY_SAFETY_SAMPLE_INSUFFICIENT" in {
        issue["code"] for issue in result["issues"]
    }


def test_digital_secondary_review_cannot_be_evaded_with_zero_digital_samples(
    valid_bundle: Any,
) -> None:
    def mutate(_evidence: dict[str, Any], gold: dict[str, Any]) -> None:
        for collection_name in (
            "documents",
            "duplicate_pairs",
            "event_clusters",
            "claim_evidence_annotations",
            "search_questions",
        ):
            for record in gold[collection_name]:
                record["domain"] = "SAFETY"

    result = _evaluate(valid_bundle, mutate)

    assert result["decision"] == "BLOCKED"
    assert "DIGITAL_SAMPLE_MISSING" in {issue["code"] for issue in result["issues"]}


def test_agreement_coefficient_is_recomputed_from_annotations(valid_bundle: Any) -> None:
    def mutate(_evidence: dict[str, Any], gold: dict[str, Any]) -> None:
        gold["agreement_statistics"]["coefficient"] = 0.81

    result = _evaluate(valid_bundle, mutate)

    assert result["decision"] == "BLOCKED"
    assert "GOLD_AGREEMENT_GATE_FAILED" in {
        issue["code"] for issue in result["issues"]
    }


def test_agreement_changes_when_a_blinded_annotation_changes(valid_bundle: Any) -> None:
    def mutate(_evidence: dict[str, Any], gold: dict[str, Any]) -> None:
        record = gold["claim_evidence_annotations"][1]
        secondary = record["annotation"]["secondary"]
        secondary["label_code"] = "UNSUPPORTED"
        secondary["label_sha256"] = _digest("gold-label:UNSUPPORTED")
        record["annotation"]["arbitration"] = {
            "arbitrator_subject": LEO,
            "resolved_label_code": "SUPPORTED",
            "resolved_label_sha256": _digest("gold-label:SUPPORTED"),
            "arbitrated_at": _timestamp(STARTED_AT - timedelta(days=1)),
        }

    result = _evaluate(valid_bundle, mutate)

    assert result["decision"] == "BLOCKED"
    assert "GOLD_AGREEMENT_GATE_FAILED" in {
        issue["code"] for issue in result["issues"]
    }


def test_hash_tampering_and_below_threshold_metric_are_blocked(valid_bundle: Any) -> None:
    root, original_evidence, original_gold, metrics, signing = valid_bundle
    evidence = copy.deepcopy(original_evidence)
    gold = copy.deepcopy(original_gold)
    recall_rate = evidence["metrics"]["rates"]["fuzzy_candidate_recall"]
    recall_rate["passing_ids"] = recall_rate["passing_ids"][:278]
    recall_rate["numerator"] = 278
    evidence["manifest_sha256"] = "0" * 64
    _sign_evidence(evidence, signing, recompute_manifest=False)

    result = evaluate_round17_payloads(
        evidence=evidence,
        gold=gold,
        metrics_definition=metrics,
        trusted_public_key_pem=signing["public_key_pem"],
        expected_key_fingerprint_sha256=signing["fingerprint"],
        root=root,
    )

    assert result["decision"] == "BLOCKED"
    codes = {issue["code"] for issue in result["issues"]}
    assert "EVIDENCE_MANIFEST_HASH_MISMATCH" in codes
    assert "PROPORTION_GATE_FAILED" in codes


def test_metrics_cannot_include_excluded_or_unknown_runs(valid_bundle: Any) -> None:
    def mutate(evidence: dict[str, Any], _gold: dict[str, Any]) -> None:
        evidence["metrics"]["input_run_ids"].append("drill-run-001")

    result = _evaluate(valid_bundle, mutate)

    assert result["decision"] == "BLOCKED"
    assert "METRIC_INPUT_CONTAMINATION" in {issue["code"] for issue in result["issues"]}


def test_operator_daily_records_must_fall_inside_the_immutable_window(
    valid_bundle: Any,
) -> None:
    def mutate(evidence: dict[str, Any], _gold: dict[str, Any]) -> None:
        evidence["metrics"]["operator_days"][0]["date"] = "2025-01-01"

    result = _evaluate(valid_bundle, mutate)

    assert result["decision"] == "BLOCKED"
    assert "OPERATOR_RECORD_OUTSIDE_WINDOW" in {
        issue["code"] for issue in result["issues"]
    }


def test_rate_denominator_cannot_be_reduced_to_one_without_eligible_ids(
    valid_bundle: Any,
) -> None:
    def mutate(evidence: dict[str, Any], _gold: dict[str, Any]) -> None:
        rate = evidence["metrics"]["rates"]["html_parse_success"]
        rate["numerator"] = 1
        rate["denominator"] = 1

    result = _evaluate(valid_bundle, mutate)

    assert result["decision"] == "BLOCKED"
    assert "RATE_POPULATION_MISMATCH" in {issue["code"] for issue in result["issues"]}


def test_rate_counts_must_be_recomputed_from_enumerated_ids(valid_bundle: Any) -> None:
    def mutate(evidence: dict[str, Any], _gold: dict[str, Any]) -> None:
        rate = evidence["metrics"]["rates"]["fuzzy_candidate_precision"]
        rate["numerator"] -= 1

    result = _evaluate(valid_bundle, mutate)

    assert result["decision"] == "BLOCKED"
    assert "RATE_COUNTS_NOT_REPRODUCIBLE" in {
        issue["code"] for issue in result["issues"]
    }


def test_north_star_predicates_reject_naked_boolean_fields(valid_bundle: Any) -> None:
    def mutate(evidence: dict[str, Any], _gold: dict[str, Any]) -> None:
        evidence["event_evaluations"][0]["within_slo"] = True

    result = _evaluate(valid_bundle, mutate)

    assert result["decision"] == "BLOCKED"
    assert "EVIDENCE_SCHEMA_INVALID" in {issue["code"] for issue in result["issues"]}


@pytest.mark.parametrize(
    "mutate_facts",
    [
        lambda facts: facts.__setitem__(
            "discovered_at", _timestamp(STARTED_AT + timedelta(hours=48))
        ),
        lambda facts: facts.__setitem__(
            "event_document_ids", facts["event_document_ids"][:1]
        ),
        lambda facts: facts["cluster_platform_event_ids"].append(_uuid7(990_100)),
        lambda facts: facts.__setitem__("current_evidence_ids", [_uuid7(990_101)]),
        lambda facts: facts.__setitem__("search_result_event_ids", []),
    ],
)
def test_five_north_star_predicates_are_recomputed_from_authoritative_facts(
    valid_bundle: Any,
    mutate_facts: Any,
) -> None:
    def mutate(evidence: dict[str, Any], _gold: dict[str, Any]) -> None:
        mutate_facts(evidence["event_evaluations"][0]["predicate_facts"])

    result = _evaluate(valid_bundle, mutate)

    assert result["decision"] == "BLOCKED"
    assert "EVENT_PREDICATE_NOT_REPRODUCIBLE" in {
        issue["code"] for issue in result["issues"]
    }


def test_event_evaluation_source_must_match_its_frozen_gold_cluster(valid_bundle: Any) -> None:
    def mutate(evidence: dict[str, Any], _gold: dict[str, Any]) -> None:
        evidence["event_evaluations"][0]["source_key"] = evidence["sources"][1]["source_key"]

    result = _evaluate(valid_bundle, mutate)

    assert result["decision"] == "BLOCKED"
    assert "EVENT_GOLD_SOURCE_MISMATCH" in {issue["code"] for issue in result["issues"]}


def test_honestly_missed_gold_event_remains_in_the_north_star_denominator(
    valid_bundle: Any,
) -> None:
    root = valid_bundle[0]

    def mutate(evidence: dict[str, Any], _gold: dict[str, Any]) -> None:
        event = evidence["event_evaluations"][96]
        event["platform_event_id"] = None
        event["source_run_id"] = None
        event["trace_evidence_ref"] = None
        facts = event["predicate_facts"]
        facts.update(
            {
                "discovered_at": None,
                "event_document_ids": [],
                "cluster_platform_event_ids": [],
                "accepted_claim_ids": [],
                "current_evidence_ids": [],
                "claim_evidence_links": [],
                "projection_revision_id": None,
                "projection_event_id": None,
                "projection_state": "MISSING",
                "search_result_event_ids": [],
                "retrieval_status": "NOT_FOUND",
            }
        )
        event["predicate_results"] = {
            "within_slo": False,
            "correct_eventization": False,
            "nonduplicate": False,
            "critical_evidence_current": False,
            "searchable_readable": False,
        }
        statement = {
            "gold_event_id": event["gold_event_id"],
            "source_key": event["source_key"],
            "platform_event_id": None,
            "predicate_facts": facts,
            "predicate_results": event["predicate_results"],
        }
        event["predicate_evidence_ref"] = _ref(
            root,
            "artifacts/events/honestly-missed-predicates.json",
            json.dumps(statement, ensure_ascii=False, sort_keys=True),
        )

    result = _evaluate(valid_bundle, mutate)

    assert result["decision"] == "PASSED", result["issues"]
    assert result["metrics"]["north_star"]["denominator"] == 100


def test_absolute_query_export_is_required_for_every_gate(valid_bundle: Any) -> None:
    def mutate(evidence: dict[str, Any], _gold: dict[str, Any]) -> None:
        evidence["metrics"]["absolute_gates"]["r3_review_bypass_count"] = 0

    result = _evaluate(valid_bundle, mutate)

    assert result["decision"] == "BLOCKED"
    assert "EVIDENCE_SCHEMA_INVALID" in {issue["code"] for issue in result["issues"]}


def test_absolute_query_count_must_equal_enumerated_row_ids(valid_bundle: Any) -> None:
    def mutate(evidence: dict[str, Any], _gold: dict[str, Any]) -> None:
        evidence["metrics"]["absolute_gates"]["r3_review_bypass_count"][
            "row_ids"
        ] = [_uuid7(990_001)]

    result = _evaluate(valid_bundle, mutate)

    assert result["decision"] == "BLOCKED"
    assert "ABSOLUTE_QUERY_EXPORT_INVALID" in {
        issue["code"] for issue in result["issues"]
    }


def test_published_critical_evidence_gate_cannot_pass_as_zero_over_zero(
    valid_bundle: Any,
) -> None:
    def mutate(evidence: dict[str, Any], _gold: dict[str, Any]) -> None:
        for name in (
            "published_critical_claim_count",
            "published_critical_claim_with_current_evidence_count",
        ):
            record = evidence["metrics"]["absolute_gates"][name]
            record["count"] = 0
            record["row_ids"] = []

    result = _evaluate(valid_bundle, mutate)

    assert result["decision"] == "BLOCKED"
    assert "PUBLISHED_CRITICAL_CLAIMS_EMPTY" in {
        issue["code"] for issue in result["issues"]
    }


def test_operator_all_zero_summaries_cannot_prove_operability(valid_bundle: Any) -> None:
    def mutate(evidence: dict[str, Any], _gold: dict[str, Any]) -> None:
        work = evidence["metrics"]["operator_work_export"]
        work["tasks"] = []
        work["sessions"] = []
        work["corrections"] = []
        for day in evidence["metrics"]["operator_days"]:
            for field in (
                "source_maintenance_minutes",
                "exception_handling_minutes",
                "r3_review_minutes",
                "copyright_correction_minutes",
            ):
                day[field] = 0
            for field in (
                "source_maintenance_task_count",
                "exception_handling_task_count",
                "r3_review_task_count",
                "copyright_correction_task_count",
            ):
                day[field] = 0

    result = _evaluate(valid_bundle, mutate)

    assert result["decision"] == "BLOCKED"
    assert "EVIDENCE_SCHEMA_INVALID" in {issue["code"] for issue in result["issues"]}


def test_zero_copyright_corrections_are_honest_when_no_correction_tasks_exist(
    valid_bundle: Any,
) -> None:
    root = valid_bundle[0]

    def mutate(evidence: dict[str, Any], _gold: dict[str, Any]) -> None:
        work = evidence["metrics"]["operator_work_export"]
        work["tasks"] = [
            task for task in work["tasks"] if task["category"] != "COPYRIGHT_CORRECTION"
        ]
        work["sessions"] = [
            session
            for session in work["sessions"]
            if session["category"] != "COPYRIGHT_CORRECTION"
        ]
        work["corrections"] = []
        for day in evidence["metrics"]["operator_days"]:
            day["copyright_correction_minutes"] = 0
            day["copyright_correction_task_count"] = 0
        statement = {key: value for key, value in work.items() if key != "evidence_ref"}
        work_ref = _ref(
            root,
            "artifacts/metrics/operator-work-zero-corrections.json",
            json.dumps(statement, ensure_ascii=False, sort_keys=True),
        )
        work["evidence_ref"] = work_ref
        for day in evidence["metrics"]["operator_days"]:
            day["evidence_ref"] = work_ref

    result = _evaluate(valid_bundle, mutate)

    assert result["decision"] == "PASSED", result["issues"]


def test_shanghai_midnight_window_uses_seven_half_open_calendar_dates() -> None:
    midnight_shanghai = datetime(2026, 7, 1, 16, 0, tzinfo=UTC)

    dates = round17_eval._shanghai_window_dates(
        midnight_shanghai,
        midnight_shanghai + timedelta(hours=168),
    )

    assert dates == {f"2026-07-{day:02d}" for day in range(2, 9)}


def test_operator_export_is_yinzi_only_and_task_counts_are_recomputed(valid_bundle: Any) -> None:
    def mutate(evidence: dict[str, Any], _gold: dict[str, Any]) -> None:
        evidence["metrics"]["operator_work_export"]["actor_subject"] = LEO
        evidence["metrics"]["operator_days"][0]["source_maintenance_task_count"] = 2

    result = _evaluate(valid_bundle, mutate)

    assert result["decision"] == "BLOCKED"
    codes = {issue["code"] for issue in result["issues"]}
    assert "OPERATOR_SUBJECT_INVALID" in codes
    assert "OPERATOR_SUMMARY_NOT_REPRODUCIBLE" in codes


def test_operator_export_covers_every_shanghai_calendar_date(valid_bundle: Any) -> None:
    def mutate(evidence: dict[str, Any], _gold: dict[str, Any]) -> None:
        evidence["metrics"]["operator_days"].pop()

    result = _evaluate(valid_bundle, mutate)

    assert result["decision"] == "BLOCKED"
    assert "OPERATOR_WINDOW_INCOMPLETE" in {issue["code"] for issue in result["issues"]}


def test_operator_backlog_and_cost_are_recomputed_from_work_export(valid_bundle: Any) -> None:
    def mutate(evidence: dict[str, Any], _gold: dict[str, Any]) -> None:
        evidence["metrics"]["operator_work_export"]["cost_entries"].append(
            {
                "ledger_entry_id": _uuid7(990_002),
                "amount_minor": 1,
                "category": "EMAIL",
                "recorded_at": _timestamp(STARTED_AT + timedelta(hours=1)),
            }
        )

    result = _evaluate(valid_bundle, mutate)

    assert result["decision"] == "BLOCKED"
    assert "OPERATOR_COST_INVALID" in {issue["code"] for issue in result["issues"]}


def _mutate_no_response_failure(
    evidence: dict[str, Any],
    *,
    root: Path,
    failure_code: str,
    request_count: int,
) -> None:
    failed = evidence["runs"][1]
    recovered = evidence["runs"][2]
    assert failed["source_key"] == recovered["source_key"]
    failed_at = failed["ended_at"]
    failed.update(
        {
            "evidence_class": "REAL_ATTEMPT",
            "response_state": "NO_RESPONSE",
            "outcome": "FAILED",
            "request_count": request_count,
            "final_url": None,
            "raw_response_sha256": None,
            "raw_evidence_ref": None,
            "response_metadata": None,
            "transport_failure_code": failure_code,
            "failure_detected_at": failed_at,
            "failure_detector_version": "round17-transport-failure-v1",
        }
    )
    failure_statement = {
        "run_id": failed["run_id"],
        "source_key": failed["source_key"],
        "failure_code": failure_code,
        "detected_at": failed_at,
        "detector_version": failed["failure_detector_version"],
        "request_url": failed["request_url"],
        "request_count": request_count,
    }
    failed["failure_evidence_ref"] = _ref(
        root,
        f"artifacts/health/{failure_code.lower()}-failure.json",
        json.dumps(failure_statement, ensure_ascii=False, sort_keys=True),
    )
    failed["database_record_ref"] = _ref(
        root,
        f"artifacts/runs/{failed['run_id']}-database-failure.json",
        json.dumps(_run_database_statement(failed), ensure_ascii=False, sort_keys=True),
    )

    recovered.update(
        {
            "recovered": True,
            "recovery_of_run_id": failed["run_id"],
            "recovery_verified_at": recovered["ended_at"],
        }
    )
    recovery_statement = {
        "run_id": recovered["run_id"],
        "source_key": recovered["source_key"],
        "recovery_of_run_id": failed["run_id"],
        "verified_at": recovered["recovery_verified_at"],
    }
    recovered["recovery_evidence_ref"] = _ref(
        root,
        f"artifacts/health/{failure_code.lower()}-recovery.json",
        json.dumps(recovery_statement, ensure_ascii=False, sort_keys=True),
    )
    recovered["database_record_ref"] = _ref(
        root,
        f"artifacts/runs/{recovered['run_id']}-database-recovery.json",
        json.dumps(_run_database_statement(recovered), ensure_ascii=False, sort_keys=True),
    )

    source = evidence["sources"][0]
    source["health_summary"].update(
        {
            "no_update_count": source["health_summary"]["no_update_count"] - 1,
            "failed_count": 1,
            "recovery_count": 1,
        }
    )
    health_statement = {
        "window_id": evidence["window"]["id"],
        "source_key": source["source_key"],
        "source_id": source["source_id"],
        "health_summary": source["health_summary"],
    }
    source["health_evidence_ref"] = _ref(
        root,
        f"artifacts/health/{source['source_key']}-{failure_code.lower()}.json",
        json.dumps(health_statement, ensure_ascii=False, sort_keys=True),
    )
    transport = evidence["metrics"]["rates"]["tier1_transport_success"]
    transport["passing_ids"].remove(failed["run_id"])
    transport["numerator"] = len(transport["passing_ids"])
    transport_statement = {
        "metric_name": "tier1_transport_success",
        "population_kind": transport["population_kind"],
        "eligible_ids": transport["eligible_ids"],
        "passing_ids": transport["passing_ids"],
        "snapshot_at": transport["snapshot_at"],
        "watermark": transport["watermark"],
    }
    transport["evidence_ref"] = _ref(
        root,
        f"artifacts/metrics/rate-tier1-{failure_code.lower()}.json",
        json.dumps(transport_statement, ensure_ascii=False, sort_keys=True),
    )


@pytest.mark.parametrize(
    ("failure_code", "request_count"),
    [("DNS_RESOLUTION_FAILED", 0), ("CONNECT_TIMEOUT", 1)],
)
def test_no_response_failures_are_honest_slots_with_verified_recovery(
    valid_bundle: Any,
    failure_code: str,
    request_count: int,
) -> None:
    root = valid_bundle[0]

    def mutate(evidence: dict[str, Any], _gold: dict[str, Any]) -> None:
        _mutate_no_response_failure(
            evidence,
            root=root,
            failure_code=failure_code,
            request_count=request_count,
        )

    result = _evaluate(valid_bundle, mutate)

    assert result["decision"] == "PASSED", result["issues"]


def test_false_success_flag_requires_causal_detection_evidence(valid_bundle: Any) -> None:
    def mutate(evidence: dict[str, Any], _gold: dict[str, Any]) -> None:
        run = evidence["runs"][1]
        run["fake_success_detected"] = True
        source = next(
            item for item in evidence["sources"] if item["source_key"] == run["source_key"]
        )
        source["health_summary"]["false_success_count"] += 1

    result = _evaluate(valid_bundle, mutate)

    assert result["decision"] == "BLOCKED"
    assert "FALSE_SUCCESS_CAUSAL_EVIDENCE_MISSING" in {
        issue["code"] for issue in result["issues"]
    }


def test_recovery_flag_must_link_an_earlier_same_source_failure(valid_bundle: Any) -> None:
    def mutate(evidence: dict[str, Any], _gold: dict[str, Any]) -> None:
        run = evidence["runs"][1]
        run["recovered"] = True
        source = next(
            item for item in evidence["sources"] if item["source_key"] == run["source_key"]
        )
        source["health_summary"]["recovery_count"] += 1

    result = _evaluate(valid_bundle, mutate)

    assert result["decision"] == "BLOCKED"
    assert "RECOVERY_CAUSAL_LINK_INVALID" in {issue["code"] for issue in result["issues"]}


def test_false_success_and_later_same_source_recovery_form_a_valid_health_chain(
    valid_bundle: Any,
) -> None:
    root = valid_bundle[0]

    def mutate(evidence: dict[str, Any], _gold: dict[str, Any]) -> None:
        failed = evidence["runs"][1]
        recovered = evidence["runs"][2]
        failed["outcome"] = "FAILED"
        failed["fake_success_detected"] = True
        failed["fake_success_detected_at"] = _timestamp(
            datetime.fromisoformat(failed["started_at"].replace("Z", "+00:00"))
            + timedelta(seconds=30)
        )
        failed["fake_success_rule_version"] = "r17-false-success-v1"
        failed["failure_cause_code"] = "EMPTY_SUCCESS_PAYLOAD"
        detection_statement = {
            "run_id": failed["run_id"],
            "source_key": failed["source_key"],
            "detected_at": failed["fake_success_detected_at"],
            "rule_version": failed["fake_success_rule_version"],
            "failure_cause_code": failed["failure_cause_code"],
        }
        failed["fake_success_evidence_ref"] = _ref(
            root,
            "artifacts/health/valid-false-success.json",
            json.dumps(detection_statement, ensure_ascii=False, sort_keys=True),
        )
        recovered["outcome"] = "SUCCEEDED"
        recovered["recovered"] = True
        recovered["recovery_of_run_id"] = failed["run_id"]
        recovered["recovery_verified_at"] = _timestamp(
            datetime.fromisoformat(recovered["started_at"].replace("Z", "+00:00"))
            + timedelta(seconds=30)
        )
        recovery_statement = {
            "run_id": recovered["run_id"],
            "source_key": recovered["source_key"],
            "recovery_of_run_id": failed["run_id"],
            "verified_at": recovered["recovery_verified_at"],
        }
        recovered["recovery_evidence_ref"] = _ref(
            root,
            "artifacts/health/valid-recovery.json",
            json.dumps(recovery_statement, ensure_ascii=False, sort_keys=True),
        )
        source = evidence["sources"][0]
        source["health_summary"].update(
            {
                "succeeded_count": 2,
                "no_update_count": source["health_summary"]["no_update_count"] - 2,
                "failed_count": 1,
                "false_success_count": 1,
                "recovery_count": 1,
            }
        )
        transport = evidence["metrics"]["rates"]["tier1_transport_success"]
        transport["passing_ids"].remove(failed["run_id"])
        transport["numerator"] = len(transport["passing_ids"])
        transport_statement = {
            "metric_name": "tier1_transport_success",
            "population_kind": transport["population_kind"],
            "eligible_ids": transport["eligible_ids"],
            "passing_ids": transport["passing_ids"],
            "snapshot_at": transport["snapshot_at"],
            "watermark": transport["watermark"],
        }
        transport["evidence_ref"] = _ref(
            root,
            "artifacts/metrics/rate-tier1-transport-with-recovery.json",
            json.dumps(transport_statement, ensure_ascii=False, sort_keys=True),
        )

    result = _evaluate(valid_bundle, mutate)

    causal_codes = {
        "FALSE_SUCCESS_CAUSAL_EVIDENCE_MISSING",
        "RECOVERY_CAUSAL_LINK_INVALID",
    }
    assert not (causal_codes & {issue["code"] for issue in result["issues"]}), result["issues"]


def test_scheduled_run_start_lateness_is_bounded(valid_bundle: Any) -> None:
    def mutate(evidence: dict[str, Any], _gold: dict[str, Any]) -> None:
        scheduled = datetime.fromisoformat(
            evidence["runs"][0]["scheduled_slot_at"].replace("Z", "+00:00")
        )
        evidence["runs"][0]["started_at"] = _timestamp(scheduled + timedelta(minutes=16))
        evidence["runs"][0]["ended_at"] = _timestamp(scheduled + timedelta(minutes=17))

    result = _evaluate(valid_bundle, mutate)

    assert result["decision"] == "BLOCKED"
    assert "RUN_START_LATENESS_EXCEEDED" in {issue["code"] for issue in result["issues"]}


def test_window_duration_rejects_subsecond_drift(valid_bundle: Any) -> None:
    def mutate(evidence: dict[str, Any], _gold: dict[str, Any]) -> None:
        evidence["window"]["ended_at"] = _timestamp(
            ENDED_AT + timedelta(milliseconds=500)
        )

    result = _evaluate(valid_bundle, mutate)

    assert result["decision"] == "BLOCKED"
    assert "WINDOW_NOT_EXACT_168_HOURS" in {
        issue["code"] for issue in result["issues"]
    }


def test_source_admission_manifest_binds_complete_runtime_identity(valid_bundle: Any) -> None:
    def mutate(evidence: dict[str, Any], _gold: dict[str, Any]) -> None:
        evidence["sources"][0]["display_name"] = "forged display name"

    result = _evaluate(valid_bundle, mutate)

    assert result["decision"] == "BLOCKED"
    assert "SOURCE_ADMISSION_MANIFEST_MISMATCH" in {
        issue["code"] for issue in result["issues"]
    }


def test_source_approval_audit_must_be_structured_and_exact(valid_bundle: Any) -> None:
    def mutate(evidence: dict[str, Any], _gold: dict[str, Any]) -> None:
        source = evidence["sources"][0]
        source["approvals"][0]["evidence_ref"] = source["health_evidence_ref"]

    result = _evaluate(valid_bundle, mutate)

    assert result["decision"] == "BLOCKED"
    assert "APPROVAL_AUDIT_REFERENCE_MISMATCH" in {
        issue["code"] for issue in result["issues"]
    }


@pytest.mark.parametrize(
    ("mutation", "issue_code"),
    [
        (
            lambda evidence: evidence["sources"][0]["approvals"][0].__setitem__(
                "mfa_verified_at",
                _timestamp(
                    datetime.fromisoformat(
                        evidence["sources"][0]["approvals"][0]["signed_at"].replace(
                            "Z", "+00:00"
                        )
                    )
                    + timedelta(seconds=1)
                ),
            ),
            "APPROVAL_MFA_ORDER_INVALID",
        ),
        (
            lambda evidence: evidence["sources"][0]["approvals"][0].__setitem__(
                "decision_id", "550e8400-e29b-41d4-a716-446655440000"
            ),
            "APPROVAL_DECISION_ID_INVALID",
        ),
        (
            lambda evidence: evidence["window"].__setitem__(
                "mfa_verified_at", _timestamp(STARTED_AT + timedelta(seconds=1))
            ),
            "WINDOW_START_MFA_ORDER_INVALID",
        ),
    ],
)
def test_governance_decisions_require_uuid7_and_prior_fresh_mfa(
    valid_bundle: Any,
    mutation: Any,
    issue_code: str,
) -> None:
    result = _evaluate(valid_bundle, lambda evidence, _gold: mutation(evidence))

    assert result["decision"] == "BLOCKED"
    assert issue_code in {issue["code"] for issue in result["issues"]}


def test_window_database_export_binds_state_segments_and_versions(valid_bundle: Any) -> None:
    def mutate(evidence: dict[str, Any], _gold: dict[str, Any]) -> None:
        evidence["window"]["version"] += 1

    result = _evaluate(valid_bundle, mutate)

    assert result["decision"] == "BLOCKED"
    assert "WINDOW_DATABASE_EXPORT_MISMATCH" in {
        issue["code"] for issue in result["issues"]
    }


def test_every_run_is_pinned_to_window_segment_and_source_versions(valid_bundle: Any) -> None:
    def mutate(evidence: dict[str, Any], _gold: dict[str, Any]) -> None:
        evidence["runs"][0]["window_id"] = "01900000-0000-7000-8000-999999999999"

    result = _evaluate(valid_bundle, mutate)

    assert result["decision"] == "BLOCKED"
    assert "RUN_WINDOW_VERSION_BINDING_MISMATCH" in {
        issue["code"] for issue in result["issues"]
    }


def test_run_universe_export_is_transactionally_complete(valid_bundle: Any) -> None:
    def mutate(evidence: dict[str, Any], _gold: dict[str, Any]) -> None:
        universe = evidence.get("run_universe")
        if isinstance(universe, dict):
            universe["included_run_count"] += 1

    result = _evaluate(valid_bundle, mutate)

    assert result["decision"] == "BLOCKED"
    assert "RUN_UNIVERSE_EXPORT_MISMATCH" in {
        issue["code"] for issue in result["issues"]
    }


def test_no_update_requires_real_response_metadata_and_change_semantics(valid_bundle: Any) -> None:
    def mutate(evidence: dict[str, Any], _gold: dict[str, Any]) -> None:
        run = next(item for item in evidence["runs"] if item["outcome"] == "NO_UPDATE")
        run["response_metadata"]["new_item_count"] = 1

    result = _evaluate(valid_bundle, mutate)

    assert result["decision"] == "BLOCKED"
    assert "NO_UPDATE_RESPONSE_METADATA_INVALID" in {
        issue["code"] for issue in result["issues"]
    }


def test_failure_drill_requires_prior_approval_safe_execution_and_result_evidence(
    valid_bundle: Any,
) -> None:
    def mutate(evidence: dict[str, Any], _gold: dict[str, Any]) -> None:
        drill = evidence.get("failure_drill")
        if isinstance(drill, dict):
            drill["completed_at"] = drill["approved_at"]

    result = _evaluate(valid_bundle, mutate)

    assert result["decision"] == "BLOCKED"
    assert "FAILURE_DRILL_INVALID" in {issue["code"] for issue in result["issues"]}


def test_source_update_requires_bidirectional_real_chain_evidence(
    valid_bundle: Any,
) -> None:
    def mutate(evidence: dict[str, Any], _gold: dict[str, Any]) -> None:
        source = evidence["sources"][0]
        source_key = source["source_key"]
        run = next(
            item
            for item in evidence["runs"]
            if item["source_key"] == source_key and item["outcome"] == "NO_UPDATE"
        )
        run["outcome"] = "SUCCEEDED"
        source["health_summary"]["succeeded_count"] += 1
        source["health_summary"]["no_update_count"] -= 1
        source["window_evidence_state"] = "NO_UPDATE"
        source["chain_evidence"] = None

    result = _evaluate(valid_bundle, mutate)

    assert result["decision"] == "BLOCKED"
    assert "SOURCE_REAL_CHAIN_EVIDENCE_MISSING" in {
        issue["code"] for issue in result["issues"]
    }


def test_north_star_success_must_reference_an_included_source_run_and_trace(
    valid_bundle: Any,
) -> None:
    def mutate(evidence: dict[str, Any], _gold: dict[str, Any]) -> None:
        event = evidence["event_evaluations"][0]
        event["source_run_id"] = "unknown-run"
        event["trace_evidence_ref"] = evidence["sources"][0]["health_evidence_ref"]

    result = _evaluate(valid_bundle, mutate)

    assert result["decision"] == "BLOCKED"
    assert "EVENT_TRACE_NOT_AUTHORITATIVE" in {
        issue["code"] for issue in result["issues"]
    }


def test_cli_returns_nonzero_blocked_when_real_evidence_is_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "round17_eval.py",
            "--evidence",
            str(tmp_path / "missing-evidence.json"),
            "--gold-manifest",
            str(tmp_path / "missing-gold.json"),
        ],
    )

    exit_code = main()
    output = json.loads(capsys.readouterr().out)

    assert exit_code == 1
    assert output["decision"] == "BLOCKED"
    assert output["issues"][0]["code"] == "REQUIRED_EVIDENCE_MISSING"
