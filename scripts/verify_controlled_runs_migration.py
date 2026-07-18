# ruff: noqa: E501, S101
"""Replay 0030 -> 0031 -> 0030 -> 0031 on an isolated loopback database."""

from __future__ import annotations

import asyncio
import ipaddress
import os
import re
from datetime import UTC, datetime, timedelta
from urllib.parse import urlsplit
from uuid import UUID

from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import create_async_engine

_DISPOSABLE_DATABASE = re.compile(r"srbg_it_[0-9a-f]{24}\Z")
_RUN = UUID("019b0000-0000-7000-8000-000000003101")
_ATTEMPT = UUID("019b0000-0000-7000-8000-000000003102")


def _url() -> str:
    value = os.environ.get("SRBG_DATABASE_URL", "")
    parsed = urlsplit(value.replace("postgresql+asyncpg", "postgresql", 1))
    database = parsed.path.removeprefix("/")
    try:
        loopback = parsed.hostname == "localhost" or (
            parsed.hostname is not None and ipaddress.ip_address(parsed.hostname).is_loopback
        )
    except ValueError:
        loopback = False
    if not loopback or _DISPOSABLE_DATABASE.fullmatch(database) is None:
        raise RuntimeError("0031 replay requires an isolated loopback database")
    return value


async def _head(database_url: str, expected: str) -> None:
    engine = create_async_engine(database_url)
    try:
        async with engine.connect() as connection:
            assert (
                await connection.scalar(text("SELECT version_num FROM alembic_version")) == expected
            )
    finally:
        await engine.dispose()


async def _exercise(database_url: str) -> None:
    engine = create_async_engine(database_url)
    now = datetime.now(UTC)
    try:
        async with engine.begin() as connection:
            source_id = await connection.scalar(
                text("SELECT id FROM source WHERE base_url='https://www.gov.cn/zhengce/'")
            )
            assert source_id is not None
            await connection.execute(
                text(
                    "INSERT INTO personal_controlled_run(id,state,wall_started_at,wall_deadline,created_at,updated_at) "
                    "VALUES(:id,'RUNNING',:now,:deadline,:now,:now)"
                ),
                {"id": _RUN, "now": now, "deadline": now + timedelta(hours=4)},
            )
            await connection.execute(
                text(
                    "INSERT INTO personal_controlled_run_source(run_id,source_id,seed_url,expected_host,path_prefix) "
                    "VALUES(:run,:source,'https://www.gov.cn/zhengce/','www.gov.cn','/zhengce/')"
                ),
                {"run": _RUN, "source": source_id},
            )
            allowance = await connection.scalar(
                text(
                    "SELECT reserve_personal_controlled_http_attempt(:attempt,:run,:source,'PROBE',"
                    ":hash,'www.gov.cn','/zhengce/',1024,:now)"
                ),
                {
                    "attempt": _ATTEMPT,
                    "run": _RUN,
                    "source": source_id,
                    "hash": "0" * 64,
                    "now": now,
                },
            )
            assert allowance == 1024
            assert (
                await connection.scalar(
                    text(
                        "SELECT settle_personal_controlled_http_attempt(:attempt,12,false,NULL,:now)"
                    ),
                    {"attempt": _ATTEMPT, "now": now + timedelta(seconds=1)},
                )
                == "RUNNING"
            )
        try:
            async with engine.begin() as connection:
                await connection.scalar(
                    text(
                        "SELECT reserve_personal_controlled_http_attempt(:attempt,:run,:source,'PROBE',"
                        ":hash,'www.gov.cn','/outside',1024,:now)"
                    ),
                    {
                        "attempt": UUID("019b0000-0000-7000-8000-000000003103"),
                        "run": _RUN,
                        "source": source_id,
                        "hash": "1" * 64,
                        "now": now + timedelta(minutes=2),
                    },
                )
        except DBAPIError as error:
            assert "CONTROLLED_RUN_PATH_DENIED" in str(error)
        else:
            raise AssertionError("outside-path reservation was accepted")
    finally:
        await engine.dispose()


async def _cleanup(database_url: str) -> None:
    engine = create_async_engine(database_url)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text("DELETE FROM personal_controlled_http_attempt WHERE run_id=:run"),
                {"run": _RUN},
            )
            await connection.execute(
                text("DELETE FROM personal_controlled_run_source WHERE run_id=:run"), {"run": _RUN}
            )
            await connection.execute(
                text("DELETE FROM personal_controlled_run WHERE id=:run"), {"run": _RUN}
            )
    finally:
        await engine.dispose()


def main() -> None:
    database_url = _url()
    config = Config("apps/api/alembic.ini")
    command.upgrade(config, "0031_controlled_personal_runs")
    asyncio.run(_head(database_url, "0031_controlled_personal_runs"))
    asyncio.run(_exercise(database_url))
    try:
        command.downgrade(config, "0030_pers10_role_archive_repair")
    except RuntimeError as error:
        assert "CONTROLLED_RUN_DOWNGRADE_BLOCKED" in str(error)
    else:
        raise AssertionError("0031 downgrade accepted controlled-run facts")
    asyncio.run(_cleanup(database_url))
    command.downgrade(config, "0030_pers10_role_archive_repair")
    asyncio.run(_head(database_url, "0030_pers10_role_archive_repair"))
    command.upgrade(config, "0031_controlled_personal_runs")
    asyncio.run(_head(database_url, "0031_controlled_personal_runs"))
    print("Controlled-run migration replay passed: 0030 -> 0031 -> 0030 -> 0031")


if __name__ == "__main__":
    main()
