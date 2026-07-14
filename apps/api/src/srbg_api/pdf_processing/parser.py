"""PyMuPDF parser producing safe previews and stable page-addressed evidence blocks."""

from __future__ import annotations

from dataclasses import dataclass, replace
from hashlib import sha256
from statistics import median
from typing import Any, cast

import pymupdf  # type: ignore[import-untyped]

from srbg_api.pdf_processing.normalization import (
    PageTextBlock,
    normalize_document,
    normalize_text,
)
from srbg_api.pdf_processing.ocr import OcrAdapter


@dataclass(frozen=True, slots=True)
class ParsedTextBlock:
    block_index: int
    kind: str
    text_source: str
    text: str
    normalized_text: str
    text_sha256: str
    bbox_mpt: tuple[int, int, int, int]
    confidence_bps: int | None = None


@dataclass(frozen=True, slots=True)
class ParsedTableCell:
    table_index: int
    row_index: int
    column_index: int
    text: str
    text_sha256: str
    bbox_mpt: tuple[int, int, int, int]
    confidence_bps: int | None = None


@dataclass(frozen=True, slots=True)
class ParsedPage:
    page_number: int
    width_mpt: int
    height_mpt: int
    rotation: int
    text_source: str
    blocks: tuple[ParsedTextBlock, ...]
    table_cells: tuple[ParsedTableCell, ...]
    preview_png: bytes
    preview_sha256: str
    normalized_text_sha256: str


@dataclass(frozen=True, slots=True)
class ParsedPdfDocument:
    pages: tuple[ParsedPage, ...]
    normalized_text: str
    semantic_body: str
    normalized_text_sha256: str
    semantic_body_sha256: str
    metadata_sha256: str
    ocr_page_count: int
    ocr_usable_page_count: int
    low_confidence_critical_count: int
    parser_version: str = "srbg-pymupdf-1.0.0"


class PdfDocumentParser:
    def __init__(
        self,
        *,
        ocr_adapter: OcrAdapter,
        native_text_min_chars: int = 20,
        max_ocr_pages: int = 200,
        max_page_pixels: int = 40_000_000,
    ) -> None:
        self._ocr_adapter = ocr_adapter
        self._native_text_min_chars = native_text_min_chars
        self._max_ocr_pages = max_ocr_pages
        self._max_page_pixels = max_page_pixels

    def parse(self, content: bytes) -> ParsedPdfDocument:
        document = pymupdf.open(stream=content, filetype="pdf")
        try:
            pages: list[ParsedPage] = []
            normalization_pages: list[list[PageTextBlock]] = []
            ocr_page_count = 0
            ocr_usable_count = 0
            low_confidence = 0
            for page_number, page in enumerate(document, start=1):
                preview = _render_preview(page, self._max_page_pixels)
                blocks = _native_blocks(page)
                native_text = " ".join(block.normalized_text for block in blocks)
                text_source = "NATIVE"
                if len("".join(native_text.split())) < self._native_text_min_chars:
                    ocr_page_count += 1
                    if ocr_page_count > self._max_ocr_pages:
                        raise ValueError("OCR_PAGE_LIMIT")
                    blocks = _ocr_blocks(
                        self._ocr_adapter.recognize(preview, page_number=page_number),
                        page_width_mpt=round(page.rect.width * 1000),
                        page_height_mpt=round(page.rect.height * 1000),
                    )
                    text_source = "OCR"
                    confidences = [
                        block.confidence_bps for block in blocks if block.confidence_bps is not None
                    ]
                    non_whitespace = len("".join(block.normalized_text for block in blocks))
                    if confidences and non_whitespace >= 10 and median(confidences) >= 8000:
                        ocr_usable_count += 1
                    low_confidence += sum(
                        1
                        for block in blocks
                        if block.confidence_bps is not None and block.confidence_bps < 9500
                    )
                normalization_page = [
                    PageTextBlock(
                        text=block.text,
                        y0_ratio=block.bbox_mpt[1] / max(round(page.rect.height * 1000), 1),
                        y1_ratio=block.bbox_mpt[3] / max(round(page.rect.height * 1000), 1),
                    )
                    for block in blocks
                ]
                normalization_pages.append(normalization_page)
                page_text = "\n".join(block.normalized_text for block in blocks)
                pages.append(
                    ParsedPage(
                        page_number=page_number,
                        width_mpt=round(page.rect.width * 1000),
                        height_mpt=round(page.rect.height * 1000),
                        rotation=page.rotation,
                        text_source=text_source,
                        blocks=tuple(blocks),
                        table_cells=tuple(_native_table_cells(page)),
                        preview_png=preview,
                        preview_sha256=sha256(preview).hexdigest(),
                        normalized_text_sha256=sha256(page_text.encode("utf-8")).hexdigest(),
                    )
                )
            normalized = normalize_document(
                normalization_pages,
                metadata=cast(dict[str, object], document.metadata or {}),
            )
            excluded = set(normalized.header_footer_blocks)
            classified_pages = tuple(
                replace(
                    page,
                    blocks=tuple(
                        replace(
                            block,
                            kind=_margin_kind(block, page, excluded),
                        )
                        for block in page.blocks
                    ),
                )
                for page in pages
            )
            return ParsedPdfDocument(
                pages=classified_pages,
                normalized_text=normalized.normalized_text,
                semantic_body=normalized.semantic_body,
                normalized_text_sha256=normalized.normalized_text_sha256,
                semantic_body_sha256=normalized.semantic_body_sha256,
                metadata_sha256=normalized.metadata_sha256,
                ocr_page_count=ocr_page_count,
                ocr_usable_page_count=ocr_usable_count,
                low_confidence_critical_count=low_confidence,
            )
        finally:
            document.close()


def _render_preview(page: pymupdf.Page, max_page_pixels: int) -> bytes:
    pixmap = page.get_pixmap(matrix=pymupdf.Matrix(2, 2), alpha=False)
    if pixmap.width * pixmap.height > max_page_pixels:
        raise ValueError("PDF_PAGE_PIXEL_LIMIT")
    return bytes(pixmap.tobytes("png"))


def _native_blocks(page: pymupdf.Page) -> list[ParsedTextBlock]:
    raw = cast(dict[str, Any], page.get_text("dict", sort=True))
    result: list[ParsedTextBlock] = []
    for raw_block in raw.get("blocks", []):
        lines = raw_block.get("lines", [])
        text = "".join(
            str(span.get("text", "")) for line in lines for span in line.get("spans", [])
        ).strip()
        normalized = normalize_text(text)
        if not normalized:
            continue
        bbox = cast(tuple[float, float, float, float], raw_block["bbox"])
        result.append(
            ParsedTextBlock(
                block_index=len(result),
                kind="BODY",
                text_source="NATIVE",
                text=text,
                normalized_text=normalized,
                text_sha256=sha256(normalized.encode("utf-8")).hexdigest(),
                bbox_mpt=(
                    round(bbox[0] * 1000),
                    round(bbox[1] * 1000),
                    round(bbox[2] * 1000),
                    round(bbox[3] * 1000),
                ),
            )
        )
    return result


def _ocr_blocks(result: Any, *, page_width_mpt: int, page_height_mpt: int) -> list[ParsedTextBlock]:
    blocks: list[ParsedTextBlock] = []
    for word in result.words:
        normalized = normalize_text(word.text)
        if not normalized:
            continue
        bbox = (
            round(word.x0_px / result.image_width_px * page_width_mpt),
            round(word.y0_px / result.image_height_px * page_height_mpt),
            round(word.x1_px / result.image_width_px * page_width_mpt),
            round(word.y1_px / result.image_height_px * page_height_mpt),
        )
        blocks.append(
            ParsedTextBlock(
                block_index=len(blocks),
                kind="BODY",
                text_source="OCR",
                text=word.text,
                normalized_text=normalized,
                text_sha256=sha256(normalized.encode("utf-8")).hexdigest(),
                bbox_mpt=bbox,
                confidence_bps=word.confidence_bps,
            )
        )
    return blocks


def _margin_kind(
    block: ParsedTextBlock,
    page: ParsedPage,
    excluded: set[tuple[int, str]],
) -> str:
    key = (page.page_number, block.normalized_text)
    if key not in excluded:
        return block.kind
    if block.bbox_mpt[3] <= page.height_mpt * 0.1:
        return "HEADER"
    return "FOOTER"


def _native_table_cells(page: pymupdf.Page) -> list[ParsedTableCell]:
    finder_method = getattr(page, "find_tables", None)
    if finder_method is None:
        return []
    try:
        tables = finder_method().tables
    except (AttributeError, RuntimeError, ValueError):
        return []
    result: list[ParsedTableCell] = []
    for table_index, table in enumerate(tables):
        rows = table.extract()
        raw_cells = list(getattr(table, "cells", []))
        column_count = max((len(row) for row in rows), default=0)
        for row_index, row in enumerate(rows):
            for column_index, value in enumerate(row):
                if value is None:
                    continue
                flat_index = row_index * max(column_count, 1) + column_index
                if flat_index >= len(raw_cells) or raw_cells[flat_index] is None:
                    continue
                bbox = raw_cells[flat_index]
                normalized = normalize_text(str(value))
                result.append(
                    ParsedTableCell(
                        table_index=table_index,
                        row_index=row_index,
                        column_index=column_index,
                        text=normalized,
                        text_sha256=sha256(normalized.encode("utf-8")).hexdigest(),
                        bbox_mpt=(
                            round(float(bbox[0]) * 1000),
                            round(float(bbox[1]) * 1000),
                            round(float(bbox[2]) * 1000),
                            round(float(bbox[3]) * 1000),
                        ),
                    )
                )
    return result
