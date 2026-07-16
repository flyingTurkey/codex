"""Create the public, verifiable LEO approval package for the Round 17 roster."""

from __future__ import annotations

import json
from base64 import b64decode, b64encode
from binascii import Error as BinasciiError
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from srbg_api.config import get_settings

AUTHORITY = Path("docs/codex-kit/assets/validation/round17_approved_authority.json")
OUTPUT = Path("docs/acceptance/assets/round17/leo-signed-approval.json")


def canonical_json(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode()


def sign_atomic_authority(
    authority: dict[str, Any],
    *,
    private_key_base64: str,
    signed_at: datetime,
) -> dict[str, Any]:
    try:
        private_bytes = b64decode(private_key_base64, validate=True)
        private_key = Ed25519PrivateKey.from_private_bytes(private_bytes)
    except (BinasciiError, ValueError) as error:
        raise ValueError("Round17 private signing key is invalid") from error
    document_bytes = canonical_json(authority)
    public_bytes = private_key.public_key().public_bytes(
        serialization.Encoding.Raw,
        serialization.PublicFormat.Raw,
    )
    return {
        "schema_version": "round17-signed-approval-v1",
        "approval_type": "ROUND17_ATOMIC_AUTHORITY",
        "authority_mode": "SIGNED_LOCAL_PILOT",
        "approval_document": authority,
        "approval_document_sha256": sha256(document_bytes).hexdigest(),
        "approval_signature": b64encode(private_key.sign(document_bytes)).decode(),
        "signer_public_key_base64": b64encode(public_bytes).decode(),
        "signer_public_key_sha256": sha256(public_bytes).hexdigest(),
        "approved_by": "019f6b65-4cf5-71d1-b75c-a6c908912f58",
        "approved_by_display_name": "LEO",
        "approved_by_responsibility": "SOURCE_APPROVER",
        "valid_from": signed_at.isoformat().replace("+00:00", "Z"),
        "valid_until": (signed_at + timedelta(days=30)).isoformat().replace("+00:00", "Z"),
    }


def main() -> None:
    settings = get_settings()
    private_key = settings.round17_leo_signing_private_key_base64
    if private_key is None:
        raise RuntimeError("Round17 signing key is not configured")
    authority = json.loads(AUTHORITY.read_text(encoding="utf-8"))
    package = sign_atomic_authority(
        authority,
        private_key_base64=private_key.get_secret_value(),
        signed_at=datetime.now(UTC),
    )
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        json.dumps(package, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(
        "Round17 authority signed; "
        f"document_sha256={package['approval_document_sha256']} "
        f"public_key_sha256={package['signer_public_key_sha256']}"
    )


if __name__ == "__main__":
    main()
