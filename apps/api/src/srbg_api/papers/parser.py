"""Deterministic OpenAlex metadata parsing with explicit copyright inputs."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal

from srbg_api.papers.domain import PaperAccessInput, determine_access_level, normalize_doi


@dataclass(frozen=True, slots=True)
class ParsedPaperAuthor:
    name: str
    orcid: str | None
    institutions: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ParsedPaper:
    external_id: str
    doi: str | None
    title: str
    journal: str | None
    issns: tuple[str, ...]
    authors: tuple[ParsedPaperAuthor, ...]
    volume: str | None
    issue: str | None
    pages: str | None
    year: int | None
    abstract: str | None
    keywords: tuple[str, ...]
    paper_type: Literal["ARTICLE", "REVIEW", "METHOD", "CASE_STUDY", "OTHER", "UNKNOWN"]
    access_level: str
    open_status: Literal["OPEN", "CLOSED", "UNKNOWN"]
    open_license: str | None
    open_fulltext_url: str | None
    retracted: bool


def parse_openalex_work(
    payload: Mapping[str, Any],
    *,
    abstract_licensed: bool,
    fulltext_licensed: bool,
) -> ParsedPaper:
    external_id = _required_string(payload, "id").rstrip("/").split("/")[-1]
    title = _required_string(payload, "title")
    location = payload.get("best_oa_location") or payload.get("primary_location") or {}
    if not isinstance(location, Mapping):
        location = {}
    source = location.get("source")
    source = source if isinstance(source, Mapping) else {}
    pdf_url = location.get("pdf_url") if isinstance(location.get("pdf_url"), str) else None
    licence = location.get("license") if isinstance(location.get("license"), str) else None
    access = determine_access_level(
        PaperAccessInput(
            abstract_licensed=abstract_licensed,
            fulltext_url_present=pdf_url is not None,
            fulltext_licensed=fulltext_licensed and licence is not None,
        )
    )
    abstract = None
    inverted = payload.get("abstract_inverted_index")
    if abstract_licensed and isinstance(inverted, Mapping):
        abstract = _restore_abstract(inverted)
    authors: list[ParsedPaperAuthor] = []
    for authorship in payload.get("authorships", []):
        if not isinstance(authorship, Mapping):
            continue
        author = authorship.get("author")
        if not isinstance(author, Mapping) or not isinstance(author.get("display_name"), str):
            continue
        institutions = tuple(
            str(institution["display_name"]).strip()
            for institution in authorship.get("institutions", [])
            if isinstance(institution, Mapping)
            and isinstance(institution.get("display_name"), str)
            and str(institution["display_name"]).strip()
        )
        authors.append(
            ParsedPaperAuthor(
                name=str(author["display_name"]).strip(),
                orcid=author.get("orcid") if isinstance(author.get("orcid"), str) else None,
                institutions=institutions,
            )
        )
    biblio = payload.get("biblio")
    biblio = biblio if isinstance(biblio, Mapping) else {}
    first_page = biblio.get("first_page")
    last_page = biblio.get("last_page")
    pages = None
    if isinstance(first_page, str):
        pages = first_page if not isinstance(last_page, str) else f"{first_page}-{last_page}"
    open_access = payload.get("open_access")
    open_access = open_access if isinstance(open_access, Mapping) else {}
    is_oa = open_access.get("is_oa")
    open_status: Literal["OPEN", "CLOSED", "UNKNOWN"] = (
        "OPEN" if is_oa is True else "CLOSED" if is_oa is False else "UNKNOWN"
    )
    issn_values = source.get("issn")
    issns = tuple(str(value) for value in issn_values) if isinstance(issn_values, list) else ()
    return ParsedPaper(
        external_id=external_id,
        doi=normalize_doi(payload.get("doi") if isinstance(payload.get("doi"), str) else None),
        title=title,
        journal=source.get("display_name") if isinstance(source.get("display_name"), str) else None,
        issns=issns,
        authors=tuple(authors),
        volume=biblio.get("volume") if isinstance(biblio.get("volume"), str) else None,
        issue=biblio.get("issue") if isinstance(biblio.get("issue"), str) else None,
        pages=pages,
        year=payload.get("publication_year")
        if isinstance(payload.get("publication_year"), int)
        else None,
        abstract=abstract,
        keywords=tuple(
            str(keyword["display_name"]).strip()
            for keyword in payload.get("keywords", [])
            if isinstance(keyword, Mapping)
            and isinstance(keyword.get("display_name"), str)
            and str(keyword["display_name"]).strip()
        ),
        paper_type=_paper_type(payload.get("type")),
        access_level=access,
        open_status=open_status,
        open_license=licence if access == "OPEN_FULLTEXT" else None,
        open_fulltext_url=pdf_url if access == "OPEN_FULLTEXT" else None,
        retracted=payload.get("is_retracted") is True,
    )


def _required_string(payload: Mapping[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"OpenAlex work is missing {key}")
    return value.strip()


def _paper_type(
    value: object,
) -> Literal["ARTICLE", "REVIEW", "METHOD", "CASE_STUDY", "OTHER", "UNKNOWN"]:
    mapping = {
        "article": "ARTICLE",
        "review": "REVIEW",
        "methods-article": "METHOD",
        "case-report": "CASE_STUDY",
    }
    if not isinstance(value, str):
        return "UNKNOWN"
    return mapping.get(value.casefold(), "OTHER")  # type: ignore[return-value]


def _restore_abstract(inverted: Mapping[str, Any]) -> str | None:
    positioned: list[tuple[int, str]] = []
    for word, positions in inverted.items():
        if not isinstance(word, str) or not isinstance(positions, list):
            continue
        positioned.extend((position, word) for position in positions if isinstance(position, int))
    positioned.sort()
    return " ".join(word for _, word in positioned) or None
