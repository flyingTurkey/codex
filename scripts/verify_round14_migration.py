"""Replay the Round 14 expand migration on an isolated loopback database."""

from __future__ import annotations

import ipaddress
import os
import re
from urllib.parse import urlsplit

from alembic import command
from alembic.config import Config

_DISPOSABLE_DATABASE = re.compile(r"srbg_it_[0-9a-f]{24}\Z")


def main() -> None:
    parsed = urlsplit(
        os.environ.get("SRBG_DATABASE_URL", "").replace("postgresql+asyncpg", "postgresql", 1)
    )
    database_name = parsed.path.removeprefix("/")
    host = parsed.hostname
    try:
        loopback = host == "localhost" or (
            host is not None and ipaddress.ip_address(host).is_loopback
        )
    except ValueError:
        loopback = False
    if not loopback or _DISPOSABLE_DATABASE.fullmatch(database_name) is None:
        raise RuntimeError("Round14 migration replay requires an isolated loopback database")
    config = Config("apps/api/alembic.ini")
    command.upgrade(config, "0013_internal_projection")
    command.upgrade(config, "0014_event_unification")
    command.downgrade(config, "0013_internal_projection")
    command.upgrade(config, "0014_event_unification")
    print("Round14 migration replay passed: 0013 -> 0014 -> 0013 -> 0014")


if __name__ == "__main__":
    main()
