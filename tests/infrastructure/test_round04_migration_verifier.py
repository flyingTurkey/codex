from pathlib import Path


def test_round04_verifier_runs_upgrade_downgrade_upgrade_on_disposable_database() -> None:
    source = Path("scripts/verify_round04_migration.py").read_text(encoding="utf-8")

    assert "0004_pdf_ocr_versioning" in source
    assert 'command.upgrade(config, "head")' in source
    assert 'command.downgrade(config, "0004_pdf_ocr_versioning")' in source
    assert "srbg_it_" in source
    assert "is_loopback" in source
