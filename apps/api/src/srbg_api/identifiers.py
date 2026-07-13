"""Identifier helpers."""

import secrets
import time
from uuid import UUID


def uuid7() -> UUID:
    """Generate an RFC 9562 UUIDv7 using UTC Unix epoch milliseconds."""

    timestamp_ms = time.time_ns() // 1_000_000
    random_a = secrets.randbits(12)
    random_b = secrets.randbits(62)
    value = (
        ((timestamp_ms & ((1 << 48) - 1)) << 80)
        | (0x7 << 76)
        | (random_a << 64)
        | (0b10 << 62)
        | random_b
    )
    return UUID(int=value)
