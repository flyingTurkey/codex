"""PostgreSQL adapter for authoritative T12 media delivery registration."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from srbg_api.intelligence_v2.media import CleanAttachmentAuthority, MediaDeliveryRecord


class PostgresMediaDeliveryRepository:
    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def close(self) -> None:
        await self._engine.dispose()

    async def load_clean_attachment(
        self, *, attachment_id: UUID, canonical_url_sha256: str
    ) -> CleanAttachmentAuthority | None:
        async with self._engine.connect() as connection:
            row = (
                (
                    await connection.execute(
                        text(
                            """
                            SELECT attachment_id,document_version_id,name,object_key,
                              content_sha256,byte_size,detected_mime
                            FROM load_clean_media_attachment_v2(
                              :attachment_id,:canonical_url_sha256
                            )
                            """
                        ),
                        {
                            "attachment_id": attachment_id,
                            "canonical_url_sha256": canonical_url_sha256,
                        },
                    )
                )
                .mappings()
                .one_or_none()
            )
        if row is None:
            return None
        return CleanAttachmentAuthority(
            attachment_id=row["attachment_id"],
            document_version_id=row["document_version_id"],
            name=str(row["name"]),
            object_key=str(row["object_key"]),
            content_sha256=str(row["content_sha256"]),
            byte_size=int(row["byte_size"]),
            detected_mime=str(row["detected_mime"]),
        )

    async def save_delivery(self, record: MediaDeliveryRecord) -> None:
        async with self._engine.begin() as connection:
            await connection.execute(
                text(
                    """
                    INSERT INTO media_rights_v2(
                      id,attachment_id,document_version_id,name,object_key,source_url,mime_type,
                      rights_basis,rights_evidence_ref,redistribution_allowed,scan_status,
                      preview_object_key,preview_sha256,preview_mime_type,preview_byte_size,
                      created_at
                    ) VALUES(
                      :id,:attachment_id,:document_version_id,:name,:object_key,:source_url,
                      :mime_type,:rights_basis,:rights_evidence_ref,:redistribution_allowed,
                      :scan_status,:preview_object_key,:preview_sha256,:preview_mime_type,
                      :preview_byte_size,:created_at
                    )
                    """
                ),
                {
                    "id": record.media_id,
                    "attachment_id": record.attachment_id,
                    "document_version_id": record.document_version_id,
                    "name": record.name,
                    "object_key": record.object_key,
                    "source_url": record.source_url,
                    "mime_type": record.mime_type,
                    "rights_basis": record.rights_basis,
                    "rights_evidence_ref": record.rights_evidence_ref,
                    "redistribution_allowed": record.redistribution_allowed,
                    "scan_status": record.scan_status,
                    "preview_object_key": record.preview_object_key,
                    "preview_sha256": record.preview_sha256,
                    "preview_mime_type": record.preview_mime_type,
                    "preview_byte_size": record.preview_byte_size,
                    "created_at": datetime.now(UTC),
                },
            )
