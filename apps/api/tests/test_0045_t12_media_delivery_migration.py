from pathlib import Path

MIGRATION = (
    Path(__file__).parents[1]
    / "migrations"
    / "versions"
    / "0045_t12_media_delivery.py"
)


def test_t12_binds_delivery_to_clean_attachment_and_safe_preview_facts() -> None:
    source = MIGRATION.read_text(encoding="utf-8")

    for token in (
        'revision = "0045_t12_media_delivery"',
        'down_revision = "0044_t11_reader_appendix"',
        'sa.Column("attachment_id"',
        'sa.Column("rights_evidence_ref"',
        'sa.Column("preview_object_key"',
        'sa.Column("preview_sha256"',
        'sa.Column("preview_mime_type"',
        'sa.Column("preview_byte_size"',
        'op.create_unique_constraint(',
        "ck_media_v2_preview_bundle",
        "trg_media_v2_authority",
        "document_attachment",
        "document_attachment_attempt",
        "security_status='CLEAN'",
        "outcome='ACCEPTED'",
        "load_clean_media_attachment_v2",
        "LANGUAGE sql SECURITY DEFINER",
        "GRANT EXECUTE ON FUNCTION load_clean_media_attachment_v2",
        "TO srbg_publication_writer",
        "CREATE VIEW media_delivery_reader_v2 WITH (security_barrier=true)",
        "GRANT SELECT ON media_delivery_reader_v2 TO srbg_projection_reader",
    ):
        assert token in source


def test_t12_migration_has_a_forward_path_and_reversible_schema_rollback() -> None:
    source = MIGRATION.read_text(encoding="utf-8")

    assert "def upgrade()" in source
    assert "def downgrade()" in source
    assert "DROP TRIGGER IF EXISTS trg_media_v2_authority" in source
    assert "DROP FUNCTION IF EXISTS load_clean_media_attachment_v2" in source
    assert "DROP VIEW IF EXISTS media_delivery_reader_v2" in source
    assert source.count("op.drop_column(\"media_rights_v2\"") >= 6
