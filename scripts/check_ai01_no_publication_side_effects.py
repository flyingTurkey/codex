"""Fail if AI preparation bypasses the PublicationService writer boundary.

PERS-07 extends the original R-AI01 preparation slice with SUMMARIZE/VERIFY and a
durable outbox handoff. Direct feed/search/daily writes remain forbidden here.
"""

from pathlib import Path

FILES = (
    Path("apps/api/src/srbg_api/ai_pipeline/content_preparation.py"),
    Path("apps/worker/src/srbg_worker/ai_content_preparation.py"),
)
FORBIDDEN = (
    "PublicationService(",
    "publish_item(",
    "publication_version",
    "feed_projection",
    "daily_report",
)


def main() -> None:
    for path in FILES:
        source = path.read_text(encoding="utf-8")
        for marker in FORBIDDEN:
            if marker in source:
                raise SystemExit(f"R-AI01 side-effect boundary violated: {path}:{marker}")
    print("AI preparation PublicationService boundary passed")


if __name__ == "__main__":
    main()
