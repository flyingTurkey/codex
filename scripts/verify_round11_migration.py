"""Replay the Round 11 Alembic boundary on an isolated loopback database."""

from __future__ import annotations

import ipaddress
import os
import re
from urllib.parse import urlsplit

from alembic import command
from alembic.config import Config

_DISPOSABLE_DATABASE = re.compile(r'srbg_it_[0-9a-f]{24}\Z')


def _is_loopback(host: str | None) -> bool:
    if host is None:
        return False
    if host.lower() == 'localhost':
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def main() -> None:
    parsed = urlsplit(
        os.environ.get('SRBG_DATABASE_URL', '').replace('postgresql+asyncpg', 'postgresql', 1),
    )
    database_name = parsed.path.removeprefix('/')
    if not _is_loopback(parsed.hostname) or _DISPOSABLE_DATABASE.fullmatch(database_name) is None:
        raise RuntimeError('Round11 migration replay requires an isolated loopback database')
    config = Config('apps/api/alembic.ini')
    command.upgrade(config, '0011_feed_search_daily')
    command.upgrade(config, '0012_operations_readiness')
    command.downgrade(config, '0011_feed_search_daily')
    command.upgrade(config, '0012_operations_readiness')
    print('Round11 migration replay passed: 0011 -> 0012 -> 0011 -> 0012')


if __name__ == '__main__':
    main()
