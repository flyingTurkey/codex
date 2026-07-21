from pathlib import Path

MIGRATION = Path("apps/api/migrations/versions/0046_owner_gold_prediction_seal.py")


def test_migration_adds_append_only_prediction_seal_without_private_payloads() -> None:
    source = MIGRATION.read_text(encoding="utf-8")

    for marker in (
        'revision = "0046_owner_gold_prediction_seal"',
        'down_revision = "0045_t12_media_delivery"',
        '"owner_gold_prediction_seal_v2"',
        '"prediction_seal_sha256"',
        "prevent_owner_gold_prediction_seal_mutation",
        "OWNER_GOLD_PREDICTION_SEAL_DOWNGRADE_BLOCKED",
        "srbg_api_role",
        "srbg_worker_role",
        "srbg_publication_writer",
    ):
        assert marker in source

    assert "predicted_relevant" not in source
    assert "confidence_bps" not in source
    assert "normalized_content" not in source
    assert "INSERT INTO owner_gold_prediction_seal_v2" not in source
