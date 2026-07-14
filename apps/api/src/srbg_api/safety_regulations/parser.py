"""Rule-based MEM HTML regulation parser with paragraph-addressed evidence."""

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from html.parser import HTMLParser
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

if TYPE_CHECKING:
    from srbg_api.pdf_processing.parser import ParsedPdfDocument

_DOCUMENT_NUMBER_PATTERN = re.compile(
    r"(?:中华人民共和国应急管理部|国家安全生产监督管理总局)\s*令\s*第\s*"
    r"[〇零一二三四五六七八九十百\d]+\s*号"
)


@dataclass(frozen=True, slots=True)
class HtmlParagraph:
    paragraph_id: str
    text: str


@dataclass(frozen=True, slots=True)
class ParsedEvidence:
    excerpt: str
    excerpt_sha256: str
    original_url: str
    paragraph_id: str | None = None
    char_start: int | None = None
    char_end: int | None = None
    locator_type: str = "HTML_PARAGRAPH"
    page_number: int | None = None
    block_index: int | None = None
    table_index: int | None = None
    row_index: int | None = None
    column_index: int | None = None
    bbox_mpt: tuple[int, int, int, int] | None = None
    confidence_bps: int | None = None


@dataclass(frozen=True, slots=True)
class ParsedClaim:
    claim_type: str
    subject: str
    predicate: str
    literal_value: str
    evidence: tuple[ParsedEvidence, ...]
    confidence_bps: int | None = None


@dataclass(frozen=True, slots=True)
class ParsedSafetyRegulation:
    document_version_id: str
    canonical_url: str
    title: str
    issuing_authority: str
    document_number: str
    published_at: datetime
    regulation_status: str
    classification: str
    paragraphs: tuple[HtmlParagraph, ...]
    claims: tuple[ParsedClaim, ...]
    effective_at: datetime | None = None
    pdf_document: "ParsedPdfDocument | None" = None
    parser_name: str = "mem_safety_regulation_html"
    parser_version: str = "1.0.0"


class _DetailParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.meta: dict[str, str] = {}
        self._trs_depth = 0
        self._paragraph_depth = 0
        self._paragraph_text: list[str] = []
        self.paragraph_texts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag == "meta" and values.get("name") and values.get("content"):
            self.meta[str(values["name"])] = str(values["content"])
        if tag == "div":
            classes = (values.get("class") or "").split()
            if self._trs_depth > 0:
                self._trs_depth += 1
            elif "TRS_Editor" in classes:
                self._trs_depth = 1
        elif tag == "p" and self._trs_depth > 0:
            self._paragraph_depth = 1
            self._paragraph_text = []
        elif self._paragraph_depth > 0:
            self._paragraph_depth += 1

    def handle_data(self, data: str) -> None:
        if self._paragraph_depth > 0:
            self._paragraph_text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if self._paragraph_depth > 0:
            if tag == "p" and self._paragraph_depth == 1:
                text = _normalize_text("".join(self._paragraph_text))
                if text:
                    self.paragraph_texts.append(text)
                self._paragraph_depth = 0
                self._paragraph_text = []
            else:
                self._paragraph_depth -= 1
        if tag == "div" and self._trs_depth > 0 and self._paragraph_depth == 0:
            self._trs_depth -= 1


class MemSafetyRegulationParser:
    parser_name = "mem_safety_regulation_html"
    parser_version = "1.0.0"

    def parse(
        self,
        content: bytes,
        *,
        document_version_id: str,
        canonical_url: str,
    ) -> ParsedSafetyRegulation:
        parser = _DetailParser()
        parser.feed(content.decode("utf-8"))
        paragraphs = tuple(
            HtmlParagraph(paragraph_id=f"html-p-{index:04d}", text=text)
            for index, text in enumerate(parser.paragraph_texts, start=1)
        )
        if not paragraphs:
            raise ValueError("MEM detail page does not contain TRS_Editor paragraphs")

        title = _required_meta(parser.meta, "ArticleTitle")
        authority = _required_meta(parser.meta, "ContentSource")
        if parser.meta.get("ColumnName") != "规章":
            raise ValueError("MEM page is not in the controlled regulation column")
        published_local = datetime.strptime(
            _required_meta(parser.meta, "PubDate"), "%Y-%m-%d %H:%M:%S"
        ).replace(tzinfo=ZoneInfo("Asia/Shanghai"))
        published_at = published_local.astimezone(UTC)

        number_evidence = next(
            (
                (paragraph, match)
                for paragraph in paragraphs
                if (match := _DOCUMENT_NUMBER_PATTERN.search(paragraph.text)) is not None
            ),
            None,
        )
        if number_evidence is None:
            raise ValueError("MEM regulation document number paragraph is missing")
        subtitle, number_match = number_evidence
        number_excerpt = number_match.group(0)
        document_number = re.sub(r"\s+", "", number_excerpt)

        title_paragraph = _paragraph_containing(paragraphs, title)
        authority_paragraph = _paragraph_containing(paragraphs, authority)
        published_date_pattern = re.compile(
            rf"{published_local.year}\s*年\s*{published_local.month}\s*月\s*"
            rf"{published_local.day}\s*日"
        )
        published_evidence = next(
            (
                (paragraph, match)
                for paragraph in paragraphs
                if (match := published_date_pattern.search(paragraph.text)) is not None
            ),
            None,
        )
        if published_evidence is None:
            raise ValueError("MEM regulation publication date evidence is missing")
        published_paragraph, published_match = published_evidence
        published_excerpt = published_match.group(0)

        claims = (
            _claim(
                "title",
                title,
                "has_title",
                title,
                title_paragraph,
                title,
                canonical_url,
            ),
            _claim(
                "issuing_authority",
                title,
                "issued_by",
                authority,
                authority_paragraph,
                authority,
                canonical_url,
            ),
            _claim(
                "document_number",
                title,
                "has_document_number",
                document_number,
                subtitle,
                number_excerpt,
                canonical_url,
            ),
            _claim(
                "published_at",
                title,
                "published_on",
                published_at.isoformat(),
                published_paragraph,
                published_excerpt,
                canonical_url,
            ),
        )
        return ParsedSafetyRegulation(
            document_version_id=document_version_id,
            canonical_url=canonical_url,
            title=title,
            issuing_authority=authority,
            document_number=document_number,
            published_at=published_at,
            regulation_status="UNKNOWN",
            classification="DEPARTMENT_RULE",
            paragraphs=paragraphs,
            claims=claims,
        )


def _required_meta(meta: dict[str, str], name: str) -> str:
    value = _normalize_text(meta.get(name, ""))
    if not value:
        raise ValueError(f"MEM detail page is missing {name}")
    return value


def _normalize_text(value: str) -> str:
    return " ".join(value.replace("\xa0", " ").split())


def _paragraph_containing(paragraphs: tuple[HtmlParagraph, ...], excerpt: str) -> HtmlParagraph:
    paragraph = next((item for item in paragraphs if excerpt in item.text), None)
    if paragraph is None:
        raise ValueError(f"evidence excerpt is missing from numbered paragraphs: {excerpt}")
    return paragraph


def _claim(
    claim_type: str,
    subject: str,
    predicate: str,
    literal_value: str,
    paragraph: HtmlParagraph,
    excerpt: str,
    original_url: str,
) -> ParsedClaim:
    start = paragraph.text.index(excerpt)
    evidence = ParsedEvidence(
        paragraph_id=paragraph.paragraph_id,
        char_start=start,
        char_end=start + len(excerpt),
        excerpt=excerpt,
        excerpt_sha256=sha256(excerpt.encode()).hexdigest(),
        original_url=original_url,
    )
    return ParsedClaim(
        claim_type=claim_type,
        subject=subject,
        predicate=predicate,
        literal_value=literal_value,
        evidence=(evidence,),
    )
