"""Replay Round 15 lifecycle migration and rollback on an isolated database."""

# ruff: noqa: S101 -- explicit assertions are migration evidence.

from __future__ import annotations

import asyncio
import ipaddress
import json
import os
import re
from datetime import UTC, datetime, timedelta
from urllib.parse import urlsplit
from uuid import UUID

from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine
from srbg_api.identifiers import uuid7

_DISPOSABLE_DATABASE = re.compile(r"srbg_it_[0-9a-f]{24}\Z")


async def _expect_db_rejection(
    connection: AsyncConnection,
    statement: str,
    parameters: dict[str, object],
    *,
    label: str,
) -> None:
    nested = await connection.begin_nested()
    try:
        await connection.execute(text(statement), parameters)
    except DBAPIError:
        await nested.rollback()
    else:
        await nested.rollback()
        raise AssertionError(f"database accepted {label}")


def _policy_document(now: datetime) -> dict[str, object]:
    evidence = {
        "result": "ALLOWED",
        "evidence_url": "https://feeds.example.test/compliance/evidence",
        "evidence_sha256": "a" * 64,
        "checked_at": now.isoformat(),
    }
    return {
        "schema_version": "2.0.0",
        "policy_version": "round15-direct-boundary-v1",
        "valid_from": now.isoformat(),
        "valid_until": (now + timedelta(days=30)).isoformat(),
        "robots_review": evidence,
        "terms_review": evidence,
        "copyright_review": evidence,
        "fetch": {
            "allowed_domains": ["feeds.example.test"],
            "minimum_interval_seconds": 900,
            "rate_limit_per_minute": 4,
            "user_agent": "SRBG-Source-Boundary-Test/1.0",
        },
        "storage_policy": "RAW_EVIDENCE_ALLOWED",
        "display_policy": "METADATA_EXCERPT_LINK",
        "download_policy": "ORIGINAL_LINK_ONLY",
        "retention": {"retention_days": 365, "delete_after_retention": False},
        "legal_hold_policy": "SUPPORTED",
        "automatic_publication": "DISABLED",
        "slo": {
            "applicability": "NOT_APPLICABLE",
            "target_minutes": None,
            "reason": "No authorized production freshness commitment in this replay.",
            "authorization_confirmed": False,
            "technical_conditions_confirmed": False,
        },
        "reason": "exercise the database authority boundary",
    }


async def _verify_authoritative_write_boundaries(database_url: str) -> None:
    engine = create_async_engine(database_url)
    source_id = uuid7()
    registered_by = uuid7()
    policy_submitter = uuid7()
    compliance_approver = uuid7()
    trial_requester = uuid7()
    now = datetime.now(UTC).replace(microsecond=0)
    policy_call = """
        SELECT submit_source_policy_version(
          :source_id,:policy_id,'2.0.0',:policy_version,CAST(:document AS jsonb),
          :valid_from,:valid_until,:actor_id,:reason,:request_id,:audit_id,:now
        )
    """
    config_call = """
        SELECT save_source_connector_config(
          :source_id,:config_id,:definition_id,:version_number,
          CAST(:config_document AS jsonb),NULL,:supersedes_id,:actor_id,
          :reason,:request_id,:audit_id,:now
        )
    """
    try:
        async with engine.connect() as connection:
            transaction = await connection.begin()
            try:
                await connection.execute(text("SET LOCAL ROLE srbg_api_role"))
                await connection.execute(
                    text(
                        """
                        SELECT register_source_candidate(
                          :source_id,'Round 15 boundary source',
                          'https://feeds.example.test','SAFETY','government','A1','P0',
                          'RSS',60,'source-ops',:governance_owner,
                          ARRAY['CN']::text[],ARRAY['CN-SC']::text[],
                          ARRAY['zh-CN']::text[],ARRAY['HIGHWAY']::text[],
                          ARRAY['SAFETY_REGULATION']::text[],
                          ARRAY['OFFICIAL_PRIMARY']::text[],
                          :registered_by,'round15-boundary-register',:audit_id,:now
                        )
                        """
                    ),
                    {
                        "source_id": source_id,
                        "governance_owner": uuid7(),
                        "registered_by": registered_by,
                        "audit_id": uuid7(),
                        "now": now,
                    },
                )
                await _expect_db_rejection(
                    connection,
                    """
                    SELECT update_source_governance_metadata(
                      :source_id,:owner,ARRAY['CN']::text[],ARRAY[:region]::text[],
                      ARRAY['zh-CN']::text[],ARRAY['HIGHWAY']::text[],
                      ARRAY['SAFETY_REGULATION']::text[],
                      ARRAY['OFFICIAL_PRIMARY']::text[],:actor,
                      'reject oversized metadata',:request_id,:audit_id,:now
                    )
                    """,
                    {
                        "source_id": source_id,
                        "owner": uuid7(),
                        "region": "X" * 1000,
                        "actor": registered_by,
                        "request_id": "round15-oversized-metadata",
                        "audit_id": uuid7(),
                        "now": now,
                    },
                    label="an oversized governance metadata item",
                )
                await _expect_db_rejection(
                    connection,
                    """
                    SELECT append_source_assessments(
                      :source_id,:authority_id,'A1','round15-v1',
                      ARRAY['bad-code']::text[],
                      ARRAY['https://example.test/evidence?token=secret']::text[],
                      :now,:independence_id,'EDITORIALLY_INDEPENDENT','round15-v1',
                      ARRAY['EDITORIAL_REVIEW']::text[],
                      ARRAY['review:editorial-policy']::text[],:now,:actor,
                      'reject unsafe assessment',:request_id,:audit_id,:now
                    )
                    """,
                    {
                        "source_id": source_id,
                        "authority_id": uuid7(),
                        "independence_id": uuid7(),
                        "actor": registered_by,
                        "request_id": "round15-unsafe-assessment",
                        "audit_id": uuid7(),
                        "now": now,
                    },
                    label="unsafe assessment item values",
                )
                await _expect_db_rejection(
                    connection,
                    """
                    SELECT apply_source_lifecycle_command(
                      :source_id,'SUBMIT_COMPLIANCE',:actor_id,
                      'inspect https://private.example.test?token=secret',
                      :request_id,:event_id,:now
                    )
                    """,
                    {
                        "source_id": source_id,
                        "actor_id": registered_by,
                        "request_id": "round15-sensitive-reason-rejected",
                        "event_id": uuid7(),
                        "now": now,
                    },
                    label="a sensitive governance reason",
                )
                await connection.execute(
                    text(
                        """
                        SELECT apply_source_lifecycle_command(
                          :source_id,'SUBMIT_COMPLIANCE',:actor_id,
                          'submit for boundary verification',:request_id,:event_id,:now
                        )
                        """
                    ),
                    {
                        "source_id": source_id,
                        "actor_id": registered_by,
                        "request_id": "round15-boundary-compliance",
                        "event_id": uuid7(),
                        "now": now,
                    },
                )

                forged_slo = _policy_document(now)
                forged_slo["policy_version"] = "forged-15-minute-slo"
                forged_slo["reason"] = "attempt an unauthorized SLO"
                forged_slo["slo"] = {
                    "applicability": "APPLICABLE",
                    "target_minutes": 15,
                    "reason": None,
                    "authorization_confirmed": False,
                    "technical_conditions_confirmed": False,
                }
                await _expect_db_rejection(
                    connection,
                    policy_call,
                    {
                        "source_id": source_id,
                        "policy_id": uuid7(),
                        "policy_version": "forged-15-minute-slo",
                        "document": json.dumps(forged_slo),
                        "valid_from": now,
                        "valid_until": now + timedelta(days=30),
                        "actor_id": policy_submitter,
                        "reason": "attempt an unauthorized SLO",
                        "request_id": "round15-forged-slo",
                        "audit_id": uuid7(),
                        "now": now,
                    },
                    label="an applicable 15-minute SLO without both confirmations",
                )
                invalid_not_applicable = _policy_document(now)
                invalid_not_applicable["policy_version"] = "forged-not-applicable-slo"
                invalid_not_applicable["reason"] = "attempt a contradictory SLO"
                invalid_not_applicable["slo"] = {
                    "applicability": "NOT_APPLICABLE",
                    "target_minutes": 15,
                    "reason": "conflicting target",
                    "authorization_confirmed": False,
                    "technical_conditions_confirmed": False,
                }
                await _expect_db_rejection(
                    connection,
                    policy_call,
                    {
                        "source_id": source_id,
                        "policy_id": uuid7(),
                        "policy_version": "forged-not-applicable-slo",
                        "document": json.dumps(invalid_not_applicable),
                        "valid_from": now,
                        "valid_until": now + timedelta(days=30),
                        "actor_id": policy_submitter,
                        "reason": "attempt a contradictory SLO",
                        "request_id": "round15-forged-slo-na",
                        "audit_id": uuid7(),
                        "now": now,
                    },
                    label="a non-applicable SLO with a target",
                )

                invalid_documents: tuple[tuple[str, dict[str, object]], ...] = (
                    (
                        "unknown top-level policy field",
                        _policy_document(now) | {"arbitrary_override": True},
                    ),
                    (
                        "unknown nested fetch field",
                        _policy_document(now)
                        | {
                            "fetch": {
                                **dict(_policy_document(now)["fetch"]),  # type: ignore[arg-type]
                                "dynamic_target": "internal.service",
                            }
                        },
                    ),
                    (
                        "user agent control characters",
                        _policy_document(now)
                        | {
                            "fetch": {
                                **dict(_policy_document(now)["fetch"]),  # type: ignore[arg-type]
                                "user_agent": "ok\r\nX-Evil: yes",
                            }
                        },
                    ),
                    (
                        "unsupported full-text storage policy",
                        _policy_document(now) | {"storage_policy": "FULLTEXT"},
                    ),
                    (
                        "out-of-range retention",
                        _policy_document(now)
                        | {
                            "retention": {
                                "retention_days": 0,
                                "delete_after_retention": False,
                            }
                        },
                    ),
                )
                for label, invalid_document in invalid_documents:
                    reason = f"reject {label}"
                    invalid_version = f"invalid-{uuid7()}"
                    invalid_document["reason"] = reason
                    invalid_document["policy_version"] = invalid_version
                    await _expect_db_rejection(
                        connection,
                        policy_call,
                        {
                            "source_id": source_id,
                            "policy_id": uuid7(),
                            "policy_version": invalid_version,
                            "document": json.dumps(invalid_document),
                            "valid_from": now,
                            "valid_until": now + timedelta(days=30),
                            "actor_id": policy_submitter,
                            "reason": reason,
                            "request_id": f"round15-{label}",
                            "audit_id": uuid7(),
                            "now": now,
                        },
                        label=label,
                    )

                policy_id = uuid7()
                valid_policy = _policy_document(now)
                valid_policy["policy_version"] = "round15-boundary-valid"
                valid_policy["reason"] = "submit valid policy for connector boundary tests"
                await connection.execute(
                    text(policy_call),
                    {
                        "source_id": source_id,
                        "policy_id": policy_id,
                        "policy_version": "round15-boundary-valid",
                        "document": json.dumps(valid_policy),
                        "valid_from": now,
                        "valid_until": now + timedelta(days=30),
                        "actor_id": policy_submitter,
                        "reason": "submit valid policy for connector boundary tests",
                        "request_id": "round15-valid-policy",
                        "audit_id": uuid7(),
                        "now": now,
                    },
                )
                await connection.execute(
                    text(
                        """
                        SELECT decide_source_policy_version(
                          :source_id,:policy_id,:decision_id,'APPROVED',:actor_id,
                          'independent boundary approval',:request_id,:audit_id,:now
                        )
                        """
                    ),
                    {
                        "source_id": source_id,
                        "policy_id": policy_id,
                        "decision_id": uuid7(),
                        "actor_id": compliance_approver,
                        "request_id": "round15-valid-policy-decision",
                        "audit_id": uuid7(),
                        "now": now,
                    },
                )
                definition_id = await connection.scalar(
                    text(
                        "SELECT id FROM connector_definition "
                        "WHERE connector_type='RSS_ATOM' AND definition_version='1.0.0'"
                    )
                )
                assert isinstance(definition_id, UUID)
                invalid_configs: tuple[tuple[str, dict[str, object]], ...] = (
                    (
                        "metadata IP host",
                        {
                            "allowed_hosts": ["169.254.169.254"],
                            "feed_url": "http://169.254.169.254/latest/meta-data",
                        },
                    ),
                    (
                        "wildcard host",
                        {
                            "allowed_hosts": ["*.example.test"],
                            "feed_url": "https://feeds.example.test/rss.xml",
                        },
                    ),
                    (
                        "URL with embedded credential",
                        {
                            "allowed_hosts": ["feeds.example.test"],
                            "feed_url": "https://feeds.example.test/rss.xml?api_key=secret",
                        },
                    ),
                    (
                        "URL with any query",
                        {
                            "allowed_hosts": ["feeds.example.test"],
                            "feed_url": "https://feeds.example.test/rss.xml?page=1",
                        },
                    ),
                    (
                        "URL with dangerous port",
                        {
                            "allowed_hosts": ["feeds.example.test"],
                            "feed_url": "https://feeds.example.test:8443/rss.xml",
                        },
                    ),
                    (
                        "wrong URL field type",
                        {"allowed_hosts": ["feeds.example.test"], "feed_url": 123},
                    ),
                    (
                        "script field",
                        {
                            "allowed_hosts": ["feeds.example.test"],
                            "feed_url": "https://feeds.example.test/rss.xml",
                            "script": "import os",
                        },
                    ),
                )
                for label, document in invalid_configs:
                    await _expect_db_rejection(
                        connection,
                        config_call,
                        {
                            "source_id": source_id,
                            "config_id": uuid7(),
                            "definition_id": definition_id,
                            "version_number": 1,
                            "config_document": json.dumps(document),
                            "supersedes_id": None,
                            "actor_id": policy_submitter,
                            "reason": f"attempt {label}",
                            "request_id": f"round15-invalid-{label}",
                            "audit_id": uuid7(),
                            "now": now,
                        },
                        label=label,
                    )

                config_id = uuid7()
                await connection.execute(
                    text(config_call),
                    {
                        "source_id": source_id,
                        "config_id": config_id,
                        "definition_id": definition_id,
                        "version_number": 1,
                        "config_document": json.dumps(
                            {
                                "allowed_hosts": ["feeds.example.test"],
                                "feed_url": "https://feeds.example.test/rss-v2.xml",
                            }
                        ),
                        "supersedes_id": None,
                        "actor_id": policy_submitter,
                        "reason": "persist a valid connector for capture checks",
                        "request_id": "round15-valid-config",
                        "audit_id": uuid7(),
                        "now": now,
                    },
                )
                trial_id = uuid7()
                await connection.execute(
                    text(
                        """
                        SELECT start_source_trial_run(
                          :source_id,:trial_id,'FIXTURE_REPLAY',:policy_id,:config_id,
                          :decision_id,:actor_id,'fixture capture boundary test',
                          :request_id,:event_id,:audit_id,:now
                        )
                        """
                    ),
                    {
                        "source_id": source_id,
                        "trial_id": trial_id,
                        "policy_id": policy_id,
                        "config_id": config_id,
                        "decision_id": uuid7(),
                        "actor_id": trial_requester,
                        "request_id": "round15-capture-trial",
                        "event_id": uuid7(),
                        "audit_id": uuid7(),
                        "now": now,
                    },
                )

                await connection.execute(text("RESET ROLE"))
                raw_id = uuid7()
                content_sha256 = "c" * 64
                response_sha256 = "d" * 64
                await connection.execute(
                    text(
                        """
                        INSERT INTO raw_object(
                          id,sha256,object_key,byte_size,declared_mime,detected_mime,
                          scan_status,storage_etag,created_at
                        ) VALUES (
                          :id,:sha256,:object_key,20,'application/xml','application/xml',
                          'CLEAN',NULL,:now
                        )
                        """
                    ),
                    {
                        "id": raw_id,
                        "sha256": content_sha256,
                        "object_key": f"sha256/cc/{content_sha256}",
                        "now": now,
                    },
                )
                await connection.execute(
                    text(
                        """
                        INSERT INTO raw_object_security_fact(
                          id,raw_object_id,status,detected_mime,rule_version,
                          reason_code,created_at
                        ) VALUES (
                          :id,:raw_id,'CLEAN','application/xml','round15-boundary',NULL,:now
                        )
                        """
                    ),
                    {"id": uuid7(), "raw_id": raw_id, "now": now},
                )
                await connection.execute(text("SET LOCAL ROLE srbg_api_role"))
                capture_call = """
                    SELECT append_source_trial_raw_capture(
                      :capture_id,:raw_id,:source_id,:trial_id,'FIXTURE',
                      :requested_url,:final_url,CAST(:redirect_chain AS jsonb),200,
                      NULL,NULL,:response_sha256,:now
                    )
                """
                await connection.execute(
                    text(capture_call),
                    {
                        "capture_id": uuid7(),
                        "raw_id": raw_id,
                        "source_id": source_id,
                        "trial_id": trial_id,
                        "requested_url": "https://feeds.example.test/rss.xml",
                        "final_url": "https://feeds.example.test/rss.xml",
                        "redirect_chain": "[]",
                        "response_sha256": response_sha256,
                        "now": now,
                    },
                )
                stored_response_hash = await connection.scalar(
                    text(
                        "SELECT response_sha256 FROM raw_object_capture WHERE raw_object_id=:raw_id"
                    ),
                    {"raw_id": raw_id},
                )
                assert stored_response_hash == response_sha256
                assert stored_response_hash != content_sha256
                unsafe_captures = (
                    (
                        "raw requested URL userinfo",
                        "https://user:secret@feeds.example.test/rss.xml",
                        "https://feeds.example.test/rss.xml",
                        "[]",
                    ),
                    (
                        "raw final URL sensitive query",
                        "https://feeds.example.test/rss.xml",
                        "https://feeds.example.test/rss.xml?token=secret",
                        "[]",
                    ),
                    (
                        "raw final URL noncredential query",
                        "https://feeds.example.test/rss.xml",
                        "https://feeds.example.test/rss.xml?page=1",
                        "[]",
                    ),
                    (
                        "raw redirect signed query",
                        "https://feeds.example.test/rss.xml",
                        "https://feeds.example.test/rss.xml",
                        json.dumps(["https://feeds.example.test/rss.xml?X-Amz-Signature=secret"]),
                    ),
                )
                for label, requested_url, final_url, redirect_chain in unsafe_captures:
                    await _expect_db_rejection(
                        connection,
                        capture_call,
                        {
                            "capture_id": uuid7(),
                            "raw_id": raw_id,
                            "source_id": source_id,
                            "trial_id": trial_id,
                            "requested_url": requested_url,
                            "final_url": final_url,
                            "redirect_chain": redirect_chain,
                            "response_sha256": response_sha256,
                            "now": now,
                        },
                        label=label,
                    )

                # A later clean result cannot erase any rejected/quarantined raw
                # history for roots or attachments.
                await connection.execute(text("RESET ROLE"))
                blocked_raw_id = uuid7()
                blocked_hash = "b" * 64
                await connection.execute(
                    text(
                        """
                        INSERT INTO raw_object(
                          id,sha256,object_key,byte_size,declared_mime,detected_mime,
                          scan_status,storage_etag,created_at
                        ) VALUES (
                          :id,:sha256,:object_key,20,'text/html','text/html',
                          'CLEAN',NULL,:now
                        )
                        """
                    ),
                    {
                        "id": blocked_raw_id,
                        "sha256": blocked_hash,
                        "object_key": f"sha256/bb/{blocked_hash}",
                        "now": now,
                    },
                )
                await connection.execute(
                    text(
                        """
                        INSERT INTO raw_object_security_fact(
                          id,raw_object_id,status,detected_mime,rule_version,
                          reason_code,created_at
                        ) VALUES
                          (:quarantined_id,:raw_id,'QUARANTINED','text/html',
                           'round15-rejected-first','MALWARE_SCAN_FAILED',:now),
                          (:clean_id,:raw_id,'CLEAN','text/html',
                           'round15-later-clean',NULL,:later)
                        """
                    ),
                    {
                        "quarantined_id": uuid7(),
                        "clean_id": uuid7(),
                        "raw_id": blocked_raw_id,
                        "now": now,
                        "later": now + timedelta(microseconds=1),
                    },
                )
                await connection.execute(text("SET LOCAL ROLE srbg_api_role"))
                await _expect_db_rejection(
                    connection,
                    capture_call,
                    {
                        "capture_id": uuid7(),
                        "raw_id": blocked_raw_id,
                        "source_id": source_id,
                        "trial_id": trial_id,
                        "requested_url": "https://feeds.example.test/blocked.html",
                        "final_url": "https://feeds.example.test/blocked.html",
                        "redirect_chain": "[]",
                        "response_sha256": "e" * 64,
                        "now": now,
                    },
                    label="a raw object with historical quarantined evidence",
                )

                # Only captured raw objects that form document versions enter the
                # quality denominator. The discovery response above is excluded.
                await connection.execute(text("RESET ROLE"))
                quality_document_id = uuid7()
                await connection.execute(
                    text(
                        """
                        INSERT INTO document(
                          id,source_id,canonical_url,document_kind,
                          first_discovered_at,current_version_id,admission_fixture
                        ) VALUES (
                          :id,:source_id,:url,'HTML',:now,NULL,true
                        )
                        """
                    ),
                    {
                        "id": quality_document_id,
                        "source_id": source_id,
                        "url": "https://feeds.example.test/quality-document",
                        "now": now,
                    },
                )
                quality_versions: list[tuple[str, UUID, UUID]] = []
                ready_raw_id: UUID | None = None
                for version_number, (state, hash_character) in enumerate(
                    (("READY", "1"), ("FAILED", "2"), ("QUARANTINED", "3")),
                    start=1,
                ):
                    document_raw_id = uuid7()
                    document_hash = hash_character * 64
                    await connection.execute(
                        text(
                            """
                            INSERT INTO raw_object(
                              id,sha256,object_key,byte_size,declared_mime,
                              detected_mime,scan_status,storage_etag,created_at
                            ) VALUES (
                              :id,:sha256,:object_key,20,'text/html','text/html',
                              'CLEAN',NULL,:now
                            )
                            """
                        ),
                        {
                            "id": document_raw_id,
                            "sha256": document_hash,
                            "object_key": (f"sha256/{hash_character * 2}/{document_hash}"),
                            "now": now,
                        },
                    )
                    await connection.execute(
                        text(
                            """
                            INSERT INTO raw_object_security_fact(
                              id,raw_object_id,status,detected_mime,rule_version,
                              reason_code,created_at
                            ) VALUES (
                              :id,:raw_id,'CLEAN','text/html',:rule,NULL,:now
                            )
                            """
                        ),
                        {
                            "id": uuid7(),
                            "raw_id": document_raw_id,
                            "rule": f"round15-quality-{version_number}",
                            "now": now,
                        },
                    )
                    capture_id = uuid7()
                    await connection.execute(text("SET LOCAL ROLE srbg_api_role"))
                    await connection.execute(
                        text(capture_call),
                        {
                            "capture_id": capture_id,
                            "raw_id": document_raw_id,
                            "source_id": source_id,
                            "trial_id": trial_id,
                            "requested_url": ("https://feeds.example.test/quality-document"),
                            "final_url": ("https://feeds.example.test/quality-document"),
                            "redirect_chain": "[]",
                            "response_sha256": hash_character * 64,
                            "now": now,
                        },
                    )
                    await connection.execute(text("RESET ROLE"))
                    version_id = uuid7()
                    await connection.execute(
                        text(
                            """
                            INSERT INTO document_version(
                              id,document_id,raw_object_id,version_number,
                              content_hash,original_filename,title,acquired_at,
                              execution_domain,raw_object_capture_id
                            ) VALUES (
                              :id,:document_id,:raw_id,:version_number,:content_hash,
                              :filename,'Quality boundary',:now,'FIXTURE',:capture_id
                            )
                            """
                        ),
                        {
                            "id": version_id,
                            "document_id": quality_document_id,
                            "raw_id": document_raw_id,
                            "version_number": version_number,
                            "content_hash": document_hash,
                            "filename": f"quality-{version_number}.html",
                            "now": now,
                            "capture_id": capture_id,
                        },
                    )
                    await connection.execute(
                        text(
                            """
                            INSERT INTO document_version_state_event(
                              id,document_version_id,state,reason_code,
                              actor_type,created_at
                            ) VALUES (
                              :id,:version_id,:state,:reason,'WORKER',:created_at
                            )
                            """
                        ),
                        {
                            "id": uuid7(),
                            "version_id": version_id,
                            "state": "READY" if state == "QUARANTINED" else state,
                            "reason": None
                            if state in {"READY", "QUARANTINED"}
                            else f"TEST_{state}",
                            "created_at": now + timedelta(microseconds=version_number),
                        },
                    )
                    if state == "QUARANTINED":
                        await connection.execute(
                            text(
                                """
                                INSERT INTO raw_object_security_fact(
                                  id,raw_object_id,status,detected_mime,rule_version,
                                  reason_code,created_at
                                ) VALUES
                                  (:negative_id,:raw_id,'QUARANTINED','text/html',
                                   'round15-quality-negative','MALWARE_FOUND',:negative_at),
                                  (:clean_id,:raw_id,'CLEAN','text/html',
                                   'round15-quality-later-clean',NULL,:clean_at)
                                """
                            ),
                            {
                                "negative_id": uuid7(),
                                "clean_id": uuid7(),
                                "raw_id": document_raw_id,
                                "negative_at": now + timedelta(microseconds=10),
                                "clean_at": now + timedelta(microseconds=11),
                            },
                        )
                    quality_versions.append((state, document_raw_id, version_id))
                    if state == "READY":
                        ready_raw_id = document_raw_id
                        await connection.execute(
                            text(
                                "UPDATE document SET current_version_id=:version_id "
                                "WHERE id=:document_id"
                            ),
                            {
                                "version_id": version_id,
                                "document_id": quality_document_id,
                            },
                        )
                assert ready_raw_id is not None

                # A duplicate capture is evidence, not another document-level raw.
                await connection.execute(text("SET LOCAL ROLE srbg_api_role"))
                await connection.execute(
                    text(capture_call),
                    {
                        "capture_id": uuid7(),
                        "raw_id": ready_raw_id,
                        "source_id": source_id,
                        "trial_id": trial_id,
                        "requested_url": "https://feeds.example.test/quality-document",
                        "final_url": "https://feeds.example.test/quality-document",
                        "redirect_chain": "[]",
                        "response_sha256": "1" * 64,
                        "now": now,
                    },
                )
                replay_result_call = """
                    SELECT record_source_fixture_replay_result(
                      :trial_id,:source_id,:config_id,:status,:reason_code,
                      :raw_capture_count,:document_count,:transport_call_count,
                      :actor_id,:now
                    )
                """
                await _expect_db_rejection(
                    connection,
                    replay_result_call,
                    {
                        "trial_id": trial_id,
                        "source_id": source_id,
                        "config_id": config_id,
                        "status": "FAILED",
                        "reason_code": "CONNECTOR_OUTPUT_MISMATCH",
                        "raw_capture_count": 4,
                        "document_count": 3,
                        "transport_call_count": 5,
                        "actor_id": trial_requester,
                        "now": now,
                    },
                    label="a fixture replay result with a forged raw capture count",
                )
                await connection.execute(
                    text(replay_result_call),
                    {
                        "trial_id": trial_id,
                        "source_id": source_id,
                        "config_id": config_id,
                        "status": "FAILED",
                        "reason_code": "CONNECTOR_OUTPUT_MISMATCH",
                        "raw_capture_count": 5,
                        "document_count": 3,
                        "transport_call_count": 5,
                        "actor_id": trial_requester,
                        "now": now,
                    },
                )
                await _expect_db_rejection(
                    connection,
                    replay_result_call,
                    {
                        "trial_id": trial_id,
                        "source_id": source_id,
                        "config_id": config_id,
                        "status": "FAILED",
                        "reason_code": "DUPLICATE_REPLAY_RESULT",
                        "raw_capture_count": 5,
                        "document_count": 3,
                        "transport_call_count": 5,
                        "actor_id": trial_requester,
                        "now": now,
                    },
                    label="a duplicate fixture replay result",
                )
                complete_call = """
                    SELECT complete_source_trial_run_with_audit(
                      :trial_id,:status,CAST(:quality AS jsonb),
                      :namespace,:actor_id,:reason,:request_id,:audit_id,:now
                    )
                """
                await _expect_db_rejection(
                    connection,
                    complete_call,
                    {
                        "trial_id": trial_id,
                        "status": "FAILED",
                        "quality": json.dumps(
                            {
                                "raw_count": 4,
                                "ready_count": 4,
                                "parse_failed_count": 0,
                                "security_failed_count": 0,
                                "rejected_raw_attempt_count": 0,
                                "ready_ratio_bps": 10000,
                            }
                        ),
                        "namespace": f"fixture/{trial_id}/raw/",
                        "actor_id": trial_requester,
                        "reason": "complete deterministic fixture quality replay",
                        "request_id": "round15-forged-fixture-quality",
                        "audit_id": uuid7(),
                        "now": now,
                    },
                    label="a client-forged source trial quality summary",
                )
                expected_quality = {
                    "raw_count": 3,
                    "ready_count": 0,
                    "parse_failed_count": 2,
                    "security_failed_count": 1,
                    "rejected_raw_attempt_count": 0,
                    "ready_ratio_bps": 0,
                }
                await connection.execute(
                    text(complete_call),
                    {
                        "trial_id": trial_id,
                        "status": "FAILED",
                        "quality": json.dumps(expected_quality),
                        "namespace": f"fixture/{trial_id}/raw/",
                        "actor_id": trial_requester,
                        "reason": "complete deterministic fixture quality replay",
                        "request_id": "round15-fixture-quality",
                        "audit_id": uuid7(),
                        "now": now,
                    },
                )
                stored_quality = await connection.scalar(
                    text(
                        "SELECT quality_summary FROM source_trial_run_result "
                        "WHERE trial_run_id=:trial_id"
                    ),
                    {"trial_id": trial_id},
                )
                assert stored_quality == expected_quality
                stored_replay_result = (
                    (
                        await connection.execute(
                            text(
                                "SELECT status,reason_code,raw_capture_count,document_count,"
                                "transport_call_count FROM source_fixture_replay_result "
                                "WHERE trial_run_id=:trial_id"
                            ),
                            {"trial_id": trial_id},
                        )
                    )
                    .mappings()
                    .one()
                )
                assert dict(stored_replay_result) == {
                    "status": "FAILED",
                    "reason_code": "CONNECTOR_OUTPUT_MISMATCH",
                    "raw_capture_count": 5,
                    "document_count": 3,
                    "transport_call_count": 5,
                }
                current_quality_version = await connection.scalar(
                    text("SELECT current_version_id FROM document WHERE id=:id"),
                    {"id": quality_document_id},
                )
                assert current_quality_version == quality_versions[0][2]

                # Context-only rejection is attributed to the current fixture
                # trial without poisoning an existing globally CLEAN content hash.
                contextual_attempt_id = uuid7()
                negative_before = await connection.scalar(
                    text(
                        """
                        SELECT count(*) FROM raw_object_security_fact
                         WHERE raw_object_id=:raw_id
                           AND status IN ('REJECTED','QUARANTINED')
                        """
                    ),
                    {"raw_id": ready_raw_id},
                )
                await connection.execute(
                    text(
                        """
                        SELECT append_source_trial_rejected_raw_attempt(
                          :attempt_id,:source_id,:trial_id,:raw_id,:content_sha256,
                          :object_key,:url,'MIME_MISMATCH',:actor_id,:request_id,:now
                        )
                        """
                    ),
                    {
                        "attempt_id": contextual_attempt_id,
                        "source_id": source_id,
                        "trial_id": trial_id,
                        "raw_id": ready_raw_id,
                        "content_sha256": "1" * 64,
                        "object_key": f"sha256/11/{'1' * 64}",
                        "url": "https://feeds.example.test/quality-document",
                        "actor_id": trial_requester,
                        "request_id": "round15-contextual-rejection",
                        "now": now + timedelta(microseconds=1),
                    },
                )
                assert (
                    await connection.scalar(
                        text(
                            "SELECT count(*) FROM source_trial_rejected_raw_attempt "
                            "WHERE id=:id AND source_id=:source_id "
                            "AND arrived_after_close=true"
                        ),
                        {"id": contextual_attempt_id, "source_id": source_id},
                    )
                    == 1
                )
                assert (
                    await connection.scalar(
                        text(
                            "SELECT count(*) FROM raw_object_security_fact "
                            "WHERE raw_object_id=:raw_id "
                            "AND status IN ('REJECTED','QUARANTINED')"
                        ),
                        {"raw_id": ready_raw_id},
                    )
                    == negative_before
                )
                assert (
                    await connection.scalar(
                        text("SELECT current_version_id FROM document WHERE id=:id"),
                        {"id": quality_document_id},
                    )
                    == quality_versions[0][2]
                )
                audit_projection = (
                    (
                        await connection.execute(
                            text(
                                """
                            SELECT event_type,after_state
                              FROM audit_log WHERE id=:attempt_id
                            """
                            ),
                            {"attempt_id": contextual_attempt_id},
                        )
                    )
                    .mappings()
                    .one()
                )
                assert audit_projection["event_type"] == "SOURCE_TRIAL_RAW_REJECTED"
                audit_text = json.dumps(audit_projection["after_state"])
                assert "quality-document" not in audit_text
                assert "object_key" not in audit_text
                await _expect_db_rejection(
                    connection,
                    """
                    SELECT append_source_trial_rejected_raw_attempt(
                      :attempt_id,:source_id,:trial_id,:raw_id,:content_sha256,
                      :object_key,:url,'MIME_MISMATCH',:actor_id,:request_id,:now
                    )
                    """,
                    {
                        "attempt_id": uuid7(),
                        "source_id": source_id,
                        "trial_id": trial_id,
                        "raw_id": ready_raw_id,
                        "content_sha256": "1" * 64,
                        "object_key": f"sha256/11/{'1' * 64}",
                        "url": ("https://feeds.example.test/quality-document?token=secret"),
                        "actor_id": trial_requester,
                        "request_id": "round15-sensitive-rejected-url",
                        "now": now,
                    },
                    label="a rejected-attempt URL containing a credential",
                )

                # The database trigger independently protects attachment reuse.
                await connection.execute(text("RESET ROLE"))
                await _expect_db_rejection(
                    connection,
                    """
                    INSERT INTO document_attachment(
                      id,document_version_id,raw_object_id,filename,role,
                      security_status,created_at
                    ) VALUES (
                      :id,:version_id,:raw_id,'blocked.html','SOURCE_ATTACHMENT',
                      'CLEAN',:now
                    )
                    """,
                    {
                        "id": uuid7(),
                        "version_id": quality_versions[0][2],
                        "raw_id": blocked_raw_id,
                        "now": now,
                    },
                    label="a clean attachment backed by rejected raw history",
                )
                await connection.execute(text("SET LOCAL ROLE srbg_api_role"))
                connector_cases: tuple[tuple[str, dict[str, object], dict[str, object]], ...] = (
                    (
                        "JSON_API",
                        {
                            "allowed_hosts": ["feeds.example.test"],
                            "endpoint_url": "https://feeds.example.test/api/notices",
                            "items_pointer": "$.items[*]",
                            "field_pointers": {
                                "external_id": "/id",
                                "url": "/url",
                                "title": "/title",
                            },
                            "pagination": "NONE",
                        },
                        {
                            "allowed_hosts": ["feeds.example.test"],
                            "endpoint_url": "https://feeds.example.test/api/notices",
                            "items_pointer": "/items",
                            "field_pointers": {
                                "external_id": "/id",
                                "url": "/url",
                                "title": "/title",
                            },
                            "pagination": "NONE",
                        },
                    ),
                    (
                        "SITEMAP",
                        {
                            "allowed_hosts": ["feeds.example.test"],
                            "sitemap_url": True,
                        },
                        {
                            "allowed_hosts": ["feeds.example.test"],
                            "sitemap_url": "https://feeds.example.test/sitemap.xml",
                        },
                    ),
                    (
                        "LIST_DETAIL",
                        {
                            "allowed_hosts": ["feeds.example.test"],
                            "list_url": "https://feeds.example.test/notices",
                            "item_selector": "article.item",
                            "link_selector": "a[href={{ next }}]",
                            "title_selector": "h2.title",
                        },
                        {
                            "allowed_hosts": ["feeds.example.test"],
                            "list_url": "https://feeds.example.test/notices",
                            "item_selector": "article.item",
                            "link_selector": "a.detail",
                            "title_selector": "h2.title",
                            "published_selector": "time.published",
                        },
                    ),
                    (
                        "DIRECT_PDF",
                        {
                            "allowed_hosts": ["feeds.example.test"],
                            "document_urls": "https://feeds.example.test/rule.pdf",
                        },
                        {
                            "allowed_hosts": ["feeds.example.test"],
                            "document_urls": ["https://feeds.example.test/rule.pdf"],
                        },
                    ),
                    (
                        "MANUAL_IMPORT",
                        {
                            "allowed_hosts": ["feeds.example.test"],
                            "url_import_enabled": False,
                            "file_import_enabled": False,
                            "allowed_file_types": ["PDF"],
                        },
                        {
                            "allowed_hosts": ["feeds.example.test"],
                            "url_import_enabled": True,
                            "file_import_enabled": True,
                            "allowed_file_types": ["HTML", "PDF", "ZIP"],
                        },
                    ),
                )
                supersedes_id = config_id
                for version_number, (kind, invalid, valid) in enumerate(
                    connector_cases,
                    start=2,
                ):
                    case_definition_id = await connection.scalar(
                        text(
                            "SELECT id FROM connector_definition "
                            "WHERE connector_type=:kind AND definition_version='1.0.0'"
                        ),
                        {"kind": kind},
                    )
                    assert isinstance(case_definition_id, UUID)
                    await _expect_db_rejection(
                        connection,
                        config_call,
                        {
                            "source_id": source_id,
                            "config_id": uuid7(),
                            "definition_id": case_definition_id,
                            "version_number": version_number,
                            "config_document": json.dumps(invalid),
                            "supersedes_id": supersedes_id,
                            "actor_id": policy_submitter,
                            "reason": f"reject malformed {kind} contract",
                            "request_id": f"round15-invalid-{kind}",
                            "audit_id": uuid7(),
                            "now": now,
                        },
                        label=f"malformed {kind} connector configuration",
                    )
                    next_config_id = uuid7()
                    await connection.execute(
                        text(config_call),
                        {
                            "source_id": source_id,
                            "config_id": next_config_id,
                            "definition_id": case_definition_id,
                            "version_number": version_number,
                            "config_document": json.dumps(valid),
                            "supersedes_id": supersedes_id,
                            "actor_id": policy_submitter,
                            "reason": f"persist valid {kind} contract",
                            "request_id": f"round15-valid-{kind}",
                            "audit_id": uuid7(),
                            "now": now,
                        },
                    )
                    supersedes_id = next_config_id

                upgraded_at = now + timedelta(seconds=1)
                upgraded_policy_id = uuid7()
                upgraded_policy = _policy_document(upgraded_at)
                upgraded_policy["policy_version"] = "round15-boundary-upgraded"
                upgraded_policy["reason"] = "upgrade policy and invalidate old connector evidence"
                upgraded_policy["valid_from"] = upgraded_at.isoformat()
                upgraded_policy["valid_until"] = (upgraded_at + timedelta(days=30)).isoformat()
                for review_key in (
                    "robots_review",
                    "terms_review",
                    "copyright_review",
                ):
                    review = dict(upgraded_policy[review_key])  # type: ignore[arg-type]
                    review["checked_at"] = upgraded_at.isoformat()
                    upgraded_policy[review_key] = review
                await connection.execute(
                    text(policy_call),
                    {
                        "source_id": source_id,
                        "policy_id": upgraded_policy_id,
                        "policy_version": "round15-boundary-upgraded",
                        "document": json.dumps(upgraded_policy),
                        "valid_from": upgraded_at,
                        "valid_until": upgraded_at + timedelta(days=30),
                        "actor_id": policy_submitter,
                        "reason": "upgrade policy and invalidate old connector evidence",
                        "request_id": "round15-upgraded-policy",
                        "audit_id": uuid7(),
                        "now": upgraded_at,
                    },
                )
                await connection.execute(
                    text(
                        """
                        SELECT decide_source_policy_version(
                          :source_id,:policy_id,:decision_id,'APPROVED',:actor_id,
                          'approve upgraded policy',:request_id,:audit_id,:now
                        )
                        """
                    ),
                    {
                        "source_id": source_id,
                        "policy_id": upgraded_policy_id,
                        "decision_id": uuid7(),
                        "actor_id": compliance_approver,
                        "request_id": "round15-upgraded-policy-approved",
                        "audit_id": uuid7(),
                        "now": upgraded_at,
                    },
                )
                await _expect_db_rejection(
                    connection,
                    """
                    SELECT start_source_trial_run(
                      :source_id,:trial_id,'FIXTURE_REPLAY',:policy_id,:config_id,
                      :decision_id,:actor_id,'old config must not cross policy versions',
                      :request_id,:event_id,:audit_id,:now
                    )
                    """,
                    {
                        "source_id": source_id,
                        "trial_id": uuid7(),
                        "policy_id": upgraded_policy_id,
                        "config_id": supersedes_id,
                        "decision_id": uuid7(),
                        "actor_id": trial_requester,
                        "request_id": "round15-old-config-after-policy-upgrade",
                        "event_id": uuid7(),
                        "audit_id": uuid7(),
                        "now": upgraded_at,
                    },
                    label="an old connector config after policy upgrade",
                )
                latest_config_matches = await connection.scalar(
                    text(
                        """
                        SELECT EXISTS(
                          SELECT 1 FROM source s
                          JOIN source_policy_version p
                            ON p.id=s.current_policy_version_id
                          JOIN connector_config_version c
                            ON c.id=s.current_connector_config_version_id
                           AND c.policy_version_id=p.id
                          WHERE s.id=:source_id
                        )
                        """
                    ),
                    {"source_id": source_id},
                )
                assert latest_config_matches is False

                rejected_at = upgraded_at + timedelta(seconds=1)
                await connection.execute(
                    text(
                        """
                        SELECT decide_source_policy_version(
                          :source_id,:policy_id,:decision_id,'REJECTED',:actor_id,
                          'revoke compliance after new evidence',:request_id,:audit_id,:now
                        )
                        """
                    ),
                    {
                        "source_id": source_id,
                        "policy_id": upgraded_policy_id,
                        "decision_id": uuid7(),
                        "actor_id": compliance_approver,
                        "request_id": "round15-upgraded-policy-rejected",
                        "audit_id": uuid7(),
                        "now": rejected_at,
                    },
                )
                compliance_current = await connection.scalar(
                    text("SELECT source_v2_policy_compliance_approved(:source_id,:policy_id,:now)"),
                    {
                        "source_id": source_id,
                        "policy_id": upgraded_policy_id,
                        "now": rejected_at,
                    },
                )
                assert compliance_current is False
                rss_definition_id = await connection.scalar(
                    text("SELECT id FROM connector_definition WHERE connector_type='RSS_ATOM'")
                )
                assert isinstance(rss_definition_id, UUID)
                await _expect_db_rejection(
                    connection,
                    config_call,
                    {
                        "source_id": source_id,
                        "config_id": uuid7(),
                        "definition_id": rss_definition_id,
                        "version_number": 7,
                        "config_document": json.dumps(
                            {
                                "allowed_hosts": ["feeds.example.test"],
                                "feed_url": "https://feeds.example.test/rss.xml",
                            }
                        ),
                        "supersedes_id": supersedes_id,
                        "actor_id": policy_submitter,
                        "reason": "latest rejected compliance must deny config",
                        "request_id": "round15-rejected-policy-config",
                        "audit_id": uuid7(),
                        "now": rejected_at,
                    },
                    label="connector persistence after the latest compliance rejection",
                )

                # Restore current evidence and exercise ACTIVE -> PAUSED -> explicit
                # isolated TRIAL -> RETIRED without deleting any evidence.
                restored_at = rejected_at + timedelta(seconds=1)
                await connection.execute(
                    text(
                        """
                        SELECT decide_source_policy_version(
                          :source_id,:policy_id,:decision_id,'APPROVED',:actor_id,
                          'approve restored compliance evidence',:request_id,
                          :audit_id,:now
                        )
                        """
                    ),
                    {
                        "source_id": source_id,
                        "policy_id": upgraded_policy_id,
                        "decision_id": uuid7(),
                        "actor_id": compliance_approver,
                        "request_id": "round15-restored-compliance",
                        "audit_id": uuid7(),
                        "now": restored_at,
                    },
                )
                current_config_id = uuid7()
                await connection.execute(
                    text(config_call),
                    {
                        "source_id": source_id,
                        "config_id": current_config_id,
                        "definition_id": rss_definition_id,
                        "version_number": 7,
                        "config_document": json.dumps(
                            {
                                "allowed_hosts": ["feeds.example.test"],
                                "feed_url": "https://feeds.example.test/rss.xml",
                            }
                        ),
                        "supersedes_id": supersedes_id,
                        "actor_id": policy_submitter,
                        "reason": "bind connector to restored policy",
                        "request_id": "round15-restored-config",
                        "audit_id": uuid7(),
                        "now": restored_at,
                    },
                )
                live_trial_id = uuid7()
                live_operator = uuid7()
                await connection.execute(
                    text(
                        """
                        SELECT start_source_trial_run(
                          :source_id,:trial_id,'LIVE_TRIAL',:policy_id,:config_id,
                          :decision_id,:actor_id,'controlled live trial replay',
                          :request_id,:event_id,:audit_id,:now
                        )
                        """
                    ),
                    {
                        "source_id": source_id,
                        "trial_id": live_trial_id,
                        "policy_id": upgraded_policy_id,
                        "config_id": current_config_id,
                        "decision_id": uuid7(),
                        "actor_id": live_operator,
                        "request_id": "round15-live-trial",
                        "event_id": uuid7(),
                        "audit_id": uuid7(),
                        "now": restored_at,
                    },
                )
                await connection.execute(text("RESET ROLE"))
                live_raw_id, live_capture_id = uuid7(), uuid7()
                live_hash = "4" * 64
                await connection.execute(
                    text(
                        """
                        INSERT INTO raw_object(
                          id,sha256,object_key,byte_size,declared_mime,detected_mime,
                          scan_status,storage_etag,created_at
                        ) VALUES (
                          :id,:sha256,:object_key,20,'text/html','text/html',
                          'CLEAN',NULL,:now
                        )
                        """
                    ),
                    {
                        "id": live_raw_id,
                        "sha256": live_hash,
                        "object_key": f"sha256/44/{live_hash}",
                        "now": restored_at,
                    },
                )
                await connection.execute(
                    text(
                        """
                        INSERT INTO raw_object_security_fact(
                          id,raw_object_id,status,detected_mime,rule_version,
                          reason_code,created_at
                        ) VALUES (
                          :security_id,:id,'CLEAN','text/html','round15-live',NULL,:now
                        )
                        """
                    ),
                    {
                        "id": live_raw_id,
                        "security_id": uuid7(),
                        "now": restored_at,
                    },
                )
                await connection.execute(text("SET LOCAL ROLE srbg_api_role"))
                await connection.execute(
                    text(
                        """
                        SELECT append_source_trial_raw_capture(
                          :capture_id,:raw_id,:source_id,:trial_id,'TRIAL',
                          :url,:url,CAST('[]' AS jsonb),200,NULL,NULL,:hash,:now
                        )
                        """
                    ),
                    {
                        "capture_id": live_capture_id,
                        "raw_id": live_raw_id,
                        "source_id": source_id,
                        "trial_id": live_trial_id,
                        "url": "https://feeds.example.test/live-document",
                        "hash": "5" * 64,
                        "now": restored_at,
                    },
                )
                await connection.execute(text("RESET ROLE"))
                live_document_id, live_version_id = uuid7(), uuid7()
                await connection.execute(
                    text(
                        """
                        INSERT INTO document(
                          id,source_id,canonical_url,document_kind,
                          first_discovered_at,current_version_id,admission_fixture
                        ) VALUES (
                          :document_id,:source_id,:url,'HTML',:now,NULL,false
                        )
                        """
                    ),
                    {
                        "document_id": live_document_id,
                        "source_id": source_id,
                        "url": "https://feeds.example.test/live-document",
                        "now": restored_at,
                    },
                )
                await connection.execute(
                    text(
                        """
                        INSERT INTO document_version(
                          id,document_id,raw_object_id,version_number,content_hash,
                          original_filename,title,acquired_at,execution_domain,
                          raw_object_capture_id
                        ) VALUES (
                          :version_id,:document_id,:raw_id,1,:hash,'live.html',
                          'Live boundary',:now,'TRIAL',:capture_id
                        )
                        """
                    ),
                    {
                        "version_id": live_version_id,
                        "document_id": live_document_id,
                        "raw_id": live_raw_id,
                        "hash": live_hash,
                        "now": restored_at,
                        "capture_id": live_capture_id,
                    },
                )
                await connection.execute(
                    text(
                        """
                        INSERT INTO document_version_state_event(
                          id,document_version_id,state,reason_code,actor_type,created_at
                        ) VALUES (
                          :event_id,:version_id,'READY',NULL,'WORKER',:now
                        )
                        """
                    ),
                    {
                        "event_id": uuid7(),
                        "version_id": live_version_id,
                        "now": restored_at,
                    },
                )
                await connection.execute(
                    text(
                        """
                        UPDATE document SET current_version_id=:version_id
                         WHERE id=:document_id
                        """
                    ),
                    {
                        "document_id": live_document_id,
                        "version_id": live_version_id,
                    },
                )
                await connection.execute(text("SET LOCAL ROLE srbg_api_role"))
                await connection.execute(
                    text(
                        """
                        SELECT complete_source_trial_run_with_audit(
                          :trial_id,'SUCCEEDED',CAST(:quality AS jsonb),
                          :namespace,:actor_id,:reason,:request_id,:audit_id,:now
                        )
                        """
                    ),
                    {
                        "trial_id": live_trial_id,
                        "quality": json.dumps(
                            {
                                "raw_count": 1,
                                "ready_count": 1,
                                "parse_failed_count": 0,
                                "security_failed_count": 0,
                                "rejected_raw_attempt_count": 0,
                                "ready_ratio_bps": 10000,
                            }
                        ),
                        "namespace": f"trial/{live_trial_id}/raw/",
                        "actor_id": live_operator,
                        "reason": "complete independently authorized live trial",
                        "request_id": "round15-live-trial-completion",
                        "audit_id": uuid7(),
                        "now": restored_at,
                    },
                )
                production_approver = uuid7()
                active_at = restored_at + timedelta(seconds=1)
                await connection.execute(
                    text(
                        """
                        SELECT approve_source_production(
                          :source_id,:policy_id,:config_id,:trial_id,:decision_id,
                          :actor_id,'independent production approval',:request_id,
                          :event_id,:audit_id,:now
                        )
                        """
                    ),
                    {
                        "source_id": source_id,
                        "policy_id": upgraded_policy_id,
                        "config_id": current_config_id,
                        "trial_id": live_trial_id,
                        "decision_id": uuid7(),
                        "actor_id": production_approver,
                        "request_id": "round15-production-approval",
                        "event_id": uuid7(),
                        "audit_id": uuid7(),
                        "now": active_at,
                    },
                )
                assert (
                    await connection.scalar(
                        text("SELECT lifecycle_state FROM source WHERE id=:id"),
                        {"id": source_id},
                    )
                    == "ACTIVE"
                )
                history_before = (
                    (
                        await connection.execute(
                            text(
                                """
                            SELECT
                              (SELECT count(*) FROM raw_object_capture
                                WHERE source_id=:source_id) captures,
                              (SELECT count(*) FROM document
                                WHERE source_id=:source_id) documents,
                              (SELECT count(*) FROM document_version version
                                JOIN document document_row
                                  ON document_row.id=version.document_id
                               WHERE document_row.source_id=:source_id) versions,
                              (SELECT count(*) FROM source_lifecycle_event
                                WHERE source_id=:source_id) lifecycle_events,
                              (SELECT count(*) FROM audit_log) audit_events,
                              (SELECT count(*) FROM fetch_run) fetch_runs
                            """
                            ),
                            {"source_id": source_id},
                        )
                    )
                    .mappings()
                    .one()
                )
                paused_at = active_at + timedelta(seconds=1)
                await connection.execute(
                    text(
                        """
                        SELECT apply_source_lifecycle_command(
                          :source_id,'PAUSE',:actor_id,
                          'pause automated production collection',:request_id,
                          :event_id,:now
                        )
                        """
                    ),
                    {
                        "source_id": source_id,
                        "actor_id": production_approver,
                        "request_id": "round15-pause",
                        "event_id": uuid7(),
                        "now": paused_at,
                    },
                )
                assert (
                    await connection.scalar(
                        text("SELECT lifecycle_state='ACTIVE' FROM source WHERE id=:id"),
                        {"id": source_id},
                    )
                    is False
                )
                paused_attempt_id = uuid7()
                await connection.execute(
                    text(
                        """
                        SELECT append_source_trial_rejected_raw_attempt(
                          :attempt_id,:source_id,:trial_id,:raw_id,:content_sha256,
                          :object_key,:url,'MIME_MISMATCH',:actor_id,:request_id,:now
                        )
                        """
                    ),
                    {
                        "attempt_id": paused_attempt_id,
                        "source_id": source_id,
                        "trial_id": trial_id,
                        "raw_id": ready_raw_id,
                        "content_sha256": "1" * 64,
                        "object_key": f"sha256/11/{'1' * 64}",
                        "url": "https://feeds.example.test/paused-in-flight",
                        "actor_id": trial_requester,
                        "request_id": "round15-paused-in-flight-rejection",
                        "now": paused_at,
                    },
                )
                assert (
                    await connection.scalar(
                        text(
                            "SELECT arrived_after_close FROM "
                            "source_trial_rejected_raw_attempt WHERE id=:id"
                        ),
                        {"id": paused_attempt_id},
                    )
                    is True
                )
                retrial_id = uuid7()
                await connection.execute(
                    text(
                        """
                        SELECT start_source_trial_run(
                          :source_id,:trial_id,'FIXTURE_REPLAY',:policy_id,:config_id,
                          :decision_id,:actor_id,'controlled replay while paused',
                          :request_id,:event_id,:audit_id,:now
                        )
                        """
                    ),
                    {
                        "source_id": source_id,
                        "trial_id": retrial_id,
                        "policy_id": upgraded_policy_id,
                        "config_id": current_config_id,
                        "decision_id": uuid7(),
                        "actor_id": uuid7(),
                        "request_id": "round15-paused-retrial",
                        "event_id": uuid7(),
                        "audit_id": uuid7(),
                        "now": paused_at + timedelta(seconds=1),
                    },
                )
                assert (
                    await connection.scalar(
                        text("SELECT lifecycle_state FROM source WHERE id=:id"),
                        {"id": source_id},
                    )
                    == "TRIAL"
                )
                retired_at = paused_at + timedelta(seconds=2)
                await connection.execute(
                    text(
                        """
                        SELECT apply_source_lifecycle_command(
                          :source_id,'RETIRE',:actor_id,
                          'retire source while preserving evidence',:request_id,
                          :event_id,:now
                        )
                        """
                    ),
                    {
                        "source_id": source_id,
                        "actor_id": production_approver,
                        "request_id": "round15-retire",
                        "event_id": uuid7(),
                        "now": retired_at,
                    },
                )
                trial_count = await connection.scalar(
                    text("SELECT count(*) FROM source_trial_run WHERE source_id=:id"),
                    {"id": source_id},
                )
                await _expect_db_rejection(
                    connection,
                    """
                    SELECT start_source_trial_run(
                      :source_id,:trial_id,'FIXTURE_REPLAY',:policy_id,:config_id,
                      :decision_id,:actor_id,'retired source replay',:request_id,
                      :event_id,:audit_id,:now
                    )
                    """,
                    {
                        "source_id": source_id,
                        "trial_id": uuid7(),
                        "policy_id": upgraded_policy_id,
                        "config_id": current_config_id,
                        "decision_id": uuid7(),
                        "actor_id": uuid7(),
                        "request_id": "round15-retired-trial-denied",
                        "event_id": uuid7(),
                        "audit_id": uuid7(),
                        "now": retired_at + timedelta(seconds=1),
                    },
                    label="a new trial for a retired source",
                )
                assert (
                    await connection.scalar(
                        text("SELECT count(*) FROM source_trial_run WHERE source_id=:id"),
                        {"id": source_id},
                    )
                    == trial_count
                )
                retired_attempt_id = uuid7()
                await connection.execute(
                    text(
                        """
                        SELECT append_source_trial_rejected_raw_attempt(
                          :attempt_id,:source_id,:trial_id,NULL,:content_sha256,
                          :object_key,:url,'MIME_MISMATCH',:actor_id,:request_id,:now
                        )
                        """
                    ),
                    {
                        "attempt_id": retired_attempt_id,
                        "source_id": source_id,
                        "trial_id": retrial_id,
                        "content_sha256": "7" * 64,
                        "object_key": f"sha256/77/{'7' * 64}",
                        "url": "https://feeds.example.test/retired-in-flight",
                        "actor_id": trial_requester,
                        "request_id": "round15-retired-in-flight-rejection",
                        "now": retired_at + timedelta(microseconds=1),
                    },
                )
                assert (
                    await connection.scalar(
                        text(
                            "SELECT arrived_after_close FROM "
                            "source_trial_rejected_raw_attempt WHERE id=:id"
                        ),
                        {"id": retired_attempt_id},
                    )
                    is True
                )

                # A clean upload authorized before retirement keeps its raw and
                # capture evidence, but the closed-trial capture can never be
                # promoted to READY or selected as the current document version.
                await connection.execute(text("RESET ROLE"))
                late_raw_id, late_capture_id = uuid7(), uuid7()
                late_document_id, late_version_id = uuid7(), uuid7()
                late_hash = "6" * 64
                await connection.execute(
                    text(
                        """
                        INSERT INTO raw_object(
                          id,sha256,object_key,byte_size,declared_mime,detected_mime,
                          scan_status,storage_etag,created_at
                        ) VALUES (
                          :id,:sha256,:object_key,20,'text/html','text/html',
                          'CLEAN',NULL,:now
                        )
                        """
                    ),
                    {
                        "id": late_raw_id,
                        "sha256": late_hash,
                        "object_key": f"sha256/66/{late_hash}",
                        "now": retired_at,
                    },
                )
                await connection.execute(
                    text(
                        """
                        INSERT INTO raw_object_security_fact(
                          id,raw_object_id,status,detected_mime,rule_version,
                          reason_code,created_at
                        ) VALUES (
                          :id,:raw_id,'CLEAN','text/html','round15-late-clean',NULL,:now
                        )
                        """
                    ),
                    {"id": uuid7(), "raw_id": late_raw_id, "now": retired_at},
                )
                await connection.execute(text("SET LOCAL ROLE srbg_api_role"))
                await connection.execute(
                    text(
                        """
                        SELECT append_source_trial_raw_capture(
                          :capture_id,:raw_id,:source_id,:trial_id,'FIXTURE',
                          :url,:url,CAST('[]' AS jsonb),200,NULL,NULL,:hash,:now
                        )
                        """
                    ),
                    {
                        "capture_id": late_capture_id,
                        "raw_id": late_raw_id,
                        "source_id": source_id,
                        "trial_id": retrial_id,
                        "url": "https://feeds.example.test/retired-clean-in-flight",
                        "hash": late_hash,
                        "now": retired_at + timedelta(microseconds=2),
                    },
                )
                assert (
                    await connection.scalar(
                        text("SELECT arrived_after_close FROM raw_object_capture WHERE id=:id"),
                        {"id": late_capture_id},
                    )
                    is True
                )
                await connection.execute(text("RESET ROLE"))
                await connection.execute(
                    text(
                        """
                        INSERT INTO document(
                          id,source_id,canonical_url,document_kind,
                          first_discovered_at,current_version_id,admission_fixture
                        ) VALUES (:id,:source_id,:url,'HTML',:now,NULL,true)
                        """
                    ),
                    {
                        "id": late_document_id,
                        "source_id": source_id,
                        "url": "https://feeds.example.test/retired-clean-in-flight",
                        "now": retired_at,
                    },
                )
                await connection.execute(
                    text(
                        """
                        INSERT INTO document_version(
                          id,document_id,raw_object_id,version_number,content_hash,
                          original_filename,title,acquired_at,execution_domain,
                          raw_object_capture_id
                        ) VALUES (
                          :id,:document_id,:raw_id,1,:hash,'late.html','Late evidence',
                          :now,'FIXTURE',:capture_id
                        )
                        """
                    ),
                    {
                        "id": late_version_id,
                        "document_id": late_document_id,
                        "raw_id": late_raw_id,
                        "hash": late_hash,
                        "now": retired_at,
                        "capture_id": late_capture_id,
                    },
                )
                for state, reason in (
                    ("RECEIVED", None),
                    ("SECURITY_PASSED", None),
                    ("FAILED", "TRIAL_CLOSED_DURING_UPLOAD"),
                ):
                    await connection.execute(
                        text(
                            """
                            INSERT INTO document_version_state_event(
                              id,document_version_id,state,reason_code,actor_type,created_at
                            ) VALUES (:id,:version_id,:state,:reason,'SYSTEM',:now)
                            """
                        ),
                        {
                            "id": uuid7(),
                            "version_id": late_version_id,
                            "state": state,
                            "reason": reason,
                            "now": retired_at + timedelta(microseconds=3),
                        },
                    )
                await _expect_db_rejection(
                    connection,
                    """
                    INSERT INTO document_version_state_event(
                      id,document_version_id,state,reason_code,actor_type,created_at
                    ) VALUES (:id,:version_id,'READY',NULL,'SYSTEM',:now)
                    """,
                    {
                        "id": uuid7(),
                        "version_id": late_version_id,
                        "now": retired_at + timedelta(microseconds=4),
                    },
                    label="a READY state for an upload arriving after trial closure",
                )
                await _expect_db_rejection(
                    connection,
                    "UPDATE document SET current_version_id=:version_id WHERE id=:id",
                    {"version_id": late_version_id, "id": late_document_id},
                    label="a current version backed by a closed-trial capture",
                )
                history_after = (
                    (
                        await connection.execute(
                            text(
                                """
                            SELECT
                              (SELECT count(*) FROM raw_object_capture
                                WHERE source_id=:source_id) captures,
                              (SELECT count(*) FROM document
                                WHERE source_id=:source_id) documents,
                              (SELECT count(*) FROM document_version version
                                JOIN document document_row
                                  ON document_row.id=version.document_id
                               WHERE document_row.source_id=:source_id) versions,
                              (SELECT count(*) FROM source_lifecycle_event
                                WHERE source_id=:source_id) lifecycle_events,
                              (SELECT count(*) FROM audit_log) audit_events,
                              (SELECT count(*) FROM fetch_run) fetch_runs
                            """
                            ),
                            {"source_id": source_id},
                        )
                    )
                    .mappings()
                    .one()
                )
                assert history_after["captures"] == history_before["captures"] + 1
                assert history_after["documents"] == history_before["documents"] + 1
                assert history_after["versions"] == history_before["versions"] + 1
                assert history_after["fetch_runs"] == history_before["fetch_runs"]
                assert history_after["lifecycle_events"] > history_before["lifecycle_events"]
                assert history_after["audit_events"] > history_before["audit_events"]
            finally:
                await transaction.rollback()
    finally:
        await engine.dispose()


async def _legacy_snapshot(database_url: str) -> dict[str, tuple[str, bool]]:
    engine = create_async_engine(database_url)
    try:
        async with engine.connect() as connection:
            rows = (
                await connection.execute(text("SELECT id,state,enabled FROM source ORDER BY id"))
            ).mappings()
            return {str(row["id"]): (str(row["state"]), bool(row["enabled"])) for row in rows}
    finally:
        await engine.dispose()


async def _seed_preexisting_negative_history(database_url: str) -> dict[str, UUID]:
    """Create a Round-14 current/attachment that a later CLEAN cannot rehabilitate."""
    engine = create_async_engine(database_url)
    try:
        async with engine.begin() as connection:
            source_id = await connection.scalar(text("SELECT id FROM source ORDER BY id LIMIT 1"))
            assert isinstance(source_id, UUID)
            now = datetime.now(UTC)
            document_id, safe_version_id, unsafe_version_id = uuid7(), uuid7(), uuid7()
            safe_raw_id, unsafe_raw_id, attachment_id = uuid7(), uuid7(), uuid7()
            safe_hash, unsafe_hash = "8" * 64, "9" * 64
            for raw_id, content_hash in (
                (safe_raw_id, safe_hash),
                (unsafe_raw_id, unsafe_hash),
            ):
                await connection.execute(
                    text(
                        """
                        INSERT INTO raw_object(
                          id,sha256,object_key,byte_size,declared_mime,detected_mime,
                          scan_status,storage_etag,created_at
                        ) VALUES (
                          :id,:hash,:object_key,20,'text/html','text/html','CLEAN',
                          NULL,:now
                        )
                        """
                    ),
                    {
                        "id": raw_id,
                        "hash": content_hash,
                        "object_key": f"sha256/{content_hash[:2]}/{content_hash}",
                        "now": now,
                    },
                )
            await connection.execute(
                text(
                    """
                    INSERT INTO raw_object_security_fact(
                      id,raw_object_id,status,detected_mime,rule_version,
                      reason_code,created_at
                    ) VALUES
                      (:safe_id,:safe_raw,'CLEAN','text/html','round15-pre-safe',NULL,:now),
                      (:negative_id,:unsafe_raw,'QUARANTINED','text/html',
                       'round15-pre-negative','MALWARE_FOUND',:negative_at),
                      (:later_clean_id,:unsafe_raw,'CLEAN','text/html',
                       'round15-pre-later-clean',NULL,:clean_at)
                    """
                ),
                {
                    "safe_id": uuid7(),
                    "safe_raw": safe_raw_id,
                    "negative_id": uuid7(),
                    "unsafe_raw": unsafe_raw_id,
                    "later_clean_id": uuid7(),
                    "now": now,
                    "negative_at": now + timedelta(microseconds=1),
                    "clean_at": now + timedelta(microseconds=2),
                },
            )
            await connection.execute(
                text(
                    """
                    INSERT INTO document(
                      id,source_id,canonical_url,document_kind,first_discovered_at,
                      current_version_id,admission_fixture
                    ) VALUES (:id,:source_id,:url,'HTML',:now,NULL,false)
                    """
                ),
                {
                    "id": document_id,
                    "source_id": source_id,
                    "url": "https://round15-preexisting.example.test/evidence",
                    "now": now,
                },
            )
            for number, version_id, raw_id, content_hash in (
                (1, safe_version_id, safe_raw_id, safe_hash),
                (2, unsafe_version_id, unsafe_raw_id, unsafe_hash),
            ):
                await connection.execute(
                    text(
                        """
                        INSERT INTO document_version(
                          id,document_id,raw_object_id,version_number,content_hash,
                          original_filename,title,acquired_at
                        ) VALUES (
                          :id,:document_id,:raw_id,:number,:hash,:filename,
                          'Preexisting evidence',:now
                        )
                        """
                    ),
                    {
                        "id": version_id,
                        "document_id": document_id,
                        "raw_id": raw_id,
                        "number": number,
                        "hash": content_hash,
                        "filename": f"preexisting-{number}.html",
                        "now": now,
                    },
                )
                await connection.execute(
                    text(
                        """
                        INSERT INTO document_version_state_event(
                          id,document_version_id,state,reason_code,actor_type,created_at
                        ) VALUES (:id,:version_id,'READY',NULL,'SYSTEM',:now)
                        """
                    ),
                    {"id": uuid7(), "version_id": version_id, "now": now},
                )
            await connection.execute(
                text("UPDATE document SET current_version_id=:version_id WHERE id=:id"),
                {"version_id": unsafe_version_id, "id": document_id},
            )
            await connection.execute(
                text(
                    """
                    INSERT INTO document_attachment(
                      id,document_version_id,raw_object_id,filename,role,
                      security_status,created_at
                    ) VALUES (
                      :id,:version_id,:raw_id,'unsafe.html','SOURCE_ATTACHMENT',
                      'CLEAN',:now
                    )
                    """
                ),
                {
                    "id": attachment_id,
                    "version_id": unsafe_version_id,
                    "raw_id": unsafe_raw_id,
                    "now": now,
                },
            )
            return {
                "document_id": document_id,
                "safe_version_id": safe_version_id,
                "unsafe_raw_id": unsafe_raw_id,
                "attachment_id": attachment_id,
            }
    finally:
        await engine.dispose()


async def _verify_upgrade(
    database_url: str,
    legacy: dict[str, tuple[str, bool]],
    preexisting_negative: dict[str, UUID],
) -> None:
    engine = create_async_engine(database_url)
    try:
        async with engine.connect() as connection:
            rows = (
                (
                    await connection.execute(
                        text(
                            """
                        SELECT s.id,s.lifecycle_state,s.trial_kind,s.enabled,
                               m.legacy_state,m.legacy_enabled,m.mapping_reason,
                               e.migration_rule_version,e.legacy_snapshot
                          FROM source s
                          JOIN source_migration_snapshot m ON m.source_id=s.id
                          JOIN source_lifecycle_event e ON e.source_id=s.id
                           AND e.migration_rule_version='round15-lifecycle-v1'
                         ORDER BY s.id
                        """
                        )
                    )
                )
                .mappings()
                .all()
            )
            assert len(rows) == len(legacy)
            for row in rows:
                legacy_state, legacy_enabled = legacy[str(row["id"])]
                assert row["legacy_state"] == legacy_state
                assert bool(row["legacy_enabled"]) is legacy_enabled
                assert row["lifecycle_state"] != "ACTIVE"
                assert row["enabled"] is False
                assert row["legacy_snapshot"]["state"] == legacy_state
                if legacy_state in {"FIXTURE_TEST", "APPROVED"}:
                    assert row["lifecycle_state"] == "TRIAL"
                    assert row["trial_kind"] == "FIXTURE_REPLAY"
            definitions = (
                (
                    await connection.execute(
                        text(
                            """
                        SELECT connector_type,schema_sha256,definition_version
                          FROM connector_definition ORDER BY connector_type
                        """
                        )
                    )
                )
                .mappings()
                .all()
            )
            assert len(definitions) == 6
            assert all(row["definition_version"] == "1.0.0" for row in definitions)
            assert all(re.fullmatch(r"[0-9a-f]{64}", row["schema_sha256"]) for row in definitions)
            replay_signature = (
                "record_source_fixture_replay_result("
                "uuid,uuid,uuid,text,text,integer,integer,integer,uuid,timestamp with time zone)"
            )
            assert await connection.scalar(
                text("SELECT has_function_privilege('srbg_api_role',:signature,'EXECUTE')"),
                {"signature": replay_signature},
            )
            assert await connection.scalar(
                text("SELECT has_function_privilege('srbg_worker_role',:signature,'EXECUTE')"),
                {"signature": replay_signature},
            )
            assert not await connection.scalar(
                text("SELECT has_function_privilege('srbg_model_role',:signature,'EXECUTE')"),
                {"signature": replay_signature},
            )
            assert await connection.scalar(
                text(
                    "SELECT has_column_privilege("
                    "'srbg_api_role','connector_config_version','credential_ref','SELECT')"
                )
            )
            for restricted_role in (
                "srbg_runtime",
                "srbg_worker_role",
                "srbg_publication_writer",
            ):
                assert not await connection.scalar(
                    text(
                        "SELECT has_column_privilege("
                        ":role,'connector_config_version','credential_ref','SELECT')"
                    ),
                    {"role": restricted_role},
                )
            assert (
                await connection.scalar(
                    text("SELECT current_version_id FROM document WHERE id=:id"),
                    {"id": preexisting_negative["document_id"]},
                )
                == preexisting_negative["safe_version_id"]
            )
            assert (
                await connection.scalar(
                    text("SELECT security_status FROM document_attachment WHERE id=:id"),
                    {"id": preexisting_negative["attachment_id"]},
                )
                == "QUARANTINED"
            )
            assert (
                await connection.scalar(
                    text(
                        """
                    SELECT EXISTS(
                      SELECT 1 FROM raw_object_security_fact fact
                       WHERE fact.raw_object_id=:raw_id
                         AND fact.status='QUARANTINED'
                    ) AND EXISTS(
                      SELECT 1 FROM raw_object_security_fact fact
                       WHERE fact.raw_object_id=:raw_id
                         AND fact.status='CLEAN'
                    )
                    """
                    ),
                    {"raw_id": preexisting_negative["unsafe_raw_id"]},
                )
                is True
            )

        async with engine.begin() as connection:
            await connection.execute(text("SET LOCAL ROLE srbg_api_role"))
            await _expect_db_rejection(
                connection,
                """
                INSERT INTO document_version(
                  id,document_id,raw_object_id,version_number,content_hash,
                  original_filename,title,acquired_at,execution_domain,
                  raw_object_capture_id
                ) VALUES (
                  :id,:document_id,:raw_id,999,:hash,'forged.html',
                  'Forged production domain',now(),'PRODUCTION',NULL
                )
                """,
                {
                    "id": uuid7(),
                    "document_id": preexisting_negative["document_id"],
                    "raw_id": preexisting_negative["unsafe_raw_id"],
                    "hash": "e" * 64,
                },
                label="API role forging a PRODUCTION document version",
            )
            attempt_id = uuid7()
            attempt_hash = "b" * 64
            nested = await connection.begin_nested()
            try:
                returned_id = await connection.scalar(
                    text(
                        """
                        SELECT append_document_attachment_attempt(
                          :attempt_id,:version_id,:content_sha256,:object_key,
                          NULL,12,'text/html','text/html',:filename_sha256,
                          :path_sha256,:url_sha256,'RECEIVED',NULL,now()
                        )
                        """
                    ),
                    {
                        "attempt_id": attempt_id,
                        "version_id": preexisting_negative["safe_version_id"],
                        "content_sha256": attempt_hash,
                        "object_key": f"sha256/bb/{attempt_hash}",
                        "filename_sha256": "c" * 64,
                        "path_sha256": "d" * 64,
                        "url_sha256": "e" * 64,
                    },
                )
                assert returned_id == attempt_id
                assert (
                    await connection.scalar(
                        text(
                            "SELECT outcome FROM document_attachment_attempt "
                            "WHERE id=:attempt_id"
                        ),
                        {"attempt_id": attempt_id},
                    )
                    == "RECEIVED"
                )
            finally:
                await nested.rollback()
            await _expect_db_rejection(
                connection,
                """
                INSERT INTO document_attachment_attempt(
                  id,document_version_id,content_sha256,object_key,byte_size,
                  declared_mime,detected_mime,filename_sha256,
                  normalized_path_sha256,canonical_url_sha256,outcome,occurred_at
                ) VALUES (
                  :attempt_id,:version_id,:content_sha256,:object_key,12,
                  'text/html','text/html',:filename_sha256,:path_sha256,
                  :url_sha256,'RECEIVED',now()
                )
                """,
                {
                    "attempt_id": uuid7(),
                    "version_id": preexisting_negative["safe_version_id"],
                    "content_sha256": attempt_hash,
                    "object_key": f"sha256/bb/{attempt_hash}",
                    "filename_sha256": "c" * 64,
                    "path_sha256": "d" * 64,
                    "url_sha256": "e" * 64,
                },
                label="API role directly inserting attachment attempt evidence",
            )
            await _expect_db_rejection(
                connection,
                """
                        INSERT INTO source_authority_assessment(
                          id,source_id,authority_level,rule_version,reason_codes,
                          evidence_refs,assessed_by,assessed_at
                        ) SELECT gen_random_uuid(),id,'A1','forged',ARRAY['FORGED'],
                                 ARRAY[]::text[],gen_random_uuid(),now()
                            FROM source LIMIT 1
                """,
                {},
                label="API role directly inserting an assessment",
            )
            await _expect_db_rejection(
                connection,
                """
                INSERT INTO source_fixture_replay_result(
                  trial_run_id,source_id,connector_config_version_id,status,
                  reason_code,raw_capture_count,document_count,transport_call_count,
                  evaluated_by,created_at
                ) VALUES (
                  gen_random_uuid(),gen_random_uuid(),gen_random_uuid(),'PASSED',
                  'FORGED',1,1,0,gen_random_uuid(),now()
                )
                """,
                {},
                label="API role directly inserting a fixture replay result",
            )
    finally:
        await engine.dispose()


async def _verify_roles_cannot_forge_active(database_url: str) -> None:
    engine = create_async_engine(database_url)
    try:
        for role in ("srbg_api_role", "srbg_model_role"):
            async with engine.connect() as connection:
                transaction = await connection.begin()
                try:
                    await connection.execute(text(f"SET LOCAL ROLE {role}"))
                    await _expect_db_rejection(
                        connection,
                        """
                        UPDATE source SET lifecycle_state='ACTIVE',enabled=true
                         WHERE id=(SELECT id FROM source ORDER BY id LIMIT 1)
                        """,
                        {},
                        label=f"{role} directly updating a source to ACTIVE",
                    )
                    await _expect_db_rejection(
                        connection,
                        """
                        INSERT INTO source(
                          id,name,base_url,channel,source_type,authority_level,
                          priority,collection_method,poll_interval_minutes,owner,
                          state,enabled,lifecycle_state,trial_kind,registered_by,
                          governance_owner_id,country_codes,region_codes,language_tags,
                          industries,content_domains,declared_roles,created_at,updated_at
                        ) VALUES (
                          :id,'forged active source','https://forged.example.test',
                          'SAFETY','government','A1','P0','RSS',60,'forger',
                          'ACTIVE',true,'ACTIVE',NULL,:actor,:actor,
                          ARRAY['CN']::text[],ARRAY['CN-SC']::text[],
                          ARRAY['zh-CN']::text[],ARRAY['HIGHWAY']::text[],
                          ARRAY['SAFETY_REGULATION']::text[],
                          ARRAY['OFFICIAL_PRIMARY']::text[],now(),now()
                        )
                        """,
                        {"id": uuid7(), "actor": uuid7()},
                        label=f"{role} directly inserting an ACTIVE source",
                    )
                finally:
                    await transaction.rollback()
    finally:
        await engine.dispose()


async def _verify_rollback(database_url: str, legacy: dict[str, tuple[str, bool]]) -> None:
    restored = await _legacy_snapshot(database_url)
    assert restored == legacy


async def _append_governance_metadata_to_migrated_source(database_url: str) -> None:
    """Persist exactly one V2 governance update on a legacy-mapped source."""
    engine = create_async_engine(database_url)
    try:
        async with engine.begin() as connection:
            await connection.execute(text("SET LOCAL ROLE srbg_api_role"))
            source_id = await connection.scalar(
                text(
                    """
                    SELECT s.id
                      FROM source s
                      JOIN source_migration_snapshot snapshot
                        ON snapshot.source_id=s.id
                     ORDER BY s.id
                     LIMIT 1
                    """
                )
            )
            assert isinstance(source_id, UUID)
            now = datetime.now(UTC).replace(microsecond=0)
            actor_id = uuid7()
            returned_id = await connection.scalar(
                text(
                    """
                    SELECT update_source_governance_metadata(
                      :source_id,:owner,ARRAY['CN']::text[],ARRAY['CN-SC']::text[],
                      ARRAY['zh-CN']::text[],ARRAY['HIGHWAY']::text[],
                      ARRAY['SAFETY_REGULATION']::text[],
                      ARRAY['OFFICIAL_PRIMARY']::text[],:actor,
                      'record rollback-sensitive governance metadata',
                      'round15-downgrade-governance-guard',:audit_id,:now
                    )
                    """
                ),
                {
                    "source_id": source_id,
                    "owner": uuid7(),
                    "actor": actor_id,
                    "audit_id": uuid7(),
                    "now": now,
                },
            )
            assert returned_id == source_id
            facts = (
                (
                    await connection.execute(
                        text(
                            """
                            SELECT governance_owner_id,country_codes,region_codes,
                                   language_tags,industries,content_domains,declared_roles
                              FROM source WHERE id=:source_id
                            """
                        ),
                        {"source_id": source_id},
                    )
                )
                .mappings()
                .one()
            )
            assert facts["governance_owner_id"] is not None
            assert facts["country_codes"] == ["CN"]
            assert facts["region_codes"] == ["CN-SC"]
            assert facts["language_tags"] == ["zh-CN"]
            assert facts["industries"] == ["HIGHWAY"]
            assert facts["content_domains"] == ["SAFETY_REGULATION"]
            assert facts["declared_roles"] == ["OFFICIAL_PRIMARY"]

            guarded_table_count = await connection.scalar(
                text(
                    """
                    SELECT
                      (SELECT count(*) FROM connector_config_version)
                    + (SELECT count(*) FROM raw_object_capture)
                    + (SELECT count(*) FROM source_trial_rejected_raw_attempt)
                    + (SELECT count(*) FROM document_attachment_attempt)
                    + (SELECT count(*) FROM source_policy_version)
                    + (SELECT count(*) FROM source_governance_decision)
                    + (SELECT count(*) FROM source_trial_run)
                    + (SELECT count(*) FROM source_trial_run_result)
                    + (SELECT count(*) FROM source_fixture_replay_result)
                    + (SELECT count(*) FROM source_authority_assessment)
                    + (SELECT count(*) FROM source_independence_assessment)
                    + (SELECT count(*) FROM source_lifecycle_event
                        WHERE migration_rule_version IS DISTINCT FROM
                              'round15-lifecycle-v1')
                    """
                )
            )
            assert guarded_table_count == 0
    finally:
        await engine.dispose()


async def _assert_round15_revision(database_url: str) -> None:
    engine = create_async_engine(database_url)
    try:
        async with engine.connect() as connection:
            revision = await connection.scalar(text("SELECT version_num FROM alembic_version"))
            assert revision == "0015b_source_center_convergence"
    finally:
        await engine.dispose()


def _require_isolated_url() -> str:
    database_url = os.environ.get("SRBG_DATABASE_URL", "")
    parsed = urlsplit(database_url.replace("postgresql+asyncpg", "postgresql", 1))
    database_name = parsed.path.removeprefix("/")
    host = parsed.hostname
    try:
        loopback = host == "localhost" or (
            host is not None and ipaddress.ip_address(host).is_loopback
        )
    except ValueError:
        loopback = False
    if not loopback or _DISPOSABLE_DATABASE.fullmatch(database_name) is None:
        raise RuntimeError("Round15 migration replay requires an isolated loopback database")
    return database_url


def main() -> None:
    database_url = _require_isolated_url()
    config = Config("apps/api/alembic.ini")
    command.upgrade(config, "0014b_event_consumer_switch")
    preexisting_negative = asyncio.run(_seed_preexisting_negative_history(database_url))
    legacy = asyncio.run(_legacy_snapshot(database_url))
    command.upgrade(config, "0015b_source_center_convergence")
    asyncio.run(_verify_upgrade(database_url, legacy, preexisting_negative))
    asyncio.run(_verify_roles_cannot_forge_active(database_url))
    asyncio.run(_verify_authoritative_write_boundaries(database_url))
    command.downgrade(config, "0014b_event_consumer_switch")
    asyncio.run(_verify_rollback(database_url, legacy))
    command.upgrade(config, "0015b_source_center_convergence")
    asyncio.run(_verify_upgrade(database_url, legacy, preexisting_negative))
    asyncio.run(_verify_roles_cannot_forge_active(database_url))
    asyncio.run(_verify_authoritative_write_boundaries(database_url))
    asyncio.run(_append_governance_metadata_to_migrated_source(database_url))
    try:
        command.downgrade(config, "0014b_event_consumer_switch")
    except DBAPIError as exc:
        assert "ROUND15_DOWNGRADE_BLOCKED" in str(exc)
    else:
        raise AssertionError("Round15 downgrade discarded migrated-source governance facts")
    asyncio.run(_assert_round15_revision(database_url))
    print(
        "Round15 migration replay passed: 0014b -> 0015 -> 0015b -> "
        "0014b -> 0015 -> 0015b; "
        "legacy mapping/events preserved; database policy/config/capture boundaries verified; "
        "governance metadata blocks destructive downgrade"
    )


if __name__ == "__main__":
    main()
