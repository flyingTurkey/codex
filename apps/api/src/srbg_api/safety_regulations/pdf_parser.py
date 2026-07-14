"""Rule-based safety-regulation extraction over page-addressed PDF blocks."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from zoneinfo import ZoneInfo

from srbg_api.pdf_processing.parser import (
    ParsedTextBlock,
    PdfDocumentParser,
)
from srbg_api.safety_regulations.parser import (
    HtmlParagraph,
    ParsedClaim,
    ParsedEvidence,
    ParsedSafetyRegulation,
)

_AUTHORITY = re.compile(r"(?:发布机关|制定机关|Issuing authority)\s*[:\uff1a]\s*(.+)", re.I)
_DOCUMENT_NUMBER = re.compile(r"(?:文号|Document number)\s*[:\uff1a]\s*(.+)", re.I)
_PUBLISHED = re.compile(r"(?:发布日期|Published)\s*[:\uff1a]\s*(\d{4}-\d{2}-\d{2})", re.I)
_EFFECTIVE = re.compile(r"(?:实施日期|施行日期|Effective)\s*[:\uff1a]\s*(\d{4}-\d{2}-\d{2})", re.I)


@dataclass(frozen=True, slots=True)
class _AddressedBlock:
    page_number: int
    block: ParsedTextBlock


class PdfSafetyRegulationParser:
    parser_name = "safety_regulation_pdf"
    parser_version = "1.0.0"

    def __init__(self, document_parser: PdfDocumentParser) -> None:
        self._document_parser = document_parser

    def parse(
        self,
        content: bytes,
        *,
        document_version_id: str,
        canonical_url: str,
    ) -> ParsedSafetyRegulation:
        pdf = self._document_parser.parse(content)
        addressed = tuple(
            _AddressedBlock(page_number=page.page_number, block=block)
            for page in pdf.pages
            for block in page.blocks
            if block.kind not in {"HEADER", "FOOTER"}
        )
        if not addressed:
            raise ValueError("PDF regulation contains no usable text blocks")

        title_block = next(
            (
                item
                for item in addressed
                if re.search(r"规定|办法|通知|REGULATION", item.block.normalized_text, re.I)
                and not _is_labeled_field(item.block.normalized_text)
            ),
            addressed[0],
        )
        title = title_block.block.normalized_text
        authority_block, authority = _required_field(addressed, _AUTHORITY, "issuing authority")
        number_block, document_number = _required_field(
            addressed, _DOCUMENT_NUMBER, "document number"
        )
        published_block, published_value = _required_field(
            addressed, _PUBLISHED, "publication date"
        )
        published_at = _official_date(published_value)
        effective_match = _optional_field(addressed, _EFFECTIVE)
        effective_at = _official_date(effective_match[1]) if effective_match else None

        claim_inputs = [
            ("title", title, "has_title", title, title_block, title),
            (
                "issuing_authority",
                title,
                "issued_by",
                authority,
                authority_block,
                authority,
            ),
            (
                "document_number",
                title,
                "has_document_number",
                document_number,
                number_block,
                document_number,
            ),
            (
                "published_at",
                title,
                "published_on",
                published_at.isoformat(),
                published_block,
                published_value,
            ),
        ]
        if effective_match is not None and effective_at is not None:
            claim_inputs.append(
                (
                    "effective_at",
                    title,
                    "effective_on",
                    effective_at.isoformat(),
                    effective_match[0],
                    effective_match[1],
                )
            )
        claims = tuple(
            _pdf_claim(
                claim_type,
                subject,
                predicate,
                literal_value,
                item,
                excerpt,
                canonical_url,
            )
            for claim_type, subject, predicate, literal_value, item, excerpt in claim_inputs
        )
        paragraphs = tuple(
            HtmlParagraph(
                paragraph_id=f"pdf-p{item.page_number:04d}-b{item.block.block_index:04d}",
                text=item.block.normalized_text,
            )
            for item in addressed
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
            effective_at=effective_at,
            pdf_document=pdf,
            parser_name=self.parser_name,
            parser_version=self.parser_version,
        )


def _is_labeled_field(value: str) -> bool:
    return any(
        pattern.search(value) for pattern in (_AUTHORITY, _DOCUMENT_NUMBER, _PUBLISHED, _EFFECTIVE)
    )


def _required_field(
    blocks: tuple[_AddressedBlock, ...], pattern: re.Pattern[str], label: str
) -> tuple[_AddressedBlock, str]:
    match = _optional_field(blocks, pattern)
    if match is None:
        raise ValueError(f"PDF regulation is missing {label}")
    return match


def _optional_field(
    blocks: tuple[_AddressedBlock, ...], pattern: re.Pattern[str]
) -> tuple[_AddressedBlock, str] | None:
    for item in blocks:
        match = pattern.search(item.block.normalized_text)
        if match is not None:
            return item, match.group(1).strip()
    return None


def _official_date(value: str) -> datetime:
    return (
        datetime.strptime(value, "%Y-%m-%d")
        .replace(tzinfo=ZoneInfo("Asia/Shanghai"))
        .astimezone(UTC)
    )


def _pdf_claim(
    claim_type: str,
    subject: str,
    predicate: str,
    literal_value: str,
    item: _AddressedBlock,
    excerpt: str,
    canonical_url: str,
) -> ParsedClaim:
    evidence = ParsedEvidence(
        excerpt=excerpt,
        excerpt_sha256=sha256(excerpt.encode("utf-8")).hexdigest(),
        original_url=canonical_url,
        locator_type="PDF_OCR" if item.block.text_source == "OCR" else "PDF_TEXT",
        page_number=item.page_number,
        block_index=item.block.block_index,
        bbox_mpt=item.block.bbox_mpt,
        confidence_bps=item.block.confidence_bps,
    )
    return ParsedClaim(
        claim_type=claim_type,
        subject=subject,
        predicate=predicate,
        literal_value=literal_value,
        evidence=(evidence,),
        confidence_bps=item.block.confidence_bps,
    )
