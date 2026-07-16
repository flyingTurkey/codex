"""Provision the test-only Round 17 LEO signing key without disclosing it."""

from __future__ import annotations

import os
from base64 import b64encode
from hashlib import sha256
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

LEO_ACTOR_ID = "019f6b65-4cf5-71d1-b75c-a6c908912f58"


def _replace_env_values(content: str, updates: dict[str, str]) -> str:
    retained = [
        line
        for line in content.splitlines()
        if line.split("=", 1)[0].strip() not in updates
    ]
    if retained and retained[-1]:
        retained.append("")
    retained.extend(f"{name}={value}" for name, value in updates.items())
    return "\n".join(retained) + "\n"


def configure_signed_local_pilot(env_path: Path) -> dict[str, str]:
    """Rotate the coupled Ed25519 fields atomically and return only the fingerprint."""

    private_key = Ed25519PrivateKey.generate()
    private_bytes = private_key.private_bytes(
        serialization.Encoding.Raw,
        serialization.PrivateFormat.Raw,
        serialization.NoEncryption(),
    )
    public_bytes = private_key.public_key().public_bytes(
        serialization.Encoding.Raw,
        serialization.PublicFormat.Raw,
    )
    fingerprint = sha256(public_bytes).hexdigest()
    updates = {
        "SRBG_ENVIRONMENT": "test",
        "SRBG_ROUND17_AUTHORITY_MODE": "SIGNED_LOCAL_PILOT",
        "SRBG_ROUND17_LEO_APPROVER_ACTOR_ID": LEO_ACTOR_ID,
        "SRBG_ROUND17_LEO_SIGNING_PRIVATE_KEY_BASE64": b64encode(private_bytes).decode(),
        "SRBG_ROUND17_LEO_SIGNING_PUBLIC_KEY_BASE64": b64encode(public_bytes).decode(),
        "SRBG_ROUND17_LEO_SIGNING_PUBLIC_KEY_SHA256": fingerprint,
        "SRBG_ROUND17_EVENTIZATION_TRUSTED_PUBLIC_KEY_BASE64": b64encode(
            public_bytes
        ).decode(),
        "SRBG_ROUND17_EVENTIZATION_TRUSTED_PUBLIC_KEY_SHA256": fingerprint,
    }
    existing = env_path.read_text(encoding="utf-8") if env_path.exists() else ""
    rendered = _replace_env_values(existing, updates)
    temporary = env_path.with_name(f".{env_path.name}.round17.tmp")
    try:
        temporary.write_text(rendered, encoding="utf-8", newline="\n")
        try:
            temporary.chmod(0o600)
        except OSError:
            pass
        os.replace(temporary, env_path)
    finally:
        temporary.unlink(missing_ok=True)
    return {"public_key_sha256": fingerprint}


def main() -> None:
    result = configure_signed_local_pilot(Path(".env"))
    print(f"Round17 signed-local key configured; public fingerprint={result['public_key_sha256']}")


if __name__ == "__main__":
    main()
