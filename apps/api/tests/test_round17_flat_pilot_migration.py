from __future__ import annotations

from pathlib import Path

MIGRATION = Path("apps/api/migrations/versions/0017c_round17_flat_pilot.py")


def test_flat_pilot_migration_is_forward_only_from_round17b() -> None:
    source = MIGRATION.read_text(encoding="utf-8")

    assert 'revision = "0017c_round17_flat_pilot"' in source
    assert 'down_revision = "0017b_round17_pilot"' in source
    assert '"authority_mode"' in source
    assert "SIGNED_LOCAL_PILOT" in source
    assert "ck_round17_staff_authority_mode" in source
    assert "ck_round17_staff_identity_assurance" in source
    assert "ck_round17_staff_identity_hashes" in source
    assert "oidc_issuer_sha256 IS NULL" in source


def test_flat_pilot_persists_signed_approval_and_single_expert_reference_facts() -> None:
    source = MIGRATION.read_text(encoding="utf-8")

    assert '"round17_signed_approval"' in source
    assert '"approval_document"' in source
    assert '"approval_signature"' in source
    assert '"signer_public_key_sha256"' in source
    assert '"valid_until"' in source
    assert '"round17_reference_annotation"' in source
    assert '"annotator_id"' in source
    assert '"LEO_SINGLE_EXPERT_REFERENCE_SET"' in source


def test_flat_pilot_tables_are_not_directly_writable_by_application_roles() -> None:
    source = MIGRATION.read_text(encoding="utf-8")

    assert "REVOKE ALL ON round17_signed_approval FROM srbg_api_role" in source
    assert "REVOKE ALL ON round17_reference_annotation FROM srbg_api_role" in source
    assert "GRANT SELECT ON round17_signed_approval TO srbg_api_role" in source
    assert "GRANT SELECT ON round17_reference_annotation TO srbg_api_role" in source
