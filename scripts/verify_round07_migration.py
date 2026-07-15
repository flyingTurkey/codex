"""Replay the Round 07 Alembic boundary on an isolated local database."""

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
    database_url = os.environ.get("SRBG_DATABASE_URL", "")
    parsed = urlsplit(database_url.replace("postgresql+asyncpg", "postgresql", 1))
    database_name = parsed.path.removeprefix("/")
    if not _is_loopback(parsed.hostname) or _DISPOSABLE_DATABASE.fullmatch(database_name) is None:
        raise RuntimeError("Round07 migration replay requires an isolated loopback database")

    config = Config("apps/api/alembic.ini")
    command.upgrade(config, "0007_papers")
    command.upgrade(config, "0008_technology_products")
    command.downgrade(config, "0007_papers")
    command.upgrade(config, "0008_technology_products")
    print("Round07 migration replay passed: 0007 -> 0008 -> 0007 -> 0008")


if __name__ == "__main__":
    main()
