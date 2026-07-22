from pathlib import Path

COMPOSE = Path("infra/compose/compose.yaml")
ENV_EXAMPLE = Path(".env.example")
MOUNT_SCRIPT = Path("scripts/mount_personal_data.ps1")
MAKEFILE = Path("Makefile")
CI_WORKFLOW = Path(".github/workflows/ci.yml")


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


def test_ci_integration_uses_an_explicit_ephemeral_data_root() -> None:
    workflow = CI_WORKFLOW.read_text(encoding="utf-8")

    integration = workflow.split("  integration:\n", 1)[1].split(
        "  schema-validation:\n", 1
    )[0]
    assert "SRBG_DATA_ROOT: /tmp/srbg-data" in integration
    for preparation in (
        'sudo install -d -m 0700 -o 999 -g 999 "$SRBG_DATA_ROOT/postgres"',
        'sudo install -d -m 0700 -o 999 -g 999 "$SRBG_DATA_ROOT/postgres-wal"',
        'sudo install -d -m 0750 -o 999 -g 1000 "$SRBG_DATA_ROOT/redis"',
        'sudo install -d -m 0750 -o 1000 -g 1000 "$SRBG_DATA_ROOT/minio"',
        'sudo install -d -m 0750 -o 1000 -g 1000 "$SRBG_DATA_ROOT/anchor-minio"',
        'sudo install -d -m 0750 -o 65534 -g 65534 "$SRBG_DATA_ROOT/prometheus"',
        'sudo install -d -m 0750 -o 472 -g 0 "$SRBG_DATA_ROOT/grafana"',
    ):
        assert preparation in integration
