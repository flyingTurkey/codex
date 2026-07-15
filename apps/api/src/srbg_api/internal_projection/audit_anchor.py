"""Anchor the tamper-evident audit chain root to independently configured object storage."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime

import aioboto3
from botocore.config import Config as BotoConfig
from botocore.exceptions import ClientError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from srbg_api.config import Settings
from srbg_api.identifiers import uuid7

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class AuditAnchorResult:
    audit_log_id: str
    entry_hash: str
    object_key: str
    already_anchored: bool


async def anchor_latest_audit_root(
    engine: AsyncEngine, settings: Settings, *, now: datetime | None = None
) -> AuditAnchorResult:
    endpoint = settings.backup_s3_endpoint_url
    bucket = settings.backup_s3_bucket
    access_key = settings.backup_s3_access_key
    secret = settings.backup_s3_secret_key
    if not endpoint or not bucket or not access_key or secret is None:
        raise ValueError("independent audit anchor storage is not configured")
    if endpoint.rstrip("/") == settings.s3_endpoint_url.rstrip("/"):
        raise ValueError("audit anchors require storage independent from raw objects")
    anchored_at = now or datetime.now(UTC)
    async with engine.begin() as connection:
        row = (
            (
                await connection.execute(
                    text(
                        "SELECT id, entry_hash, created_at FROM audit_log "
                        "ORDER BY created_at DESC, id DESC LIMIT 1"
                    )
                )
            )
            .mappings()
            .first()
        )
        if row is None:
            raise ValueError("audit chain is empty")
        existing = await connection.scalar(
            text("SELECT anchor_object_key FROM audit_chain_anchor WHERE audit_log_id = :id"),
            {"id": row["id"]},
        )
        if existing is not None:
            LOGGER.info(
                "audit_chain_anchor_verified",
                extra={"audit_log_id": str(row["id"]), "already_anchored": True},
            )
            return AuditAnchorResult(str(row["id"]), row["entry_hash"], existing, True)
        object_key = (
            f"audit-chain-anchors/{anchored_at:%Y/%m/%d}/"
            f"{row['created_at'].isoformat()}-{row['entry_hash']}.json"
        )
        payload = json.dumps(
            {
                "audit_log_id": str(row["id"]),
                "entry_hash": row["entry_hash"],
                "audit_created_at": row["created_at"].isoformat(),
                "anchored_at": anchored_at.isoformat(),
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        client_config = BotoConfig(
            connect_timeout=settings.external_io_timeout_seconds,
            read_timeout=settings.external_io_timeout_seconds,
            retries={"max_attempts": 2, "mode": "standard"},
        )
        async with aioboto3.Session().client(
            "s3",
            endpoint_url=endpoint,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret.get_secret_value(),
            region_name=settings.s3_region,
            config=client_config,
        ) as client:
            try:
                await client.put_object(
                    Bucket=bucket,
                    Key=object_key,
                    Body=payload,
                    ContentType="application/json",
                    IfNoneMatch="*",
                )
            except ClientError as exc:
                if exc.response.get("Error", {}).get("Code") not in {
                    "PreconditionFailed",
                    "412",
                }:
                    raise
        await connection.execute(
            text(
                """
                INSERT INTO audit_chain_anchor
                    (id, audit_log_id, entry_hash, anchor_store, anchor_object_key, anchored_at)
                VALUES (:id, :audit_id, :entry_hash, :store, :key, :now)
                ON CONFLICT (audit_log_id) DO NOTHING
                """
            ),
            {
                "id": uuid7(),
                "audit_id": row["id"],
                "entry_hash": row["entry_hash"],
                "store": endpoint,
                "key": object_key,
                "now": anchored_at,
            },
        )
    LOGGER.info(
        "audit_chain_anchor_persisted",
        extra={"audit_log_id": str(row["id"]), "already_anchored": False},
    )
    return AuditAnchorResult(str(row["id"]), row["entry_hash"], object_key, False)
