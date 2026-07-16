from __future__ import annotations

import json
from base64 import b64decode, b64encode
from datetime import UTC, datetime
from hashlib import sha256

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from scripts.round17_sign_approval import canonical_json, sign_atomic_authority


def test_atomic_authority_signature_covers_all_frozen_decisions() -> None:
    private_key = Ed25519PrivateKey.generate()
    private_bytes = private_key.private_bytes(
        serialization.Encoding.Raw,
        serialization.PrivateFormat.Raw,
        serialization.NoEncryption(),
    )
    authority = {
        "schema_version": "round17-authority-v1",
        "roster_version": "r17-sources-v0.1",
        "sources": [{"source_code": f"SRC-{index:02d}"} for index in range(20)],
        "window": {"duration_hours": 168, "automatic_start": False},
        "reference_model": "LEO_SINGLE_EXPERT_REFERENCE_SET",
    }

    package = sign_atomic_authority(
        authority,
        private_key_base64=b64encode(private_bytes).decode(),
        signed_at=datetime(2026, 7, 16, tzinfo=UTC),
    )

    assert package["schema_version"] == "round17-signed-approval-v1"
    assert package["approval_type"] == "ROUND17_ATOMIC_AUTHORITY"
    assert package["approval_document"] == authority
    assert package["approval_document_sha256"] == sha256(
        canonical_json(authority)
    ).hexdigest()
    public_key = Ed25519PublicKey.from_public_bytes(
        b64decode(package["signer_public_key_base64"], validate=True)
    )
    public_key.verify(
        b64decode(package["approval_signature"], validate=True),
        canonical_json(authority),
    )
    assert "private" not in json.dumps(package).lower()
