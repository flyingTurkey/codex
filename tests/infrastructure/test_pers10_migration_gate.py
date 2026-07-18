from subprocess import CompletedProcess

import pytest

from scripts import run_pers10_migration_gate as gate
from scripts.run_pers10_migration_gate import IMAGE, _validated_port


def test_pers10_gate_pins_postgres_and_accepts_only_loopback_bindings() -> None:
    assert IMAGE == "srbg-postgres:17.10-pgvector-0.8.2"
    assert _validated_port("127.0.0.1:49152\n") == 49152
    for unsafe in ("0.0.0.0:49152", "[::]:49152", "127.0.0.1:0", "remote:5432"):
        with pytest.raises(RuntimeError):
            _validated_port(unsafe)


def test_pers10_gate_rejects_green_result_when_disposable_cleanup_fails(monkeypatch) -> None:
    def fake_run(command, *, environment):
        if tuple(command[:3]) == ("docker", "rm", "--force"):
            return CompletedProcess(command, 1, "", "cleanup failed")
        if tuple(command[:2]) == ("docker", "port"):
            return CompletedProcess(command, 0, "127.0.0.1:49152\n", "")
        return CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(gate, "_run", fake_run)
    monkeypatch.setattr(
        gate.subprocess,
        "run",
        lambda *args, **kwargs: CompletedProcess(args[0], 0, "", ""),
    )

    assert gate.main(("tests/infrastructure/test_pers10_migration_gate.py", "-q")) == 1
