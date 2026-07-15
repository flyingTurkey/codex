"""Replay the Round 09 Alembic boundary on an isolated local database."""

from __future__ import annotations

import ipaddress
import os
import re
from urllib.parse import urlsplit

from alembic import command
from alembic.config import Config

_DISPOSABLE_DATABASE = re.compile(r"srbg_it_[0-9a-f]{24}\Z")


def _is_loopback(host: str | None) -> bool:
    if host is None:
        return False
    if host.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def main() -> None:
    parsed = urlsplit(
        os.environ.get("SRBG_DATABASE_URL", "").replace(
            "postgresql+asyncpg", "postgresql", 1
        )
    )
    database_name = parsed.path.removeprefix("/")
    if not _is_loopback(parsed.hostname) or _DISPOSABLE_DATABASE.fullmatch(database_name) is None:
        raise RuntimeError("Round09 migration replay requires an isolated loopback database")
    config = Config("apps/api/alembic.ini")
    command.upgrade(config, "0009_dedup_events_scoring")
    command.upgrade(config, "0010_ai_editorial_governance")
    command.downgrade(config, "0009_dedup_events_scoring")
    command.upgrade(config, "0010_ai_editorial_governance")
    print("Round09 migration replay passed: 0009 -> 0010 -> 0009 -> 0010")


if __name__ == "__main__":
    main()
