"""Replay the Round 04 Alembic boundary on an isolated local database."""

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
        raise RuntimeError("Round04 migration replay requires an isolated loopback database")

    config = Config("apps/api/alembic.ini")
    command.upgrade(config, "0004_pdf_ocr_versioning")
    command.upgrade(config, "head")
    command.downgrade(config, "0004_pdf_ocr_versioning")
    command.upgrade(config, "head")
    print("Round04 migration replay passed: 0004 -> 0005 -> 0004 -> 0005")


if __name__ == "__main__":
    main()
