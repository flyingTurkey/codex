"""Write-only local AI secrets for development, test, and isolated demonstrations."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from srbg_api.ai_pipeline.catalog import ProviderCode


class SecretStorageDisabled(RuntimeError):
    pass


class LocalAiSecretStore:
    _ALLOWED_ENVIRONMENTS = frozenset({"demo", "development", "test"})

    def __init__(self, *, root: Path, environment: str) -> None:
        self._root = root.resolve()
        self._environment = environment.casefold()

    def put(self, provider: ProviderCode, secret: str) -> None:
        if self._environment not in self._ALLOWED_ENVIRONMENTS:
            raise SecretStorageDisabled("MODEL_DISABLED: local Secret storage is disabled")
        if not secret or len(secret) > 4096 or "\x00" in secret or "\r" in secret or "\n" in secret:
            raise ValueError("AI Secret has an invalid shape")
        self._root.mkdir(mode=0o700, parents=True, exist_ok=True)
        target = self._root / f"{provider.value}.key"
        descriptor, temporary_name = tempfile.mkstemp(prefix=".ai-secret-", dir=self._root)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as handle:
                handle.write(secret)
                handle.flush()
                os.fsync(handle.fileno())
            os.chmod(temporary_name, 0o600)
            os.replace(temporary_name, target)
        finally:
            if os.path.exists(temporary_name):
                os.unlink(temporary_name)

    def is_configured(self, provider: ProviderCode) -> bool:
        path = self._root / f"{provider.value}.key"
        return path.is_file() and path.stat().st_size > 0

    def __repr__(self) -> str:
        return f"LocalAiSecretStore(environment={self._environment!r}, root=<redacted>)"
