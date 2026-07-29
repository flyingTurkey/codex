"""Fail unless the Alembic repository has exactly one head."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory


def validate_single_head(heads: Sequence[str]) -> str:
    normalized = tuple(heads)
    if len(normalized) != 1:
        raise RuntimeError(f"migration repository must have exactly one Alembic head: {normalized}")
    return normalized[0]


def main(arguments: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("apps/api/alembic.ini"),
    )
    namespace = parser.parse_args(arguments)
    config = Config(str(namespace.config))
    head = validate_single_head(ScriptDirectory.from_config(config).get_heads())
    print(head)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
