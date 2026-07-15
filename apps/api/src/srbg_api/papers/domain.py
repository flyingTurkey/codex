# ruff: noqa: RUF001
"""Deterministic, evidence-safe paper identity and presentation rules."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal
from urllib.parse import unquote

AccessLevel = Literal["METADATA_ONLY", "ABSTRACT_ALLOWED", "OPEN_FULLTEXT"]
_DOI_PATTERN = re.compile(r"^10\.\d{4,9}/\S+$", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class PaperAccessInput:
    abstract_licensed: bool
    fulltext_url_present: bool
    fulltext_licensed: bool


def normalize_doi(value: str | None) -> str | None:
    if value is None or not value.strip():
        return None
    normalized = unquote(value).strip().lower()
    normalized = re.sub(r"^(?:https?://(?:dx\.)?doi\.org/|doi\s*:\s*)", "", normalized)
    normalized = "".join(normalized.split()).rstrip(".,;)")
    if not _DOI_PATTERN.fullmatch(normalized):
        raise ValueError("invalid DOI")
    return normalized


def _normalized_text(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).casefold()
    value = re.sub(r"[\s\W_]+", "", value, flags=re.UNICODE)
    return value


def bibliographic_fingerprint(title: str, first_author: str, year: int) -> str:
    if not 1000 <= year <= 9999 or not title.strip() or not first_author.strip():
        raise ValueError("title, first author, and four-digit year are required")
    canonical = "\x1f".join((_normalized_text(title), _normalized_text(first_author), str(year)))
    return hashlib.sha256(canonical.encode()).hexdigest()


def determine_access_level(policy: PaperAccessInput) -> AccessLevel:
    if policy.fulltext_url_present and policy.fulltext_licensed:
        return "OPEN_FULLTEXT"
    if policy.abstract_licensed:
        return "ABSTRACT_ALLOWED"
    return "METADATA_ONLY"


def _citation_value(paper: Mapping[str, Any], key: str) -> str | None:
    value = paper.get(key)
    return str(value).strip() if value is not None and str(value).strip() else None


def format_ris(paper: Mapping[str, Any]) -> str:
    lines = ["TY  - JOUR"]
    for author in paper.get("authors", []):
        lines.append(f"AU  - {str(author).strip()}")
    fields = (
        ("TI", "title"),
        ("JO", "journal"),
        ("PY", "year"),
        ("VL", "volume"),
        ("IS", "issue"),
        ("SP", "pages"),
        ("DO", "doi"),
    )
    for code, key in fields:
        value = _citation_value(paper, key)
        if value:
            lines.append(f"{code}  - {value}")
    lines.append("ER  -")
    return "\r\n".join(lines) + "\r\n"


def _bibtex_escape(value: str) -> str:
    return value.replace("\\", "\\textbackslash{} ").replace("{", "\\{").replace("}", "\\}")


def format_bibtex(paper: Mapping[str, Any]) -> str:
    doi = _citation_value(paper, "doi") or "paper"
    year = _citation_value(paper, "year") or "nd"
    key = re.sub(r"[^a-z0-9]+", "", doi.casefold())[-24:] or f"paper{year}"
    values: list[tuple[str, str]] = []
    authors = [str(author).strip() for author in paper.get("authors", []) if str(author).strip()]
    if authors:
        values.append(("author", " and ".join(authors)))
    for bib_key, source_key in (
        ("title", "title"),
        ("journal", "journal"),
        ("year", "year"),
        ("volume", "volume"),
        ("number", "issue"),
        ("pages", "pages"),
        ("doi", "doi"),
    ):
        value = _citation_value(paper, source_key)
        if value:
            values.append((bib_key, value))
    body = ",\n".join(f"  {name} = {{{_bibtex_escape(value)}}}" for name, value in values)
    return f"@article{{{key},\n{body}\n}}\n"


def format_gbt7714(paper: Mapping[str, Any]) -> str:
    authors = [str(author).strip() for author in paper.get("authors", []) if str(author).strip()]
    author_text = ", ".join(authors[:3])
    if len(authors) > 3:
        author_text += ", 等"
    title = _citation_value(paper, "title") or "题名缺失"
    journal = _citation_value(paper, "journal") or "期刊缺失"
    year = _citation_value(paper, "year") or "日期不详"
    volume = _citation_value(paper, "volume")
    issue = _citation_value(paper, "issue")
    pages = _citation_value(paper, "pages")
    locator = f", {volume or ''}" if volume else ""
    if issue:
        locator += f"({issue})"
    if pages:
        locator += f": {pages}"
    prefix = f"{author_text}. " if author_text else ""
    result = f"{prefix}{title}[J]. {journal}, {year}{locator}."
    doi = _citation_value(paper, "doi")
    return f"{result[:-1]} doi:{doi}." if doi else result


def rank_similar_papers(
    *,
    engineering_domains: Sequence[str],
    technology_tags: Sequence[str],
    candidates: Sequence[Mapping[str, Any]],
    limit: int = 5,
) -> list[dict[str, Any]]:
    domain_set, tag_set = set(engineering_domains), set(technology_tags)
    ranked: list[tuple[int, int, str, dict[str, Any]]] = []
    for candidate in candidates:
        if not candidate.get("visible"):
            continue
        shared_domains = sorted(domain_set.intersection(candidate.get("engineering_domains", [])))
        shared_tags = sorted(tag_set.intersection(candidate.get("technology_tags", [])))
        if not shared_domains and not shared_tags:
            continue
        item = dict(candidate)
        item.pop("visible", None)
        item["match_reasons"] = [f"工程专业：{code}" for code in shared_domains] + [
            f"技术标签：{code}" for code in shared_tags
        ]
        item.pop("score", None)
        ranked.append((-len(shared_domains), -len(shared_tags), str(candidate["id"]), item))
    ranked.sort(key=lambda entry: entry[:3])
    return [entry[3] for entry in ranked[:limit]]
