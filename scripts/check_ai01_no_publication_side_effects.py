"""Fail if R-AI01 implementation calls publication or summary paths."""

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
    "AiStep.SUMMARIZE",
)


def main() -> None:
    for path in FILES:
        source = path.read_text(encoding="utf-8")
        for marker in FORBIDDEN:
            if marker in source:
                raise SystemExit(f"R-AI01 side-effect boundary violated: {path}:{marker}")
    print("R-AI01 no-publication side-effect boundary passed")


if __name__ == "__main__":
    main()
