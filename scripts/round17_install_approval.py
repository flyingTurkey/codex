"""Atomically install the verified test-only LEO authority in PostgreSQL."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine
from srbg_api.config import get_settings
from srbg_api.identifiers import uuid7
from srbg_api.operations.service import _round17_signed_approval_is_trusted

PACKAGE = Path("docs/acceptance/assets/round17/leo-signed-approval.json")
HEAD = "0017c_round17_flat_pilot"


def _timestamp(value: object) -> datetime:
    if not isinstance(value, str):
        raise RuntimeError("signed approval timestamp is missing")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise RuntimeError("signed approval timestamp lacks a UTC offset")
    return parsed.astimezone(UTC)


def _load_package() -> dict[str, object]:
    loaded = json.loads(PACKAGE.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise RuntimeError("signed approval package must be an object")
    return loaded


async def install(*, loopback_port: int | None = None) -> str:
    settings = get_settings()
    package = _load_package()
    document = package.get("approval_document")
    if not isinstance(document, dict):
        raise RuntimeError("signed approval document is missing")
    sources = document.get("sources")
    if not isinstance(sources, list):
        raise RuntimeError("signed approval roster is missing")
    source_codes = tuple(
        str(source.get("source_code")) for source in sources if isinstance(source, dict)
    )
    row = dict(package)
    row["approved_by"] = UUID(str(package["approved_by"]))
    row["valid_from"] = _timestamp(package.get("valid_from"))
    row["valid_until"] = _timestamp(package.get("valid_until"))
    now = datetime.now(UTC)
    if not _round17_signed_approval_is_trusted(
        row,
        source_codes=source_codes,
        leo_actor_id=settings.round17_leo_approver_actor_id,
        trusted_public_key_base64=settings.round17_leo_signing_public_key_base64,
        trusted_public_key_sha256=settings.round17_leo_signing_public_key_sha256,
        now=now,
    ):
        raise RuntimeError("signed approval did not pass server trust verification")

    database_url = make_url(settings.database_url)
    if loopback_port is not None:
        database_url = database_url.set(host="127.0.0.1", port=loopback_port)
    engine = create_async_engine(database_url)
    try:
        async with engine.begin() as connection:
            revision = await connection.scalar(text("SELECT version_num FROM alembic_version"))
            if revision != HEAD:
                raise RuntimeError(f"database must be migrated to {HEAD}")
            existing_binding = (
                (
                    await connection.execute(
                        text(
                            """SELECT actor_id,display_name,responsibility,authority_mode,
                                      local_identity,oidc_issuer_sha256,oidc_subject_sha256
                                 FROM round17_staff_binding
                                WHERE actor_id=:actor"""
                        ),
                        {"actor": row["approved_by"]},
                    )
                )
                .mappings()
                .all()
            )
            if existing_binding:
                expected = {
                    "actor_id": row["approved_by"],
                    "display_name": "LEO",
                    "responsibility": "SOURCE_APPROVER",
                    "authority_mode": "SIGNED_LOCAL_PILOT",
                    "local_identity": True,
                    "oidc_issuer_sha256": None,
                    "oidc_subject_sha256": None,
                }
                if len(existing_binding) != 1 or dict(existing_binding[0]) != expected:
                    raise RuntimeError("LEO has a conflicting Round17 staff binding")
            else:
                await connection.execute(
                    text(
                        """INSERT INTO round17_staff_binding (
                             id,actor_id,display_name,responsibility,oidc_issuer_sha256,
                             oidc_subject_sha256,local_identity,bound_by,bound_at,authority_mode
                           ) VALUES (
                             :id,:actor,'LEO','SOURCE_APPROVER',NULL,NULL,true,:actor,:now,
                             'SIGNED_LOCAL_PILOT'
                           )"""
                    ),
                    {"id": uuid7(), "actor": row["approved_by"], "now": now},
                )
            existing_hash = await connection.scalar(
                text(
                    """SELECT approval_document_sha256 FROM round17_signed_approval
                        WHERE approval_type=:approval_type"""
                ),
                {"approval_type": package["approval_type"]},
            )
            if existing_hash is not None and existing_hash != package["approval_document_sha256"]:
                raise RuntimeError("a different atomic Round17 approval is already installed")
            if existing_hash is None:
                approval_id = uuid7()
                await connection.execute(
                    text(
                        """INSERT INTO round17_signed_approval (
                             id,approval_type,authority_mode,approval_document,
                             approval_document_sha256,approval_signature,
                             signer_public_key_sha256,approved_by,approved_by_display_name,
                             approved_by_responsibility,valid_from,valid_until,created_at
                           ) VALUES (
                             :id,:approval_type,'SIGNED_LOCAL_PILOT',CAST(:document AS jsonb),
                             :document_sha256,:signature,:fingerprint,:actor,'LEO',
                             'SOURCE_APPROVER',:valid_from,:valid_until,:now
                           )"""
                    ),
                    {
                        "id": approval_id,
                        "approval_type": package["approval_type"],
                        "document": json.dumps(document, ensure_ascii=False),
                        "document_sha256": package["approval_document_sha256"],
                        "signature": package["approval_signature"],
                        "fingerprint": package["signer_public_key_sha256"],
                        "actor": row["approved_by"],
                        "valid_from": row["valid_from"],
                        "valid_until": row["valid_until"],
                        "now": now,
                    },
                )
                await connection.execute(
                    text(
                        "SELECT append_audit_event(:id,'ROUND17_ATOMIC_AUTHORITY_INSTALLED',"
                        ":actor,'ROUND17_SIGNED_APPROVAL',:approval,NULL,"
                        "jsonb_build_object('document_sha256',CAST(:sha AS text)),"
                        ":reason,:request,:now)"
                    ),
                    {
                        "id": uuid7(),
                        "actor": row["approved_by"],
                        "approval": approval_id,
                        "sha": package["approval_document_sha256"],
                        "reason": "install the LEO-frozen Round17 atomic authority",
                        "request": f"round17-authority:{package['approval_document_sha256']}",
                        "now": now,
                    },
                )
    finally:
        await engine.dispose()
    return str(package["approval_document_sha256"])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--loopback-port", type=int)
    args = parser.parse_args()
    import asyncio

    document_hash = asyncio.run(install(loopback_port=args.loopback_port))
    print(f"Round17 atomic authority installed; document_sha256={document_hash}")


if __name__ == "__main__":
    main()
