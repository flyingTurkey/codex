"""Check local Markdown links without browser or network access."""

from __future__ import annotations

import argparse
import re
from collections.abc import Sequence
from pathlib import Path
from urllib.parse import unquote

MARKDOWN_LINK = re.compile(r"!?\[[^\]]*]\((?P<target>[^)]+)\)")
IGNORED_PREFIXES = ("http://", "https://", "mailto:", "#", "data:")


def broken_links(repository: Path) -> list[str]:
    failures: list[str] = []
    for document in sorted(repository.rglob("*.md")):
        ignored = {".git", ".cache", ".tools", ".venv", "node_modules"}
        if any(part in ignored for part in document.parts):
            continue
        content = document.read_text(encoding="utf-8")
        for match in MARKDOWN_LINK.finditer(content):
            raw_target = match.group("target").strip().strip("<>")
            if not raw_target or raw_target.startswith(IGNORED_PREFIXES):
                continue
            path_part = unquote(raw_target.split("#", 1)[0])
            if not path_part:
                continue
            target = (document.parent / path_part).resolve()
            try:
                target.relative_to(repository)
            except ValueError:
                failures.append(
                    f"{document.relative_to(repository)}: "
                    f"link escapes repository: {raw_target}"
                )
                continue
            if not target.exists():
                failures.append(
                    f"{document.relative_to(repository)}: "
                    f"missing link target: {raw_target}"
                )
    return failures


def main(arguments: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", type=Path, default=Path.cwd())
    namespace = parser.parse_args(arguments)
    failures = broken_links(namespace.repository.resolve())
    if failures:
        print("\n".join(failures))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
