import os
from datetime import UTC, datetime, timedelta
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
    return {
        "policy_version": f"integration-{uuid4()}",
        "status": "VALID",
        "robots_review": {
            "result": "ALLOWED",
            "evidence_url": "https://example.test/robots.txt",
            "evidence_sha256": evidence_hash,
            "checked_at": now.isoformat(),
        },
        "terms_review": {
            "result": "NOT_PRESENT",
            "evidence_url": "https://example.test/terms-review",
            "evidence_sha256": evidence_hash,
            "checked_at": now.isoformat(),
        },
        "copyright": {
            "storage_policy": "RAW_EVIDENCE_ALLOWED",
            "display_policy": "METADATA_EXCERPT_LINK",
            "fulltext_allowed": False,
            "image_allowed": False,
            "excerpt_max_chars": 300,
            "attribution_template": "来源: {source_name}",
        },
        "access": {
            "allowed_domains": ["example.test"],
            "requires_auth": False,
            "rate_limit_per_minute": 10,
            "user_agent": "SRBGSourceAdapter/1.0",
        },
        "review": {
            "valid_until": (now + timedelta(days=30)).isoformat(),
            "approval_id": f"integration-{uuid4()}",
        },
    }


def test_source_fixture_vertical_slice() -> None:
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
    admin = {"X-SRBG-Local-Roles": "source_admin"}
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
        },
    )
    assert created.status_code == 201, created.text
    source_id = created.json()["id"]

    compliance = client.post(
        f"/api/v1/admin/sources/{source_id}/transitions",
        headers=admin,
        json={"target_state": "COMPLIANCE_REVIEW", "reason": "integration gate"},
    )
    assert compliance.status_code == 200, compliance.text
    policy = client.put(
        f"/api/v1/admin/sources/{source_id}/policy",
        headers=admin,
        json=_policy_payload(datetime.now(UTC)),
    )
    assert policy.status_code == 200, policy.text
    fixture_state = client.post(
        f"/api/v1/admin/sources/{source_id}/transitions",
        headers=admin,
        json={"target_state": "FIXTURE_TEST", "reason": "policy passed"},
    )
    assert fixture_state.status_code == 200, fixture_state.text

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

    # Even simulated direct state/flag tampering cannot make evidence-incomplete sources effective.
    async def tamper() -> None:
        tamper_engine = create_database_engine(settings)
        async with tamper_engine.begin() as connection:
            await connection.execute(
                text("UPDATE source SET state = 'ACTIVE', enabled = true WHERE id = :source_id"),
                {"source_id": UUID(source_id)},
            )
        await tamper_engine.dispose()

    asyncio.run(tamper())
    detail = client.get(f"/api/v1/admin/sources/{source_id}", headers=admin)
    assert detail.status_code == 200
    assert detail.json()["effective_active"] is False
    client.__exit__(None, None, None)
