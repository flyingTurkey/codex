# ruff: noqa: E501
"""Bind T12 media delivery to CLEAN attachment and derived preview facts.

Revision ID: 0045_t12_media_delivery
Revises: 0044_t11_reader_appendix
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision = "0045_t12_media_delivery"
down_revision = "0044_t11_reader_appendix"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("media_rights_v2", sa.Column("attachment_id", sa.Uuid()))
    op.add_column("media_rights_v2", sa.Column("rights_evidence_ref", sa.String(500)))
    op.add_column("media_rights_v2", sa.Column("preview_object_key", sa.String(1000)))
    op.add_column("media_rights_v2", sa.Column("preview_sha256", sa.String(64)))
    op.add_column("media_rights_v2", sa.Column("preview_mime_type", sa.String(100)))
    op.add_column("media_rights_v2", sa.Column("preview_byte_size", sa.BigInteger()))
    op.create_foreign_key(
        "fk_media_v2_attachment",
        "media_rights_v2",
        "document_attachment",
        ["attachment_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_unique_constraint(
        "uq_media_v2_attachment", "media_rights_v2", ["attachment_id"]
    )
    op.create_check_constraint(
        "ck_media_v2_rights_evidence",
        "media_rights_v2",
        "rights_basis IS NULL OR (rights_evidence_ref IS NOT NULL AND length(rights_evidence_ref) BETWEEN 1 AND 500)",
    )
    op.create_check_constraint(
        "ck_media_v2_preview_bundle",
        "media_rights_v2",
        "(preview_object_key IS NULL AND preview_sha256 IS NULL AND preview_mime_type IS NULL AND preview_byte_size IS NULL) OR "
        "(preview_object_key IS NOT NULL AND preview_sha256 ~ '^[0-9a-f]{64}$' AND "
        "preview_object_key = 'sha256/' || left(preview_sha256,2) || '/' || preview_sha256 AND "
        "preview_mime_type='image/png' AND preview_byte_size BETWEEN 1 AND 10000000)",
    )
    op.execute(
        """
        CREATE FUNCTION load_clean_media_attachment_v2(
          p_attachment_id uuid,p_canonical_url_sha256 text
        ) RETURNS TABLE(
          attachment_id uuid,document_version_id uuid,name varchar,object_key varchar,
          content_sha256 varchar,byte_size bigint,detected_mime varchar
        ) LANGUAGE sql SECURITY DEFINER
        SET search_path = pg_catalog, public AS $$
          SELECT attachment.id,attachment.document_version_id,attachment.filename,
            raw.object_key,raw.sha256,raw.byte_size,raw.detected_mime
          FROM document_attachment attachment
          JOIN raw_object raw ON raw.id=attachment.raw_object_id
          WHERE attachment.id=p_attachment_id
            AND attachment.security_status='CLEAN'
            AND raw.scan_status='CLEAN'
            AND EXISTS(
              SELECT 1 FROM document_attachment_attempt attempt
              WHERE attempt.document_version_id=attachment.document_version_id
                AND attempt.object_key=raw.object_key
                AND attempt.content_sha256=raw.sha256
                AND attempt.canonical_url_sha256=p_canonical_url_sha256
                AND attempt.outcome='ACCEPTED'
            )
        $$
        """
    )
    op.execute(
        "REVOKE ALL ON FUNCTION load_clean_media_attachment_v2(uuid,text) FROM PUBLIC"
    )
    op.execute(
        "GRANT EXECUTE ON FUNCTION load_clean_media_attachment_v2(uuid,text) "
        "TO srbg_publication_writer"
    )
    op.execute(
        """
        CREATE FUNCTION enforce_media_v2_authority() RETURNS trigger
        LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, public AS $$
        BEGIN
          IF NEW.attachment_id IS NULL OR NEW.rights_basis IS NULL
             OR NEW.rights_evidence_ref IS NULL
             OR NOT EXISTS (
               SELECT 1
               FROM document_attachment attachment
               JOIN raw_object raw ON raw.id=attachment.raw_object_id
               WHERE attachment.id=NEW.attachment_id
                 AND attachment.document_version_id=NEW.document_version_id
                 AND attachment.security_status='CLEAN'
                 AND raw.scan_status='CLEAN'
                 AND raw.object_key=NEW.object_key
                 AND raw.detected_mime=NEW.mime_type
             )
             OR NOT EXISTS (
               SELECT 1 FROM document_attachment_attempt attempt
               JOIN raw_object raw ON raw.object_key=attempt.object_key
               WHERE attempt.document_version_id=NEW.document_version_id
                 AND attempt.object_key=NEW.object_key
                 AND attempt.outcome='ACCEPTED'
                 AND encode(digest(NEW.source_url,'sha256'),'hex')=attempt.canonical_url_sha256
             ) THEN
            RAISE EXCEPTION 'media delivery lacks authoritative CLEAN attachment evidence';
          END IF;
          RETURN NEW;
        END $$
        """
    )
    op.execute(
        "CREATE TRIGGER trg_media_v2_authority BEFORE INSERT OR UPDATE ON media_rights_v2 "
        "FOR EACH ROW EXECUTE FUNCTION enforce_media_v2_authority()"
    )
    op.execute(
        """
        CREATE VIEW media_delivery_reader_v2 WITH (security_barrier=true) AS
        SELECT media.id,media.document_version_id,media.name,media.object_key,
          media.source_url,media.mime_type,media.rights_basis,
          media.redistribution_allowed,media.scan_status,
          attachment.security_status AS attachment_scan_status,
          raw.scan_status AS raw_scan_status,media.preview_object_key,
          media.preview_mime_type,media.created_at
        FROM media_rights_v2 media
        JOIN document_attachment attachment ON attachment.id=media.attachment_id
        JOIN raw_object raw ON raw.id=attachment.raw_object_id
        """
    )
    op.execute(
        "GRANT SELECT ON media_delivery_reader_v2 TO srbg_projection_reader,"
        "srbg_publication_writer"
    )


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS media_delivery_reader_v2")
    op.execute("DROP TRIGGER IF EXISTS trg_media_v2_authority ON media_rights_v2")
    op.execute("DROP FUNCTION IF EXISTS enforce_media_v2_authority()")
    op.execute("DROP FUNCTION IF EXISTS load_clean_media_attachment_v2(uuid,text)")
    op.drop_constraint("ck_media_v2_preview_bundle", "media_rights_v2", type_="check")
    op.drop_constraint("ck_media_v2_rights_evidence", "media_rights_v2", type_="check")
    op.drop_constraint("uq_media_v2_attachment", "media_rights_v2", type_="unique")
    op.drop_constraint("fk_media_v2_attachment", "media_rights_v2", type_="foreignkey")
    op.drop_column("media_rights_v2", "preview_byte_size")
    op.drop_column("media_rights_v2", "preview_mime_type")
    op.drop_column("media_rights_v2", "preview_sha256")
    op.drop_column("media_rights_v2", "preview_object_key")
    op.drop_column("media_rights_v2", "rights_evidence_ref")
    op.drop_column("media_rights_v2", "attachment_id")
