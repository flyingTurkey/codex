from pathlib import Path

COMPOSE = Path("infra/compose/compose.yaml")
ENV_EXAMPLE = Path(".env.example")
MOUNT_SCRIPT = Path("scripts/mount_personal_data.ps1")
MAKEFILE = Path("Makefile")


def test_compose_uses_the_external_personal_data_root_for_business_state() -> None:
    compose = COMPOSE.read_text(encoding="utf-8")
    for directory, target in (
        ("postgres", "/var/lib/postgresql/data"),
        ("postgres-wal", "/wal-archive"),
        ("minio", "/data"),
        ("anchor-minio", "/data"),
        ("redis", "/data"),
        ("prometheus", "/prometheus"),
        ("grafana", "/var/lib/grafana"),
    ):
        assert (
            "${SRBG_DATA_ROOT:?SRBG_DATA_ROOT must point to the mounted D-drive "
            f"ext4 data root}}/{directory}:{target}"
        ) in compose


def test_external_personal_data_root_is_explicit_and_old_volumes_are_not_reused() -> None:
    compose = COMPOSE.read_text(encoding="utf-8")
    environment = ENV_EXAMPLE.read_text(encoding="utf-8")
    assert "SRBG_DATA_ROOT=/mnt/host/wsl/SRBGDataDisk/srv" in environment
    assert "SRBG_SOURCE_DISCOVERY_ENABLED: ${SRBG_SOURCE_DISCOVERY_ENABLED:-true}" in compose
    assert "SRBG_SOURCE_DISCOVERY_ENABLED=false" in environment
    for declaration in (
        "  postgres-data:",
        "  postgres-wal-archive:",
        "  redis-data:",
        "  minio-data:",
        "  anchor-minio-data:",
        "  prometheus-data:",
        "  grafana-data:",
    ):
        assert declaration not in compose


def test_runtime_refuses_to_start_without_the_verified_d_drive_vhd_mount() -> None:
    script = MOUNT_SCRIPT.read_text(encoding="utf-8")
    makefile = MAKEFILE.read_text(encoding="utf-8")
    for token in (
        "D:\\SRBGData\\srbg-data.vhdx",
        "SRBGDataDisk",
        "/mnt/host/wsl/SRBGDataDisk/srv",
        "wsl.exe --mount --vhd",
        "PERSONAL_DATA_MOUNT_FAILED",
    ):
        assert token in script
    assert "dev: personal-data-ready" in makefile
    assert "runtime-ready: personal-data-ready" in makefile
