import os
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from srbg_api.config import get_settings
from srbg_api.database import create_database_engine
from srbg_api.document_vault.service import DocumentVaultService, SourceVaultMetrics
from srbg_api.document_vault.storage import S3ObjectStore
from srbg_api.main import create_app
from srbg_api.source_registry.repository import SourceVaultRepository
from srbg_api.source_registry.service import SourceRegistryService

pytestmark = pytest.mark.skipif(
    os.environ.get("SRBG_RUN_SOURCE_INTEGRATION") != "1",
    reason="run through make source-fixture-test",
)

FIXTURES = Path(__file__).parent / "fixtures" / "source"


class CleanIntegrationScanner:
    async def scan(self, content: bytes) -> None:
        assert content


def _policy_payload(now: datetime) -> dict[str, object]:
    evidence_hash = "a" * 64
    evidence = {
        "result": "ALLOWED",
        "evidence_url": "https://example.test/compliance-evidence",
        "evidence_sha256": evidence_hash,
        "checked_at": now.isoformat(),
    }
    return {
        "schema_version": "2.0.0",
        "policy_version": f"integration-{uuid4()}",
        "valid_from": now.isoformat(),
        "valid_until": (now + timedelta(days=30)).isoformat(),
        "robots_review": evidence,
        "terms_review": evidence,
        "copyright_review": evidence,
        "fetch": {
            "allowed_domains": ["example.test", "connector-only.example.test"],
            "minimum_interval_seconds": 900,
            "rate_limit_per_minute": 10,
            "user_agent": "SRBGSourceAdapter/1.0",
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
            "reason": "fixture replay has no production freshness SLO",
            "authorization_confirmed": False,
            "technical_conditions_confirmed": False,
        },
        "reason": "isolated fixture integration policy",
    }


def test_source_fixture_vertical_slice(monkeypatch: pytest.MonkeyPatch) -> None:
    async def reject_live_network(*args: object, **kwargs: object) -> object:
        del args, kwargs
        raise AssertionError("fixture replay must not invoke a live HTTP transport")

    monkeypatch.setattr(
        "srbg_api.acquisition.live.HttpxTransport.request",
        reject_live_network,
    )
    monkeypatch.setattr(
        "srbg_api.acquisition.http.ResilientHttpClient.get",
        reject_live_network,
    )
    get_settings.cache_clear()
    settings = get_settings()
    engine = create_database_engine(settings)
    repository = SourceVaultRepository(engine)
    metrics = SourceVaultMetrics()
    service = SourceRegistryService(
        repository,
        DocumentVaultService(
            repository=repository,
            object_store=S3ObjectStore(settings),
            malware_scanner=CleanIntegrationScanner(),
            metrics=metrics,
        ),
    )
    client = TestClient(create_app(checkers={}, source_service=service))
    client.__enter__()
    admin = {
        "X-SRBG-Local-Roles": "source_admin",
        "X-SRBG-Local-Step-Up": "true",
        "X-SRBG-Local-User-ID": "019b1500-0000-7000-8000-000000000101",
    }
    approver = admin | {"X-SRBG-Local-User-ID": "019b1500-0000-7000-8000-000000000102"}
    unique = uuid4().hex

    created = client.post(
        "/api/v1/admin/sources",
        headers=admin,
        json={
            "name": f"集成测试来源-{unique}",
            "base_url": f"https://example.test/source/{unique}",
            "channel": "BOTH",
            "source_type": "government",
            "authority_level": "A1",
            "priority": "P0",
            "collection_method": "manual_fixture",
            "poll_interval_minutes": 60,
            "owner": "source_ops",
            "governance_owner_id": "019b1500-0000-7000-8000-000000000103",
            "country_codes": ["CN"],
            "region_codes": ["CN-SC"],
            "language_tags": ["zh-CN"],
            "industries": ["HIGHWAY"],
            "content_domains": ["SAFETY_REGULATION"],
            "declared_roles": ["OFFICIAL_PRIMARY"],
        },
    )
    assert created.status_code == 201, created.text
    source_id = created.json()["id"]

    assessed_at = datetime.now(UTC).isoformat()
    assessment = client.post(
        f"/api/v1/admin/sources/{source_id}/assessments",
        headers=admin,
        json={
            "authority": {
                "level": "A1",
                "rule_version": "authority-integration-v1",
                "reason_codes": ["OFFICIAL_PUBLISHER"],
                "evidence_refs": ["https://example.test/publisher-evidence"],
                "assessed_at": assessed_at,
            },
            "independence": {
                "level": "NOT_INDEPENDENT",
                "rule_version": "independence-integration-v1",
                "reason_codes": ["SELF_PUBLISHED"],
                "evidence_refs": ["https://example.test/editorial-evidence"],
                "assessed_at": assessed_at,
            },
            "reason": "record separate explainable source assessments",
        },
    )
    assert assessment.status_code == 200, assessment.text

    compliance = client.post(
        f"/api/v1/admin/sources/{source_id}/submit-compliance",
        headers=admin,
        json={"reason": "integration compliance review"},
    )
    assert compliance.status_code == 200, compliance.text
    policy = client.post(
        f"/api/v1/admin/sources/{source_id}/policy-versions",
        headers=admin,
        json=_policy_payload(datetime.now(UTC)),
    )
    assert policy.status_code == 201, policy.text
    policy_id = policy.json()["id"]
    decision = client.post(
        f"/api/v1/admin/sources/{source_id}/policy-versions/{policy_id}/decisions",
        headers=approver,
        json={"outcome": "APPROVED", "reason": "independent compliance approval"},
    )
    assert decision.status_code == 200, decision.text
    preview_config = {
        "connector_type": "MANUAL_IMPORT",
        "definition_version": "1.0.0",
        "config": {
            "allowed_hosts": ["example.test"],
            "url_import_enabled": True,
            "file_import_enabled": True,
            "allowed_file_types": ["HTML", "PDF"],
            "credential_ref": "vault://source-connectors/integration/manual-import",
        },
    }
    preview_response = client.post(
        f"/api/v1/admin/sources/{source_id}/connector-config-versions/preview",
        headers=admin,
        json=preview_config,
    )
    assert preview_response.status_code == 200, preview_response.text
    assert preview_response.json()["network_io_performed"] is False
    assert preview_response.json()["config"]["credential_ref"] == "[configured]"
    config = client.post(
        f"/api/v1/admin/sources/{source_id}/connector-config-versions",
        headers=admin,
        json=preview_config | {"reason": "versioned manual fixture connector"},
    )
    assert config.status_code == 201, config.text
    assert config.json()["credential_configured"] is True
    assert "credential_ref" not in config.text
    config_id = config.json()["id"]
    fixture_state = client.post(
        f"/api/v1/admin/sources/{source_id}/trial-runs",
        headers=admin,
        json={
            "kind": "FIXTURE_REPLAY",
            "policy_version_id": policy_id,
            "connector_config_version_id": config_id,
            "reason": "isolated fixed fixture replay",
        },
    )
    assert fixture_state.status_code == 201, fixture_state.text

    upload_headers = admin | {
        "Content-Type": "text/html",
        "X-Filename": "fixture.html",
        "X-Document-URL": f"https://example.test/documents/{unique}",
    }
    sample = (FIXTURES / "round01-sample.html").read_bytes()
    first_content = sample.replace(b"{{UNIQUE}}", f"{unique}-v1".encode())
    changed_content = sample.replace(b"{{UNIQUE}}", f"{unique}-v2".encode())
    first = client.post(
        f"/api/v1/admin/sources/{source_id}/fixture",
        headers=upload_headers,
        content=first_content,
    )
    duplicate = client.post(
        f"/api/v1/admin/sources/{source_id}/fixture",
        headers=upload_headers,
        content=first_content,
    )
    changed = client.post(
        f"/api/v1/admin/sources/{source_id}/fixture",
        headers=upload_headers,
        content=changed_content,
    )

    assert first.status_code == 201, first.text
    assert duplicate.status_code == 201, duplicate.text
    assert changed.status_code == 201, changed.text
    assert (
        first.json()["document"]["raw_object"]["id"]
        == duplicate.json()["document"]["raw_object"]["id"]
    )
    assert duplicate.json()["version_created"] is False
    assert changed.json()["document"]["current_version"]["version_number"] == 2
    assert metrics.uploads == 3
    assert metrics.deduplications == 1

    viewer_completion = client.post(
        (
            f"/api/v1/admin/sources/{source_id}/trial-runs/"
            f"{fixture_state.json()['id']}/complete-fixture"
        ),
        headers={"X-SRBG-Local-Roles": "viewer"},
        json={"reason": "viewer cannot complete source trials"},
    )
    assert viewer_completion.status_code == 403

    completed_fixture = client.post(
        (
            f"/api/v1/admin/sources/{source_id}/trial-runs/"
            f"{fixture_state.json()['id']}/complete-fixture"
        ),
        headers=admin,
        json={"reason": "finish the isolated fixture replay with server-derived quality"},
    )
    assert completed_fixture.status_code == 200, completed_fixture.text
    assert completed_fixture.json()["status"] == "SUCCEEDED"
    assert completed_fixture.json()["kind"] == "FIXTURE_REPLAY"
    assert completed_fixture.json()["quality_summary"] == {
        "raw_count": 2,
        "ready_count": 2,
        "parse_failed_count": 0,
        "security_failed_count": 0,
        "rejected_raw_attempt_count": 0,
        "ready_ratio_bps": 10000,
    }

    fixture_detail = client.get(f"/api/v1/admin/sources/{source_id}", headers=admin)
    assert fixture_detail.status_code == 200
    assert fixture_detail.json()["effective_active"] is False
    assert fixture_detail.json()["runtime_authorization"] == "TRIAL_ONLY"
    assert {
        "START_FIXTURE_TRIAL",
        "START_LIVE_TRIAL",
    }.issubset(set(fixture_detail.json()["available_actions"]))
    fixture_audit = client.get(f"/api/v1/admin/sources/{source_id}/audit-events", headers=admin)
    assert fixture_audit.status_code == 200
    assert any(event["event_type"] == "SOURCE_TRIAL_COMPLETED" for event in fixture_audit.json())

    viewer_upload = client.post(
        f"/api/v1/admin/sources/{source_id}/fixture",
        headers=upload_headers | {"X-SRBG-Local-Roles": "viewer"},
        content=b"<!doctype html><html><body>denied</body></html>",
    )
    assert viewer_upload.status_code == 403

    preview = client.get(
        f"/api/v1/admin/documents/{changed.json()['document']['id']}",
        headers=admin,
    )
    assert preview.status_code == 200
    assert (
        preview.json()["current_version"]["content_hash"]
        == changed.json()["document"]["current_version"]["content_hash"]
    )

    raw_object_id = UUID(first.json()["document"]["raw_object"]["id"])

    async def overwrite_raw_object() -> None:
        tamper_engine = create_database_engine(settings)
        try:
            async with tamper_engine.begin() as connection:
                await connection.execute(
                    text("UPDATE raw_object SET byte_size = byte_size + 1 WHERE id = :raw_id"),
                    {"raw_id": raw_object_id},
                )
        finally:
            await tamper_engine.dispose()

    import asyncio

    with pytest.raises(DBAPIError, match="raw_object is immutable"):
        asyncio.run(overwrite_raw_object())

    # Runtime SQL cannot use legacy flags to forge production authority.
    async def tamper() -> None:
        tamper_engine = create_database_engine(settings)
        try:
            async with tamper_engine.begin() as connection:
                await connection.execute(
                    text(
                        "UPDATE source SET state = 'ACTIVE', enabled = true WHERE id = :source_id"
                    ),
                    {"source_id": UUID(source_id)},
                )
        finally:
            await tamper_engine.dispose()

    with pytest.raises(DBAPIError):
        asyncio.run(tamper())
    detail = client.get(f"/api/v1/admin/sources/{source_id}", headers=admin)
    assert detail.status_code == 200
    assert detail.json()["effective_active"] is False
    assert detail.json()["source_authority"]["rule_version"] == "authority-integration-v1"
    assert detail.json()["source_authority"]["evidence_refs"]
    assert detail.json()["source_independence"]["rule_version"] == "independence-integration-v1"

    # Policy scope alone is insufficient: the current trial configuration must
    # independently allow the host before bytes are written to object storage.
    restricted_config_payload = {
        "connector_type": "MANUAL_IMPORT",
        "definition_version": "1.0.0",
        "config": {
            "allowed_hosts": ["connector-only.example.test"],
            "url_import_enabled": True,
            "file_import_enabled": True,
            "allowed_file_types": ["HTML", "PDF"],
            "credential_ref": "vault://source-connectors/integration/restricted",
        },
        "reason": "narrow connector host boundary",
    }
    restricted_config = client.post(
        f"/api/v1/admin/sources/{source_id}/connector-config-versions",
        headers=admin,
        json=restricted_config_payload,
    )
    assert restricted_config.status_code == 201, restricted_config.text
    restricted_trial = client.post(
        f"/api/v1/admin/sources/{source_id}/trial-runs",
        headers=admin,
        json={
            "kind": "FIXTURE_REPLAY",
            "policy_version_id": policy_id,
            "connector_config_version_id": restricted_config.json()["id"],
            "reason": "connector host intersection replay",
        },
    )
    assert restricted_trial.status_code == 201, restricted_trial.text
    denied_content = (
        b"<!doctype html><html><body>connector-host-denied-" + unique.encode() + b"</body></html>"
    )
    denied_hash = sha256(denied_content).hexdigest()
    denied = client.post(
        f"/api/v1/admin/sources/{source_id}/fixture",
        headers=upload_headers,
        content=denied_content,
    )
    assert denied.status_code == 422, denied.text

    async def denied_raw_was_not_persisted() -> bool:
        verification_engine = create_database_engine(settings)
        try:
            verification_repository = SourceVaultRepository(verification_engine)
            return await verification_repository.raw_object_exists(denied_hash)
        finally:
            await verification_engine.dispose()

    assert asyncio.run(denied_raw_was_not_persisted()) is False

    failed_fixture = client.post(
        (
            f"/api/v1/admin/sources/{source_id}/trial-runs/"
            f"{restricted_trial.json()['id']}/complete-fixture"
        ),
        headers=admin,
        json={"reason": "close a fixture replay with rejected evidence"},
    )
    assert failed_fixture.status_code == 200, failed_fixture.text
    assert failed_fixture.json()["status"] == "FAILED"
    assert failed_fixture.json()["quality_summary"] == {
        "raw_count": 0,
        "ready_count": 0,
        "parse_failed_count": 0,
        # Host authorization is denied before any bytes or raw-attempt fact is
        # accepted, so the empty trial fails closed without inventing evidence.
        "security_failed_count": 0,
        "rejected_raw_attempt_count": 0,
        "ready_ratio_bps": 0,
    }

    # A fixture trial validates the bound connector configuration, not merely
    # whether arbitrary uploaded bytes passed the generic file-safety checks.
    feed_url = f"https://example.test/feeds/{unique}.xml"
    detail_url = f"https://example.test/notices/{unique}.html"
    rss_config_payload = {
        "connector_type": "RSS_ATOM",
        "definition_version": "1.0.0",
        "config": {
            "allowed_hosts": ["example.test"],
            "feed_url": feed_url,
        },
        "reason": "bind the source-specific RSS fixture replay",
    }
    rss_preview = client.post(
        f"/api/v1/admin/sources/{source_id}/connector-config-versions/preview",
        headers=admin,
        json={key: value for key, value in rss_config_payload.items() if key != "reason"},
    )
    assert rss_preview.status_code == 200, rss_preview.text
    assert rss_preview.json()["network_io_performed"] is False
    rss_config = client.post(
        f"/api/v1/admin/sources/{source_id}/connector-config-versions",
        headers=admin,
        json=rss_config_payload,
    )
    assert rss_config.status_code == 201, rss_config.text

    invalid_rss_trial = client.post(
        f"/api/v1/admin/sources/{source_id}/trial-runs",
        headers=admin,
        json={
            "kind": "FIXTURE_REPLAY",
            "policy_version_id": policy_id,
            "connector_config_version_id": rss_config.json()["id"],
            "reason": "prove invalid RSS fixture bytes fail the bound adapter",
        },
    )
    assert invalid_rss_trial.status_code == 201, invalid_rss_trial.text
    invalid_feed = client.post(
        f"/api/v1/admin/sources/{source_id}/fixture",
        headers=admin
        | {
            "Content-Type": "text/html",
            "X-Filename": "not-a-feed.html",
            "X-Document-URL": feed_url,
        },
        content=(
            b"<!doctype html><html><head><title>not rss</title></head>"
            b"<body>clean but structurally invalid for RSS</body></html>"
        ),
    )
    assert invalid_feed.status_code == 201, invalid_feed.text
    invalid_completion = client.post(
        (
            f"/api/v1/admin/sources/{source_id}/trial-runs/"
            f"{invalid_rss_trial.json()['id']}/complete-fixture"
        ),
        headers=admin,
        json={"reason": "complete only after executing the bound RSS adapter"},
    )
    assert invalid_completion.status_code == 200, invalid_completion.text
    assert invalid_completion.json()["status"] == "FAILED"

    valid_rss_trial = client.post(
        f"/api/v1/admin/sources/{source_id}/trial-runs",
        headers=admin,
        json={
            "kind": "FIXTURE_REPLAY",
            "policy_version_id": policy_id,
            "connector_config_version_id": rss_config.json()["id"],
            "reason": "retry the same RSS connector with fixed safe fixtures",
        },
    )
    assert valid_rss_trial.status_code == 201, valid_rss_trial.text
    rss_bytes = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel><title>固定安全回放</title><item>
<guid>{unique}</guid><title>桥梁施工安全通知</title><link>{detail_url}</link>
<pubDate>Wed, 15 Jul 2026 02:00:00 GMT</pubDate>
</item></channel></rss>""".encode()
    rss_upload = client.post(
        f"/api/v1/admin/sources/{source_id}/fixture",
        headers=admin
        | {
            "Content-Type": "application/xml",
            "X-Filename": "feed.xml",
            "X-Document-URL": feed_url,
        },
        content=rss_bytes,
    )
    assert rss_upload.status_code == 201, rss_upload.text
    detail_upload = client.post(
        f"/api/v1/admin/sources/{source_id}/fixture",
        headers=admin
        | {
            "Content-Type": "text/html",
            "X-Filename": "notice.html",
            "X-Document-URL": detail_url,
        },
        content=(
            b"<!doctype html><html><head><title>safe detail</title></head>"
            b"<body><main>fixed RSS detail replay</main></body></html>"
        ),
    )
    assert detail_upload.status_code == 201, detail_upload.text
    valid_completion = client.post(
        (
            f"/api/v1/admin/sources/{source_id}/trial-runs/"
            f"{valid_rss_trial.json()['id']}/complete-fixture"
        ),
        headers=admin,
        json={"reason": "complete the bound RSS fixture replay without live network I/O"},
    )
    assert valid_completion.status_code == 200, valid_completion.text
    assert valid_completion.json()["status"] == "SUCCEEDED"
    assert valid_completion.json()["kind"] == "FIXTURE_REPLAY"
    valid_quality = valid_completion.json()["quality_summary"]
    assert valid_quality["raw_count"] >= 1
    assert valid_quality["ready_count"] == valid_quality["raw_count"]
    client.__exit__(None, None, None)
